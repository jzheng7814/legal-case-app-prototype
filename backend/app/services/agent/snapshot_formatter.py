"""
Markdown formatter for snapshots - creates human-readable prompts for the LLM.
Ported from scratch/gavel/.../agent/snapshot_formatter.py
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json

from app.services.agent.schemas import Snapshot, DocumentInfo, ActionRecord, Evidence

class SnapshotFormatter:
    """
    Formats snapshots as readable markdown for better LLM comprehension.
    """
    
    @staticmethod
    def format_as_markdown(snapshot: Snapshot) -> str:
        """
        Format snapshot as markdown for the user prompt.
        """
        sections = []
        
        # Header with context
        sections.append(SnapshotFormatter._format_header(snapshot))
        
        # Full action history (if any actions beyond the recent actions limit)
        if len(snapshot.action_tail) > snapshot.recent_actions_detail:
            # We don't implement full history yet in this port to save tokens/complexity, 
            # or we can add it if needed. The scratch code had it.
            pass
        
        # Recent actions (if any) - show history first before current state
        if snapshot.action_tail:
            sections.append(SnapshotFormatter._format_recent_actions(snapshot))
        
        # Current status
        sections.append(SnapshotFormatter._format_status(snapshot))
        
        # Documents section
        sections.append(SnapshotFormatter._format_documents(snapshot))
        
        # Progress section
        sections.append(SnapshotFormatter._format_progress(snapshot))
        
        # Decision prompt
        sections.append(SnapshotFormatter._format_decision_prompt())
        
        return "\n\n".join(sections)
    
    @staticmethod
    def _format_header(snapshot: Snapshot) -> str:
        """Format the header section."""
        header = f"""# Legal Checklist Extraction
**Step {snapshot.run_header.step}**

## Your Task
{snapshot.task.user_instruction}"""

        # Only show additional constraints if there are task-specific ones
        if snapshot.task.constraints:
            header += f"\n## Requirements"
            for constraint in snapshot.task.constraints:
                header += f"\n- {constraint}"
            header += "\n"

        # Add checklist definitions if available
        if snapshot.task.checklist_definitions:
            header += "\n## Checklist Items to Extract"
            for key, description in snapshot.task.checklist_definitions.items():
                header += f"\n- **{key}**: {description}"
        
        return header
    
    @staticmethod
    def _format_status(snapshot: Snapshot) -> str:
        """Format the current status section."""
        checklist = snapshot.checklist
        # Note: In schema, extracted is List[ExtractedValue].
        extracted_count = sum(1 for item in checklist if item.extracted)
        empty_count = sum(1 for item in checklist if not item.extracted)
        total_keys = len(checklist)
        total_values = sum(len(item.extracted) for item in checklist if item.extracted)
        
        # Count "Not Applicable" items - simplistic check
        not_applicable_count = sum(
            1 for item in checklist 
            if len(item.extracted) == 1 and item.extracted[0].value == "Not Applicable"
        )
        
        status = f"""## Current Status
- **Keys with Values**: {extracted_count}/{total_keys}
- **Empty Keys**: {empty_count}/{total_keys}
- **Not Applicable**: {not_applicable_count}/{total_keys}
- **Total Values Extracted**: {total_values}
- **Documents in Corpus**: {len(snapshot.documents)}"""
        
        return status
    
    @staticmethod
    def _calculate_coverage_tokens(token_ranges: list) -> int:
        """Calculate total unique tokens covered by the ranges."""
        if not token_ranges:
            return 0
        
        # Merge overlapping ranges first
        sorted_ranges = sorted(token_ranges, key=lambda x: x[0])
        merged = []
        
        for start, end in sorted_ranges:
            if merged and start <= merged[-1][1]:
                # Overlapping or adjacent - extend the last range
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                # Non-overlapping - add new range
                merged.append((start, end))
        
        # Calculate total covered tokens
        total = sum(end - start for start, end in merged)
        return total
    
    @staticmethod
    def _format_documents(snapshot: Snapshot) -> str:
        """Format the documents section with detailed visit status."""
        if not snapshot.documents:
            return """## Available Documents
No documents discovered yet."""
        
        lines = ["## Available Documents"]
        for doc in snapshot.documents:
            # Determine visit status based on coverage
            ranges = doc.coverage.token_ranges if (doc.coverage and doc.coverage.token_ranges) else []
            
            if doc.visited and ranges:
                covered_tokens = SnapshotFormatter._calculate_coverage_tokens(ranges)
                coverage_percentage = (covered_tokens / doc.token_count * 100) if doc.token_count > 0 else 0
                
                # Classify as fully or partially visited
                if covered_tokens >= doc.token_count:
                    status = "✓ Fully Visited"
                else:
                    status = "◐ Partially Visited"
            else:
                status = "○ Unvisited"
                coverage_percentage = 0
            
            # Format the main document line
            lines.append(f"- **{doc.name}** [{doc.type}] - {doc.token_count:,} tokens - {status}")
            
            # Show token ranges if document has been visited
            if doc.visited and ranges:
                # Show all token ranges without truncation
                range_str = ", ".join([f"{start}-{end}" for start, end in ranges])
                lines.append(f"  Viewed tokens: {range_str} ({coverage_percentage:.0f}% coverage)")
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_progress(snapshot: Snapshot) -> str:
        """Format the progress section with document-level breakdown."""
        checklist = snapshot.checklist
        
        lines = ["## Extraction Progress"]
        
        extracted_items = []
        not_applicable_items = []
        empty_items = []
        
        for item in checklist:
            if not item.extracted:
                empty_items.append(item)
            elif len(item.extracted) == 1 and item.extracted[0].value == "Not Applicable":
                not_applicable_items.append(item)
            else:
                extracted_items.append(item)
        
        # Show keys with extracted values
        if extracted_items:
            lines.append(f"\n**Keys with Extracted Values** ({len(extracted_items)}):")
            for item in extracted_items:
                total_values = len(item.extracted)
                value_text = "value" if total_values == 1 else "values"
                
                # Simplified doc info
                doc_counts = {}
                for val in item.extracted:
                    for ev in val.evidence:
                         doc_counts[ev.source_document] = doc_counts.get(ev.source_document, 0) + 1
                
                doc_info_str = ", ".join([f"{count} from {doc}" for doc, count in doc_counts.items()])
                lines.append(f"- **{item.key}**: {total_values} {value_text} ({doc_info_str})")
        
        # Show Not Applicable items
        if not_applicable_items:
            lines.append(f"\n**Keys Marked as Not Applicable** ({len(not_applicable_items)}):")
            for item in not_applicable_items:
                evidence_doc = item.extracted[0].evidence[0].source_document if item.extracted[0].evidence else "unknown"
                lines.append(f"- **{item.key}**: Not Applicable (evidence from {evidence_doc})")
        
        # Show empty keys
        if empty_items:
            lines.append(f"\n**Keys Not Yet Explored** ({len(empty_items)}):")
            for item in empty_items:
                lines.append(f"- **{item.key}**: Empty")
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_recent_actions(snapshot: Snapshot) -> str:
        """Format recent actions section."""
        recent_actions = snapshot.action_tail
        if not recent_actions:
            return "## Recent Actions\nNo actions yet."
            
        first_step = recent_actions[0].step
        last_step = recent_actions[-1].step
        lines = [f"## Recent Actions (Steps {first_step}-{last_step})"]
        
        for action in recent_actions:
            lines.append(f"Step {action.step}. `{action.tool}`")
            if action.error:
                lines.append(f"   **❌ ERROR**: {action.error}")
            elif action.result_summary:
                # Simple summary
                lines.append(f"   Result: {json.dumps(action.result_summary, default=str)[:200]}...") # Truncated
        
        return "\n".join(lines)

    @staticmethod
    def _format_decision_prompt() -> str:
        return """## Decision Required
Based on the current status and recent actions, what is your next step?
Remember to:
1. Consult the **Decision Policy**.
2. Avoid repeating ineffective actions.
3. Stop only when all keys are filled or no further information can be found.
"""

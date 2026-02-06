"""
Markdown formatter for snapshots - creates human-readable prompts for the LLM.
Ported from scratch/gavel/.../agent/snapshot_formatter.py with doc_id conventions.
"""

from typing import Any
from datetime import datetime
import json

from app.services.agent.schemas import Snapshot, ActionRecord


class SnapshotFormatter:
    """
    Formats snapshots as readable markdown for better LLM comprehension.
    """

    @staticmethod
    def format_as_markdown(snapshot: Snapshot) -> str:
        sections = []

        sections.append(SnapshotFormatter._format_header(snapshot))

        if len(snapshot.action_tail) > snapshot.recent_actions_detail:
            sections.append(SnapshotFormatter._format_full_action_history(snapshot))

        if snapshot.action_tail:
            sections.append(SnapshotFormatter._format_recent_actions(snapshot))

        sections.append(SnapshotFormatter._format_status(snapshot))
        sections.append(SnapshotFormatter._format_documents(snapshot))
        sections.append(SnapshotFormatter._format_progress(snapshot))

        if (
            snapshot.stop_count > 0
            and snapshot.first_stop_step is not None
            and snapshot.run_header.step == snapshot.first_stop_step + 2
        ):
            sections.append(SnapshotFormatter._format_stop_status(snapshot))

        sections.append(SnapshotFormatter._format_decision_prompt())

        return "\n\n".join(sections)

    @staticmethod
    def _format_header(snapshot: Snapshot) -> str:
        header = f"""# Legal Checklist Extraction
**Step {snapshot.run_header.step}**

## Your Task
{snapshot.task.user_instruction}"""

        if snapshot.task.constraints:
            header += "\n## Requirements"
            for constraint in snapshot.task.constraints:
                header += f"\n- {constraint}"
            header += "\n"

        if snapshot.task.checklist_definitions:
            header += "\n## Checklist Items to Extract"
            for key, description in snapshot.task.checklist_definitions.items():
                header += f"\n- **{key}**: {description}"

        return header

    @staticmethod
    def _format_status(snapshot: Snapshot) -> str:
        checklist = snapshot.checklist
        extracted_count = sum(1 for item in checklist if item.extracted)
        empty_count = sum(1 for item in checklist if not item.extracted)
        total_keys = len(checklist)
        total_values = sum(len(item.extracted) for item in checklist if item.extracted)

        not_applicable_count = sum(
            1
            for item in checklist
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
    def _calculate_coverage_units(ranges: list) -> int:
        if not ranges:
            return 0

        sorted_ranges = sorted(ranges, key=lambda x: x[0])
        merged = []

        for start, end in sorted_ranges:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))

        total = sum(end - start for start, end in merged)
        return total

    @staticmethod
    def _format_documents(snapshot: Snapshot) -> str:
        if not snapshot.documents:
            return """## Available Documents
No documents discovered yet."""

        lines = ["## Available Documents"]
        for doc in snapshot.documents:
            ranges = doc.coverage.token_ranges if (doc.coverage and doc.coverage.token_ranges) else []

            if doc.visited and ranges:
                covered_units = SnapshotFormatter._calculate_coverage_units(ranges)
                coverage_percentage = (covered_units / doc.token_count * 100) if doc.token_count > 0 else 0

                if covered_units >= doc.token_count:
                    status = "✓ Fully Visited"
                else:
                    status = "◐ Partially Visited"
            else:
                status = "○ Unvisited"
                coverage_percentage = 0

            lines.append(
                f"- **{doc.name}** (ID {doc.id}) [{doc.type}] - {doc.token_count:,} sentences - {status}"
            )

            if doc.visited and ranges:
                range_str = ", ".join([f"{start}-{end}" for start, end in ranges])
                lines.append(f"  Viewed sentences: {range_str} ({coverage_percentage:.0f}% coverage)")

        return "\n".join(lines)

    @staticmethod
    def _format_progress(snapshot: Snapshot) -> str:
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

        if extracted_items:
            lines.append(f"\n**Keys with Extracted Values** ({len(extracted_items)}):")
            for item in extracted_items:
                doc_values = {}
                for extracted in item.extracted:
                    unique_docs_for_value = set()
                    for evidence in extracted.evidence:
                        unique_docs_for_value.add(evidence.source_document)

                    for doc_id in unique_docs_for_value:
                        if doc_id not in doc_values:
                            doc_values[doc_id] = 0
                        doc_values[doc_id] += 1

                total_values = len(item.extracted)
                value_text = "value" if total_values == 1 else "values"
                doc_info = ", ".join([f"{count} from {doc_id}" for doc_id, count in doc_values.items()])
                lines.append(f"- **{item.key}**: {total_values} {value_text} ({doc_info})")

        if not_applicable_items:
            lines.append(f"\n**Keys Marked as Not Applicable** ({len(not_applicable_items)}):")
            for item in not_applicable_items:
                evidence_doc = (
                    item.extracted[0].evidence[0].source_document
                    if item.extracted[0].evidence
                    else "unknown"
                )
                lines.append(f"- **{item.key}**: Not Applicable (evidence from {evidence_doc})")

        if empty_items:
            lines.append(f"\n**Keys Not Yet Explored** ({len(empty_items)}):")
            for item in empty_items:
                lines.append(f"- **{item.key}**: Empty")

        return "\n".join(lines)

    @staticmethod
    def _format_recent_actions(snapshot: Snapshot) -> str:
        recent_actions = (
            snapshot.action_tail[-snapshot.recent_actions_detail :]
            if len(snapshot.action_tail) > snapshot.recent_actions_detail
            else snapshot.action_tail
        )

        if len(snapshot.action_tail) > snapshot.recent_actions_detail and recent_actions:
            first_step = recent_actions[0].step
            last_step = recent_actions[-1].step
            lines = [f"## Recent Actions (Steps {first_step}-{last_step} with Detailed Results)"]
        elif recent_actions:
            first_step = recent_actions[0].step
            last_step = recent_actions[-1].step
            lines = [f"## Recent Actions (Steps {first_step}-{last_step})"]
        else:
            lines = ["## Recent Actions"]

        for action in recent_actions:
            step_number = action.step
            action_line = SnapshotFormatter._format_action_line(action, step_number)
            lines.append(action_line)

            if action.result_summary:
                result_lines = SnapshotFormatter._format_action_result(
                    action.result_summary,
                    action.tool,
                    indent="   ",
                    action=action,
                )
                lines.extend(result_lines)
            elif action.error:
                lines.append(f"   **❌ ERROR**: {action.error}")

        return "\n".join(lines)

    @staticmethod
    def _format_action_line(action: ActionRecord, step_number: int) -> str:
        line_parts = [f"Step {step_number}. `{action.tool}`"]

        if action.tool == "search_document_regex":
            if action.target:
                doc_ids = action.target.get("doc_ids", [])
                doc_id = action.target.get("doc_id")
                pattern = action.target.get("pattern", "")

                if doc_ids and len(doc_ids) > 0:
                    docs_str = ", ".join([str(doc_id) for doc_id in doc_ids])
                    line_parts.append(f"on [{docs_str}] (pattern: \"{pattern}\")")
                elif doc_id == -1:
                    line_parts.append(f"on all documents (pattern: \"{pattern}\")")
                elif doc_id is not None:
                    line_parts.append(f"on {doc_id} (pattern: \"{pattern}\")")

        elif action.tool == "read_document":
            if action.target:
                doc_id = action.target.get("doc_id")
                start = action.target.get("start_sentence", 0)
                end = action.target.get("end_sentence", 0)
                line_parts.append(f"on {doc_id} (sentences {start}-{end})")

        elif action.tool in ["update_checklist", "append_checklist"]:
            if action.changed_keys:
                keys_str = ", ".join(action.changed_keys[:3])
                if len(action.changed_keys) > 3:
                    keys_str += f", +{len(action.changed_keys)-3} more"
                line_parts.append(f"({keys_str})")
            elif action.target and "patch" in action.target:
                patch = action.target.get("patch", [])
                keys = [p.get("key") for p in patch if isinstance(p, dict) and "key" in p]
                if keys:
                    keys_str = ", ".join(keys[:3])
                    if len(keys) > 3:
                        keys_str += f", +{len(keys)-3} more"
                    line_parts.append(f"({keys_str})")

        elif action.tool == "get_checklist":
            if action.target:
                item = action.target.get("item", "all")
                if item != "all":
                    line_parts.append(f"(item: {item})")

        elif action.tool in ["parse_error", "validation_error"]:
            if action.target and isinstance(action.target, dict):
                error_msg = action.target.get("error", "Unknown error")
                if len(error_msg) > 60:
                    error_msg = error_msg[:60] + "..."
                line_parts.append(f"- {error_msg}")

        elif action.tool == "stop":
            if action.target and isinstance(action.target, dict):
                reason = action.target.get("reason", "No reason provided")
                line_parts.append(f"- {reason}")

        if action.auto_generated:
            line_parts.append("[AUTO-GENERATED]")

        if action.error:
            line_parts.append("**❌ ERROR**")
        elif action.validation_errors:
            line_parts.append(f"**⚠️ {len(action.validation_errors)} validation error(s)**")

        return " ".join(line_parts)

    @staticmethod
    def _format_action_result(result: dict, tool: str, indent: str = "", action: ActionRecord | None = None) -> list[str]:
        TOOLS_WITH_FULL_RESULTS = {
            "read_document",
            "search_document_regex",
            "get_checklist",
            "append_checklist",
            "update_checklist",
        }

        lines = []

        if "error" in result:
            lines.append(f"{indent}**❌ ERROR**: {result['error']}")
            other_fields = {k: v for k, v in result.items() if k != "error"}
            if other_fields:
                lines.append(f"{indent}Additional info:")
                json_str = json.dumps(other_fields, indent=2, default=str)
                indented_json = "\n".join(f"{indent}{line}" for line in json_str.split("\n"))
                lines.append(f"{indent}```json\n{indented_json}\n{indent}```")
            return lines

        if tool in TOOLS_WITH_FULL_RESULTS:
            if tool == "read_document":
                full_text = result.get("text", "")
                lines.append(
                    f"{indent}Read from **{result.get('doc_id', 'unknown')}** (sentences {result.get('start_sentence', 0)}-{result.get('end_sentence', 0)}):"
                )
                lines.append(f"{indent}```")
                for text_line in full_text.split("\n"):
                    lines.append(f"{indent}{text_line}")
                lines.append(f"{indent}```")

            elif tool == "search_document_regex":
                if "results" in result:
                    doc_results = result.get("results", [])
                    total_matches = result.get("total_matches", 0)
                    docs_searched = result.get("documents_searched", [])

                    lines.append(
                        f"{indent}Search in {len(docs_searched)} document{'s' if len(docs_searched) != 1 else ''} found {total_matches} total match{'es' if total_matches != 1 else ''}:"
                    )

                    matches_shown = 0
                    max_total_matches = 20

                    for doc_result in doc_results:
                        if matches_shown >= max_total_matches:
                            break

                        doc_id = doc_result.get("doc_id", "unknown")
                        matches = doc_result.get("matches", [])

                        matches_to_show = min(len(matches), max_total_matches - matches_shown)

                        if matches_to_show > 0:
                            lines.append(
                                f"{indent}**{doc_id}** ({len(matches)} match{'es' if len(matches) != 1 else ''}):"
                            )

                            for i, match in enumerate(matches[:matches_to_show], 1):
                                snippet = match.get("snippet", "")
                                lines.append(
                                    f"{indent}  Match {i} (sentences {match.get('start_sentence', 0)}-{match.get('end_sentence', 0)}):"
                                )
                                lines.append(f"{indent}  ```")
                                for snippet_line in snippet.split("\n"):
                                    lines.append(f"{indent}  {snippet_line}")
                                lines.append(f"{indent}  ```")
                                matches_shown += 1

                    if total_matches > max_total_matches:
                        lines.append(
                            f"{indent}**Showing first {max_total_matches} of {total_matches} total matches.**"
                        )
                        remaining_summary = []
                        for doc_result in doc_results:
                            doc_id = doc_result.get("doc_id", "unknown")
                            doc_matches = len(doc_result.get("matches", []))
                            shown_count = 0
                            for shown_doc in doc_results:
                                if shown_doc.get("doc_id") == doc_id:
                                    shown_count = min(
                                        doc_matches,
                                        max_total_matches
                                        - sum(len(d.get("matches", [])) for d in doc_results[: doc_results.index(shown_doc)]),
                                    )
                                    shown_count = max(0, shown_count)
                                    break
                            remaining = doc_matches - shown_count
                            if remaining > 0:
                                remaining_summary.append(f"{remaining} in {doc_id}")

                        if remaining_summary:
                            lines.append(f"{indent}Remaining matches: {', '.join(remaining_summary[:5])}")
                            if len(remaining_summary) > 5:
                                lines.append(
                                    f"{indent}... and {len(remaining_summary) - 5} more documents with matches"
                                )
                            lines.append(f"{indent}Search individual documents for complete results.")

            elif tool == "get_checklist":
                stats = result.get("completion_stats", {})
                total_keys = stats.get("total", stats.get("filled", 0) + stats.get("empty", 0))
                lines.append(
                    f"{indent}Checklist Status: {stats.get('filled', 0)}/{total_keys} filled, {stats.get('empty', 0)} empty"
                )

                checklist = result.get("checklist", [])
                filled_items = [item for item in checklist if item.get("extracted")]
                if filled_items:
                    lines.append(f"{indent}Filled keys:")
                    for item in filled_items[:10]:
                        key = item.get("key", "unknown")
                        value_count = len(item.get("extracted", []))
                        lines.append(f"{indent}- {key}: {value_count} value{'s' if value_count != 1 else ''}")

            elif tool in ["append_checklist", "update_checklist"]:
                updated_keys = result.get("updated_keys", result.get("appended_keys", []))
                operation = "updated" if tool == "update_checklist" else "appended"

                if updated_keys:
                    lines.append(
                        f"{indent}→ Successfully {operation} {len(updated_keys)} key{'s' if len(updated_keys) != 1 else ''}: {', '.join(updated_keys)}"
                    )

                    if action and action.target and "patch" in action.target:
                        patch = action.target.get("patch", [])
                        lines.append(f"{indent}")
                        lines.append(f"{indent}**Extracted Values:**")

                        for patch_item in patch:
                            key = patch_item.get("key", "unknown")
                            extracted_items = patch_item.get("extracted", [])

                            if extracted_items:
                                lines.append(f"{indent}• **{key}**:")

                                for idx, extracted in enumerate(extracted_items, 1):
                                    value = extracted.get("value", "")
                                    evidence_list = extracted.get("evidence", [])

                                    if value:
                                        lines.append(f"{indent}  {idx}. {value}")

                                    for ev_idx, ev in enumerate(evidence_list, 1):
                                        text = ev.get("text", "")
                                        source_document = ev.get("source_document", "unknown")
                                        location = ev.get("location", "unknown")
                                        lines.append(
                                            f"{indent}     Evidence {ev_idx}: [{source_document}] {location}"
                                        )
                                        if text:
                                            lines.append(f"{indent}     \"{text}\"")

        return lines

    @staticmethod
    def _format_full_action_history(snapshot: Snapshot) -> str:
        action_history = snapshot.action_tail
        if not action_history:
            return "## Full Action History\nNo actions yet."

        lines = ["## Full Action History"]
        for action in action_history:
            snippet = SnapshotFormatter._format_result_snippet(action)
            if snippet:
                lines.append(f"Step {action.step}. `{action.tool}`: {snippet}")
            else:
                lines.append(f"Step {action.step}. `{action.tool}`")

        return "\n".join(lines)

    @staticmethod
    def _format_result_snippet(action: ActionRecord) -> str:
        if action.tool == "stop":
            reason = ""
            if action.target and isinstance(action.target, dict):
                reason = action.target.get("reason", "No reason provided")
            if len(reason) > 60:
                reason = reason[:60] + "..."
            return f"Stop attempt: {reason}"

        if action.tool in ["parse_error", "validation_error"]:
            error_msg = ""
            if action.target and isinstance(action.target, dict):
                error_msg = action.target.get("error", "Unknown error")
            elif action.error:
                error_msg = action.error
            else:
                error_msg = "Parse/validation failure"

            if len(error_msg) > 60:
                error_msg = error_msg[:60] + "..."
            return f"**ERROR**: {error_msg}"

        if not action.result_summary or action.error:
            if action.error:
                error_msg = str(action.error)
                if len(error_msg) > 60:
                    error_msg = error_msg[:60] + "..."
                return f"Error: {error_msg}"
            return ""

        result = action.result_summary

        if action.tool == "list_documents":
            docs = result.get("documents", [])
            return f"Found {len(docs)} documents"

        if action.tool == "search_document_regex":
            total_matches = result.get("total_matches", 0)
            docs_searched = result.get("documents_searched", [])
            if len(docs_searched) == 1:
                doc_id = docs_searched[0] if docs_searched else "unknown"
                return f"Found {total_matches} matches in {doc_id}"
            if len(docs_searched) > 1:
                return f"Found {total_matches} matches across {len(docs_searched)} documents"
            return "Found 0 matches"

        if action.tool == "read_document":
            start = result.get("start_sentence", 0)
            end = result.get("end_sentence", 0)
            doc_id = result.get("doc_id", "unknown")
            return f"Read {end - start} sentences from {doc_id}"

        if action.tool == "get_checklist":
            stats = result.get("completion_stats", {})
            total_keys = stats.get("total", stats.get("filled", 0) + stats.get("empty", 0))
            return f"Checklist: {stats.get('filled', 0)}/{total_keys} filled"

        if action.tool in ["update_checklist", "append_checklist"]:
            updated = result.get("updated_keys", [])
            if updated:
                return f"Updated {len(updated)} key(s)"
            return "No updates made"

        return ""

    @staticmethod
    def _format_stop_status(snapshot: Snapshot) -> str:
        message = """## Stop Status
The model previously attempted to stop. The checklist was retrieved automatically.
Review the results and decide whether to continue extracting or confirm stopping.
"""
        return message

    @staticmethod
    def _format_decision_prompt() -> str:
        return """## Decision Required
Based on the current status and recent actions, what is your next step?
Remember to:
1. Consult the **Decision Policy**.
2. Avoid repeating ineffective actions.
3. Stop only when all keys are filled or no further information can be found.
"""

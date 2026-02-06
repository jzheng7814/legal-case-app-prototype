#!/usr/bin/env python3
"""
Scratch script to verify verbatim evidence snippets against case documents.
Whitespace-normalized, case-insensitive matching with match counts and indices.
"""

from __future__ import annotations

import sys
from typing import Dict, List, Tuple

from app.db.models import CaseDocument, ChecklistItem
from app.db.session import get_session, init_db


def normalize_with_map(text: str) -> Tuple[str, List[int]]:
    """Lowercase + collapse whitespace to single spaces, returning index map to original."""
    norm_chars: List[str] = []
    index_map: List[int] = []
    in_ws = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if not in_ws:
                norm_chars.append(" ")
                index_map.append(i)
                in_ws = True
            continue
        in_ws = False
        norm_chars.append(ch.lower())
        index_map.append(i)

    # Strip leading/trailing spaces to keep evidence/content consistent
    while norm_chars and norm_chars[0] == " ":
        norm_chars.pop(0)
        index_map.pop(0)
    while norm_chars and norm_chars[-1] == " ":
        norm_chars.pop()
        index_map.pop()

    return "".join(norm_chars), index_map


def normalize(text: str) -> str:
    """Normalize text (lowercase + collapse whitespace)."""
    return normalize_with_map(text)[0]


def find_all(haystack: str, needle: str) -> List[int]:
    """Return all (possibly overlapping) match indices."""
    if not needle:
        return []
    indices: List[int] = []
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            break
        indices.append(idx)
        start = idx + 1
    return indices


def truncate(text: str, limit: int = 140) -> str:
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def main() -> int:
    case_id = "46094"
    if len(sys.argv) > 1:
        case_id = sys.argv[1]

    init_db()
    session = get_session()
    try:
        documents = (
            session.query(CaseDocument)
            .filter(CaseDocument.case_id == case_id)
            .all()
        )
        items = (
            session.query(ChecklistItem)
            .filter(ChecklistItem.case_id == case_id)
            .order_by(ChecklistItem.item_index.asc())
            .all()
        )
    finally:
        session.close()

    if not items:
        print(f"ERROR: case_id {case_id} not found in checklist data")
        return 1
    if not documents:
        print(f"ERROR: case_id {case_id} not found in documents data")
        return 1

    doc_by_id: Dict[int, CaseDocument] = {doc.document_id: doc for doc in documents}

    norm_cache: Dict[int, Tuple[str, List[int]]] = {}

    total = 0
    matched = 0
    unmatched_records = []

    print(f"Case {case_id} | Evidence checks: {len(items)}")
    print("-" * 80)

    for item in items:
        total += 1
        bin_id = item.bin_id
        value = item.value
        doc_id = item.document_id
        ev_text = item.text or ""

        doc = doc_by_id.get(doc_id)
        title = doc.title if doc else None
        content = doc.content if doc else None

        if not doc:
            print(f"NO_MATCH\tbinId={bin_id}\tdocId={doc_id}\treason=doc_not_found\tev=\"{truncate(ev_text)}\"")
            unmatched_records.append((bin_id, doc_id, title, truncate(ev_text)))
            continue
        if not content:
            print(f"NO_MATCH\tbinId={bin_id}\tdocId={doc_id}\ttitle={title}\treason=empty_content\tev=\"{truncate(ev_text)}\"")
            unmatched_records.append((bin_id, doc_id, title, truncate(ev_text)))
            continue

        if doc_id not in norm_cache:
            norm_cache[doc_id] = normalize_with_map(content)
        norm_content, index_map = norm_cache[doc_id]

        norm_ev = normalize(ev_text)
        if not norm_ev:
            print(f"NO_MATCH\tbinId={bin_id}\tdocId={doc_id}\ttitle={title}\treason=empty_evidence_text")
            unmatched_records.append((bin_id, doc_id, title, truncate(ev_text)))
            continue

        match_indices = find_all(norm_content, norm_ev)
        if match_indices:
            matched += 1
            orig_indices = []
            for idx in match_indices:
                if 0 <= idx < len(index_map):
                    orig_indices.append(index_map[idx])
                else:
                    orig_indices.append(None)
            print(
                "MATCH"
                f"\tbinId={bin_id}"
                f"\tdocId={doc_id}"
                f"\ttitle={title}"
                f"\tcount={len(match_indices)}"
                f"\tnorm_indices={match_indices}"
                f"\torig_indices={orig_indices}"
                f"\tvalue=\"{truncate(str(value))}\""
                f"\tev=\"{truncate(ev_text)}\""
            )
        else:
            print(
                "NO_MATCH"
                f"\tbinId={bin_id}"
                f"\tdocId={doc_id}"
                f"\ttitle={title}"
                f"\tvalue=\"{truncate(str(value))}\""
                f"\tev=\"{truncate(ev_text)}\""
            )
            unmatched_records.append((bin_id, doc_id, title, truncate(ev_text)))

    print("-" * 80)
    unmatched = total - matched
    match_rate = (matched / total * 100) if total else 0.0
    print(f"Summary for case {case_id}:")
    print(f"  Total evidence entries: {total}")
    print(f"  Matched: {matched}")
    print(f"  Unmatched: {unmatched}")
    print(f"  Match rate: {match_rate:.2f}%")
    if unmatched_records:
        print("  Unmatched evidence list:")
        for bin_id, doc_id, title, ev in unmatched_records:
            print(f"    binId={bin_id}\tdocId={doc_id}\ttitle={title}\tev=\"{ev}\"")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

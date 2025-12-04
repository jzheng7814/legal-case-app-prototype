import React, { useCallback, useMemo, useState } from 'react';
import { ClipboardList } from 'lucide-react';
import { SUMMARY_DOCUMENT_ID } from '../constants';

const BIN_LABELS = {
    basic_info: 'Basic Case Information',
    legal_foundation: 'Legal Foundation',
    judge: 'Judge Information',
    related_cases: 'Related Cases',
    filings_proceedings: 'Filings and Proceedings',
    decrees: 'Decrees',
    settlements: 'Settlements',
    monitoring: 'Monitoring',
    context: 'Context'
};

const formatLabel = (label = '') =>
    label.replace(/_/g, ' ').replace(/\s+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()).trim();

const normaliseChecklistEntries = (payload) => {
    if (!payload) {
        return [];
    }

    const coerceExtraction = (entry = {}) => ({
        reasoning: entry?.extraction?.reasoning ?? entry?.result?.reasoning ?? '',
        extracted: Array.isArray(entry?.extraction?.extracted ?? entry?.result?.extracted)
            ? entry.extraction?.extracted ?? entry.result?.extracted
            : []
    });

    const mapEntry = (entry = {}) => {
        const binId = entry?.binId ?? entry?.bin_id ?? entry?.id ?? entry?.itemName ?? entry?.item_name ?? entry?.name;
        const extraction = coerceExtraction(entry);
        if (!binId) {
            return null;
        }
        return {
            itemName: binId,
            label: BIN_LABELS[binId] ?? formatLabel(binId),
            extraction
        };
    };

    if (Array.isArray(payload)) {
        const hasBins = payload.some((entry) => entry && (entry.binId || entry.bin_id || entry.id));
        const hasItems = payload.some((entry) => entry && (entry.itemName || entry.item_name || entry.name));
        if (hasBins || hasItems) {
            return payload.map(mapEntry).filter(Boolean);
        }
    }

    if (Array.isArray(payload?.bins)) {
        return payload.bins.map(mapEntry).filter(Boolean);
    }

    if (Array.isArray(payload?.items)) {
        return payload.items.map(mapEntry).filter(Boolean);
    }

    return [];
};

const resolveEvidenceMeta = (evidenceItem = {}) => {
    let documentId = evidenceItem.documentId ?? evidenceItem.document_id ?? null;
    if (typeof documentId === 'string') {
        const trimmed = documentId.trim();
        if (trimmed) {
            if (trimmed.toLowerCase() === 'summary') {
                documentId = SUMMARY_DOCUMENT_ID;
            } else if (trimmed.toLowerCase().startsWith('document ')) {
                documentId = Number.parseInt(trimmed.slice(9).trim(), 10);
            } else {
                documentId = Number.parseInt(trimmed, 10);
            }
        }
    }
    if (Number.isNaN(documentId)) {
        documentId = null;
    }
    const rawStart = evidenceItem.startOffset ?? evidenceItem.start_offset ?? null;
    const rawEnd = evidenceItem.endOffset ?? evidenceItem.end_offset ?? null;
    const parsedStart =
        typeof rawStart === 'number' ? rawStart : rawStart != null ? Number.parseInt(rawStart, 10) : null;
    const parsedEnd = typeof rawEnd === 'number' ? rawEnd : rawEnd != null ? Number.parseInt(rawEnd, 10) : null;
    const startOffset = Number.isFinite(parsedStart) ? parsedStart : null;
    const endOffset = Number.isFinite(parsedEnd) ? parsedEnd : null;
    const isVerified = evidenceItem.verified !== false;
    return { documentId, startOffset, endOffset, isVerified };
};

const ChecklistColumn = ({
    title,
    items = [],
    onAdd,
    source,
    onEvidenceNavigate,
    resolveDocumentTitle = () => null,
    resolveDocumentText = () => null
}) => {
    const entries = useMemo(() => normaliseChecklistEntries(items), [items]);
    const [expandedEvidence, setExpandedEvidence] = useState(() => new Set());

    const toggleEvidence = useCallback((key) => {
        setExpandedEvidence((current) => {
            const next = new Set(current);
            if (next.has(key)) {
                next.delete(key);
            } else {
                next.add(key);
            }
            return next;
        });
    }, []);

    const extractEvidenceText = useCallback(
        (documentId, startOffset, endOffset, fallbackText) => {
            const text = resolveDocumentText(documentId);
            if (
                text &&
                startOffset != null &&
                endOffset != null &&
                endOffset > startOffset &&
                endOffset <= text.length
            ) {
                return text.slice(startOffset, endOffset);
            }
            return typeof fallbackText === 'string' ? fallbackText : null;
        },
        [resolveDocumentText]
    );

    return (
        <div className="flex flex-col min-h-0 bg-[var(--color-surface-panel)] border border-[var(--color-border)] rounded-lg shadow-sm">
            <div className="flex items-center gap-2 border-b border-[var(--color-border)] px-3 py-2">
                <ClipboardList className="h-4 w-4 text-[var(--color-text-muted)]" />
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">{title}</h3>
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-2 space-y-3">
                {entries.length === 0 && (
                    <p className="text-xs text-[var(--color-text-muted)]">No checklist items available yet.</p>
                )}
                {entries.map(({ itemName, label, extraction }) => {
                    const extracted = Array.isArray(extraction?.extracted) ? extraction.extracted : [];
                    return (
                        <div key={itemName} className="rounded border border-[var(--color-border)] bg-[var(--color-surface-panel-alt)] px-3 py-2">
                            <div className="flex items-start justify-between gap-2">
                                <div>
                                    <p className="text-sm font-semibold text-[var(--color-text-primary)]">{label ?? formatLabel(itemName)}</p>
                                </div>
                            </div>
                            {extracted.length === 0 ? (
                                <p className="mt-2 text-xs italic text-[var(--color-text-muted)]">No extracted values.</p>
                            ) : (
                                <div className="mt-2 space-y-2">
                                    {extracted.map((entry, index) => (
                                        <div key={`${itemName}-${index}`} className="rounded bg-[var(--color-surface-panel)] p-2 shadow-sm border border-[var(--color-border)]">
                                            <div className="flex items-start justify-between gap-2">
                                                <p className="text-sm text-[var(--color-text-primary)]">{entry.value || '--'}</p>
                                                <button
                                                    type="button"
                                                    onClick={() => onAdd({
                                                        itemName,
                                                        value: entry.value,
                                                        evidence: entry.evidence,
                                                        source
                                                    })}
                                                    aria-label="Pin checklist item for chat"
                                                    className="inline-flex h-6 w-6 flex-shrink-0 items-center justify-center rounded bg-[var(--color-accent)] text-xs font-medium text-[var(--color-text-inverse)] hover:bg-[var(--color-accent-hover)]"
                                                >
                                                    +
                                                </button>
                                            </div>
                                            {Array.isArray(entry.evidence) && entry.evidence.length > 0 && (
                                                <ul className="mt-2 space-y-1">
                                                    {entry.evidence.map((evidenceItem, evidenceIndex) => {
                                                        const { documentId, startOffset, endOffset, isVerified } = resolveEvidenceMeta(evidenceItem);
                                                        const evidenceText = extractEvidenceText(
                                                            documentId,
                                                            startOffset,
                                                            endOffset,
                                                            evidenceItem?.text
                                                        );
                                                        const evidenceKey = `${itemName}-${index}-${evidenceIndex}`;
                                                        const isExpanded = expandedEvidence.has(evidenceKey);
                                                        const hasExactRange =
                                                            startOffset != null &&
                                                            endOffset != null &&
                                                            endOffset > startOffset;
                                                        const canNavigate =
                                                            typeof onEvidenceNavigate === 'function' &&
                                                            documentId != null &&
                                                            hasExactRange;
                                                        const docTitle =
                                                            documentId === SUMMARY_DOCUMENT_ID
                                                                ? 'Summary'
                                                                : resolveDocumentTitle(documentId);
                                                        const resolvedLabel = docTitle
                                                            ? docTitle
                                                            : documentId != null
                                                                ? `Document ${documentId}`
                                                                : 'Document';
                                                        const snippet =
                                                            (evidenceText || evidenceItem?.text || '').trim() || 'View evidence';
                                                        const shortSnippet = snippet.length > 160 ? `${snippet.slice(0, 160)}…` : snippet;
                                                        const navigatePayload = {
                                                            documentId,
                                                            startOffset: hasExactRange ? startOffset : null,
                                                            endOffset: hasExactRange ? endOffset : null,
                                                            verified: isVerified
                                                        };
                                                        return (
                                                            <li key={`${itemName}-evidence-${evidenceIndex}`} className="text-xs text-[var(--color-text-muted)]">
                                                                <div className="flex items-center justify-between gap-2">
                                                                    <div className="flex-1">
                                                                        <button
                                                                            type="button"
                                                                            disabled={!canNavigate}
                                                                            onClick={() => {
                                                                                if (!canNavigate) {
                                                                                    return;
                                                                                }
                                                                                onEvidenceNavigate(navigatePayload);
                                                                            }}
                                                                            className={`block text-left underline decoration-dotted ${
                                                                                canNavigate
                                                                                    ? 'text-[var(--color-accent)] hover:text-[var(--color-accent-hover)]'
                                                                                    : 'cursor-not-allowed text-[var(--color-text-muted)]'
                                                                            }`}
                                                                        >
                                                                            {shortSnippet}
                                                                        </button>
                                                                        <span className="block text-[11px] text-[var(--color-text-secondary)]">
                                                                            {resolvedLabel}
                                                                        </span>
                                                                        {!isVerified && (
                                                                            <span className="mt-0.5 block text-[11px] text-[var(--color-text-warning)]">
                                                                                Location not auto-verified—opening the document so you can confirm manually.
                                                                            </span>
                                                                        )}
                                                                    </div>
                                                                    {evidenceText ? (
                                                                        <button
                                                                            type="button"
                                                                            onClick={() => toggleEvidence(evidenceKey)}
                                                                            className="flex-shrink-0 rounded border border-[var(--color-border)] bg-[var(--color-surface-panel)] px-2 py-1 text-[11px] text-[var(--color-text-secondary)] hover:border-[var(--color-border-strong)]"
                                                                        >
                                                                            {isExpanded ? 'Hide evidence' : 'Show evidence'}
                                                                        </button>
                                                                    ) : (
                                                                        <span className="text-[11px] text-[var(--color-text-muted)] flex-shrink-0">
                                                                            Evidence unavailable
                                                                        </span>
                                                                    )}
                                                                </div>
                                                                {isExpanded && evidenceText && (
                                                                    <div className="mt-1 rounded border border-[var(--color-border)] bg-[var(--color-surface-panel)] p-2 text-[11px] text-[var(--color-text-primary)]">
                                                                        <pre className="whitespace-pre-wrap break-words font-mono leading-relaxed">
                                                                            {evidenceText}
                                                                        </pre>
                                                                    </div>
                                                                )}
                                                            </li>
                                                        );
                                                    })}
                                                </ul>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

const ChecklistPanel = ({
    summaryChecklists,
    documentChecklists,
    documentChecklistStatus = 'idle',
    onAddChecklist,
    onEvidenceNavigate,
    resolveDocumentTitle,
    resolveDocumentText
}) => {
    let documentStatusMessage = null;
    if (documentChecklistStatus === 'pending') {
        documentStatusMessage = 'Extracting checklist items from uploaded documents...';
    } else if (documentChecklistStatus === 'error') {
        documentStatusMessage = 'Failed to load document checklist items. Try refreshing later.';
    } else if (documentChecklistStatus === 'fallback') {
        documentStatusMessage = 'Document checklist unavailable for demo documents.';
    }

    const documentStatusClass =
        documentChecklistStatus === 'error'
            ? 'text-[var(--color-danger)]'
            : 'text-[var(--color-text-muted)]';

    return (
        <div className="flex-1 border-t border-[var(--color-border)] bg-[var(--color-surface-panel-alt)] px-4 py-4 flex flex-col min-h-0">
            <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-[var(--color-text-secondary)]">Extracted Checklist Items</h2>
                <p className="text-xs text-[var(--color-text-muted)]">Click "+" to pin items for conversation.</p>
            </div>
            <div className="mt-3 grid grid-cols-1 gap-3 overflow-hidden md:grid-cols-2 flex-1 min-h-0">
                <ChecklistColumn
                    title="Summary"
                    items={summaryChecklists}
                    onAdd={onAddChecklist}
                    source="Summary Checklist"
                    onEvidenceNavigate={onEvidenceNavigate}
                    resolveDocumentTitle={resolveDocumentTitle}
                    resolveDocumentText={resolveDocumentText}
                />
                <div className="flex flex-col min-h-0">
                    {documentStatusMessage && (
                        <p className={`text-xs px-2 pb-1 ${documentStatusClass}`}>{documentStatusMessage}</p>
                    )}
                    <ChecklistColumn
                        title="Documents"
                        items={documentChecklists}
                        onAdd={onAddChecklist}
                        source="Document Checklist"
                        onEvidenceNavigate={onEvidenceNavigate}
                        resolveDocumentTitle={resolveDocumentTitle}
                        resolveDocumentText={resolveDocumentText}
                    />
                </div>
            </div>
        </div>
    );
};

export default ChecklistPanel;

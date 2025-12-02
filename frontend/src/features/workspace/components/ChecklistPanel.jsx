import React, { useMemo } from 'react';
import { ClipboardList } from 'lucide-react';
import { SUMMARY_DOCUMENT_ID } from '../constants';

const formatLabel = (label = '') =>
    label.replace(/_/g, ' ').replace(/\s+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()).trim();

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
    const textLength = typeof evidenceItem.text === 'string' ? evidenceItem.text.length : null;
    const parsedStart =
        typeof rawStart === 'number' ? rawStart : rawStart != null ? Number.parseInt(rawStart, 10) : null;
    const startOffset = Number.isFinite(parsedStart) ? parsedStart : null;
    const endOffset =
        startOffset != null && Number.isFinite(textLength) ? startOffset + textLength : null;
    const isVerified = evidenceItem.verified !== false;
    return { documentId, startOffset, endOffset, isVerified };
};

const ChecklistColumn = ({
    title,
    items = [],
    onAdd,
    source,
    onEvidenceNavigate,
    resolveDocumentTitle = () => null
}) => {
    const entries = useMemo(() => {
        if (!Array.isArray(items)) {
            return [];
        }
        return items.map((entry) => ({
            itemName: entry?.itemName ?? entry?.item_name ?? entry?.name ?? 'Checklist Item',
            extraction: entry?.extraction ?? entry?.result ?? {
                reasoning: '',
                extracted: []
            }
        }));
    }, [items]);

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
                {entries.map(({ itemName, extraction }) => {
                    const extracted = Array.isArray(extraction?.extracted) ? extraction.extracted : [];
                    return (
                        <div key={itemName} className="rounded border border-[var(--color-border)] bg-[var(--color-surface-panel-alt)] px-3 py-2">
                            <div className="flex items-start justify-between gap-2">
                                <div>
                                    <p className="text-sm font-semibold text-[var(--color-text-primary)]">{formatLabel(itemName)}</p>
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
                                                        const hasExactRange =
                                                            isVerified &&
                                                            startOffset != null &&
                                                            endOffset != null &&
                                                            endOffset > startOffset;
                                                        const canNavigate =
                                                            typeof onEvidenceNavigate === 'function' &&
                                                            documentId != null;
                                                        const docTitle =
                                                            documentId === SUMMARY_DOCUMENT_ID
                                                                ? 'Summary'
                                                                : resolveDocumentTitle(documentId);
                                                        const offsetLabel =
                                                            hasExactRange
                                                                ? ` · chars ${startOffset}-${endOffset}`
                                                                : '';
                                                        const resolvedLabel = docTitle
                                                            ? `${docTitle}${documentId != null && documentId !== SUMMARY_DOCUMENT_ID ? ` (ID ${documentId})` : ''}`
                                                            : documentId != null
                                                                ? `Document ${documentId}`
                                                                : 'Document';
                                                        const navigatePayload = {
                                                            documentId,
                                                            startOffset: hasExactRange ? startOffset : null,
                                                            endOffset: hasExactRange ? endOffset : null,
                                                            verified: isVerified
                                                        };
                                                        return (
                                                            <li key={`${itemName}-evidence-${evidenceIndex}`} className="text-xs text-[var(--color-text-muted)]">
                                                                <button
                                                                    type="button"
                                                                    disabled={!canNavigate}
                                                                    onClick={() => {
                                                                        if (!canNavigate) {
                                                                            return;
                                                                        }
                                                                        onEvidenceNavigate(navigatePayload);
                                                                    }}
                                                                    className={`w-full text-left rounded px-2 py-1 transition ${
                                                                        canNavigate
                                                                            ? 'hover:bg-[var(--color-warning-soft)] focus:outline-none focus:ring-1 focus:ring-[var(--color-warning-soft)]'
                                                                            : 'cursor-default text-[var(--color-text-muted)]'
                                                                    }`}
                                                                >
                                                                    <span className="block italic text-[var(--color-text-secondary)]">
                                                                        “{evidenceItem?.text || 'N/A'}”
                                                                    </span>
                                                                    <span className="block text-[11px] text-[var(--color-text-muted)]">
                                                                        {resolvedLabel}
                                                                        {offsetLabel}
                                                                    </span>
                                                                    {!isVerified && (
                                                                        <span className="mt-0.5 block text-[11px] text-[var(--color-text-warning)]">
                                                                            Location not auto-verified—opening the document so you can confirm manually.
                                                                        </span>
                                                                    )}
                                                                </button>
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
    resolveDocumentTitle
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
                    />
                </div>
            </div>
        </div>
    );
};

export default ChecklistPanel;

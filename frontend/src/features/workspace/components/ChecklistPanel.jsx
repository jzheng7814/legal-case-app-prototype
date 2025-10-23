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
    return { documentId, startOffset, endOffset };
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
        <div className="flex flex-col min-h-0 bg-white border border-gray-200 rounded-lg shadow-sm">
            <div className="flex items-center gap-2 border-b px-3 py-2">
                <ClipboardList className="h-4 w-4 text-gray-500" />
                <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-600">{title}</h3>
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-2 space-y-3">
                {entries.length === 0 && (
                    <p className="text-xs text-gray-500">No checklist items available yet.</p>
                )}
                {entries.map(({ itemName, extraction }) => {
                    const extracted = Array.isArray(extraction?.extracted) ? extraction.extracted : [];
                    return (
                        <div key={itemName} className="rounded border border-gray-100 bg-gray-50/80 px-3 py-2">
                            <div className="flex items-start justify-between gap-2">
                                <div>
                                    <p className="text-sm font-semibold text-gray-800">{formatLabel(itemName)}</p>
                                </div>
                            </div>
                            {extracted.length === 0 ? (
                                <p className="mt-2 text-xs italic text-gray-400">No extracted values.</p>
                            ) : (
                                <div className="mt-2 space-y-2">
                                    {extracted.map((entry, index) => (
                                        <div key={`${itemName}-${index}`} className="rounded bg-white p-2 shadow-sm border border-gray-200">
                                            <div className="flex items-start justify-between gap-2">
                                                <p className="text-sm text-gray-900">{entry.value || '--'}</p>
                                                <button
                                                    type="button"
                                                    onClick={() => onAdd({
                                                        itemName,
                                                        value: entry.value,
                                                        evidence: entry.evidence,
                                                        source
                                                    })}
                                                    aria-label="Pin checklist item for chat"
                                                    className="inline-flex h-6 w-6 flex-shrink-0 items-center justify-center rounded bg-blue-600 text-xs font-medium text-white hover:bg-blue-700"
                                                >
                                                    +
                                                </button>
                                            </div>
                                            {Array.isArray(entry.evidence) && entry.evidence.length > 0 && (
                                                <ul className="mt-2 space-y-1">
                                                    {entry.evidence.map((evidenceItem, evidenceIndex) => {
                                                        const { documentId, startOffset, endOffset } = resolveEvidenceMeta(evidenceItem);
                                                        const canNavigate =
                                                            typeof onEvidenceNavigate === 'function' &&
                                                            documentId != null &&
                                                            startOffset != null &&
                                                            endOffset != null &&
                                                            endOffset > startOffset;
                                                        const docTitle =
                                                            documentId === SUMMARY_DOCUMENT_ID
                                                                ? 'Summary'
                                                                : resolveDocumentTitle(documentId);
                                                        const offsetLabel =
                                                            startOffset != null && endOffset != null && endOffset > startOffset
                                                                ? ` · chars ${startOffset}-${endOffset}`
                                                                : '';
                                                        const resolvedLabel = docTitle
                                                            ? `${docTitle}${documentId != null && documentId !== SUMMARY_DOCUMENT_ID ? ` (ID ${documentId})` : ''}`
                                                            : documentId != null
                                                                ? `Document ${documentId}`
                                                                : 'Document';
                                                        return (
                                                            <li key={`${itemName}-evidence-${evidenceIndex}`} className="text-xs text-gray-600">
                                                                <button
                                                                    type="button"
                                                                    disabled={!canNavigate}
                                                                    onClick={() => {
                                                                        if (!canNavigate) {
                                                                            return;
                                                                        }
                                                                        onEvidenceNavigate({
                                                                            documentId,
                                                                            startOffset,
                                                                            endOffset
                                                                        });
                                                                    }}
                                                                    className={`w-full text-left rounded px-2 py-1 transition ${
                                                                        canNavigate
                                                                            ? 'hover:bg-yellow-100 focus:outline-none focus:ring-1 focus:ring-yellow-400'
                                                                            : 'cursor-default text-gray-500'
                                                                    }`}
                                                                >
                                                                    <span className="block italic text-gray-700">
                                                                        “{evidenceItem?.text || 'N/A'}”
                                                                    </span>
                                                                    <span className="block text-[11px] text-gray-500">
                                                                        {resolvedLabel}
                                                                        {offsetLabel}
                                                                    </span>
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
        documentChecklistStatus === 'error' ? 'text-red-600' : 'text-gray-500';

    return (
        <div className="flex-1 border-t bg-gray-100 px-4 py-4 flex flex-col min-h-0">
            <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-gray-700">Extracted Checklist Items</h2>
                <p className="text-xs text-gray-500">Click "+" to pin items for conversation.</p>
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

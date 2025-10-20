import React, { useMemo } from 'react';
import { ClipboardList } from 'lucide-react';

const formatLabel = (label = '') =>
    label.replace(/_/g, ' ').replace(/\s+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()).trim();

const ChecklistColumn = ({ title, items = [], onAdd, source }) => {
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
                                                        const docLabel = evidenceItem?.source_document || evidenceItem?.sourceDocument;
                                                        const placement = evidenceItem?.location ? ` (${evidenceItem.location})` : '';
                                                        return (
                                                            <li key={`${itemName}-evidence-${evidenceIndex}`} className="text-xs text-gray-600">
                                                                <span className="italic">"{evidenceItem?.text || 'N/A'}"</span>
                                                                {docLabel && (
                                                                    <span>{` - ${docLabel}${placement}`}</span>
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

const ChecklistPanel = ({ summaryChecklists, documentChecklists, onAddChecklist }) => (
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
            />
            <ChecklistColumn
                title="Documents"
                items={documentChecklists}
                onAdd={onAddChecklist}
                source="Document Checklist"
            />
        </div>
    </div>
);

export default ChecklistPanel;

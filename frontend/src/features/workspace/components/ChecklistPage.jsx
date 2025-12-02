import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Trash2 } from 'lucide-react';
import DocumentsPanel from '../DocumentsPanel';
import { useChecklist, useDocuments, useHighlight } from '../state/WorkspaceProvider';

const ChecklistPage = ({ isActive }) => {
    const { categories, isLoading, addItem, deleteItem } = useChecklist();
    const documents = useDocuments();
    const {
        selectedDocumentText,
        selectedDocumentRange,
        tooltipPosition,
        setInteractionMode,
        clearSelection,
        handleContextClick
    } = useHighlight();
    const [isPickerOpen, setIsPickerOpen] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [actionError, setActionError] = useState(null);

    useEffect(() => {
        if (isActive) {
            setInteractionMode('checklist');
        }
    }, [isActive, setInteractionMode]);

    useEffect(() => {
        if (!selectedDocumentText) {
            setIsPickerOpen(false);
        }
    }, [selectedDocumentText]);

    const selectionAvailable = Boolean(
        isActive &&
        selectedDocumentText &&
        selectedDocumentRange &&
        documents.selectedDocument != null
    );

    const handleCategorySelect = useCallback(async (categoryId) => {
        if (!selectionAvailable) {
            return;
        }
        setIsSubmitting(true);
        setActionError(null);
        try {
            await addItem({
                categoryId,
                text: selectedDocumentText,
                documentId: documents.selectedDocument,
                startOffset: selectedDocumentRange.start,
                endOffset: selectedDocumentRange.end
            });
            clearSelection();
            setIsPickerOpen(false);
        } catch (error) {
            setActionError(error.message || 'Failed to add checklist item.');
        } finally {
            setIsSubmitting(false);
        }
    }, [addItem, clearSelection, documents.selectedDocument, selectedDocumentRange, selectedDocumentText, selectionAvailable]);

    const handleDelete = useCallback(async (valueId) => {
        if (!valueId) {
            return;
        }
        setActionError(null);
        try {
            await deleteItem(valueId);
        } catch (error) {
            setActionError(error.message || 'Failed to delete checklist item.');
        }
    }, [deleteItem]);

    const handleValueNavigate = useCallback((value) => {
        if (
            value.documentId == null ||
            value.startOffset == null ||
            value.endOffset == null ||
            value.endOffset <= value.startOffset
        ) {
            return;
        }
        handleContextClick({
            type: 'document-selection',
            documentId: value.documentId,
            range: { start: value.startOffset, end: value.endOffset }
        });
    }, [handleContextClick]);

    const renderSelectionTooltip = () => {
        if (!selectionAvailable) {
            return null;
        }
        const style = {
            left: tooltipPosition.x,
            top: tooltipPosition.y
        };
        if (!isPickerOpen) {
            return (
                <button
                    type="button"
                    className="fixed z-50 -translate-x-1/2 rounded-full bg-[var(--color-accent)] px-3 py-1 text-xs font-semibold text-[var(--color-text-inverse)] shadow-lg hover:bg-[var(--color-accent-hover)]"
                    style={style}
                    onClick={() => setIsPickerOpen(true)}
                >
                    + Add item
                </button>
            );
        }

        return (
            <div
                className="fixed z-50 -translate-x-1/2 min-w-[240px] rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-panel)] p-3 shadow-lg"
                style={style}
            >
                <p className="text-xs font-semibold text-[var(--color-text-secondary)] mb-2">Assign to checklist category</p>
                <div className="grid grid-cols-2 gap-2">
                    {categories.map((category) => (
                        <button
                            key={category.id}
                            type="button"
                            disabled={isSubmitting}
                            onClick={() => handleCategorySelect(category.id)}
                            className="flex items-center gap-2 rounded border border-[var(--color-border)] px-2 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] hover:border-[var(--color-border-strong)] disabled:opacity-50"
                        >
                            <span
                                className="h-2.5 w-2.5 rounded-full"
                                style={{ backgroundColor: category.color }}
                            />
                            {category.label}
                        </button>
                    ))}
                </div>
                <button
                    type="button"
                    className="mt-2 w-full rounded border border-[var(--color-border)] bg-[var(--color-surface-panel-alt)] py-1 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)]"
                    onClick={() => setIsPickerOpen(false)}
                    disabled={isSubmitting}
                >
                    Cancel
                </button>
            </div>
        );
    };

    const sortedCategories = useMemo(() => categories, [categories]);

    return (
        <div className="flex flex-1 overflow-hidden bg-[var(--color-surface-panel-alt)]">
            <div className="w-[40%] border-r border-[var(--color-border)] bg-[var(--color-surface-panel)] flex flex-col overflow-hidden">
                <div className="border-b border-[var(--color-border)] px-4 py-3">
                    <div className="flex items-center justify-between">
                        <div>
                            <h2 className="text-base font-semibold text-[var(--color-text-primary)]">Document Checklist</h2>
                            <p className="text-xs text-[var(--color-text-muted)]">Review AI suggestions or add your own from document spans.</p>
                        </div>
                        {isLoading && (
                            <span className="text-xs text-[var(--color-accent)] font-medium">Loading…</span>
                        )}
                    </div>
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {sortedCategories.map((category) => (
                        <div
                            key={category.id}
                            className="rounded-lg border bg-[var(--color-surface-panel)] shadow-sm"
                            style={{ borderColor: `${category.color}33` }}
                        >
                            <div className="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2">
                                <div className="flex items-center gap-2">
                                    <span
                                        className="h-2.5 w-2.5 rounded-full"
                                        style={{ backgroundColor: category.color }}
                                    />
                                    <p className="text-sm font-semibold text-[var(--color-text-primary)]">{category.label}</p>
                                </div>
                                <span className="text-xs text-[var(--color-text-muted)]">{category.values.length} entries</span>
                            </div>
                            <div className="p-3 space-y-3">
                                {category.values.length === 0 ? (
                                    <p className="text-xs text-[var(--color-text-muted)]">Nothing captured yet.</p>
                                ) : (
                                    category.values.map((value) => (
                                        <div
                                            key={value.id}
                                            className="rounded border border-[var(--color-border)] bg-[var(--color-surface-panel-alt)] px-2 py-2"
                                        >
                                            <div className="flex items-start justify-between gap-3">
                                                <button
                                                    type="button"
                                                    onClick={() => handleValueNavigate(value)}
                                                    className="flex-1 text-left"
                                                >
                                                    <p className="text-sm text-[var(--color-text-primary)] hover:text-[var(--color-accent)] transition">
                                                        {value.text || value.value || '—'}
                                                    </p>
                                                    <p className="text-[11px] text-[var(--color-text-muted)] mt-1">
                                                        {value.documentId != null ? `Document ${value.documentId}` : 'No document reference'}
                                                        {value.startOffset != null && value.endOffset != null ? ` · chars ${value.startOffset}-${value.endOffset}` : ''}
                                                        {(value.documentId != null && value.startOffset != null && value.endOffset != null && value.endOffset > value.startOffset) ? ' · Click to jump' : ''}
                                                    </p>
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => handleDelete(value.id)}
                                                    className="text-[var(--color-text-muted)] hover:text-[var(--color-danger)]"
                                                    title="Delete item"
                                                >
                                                    <Trash2 className="h-4 w-4" />
                                                </button>
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>
                    ))}
                    {actionError && (
                        <div className="rounded bg-[var(--color-danger-soft)] px-3 py-2 text-xs text-[var(--color-danger)]">
                            {actionError}
                        </div>
                    )}
                </div>
            </div>
            <div className="flex-1 relative">
                <DocumentsPanel />
                {selectionAvailable && (
                    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-[var(--color-overlay-scrim)] px-3 py-1 text-xs text-[var(--color-text-inverse)] shadow">
                        Select a category to capture this document span.
                    </div>
                )}
            </div>
            {renderSelectionTooltip()}
        </div>
    );
};

export default ChecklistPage;

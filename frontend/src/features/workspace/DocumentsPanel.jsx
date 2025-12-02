import React, { useEffect, useMemo, useState } from 'react';
import { useDocuments, useHighlight, useChecklist } from './state/WorkspaceProvider';
import { computeOverlayRects, createRangeFromOffsets } from '../../utils/selection';

const DocumentsPanel = () => {
    const {
        documents,
        selectedDocument,
        setSelectedDocument,
        isLoadingDocuments,
        documentRef,
        getCurrentDocument
    } = useDocuments();
    const { activeHighlight, highlightRects } = useHighlight();
    const { highlightsByDocument } = useChecklist();
    const [categoryHighlights, setCategoryHighlights] = useState([]);
    const activeChecklistHighlights = useMemo(
        () => highlightsByDocument?.[selectedDocument] || [],
        [highlightsByDocument, selectedDocument]
    );
    const currentDocumentText = getCurrentDocument() || 'No document content';

    useEffect(() => {
        const container = documentRef.current;
        if (!container || !activeChecklistHighlights.length) {
            setCategoryHighlights([]);
            return undefined;
        }

        const updateRects = () => {
            const next = [];
            activeChecklistHighlights.forEach((entry) => {
                if (entry.startOffset == null || entry.endOffset == null) {
                    return;
                }
                const range = createRangeFromOffsets(container, entry.startOffset, entry.endOffset);
                if (!range) {
                    return;
                }
                next.push({
                    id: entry.id,
                    color: entry.color,
                    label: entry.label,
                    rects: computeOverlayRects(container, range)
                });
            });
            setCategoryHighlights(next);
        };

        updateRects();
        const handleScroll = () => requestAnimationFrame(updateRects);
        container.addEventListener('scroll', handleScroll);
        window.addEventListener('resize', handleScroll);
        return () => {
            container.removeEventListener('scroll', handleScroll);
            window.removeEventListener('resize', handleScroll);
        };
    }, [activeChecklistHighlights, documentRef, currentDocumentText]);

    return (
        <div className="flex-1 bg-white flex flex-col border-l">
            <div className="border-b px-4 py-3">
                <h2 className="text-base font-semibold text-gray-800">Document Viewer</h2>
                <p className="text-xs text-gray-500">Select spans to add checklist entries. Highlights show captured facts.</p>
            </div>

            <div className="flex-1 p-4 flex flex-col space-y-4 min-h-0">
                {documents.length > 0 ? (
                    <select
                        value={selectedDocument != null ? String(selectedDocument) : ''}
                        onChange={(event) => {
                            const nextValue = Number.parseInt(event.target.value, 10);
                            if (!Number.isNaN(nextValue)) {
                                setSelectedDocument(nextValue);
                            }
                        }}
                        className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                        {documents.map((doc) => (
                            <option key={doc.id} value={String(doc.id)}>
                                {doc.title}
                                {doc.type ? ` (${doc.type})` : ''}
                            </option>
                        ))}
                    </select>
                ) : (
                    <div className="text-sm text-gray-500">
                        {isLoadingDocuments ? 'Loading documents...' : 'No documents loaded'}
                    </div>
                )}

                <div className="relative flex-1 min-h-0">
                    <div
                        ref={documentRef}
                        className="relative h-full w-full bg-gray-50 border border-gray-300 rounded-md p-4 overflow-y-auto cursor-text"
                    >
                        <pre className="text-xs leading-relaxed font-mono whitespace-pre-wrap">
                            {currentDocumentText}
                        </pre>
                        {categoryHighlights.map((entry) =>
                            entry.rects.map((rect, index) => (
                                <span
                                    key={`${entry.id}-${index}`}
                                    className="pointer-events-none absolute rounded-sm border border-white/70"
                                    style={{
                                        top: rect.top,
                                        left: rect.left,
                                        width: rect.width,
                                        height: rect.height,
                                        backgroundColor: entry.color,
                                        opacity: 0.25,
                                        zIndex: 5
                                    }}
                                />
                            ))
                        )}
                        {activeHighlight?.useOverlay && activeHighlight.type === 'document' && highlightRects.map((rect, index) => (
                            <span
                                key={`document-highlight-${index}`}
                                className="pointer-events-none absolute z-10 rounded-sm bg-yellow-200/70"
                                style={{
                                    top: rect.top,
                                    left: rect.left,
                                    width: rect.width,
                                    height: rect.height
                                }}
                            />
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default DocumentsPanel;

import React from 'react';
import { useDocuments, useHighlight } from './state/WorkspaceProvider';

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

    return (
        <div className="w-1/3 bg-white border-l flex flex-col">
            <div className="border-b p-4">
                <h2 className="text-lg font-semibold">Case Documents</h2>
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
                            {getCurrentDocument() || 'No document content'}
                        </pre>
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

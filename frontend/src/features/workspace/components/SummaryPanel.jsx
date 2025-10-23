import React, { useCallback, useMemo, useState } from 'react';
import { Edit3, Sparkles } from 'lucide-react';
import { useSummary, useHighlight, useDocuments, useChat } from '../state/WorkspaceProvider';
import ChecklistPanel from './ChecklistPanel';
import { SUMMARY_DOCUMENT_ID } from '../constants';

const SummaryPanel = () => {
    const {
        summaryText,
        setSummaryText,
        isEditMode,
        toggleEditMode,
        isGeneratingSummary,
        generateAISummary,
        refreshSuggestions,
        isLoadingSuggestions,
        summaryRef,
        suggestionsError,
        documentChecklists,
        documentChecklistStatus,
        summaryChecklists
    } = useSummary();
    const documents = useDocuments();
    const activeCaseId = documents.caseId;
    const {
        renderSummaryWithSuggestions,
        activeHighlight,
        highlightRects,
        showTabTooltip,
        tooltipPosition,
        selectedText,
        selectedDocumentText,
        handleContextClick
    } = useHighlight();
    const { addChecklistContext } = useChat();
    const [localError, setLocalError] = useState(null);

    const canGenerateSummary = !isEditMode;

    const contextDocuments = documents.documents;

    const handleGenerateSummary = useCallback(async () => {
        setLocalError(null);
        try {
            const generated = await generateAISummary({ caseId: activeCaseId, documents: contextDocuments });
            if (generated) {
                await refreshSuggestions({ caseId: activeCaseId, documents: contextDocuments });
            }
        } catch (error) {
            setLocalError(error.message || 'Failed to generate summary.');
        }
    }, [activeCaseId, contextDocuments, generateAISummary, refreshSuggestions]);

    const handleRefreshSuggestions = useCallback(async () => {
        setLocalError(null);
        try {
            await refreshSuggestions({ caseId: activeCaseId, documents: contextDocuments });
        } catch (error) {
            setLocalError(error.message || 'Failed to refresh suggestions.');
        }
    }, [activeCaseId, contextDocuments, refreshSuggestions]);

    const handleAddChecklistToChat = useCallback(({ itemName, value, evidence, source }) => {
        addChecklistContext({ itemName, value, evidence, source });
    }, [addChecklistContext]);

    const documentTitleLookup = useMemo(() => {
        const map = {};
        (documents.documents || []).forEach((doc) => {
            map[doc.id] = doc.title || doc.id;
        });
        return map;
    }, [documents.documents]);

    const resolveDocumentTitle = useCallback(
        (documentId) => {
            if (documentId == null) {
                return null;
            }
            if (documentId === SUMMARY_DOCUMENT_ID) {
                return 'Summary';
            }
            const lookupKey = typeof documentId === 'number' ? documentId : Number.parseInt(documentId, 10);
            if (Number.isNaN(lookupKey)) {
                return null;
            }
            return documentTitleLookup[lookupKey] || null;
        },
        [documentTitleLookup]
    );

    const handleEvidenceNavigate = useCallback(
        ({ documentId, startOffset, endOffset }) => {
            if (startOffset == null || endOffset == null || endOffset <= startOffset) {
                return;
            }
            if (documentId === SUMMARY_DOCUMENT_ID) {
                handleContextClick({
                    type: 'selection',
                    range: { start: startOffset, end: endOffset }
                });
                return;
            }
            if (documentId == null) {
                return;
            }
            const resolvedDocumentId = typeof documentId === 'number' ? documentId : Number.parseInt(documentId, 10);
            if (Number.isNaN(resolvedDocumentId)) {
                return;
            }
            handleContextClick({
                type: 'document-selection',
                documentId: resolvedDocumentId,
                range: { start: startOffset, end: endOffset }
            });
        },
        [handleContextClick]
    );

    return (
        <div className="w-2/5 border-r bg-white flex flex-col overflow-hidden">
            <div className="border-b p-4">
                <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold">Case Summary</h2>
                    <div className="flex items-center space-x-2">
                        {!summaryText && isEditMode && (
                            <span className="text-xs text-gray-400 italic">(Generate disabled in edit mode)</span>
                        )}
                        {canGenerateSummary && (
                            <button
                                onClick={handleGenerateSummary}
                                disabled={isGeneratingSummary || documents.isLoadingDocuments}
                                className="flex items-center px-3 py-1 text-sm bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
                            >
                                <Sparkles className="h-4 w-4 mr-1" />
                                {isGeneratingSummary ? 'Generating...' : summaryText ? 'Regenerate with AI' : 'Generate with AI'}
                            </button>
                        )}
                        {summaryText && !isEditMode && (
                            <button
                                onClick={handleRefreshSuggestions}
                                disabled={isLoadingSuggestions}
                                className="flex items-center px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                            >
                                <Sparkles className="h-4 w-4 mr-1" />
                                {isLoadingSuggestions ? 'Refreshing...' : 'Refresh Suggestions'}
                            </button>
                        )}
                        <button
                            onClick={toggleEditMode}
                            className={`flex items-center px-3 py-1 text-sm rounded ${
                                isEditMode
                                    ? 'bg-blue-600 text-white hover:bg-blue-700'
                                    : 'bg-gray-600 text-white hover:bg-gray-700'
                            }`}
                        >
                            <Edit3 className="h-4 w-4 mr-1" />
                            {isEditMode ? 'Exit Edit' : 'Edit'}
                        </button>
                    </div>
                </div>
                {(localError || suggestionsError) && (
                    <div className="mt-2 text-xs text-red-600">
                        {localError || suggestionsError?.message}
                    </div>
                )}
            </div>

            <div className="flex-1 flex flex-col min-h-0">
                <div className="flex-1 p-4 flex flex-col min-h-0">
                    <div className="relative flex-1 min-h-0">
                        {isEditMode ? (
                            <textarea
                                ref={summaryRef}
                                value={summaryText}
                                onChange={(event) => setSummaryText(event.target.value)}
                                placeholder="Write your case summary here..."
                                className="w-full h-full min-h-0 resize-none border border-gray-300 rounded-md px-3 py-2 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-blue-500 overflow-auto"
                            />
                        ) : (
                            <div
                                ref={summaryRef}
                                className="relative h-full w-full border border-gray-300 rounded-md px-3 py-2 text-sm leading-relaxed cursor-text overflow-y-auto whitespace-pre-wrap"
                            >
                                {summaryText ? renderSummaryWithSuggestions(summaryText) : (
                                    <span className="text-gray-500">Your summary will appear here...</span>
                                )}
                                {activeHighlight?.useOverlay && activeHighlight.type === 'summary' && highlightRects.map((rect, index) => (
                                    <span
                                        key={`summary-highlight-${index}`}
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
                        )}
                    </div>
                </div>
                <ChecklistPanel
                    summaryChecklists={summaryChecklists}
                    documentChecklists={documentChecklists}
                    documentChecklistStatus={documentChecklistStatus}
                    onAddChecklist={handleAddChecklistToChat}
                    onEvidenceNavigate={handleEvidenceNavigate}
                    resolveDocumentTitle={resolveDocumentTitle}
                />
            </div>

            {showTabTooltip && (selectedText || selectedDocumentText) && (
                <div
                    className="fixed z-50 bg-black text-white text-xs py-1 px-2 rounded pointer-events-none"
                    style={{
                        left: tooltipPosition.x - 50,
                        top: tooltipPosition.y,
                        transform: 'translateX(-50%)'
                    }}
                >
                    [Tab] +
                </div>
            )}
        </div>
    );
};

export default SummaryPanel;

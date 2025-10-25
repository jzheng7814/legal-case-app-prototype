import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Edit3, Sparkles, Plus } from 'lucide-react';
import { useSummary, useHighlight, useDocuments, useChat } from '../state/WorkspaceProvider';
import ChecklistPanel from './ChecklistPanel';
import { SUMMARY_DOCUMENT_ID } from '../constants';
import SummaryPatchPanel from './SummaryPatchPanel';
import { createRangeFromOffsets, computeOverlayRects, scrollRangeIntoView } from '../../../utils/selection';

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
        summaryChecklists,
        versionHistory,
        activeVersionId,
        saveCurrentVersion,
        selectVersion,
        patchAction,
        activePatchId,
        clearPatchPreview
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
    const [patchOverlayRects, setPatchOverlayRects] = useState([]);
    const [patchOverlayMeta, setPatchOverlayMeta] = useState(null);
    const patchPanelRef = useRef(null);

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

    useEffect(() => {
        if (isEditMode || (patchAction && patchAction.isStale)) {
            clearPatchPreview();
        }
    }, [isEditMode, patchAction, clearPatchPreview]);

    useEffect(() => {
        if (!activePatchId || !patchAction || patchAction.isStale || !summaryRef.current) {
            setPatchOverlayRects([]);
            setPatchOverlayMeta(null);
            return;
        }
        const target = patchAction.patches.find((patch) => patch.id === activePatchId && patch.status === 'applied');
        if (!target) {
            setPatchOverlayRects([]);
            setPatchOverlayMeta(null);
            return;
        }
        const container = summaryRef.current;
        const resolveEnd = () => {
            if (target.currentEnd > target.currentStart) {
                return target.currentEnd;
            }
            if (summaryText.length > target.currentStart) {
                return target.currentStart + 1;
            }
            return target.currentStart;
        };
        const highlightEnd = resolveEnd();

        const updateRects = () => {
            const range = createRangeFromOffsets(container, target.currentStart, highlightEnd);
            if (!range) {
                setPatchOverlayRects([]);
                return;
            }
            scrollRangeIntoView(container, range);
            setPatchOverlayRects(computeOverlayRects(container, range));
        };

        updateRects();
        setPatchOverlayMeta({ deletedText: target.deletedText, insertText: target.insertText });

        const handleScroll = () => requestAnimationFrame(updateRects);
        container.addEventListener('scroll', handleScroll);
        window.addEventListener('resize', handleScroll);
        return () => {
            container.removeEventListener('scroll', handleScroll);
            window.removeEventListener('resize', handleScroll);
        };
    }, [activePatchId, patchAction, summaryRef, summaryText.length]);

    useEffect(() => {
        if (typeof document === 'undefined') {
            return undefined;
        }
        if (!activePatchId) {
            return undefined;
        }
        const handleDocumentClick = (event) => {
            if (!summaryRef.current) {
                return;
            }
            if (summaryRef.current.contains(event.target)) {
                return;
            }
            if (patchPanelRef.current && patchPanelRef.current.contains(event.target)) {
                return;
            }
            clearPatchPreview();
        };
        document.addEventListener('mousedown', handleDocumentClick);
        return () => {
            document.removeEventListener('mousedown', handleDocumentClick);
        };
    }, [activePatchId, clearPatchPreview, summaryRef]);

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

    const handleVersionSelect = useCallback((event) => {
        selectVersion(event.target.value);
    }, [selectVersion]);

    const documentTitleLookup = useMemo(() => {
        const map = {};
        (documents.documents || []).forEach((doc) => {
            map[doc.id] = doc.title || doc.id;
        });
        return map;
    }, [documents.documents]);

    const versionOptions = useMemo(() => versionHistory.map((entry) => {
        const date = entry.savedAt ? new Date(entry.savedAt) : null;
        const hasValidDate = date && !Number.isNaN(date.getTime());
        return {
            id: entry.id,
            label: hasValidDate ? date.toLocaleString() : entry.savedAt || entry.id
        };
    }), [versionHistory]);

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
            <div className="border-b p-4 space-y-3">
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
                <div className="flex items-center space-x-2">
                    <select
                        value={activeVersionId || ''}
                        onChange={handleVersionSelect}
                        className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                        <option value="">Current Draft</option>
                        {versionOptions.map((version) => (
                            <option key={version.id} value={version.id}>
                                {version.label}
                            </option>
                        ))}
                    </select>
                    <button
                        onClick={saveCurrentVersion}
                        className="p-2 text-blue-600 hover:text-blue-800"
                        title="Save current version"
                    >
                        <Plus className="h-4 w-4" />
                    </button>
                </div>
                {(localError || suggestionsError) && (
                    <div className="mt-2 text-xs text-red-600">
                        {localError || suggestionsError?.message}
                    </div>
                )}
            </div>

            <SummaryPatchPanel panelRef={patchPanelRef} />

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
                                {patchOverlayRects.map((rect, index) => (
                                    <span
                                        key={`patch-preview-${index}`}
                                        className="pointer-events-none absolute z-30 rounded-sm bg-blue-200/60"
                                        style={{
                                            top: rect.top,
                                            left: rect.left,
                                            width: rect.width,
                                            height: rect.height
                                        }}
                                    />
                                ))}
                                {patchOverlayMeta?.deletedText && patchOverlayRects[0] && (
                                    <div
                                        className="pointer-events-none absolute z-40 rounded bg-white/80 px-2 py-0.5 text-xs font-semibold text-red-700 line-through"
                                        style={{
                                            top: Math.max(0, patchOverlayRects[0].top - 20),
                                            left: patchOverlayRects[0].left
                                        }}
                                    >
                                        {patchOverlayMeta.deletedText || '(whitespace)'}
                                    </div>
                                )}
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

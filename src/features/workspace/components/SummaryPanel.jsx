import React from 'react';
import { Edit3, Sparkles } from 'lucide-react';
import { useSummary, useHighlight } from '../state/WorkspaceProvider';

const SummaryPanel = () => {
    const {
        summaryText,
        setSummaryText,
        isEditMode,
        toggleEditMode,
        isGeneratingSummary,
        generateAISummary,
        summaryRef
    } = useSummary();
    const {
        renderSummaryWithSuggestions,
        activeHighlight,
        highlightRects,
        showTabTooltip,
        tooltipPosition,
        selectedText,
        selectedDocumentText
    } = useHighlight();

    const canGenerateSummary = !summaryText && !isEditMode;

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
                                onClick={generateAISummary}
                                disabled={isGeneratingSummary}
                                className="flex items-center px-3 py-1 text-sm bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
                            >
                                <Sparkles className="h-4 w-4 mr-1" />
                                {isGeneratingSummary ? 'Generating...' : 'Generate with AI'}
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
            </div>

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

            {showTabTooltip && (selectedText || selectedDocumentText) && (
                <div
                    className="fixed z-50 bg-black text-white text-xs py-1 px-2 rounded pointer-events-none"
                    style={{
                        left: tooltipPosition.x - 50,
                        top: tooltipPosition.y,
                        transform: 'translateX(-50%)'
                    }}
                >
                    [Tab] Add to Chat
                </div>
            )}
        </div>
    );
};

export default SummaryPanel;

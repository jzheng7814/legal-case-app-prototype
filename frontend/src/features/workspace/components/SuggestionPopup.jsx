import React from 'react';
import { Check, MessageCircle, X } from 'lucide-react';
import { useHighlight } from '../state/WorkspaceProvider';

const SuggestionPopup = () => {
    const {
        hoveredSuggestion,
        persistentSuggestionPopup,
        hoverPosition,
        handlePopupEnter,
        handlePopupLeave,
        applySuggestion,
        rejectSuggestion,
        startSuggestionDiscussion,
        setPersistentSuggestionPopup,
        setHighlightedContext
    } = useHighlight();

    const activeSuggestion = persistentSuggestionPopup || hoveredSuggestion;

    if (!activeSuggestion) {
        return null;
    }

    return (
        <div
            className={`fixed z-50 bg-white border border-gray-200 shadow-lg rounded-lg p-4 max-w-sm suggestion-popup ${
                persistentSuggestionPopup ? 'border-blue-400' : ''
            }`}
            style={{ left: hoverPosition.x, top: hoverPosition.y }}
            onMouseEnter={handlePopupEnter}
            onMouseLeave={persistentSuggestionPopup ? undefined : handlePopupLeave}
        >
            <div className="mb-3">
                <div className="text-sm font-medium mb-1">
                    AI Suggestion{persistentSuggestionPopup ? ' (Click outside to close)' : ':'}
                </div>
                <div className="text-xs text-gray-600">
                    {activeSuggestion.comment}
                </div>
            </div>

            <div className="mb-3 text-xs">
                <div className="line-through text-red-600">
                    {activeSuggestion.originalText}
                </div>
                <div className="text-green-600">
                    → {activeSuggestion.suggestedText}
                </div>
            </div>

            <div className="flex space-x-2">
                <button
                    onClick={() => {
                        applySuggestion(activeSuggestion);
                        setPersistentSuggestionPopup(null);
                        setHighlightedContext(null);
                    }}
                    className="flex items-center px-2 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700"
                >
                    <Check className="h-3 w-3 mr-1" />
                    Accept
                </button>
                <button
                    onClick={() => {
                        rejectSuggestion(activeSuggestion);
                        setPersistentSuggestionPopup(null);
                        setHighlightedContext(null);
                    }}
                    className="flex items-center px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700"
                >
                    <X className="h-3 w-3 mr-1" />
                    Reject
                </button>
                <button
                    onClick={() => startSuggestionDiscussion(activeSuggestion)}
                    className="flex items-center px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
                >
                    <MessageCircle className="h-3 w-3 mr-1" />
                    Discuss
                </button>
            </div>
        </div>
    );
};

export default SuggestionPopup;

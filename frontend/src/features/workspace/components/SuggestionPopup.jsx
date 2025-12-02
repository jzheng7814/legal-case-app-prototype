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
            className={`fixed z-50 bg-[var(--color-surface-panel)] border border-[var(--color-border)] shadow-lg rounded-lg p-4 max-w-sm suggestion-popup ${
                persistentSuggestionPopup ? 'border-[var(--color-accent)]' : ''
            }`}
            style={{ left: hoverPosition.x, top: hoverPosition.y }}
            onMouseEnter={handlePopupEnter}
            onMouseLeave={persistentSuggestionPopup ? undefined : handlePopupLeave}
        >
            <div className="mb-3">
                <div className="text-sm font-medium mb-1 text-[var(--color-text-primary)]">
                    AI Suggestion{persistentSuggestionPopup ? ' (Click outside to close)' : ':'}
                </div>
                <div className="text-xs text-[var(--color-text-muted)]">
                    {activeSuggestion.comment}
                </div>
            </div>

            <div className="mb-3 text-xs">
                <div className="line-through text-[var(--color-danger)]">
                    {activeSuggestion.originalText}
                </div>
                <div className="text-[var(--color-text-success)]">
                    → {activeSuggestion.text}
                </div>
            </div>

            <div className="flex space-x-2">
                <button
                    onClick={() => {
                        applySuggestion(activeSuggestion);
                        setPersistentSuggestionPopup(null);
                        setHighlightedContext(null);
                    }}
                    className="flex items-center px-2 py-1 text-xs bg-[var(--color-success)] text-[var(--color-text-inverse)] rounded hover:bg-[var(--color-success-hover)]"
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
                    className="flex items-center px-2 py-1 text-xs bg-[var(--color-danger)] text-[var(--color-text-inverse)] rounded hover:bg-[var(--color-danger-hover)]"
                >
                    <X className="h-3 w-3 mr-1" />
                    Reject
                </button>
                <button
                    onClick={() => startSuggestionDiscussion(activeSuggestion)}
                    className="flex items-center px-2 py-1 text-xs bg-[var(--color-accent)] text-[var(--color-text-inverse)] rounded hover:bg-[var(--color-accent-hover)]"
                >
                    <MessageCircle className="h-3 w-3 mr-1" />
                    Discuss
                </button>
            </div>
        </div>
    );
};

export default SuggestionPopup;

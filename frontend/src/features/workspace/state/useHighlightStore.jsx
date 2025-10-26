import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
    supportsCssHighlight,
    computeOverlayRects,
    getOffsetsForRange,
    createRangeFromOffsets,
    scrollRangeIntoView
} from '../../../utils/selection';

const CSS_HIGHLIGHT_KEY = 'jump-highlight';
const EMPTY_TOOLTIP_POSITION = { x: 0, y: 0 };

const DEFAULT_CHAT_HELPERS = {
    isSelectionInContext: () => false,
    addContextEntry: () => {},
    removeSuggestionContext: () => {},
    startChatAboutSuggestion: () => {}
};

const useHighlightStore = ({ summary, documents }) => {
    const chatHelpersRef = useRef(DEFAULT_CHAT_HELPERS);

    const [selectedText, setSelectedText] = useState('');
    const [selectedRange, setSelectedRange] = useState(null);
    const [selectedDocumentText, setSelectedDocumentText] = useState('');
    const [selectedDocumentRange, setSelectedDocumentRange] = useState(null);
    const [showTabTooltip, setShowTabTooltip] = useState(false);
    const [tooltipPosition, setTooltipPosition] = useState(EMPTY_TOOLTIP_POSITION);
    const [hoveredSuggestion, setHoveredSuggestion] = useState(null);
    const [hoverPosition, setHoverPosition] = useState({ x: 0, y: 0 });
    const hoverTimeoutRef = useRef(null);
    const [highlightedContext, setHighlightedContext] = useState(null);
    const [persistentSuggestionPopup, setPersistentSuggestionPopup] = useState(null);
    const [pendingHighlight, setPendingHighlight] = useState(null);
    const [activeHighlight, setActiveHighlight] = useState(null);
    const [highlightRects, setHighlightRects] = useState([]);
    const [rejectedSuggestions, setRejectedSuggestions] = useState(() => new Set());
    const cssHighlightHandleRef = useRef(null);

    const registerChatHelpers = useCallback((helpers) => {
        chatHelpersRef.current = { ...DEFAULT_CHAT_HELPERS, ...helpers };
    }, []);

    const clearCssHighlight = useCallback(() => {
        if (!supportsCssHighlight()) {
            return;
        }
        if (cssHighlightHandleRef.current) {
            window.CSS.highlights.delete(cssHighlightHandleRef.current);
            cssHighlightHandleRef.current = null;
        }
    }, []);

    const applyCssHighlight = useCallback((range) => {
        if (!supportsCssHighlight()) {
            return false;
        }
        clearCssHighlight();
        const highlight = new window.Highlight(range);
        window.CSS.highlights.set(CSS_HIGHLIGHT_KEY, highlight);
        cssHighlightHandleRef.current = CSS_HIGHLIGHT_KEY;
        return true;
    }, [clearCssHighlight]);

    const clearActiveHighlight = useCallback(() => {
        clearCssHighlight();
        setActiveHighlight(null);
        setHighlightRects([]);
    }, [clearCssHighlight]);

    useEffect(() => () => clearCssHighlight(), [clearCssHighlight]);
    useEffect(() => {
        if (typeof document === 'undefined') {
            return;
        }
        if (!document.getElementById('workspace-highlight-style')) {
            const styleEl = document.createElement('style');
            styleEl.id = 'workspace-highlight-style';
            styleEl.textContent = '::highlight(' + CSS_HIGHLIGHT_KEY + ') { background-color: rgba(250, 204, 21, 0.35); }';
            document.head.appendChild(styleEl);
        }
    }, []);


    const resetSelectionState = useCallback(() => {
        setSelectedText('');
        setSelectedRange(null);
        setSelectedDocumentText('');
        setSelectedDocumentRange(null);
        setShowTabTooltip(false);
        setTooltipPosition(EMPTY_TOOLTIP_POSITION);
    }, []);

    const updateTooltip = useCallback((rect) => {
        setTooltipPosition({
            x: rect.left + rect.width / 2,
            y: rect.top - 30
        });
    }, []);

    const captureSummarySelection = useCallback((range, container) => {
        const offsets = getOffsetsForRange(container, range);
        if (!offsets) {
            return;
        }
        setSelectedText(offsets.text);
        setSelectedRange({ start: offsets.start, end: offsets.end });
        setSelectedDocumentText('');
        setSelectedDocumentRange(null);
        const alreadyInContext = chatHelpersRef.current.isSelectionInContext({
            type: 'selection',
            range: { start: offsets.start, end: offsets.end }
        });
        setShowTabTooltip(!alreadyInContext);
        updateTooltip(range.getBoundingClientRect());
    }, [updateTooltip]);

    const captureDocumentSelection = useCallback((range, container, documentId) => {
        const offsets = getOffsetsForRange(container, range);
        if (!offsets) {
            return;
        }
        setSelectedDocumentText(offsets.text);
        setSelectedDocumentRange({ start: offsets.start, end: offsets.end });
        setSelectedText('');
        setSelectedRange(null);
        const alreadyInContext = chatHelpersRef.current.isSelectionInContext({
            type: 'document-selection',
            range: { start: offsets.start, end: offsets.end },
            documentId
        });
        setShowTabTooltip(!alreadyInContext);
        updateTooltip(range.getBoundingClientRect());
    }, [updateTooltip]);

    useEffect(() => {
        const handleSelectionChange = () => {
            const summaryEl = summary.summaryRef.current;
            const documentEl = documents.documentRef.current;

            if (!summaryEl && !documentEl) {
                return;
            }

            if (summaryEl instanceof HTMLTextAreaElement && document.activeElement === summaryEl) {
                const { selectionStart, selectionEnd, value } = summaryEl;
                if (selectionStart != null && selectionEnd != null && selectionStart !== selectionEnd) {
                    setSelectedText(value.slice(selectionStart, selectionEnd));
                    setSelectedRange({ start: selectionStart, end: selectionEnd });
                    setSelectedDocumentText('');
                    setSelectedDocumentRange(null);
                    const alreadyInContext = chatHelpersRef.current.isSelectionInContext({
                        type: 'selection',
                        range: { start: selectionStart, end: selectionEnd }
                    });
                    setShowTabTooltip(!alreadyInContext);
                    const rect = summaryEl.getBoundingClientRect();
                    setTooltipPosition({ x: rect.left + rect.width / 2, y: rect.top - 30 });
                    return;
                }
            }

            const selection = window.getSelection();
            if (!selection || selection.rangeCount === 0) {
                return;
            }

            const range = selection.getRangeAt(0);

            if (summary.summaryRef.current && summary.summaryRef.current.contains(range.startContainer)) {
                if (!range.collapsed) {
                    captureSummarySelection(range, summary.summaryRef.current);
                } else {
                    resetSelectionState();
                }
                return;
            }

            if (documents.documentRef.current && documents.documentRef.current.contains(range.startContainer)) {
                if (!range.collapsed) {
                    captureDocumentSelection(range, documents.documentRef.current, documents.selectedDocument);
                } else {
                    resetSelectionState();
                }
                return;
            }

            resetSelectionState();
        };

        const handleClick = (event) => {
            const summaryEl = summary.summaryRef.current;
            const documentEl = documents.documentRef.current;
            if (
                summaryEl && !summaryEl.contains(event.target) &&
                documentEl && !documentEl.contains(event.target)
            ) {
                resetSelectionState();
                window.getSelection()?.removeAllRanges();
                clearActiveHighlight();
            }

            if (
                persistentSuggestionPopup &&
                !event.target.closest('.suggestion-popup') &&
                !event.target.closest('.highlighted-suggestion')
            ) {
                setPersistentSuggestionPopup(null);
                setHighlightedContext(null);
                clearActiveHighlight();
            }
        };

        document.addEventListener('selectionchange', handleSelectionChange);
        document.addEventListener('click', handleClick);
        return () => {
            document.removeEventListener('selectionchange', handleSelectionChange);
            document.removeEventListener('click', handleClick);
        };
    }, [captureDocumentSelection, captureSummarySelection, clearActiveHighlight, documents.documentRef, documents.selectedDocument, persistentSuggestionPopup, resetSelectionState, summary.summaryRef]);

    useEffect(() => {
        const handleKeyDown = (event) => {
            if (event.key === 'Tab' && !summary.isEditMode && (selectedText || selectedDocumentText)) {
                event.preventDefault();
                setShowTabTooltip(false);
                if (selectedText && selectedRange) {
                    chatHelpersRef.current.addContextEntry({
                        type: 'selection',
                        content: selectedText,
                        source: 'Case Summary',
                        range: selectedRange
                    });
                } else if (selectedDocumentText && selectedDocumentRange) {
                    const currentDoc = documents.documents.find((doc) => doc.id === documents.selectedDocument);
                    chatHelpersRef.current.addContextEntry({
                        type: 'document-selection',
                        content: selectedDocumentText,
                        source: currentDoc ? currentDoc.title : 'Unknown Document',
                        documentId: documents.selectedDocument,
                        range: selectedDocumentRange
                    });
                }
                window.getSelection()?.removeAllRanges();
                resetSelectionState();
            }

            if (event.key === 'Escape' && (selectedText || selectedDocumentText)) {
                event.preventDefault();
                window.getSelection()?.removeAllRanges();
                resetSelectionState();
            }
        };

        document.addEventListener('keydown', handleKeyDown);
        return () => document.removeEventListener('keydown', handleKeyDown);
    }, [documents.documents, documents.selectedDocument, resetSelectionState, selectedDocumentRange, selectedDocumentText, selectedRange, selectedText, summary.isEditMode]);

    useEffect(() => {
        if (summary.isEditMode) {
            clearActiveHighlight();
        }
    }, [summary.isEditMode, clearActiveHighlight]);

    useEffect(() => {
        if (activeHighlight?.type === 'document' && activeHighlight.documentId && activeHighlight.documentId !== documents.selectedDocument) {
            clearActiveHighlight();
        }
    }, [activeHighlight, clearActiveHighlight, documents.selectedDocument]);

    const handleSuggestionHover = useCallback((event, suggestion) => {
        if (!event?.target) {
            return;
        }
        if (hoverTimeoutRef.current) {
            clearTimeout(hoverTimeoutRef.current);
            hoverTimeoutRef.current = null;
        }
        const rect = event.target.getBoundingClientRect();
        setHoverPosition({ x: rect.left, y: rect.bottom + 5 });
        setHoveredSuggestion(suggestion);
    }, []);

    const handleSuggestionLeave = useCallback(() => {
        hoverTimeoutRef.current = setTimeout(() => {
            setHoveredSuggestion(null);
            hoverTimeoutRef.current = null;
        }, 200);
    }, []);

    const handlePopupEnter = useCallback(() => {
        if (hoverTimeoutRef.current) {
            clearTimeout(hoverTimeoutRef.current);
            hoverTimeoutRef.current = null;
        }
    }, []);

    const handlePopupLeave = useCallback(() => {
        setHoveredSuggestion(null);
    }, []);

    const renderSummaryWithSuggestions = useCallback((text) => {
        if (summary.isEditMode || !text) {
            return text;
        }

        const applicable = summary.suggestions.filter((suggestion) =>
            suggestion.type === 'edit' &&
            text.includes(suggestion.originalText) &&
            !rejectedSuggestions.has(suggestion.id)
        );

        if (applicable.length === 0) {
            return text;
        }

        let parts = text.split(/(\n)/);

        applicable.forEach((suggestion) => {
            const newParts = [];
            parts.forEach((part, index) => {
                if (typeof part === 'string' && part.includes(suggestion.originalText)) {
                    const segments = part.split(suggestion.originalText);
                    segments.forEach((segment, segmentIndex) => {
                        if (segment) {
                            newParts.push(segment);
                        }
                        if (segmentIndex < segments.length - 1) {
                            const isHighlighted = highlightedContext?.type === 'suggestion' && highlightedContext.id === suggestion.id;
                            newParts.push(
                                <span
                                    key={`suggestion-${suggestion.id}-${index}-${segmentIndex}`}
                                    data-suggestion-id={suggestion.id}
                                    className={`border-b-2 border-yellow-400 cursor-pointer hover:bg-yellow-200 highlighted-suggestion ${
                                        isHighlighted ? 'bg-yellow-300' : 'bg-yellow-100'
                                    }`}
                                    onMouseEnter={(event) => {
                                        if (!persistentSuggestionPopup) {
                                            handleSuggestionHover(event, suggestion);
                                        }
                                    }}
                                    onMouseLeave={!persistentSuggestionPopup ? handleSuggestionLeave : undefined}
                                >
                                    {suggestion.originalText}
                                </span>
                            );
                        }
                    });
                } else {
                    newParts.push(part);
                }
            });
            parts = newParts;
        });

        return parts;
    }, [
        handleSuggestionHover,
        handleSuggestionLeave,
        highlightedContext,
        persistentSuggestionPopup,
        rejectedSuggestions,
        summary.isEditMode,
        summary.suggestions
    ]);

    const applySuggestion = useCallback((suggestion) => {
        if (!suggestion) {
            return;
        }
        if (suggestion.type === 'edit') {
            summary.setSummaryText((prev) => prev.replace(suggestion.originalText, suggestion.text));
        }
        setHoveredSuggestion(null);
        chatHelpersRef.current.removeSuggestionContext(suggestion.id);
    }, [summary]);

    const rejectSuggestion = useCallback((suggestion) => {
        if (!suggestion) {
            return;
        }
        setRejectedSuggestions((prev) => new Set(prev).add(suggestion.id));
        setHoveredSuggestion(null);
        chatHelpersRef.current.removeSuggestionContext(suggestion.id);
    }, []);

    const startSuggestionDiscussion = useCallback((suggestion) => {
        if (!suggestion) {
            return;
        }
        chatHelpersRef.current.startChatAboutSuggestion(suggestion);
        setHoveredSuggestion(null);
        setPersistentSuggestionPopup(null);
    }, []);

    const handleContextClick = useCallback((contextItem) => {
        clearActiveHighlight();
        if (contextItem.type === 'suggestion') {
            const suggestion = summary.suggestions.find((candidate) => candidate.id === contextItem.suggestionId);
            if (suggestion) {
                setHighlightedContext({ type: 'suggestion', id: suggestion.id });
                setPersistentSuggestionPopup(suggestion);

                if (suggestion.position && summary.summaryRef.current) {
                    const range = createRangeFromOffsets(summary.summaryRef.current, suggestion.position.start, suggestion.position.end);
                    if (range) {
                        scrollRangeIntoView(summary.summaryRef.current, range);
                    } else {
                        summary.summaryRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                } else if (summary.summaryRef.current) {
                    summary.summaryRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }
            return;
        }

        if (contextItem.type === 'selection' && contextItem.range) {
            setPendingHighlight({ type: 'summary', range: contextItem.range, timestamp: Date.now() });
            return;
        }

        if (contextItem.type === 'document-selection' && contextItem.range) {
            const targetDocumentId = contextItem.documentId ?? documents.selectedDocument;
            const highlightPayload = {
                type: 'document',
                range: contextItem.range,
                documentId: targetDocumentId,
                timestamp: Date.now()
            };
            if (
                targetDocumentId != null &&
                targetDocumentId !== documents.selectedDocument &&
                documents.documents.some((doc) => doc.id === targetDocumentId)
            ) {
                setPendingHighlight(highlightPayload);
                documents.setSelectedDocument(targetDocumentId);
            } else {
                setPendingHighlight(highlightPayload);
            }
        }
    }, [clearActiveHighlight, documents, summary.suggestions, summary.summaryRef]);

    useEffect(() => {
        if (!pendingHighlight) {
            return;
        }

        const { type, range, documentId } = pendingHighlight;
        if (!range || range.start == null || range.end == null || range.start === range.end) {
            setPendingHighlight(null);
            return;
        }

        if (type === 'summary' && summary.isEditMode) {
            setPendingHighlight(null);
            return;
        }

        if (type === 'document' && documentId != null && documentId !== documents.selectedDocument) {
            return;
        }

        const container = type === 'document' ? documents.documentRef.current : summary.summaryRef.current;
        if (!container) {
            return;
        }

        const applyHighlight = () => {
            const domRange = createRangeFromOffsets(container, range.start, range.end);
            if (!domRange) {
                clearActiveHighlight();
                setPendingHighlight(null);
                return;
            }

            scrollRangeIntoView(container, domRange);
            const usedCss = applyCssHighlight(domRange);
            if (!usedCss) {
                setHighlightRects(computeOverlayRects(container, domRange));
            } else {
                setHighlightRects([]);
            }

            setActiveHighlight({
                type,
                documentId: type === 'document' ? documentId || documents.selectedDocument : null,
                range: { start: range.start, end: range.end },
                useOverlay: !usedCss
            });
            setPendingHighlight(null);
        };

        requestAnimationFrame(applyHighlight);
    }, [applyCssHighlight, clearActiveHighlight, documents.documentRef, documents.selectedDocument, pendingHighlight, summary.isEditMode, summary.summaryRef]);

    useEffect(() => {
        if (!activeHighlight || !activeHighlight.useOverlay) {
            return;
        }

        const container = activeHighlight.type === 'document' ? documents.documentRef.current : summary.summaryRef.current;
        if (!container) {
            return;
        }

        let animationFrameId = null;

        const updateRects = () => {
            const overlayRange = createRangeFromOffsets(container, activeHighlight.range.start, activeHighlight.range.end);
            if (!overlayRange) {
                clearActiveHighlight();
                return;
            }
            setHighlightRects(computeOverlayRects(container, overlayRange));
        };

        updateRects();

        const handleScrollOrResize = () => {
            if (animationFrameId) {
                cancelAnimationFrame(animationFrameId);
            }
            animationFrameId = requestAnimationFrame(updateRects);
        };

        container.addEventListener('scroll', handleScrollOrResize);
        window.addEventListener('resize', handleScrollOrResize);

        return () => {
            container.removeEventListener('scroll', handleScrollOrResize);
            window.removeEventListener('resize', handleScrollOrResize);
            if (animationFrameId) {
                cancelAnimationFrame(animationFrameId);
            }
        };
    }, [activeHighlight, clearActiveHighlight, documents.documentRef, summary.summaryRef]);

    const value = useMemo(() => ({
        registerChatHelpers,
        selectedText,
        selectedRange,
        selectedDocumentText,
        selectedDocumentRange,
        showTabTooltip,
        tooltipPosition,
        hoveredSuggestion,
        hoverPosition,
        highlightedContext,
        setHighlightedContext,
        persistentSuggestionPopup,
        setPersistentSuggestionPopup,
        activeHighlight,
        highlightRects,
        renderSummaryWithSuggestions,
        handleSuggestionHover,
        handleSuggestionLeave,
        handlePopupEnter,
        handlePopupLeave,
        applySuggestion,
        rejectSuggestion,
        startSuggestionDiscussion,
        handleContextClick,
        clearActiveHighlight
    }), [
        activeHighlight,
        applySuggestion,
        handleContextClick,
        handlePopupEnter,
        handlePopupLeave,
        handleSuggestionHover,
        handleSuggestionLeave,
        highlightedContext,
        highlightRects,
        hoveredSuggestion,
        hoverPosition,
        persistentSuggestionPopup,
        registerChatHelpers,
        renderSummaryWithSuggestions,
        rejectSuggestion,
        selectedDocumentRange,
        selectedDocumentText,
        selectedRange,
        selectedText,
        showTabTooltip,
        startSuggestionDiscussion,
        tooltipPosition,
        clearActiveHighlight
    ]);

    return value;
};

export default useHighlightStore;

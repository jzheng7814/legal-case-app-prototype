import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Upload, FileText, MessageCircle, Check, X, Edit3, Sparkles, Send, Plus, Trash2 } from 'lucide-react';

const supportsCssHighlight = () => typeof window !== 'undefined' && window.CSS && window.CSS.highlights && typeof window.Highlight === 'function';

const computeOverlayRects = (container, range) => {
    const containerRect = container.getBoundingClientRect();
    return Array.from(range.getClientRects())
        .map((rect) => ({
            top: rect.top - containerRect.top + container.scrollTop,
            left: rect.left - containerRect.left + container.scrollLeft,
            width: rect.width,
            height: rect.height
        }))
        .filter((rect) => rect.width > 0 && rect.height > 0);
};

const getOffsetsForRange = (container, range) => {
    if (!container || !range) {
        return null;
    }

    if (container instanceof HTMLTextAreaElement) {
        const { selectionStart, selectionEnd, value } = container;
        if (selectionStart == null || selectionEnd == null || selectionStart === selectionEnd) {
            return null;
        }
        return {
            start: selectionStart,
            end: selectionEnd,
            text: value.slice(selectionStart, selectionEnd)
        };
    }

    if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) {
        return null;
    }

    const preRange = range.cloneRange();
    preRange.selectNodeContents(container);
    preRange.setEnd(range.startContainer, range.startOffset);
    const start = preRange.toString().length;
    const selectedText = range.toString();
    const end = start + selectedText.length;
    preRange.detach?.();

    return { start, end, text: selectedText };
};

const createRangeFromOffsets = (container, start, end) => {
    if (!container || start == null || end == null || start === end) {
        return null;
    }

    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    let currentPos = 0;
    let startNode = null;
    let endNode = null;
    let startOffset = 0;
    let endOffset = 0;

    while (walker.nextNode()) {
        const node = walker.currentNode;
        const nodeLength = node.textContent.length;

        if (!startNode && currentPos + nodeLength > start) {
            startNode = node;
            startOffset = start - currentPos;
        }

        if (!endNode && currentPos + nodeLength >= end) {
            endNode = node;
            endOffset = end - currentPos;
            break;
        }

        currentPos += nodeLength;
    }

    if (!startNode || !endNode) {
        return null;
    }

    const range = document.createRange();
    range.setStart(startNode, startOffset);
    range.setEnd(endNode, endOffset);
    return range;
};

const scrollRangeIntoView = (container, range) => {
    if (!container || !range) {
        return;
    }

    const rects = range.getClientRects();
    if (!rects.length) {
        return;
    }

    const containerRect = container.getBoundingClientRect();
    const firstRect = rects[0];
    const lastRect = rects[rects.length - 1];
    const currentScrollTop = container.scrollTop || 0;
    const targetTop = firstRect.top - containerRect.top + currentScrollTop;
    const targetBottom = lastRect.bottom - containerRect.top + currentScrollTop;
    const targetMiddle = (targetTop + targetBottom) / 2;
    const desiredTop = Math.max(0, targetMiddle - container.clientHeight / 2);

    if (typeof container.scrollTo === 'function') {
        container.scrollTo({ top: desiredTop, behavior: 'smooth' });
    } else {
        container.scrollTop = desiredTop;
    }
};

const scrollElementIntoContainer = (container, element) => {
    if (!container || !element) {
        return;
    }

    const containerRect = container.getBoundingClientRect();
    const elementRect = element.getBoundingClientRect();
    const currentScrollTop = container.scrollTop || 0;
    const targetTop = elementRect.top - containerRect.top + currentScrollTop;
    const targetBottom = elementRect.bottom - containerRect.top + currentScrollTop;
    const targetMiddle = (targetTop + targetBottom) / 2;
    const desiredTop = Math.max(0, targetMiddle - container.clientHeight / 2);

    if (typeof container.scrollTo === 'function') {
        container.scrollTo({ top: desiredTop, behavior: 'smooth' });
    } else {
        container.scrollTop = desiredTop;
    }
};

const calculateTextChange = (previousText, nextText) => {
    if (previousText === nextText) {
        return null;
    }

    let start = 0;
    const prevLength = previousText.length;
    const nextLength = nextText.length;

    while (start < prevLength && start < nextLength && previousText[start] === nextText[start]) {
        start += 1;
    }

    let prevEnd = prevLength - 1;
    let nextEnd = nextLength - 1;

    while (prevEnd >= start && nextEnd >= start && previousText[prevEnd] === nextText[nextEnd]) {
        prevEnd -= 1;
        nextEnd -= 1;
    }

    const removedLength = prevEnd >= start ? prevEnd - start + 1 : 0;
    const insertedLength = nextEnd >= start ? nextEnd - start + 1 : 0;

    return {
        start,
        removedLength,
        insertedLength
    };
};

const adjustRangeForChange = (range, change, maxLength) => {
    if (!range || !change) {
        return range;
    }

    const delta = change.insertedLength - change.removedLength;
    const changeEnd = change.start + change.removedLength;

    let { start, end } = range;

    if (changeEnd <= start) {
        start += delta;
        end += delta;
    } else if (change.start >= end) {
        // no adjustment needed when change is entirely after the range
    } else {
        if (change.start < start) {
            start = change.start;
        }
        end += delta;
    }

    start = Math.max(0, start);
    end = Math.max(start, end);
    const clampedEnd = Math.min(end, maxLength);
    const clampedStart = Math.min(start, clampedEnd);

    return {
        start: clampedStart,
        end: clampedEnd
    };
};

const buildChatTitle = (text) => {
    if (!text) {
        return 'Untitled Chat';
    }
    return text.length > 30 ? `${text.slice(0, 30)}...` : text;
};

const LegalCaseApp = () => {
    const [currentPage, setCurrentPage] = useState('home');
    const [documents, setDocuments] = useState([]);
    const [caseId, setCaseId] = useState('');
    const [uploadedFiles, setUploadedFiles] = useState([]);
    const [summaryText, setSummaryText] = useState('');
    const [isEditMode, setIsEditMode] = useState(false);
    const [selectedDocument, setSelectedDocument] = useState('');
    const [selectedText, setSelectedText] = useState('');
    const [selectedRange, setSelectedRange] = useState(null);
    const [selectedDocumentText, setSelectedDocumentText] = useState('');
    const [selectedDocumentRange, setSelectedDocumentRange] = useState(null);
    const [showTabTooltip, setShowTabTooltip] = useState(false);
    const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 });
    const [hoveredSuggestion, setHoveredSuggestion] = useState(null);
    const [hoverPosition, setHoverPosition] = useState({ x: 0, y: 0 });
    const [hoverTimeout, setHoverTimeout] = useState(null);
    const [chatMessages, setChatMessages] = useState([]);
    const [currentMessage, setCurrentMessage] = useState('');
    const [chatContext, setChatContext] = useState([]);
    const [chatContextsById, setChatContextsById] = useState({});
    const [allChats, setAllChats] = useState([]);
    const [currentChatId, setCurrentChatId] = useState(null);
    const [isNewChat, setIsNewChat] = useState(false);
    const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
    const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
    const [rejectedSuggestions, setRejectedSuggestions] = useState(new Set());
    const [highlightedContext, setHighlightedContext] = useState(null);
    const [persistentSuggestionPopup, setPersistentSuggestionPopup] = useState(null);
    const [pendingHighlight, setPendingHighlight] = useState(null);
    const [activeHighlight, setActiveHighlight] = useState(null);
    const [highlightRects, setHighlightRects] = useState([]);
    
    const summaryRef = useRef(null);
    const chatInputRef = useRef(null);
    const documentRef = useRef(null);
    const previousSummaryTextRef = useRef(summaryText);
    const cssHighlightHandleRef = useRef(null);

    // Mock suggestions - in real app these would come from AI backend
    const suggestions = [
        {
            id: 1,
            type: 'edit',
            originalText: 'unforeseen',
            suggestedText: 'unforeseeable',
            comment: 'Spelling correction for legal accuracy',
            position: { start: 445, end: 454 },
            sourceDocument: 'main-case'
        },
        {
            id: 2,
            type: 'addition',
            text: 'pursuant to the terms specified in the original agreement',
            comment: 'Add legal precision to contractual reference',
            insertAfter: 'Section 4.2 of the contract',
            position: { start: 320, end: 349 },
            sourceDocument: 'contract'
        },
        {
            id: 3,
            type: 'edit',
            originalText: 'Key evidence includes',
            suggestedText: 'The evidentiary record demonstrates',
            comment: 'More formal legal language',
            position: { start: 520, end: 540 },
            sourceDocument: 'main-case'
        }
    ];

    useEffect(() => {
        if (typeof document === 'undefined') {
            return;
        }
        if (!document.getElementById('jump-highlight-style')) {
            const styleEl = document.createElement('style');
            styleEl.id = 'jump-highlight-style';
            styleEl.textContent = '::highlight(jump-highlight) { background-color: rgba(250, 204, 21, 0.35); }';
            document.head.appendChild(styleEl);
        }
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
        const key = 'jump-highlight';
        window.CSS.highlights.set(key, highlight);
        cssHighlightHandleRef.current = key;
        return true;
    }, [clearCssHighlight]);

    const clearActiveHighlight = useCallback(() => {
        clearCssHighlight();
        setActiveHighlight(null);
        setHighlightRects([]);
    }, [clearCssHighlight]);

    const removeSuggestionContext = useCallback((suggestionId) => {
        const filterFn = (item) => !(item.type === 'suggestion' && item.suggestionId === suggestionId);
        setChatContext((prev) => prev.filter(filterFn));
        setChatContextsById((prev) => {
            let changed = false;
            const nextEntries = Object.entries(prev).map(([chatId, items]) => {
                const filtered = items.filter(filterFn);
                if (filtered.length !== items.length) {
                    changed = true;
                }
                return [chatId, filtered];
            });
            if (!changed) {
                return prev;
            }
            return Object.fromEntries(nextEntries);
        });
        setAllChats((prev) => prev.map((chat) => {
            if (!chat.context) {
                return chat;
            }
            const filtered = chat.context.filter(filterFn);
            if (filtered.length === chat.context.length) {
                return chat;
            }
            return { ...chat, context: filtered };
        }));
    }, []);

    const persistContextForCurrentChat = useCallback(() => {
        if (!currentChatId) {
            return;
        }
        const currentContext = chatContextsById[currentChatId] ?? chatContext;
        setChatContextsById((prev) => ({ ...prev, [currentChatId]: currentContext }));
        setAllChats((prev) => prev.map((chat) =>
            chat.id === currentChatId ? { ...chat, context: currentContext } : chat
        ));
    }, [currentChatId, chatContextsById, chatContext]);

    useEffect(() => () => clearCssHighlight(), [clearCssHighlight]);


    // Load documents from /public/documents when proceeding to summary
    const loadDocuments = async () => {
        setIsLoadingDocuments(true);
        const documentList = [
            { id: 'main-case', name: 'Johnson v. XYZ Corporation', type: 'Case File', filename: 'main-case.txt' },
            { id: 'contract', name: 'Software Licensing Agreement', type: 'Contract', filename: 'contract.txt' },
            { id: 'correspondence', name: 'Email Correspondence', type: 'Communications', filename: 'correspondence.txt' }
        ];

        const loadedDocs = [];
        
        for (const doc of documentList) {
            try {
                const response = await fetch(`/documents/${doc.filename}`);
                if (response.ok) {
                    const content = await response.text();
                    loadedDocs.push({
                        ...doc,
                        content
                    });
                } else {
                    console.warn(`Failed to load ${doc.filename}`);
                    loadedDocs.push({
                        ...doc,
                        content: `Failed to load document: ${doc.filename}`
                    });
                }
            } catch (error) {
                console.error(`Error loading ${doc.filename}:`, error);
                loadedDocs.push({
                    ...doc,
                    content: `Error loading document: ${doc.filename}`
                });
            }
        }

        setDocuments(loadedDocs);
        if (loadedDocs.length > 0) {
            setSelectedDocument(loadedDocs[0].id);
        }
        setIsLoadingDocuments(false);
    };

    // Handle text selection in summary and documents
    useEffect(() => {
        const handleSelection = () => {
            const summaryElement = summaryRef.current;
            const documentElement = documentRef.current;

            if (summaryElement instanceof HTMLTextAreaElement && document.activeElement === summaryElement) {
                const { selectionStart, selectionEnd, value } = summaryElement;
                if (selectionStart != null && selectionEnd != null && selectionStart !== selectionEnd) {
                    const selectedText = value.slice(selectionStart, selectionEnd);
                    setSelectedText(selectedText);
                    setSelectedRange({ start: selectionStart, end: selectionEnd });
                    setSelectedDocumentText('');
                    setSelectedDocumentRange(null);

                    const isAlreadyInContext = chatContext.some(item =>
                        item.type === 'selection' &&
                        item.range &&
                        item.range.start === selectionStart &&
                        item.range.end === selectionEnd
                    );
                    setShowTabTooltip(!isAlreadyInContext);

                    const textareaRect = summaryElement.getBoundingClientRect();
                    setTooltipPosition({
                        x: textareaRect.left + (textareaRect.width / 2),
                        y: textareaRect.top - 30
                    });
                    return;
                }
            }

            if (summaryElement instanceof HTMLTextAreaElement && document.activeElement === summaryElement) {
                setSelectedText('');
                setSelectedRange(null);
                setShowTabTooltip(false);
            }

            const selection = window.getSelection();
            if (!selection || selection.rangeCount === 0) {
                return;
            }

            const range = selection.getRangeAt(0);

            if (activeHighlight) {
                clearActiveHighlight();
            }

            if (
                summaryElement &&
                !(summaryElement instanceof HTMLTextAreaElement) &&
                summaryElement.contains(range.startContainer) &&
                summaryElement.contains(range.endContainer)
            ) {
                if (!range.collapsed) {
                    const offsets = getOffsetsForRange(summaryElement, range);
                    if (!offsets) {
                        return;
                    }

                    setSelectedText(offsets.text);
                    setSelectedRange({ start: offsets.start, end: offsets.end });
                    setSelectedDocumentText('');
                    setSelectedDocumentRange(null);

                    const isAlreadyInContext = chatContext.some(item =>
                        item.type === 'selection' &&
                        item.range &&
                        item.range.start === offsets.start &&
                        item.range.end === offsets.end
                    );
                    setShowTabTooltip(!isAlreadyInContext);

                    const rect = range.getBoundingClientRect();
                    setTooltipPosition({
                        x: rect.left + (rect.width / 2),
                        y: rect.top - 30
                    });
                } else {
                    setSelectedText('');
                    setSelectedRange(null);
                    setShowTabTooltip(false);
                }
                return;
            }

            if (
                documentElement &&
                documentElement.contains(range.startContainer) &&
                documentElement.contains(range.endContainer)
            ) {
                if (!range.collapsed) {
                    const offsets = getOffsetsForRange(documentElement, range);
                    if (!offsets) {
                        return;
                    }

                    setSelectedDocumentText(offsets.text);
                    setSelectedDocumentRange({ start: offsets.start, end: offsets.end });
                    setSelectedText('');
                    setSelectedRange(null);

                    const isAlreadyInContext = chatContext.some(item =>
                        item.type === 'document-selection' &&
                        item.documentId === selectedDocument &&
                        item.range &&
                        item.range.start === offsets.start &&
                        item.range.end === offsets.end
                    );
                    setShowTabTooltip(!isAlreadyInContext);

                    const rect = range.getBoundingClientRect();
                    setTooltipPosition({
                        x: rect.left + (rect.width / 2),
                        y: rect.top - 30
                    });
                } else {
                    setSelectedDocumentText('');
                    setSelectedDocumentRange(null);
                    setShowTabTooltip(false);
                }
                return;
            }

            setSelectedText('');
            setSelectedRange(null);
            setSelectedDocumentText('');
            setSelectedDocumentRange(null);
            setShowTabTooltip(false);
        };

        const handleClick = (e) => {
        if (
            summaryRef.current && !summaryRef.current.contains(e.target) &&
            documentRef.current && !documentRef.current.contains(e.target)
        ) {
            setSelectedText('');
            setSelectedRange(null);
            setSelectedDocumentText('');
            setSelectedDocumentRange(null);
            setShowTabTooltip(false);
            const activeSelection = window.getSelection();
            activeSelection?.removeAllRanges();
            clearActiveHighlight();
        }

        if (
            persistentSuggestionPopup &&
            !e.target.closest('.suggestion-popup') &&
            !e.target.closest('.highlighted-suggestion')
        ) {
            setPersistentSuggestionPopup(null);
            setHighlightedContext(null);
            clearActiveHighlight();
        }
    };

        document.addEventListener('selectionchange', handleSelection);
        document.addEventListener('click', handleClick);
        return () => {
            document.removeEventListener('selectionchange', handleSelection);
            document.removeEventListener('click', handleClick);
        };
    }, [chatContext, persistentSuggestionPopup, selectedDocument, activeHighlight, clearActiveHighlight]);

    useEffect(() => {
        const previousText = previousSummaryTextRef.current;
        if (previousText === summaryText) {
            return;
        }

        const change = calculateTextChange(previousText || '', summaryText || '');
        previousSummaryTextRef.current = summaryText;

        if (!change) {
            return;
        }

        const updateContext = (contextArray) => {
            let didUpdate = false;
            const updatedContext = contextArray.map((item) => {
                if (item.type !== 'selection' || !item.range) {
                    return item;
                }

                const adjustedRange = adjustRangeForChange(item.range, change, summaryText.length);
                const newContent = summaryText.slice(adjustedRange.start, adjustedRange.end);

                if (
                    adjustedRange.start === item.range.start &&
                    adjustedRange.end === item.range.end &&
                    newContent === item.content
                ) {
                    return item;
                }

                didUpdate = true;
                return {
                    ...item,
                    range: adjustedRange,
                    content: newContent
                };
            });

            const filteredContext = updatedContext.filter((item) => {
                if (item.type !== 'selection' || !item.range) {
                    return true;
                }
                return item.range.end > item.range.start && item.content.length > 0;
            });

            if (!didUpdate && filteredContext.length === contextArray.length) {
                return contextArray;
            }

            return filteredContext;
        };

        setChatContext((prev) => updateContext(prev));
        setChatContextsById((prev) => {
            const updatedEntries = {};
            let changed = false;
            Object.entries(prev).forEach(([chatId, contextArray]) => {
                const updatedArray = updateContext(contextArray);
                if (updatedArray !== contextArray) {
                    updatedEntries[chatId] = updatedArray;
                    changed = true;
                }
            });
            if (!changed) {
                return prev;
            }
            return { ...prev, ...updatedEntries };
        });
        setAllChats((prev) => {
            let changed = false;
            const next = prev.map((chat) => {
                if (!chat.context) {
                    return chat;
                }
                const updatedContext = updateContext(chat.context);
                if (updatedContext !== chat.context) {
                    changed = true;
                    return { ...chat, context: updatedContext };
                }
                return chat;
            });
            return changed ? next : prev;
        });
    }, [summaryText]);

    const addContextToCurrentChat = useCallback((contextEntry) => {
        if (!currentChatId) {
            setChatContext((prev) => [...prev, contextEntry]);
            return;
        }

        const existing = chatContextsById[currentChatId] ?? chatContext;
        const updated = [...existing, contextEntry];
        setChatContext(updated);
        setChatContextsById((prev) => ({ ...prev, [currentChatId]: updated }));
        setAllChats((prev) => prev.map((chat) =>
            chat.id === currentChatId ? { ...chat, context: updated } : chat
        ));
    }, [currentChatId, chatContextsById, chatContext]);

    const addSelectedDocumentTextToContext = useCallback(() => {
        if (selectedDocumentText && selectedDocumentRange) {
            const currentDoc = documents.find((d) => d.id === selectedDocument);
            const contextEntry = {
                type: 'document-selection',
                content: selectedDocumentText,
                source: currentDoc ? currentDoc.name : 'Unknown Document',
                documentId: selectedDocument,
                range: selectedDocumentRange
            };
            addContextToCurrentChat(contextEntry);
            setSelectedDocumentText('');
            setSelectedDocumentRange(null);
            setShowTabTooltip(false);
            window.getSelection().removeAllRanges();
        }
    }, [addContextToCurrentChat, documents, selectedDocument, selectedDocumentRange, selectedDocumentText]);

    const addSelectedTextToContext = useCallback(() => {
        if (selectedText && selectedRange) {
            const contextEntry = {
                type: 'selection',
                content: selectedText,
                source: 'Case Summary',
                range: selectedRange
            };
            addContextToCurrentChat(contextEntry);
            setSelectedText('');
            setSelectedRange(null);
            setShowTabTooltip(false);
            window.getSelection().removeAllRanges();
        }
    }, [addContextToCurrentChat, selectedRange, selectedText]);

    // Handle Tab key for adding selected text to chat context and Esc key for clearing selection
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.key === 'Tab' && (selectedText || selectedDocumentText) && !isEditMode) {
                e.preventDefault();
                setShowTabTooltip(false);
                if (selectedText) {
                    addSelectedTextToContext();
                } else if (selectedDocumentText) {
                    addSelectedDocumentTextToContext();
                }
            } else if (e.key === 'Escape' && (selectedText || selectedDocumentText)) {
                e.preventDefault();
                setSelectedText('');
                setSelectedRange(null);
                setSelectedDocumentText('');
                setSelectedDocumentRange(null);
                setShowTabTooltip(false);
                window.getSelection().removeAllRanges();
            }
        };

        document.addEventListener('keydown', handleKeyDown);
        return () => document.removeEventListener('keydown', handleKeyDown);
    }, [selectedText, selectedDocumentText, isEditMode, addSelectedDocumentTextToContext, addSelectedTextToContext]);

    const handleFileUpload = (event) => {
        const files = Array.from(event.target.files);
        setUploadedFiles(files);
    };

    const handleProceed = async () => {
        if (uploadedFiles.length > 0 || caseId) {
            setCurrentPage('summary');
            await loadDocuments();
        }
    };

    useEffect(() => {
        if (isEditMode) {
            clearActiveHighlight();
        }
    }, [isEditMode, clearActiveHighlight]);

    useEffect(() => {
        if (currentPage === 'home') {
            clearActiveHighlight();
        }
    }, [currentPage, clearActiveHighlight]);

    useEffect(() => {
        if (activeHighlight?.type === 'document' && activeHighlight.documentId && activeHighlight.documentId !== selectedDocument) {
            clearActiveHighlight();
        }
    }, [activeHighlight, selectedDocument, clearActiveHighlight]);

    const generateAISummary = () => {
        setIsGeneratingSummary(true);
        setSummaryText('Generating AI summary...');
        
        // Simulate AI generation with mock data
        setTimeout(() => {
            const mockSummary = `The plaintiff, Sarah Johnson, filed a breach of contract claim against XYZ Corporation on March 15, 2024. The dispute centers around a software licensing agreement signed in January 2024, where Johnson alleges that XYZ Corporation failed to deliver the promised software updates and technical support as outlined in Section 4.2 of the contract.

The defendant argues that delays were caused by unforeseen technical difficulties and that they provided alternative solutions that met the contractual obligations. Key evidence includes email correspondence between the parties from February 2024 and technical documentation showing attempted deliveries.

The court found that while XYZ Corporation did experience legitimate technical challenges, their failure to communicate these issues promptly and provide adequate alternative solutions constituted a material breach. Damages awarded to plaintiff totaled $45,000 in direct costs and lost business revenue.`;
            
            setSummaryText(mockSummary);
            setIsGeneratingSummary(false);
        }, 1500);
    };

    const toggleEditMode = () => {
        setIsEditMode(!isEditMode);
        if (isEditMode) {
            // Exiting edit mode - would regenerate suggestions from backend
            console.log('Regenerating AI suggestions...');
        }
    };

    const renderSummaryWithSuggestions = (text) => {
        if (isEditMode || !text) {
            return text;
        }

        // Find all suggestions that apply to this text and haven't been rejected
        const applicableSuggestions = suggestions.filter(s => 
            s.type === 'edit' && 
            text.includes(s.originalText) && 
            !rejectedSuggestions.has(s.id)
        );

        if (applicableSuggestions.length === 0) {
            return text;
        }

        // Preserve newline characters so offset calculations remain accurate
        let parts = text.split(/(\n)/);
        
        applicableSuggestions.forEach(suggestion => {
            const newParts = [];
            parts.forEach(part => {
                if (typeof part === 'string' && part.includes(suggestion.originalText)) {
                    const segments = part.split(suggestion.originalText);
                    for (let i = 0; i < segments.length; i++) {
                        if (segments[i]) {
                            newParts.push(segments[i]);
                        }
                        if (i < segments.length - 1) {
                            const isHighlighted = highlightedContext?.type === 'suggestion' && highlightedContext.id === suggestion.id;
                            newParts.push(
                                <span
                                    key={`suggestion-${suggestion.id}-${i}`}
                                    data-suggestion-id={suggestion.id}
                                    className={`border-b-2 border-yellow-400 cursor-pointer hover:bg-yellow-200 highlighted-suggestion ${
                                        isHighlighted ? 'bg-yellow-300' : 'bg-yellow-100'
                                    }`}
                                    onMouseEnter={(e) => !persistentSuggestionPopup && handleSuggestionHover(e, suggestion)}
                                    onMouseLeave={!persistentSuggestionPopup ? handleSuggestionLeave : undefined}
                                >
                                    {suggestion.originalText}
                                </span>
                            );
                        }
                    }
                } else if (part === '\n') {
                    newParts.push('\n');
                } else {
                    newParts.push(part);
                }
            });
            parts = newParts;
        });

        return parts;
    };

    const handleSuggestionHover = (e, suggestion) => {
        // Clear any existing timeout
        if (hoverTimeout) {
            clearTimeout(hoverTimeout);
            setHoverTimeout(null);
        }
        
        const rect = e.target.getBoundingClientRect();
        setHoverPosition({ x: rect.left, y: rect.bottom + 5 });
        setHoveredSuggestion(suggestion);
    };

    const handleSuggestionLeave = () => {
        // Set a timeout before hiding the popup to allow mouse to move to it
        const timeout = setTimeout(() => {
            setHoveredSuggestion(null);
        }, 200);
        setHoverTimeout(timeout);
    };

    const handlePopupEnter = () => {
        // Clear the timeout when mouse enters popup
        if (hoverTimeout) {
            clearTimeout(hoverTimeout);
            setHoverTimeout(null);
        }
    };

    const handlePopupLeave = () => {
        // Hide immediately when leaving popup
        setHoveredSuggestion(null);
    };

    const applySuggestion = (suggestion) => {
        if (suggestion.type === 'edit') {
            const newText = summaryText.replace(suggestion.originalText, suggestion.suggestedText);
            setSummaryText(newText);
        }
        setHoveredSuggestion(null);
        removeSuggestionContext(suggestion.id);
    };

    const rejectSuggestion = (suggestion) => {
        setRejectedSuggestions(prev => new Set([...prev, suggestion.id]));
        setHoveredSuggestion(null);
        removeSuggestionContext(suggestion.id);
    };

    const startChatAboutSuggestion = (suggestion) => {
        if (!suggestion) {
            return;
        }

        const timestamp = Date.now();
        const userMessage = {
            id: timestamp + 1,
            type: 'user',
            content: `Can we discuss this suggestion? "${suggestion.comment}"`
        };

        const aiResponse = {
            id: timestamp + 2,
            type: 'ai',
            content: `I suggested changing "${suggestion.originalText}" to "${suggestion.suggestedText}" because ${suggestion.comment.toLowerCase()}. This adjustment improves the legal clarity of the summary. Let me know if you'd like additional rationale or alternative language.`
        };

        const newMessages = [userMessage, aiResponse];
        const newChatId = timestamp;
        const newChatTitle = buildChatTitle(`Discuss: ${suggestion.comment}`);
        const preservedChatTitle = buildChatTitle(
            (chatMessages.find((message) => message.type === 'user') || {}).content || 'Saved Chat'
        );

        const newChatContext = [];

        setAllChats((prevChats) => {
            let persistedChats = prevChats;

            if (currentChatId && chatMessages.length > 0) {
                const updatedContext = chatContextsById[currentChatId] || chatContext;
                persistedChats = prevChats.map((chat) =>
                    chat.id === currentChatId
                        ? { ...chat, messages: chatMessages, context: updatedContext }
                        : chat
                );
            } else if (isNewChat && chatMessages.length > 0) {
                const preservedChat = {
                    id: timestamp - 1,
                    title: preservedChatTitle,
                    messages: chatMessages,
                    context: chatContext,
                    createdAt: new Date()
                };
                persistedChats = [preservedChat, ...prevChats];
            }

            const newChat = {
                id: newChatId,
                title: newChatTitle,
                messages: newMessages,
                context: newChatContext,
                createdAt: new Date()
            };

            return [newChat, ...persistedChats.filter((chat) => chat.id !== newChatId)];
        });

        setChatMessages(newMessages);
        setChatContextsById((prev) => ({
            ...prev,
            [newChatId]: newChatContext
        }));
        setChatContext(newChatContext);
        setCurrentChatId(newChatId);
        setIsNewChat(false);
        setHoveredSuggestion(null);
        setPersistentSuggestionPopup(null);
    };

    const handleContextClick = (contextItem) => {
        clearActiveHighlight();
        if (contextItem.type === 'suggestion') {
            const suggestion = suggestions.find((s) => s.id === contextItem.suggestionId);
            if (suggestion) {
                setHighlightedContext({ type: 'suggestion', id: suggestion.id });
                setPersistentSuggestionPopup(suggestion);

                if (suggestion.position && summaryRef.current) {
                    const range = createRangeFromOffsets(summaryRef.current, suggestion.position.start, suggestion.position.end);
                    if (range) {
                        scrollRangeIntoView(summaryRef.current, range);
                    } else {
                        summaryRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                } else if (summaryRef.current) {
                    summaryRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }
            return;
        }

        if (contextItem.type === 'selection' && contextItem.range) {
            if (summaryRef.current) {
                setPendingHighlight({
                    type: 'summary',
                    range: contextItem.range,
                    timestamp: Date.now()
                });
            }
            return;
        }

        if (contextItem.type === 'document-selection' && contextItem.range) {
            const targetDocumentId = contextItem.documentId || selectedDocument;
            const highlightPayload = {
                type: 'document',
                range: contextItem.range,
                documentId: targetDocumentId,
                timestamp: Date.now()
            };

            if (targetDocumentId && targetDocumentId !== selectedDocument) {
                setPendingHighlight(highlightPayload);
                setSelectedDocument(targetDocumentId);
            } else {
                setPendingHighlight(highlightPayload);
            }
        }
    };

    const removeContextItem = (indexToRemove) => {
        clearActiveHighlight();
        if (currentChatId) {
            const existing = chatContextsById[currentChatId] ?? chatContext;
            const updated = existing.filter((_, index) => index !== indexToRemove);
            setChatContext(updated);
            setChatContextsById((prev) => ({ ...prev, [currentChatId]: updated }));
            setAllChats((prev) => prev.map((chat) =>
                chat.id === currentChatId ? { ...chat, context: updated } : chat
            ));
        } else {
            setChatContext((prev) => prev.filter((_, index) => index !== indexToRemove));
        }
    };

    useEffect(() => {
        if (!pendingHighlight) {
            return;
        }

        const { type, range, documentId } = pendingHighlight;
        if (!range || range.start == null || range.end == null || range.start === range.end) {
            setPendingHighlight(null);
            return;
        }

        if (type === 'summary' && isEditMode) {
            setPendingHighlight(null);
            return;
        }

        if (type === 'document' && documentId && documentId !== selectedDocument) {
            return;
        }

        const container = type === 'document' ? documentRef.current : summaryRef.current;
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

            const usedCssHighlight = applyCssHighlight(domRange);
            if (!usedCssHighlight) {
                setHighlightRects(computeOverlayRects(container, domRange));
            } else {
                setHighlightRects([]);
            }

            setActiveHighlight({
                type,
                documentId: type === 'document' ? documentId || selectedDocument : null,
                range: { start: range.start, end: range.end },
                useOverlay: !usedCssHighlight
            });
            setPendingHighlight(null);
        };

        requestAnimationFrame(applyHighlight);
    }, [pendingHighlight, selectedDocument, isEditMode, applyCssHighlight, clearActiveHighlight]);

    useEffect(() => {
        if (!activeHighlight || !activeHighlight.useOverlay) {
            return;
        }

        const container = activeHighlight.type === 'document' ? documentRef.current : summaryRef.current;
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
    }, [activeHighlight, clearActiveHighlight]);

    const sendChatMessage = () => {
        if (currentMessage.trim()) {
            const userMessage = {
                id: Date.now(),
                type: 'user',
                content: currentMessage
            };
            
            const aiResponse = {
                id: Date.now() + 1,
                type: 'ai',
                content: `I understand your question about: "${currentMessage}". Based on the context provided, here's my analysis...`
            };

            const newMessages = [...chatMessages, userMessage, aiResponse];
            setChatMessages(newMessages);
            setCurrentMessage('');
            
            // Persist message history depending on chat lifecycle state
            if (isNewChat && chatMessages.length === 0) {
                saveCurrentChat(newMessages);
            } else if (currentChatId) {
                updateExistingChat(newMessages);
            } else if (!currentChatId) {
                // First-ever chat before the user explicitly creates one
                saveCurrentChat(newMessages);
            }
        }
    };

    const createNewChat = () => {
        // Save current chat if it has messages
        if (chatMessages.length > 0 && isNewChat) {
            saveCurrentChat(chatMessages);
        }
        if (currentChatId) {
            persistContextForCurrentChat();
        }
        
        // Reset to new chat state
        setChatMessages([]);
        setChatContext([]);
        setCurrentChatId(null);
        setIsNewChat(true);
    };

    const saveCurrentChat = (messages) => {
        const chatId = Date.now();
        const title = generateChatTitle(messages);
        const newChat = {
            id: chatId,
            title,
            messages,
            context: chatContext,
            createdAt: new Date()
        };
        
        setAllChats(prev => [newChat, ...prev]);
        setChatContextsById(prev => ({ ...prev, [chatId]: chatContext }));
        setCurrentChatId(chatId);
        setIsNewChat(false);
    };

    const updateExistingChat = (messages) => {
        if (!currentChatId) {
            return;
        }
        const currentContext = chatContextsById[currentChatId] ?? chatContext;
        setAllChats(prev => prev.map(chat => 
            chat.id === currentChatId 
                ? { ...chat, messages, context: currentContext }
                : chat
        ));
        setChatContextsById(prev => ({ ...prev, [currentChatId]: currentContext }));
    };

    const generateChatTitle = (messages) => {
        const userMessages = messages.filter(m => m.type === 'user');
        if (userMessages.length > 0) {
            return userMessages[0].content.substring(0, 30) + '...';
        }
        return `Chat ${new Date().toLocaleDateString()}`;
    };

    const selectChat = (chatId) => {
        if (chatId === currentChatId) {
            return;
        }

        if (isNewChat && chatMessages.length === 0) {
            // Don't save empty new chats
        } else if (isNewChat && chatMessages.length > 0) {
            saveCurrentChat(chatMessages);
        } else if (currentChatId && chatMessages.length > 0) {
            updateExistingChat(chatMessages);
        } else if (currentChatId) {
            persistContextForCurrentChat();
        }

        const chat = allChats.find(c => c.id === chatId);
        if (chat) {
            const storedContext = chatContextsById[chat.id] ?? (chat.context || []);
            setChatContextsById(prev => ({ ...prev, [chat.id]: storedContext }));
            setChatMessages(chat.messages);
            setChatContext(storedContext);
            setCurrentChatId(chat.id);
            setIsNewChat(false);
        }
    };

    const deleteCurrentChat = () => {
        if (currentChatId) {
            setAllChats(prev => prev.filter(chat => chat.id !== currentChatId));
            setChatContextsById(prev => {
                const { [currentChatId]: _removed, ...rest } = prev;
                return rest;
            });
        }
        
        // Reset to new chat state
        setChatMessages([]);
        setChatContext([]);
        setCurrentChatId(null);
        setIsNewChat(true);
    };

    const getCurrentDocument = () => {
        const doc = documents.find(d => d.id === selectedDocument);
        if (isLoadingDocuments) {
            return 'Loading documents...';
        }
        return doc ? doc.content : 'No document selected';
    };

    if (currentPage === 'home') {
        return (
            <div className="min-h-screen bg-gray-50 p-6">
                <div className="max-w-2xl mx-auto">
                    <h1 className="text-3xl font-bold text-gray-900 mb-8 text-center">
                        Legal Case Summarization
                    </h1>
                    
                    <div className="bg-white rounded-lg shadow-md p-6 mb-6">
                        <h2 className="text-xl font-semibold mb-4">Upload Case Documents</h2>
                        
                        <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 mb-4">
                            <div className="text-center">
                                <Upload className="mx-auto h-12 w-12 text-gray-400 mb-4" />
                                <div className="flex text-sm text-gray-600">
                                    <label className="relative cursor-pointer bg-white rounded-md font-medium text-blue-600 hover:text-blue-500">
                                        <span>Upload case files</span>
                                        <input
                                            type="file"
                                            className="sr-only"
                                            multiple
                                            accept=".pdf,.doc,.docx,.txt"
                                            onChange={handleFileUpload}
                                        />
                                    </label>
                                    <p className="pl-1">or drag and drop</p>
                                </div>
                                <p className="text-xs text-gray-500">PDF, DOC, DOCX, TXT up to 10MB</p>
                            </div>
                        </div>
                        
                        {uploadedFiles.length > 0 && (
                            <div className="space-y-2 mb-4">
                                {uploadedFiles.map((file, index) => (
                                    <div key={index} className="flex items-center p-3 bg-blue-50 rounded-md">
                                        <FileText className="h-5 w-5 text-blue-600 mr-2" />
                                        <span className="text-sm text-blue-900">{file.name}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                        
                        <div className="mt-4">
                            <div className="text-center text-gray-500 mb-4">OR</div>
                            <input
                                type="text"
                                placeholder="Enter Case ID (e.g., 3:24-cv-01234-ABC)"
                                value={caseId}
                                onChange={(e) => setCaseId(e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                        </div>
                    </div>
                    
                    <button
                        onClick={handleProceed}
                        disabled={!(uploadedFiles.length > 0 || caseId)}
                        className="w-full bg-blue-600 text-white py-3 px-4 rounded-md font-medium hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
                    >
                        Proceed to Summary Editor
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50">
            {/* Header */}
            <div className="bg-white border-b px-6 py-4">
                <div className="flex items-center justify-between">
                    <h1 className="text-xl font-semibold">Case Summary Editor</h1>
                    <button
                        onClick={() => setCurrentPage('home')}
                        className="text-blue-600 hover:text-blue-800"
                    >
                        ← Back to Home
                    </button>
                </div>
            </div>
            
            <div className="flex h-[calc(100vh-73px)]">
                {/* Left Pane - Summary */}
                <div className="w-2/5 border-r bg-white flex flex-col">
                    {/* Summary Header */}
                    <div className="border-b p-4">
                        <div className="flex items-center justify-between">
                            <h2 className="text-lg font-semibold">Case Summary</h2>
                            <div className="flex items-center space-x-2">
                                {!summaryText && isEditMode && (
                                    <span className="text-xs text-gray-400 italic">(Generate disabled in edit mode)</span>
                                )}
                                {!summaryText && !isEditMode && (
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
                    
                    {/* Summary Content */}
                    <div className="flex-1 p-4">            
                        <div className="flex-1 pb-4">
                            {isEditMode ? (
                                <textarea
                                    ref={summaryRef}
                                    value={summaryText}
                                    onChange={(e) => setSummaryText(e.target.value)}
                                    placeholder="Write your case summary here..."
                                    className="w-full h-full px-3 py-2 border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm leading-relaxed"
                                    style={{ minHeight: 'calc(100vh - 300px)', fontFamily: 'inherit' }}
                                />
                            ) : (
                <div
                    ref={summaryRef}
                    className="relative w-full px-3 py-2 border border-gray-300 rounded-md text-sm leading-relaxed cursor-text overflow-y-auto"
                    style={{ whiteSpace: 'pre-wrap', height: 'calc(100vh - 250px)', maxHeight: 'calc(100vh - 250px)' }}
                >
                    {summaryText ? renderSummaryWithSuggestions(summaryText) : 
                        <span className="text-gray-500">Your summary will appear here...</span>
                    }
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
                </div>
                
                {/* Middle Pane - Chat */}
                <div className="w-1/3 border-r bg-white flex flex-col">
                    <div className="border-b p-4">
                        <div className="flex items-center justify-between mb-2">
                            <h2 className="text-lg font-semibold">AI Assistant</h2>
                            <div className="flex items-center space-x-2">
                                <button
                                    onClick={createNewChat}
                                    className="p-1 text-blue-600 hover:text-blue-800"
                                    title="New Chat"
                                >
                                    <Plus className="h-4 w-4" />
                                </button>
                                <button
                                    onClick={deleteCurrentChat}
                                    className="p-1 text-red-600 hover:text-red-800"
                                    title="Delete Current Chat"
                                >
                                    <Trash2 className="h-4 w-4" />
                                </button>
                            </div>
                        </div>
                        <div className="flex space-x-2">
                            <select
                                value={currentChatId || 'new'}
                                onChange={(e) => {
                                    if (e.target.value === 'new') {
                                        createNewChat();
                                    } else {
                                        selectChat(parseInt(e.target.value));
                                    }
                                }}
                                className="flex-1 px-2 py-1 text-xs border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                            >
                                <option value="new">
                                    {isNewChat ? 'New Chat' : 'Create New Chat'}
                                </option>
                                {allChats.map((chat) => (
                                    <option key={chat.id} value={chat.id}>
                                        {chat.title}
                                    </option>
                                ))}
                            </select>
                        </div>
                        {isEditMode && (
                            <div className="text-xs text-gray-400 italic mt-1">
                                Chat input disabled in edit mode
                            </div>
                        )}
                    </div>
                    
                    {/* Chat Messages */}
                    <div className="flex-1 p-4 overflow-y-auto pb-4">
                        {chatMessages.length === 0 ? (
                            <div className="text-center text-gray-500 text-sm">
                                {isEditMode ? 
                                    'Chat history is visible but input is disabled in edit mode' : 
                                    'Start a conversation with AI about your case summary'
                                }
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {chatMessages.map((message) => (
                                    <div
                                        key={message.id}
                                        className={`p-3 rounded-lg text-sm ${
                                            message.type === 'user' 
                                                ? 'bg-blue-600 text-white ml-4' 
                                                : message.type === 'ai'
                                                ? 'bg-gray-100 mr-4'
                                                : 'bg-yellow-50 text-yellow-800 text-xs'
                                        }`}
                                    >
                                        {message.content}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                    
                    {/* Chat Context - Above Input */}
                    {chatContext.length > 0 && (
                        <div className="border-t bg-gray-50 p-3" style={{ maxHeight: '120px', overflowY: 'auto' }}>
                            <div className="text-xs font-medium text-gray-700 mb-2">Context ({chatContext.length}):</div>
                            <div className="space-y-1">
                                {chatContext.map((item, index) => (
                                    <div 
                                        key={index} 
                                        className="text-xs bg-white p-2 rounded border flex items-start justify-between cursor-pointer hover:bg-gray-50"
                                        onClick={() => handleContextClick(item)}
                                    >
                                        <div className="flex-1">
                                            <span className="font-medium text-blue-600">
                                                {item.type === 'suggestion' ? 'Suggestion: ' : 
                                                  item.type === 'document-selection' ? `${item.source}: ` : 
                                                  `${item.source}: `}
                                            </span>
                                            <span className="text-gray-600">
                                                {item.content.substring(0, 60)}...
                                            </span>
                                        </div>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                removeContextItem(index);
                                            }}
                                            className="ml-2 text-red-600 hover:text-red-800 p-1"
                                            title="Remove context item"
                                        >
                                            <X className="h-3 w-3" />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                    
                    {/* Chat Input */}
                    <div className="border-t p-4">
                        <div className="flex space-x-2">
                            <input
                                ref={chatInputRef}
                                type="text"
                                value={currentMessage}
                                onChange={(e) => setCurrentMessage(e.target.value)}
                                onKeyPress={(e) => e.key === 'Enter' && !isEditMode && sendChatMessage()}
                                placeholder={isEditMode ? "Chat input disabled in edit mode" : "Ask about your case summary..."}
                                disabled={isEditMode}
                                className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm disabled:bg-gray-100 disabled:text-gray-500"
                            />
                            <button
                                onClick={sendChatMessage}
                                disabled={isEditMode}
                                className="px-3 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
                            >
                                <Send className="h-4 w-4" />
                            </button>
                        </div>
                    </div>
                </div>
                
                {/* Right Pane - Documents */}
                <div className="w-1/3 bg-white flex flex-col">
                    <div className="border-b p-4">
                        <h2 className="text-lg font-semibold">Case Documents</h2>
                    </div>
                    
                    <div className="flex-1 p-4">
                        {documents.length > 0 ? (
                            <select
                                value={selectedDocument}
                                onChange={(e) => setSelectedDocument(e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 mb-4"
                            >
                                {documents.map((doc) => (
                                    <option key={doc.id} value={doc.id}>
                                        {doc.name} ({doc.type})
                                    </option>
                                ))}
                            </select>
                        ) : (
                            <div className="text-sm text-gray-500 mb-4">
                                {isLoadingDocuments ? 'Loading documents...' : 'No documents loaded'}
                            </div>
                        )}
                        
                <div 
                    ref={documentRef}
                    className="relative bg-gray-50 p-4 rounded-md overflow-y-auto pb-4 cursor-text" 
                    style={{ height: 'calc(100vh - 250px)' }}
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

            {/* Tab Tooltip */}
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

            {/* Suggestion Hover Popup or Persistent Popup */}
            {(hoveredSuggestion || persistentSuggestionPopup) && (
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
                            {(persistentSuggestionPopup || hoveredSuggestion).comment}
                        </div>
                    </div>
                    
                    <div className="mb-3 text-xs">
                        <div className="line-through text-red-600">
                            {(persistentSuggestionPopup || hoveredSuggestion).originalText}
                        </div>
                        <div className="text-green-600">
                            → {(persistentSuggestionPopup || hoveredSuggestion).suggestedText}
                        </div>
                    </div>
                    
                    <div className="flex space-x-2">
                        <button
                            onClick={() => {
                                applySuggestion(persistentSuggestionPopup || hoveredSuggestion);
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
                                rejectSuggestion(persistentSuggestionPopup || hoveredSuggestion);
                                setPersistentSuggestionPopup(null);
                                setHighlightedContext(null);
                            }}
                            className="flex items-center px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700"
                        >
                            <X className="h-3 w-3 mr-1" />
                            Reject
                        </button>
                        <button
                            onClick={() => startChatAboutSuggestion(persistentSuggestionPopup || hoveredSuggestion)}
                            className="flex items-center px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
                        >
                            <MessageCircle className="h-3 w-3 mr-1" />
                            Discuss
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default LegalCaseApp;

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { buildChatTitle, calculateTextChange, adjustRangeForChange } from '../../../utils/text';

const useChatStore = ({ summary, documents, highlight }) => {
    const [chatMessages, setChatMessages] = useState([]);
    const [currentMessage, setCurrentMessage] = useState('');
    const [chatContext, setChatContext] = useState([]);
    const [chatContextsById, setChatContextsById] = useState({});
    const [allChats, setAllChats] = useState([]);
    const [currentChatId, setCurrentChatId] = useState(null);
    const [isNewChat, setIsNewChat] = useState(false);
    const chatInputRef = useRef(null);
    const previousSummaryTextRef = useRef(summary.summaryText);

    const persistContextForCurrentChat = useCallback(() => {
        if (!currentChatId) {
            return;
        }
        const currentContext = chatContextsById[currentChatId] ?? chatContext;
        setChatContextsById((prev) => ({ ...prev, [currentChatId]: currentContext }));
        setAllChats((prev) => prev.map((chat) =>
            chat.id === currentChatId ? { ...chat, context: currentContext } : chat
        ));
    }, [chatContext, chatContextsById, currentChatId]);

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
    }, [chatContext, chatContextsById, currentChatId]);

    const removeSuggestionContext = useCallback((suggestionId) => {
        const filterFn = (item) => !(item.type === 'suggestion' && item.suggestionId === suggestionId);
        setChatContext((prev) => prev.filter(filterFn));
        setChatContextsById((prev) => {
            let changed = false;
            const entries = Object.entries(prev).map(([chatId, items]) => {
                const filtered = items.filter(filterFn);
                if (filtered.length !== items.length) {
                    changed = true;
                }
                return [chatId, filtered];
            });
            if (!changed) {
                return prev;
            }
            return Object.fromEntries(entries);
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

    const isSelectionInContext = useCallback(({ type, range, documentId }) => {
        const activeContext = currentChatId ? (chatContextsById[currentChatId] ?? chatContext) : chatContext;
        return activeContext.some((item) => {
            if (item.type !== type) {
                return false;
            }
            if (type === 'document-selection' && item.documentId !== documentId) {
                return false;
            }
            if (!item.range || !range) {
                return false;
            }
            return item.range.start === range.start && item.range.end === range.end;
        });
    }, [chatContext, chatContextsById, currentChatId]);

    const saveCurrentChat = useCallback((messages) => {
        const chatId = Date.now();
        const title = (() => {
            const userMessages = messages.filter((message) => message.type === 'user');
            if (userMessages.length > 0) {
                return buildChatTitle(userMessages[0].content);
            }
            return `Chat ${new Date().toLocaleDateString()}`;
        })();
        const newChat = {
            id: chatId,
            title,
            messages,
            context: chatContext,
            createdAt: new Date()
        };
        setAllChats((prev) => [newChat, ...prev]);
        setChatContextsById((prev) => ({ ...prev, [chatId]: chatContext }));
        setCurrentChatId(chatId);
        setIsNewChat(false);
    }, [chatContext]);

    const updateExistingChat = useCallback((messages) => {
        if (!currentChatId) {
            return;
        }
        const currentContext = chatContextsById[currentChatId] ?? chatContext;
        setAllChats((prev) => prev.map((chat) =>
            chat.id === currentChatId
                ? { ...chat, messages, context: currentContext }
                : chat
        ));
        setChatContextsById((prev) => ({ ...prev, [currentChatId]: currentContext }));
    }, [chatContext, chatContextsById, currentChatId]);

    const startChatAboutSuggestion = useCallback((suggestion) => {
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
                context: [],
                createdAt: new Date()
            };

            return [newChat, ...persistedChats.filter((chat) => chat.id !== newChatId)];
        });

        setChatMessages(newMessages);
        setChatContextsById((prev) => ({ ...prev, [newChatId]: [] }));
        setChatContext([]);
        setCurrentChatId(newChatId);
        setIsNewChat(false);
    }, [chatContext, chatContextsById, chatMessages, currentChatId, isNewChat]);

    const sendChatMessage = useCallback(() => {
        if (!currentMessage.trim()) {
            return;
        }
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

        if (isNewChat && chatMessages.length === 0) {
            saveCurrentChat(newMessages);
        } else if (currentChatId) {
            updateExistingChat(newMessages);
        } else if (!currentChatId) {
            saveCurrentChat(newMessages);
        }
    }, [chatMessages, currentChatId, currentMessage, isNewChat, saveCurrentChat, updateExistingChat]);

    const createNewChat = useCallback(() => {
        if (chatMessages.length > 0 && isNewChat) {
            saveCurrentChat(chatMessages);
        }
        if (currentChatId) {
            persistContextForCurrentChat();
        }
        setChatMessages([]);
        setChatContext([]);
        setCurrentChatId(null);
        setIsNewChat(true);
    }, [chatMessages, currentChatId, isNewChat, persistContextForCurrentChat, saveCurrentChat]);

    const selectChat = useCallback((chatId) => {
        if (chatId === currentChatId) {
            return;
        }
        if (isNewChat && chatMessages.length === 0) {
            // nothing to save
        } else if (isNewChat && chatMessages.length > 0) {
            saveCurrentChat(chatMessages);
        } else if (currentChatId && chatMessages.length > 0) {
            updateExistingChat(chatMessages);
        } else if (currentChatId) {
            persistContextForCurrentChat();
        }

        const chat = allChats.find((entry) => entry.id === chatId);
        if (chat) {
            const storedContext = chatContextsById[chat.id] ?? (chat.context || []);
            setChatContextsById((prev) => ({ ...prev, [chat.id]: storedContext }));
            setChatMessages(chat.messages);
            setChatContext(storedContext);
            setCurrentChatId(chat.id);
            setIsNewChat(false);
        }
    }, [allChats, chatContextsById, chatMessages, currentChatId, isNewChat, persistContextForCurrentChat, saveCurrentChat, updateExistingChat]);

    const deleteCurrentChat = useCallback(() => {
        if (currentChatId) {
            setAllChats((prev) => prev.filter((chat) => chat.id !== currentChatId));
            setChatContextsById((prev) => {
                const { [currentChatId]: _removed, ...rest } = prev;
                return rest;
            });
        }
        setChatMessages([]);
        setChatContext([]);
        setCurrentChatId(null);
        setIsNewChat(true);
    }, [currentChatId]);

    const removeContextItem = useCallback((indexToRemove) => {
        highlight.clearActiveHighlight();
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
    }, [chatContext, chatContextsById, currentChatId, highlight]);

    useEffect(() => {
        const previousText = previousSummaryTextRef.current;
        if (previousText === summary.summaryText) {
            return;
        }
        const change = calculateTextChange(previousText || '', summary.summaryText || '');
        previousSummaryTextRef.current = summary.summaryText;
        if (!change) {
            return;
        }

        const updateContext = (contextArray) => {
            let didUpdate = false;
            const updatedContext = contextArray.map((item) => {
                if (item.type !== 'selection' || !item.range) {
                    return item;
                }
                const adjustedRange = adjustRangeForChange(item.range, change, summary.summaryText.length);
                const newContent = summary.summaryText.slice(adjustedRange.start, adjustedRange.end);
                if (
                    adjustedRange.start === item.range.start &&
                    adjustedRange.end === item.range.end &&
                    newContent === item.content
                ) {
                    return item;
                }
                didUpdate = true;
                return { ...item, range: adjustedRange, content: newContent };
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
    }, [summary.summaryText]);

    useEffect(() => {
        highlight.registerChatHelpers({
            isSelectionInContext,
            addContextEntry: addContextToCurrentChat,
            removeSuggestionContext,
            startChatAboutSuggestion
        });
    }, [addContextToCurrentChat, highlight, isSelectionInContext, removeSuggestionContext, startChatAboutSuggestion]);

    const value = useMemo(() => ({
        chatMessages,
        setChatMessages,
        currentMessage,
        setCurrentMessage,
        chatContext,
        chatContextsById,
        allChats,
        currentChatId,
        isNewChat,
        chatInputRef,
        sendChatMessage,
        createNewChat,
        deleteCurrentChat,
        selectChat,
        removeContextItem,
        persistContextForCurrentChat
    }), [
        allChats,
        chatContext,
        chatContextsById,
        chatMessages,
        createNewChat,
        currentChatId,
        currentMessage,
        deleteCurrentChat,
        isNewChat,
        persistContextForCurrentChat,
        removeContextItem,
        selectChat,
        sendChatMessage,
        setCurrentMessage
    ]);

    return value;
};

export default useChatStore;

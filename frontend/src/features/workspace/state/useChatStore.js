import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createChatSession, getChatSession, sendChatMessage as sendChatMessageApi } from '../../../services/apiClient';
import { SUMMARY_DOCUMENT_ID } from '../constants';

const mapMessagesToUi = (messages = []) =>
    messages.map((message) => ({
        id: message.id,
        type: message.role === 'user' ? 'user' : 'ai',
        content: message.content
    }));

const toDocumentId = (value) => {
    if (value == null) {
        return null;
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
        return value;
    }
    if (typeof value === 'string') {
        const trimmed = value.trim();
        if (!trimmed) {
            return null;
        }
        const lowered = trimmed.toLowerCase();
        if (lowered === 'summary') {
            return SUMMARY_DOCUMENT_ID;
        }
        if (lowered.startsWith('document ')) {
            const parsed = Number.parseInt(trimmed.slice(9).trim(), 10);
            return Number.isNaN(parsed) ? null : parsed;
        }
        const parsed = Number.parseInt(trimmed, 10);
        return Number.isNaN(parsed) ? null : parsed;
    }
    return null;
};

const buildContextPayload = (contextItems = []) =>
    contextItems.map((item) => ({
        type: item.type,
        document_id: toDocumentId(item.documentId),
        highlight_text: item.content || item.highlight || null,
        summary_snippet: item.summarySnippet || null
    }));

const isRangeEqual = (left, right) => left?.start === right?.start && left?.end === right?.end;

const useChatStore = ({ summary, documents, highlight }) => {
    const currentSummaryText = summary.summaryText;
    const applySummaryUpdate = summary.applyAiSummaryUpdate;
    const [chatMessages, setChatMessages] = useState([]);
    const [currentMessage, setCurrentMessage] = useState('');
    const [chatContext, setChatContext] = useState([]);
    const [allChats, setAllChats] = useState([]);
    const [currentChatId, setCurrentChatId] = useState(null);
    const [isNewChat, setIsNewChat] = useState(true);
    const [isSending, setIsSending] = useState(false);
    const chatInputRef = useRef(null);

    const ensureSession = useCallback(async () => {
        if (currentChatId) {
            return currentChatId;
        }
        const { session } = await createChatSession();
        setCurrentChatId(session.id);
        setAllChats((previous) => [{ id: session.id, title: session.title, messages: [], context: [] }, ...previous]);
        return session.id;
    }, [currentChatId]);

    const loadSessionHistory = useCallback(async (sessionId) => {
        const response = await getChatSession(sessionId);
        const messages = mapMessagesToUi(response.session?.messages || []);
        setChatMessages(messages);
        setChatContext(response.session?.context || []);
    }, []);

    const createNewChat = useCallback(async () => {
        const { session } = await createChatSession();
        setCurrentChatId(session.id);
        setChatMessages([]);
        setChatContext([]);
        setIsNewChat(true);
        setAllChats((previous) => [{ id: session.id, title: session.title, messages: [], context: [] }, ...previous]);
    }, []);

    const selectChat = useCallback(async (chatId) => {
        if (!chatId) {
            await createNewChat();
            return;
        }
        setCurrentChatId(chatId);
        setIsNewChat(false);
        const existing = allChats.find((chat) => chat.id === chatId);
        if (existing?.messages?.length) {
            setChatMessages(existing.messages);
            setChatContext(existing.context || []);
        } else {
            await loadSessionHistory(chatId);
        }
    }, [allChats, createNewChat, loadSessionHistory]);

    const deleteCurrentChat = useCallback(() => {
        if (!currentChatId) {
            return;
        }
        setAllChats((previous) => previous.filter((chat) => chat.id !== currentChatId));
        setCurrentChatId(null);
        setChatMessages([]);
        setChatContext([]);
        setIsNewChat(true);
    }, [currentChatId]);

    const addContextEntry = useCallback((entry) => {
        if (!entry) {
            return;
        }
        const normalizedEntry =
            entry.type === 'document-selection'
                ? { ...entry, documentId: toDocumentId(entry.documentId) }
                : entry;
        setChatContext((previous) => [...previous, normalizedEntry]);
    }, []);

    const documentLabels = useMemo(() => {
        const mapping = {};
        (documents.documents || []).forEach((doc) => {
            mapping[doc.id] = doc.title || doc.name || doc.id;
        });
        mapping[SUMMARY_DOCUMENT_ID] = 'Summary';
        return mapping;
    }, [documents.documents]);

    const addChecklistContext = useCallback(({ itemName, value, source, evidence }) => {
        const trimmedValue = value?.trim();
        if (!trimmedValue) {
            return;
        }

        const label = (itemName || 'Checklist Item').replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
        const evidenceLines = (evidence || [])
            .map((entry) => {
                const targetId = toDocumentId(entry.documentId ?? entry.document_id);
                const baseLabel = targetId === SUMMARY_DOCUMENT_ID
                    ? 'Summary'
                    : documentLabels[targetId] || (targetId != null ? `Document ${targetId}` : 'Document');
                const docIdLabel = targetId != null && targetId !== SUMMARY_DOCUMENT_ID ? ` (ID ${targetId})` : '';
                const rawStart = entry.startOffset ?? entry.start_offset ?? null;
                const rawEnd = entry.endOffset ?? entry.end_offset ?? null;
                const startOffset =
                    typeof rawStart === 'number'
                        ? rawStart
                        : rawStart != null
                            ? Number.parseInt(rawStart, 10)
                            : null;
                const endOffset =
                    typeof rawEnd === 'number'
                        ? rawEnd
                        : rawEnd != null
                            ? Number.parseInt(rawEnd, 10)
                            : null;
                const sentenceIds = Array.isArray(entry.sentenceIds ?? entry.sentence_ids)
                    ? (entry.sentenceIds ?? entry.sentence_ids)
                    : [];
                const offsetsProvided =
                    startOffset != null && endOffset != null && endOffset > startOffset;
                const offsetLabel = offsetsProvided
                    ? ` [${startOffset}-${endOffset}]`
                    : sentenceIds.length
                        ? ` [sentences ${sentenceIds.join(', ')}]`
                        : '';
                const snippet = typeof entry.text === 'string' && entry.text.trim().length
                    ? entry.text.trim()
                    : sentenceIds.length
                        ? `Sentences ${sentenceIds.join(', ')}`
                        : 'Evidence span';
                return `${baseLabel}${docIdLabel}${offsetLabel}: ${snippet}`;
            })
            .filter(Boolean);

        const payloadLines = [`${label}: ${trimmedValue}`];
        if (evidenceLines.length) {
            payloadLines.push('Evidence:');
            evidenceLines.forEach((line) => payloadLines.push(`- ${line}`));
        }
        if (source) {
            payloadLines.push(`Origin: ${source}`);
        }

        const content = payloadLines.join('\n');
        setChatContext((previous) => {
            if (previous.some((entry) => entry.type === 'checklist' && entry.content === content)) {
                return previous;
            }
            return [
                ...previous,
                {
                    type: 'checklist',
                    content,
                    checklistItem: itemName,
                    source
                }
            ];
        });
    }, [documentLabels, setChatContext]);

    const removeContextItem = useCallback((index) => {
        setChatContext((previous) => previous.filter((_, idx) => idx !== index));
    }, []);

    const isSelectionInContext = useCallback((candidate) => {
        return chatContext.some((entry) => {
            if (candidate.type !== entry.type) {
                return false;
            }
            if (candidate.type === 'selection') {
                return isRangeEqual(candidate.range, entry.range);
            }
            if (candidate.type === 'document-selection') {
                const candidateId = toDocumentId(candidate.documentId);
                const entryId = toDocumentId(entry.documentId);
                return (
                    candidateId != null &&
                    entryId != null &&
                    candidateId === entryId &&
                    isRangeEqual(candidate.range, entry.range)
                );
            }
            if (candidate.type === 'suggestion') {
                return candidate.suggestionId === entry.suggestionId;
            }
            return candidate.content === entry.content;
        });
    }, [chatContext]);

    const removeSuggestionContext = useCallback((suggestionId) => {
        setChatContext((previous) => previous.filter((entry) => entry.suggestionId !== suggestionId));
    }, []);

    const submitMessage = useCallback(async (message, contextOverride) => {
        if (!message.trim()) {
            return;
        }
        setIsSending(true);
        const activeContext = contextOverride ?? chatContext;
        try {
            const sessionId = await ensureSession();
            const payload = {
                message,
                summaryText: currentSummaryText,
                context: buildContextPayload(activeContext),
                documents: (documents.documents || []).map((doc) => ({ id: doc.id, title: doc.title })),
            };
            const response = await sendChatMessageApi(sessionId, payload);
            const summaryUpdate = response.summaryUpdate ?? response.summary_update;
            const summaryPatches = response.summaryPatches ?? response.summary_patches ?? [];
            const newMessages = mapMessagesToUi(response.messages);
            setChatMessages((previous) => [...previous, ...newMessages]);
            setChatContext(activeContext);
            if (summaryUpdate) {
                const nextSummary = typeof summaryUpdate === 'string' ? summaryUpdate.trim() : summaryUpdate;
                applySummaryUpdate(nextSummary, summaryPatches);
            } else if (summaryPatches.length) {
                applySummaryUpdate(currentSummaryText, summaryPatches);
            }
            setAllChats((previous) => {
                const filtered = previous.filter((chat) => chat.id !== sessionId);
                const existing = previous.find((chat) => chat.id === sessionId);
                const updated = {
                    id: sessionId,
                    title: existing?.title || newMessages[0]?.content?.slice(0, 40) || 'Chat',
                    messages: [...(existing?.messages || []), ...newMessages],
                    context: activeContext
                };
                return [updated, ...filtered];
            });
            setIsNewChat(false);
        } catch (error) {
            console.error('Failed to send chat message', error);
        } finally {
            setIsSending(false);
        }
    }, [applySummaryUpdate, chatContext, currentSummaryText, documents.documents, ensureSession]);

    const sendChatMessage = useCallback(async () => {
        if (isSending || !currentMessage.trim()) {
            return;
        }
        await submitMessage(currentMessage);
        setCurrentMessage('');
    }, [currentMessage, isSending, submitMessage]);

    const startChatAboutSuggestion = useCallback(async (suggestion) => {
        if (!suggestion) {
            return;
        }
        const suggestionContext = { type: 'suggestion', content: suggestion.comment, suggestionId: suggestion.id };
        const combinedContext = [suggestionContext, ...chatContext];
        await submitMessage(`Can we discuss this suggestion? "${suggestion.comment}"`, combinedContext);
    }, [chatContext, submitMessage]);

    useEffect(() => {
        highlight.registerChatHelpers({
            isSelectionInContext,
            addContextEntry,
            removeSuggestionContext,
            startChatAboutSuggestion
        });
    }, [addContextEntry, highlight, isSelectionInContext, removeSuggestionContext, startChatAboutSuggestion]);

    const value = useMemo(() => ({
        chatMessages,
        setChatMessages,
        currentMessage,
        setCurrentMessage,
        chatContext,
        allChats,
        currentChatId,
        isNewChat,
        chatInputRef,
        sendChatMessage,
        createNewChat,
        deleteCurrentChat,
        selectChat,
        removeContextItem,
        addChecklistContext,
        isSending
    }), [
        allChats,
        chatContext,
        chatMessages,
        createNewChat,
        currentChatId,
        currentMessage,
        deleteCurrentChat,
        isNewChat,
        removeContextItem,
        selectChat,
        sendChatMessage,
        addChecklistContext,
        isSending
    ]);

    return value;
};

export default useChatStore;

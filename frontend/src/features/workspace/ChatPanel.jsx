import React, { useEffect, useRef } from 'react';
import { Plus, Trash2, Send, X } from 'lucide-react';
import { useChat, useHighlight, useSummary } from './state/WorkspaceProvider';

const renderMessageContent = (content = '', messageId) => {
    if (typeof content !== 'string' || !content.length) {
        return null;
    }

    const lines = content.split(/\r?\n/);
    const elements = [];
    let bulletBuffer = [];
    let segmentIndex = 0;

    const nextKey = (type) => `${messageId || 'message'}-${type}-${segmentIndex++}`;

    const flushBullets = () => {
        if (!bulletBuffer.length) {
            return;
        }
        elements.push(
            <ul key={nextKey('bullets')} className="space-y-1 text-sm">
                {bulletBuffer.map((bullet, index) => (
                    <li key={`${messageId || 'message'}-bullet-${segmentIndex}-${index}`} className="flex items-start gap-2">
                        <span className="select-none leading-6">-</span>
                        <span className="flex-1">{bullet}</span>
                    </li>
                ))}
            </ul>
        );
        bulletBuffer = [];
    };

    lines.forEach((line) => {
        const bulletMatch = line.match(/^\s*-\s+(.*)$/);
        if (bulletMatch) {
            bulletBuffer.push(bulletMatch[1].trim());
            return;
        }

        flushBullets();

        if (!line.trim()) {
            elements.push(<div key={nextKey('break')} className="h-2" aria-hidden="true" />);
            return;
        }

        elements.push(
            <p key={nextKey('paragraph')} className="text-sm leading-relaxed">
                {line.trim()}
            </p>
        );
    });

    flushBullets();

    return elements;
};

const ChatPanel = () => {
    const messagesContainerRef = useRef(null);
    const {
        chatMessages,
        currentMessage,
        setCurrentMessage,
        chatContext,
        sendChatMessage,
        createNewChat,
        deleteCurrentChat,
        allChats,
        currentChatId,
        isNewChat,
        selectChat,
        removeContextItem,
        chatInputRef,
        isSending
    } = useChat();
    const { isEditMode } = useSummary();
    const { handleContextClick } = useHighlight();

    useEffect(() => {
        if (!messagesContainerRef.current) {
            return;
        }
        messagesContainerRef.current.scrollTo({
            top: messagesContainerRef.current.scrollHeight,
            behavior: 'smooth'
        });
    }, [chatMessages]);

    const handleChatSelect = async (event) => {
        const value = event.target.value;
        if (!value) {
            await createNewChat();
            return;
        }
        await selectChat(value);
    };

    const canDeleteChat = Boolean(currentChatId) && !isNewChat;

    return (
        <div className="bg-[var(--color-surface-panel)] flex flex-col h-full min-w-0 border-l border-[var(--color-border)]">
            <div className="border-b border-[var(--color-border)] px-4 py-4">
                <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">AI Legal Assistant</h2>
            </div>

            <div className="px-4 py-3 flex items-center space-x-2 border-b border-[var(--color-border)]">
                <select
                    value={currentChatId || ''}
                    onChange={handleChatSelect}
                    className="flex-1 px-3 py-2 border border-[var(--color-input-border)] rounded-md text-sm bg-[var(--color-input-bg)] text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                >
                    <option value="">New Conversation</option>
                    {allChats.map((chat) => (
                        <option key={chat.id} value={chat.id}>
                            {chat.title}
                        </option>
                    ))}
                </select>
                <button
                    onClick={createNewChat}
                    className="p-2 text-[var(--color-accent)] hover:text-[var(--color-accent-hover)]"
                    title="New Chat"
                >
                    <Plus className="h-4 w-4" />
                </button>
                <button
                    onClick={deleteCurrentChat}
                    disabled={!canDeleteChat}
                    className={`p-2 ${
                        canDeleteChat
                            ? 'text-[var(--color-danger)] hover:text-[var(--color-danger-hover)]'
                            : 'text-[var(--color-input-disabled-text)] cursor-not-allowed'
                    }`}
                    title="Delete Current Chat"
                >
                    <Trash2 className="h-4 w-4" />
                </button>
            </div>

            <div ref={messagesContainerRef} className="flex-1 overflow-y-auto p-4 space-y-4 bg-[var(--color-surface-panel)]">
                {chatMessages.length === 0 ? (
                    <div className="text-sm text-[var(--color-text-muted)] italic">
                        Start a conversation to explore AI-driven guidance for your summary.
                    </div>
                ) : (
                    <div className="space-y-2">
                        {chatMessages.map((message) => (
                            <div
                                key={message.id}
                                className={`p-3 rounded-lg text-sm ${
                                    message.type === 'user'
                                        ? 'bg-[var(--color-chat-user-bg)] text-[var(--color-chat-user-text)] ml-4'
                                        : message.type === 'ai'
                                            ? 'bg-[var(--color-chat-ai-bg)] text-[var(--color-chat-ai-text)] mr-4'
                                            : 'bg-[var(--color-chat-system-bg)] text-[var(--color-chat-system-text)] text-xs'
                                }`}
                            >
                                {renderMessageContent(message.content, message.id)}
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {chatContext.length > 0 && (
                <div className="border-t border-[var(--color-border)] bg-[var(--color-surface-panel-alt)]">
                    <div className="px-3 py-2 text-xs font-medium text-[var(--color-text-secondary)] border-b border-[var(--color-border)]">Context ({chatContext.length}):</div>
                    <div className="max-h-32 overflow-y-auto px-3 py-2 space-y-1">
                        {chatContext.map((item, index) => (
                            <div
                                key={index}
                                className="text-xs bg-[var(--color-surface-panel)] p-2 rounded border border-[var(--color-border)] flex items-start justify-between cursor-pointer hover:bg-[var(--color-surface-panel-alt)]"
                                onClick={() => handleContextClick(item)}
                            >
                                <div className="flex-1">
                                    <span className="font-medium text-[var(--color-accent)]">
                                        {item.type === 'suggestion' ? 'Suggestion: '
                                            : item.type === 'document-selection' ? `${item.source}: `
                                            : `${item.source}: `}
                                    </span>
                                    <span className="text-[var(--color-text-muted)]">
                                        {item.content.substring(0, 60)}...
                                    </span>
                                </div>
                                <button
                                    onClick={(event) => {
                                        event.stopPropagation();
                                        removeContextItem(index);
                                    }}
                                    className="ml-2 text-[var(--color-danger)] hover:text-[var(--color-danger-hover)] p-1"
                                    title="Remove context item"
                                >
                                    <X className="h-3 w-3" />
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <div className="border-t border-[var(--color-border)] p-4 bg-[var(--color-surface-panel)]">
                <div className="flex space-x-2">
                    <textarea
                        ref={chatInputRef}
                        value={currentMessage}
                        onChange={(event) => setCurrentMessage(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === 'Enter' && !event.shiftKey) {
                                event.preventDefault();
                                if (!isEditMode && !isSending) {
                                    sendChatMessage();
                                }
                            }
                        }}
                        placeholder={isEditMode ? 'Chat input disabled in edit mode' : 'Ask about your case summary...'}
                        disabled={isEditMode || isSending}
                        rows={3}
                        className="flex-1 px-3 py-2 border border-[var(--color-input-border)] rounded-md focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] text-sm bg-[var(--color-input-bg)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] disabled:bg-[var(--color-input-disabled-bg)] disabled:text-[var(--color-input-disabled-text)] resize-none"
                    />
                    <button
                        onClick={sendChatMessage}
                        disabled={isEditMode || isSending}
                        className="px-3 py-2 bg-[var(--color-accent)] text-[var(--color-text-inverse)] rounded-md hover:bg-[var(--color-accent-hover)] disabled:bg-[var(--color-surface-muted)] disabled:text-[var(--color-input-disabled-text)] disabled:cursor-not-allowed"
                    >
                        <Send className="h-4 w-4" />
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ChatPanel;

import React, { useEffect, useRef } from 'react';
import { Plus, Trash2, Send, X } from 'lucide-react';
import { useChat, useHighlight, useSummary } from './state/WorkspaceProvider';

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
        chatInputRef
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

    const handleChatSelect = (event) => {
        const value = event.target.value;
        if (!value) {
            createNewChat();
            return;
        }
        selectChat(Number(value));
    };

    const canDeleteChat = Boolean(currentChatId) && !isNewChat;

    return (
        <div className="w-1/3 bg-white flex flex-col">
            <div className="border-b px-4 py-4">
                <h2 className="text-lg font-semibold">AI Legal Assistant</h2>
            </div>

            <div className="px-4 py-3 flex items-center space-x-2">
                <select
                    value={currentChatId || ''}
                    onChange={handleChatSelect}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                    className="p-2 text-blue-600 hover:text-blue-800"
                    title="New Chat"
                >
                    <Plus className="h-4 w-4" />
                </button>
                <button
                    onClick={deleteCurrentChat}
                    disabled={!canDeleteChat}
                    className={`p-2 ${
                        canDeleteChat
                            ? 'text-red-600 hover:text-red-800'
                            : 'text-gray-300 cursor-not-allowed'
                    }`}
                    title="Delete Current Chat"
                >
                    <Trash2 className="h-4 w-4" />
                </button>
            </div>

            <div ref={messagesContainerRef} className="flex-1 overflow-y-auto p-4 space-y-4">
                {chatMessages.length === 0 ? (
                    <div className="text-sm text-gray-500 italic">
                        Start a conversation to explore AI-driven guidance for your summary.
                    </div>
                ) : (
                    <div className="space-y-2">
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

            {chatContext.length > 0 && (
                <div className="border-t bg-gray-50">
                    <div className="px-3 py-2 text-xs font-medium text-gray-700 border-b border-gray-200">Context ({chatContext.length}):</div>
                    <div className="max-h-32 overflow-y-auto px-3 py-2 space-y-1">
                        {chatContext.map((item, index) => (
                            <div
                                key={index}
                                className="text-xs bg-white p-2 rounded border flex items-start justify-between cursor-pointer hover:bg-gray-50"
                                onClick={() => handleContextClick(item)}
                            >
                                <div className="flex-1">
                                    <span className="font-medium text-blue-600">
                                        {item.type === 'suggestion' ? 'Suggestion: '
                                            : item.type === 'document-selection' ? `${item.source}: `
                                            : `${item.source}: `}
                                    </span>
                                    <span className="text-gray-600">
                                        {item.content.substring(0, 60)}...
                                    </span>
                                </div>
                                <button
                                    onClick={(event) => {
                                        event.stopPropagation();
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

            <div className="border-t p-4">
                <div className="flex space-x-2">
                    <input
                        ref={chatInputRef}
                        type="text"
                        value={currentMessage}
                        onChange={(event) => setCurrentMessage(event.target.value)}
                        onKeyPress={(event) => event.key === 'Enter' && !isEditMode && sendChatMessage()}
                        placeholder={isEditMode ? 'Chat input disabled in edit mode' : 'Ask about your case summary...'}
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
    );
};

export default ChatPanel;

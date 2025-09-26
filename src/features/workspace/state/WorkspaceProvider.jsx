import React, { createContext, useContext, useMemo } from 'react';
import useDocumentsStore from './useDocumentsStore';
import useSummaryStore from './useSummaryStore';
import useHighlightStore from './useHighlightStore';
import useChatStore from './useChatStore';

const WorkspaceStateContext = createContext(null);

export const WorkspaceStateProvider = ({ children }) => {
    const documents = useDocumentsStore();
    const summary = useSummaryStore();
    const highlight = useHighlightStore({ summary, documents });
    const chat = useChatStore({ summary, documents, highlight });

    const value = useMemo(() => ({ documents, summary, highlight, chat }), [documents, summary, highlight, chat]);

    return (
        <WorkspaceStateContext.Provider value={value}>
            {children}
        </WorkspaceStateContext.Provider>
    );
};

const useWorkspaceState = () => {
    const context = useContext(WorkspaceStateContext);
    if (!context) {
        throw new Error('useWorkspaceState must be used within a WorkspaceStateProvider');
    }
    return context;
};

export const useDocuments = () => useWorkspaceState().documents;
export const useSummary = () => useWorkspaceState().summary;
export const useHighlight = () => useWorkspaceState().highlight;
export const useChat = () => useWorkspaceState().chat;

export default WorkspaceStateProvider;

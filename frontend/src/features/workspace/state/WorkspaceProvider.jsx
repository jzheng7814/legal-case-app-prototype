import React, { createContext, useContext, useMemo } from 'react';
import useDocumentsStore from './useDocumentsStore';
import useSummaryStore from './useSummaryStore';
import useHighlightStore from './useHighlightStore';
import useChatStore from './useChatStore';
import useChecklistStore from './useChecklistStore';

const WorkspaceStateContext = createContext(null);

export const WorkspaceStateProvider = ({ children, caseId }) => {
    const documents = useDocumentsStore({ caseId });
    const summary = useSummaryStore({ caseId: documents.caseId });
    const highlight = useHighlightStore({ summary, documents });
    const chat = useChatStore({ summary, documents, highlight });
    const checklist = useChecklistStore({ caseId: documents.caseId });

    const value = useMemo(
        () => ({ documents, summary, highlight, chat, checklist }),
        [documents, summary, highlight, chat, checklist]
    );

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

// eslint-disable-next-line react-refresh/only-export-components
export const useDocuments = () => useWorkspaceState().documents;
// eslint-disable-next-line react-refresh/only-export-components
export const useSummary = () => useWorkspaceState().summary;
// eslint-disable-next-line react-refresh/only-export-components
export const useHighlight = () => useWorkspaceState().highlight;
// eslint-disable-next-line react-refresh/only-export-components
export const useChat = () => useWorkspaceState().chat;
// eslint-disable-next-line react-refresh/only-export-components
export const useChecklist = () => useWorkspaceState().checklist;

export default WorkspaceStateProvider;

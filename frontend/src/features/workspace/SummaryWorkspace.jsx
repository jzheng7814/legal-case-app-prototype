import React from 'react';
import WorkspaceStateProvider from './state/WorkspaceProvider';
import SummaryPanel from './components/SummaryPanel';
import ChatPanel from './ChatPanel';
import DocumentsPanel from './DocumentsPanel';
import SuggestionPopup from './components/SuggestionPopup';

const SummaryWorkspaceView = ({ onExit }) => (
    <div className="min-h-screen bg-gray-50">
        <div className="bg-white border-b px-6 py-4">
            <div className="flex items-center justify-between">
                <h1 className="text-xl font-semibold">Case Summary Editor</h1>
                <button
                    onClick={() => onExit?.()}
                    className="text-blue-600 hover:text-blue-800"
                >
                    ← Back to Home
                </button>
            </div>
        </div>

        <div className="flex h-[calc(100vh-73px)] overflow-hidden">
            <SummaryPanel />
            <ChatPanel />
            <DocumentsPanel />
        </div>

        <SuggestionPopup />
    </div>
);

const SummaryWorkspace = ({ onExit, caseId, uploadedDocuments }) => (
    <WorkspaceStateProvider caseId={caseId} uploadedDocuments={uploadedDocuments}>
        <SummaryWorkspaceView onExit={onExit} />
    </WorkspaceStateProvider>
);

export default SummaryWorkspace;

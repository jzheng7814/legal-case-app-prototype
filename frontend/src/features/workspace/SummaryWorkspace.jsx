import React, { useState } from 'react';
import WorkspaceStateProvider from './state/WorkspaceProvider';
import CanvasPage from './components/CanvasPage';
import ChecklistPage from './components/ChecklistPage';
import SuggestionPopup from './components/SuggestionPopup';

const SummaryWorkspaceView = ({ onExit }) => {
    const [activePage, setActivePage] = useState('canvas');

    return (
        <div className="min-h-screen bg-gray-50">
            <div className="bg-white border-b px-6 py-4">
                <div className="flex items-center justify-between flex-wrap gap-4">
                    <div>
                        <h1 className="text-xl font-semibold">Case Workspace</h1>
                        <p className="text-sm text-gray-500">Switch between the summary canvas and checklist curation.</p>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="flex rounded-md border border-gray-200 bg-gray-100 overflow-hidden">
                            {[
                                { id: 'canvas', label: 'Canvas' },
                                { id: 'checklist', label: 'Checklist' }
                            ].map((tab) => (
                                <button
                                    key={tab.id}
                                    type="button"
                                    onClick={() => setActivePage(tab.id)}
                                    className={`px-4 py-1.5 text-sm font-medium transition ${
                                        activePage === tab.id
                                            ? 'bg-white text-blue-600 shadow-sm'
                                            : 'text-gray-500 hover:text-gray-700'
                                    }`}
                                >
                                    {tab.label}
                                </button>
                            ))}
                        </div>
                        <button
                            onClick={() => onExit?.()}
                            className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                        >
                            ← Back to Home
                        </button>
                    </div>
                </div>
            </div>

            <div className="flex h-[calc(100vh-96px)] overflow-hidden bg-gray-100">
                {activePage === 'canvas' ? <CanvasPage isActive /> : <ChecklistPage isActive />}
            </div>

            <SuggestionPopup />
        </div>
    );
};

const SummaryWorkspace = ({ onExit, caseId, uploadedDocuments }) => (
    <WorkspaceStateProvider caseId={caseId} uploadedDocuments={uploadedDocuments}>
        <SummaryWorkspaceView onExit={onExit} />
    </WorkspaceStateProvider>
);

export default SummaryWorkspace;

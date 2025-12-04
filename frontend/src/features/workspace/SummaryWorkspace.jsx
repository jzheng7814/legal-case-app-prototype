import React, { useCallback, useEffect, useRef, useState } from 'react';
import WorkspaceStateProvider from './state/WorkspaceProvider';
import CanvasPage from './components/CanvasPage';
import ChecklistPage from './components/ChecklistPage';
import ThemeToggle from '../../theme/ThemeToggle';

const SummaryWorkspaceView = ({ onExit }) => {
    const [activePage, setActivePage] = useState('canvas');
    const [canvasSplit, setCanvasSplit] = useState(30);
    const [checklistSplit, setChecklistSplit] = useState(30);
    const workspaceRef = useRef(null);
    const dragCleanupRef = useRef(null);

    const clampSplit = useCallback((value) => Math.min(80, Math.max(20, value)), []);

    const startDrag = useCallback((setSplit) => (event) => {
        event.preventDefault();
        const handleMouseMove = (moveEvent) => {
            if (!workspaceRef.current) {
                return;
            }
            const rect = workspaceRef.current.getBoundingClientRect();
            if (!rect.width) {
                return;
            }
            const relativeX = moveEvent.clientX - rect.left;
            const percentage = clampSplit((relativeX / rect.width) * 100);
            setSplit(percentage);
        };
        const handleMouseUp = () => {
            dragCleanupRef.current?.();
        };
        const cleanup = () => {
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
            dragCleanupRef.current = null;
        };

        dragCleanupRef.current?.();
        dragCleanupRef.current = cleanup;
        window.addEventListener('mousemove', handleMouseMove);
        window.addEventListener('mouseup', handleMouseUp);
    }, [clampSplit]);

    useEffect(() => {
        return () => {
            dragCleanupRef.current?.();
        };
    }, []);

    return (
        <div className="min-h-screen bg-[var(--color-surface-app)] text-[var(--color-text-primary)] transition-colors">
            <div className="bg-[var(--color-surface-panel)] border-b border-[var(--color-border)] px-6 py-4 shadow-sm">
                <div className="flex items-center justify-between flex-wrap gap-4">
                    <div>
                        <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">Case Workspace</h1>
                        <p className="text-sm text-[var(--color-text-muted)]">Switch between the summary canvas and checklist curation.</p>
                    </div>
                    <div className="flex items-center gap-3 flex-wrap">
                        <div className="flex rounded-md border border-[var(--color-border)] bg-[var(--color-surface-panel-alt)] overflow-hidden">
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
                                            ? 'bg-[var(--color-surface-panel)] text-[var(--color-accent)] shadow-sm'
                                            : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]'
                                    }`}
                                >
                                    {tab.label}
                                </button>
                            ))}
                        </div>
                        <ThemeToggle />
                        <button
                            onClick={() => onExit?.()}
                            className="text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] text-sm font-medium"
                        >
                            ← Back to Home
                        </button>
                    </div>
                </div>
            </div>

            <div ref={workspaceRef} className="flex h-[calc(100vh-96px)] overflow-hidden bg-[var(--color-surface-panel-alt)]">
                {activePage === 'canvas' ? (
                    <CanvasPage
                        isActive
                        split={canvasSplit}
                        onSplitChange={startDrag(setCanvasSplit)}
                    />
                ) : (
                    <ChecklistPage
                        isActive
                        split={checklistSplit}
                        onSplitChange={startDrag(setChecklistSplit)}
                    />
                )}
            </div>

        </div>
    );
};

const SummaryWorkspace = ({ onExit, caseId, uploadedDocuments }) => (
    <WorkspaceStateProvider caseId={caseId} uploadedDocuments={uploadedDocuments}>
        <SummaryWorkspaceView onExit={onExit} />
    </WorkspaceStateProvider>
);

export default SummaryWorkspace;

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';
import WorkspaceStateProvider from './state/WorkspaceProvider';
import ChecklistPanel from './components/ChecklistPage';
import SummaryPanel from './components/SummaryPanel';
import DocumentsPanel from './DocumentsPanel';
import ChatPanel from './ChatPanel';
import DividerHandle from './components/DividerHandle';
import ThemeToggle from '../../theme/ThemeToggle';
import { useHighlight } from './state/WorkspaceProvider';

const PANE_ORDER = ['checklist', 'summary', 'documents'];
const MIN_SPLIT = 15;
const MAX_SPLIT = 85;

const SummaryWorkspaceView = ({ onExit }) => {
    const [visiblePanes, setVisiblePanes] = useState({
        checklist: true,
        summary: false,
        documents: true
    });
    const [pairSplits, setPairSplits] = useState({
        'checklist-summary': 40,
        'summary-documents': 55,
        'checklist-documents': 45
    });
    const [threeSplit, setThreeSplit] = useState({ first: 30, second: 65 });
    const [isChatOpen, setIsChatOpen] = useState(false);
    const workspaceRef = useRef(null);
    const dragCleanupRef = useRef(null);
    const { setInteractionMode } = useHighlight();

    const activePanes = useMemo(
        () => PANE_ORDER.filter((pane) => visiblePanes[pane]),
        [visiblePanes]
    );

    useEffect(() => {
        setInteractionMode(visiblePanes.summary ? 'canvas' : 'checklist');
    }, [setInteractionMode, visiblePanes.summary]);

    useEffect(() => () => dragCleanupRef.current?.(), []);

    const clampSplit = useCallback((value) => Math.min(MAX_SPLIT, Math.max(MIN_SPLIT, value)), []);

    const togglePane = useCallback((pane) => {
        setVisiblePanes((current) => {
            const next = { ...current, [pane]: !current[pane] };
            if (!Object.values(next).some(Boolean)) {
                return current;
            }
            return next;
        });
    }, []);

    const startDragPair = useCallback((pairKey) => (event) => {
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
            setPairSplits((current) => ({
                ...current,
                [pairKey]: percentage
            }));
        };
        const handleMouseUp = () => dragCleanupRef.current?.();
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

    const startDragThree = useCallback((positionKey) => (event) => {
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
            setThreeSplit((current) => {
                if (positionKey === 'first') {
                    const maxAllowed = Math.max(MIN_SPLIT, current.second - MIN_SPLIT);
                    return { ...current, first: Math.min(percentage, maxAllowed) };
                }
                const minAllowed = Math.min(MAX_SPLIT, current.first + MIN_SPLIT);
                return { ...current, second: Math.max(percentage, minAllowed) };
            });
        };
        const handleMouseUp = () => dragCleanupRef.current?.();
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

    const renderPane = (pane) => {
        if (pane === 'checklist') {
            return <ChecklistPanel isActive={visiblePanes.checklist} />;
        }
        if (pane === 'summary') {
            return <SummaryPanel />;
        }
        return <DocumentsPanel />;
    };

    const renderLayout = () => {
        if (activePanes.length === 1) {
            return (
                <div className="flex flex-1 min-w-0 min-h-0">
                    <div className="flex-1 min-w-0 min-h-0 flex flex-col">{renderPane(activePanes[0])}</div>
                </div>
            );
        }

        if (activePanes.length === 2) {
            const pairKey = `${activePanes[0]}-${activePanes[1]}`;
            const split = pairSplits[pairKey] ?? 50;
            return (
                <div className="flex flex-1 min-w-0 min-h-0">
                    <div
                        className="min-w-0 min-h-0 flex flex-col"
                        style={{ flexBasis: `${split}%` }}
                    >
                        {renderPane(activePanes[0])}
                    </div>
                    <DividerHandle onMouseDown={startDragPair(pairKey)} />
                    <div
                        className="min-w-0 min-h-0 flex flex-col"
                        style={{ flexBasis: `${100 - split}%` }}
                    >
                        {renderPane(activePanes[1])}
                    </div>
                </div>
            );
        }

        const middleWidth = Math.max(MIN_SPLIT, threeSplit.second - threeSplit.first);

        return (
            <div className="flex flex-1 min-w-0 min-h-0">
                <div
                    className="min-w-0 min-h-0 flex flex-col"
                    style={{ flexBasis: `${threeSplit.first}%` }}
                >
                    {renderPane(activePanes[0])}
                </div>
                <DividerHandle onMouseDown={startDragThree('first')} />
                <div
                    className="min-w-0 min-h-0 flex flex-col"
                    style={{ flexBasis: `${middleWidth}%` }}
                >
                    {renderPane(activePanes[1])}
                </div>
                <DividerHandle onMouseDown={startDragThree('second')} />
                <div
                    className="min-w-0 min-h-0 flex flex-col"
                    style={{ flexBasis: `${100 - threeSplit.second}%` }}
                >
                    {renderPane(activePanes[2])}
                </div>
            </div>
        );
    };

    return (
        <div className="min-h-screen bg-[var(--color-surface-app)] text-[var(--color-text-primary)] transition-colors">
            <div className="bg-[var(--color-surface-panel)] border-b border-[var(--color-border)] px-6 py-4 shadow-sm">
                <div className="flex items-center justify-between flex-wrap gap-4">
                    <div>
                        <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">Case Workspace</h1>
                        <p className="text-sm text-[var(--color-text-muted)]">Toggle the views you need; checklist drives summary generation.</p>
                    </div>
                    <div className="flex items-center gap-3 flex-wrap">
                        <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
                            View:
                            <div className="flex rounded-md border border-[var(--color-border)] bg-[var(--color-surface-panel-alt)] overflow-hidden">
                                {PANE_ORDER.map((pane) => (
                                    <button
                                        key={pane}
                                        type="button"
                                        onClick={() => togglePane(pane)}
                                        className={`px-3 py-1.5 text-sm font-medium transition ${
                                            visiblePanes[pane]
                                                ? 'bg-[var(--color-surface-panel)] text-[var(--color-accent)] shadow-sm'
                                                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]'
                                        }`}
                                    >
                                        {pane === 'checklist' ? 'Checklist' : pane === 'summary' ? 'Summary' : 'Documents'}
                                    </button>
                                ))}
                            </div>
                        </div>
                        <button
                            type="button"
                            onClick={() => setIsChatOpen(true)}
                            className="px-3 py-1.5 text-sm font-medium rounded border border-[var(--color-border)] bg-[var(--color-surface-panel-alt)] text-[var(--color-text-primary)] hover:border-[var(--color-border-strong)]"
                        >
                            Ask AI
                        </button>
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

            <div ref={workspaceRef} className="flex h-[calc(100vh-96px)] min-h-0 overflow-hidden bg-[var(--color-surface-panel-alt)]">
                {renderLayout()}
            </div>

            {isChatOpen && (
                <div className="fixed inset-0 z-50 flex">
                    <div
                        className="flex-1 bg-[var(--color-overlay-scrim)]"
                        onClick={() => setIsChatOpen(false)}
                        aria-hidden="true"
                    />
                    <div className="relative w-full max-w-[420px] h-full bg-[var(--color-surface-panel)] border-l border-[var(--color-border)] shadow-2xl">
                        <button
                            type="button"
                            onClick={() => setIsChatOpen(false)}
                            className="absolute top-3 right-3 p-2 rounded hover:bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]"
                            aria-label="Close chat"
                        >
                            <X className="h-4 w-4" />
                        </button>
                        <div className="h-full pt-10">
                            <ChatPanel />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

const SummaryWorkspace = ({ onExit, caseId, uploadedDocuments }) => (
    <WorkspaceStateProvider caseId={caseId} uploadedDocuments={uploadedDocuments}>
        <SummaryWorkspaceView onExit={onExit} />
    </WorkspaceStateProvider>
);

export default SummaryWorkspace;

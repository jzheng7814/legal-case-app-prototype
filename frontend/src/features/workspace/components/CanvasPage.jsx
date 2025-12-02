import React, { useEffect } from 'react';
import ChatPanel from '../ChatPanel';
import SummaryPanel from './SummaryPanel';
import { useHighlight } from '../state/WorkspaceProvider';

const CanvasPage = ({ isActive }) => {
    const { setInteractionMode } = useHighlight();

    useEffect(() => {
        if (isActive) {
            setInteractionMode('canvas');
        }
    }, [isActive, setInteractionMode]);

    return (
        <div className="flex flex-1 overflow-hidden w-full bg-[var(--color-surface-panel-alt)]">
            <div className="h-full border-r border-[var(--color-border)] bg-[var(--color-surface-panel)] flex flex-col basis-1/4 grow min-w-0">
                <ChatPanel />
            </div>
            <div className="relative h-full bg-[var(--color-surface-panel)] flex flex-col basis-3/4 grow min-w-0">
                <SummaryPanel />
            </div>
        </div>
    );
};

export default CanvasPage;

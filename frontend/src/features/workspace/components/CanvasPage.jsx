import React, { useEffect } from 'react';
import ChatPanel from '../ChatPanel';
import SummaryPanel from './SummaryPanel';
import { useHighlight } from '../state/WorkspaceProvider';
import DividerHandle from './DividerHandle';

const CanvasPage = ({ isActive, split = 30, onSplitChange }) => {
    const { setInteractionMode } = useHighlight();

    useEffect(() => {
        if (isActive) {
            setInteractionMode('canvas');
        }
    }, [isActive, setInteractionMode]);

    return (
        <div className="flex flex-1 overflow-hidden w-full bg-[var(--color-surface-panel-alt)] min-w-0">
            <div
                className="h-full border-r border-[var(--color-border)] bg-[var(--color-surface-panel)] flex flex-col min-w-0"
                style={{ flexBasis: `${split}%` }}
            >
                <ChatPanel />
            </div>
            <DividerHandle onMouseDown={onSplitChange} />
            <div
                className="relative h-full bg-[var(--color-surface-panel)] flex flex-col flex-1 min-w-0"
                style={{ flexBasis: `${100 - split}%` }}
            >
                <SummaryPanel />
            </div>
        </div>
    );
};

export default CanvasPage;

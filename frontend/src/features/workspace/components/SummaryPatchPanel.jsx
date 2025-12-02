import React, { useMemo } from 'react';
import { AlertTriangle, MapPin, RotateCcw, Undo2 } from 'lucide-react';
import { useSummary } from '../state/WorkspaceProvider';

const formatPatchDescription = (patch) => {
    const removed = patch.deleteCount > 0 ? patch.deletedText || '' : '';
    const added = patch.insertText || '';
    if (removed && added) {
        return `Replaced “${removed.trim()}” with “${added.trim()}”.`;
    }
    if (removed) {
        return `Removed “${removed.trim()}”.`;
    }
    if (added) {
        return `Inserted “${added.trim()}”.`;
    }
    return 'Minor whitespace adjustment.';
};

const SummaryPatchPanel = ({ panelRef }) => {
    const {
        patchAction,
        activePatchId,
        previewPatch,
        clearPatchPreview,
        revertPatch,
        revertAllPatches,
        dismissPatchAction
    } = useSummary();

    const entries = useMemo(() => {
        if (!patchAction?.patches?.length) {
            return [];
        }
        return patchAction.patches.map((patch, index) => ({
            ...patch,
            ordinal: index + 1,
            description: formatPatchDescription(patch)
        }));
    }, [patchAction]);

    if (!patchAction || entries.length === 0) {
        return null;
    }

    const disableActions = patchAction.isStale;

    const handleJump = (patch) => {
        if (disableActions || patch.status !== 'applied') {
            return;
        }
        if (activePatchId === patch.id) {
            clearPatchPreview();
        } else {
            previewPatch(patch.id);
        }
    };

    const handleRevert = (patch) => {
        if (disableActions || patch.status !== 'applied') {
            return;
        }
        revertPatch(patch.id);
    };

    return (
        <div ref={panelRef} className="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-info-soft)] px-3 py-2 text-sm">
            <div className="flex items-center justify-between">
                <div>
                    <p className="font-semibold text-[var(--color-text-primary)]">Summary changes</p>
                    <p className="text-xs text-[var(--color-text-secondary)]">Review what the assistant modified before editing again.</p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        type="button"
                        onClick={revertAllPatches}
                        disabled={disableActions || entries.every((patch) => patch.status !== 'applied')}
                        className={`flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold ${
                            disableActions || entries.every((patch) => patch.status !== 'applied')
                                ? 'text-[var(--color-text-muted)] cursor-not-allowed'
                                : 'text-[var(--color-accent)] hover:text-[var(--color-accent-hover)]'
                        }`}
                    >
                        <RotateCcw className="h-3.5 w-3.5" />
                        Revert all
                    </button>
                    <button
                        type="button"
                        onClick={dismissPatchAction}
                        className="text-xs font-semibold text-[var(--color-accent)] hover:text-[var(--color-accent-hover)]"
                    >
                        Dismiss
                    </button>
                </div>
            </div>

            {patchAction.isStale && (
                <div className="mt-2 flex items-center gap-1 text-xs text-[var(--color-text-warning)]">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    A newer edit changed the summary. Jump and revert controls are disabled, but the history is preserved below.
                </div>
            )}

            <div className="mt-3 max-h-64 overflow-y-auto pr-1">
                <ul className="space-y-2">
                    {entries.map((patch) => {
                        const isActive = patch.id === activePatchId;
                        const canInteract = patch.status === 'applied' && !disableActions;
                        return (
                            <li
                                key={patch.id}
                                className={`rounded border px-3 py-2 ${
                                    isActive ? 'border-[var(--color-accent)] bg-[var(--color-surface-panel)]' : 'border-[var(--color-border)] bg-[var(--color-surface-panel)]'
                                }`}
                            >
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-xs font-semibold text-[var(--color-text-primary)]">Change {patch.ordinal}</p>
                                        <p className="text-xs text-[var(--color-text-secondary)]">{patch.description}</p>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <button
                                            type="button"
                                            onClick={() => handleJump(patch)}
                                            disabled={!canInteract}
                                            className={`flex items-center gap-1 rounded px-2 py-1 text-xs ${
                                                canInteract ? 'text-[var(--color-accent)] hover:text-[var(--color-accent-hover)]' : 'text-[var(--color-text-muted)]'
                                            }`}
                                        >
                                            <MapPin className="h-3.5 w-3.5" />
                                            {isActive ? 'Hide' : 'Jump'}
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => handleRevert(patch)}
                                            disabled={!canInteract}
                                            className={`flex items-center gap-1 rounded px-2 py-1 text-xs ${
                                                canInteract ? 'text-[var(--color-accent)] hover:text-[var(--color-accent-hover)]' : 'text-[var(--color-text-muted)]'
                                            }`}
                                        >
                                            <Undo2 className="h-3.5 w-3.5" />
                                            Revert
                                        </button>
                                    </div>
                                </div>
                                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                                    {patch.deleteCount > 0 && (
                                        <span className="rounded bg-[var(--color-danger-soft)] px-2 py-0.5 text-[var(--color-danger)] line-through">
                                            {patch.deletedText || '(whitespace)'}
                                        </span>
                                    )}
                                    {patch.insertText && (
                                        <span className="rounded bg-[var(--color-success-soft)] px-2 py-0.5 text-[var(--color-text-success)]">
                                            {patch.insertText}
                                        </span>
                                    )}
                                    {patch.status === 'reverted' && (
                                        <span className="rounded bg-[var(--color-surface-muted)] px-2 py-0.5 text-[var(--color-text-secondary)]">Reverted</span>
                                    )}
                                </div>
                            </li>
                        );
                    })}
                </ul>
            </div>
        </div>
    );
};

export default SummaryPatchPanel;

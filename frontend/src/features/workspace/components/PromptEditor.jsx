import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Upload, Download, RotateCcw } from 'lucide-react';
import { usePrompt } from '../state/WorkspaceProvider';

const EVIDENCE_BLOCK_TOKEN = '{evidence_block}';

const PromptEditor = ({ onBack }) => {
    const { prompt, defaultPrompt, isLoading, error, commitPrompt } = usePrompt();
    const [draftPrompt, setDraftPrompt] = useState(prompt || '');
    const [hasLocalEdits, setHasLocalEdits] = useState(false);
    const [actionError, setActionError] = useState(null);
    const [showMissingWarning, setShowMissingWarning] = useState(false);
    const fileInputRef = useRef(null);

    useEffect(() => {
        if (hasLocalEdits) {
            return;
        }
        setDraftPrompt(prompt || '');
    }, [hasLocalEdits, prompt]);

    const hasEvidenceBlock = draftPrompt.includes(EVIDENCE_BLOCK_TOKEN);

    const handleBack = useCallback(() => {
        setActionError(null);
        if (!hasEvidenceBlock) {
            setShowMissingWarning(true);
            return;
        }
        commitPrompt(draftPrompt);
        setHasLocalEdits(false);
        onBack?.();
    }, [commitPrompt, draftPrompt, hasEvidenceBlock, onBack]);

    const handleConfirmBack = useCallback(() => {
        setShowMissingWarning(false);
        commitPrompt(draftPrompt);
        setHasLocalEdits(false);
        onBack?.();
    }, [commitPrompt, draftPrompt, onBack]);

    const handleCancelWarning = useCallback(() => {
        setShowMissingWarning(false);
    }, []);

    const handleReset = useCallback(() => {
        if (!defaultPrompt) {
            setActionError('Default prompt is not available yet.');
            return;
        }
        setDraftPrompt(defaultPrompt);
        setHasLocalEdits(true);
        setActionError(null);
    }, [defaultPrompt]);

    const handleExport = useCallback(() => {
        setActionError(null);
        try {
            const payload = {
                prompt: draftPrompt,
                exported_at: new Date().toISOString()
            };
            const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = 'summary-prompt.json';
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        } catch (err) {
            setActionError(err.message || 'Failed to export prompt.');
        }
    }, [draftPrompt]);

    const handleImportClick = useCallback(() => {
        setActionError(null);
        fileInputRef.current?.click();
    }, []);

    const handleImportFile = useCallback(async (event) => {
        const file = event.target.files?.[0];
        if (!file) {
            return;
        }
        setActionError(null);
        try {
            const text = await file.text();
            const payload = JSON.parse(text);
            if (!payload || typeof payload !== 'object') {
                throw new Error('Prompt import must be a JSON object.');
            }
            if (typeof payload.prompt !== 'string') {
                throw new Error('Prompt import is missing a prompt string.');
            }
            if (typeof payload.exported_at !== 'string') {
                throw new Error('Prompt import is missing exported_at metadata.');
            }
            setDraftPrompt(payload.prompt);
            setHasLocalEdits(true);
        } catch (err) {
            setActionError(err.message || 'Failed to import prompt.');
        } finally {
            event.target.value = '';
        }
    }, []);

    return (
        <div className="h-screen overflow-hidden bg-[var(--color-surface-app)] text-[var(--color-text-primary)] flex flex-col">
            <div className="bg-[var(--color-surface-panel)] border-b border-[var(--color-border)] px-6 py-4 shadow-sm">
                <div className="flex items-center justify-between flex-wrap gap-4">
                    <div>
                        <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">Summary Prompt</h1>
                        <p className="text-sm text-[var(--color-text-muted)]">
                            Edit the full prompt template. Include {EVIDENCE_BLOCK_TOKEN} to inject evidence.
                        </p>
                    </div>
                    <div className="flex items-center gap-3 flex-wrap">
                        <button
                            type="button"
                            onClick={handleImportClick}
                            className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded border border-[var(--color-border)] bg-[var(--color-surface-panel-alt)] text-[var(--color-text-primary)] hover:border-[var(--color-border-strong)]"
                        >
                            <Upload className="h-4 w-4" />
                            Import
                        </button>
                        <button
                            type="button"
                            onClick={handleExport}
                            className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded border border-[var(--color-border)] bg-[var(--color-surface-panel-alt)] text-[var(--color-text-primary)] hover:border-[var(--color-border-strong)]"
                        >
                            <Download className="h-4 w-4" />
                            Export
                        </button>
                        <button
                            type="button"
                            onClick={handleReset}
                            className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded border border-[var(--color-border)] bg-[var(--color-surface-panel-alt)] text-[var(--color-text-primary)] hover:border-[var(--color-border-strong)]"
                        >
                            <RotateCcw className="h-4 w-4" />
                            Reset to Default
                        </button>
                        <button
                            type="button"
                            onClick={handleBack}
                            className="px-3 py-1.5 text-sm font-medium rounded bg-[var(--color-accent)] text-[var(--color-text-inverse)] hover:bg-[var(--color-accent-hover)]"
                        >
                            Back to Workspace
                        </button>
                    </div>
                </div>
            </div>

            <div className="flex-1 min-h-0 overflow-hidden p-6 pb-4">
                <div className="h-full min-h-0 flex flex-col gap-3">
                    {isLoading && (
                        <div className="text-sm text-[var(--color-text-muted)]">Loading default prompt...</div>
                    )}
                    {error && (
                        <div className="rounded bg-[var(--color-danger-soft)] px-3 py-2 text-xs text-[var(--color-danger)]">
                            {error.message || 'Failed to load default prompt.'}
                        </div>
                    )}
                    {!isLoading && !hasEvidenceBlock && (
                        <div className="rounded border border-[var(--color-warning)] bg-[var(--color-warning-soft)] px-3 py-2 text-xs text-[var(--color-warning-strong)]">
                            {EVIDENCE_BLOCK_TOKEN} is missing. Evidence will not be inserted into the prompt.
                        </div>
                    )}
                    {actionError && (
                        <div className="rounded bg-[var(--color-danger-soft)] px-3 py-2 text-xs text-[var(--color-danger)]">
                            {actionError}
                        </div>
                    )}
                    <textarea
                        value={draftPrompt}
                        onChange={(event) => {
                            setDraftPrompt(event.target.value);
                            setHasLocalEdits(true);
                        }}
                        className="h-full min-h-0 flex-1 w-full resize-none rounded-md border border-[var(--color-input-border)] bg-[var(--color-input-bg)] p-4 text-sm leading-relaxed text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                        placeholder="Paste or write your summary prompt template here..."
                    />
                </div>
            </div>

            <input
                ref={fileInputRef}
                type="file"
                accept="application/json"
                onChange={handleImportFile}
                className="hidden"
            />

            {showMissingWarning && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-overlay-scrim)] px-4">
                    <div className="w-full max-w-md rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-panel)] shadow-2xl">
                        <div className="border-b border-[var(--color-border)] px-4 py-3">
                            <p className="text-sm font-semibold text-[var(--color-text-primary)]">Missing evidence block</p>
                        </div>
                        <div className="px-4 py-3 text-sm text-[var(--color-text-secondary)]">
                            Your prompt doesn&apos;t include {EVIDENCE_BLOCK_TOKEN}. Summary generation will ignore evidence.
                            Go back anyway?
                        </div>
                        <div className="flex items-center justify-end gap-2 border-t border-[var(--color-border)] bg-[var(--color-surface-panel-alt)] px-4 py-3">
                            <button
                                type="button"
                                onClick={handleCancelWarning}
                                className="rounded border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-text-secondary)] hover:border-[var(--color-border-strong)]"
                            >
                                Stay
                            </button>
                            <button
                                type="button"
                                onClick={handleConfirmBack}
                                className="rounded bg-[var(--color-accent)] px-3 py-1.5 text-sm font-semibold text-[var(--color-text-inverse)] shadow hover:bg-[var(--color-accent-hover)]"
                            >
                                Go back anyway
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default PromptEditor;

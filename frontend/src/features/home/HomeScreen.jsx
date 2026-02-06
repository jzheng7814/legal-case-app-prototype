import React from 'react';
import ThemeToggle from '../../theme/ThemeToggle';

const HomeScreen = ({
    caseId,
    caseIdError,
    onCaseIdChange,
    onProceed,
    canProceed
}) => (
    <div className="min-h-screen bg-[var(--color-surface-app)] p-6 text-[var(--color-text-primary)] transition-colors">
        <div className="max-w-2xl mx-auto space-y-6">
            <div className="flex items-center justify-between">
                <h1 className="text-3xl font-bold">Legal Case Summarization</h1>
                <ThemeToggle />
            </div>

            <div className="bg-[var(--color-surface-panel)] rounded-lg shadow-md p-6 border border-[var(--color-border)]">
                <h2 className="text-xl font-semibold mb-4">Enter Case ID</h2>
                <input
                    type="text"
                    placeholder="Enter Case ID"
                    value={caseId}
                    onChange={(e) => onCaseIdChange(e.target.value)}
                    className="w-full px-3 py-2 border border-[var(--color-input-border)] rounded-md bg-[var(--color-input-bg)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]"
                />
                {caseIdError && (
                    <p className="mt-2 text-sm text-[var(--color-text-danger)]">{caseIdError}</p>
                )}
            </div>

            <button
                onClick={onProceed}
                disabled={!canProceed}
                className="w-full bg-[var(--color-accent)] text-[var(--color-text-inverse)] py-3 px-4 rounded-md font-medium hover:bg-[var(--color-accent-hover)] disabled:bg-[var(--color-surface-muted)] disabled:text-[var(--color-input-disabled-text)] disabled:cursor-not-allowed transition-colors"
            >
                Proceed to Summary Editor
            </button>
        </div>
    </div>
);

export default HomeScreen;

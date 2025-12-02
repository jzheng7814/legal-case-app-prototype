import React from 'react';
import { Upload, FileText } from 'lucide-react';
import ThemeToggle from '../../theme/ThemeToggle';

const HomeScreen = ({
    caseId,
    onCaseIdChange,
    uploadedFiles,
    onFileUpload,
    onProceed,
    canProceed,
    isProcessingUploads = false
}) => (
    <div className="min-h-screen bg-[var(--color-surface-app)] p-6 text-[var(--color-text-primary)] transition-colors">
        <div className="max-w-2xl mx-auto space-y-6">
            <div className="flex items-center justify-between">
                <h1 className="text-3xl font-bold">Legal Case Summarization</h1>
                <ThemeToggle />
            </div>

            <div className="bg-[var(--color-surface-panel)] rounded-lg shadow-md p-6 border border-[var(--color-border)]">
                <h2 className="text-xl font-semibold mb-4">Upload Case Documents</h2>

                <div className="border-2 border-dashed border-[var(--color-border-strong)] rounded-lg p-8 mb-4">
                    <div className="flex flex-col items-center text-center space-y-4 text-[var(--color-text-muted)]">
                        <Upload className="h-12 w-12" />
                        <div className="flex items-center justify-center gap-2 text-sm">
                            <label className="relative cursor-pointer bg-[var(--color-surface-panel)] border border-[var(--color-border)] rounded-md font-medium text-[var(--color-accent)] hover:text-[var(--color-accent-hover)] px-4 py-2 transition">
                                <span>Upload case files</span>
                                <input
                                    type="file"
                                    className="sr-only"
                                    multiple
                                    accept=".pdf,.doc,.docx,.txt"
                                    onChange={onFileUpload}
                                />
                            </label>
                            <span>or drag and drop</span>
                        </div>
                        <p className="text-xs">PDF, DOC, DOCX, TXT up to 10MB</p>
                        {isProcessingUploads && (
                            <p className="text-xs text-[var(--color-accent)]">Processing uploaded files...</p>
                        )}
                    </div>
                </div>

                {uploadedFiles.length > 0 && (
                    <div className="space-y-2 mb-4">
                        {uploadedFiles.map((file, index) => (
                            <div key={index} className="flex items-center p-3 bg-[var(--color-accent-soft)] rounded-md">
                                <FileText className="h-5 w-5 text-[var(--color-accent)] mr-2" />
                                <span className="text-sm text-[var(--color-accent-strong)]">{file.name}</span>
                            </div>
                        ))}
                    </div>
                )}

                <div className="mt-4">
                    <div className="text-center text-[var(--color-text-muted)] mb-4">OR</div>
                    <input
                        type="text"
                        placeholder="Enter Case ID (e.g., -1)"
                        value={caseId}
                        onChange={(e) => onCaseIdChange(e.target.value)}
                        className="w-full px-3 py-2 border border-[var(--color-input-border)] rounded-md bg-[var(--color-input-bg)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]"
                    />
                </div>
            </div>

            <button
                onClick={onProceed}
                disabled={!canProceed}
                className="w-full bg-[var(--color-accent)] text-[var(--color-text-inverse)] py-3 px-4 rounded-md font-medium hover:bg-[var(--color-accent-hover)] disabled:bg-[var(--color-surface-muted)] disabled:text-[var(--color-input-disabled-text)] disabled:cursor-not-allowed transition-colors"
            >
                {isProcessingUploads ? 'Preparing documents...' : 'Proceed to Summary Editor'}
            </button>
        </div>
    </div>
);

export default HomeScreen;

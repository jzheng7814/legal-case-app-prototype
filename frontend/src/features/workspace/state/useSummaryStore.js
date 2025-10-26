import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { diffWordsWithSpace } from 'diff';
import { fetchSuggestions, getSummaryJob, startSummaryJob } from '../../../services/apiClient';
import { DEFAULT_CASE_ID } from '../../../services/documentService';

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 600000;

const normaliseCaseId = (value) => {
    const trimmed = (value || '').trim();
    return trimmed.length > 0 ? trimmed : DEFAULT_CASE_ID;
};

const buildDocumentPayload = (documents = []) =>
    documents.map((doc) => ({
        id: doc.id,
        title: doc.title || doc.name || doc.id,
        include_full_text: true,
        content: doc.content
    }));

const normaliseSuggestions = (suggestions = []) =>
    suggestions.map((suggestion) => ({
        ...suggestion,
        type: suggestion.type || 'edit',
        originalText: suggestion.originalText ?? suggestion.original_text ?? '',
        text: suggestion.text ?? '',
        sourceDocument: suggestion.sourceDocument ?? suggestion.source_document ?? null
    }));

const normaliseChecklistCollection = (collection) => {
    if (!collection) {
        return [];
    }

    if (Array.isArray(collection)) {
        return collection
            .map((entry) => ({
                itemName: entry?.itemName ?? entry?.item_name ?? entry?.name ?? '',
                extraction: {
                    reasoning: entry?.extraction?.reasoning ?? entry?.result?.reasoning ?? '',
                    extracted: Array.isArray(entry?.extraction?.extracted ?? entry?.result?.extracted)
                        ? entry.extraction?.extracted ?? entry.result?.extracted
                        : []
                }
            }))
            .filter((entry) => entry.itemName);
    }

    const items = collection.items ?? collection.Items;
    if (Array.isArray(items)) {
        return items
            .map((entry) => ({
                itemName: entry?.itemName ?? entry?.item_name ?? entry?.name ?? '',
                extraction: {
                    reasoning: entry?.extraction?.reasoning ?? entry?.result?.reasoning ?? '',
                    extracted: Array.isArray(entry?.extraction?.extracted ?? entry?.result?.extracted)
                        ? entry.extraction?.extracted ?? entry.result?.extracted
                        : []
                }
            }))
            .filter((entry) => entry.itemName);
    }

    if (typeof collection === 'object') {
        return Object.entries(collection)
            .map(([itemName, payload]) => ({
                itemName,
                extraction: {
                    reasoning: payload?.reasoning ?? '',
                    extracted: Array.isArray(payload?.extracted) ? payload.extracted : []
                }
            }));
    }

    return [];
};

const toPositiveInteger = (value, defaultValue = 0) => {
    const parsed = typeof value === 'number' ? value : Number.parseInt(value, 10);
    if (!Number.isFinite(parsed) || parsed < 0) {
        return defaultValue;
    }
    return parsed;
};

const normalisePatchPayload = (patch = {}) => ({
    startIndex: toPositiveInteger(patch.startIndex ?? patch.start_index, 0),
    deleteCount: toPositiveInteger(patch.deleteCount ?? patch.delete_count, 0),
    insertText: typeof patch.insertText === 'string'
        ? patch.insertText
        : typeof patch.insert_text === 'string'
            ? patch.insert_text
            : ''
});

const buildWordLevelPatches = (baseSummary = '', nextSummary = '') => {
    const source = baseSummary ?? '';
    const target = nextSummary ?? '';
    if (source === target) {
        return [];
    }
    const segments = diffWordsWithSpace(source, target);
    const patches = [];
    let baseCursor = 0;
    let pendingPatch = null;

    const flushPatch = () => {
        if (pendingPatch && (pendingPatch.deleteCount > 0 || pendingPatch.insertText.length > 0)) {
            const startIndex = Math.max(0, Math.min(pendingPatch.startIndex, source.length));
            patches.push({
                startIndex,
                deleteCount: pendingPatch.deleteCount,
                insertText: pendingPatch.insertText
            });
        }
        pendingPatch = null;
    };

    segments.forEach((segment) => {
        const value = segment.value || '';
        if (!segment.added && !segment.removed) {
            baseCursor += value.length;
            flushPatch();
            return;
        }

        if (!pendingPatch) {
            pendingPatch = {
                startIndex: baseCursor,
                deleteCount: 0,
                insertText: ''
            };
        }

        if (segment.removed) {
            pendingPatch.deleteCount += value.length;
            baseCursor += value.length;
        }

        if (segment.added) {
            pendingPatch.insertText += value;
        }
    });

    flushPatch();

    return patches.filter((patch) => patch.deleteCount > 0 || patch.insertText.length > 0);
};

const applyRawPatchesToBase = (baseSummary = '', patches = []) => {
    if (!patches?.length) {
        return baseSummary ?? '';
    }
    const source = baseSummary ?? '';
    let cursor = 0;
    let output = '';
    patches
        .slice()
        .sort((a, b) => a.startIndex - b.startIndex)
        .forEach((patch) => {
            const boundedStart = Math.max(0, Math.min(patch.startIndex, source.length));
            output += source.slice(cursor, boundedStart);
            output += patch.insertText || '';
            cursor = boundedStart + patch.deleteCount;
        });
    output += source.slice(cursor);
    return output;
};

const resolveFinalSummary = (baseSummary = '', providedSummary, patches = []) => {
    const source = baseSummary ?? '';
    const provided = typeof providedSummary === 'string' ? providedSummary : null;
    if (provided != null && provided !== source) {
        return provided;
    }
    if (patches.length > 0) {
        return applyRawPatchesToBase(source, patches);
    }
    if (provided != null) {
        return provided;
    }
    return source;
};

const applyPatchesToBase = (baseSummary, patches) => {
    if (!baseSummary || !patches?.length) {
        return baseSummary ?? '';
    }
    let cursor = 0;
    let output = '';
    patches.forEach((patch) => {
        const { startIndex, deleteCount, insertText, status } = patch;
        const boundedStart = Math.min(startIndex, baseSummary.length);
        output += baseSummary.slice(cursor, boundedStart);
        if (status === 'applied') {
            output += insertText;
            cursor = boundedStart + deleteCount;
        } else {
            cursor = boundedStart;
        }
    });
    output += baseSummary.slice(cursor);
    return output;
};

const recomputePatchPositions = (baseSummary, patches) => {
    if (!patches) {
        return [];
    }
    let delta = 0;
    return patches.map((patch) => {
        const currentStart = patch.startIndex + delta;
        const appliedLength = patch.status === 'applied'
            ? patch.insertText.length
            : patch.deleteCount;
        const currentEnd = currentStart + appliedLength;
        const nextDelta = patch.status === 'applied'
            ? delta + (patch.insertText.length - patch.deleteCount)
            : delta;
        delta = nextDelta;
        return {
            ...patch,
            currentStart,
            currentEnd
        };
    });
};

const hydratePatchAction = (action) => {
    if (!action) {
        return null;
    }
    return {
        ...action,
        patches: recomputePatchPositions(action.baseSummary, action.patches)
    };
};

const useSummaryStore = ({
    caseId = DEFAULT_CASE_ID,
    prefetchedDocumentChecklists = null,
    documentChecklistStatus: initialDocumentChecklistStatus = 'idle'
} = {}) => {
    const [summaryText, setSummaryTextState] = useState('');
    const [isEditMode, setIsEditMode] = useState(false);
    const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
    const [summaryJobId, setSummaryJobId] = useState(null);
    const [lastSummaryError, setLastSummaryError] = useState(null);
    const [suggestions, setSuggestions] = useState([]);
    const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(false);
    const [suggestionsError, setSuggestionsError] = useState(null);
    const summaryRef = useRef(null);
    const [documentChecklists, setDocumentChecklists] = useState([]);
    const [documentChecklistStatus, setDocumentChecklistStatus] = useState(
        initialDocumentChecklistStatus ?? 'idle'
    );
    const [summaryChecklists, setSummaryChecklists] = useState([]);
    const [versionHistory, setVersionHistory] = useState([]);
    const [activeVersionId, setActiveVersionId] = useState(null);
    const [patchAction, setPatchAction] = useState(null);
    const [activePatchId, setActivePatchId] = useState(null);

    const toggleEditMode = useCallback(() => {
        setIsEditMode((previous) => !previous);
    }, []);

    const resolvedCaseId = useMemo(() => normaliseCaseId(caseId), [caseId]);

    useEffect(() => {
        if (prefetchedDocumentChecklists != null) {
            setDocumentChecklists(normaliseChecklistCollection(prefetchedDocumentChecklists));
            setDocumentChecklistStatus(
                initialDocumentChecklistStatus && initialDocumentChecklistStatus !== 'pending'
                    ? initialDocumentChecklistStatus
                    : 'cached'
            );
            return;
        }

        setDocumentChecklistStatus((currentStatus) => {
            if (currentStatus === 'ready' && initialDocumentChecklistStatus === 'pending') {
                return currentStatus;
            }
            return initialDocumentChecklistStatus ?? currentStatus;
        });
    }, [prefetchedDocumentChecklists, initialDocumentChecklistStatus]);

    const draftSummaryRef = useRef(null);

    const setSummaryText = useCallback((value, options = {}) => {
        const { skipPatchInvalidation = false } = options;
        setActiveVersionId(null);
        draftSummaryRef.current = null;
        setSummaryTextState((previous) => {
            const nextValue = typeof value === 'function' ? value(previous) : value;
            if (!skipPatchInvalidation && nextValue !== previous) {
                setPatchAction((current) => (current && !current.isStale ? { ...current, isStale: true } : current));
                setActivePatchId(null);
            }
            return nextValue;
        });
    }, []);

    const summaryTextRef = useRef('');
    useEffect(() => {
        summaryTextRef.current = summaryText;
    }, [summaryText]);

    const saveCurrentVersion = useCallback(() => {
        const timestamp = new Date();
        const versionId = `${timestamp.getTime().toString()}-${Math.random().toString(36).slice(2, 8)}`;
        const entry = {
            id: versionId,
            savedAt: timestamp.toISOString(),
            summaryText
        };
        setVersionHistory((previous) => [entry, ...previous]);
        setActiveVersionId(versionId);
        draftSummaryRef.current = null;
        return entry;
    }, [summaryText]);

    const selectVersion = useCallback((versionId) => {
        if (!versionId) {
            if (draftSummaryRef.current != null) {
                setSummaryTextState(draftSummaryRef.current);
            }
            draftSummaryRef.current = null;
            setActiveVersionId(null);
            return;
        }

        const targetVersion = versionHistory.find((entry) => entry.id === versionId);
        if (!targetVersion) {
            return;
        }

        if (activeVersionId == null) {
            draftSummaryRef.current = summaryText;
        }

        setActiveVersionId(versionId);
        setSummaryTextState(targetVersion.summaryText);
    }, [activeVersionId, summaryText, versionHistory]);

    const applyAiSummaryUpdate = useCallback((nextSummary, patches = []) => {
        const baseSummary = summaryTextRef.current ?? '';
        const normalisedPatches = Array.isArray(patches)
            ? patches
                .map(normalisePatchPayload)
                .filter((entry) => entry.deleteCount > 0 || entry.insertText.length > 0)
            : [];

        const finalSummary = resolveFinalSummary(baseSummary, nextSummary, normalisedPatches);
        const wordPatches = buildWordLevelPatches(baseSummary, finalSummary);

        if (wordPatches.length === 0) {
            setPatchAction(null);
            setActivePatchId(null);
            setSummaryText(finalSummary ?? '', { skipPatchInvalidation: true });
            return;
        }

        const actionId = `ai-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
        const preparedAction = {
            id: actionId,
            createdAt: new Date().toISOString(),
            baseSummary,
            isStale: false,
            patches: wordPatches.map((patch, index) => ({
                ...patch,
                id: `${actionId}-${index}`,
                deletedText: baseSummary.slice(patch.startIndex, patch.startIndex + patch.deleteCount) || '',
                status: 'applied'
            }))
        };

        setPatchAction(hydratePatchAction(preparedAction));
        setActivePatchId(null);
        setSummaryText(finalSummary ?? '', { skipPatchInvalidation: true });
    }, [setSummaryText]);

    const revertPatch = useCallback((patchId) => {
        setPatchAction((current) => {
            if (!current || current.isStale) {
                return current;
            }
            const index = current.patches.findIndex((patch) => patch.id === patchId);
            if (index === -1 || current.patches[index].status !== 'applied') {
                return current;
            }
            const updated = {
                ...current,
                patches: current.patches.map((patch, idx) =>
                    idx === index ? { ...patch, status: 'reverted' } : patch
                )
            };
            const hydrated = hydratePatchAction(updated);
            const recomposed = applyPatchesToBase(hydrated.baseSummary, hydrated.patches);
            setSummaryText(recomposed, { skipPatchInvalidation: true });
            if (activePatchId === patchId) {
                setActivePatchId(null);
            }
            return hydrated;
        });
    }, [activePatchId, setSummaryText]);

    const revertAllPatches = useCallback(() => {
        setPatchAction((current) => {
            if (!current || current.isStale) {
                return current;
            }
            if (!current.patches.some((patch) => patch.status === 'applied')) {
                return current;
            }
            const updated = {
                ...current,
                patches: current.patches.map((patch) => ({ ...patch, status: 'reverted' }))
            };
            setSummaryText(updated.baseSummary, { skipPatchInvalidation: true });
            setActivePatchId(null);
            return hydratePatchAction(updated);
        });
    }, [setSummaryText]);

    const previewPatch = useCallback((patchId) => {
        if (!patchId) {
            setActivePatchId(null);
            return;
        }
        if (!patchAction || patchAction.isStale) {
            setActivePatchId(null);
            return;
        }
        const exists = patchAction.patches.some(
            (patch) => patch.id === patchId && patch.status === 'applied'
        );
        setActivePatchId(exists ? patchId : null);
    }, [patchAction]);

    const clearPatchPreview = useCallback(() => {
        setActivePatchId(null);
    }, []);

    const dismissPatchAction = useCallback(() => {
        setPatchAction(null);
        setActivePatchId(null);
    }, []);

    useEffect(() => {
        if (!patchAction || patchAction.isStale) {
            setActivePatchId(null);
            return;
        }
        if (activePatchId) {
            const stillExists = patchAction.patches.some(
                (patch) => patch.id === activePatchId && patch.status === 'applied'
            );
            if (!stillExists) {
                setActivePatchId(null);
            }
        }
    }, [activePatchId, patchAction]);

    const pollSummaryJob = useCallback(async (caseIdentifier, jobId) => {
        const startedAt = Date.now();
        let currentJob;
        const normalisedCaseId = normaliseCaseId(caseIdentifier);

        while (Date.now() - startedAt < POLL_TIMEOUT_MS) {
            currentJob = await getSummaryJob(normalisedCaseId, jobId).then((response) => response.job);
            if (currentJob.status === 'succeeded' || currentJob.status === 'failed') {
                return currentJob;
            }
            await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
        }

        throw new Error('Timed out waiting for summary generation to complete.');
    }, []);

    const generateAISummary = useCallback(async (
        { caseId: overrideCaseId, documents = [], instructions } = {}
    ) => {
        if (!documents.length) {
            throw new Error('At least one document is required to generate a summary.');
        }

        const targetCaseId = normaliseCaseId(overrideCaseId ?? resolvedCaseId);
        setIsGeneratingSummary(true);
        setLastSummaryError(null);
        setSuggestions([]);
        setSummaryChecklists([]);

        try {
            const requestBody = {
                documents: buildDocumentPayload(documents),
                ...(instructions ? { instructions } : {})
            };
            const { job } = await startSummaryJob(targetCaseId, requestBody);
            setSummaryJobId(job.id);

            const finalJob = await pollSummaryJob(targetCaseId, job.id);
            if (finalJob.status !== 'succeeded') {
                throw new Error(finalJob.error || 'Summary generation failed.');
            }
            setSummaryText(finalJob.summary_text || '');
            return finalJob.summary_text || '';
        } catch (error) {
            console.error('Failed to generate summary', error);
            setLastSummaryError(error);
            setSummaryText((previous) => previous || 'Failed to generate AI summary. Please try again.');
            throw error;
        } finally {
            setIsGeneratingSummary(false);
        }
    }, [pollSummaryJob, resolvedCaseId, setSummaryText]);

    const refreshSuggestions = useCallback(async (
        { caseId: overrideCaseId, documents = [], maxSuggestions = 6 } = {}
    ) => {
        if (!summaryText.trim()) {
            setSummaryChecklists([]);
            setDocumentChecklistStatus('idle');
            return [];
        }

        setIsLoadingSuggestions(true);
        setSuggestionsError(null);
        setDocumentChecklistStatus('pending');
        try {
            const response = await fetchSuggestions(normaliseCaseId(overrideCaseId ?? resolvedCaseId), {
                summaryText,
                documents: buildDocumentPayload(documents),
                maxSuggestions
            });
            const normalisedSuggestions = normaliseSuggestions(response.suggestions);
            const documentChecklistPayload = response.documentChecklists ?? response.document_checklists ?? [];
            const summaryChecklistPayload = response.summaryChecklists ?? response.summary_checklists ?? [];
            setDocumentChecklists(normaliseChecklistCollection(documentChecklistPayload));
            setDocumentChecklistStatus('ready');
            setSummaryChecklists(normaliseChecklistCollection(summaryChecklistPayload));
            setSuggestions(normalisedSuggestions);
            return normalisedSuggestions;
        } catch (error) {
            console.error('Failed to fetch AI suggestions', error);
            setSuggestionsError(error);
            setDocumentChecklistStatus('error');
            throw error;
        } finally {
            setIsLoadingSuggestions(false);
        }
    }, [resolvedCaseId, summaryText]);

    const value = useMemo(() => ({
        summaryText,
        setSummaryText,
        isEditMode,
        setIsEditMode,
        toggleEditMode,
        isGeneratingSummary,
        generateAISummary,
        summaryJobId,
        lastSummaryError,
        suggestions,
        refreshSuggestions,
        isLoadingSuggestions,
        suggestionsError,
        summaryRef,
        documentChecklists,
        documentChecklistStatus,
        summaryChecklists,
        versionHistory,
        activeVersionId,
        saveCurrentVersion,
        selectVersion,
        patchAction,
        activePatchId,
        applyAiSummaryUpdate,
        revertPatch,
        revertAllPatches,
        previewPatch,
        clearPatchPreview,
        dismissPatchAction,
        caseId: resolvedCaseId
    }), [
        generateAISummary,
        isEditMode,
        isGeneratingSummary,
        lastSummaryError,
        refreshSuggestions,
        suggestions,
        suggestionsError,
        summaryJobId,
        summaryText,
        toggleEditMode,
        isLoadingSuggestions,
        documentChecklists,
        documentChecklistStatus,
        summaryChecklists,
        versionHistory,
        activeVersionId,
        saveCurrentVersion,
        selectVersion,
        patchAction,
        activePatchId,
        applyAiSummaryUpdate,
        revertPatch,
        revertAllPatches,
        previewPatch,
        clearPatchPreview,
        dismissPatchAction,
        resolvedCaseId,
        setSummaryText
    ]);

    return value;
};

export default useSummaryStore;

import { useCallback, useMemo, useRef, useState } from 'react';
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

const useSummaryStore = ({ caseId = DEFAULT_CASE_ID } = {}) => {
    const [summaryText, setSummaryText] = useState('');
    const [isEditMode, setIsEditMode] = useState(false);
    const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
    const [summaryJobId, setSummaryJobId] = useState(null);
    const [lastSummaryError, setLastSummaryError] = useState(null);
    const [suggestions, setSuggestions] = useState([]);
    const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(false);
    const [suggestionsError, setSuggestionsError] = useState(null);
    const summaryRef = useRef(null);
    const [documentChecklists, setDocumentChecklists] = useState({});
    const [summaryChecklists, setSummaryChecklists] = useState({});

    const toggleEditMode = useCallback(() => {
        setIsEditMode((previous) => !previous);
    }, []);

    const resolvedCaseId = useMemo(() => normaliseCaseId(caseId), [caseId]);

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
        setDocumentChecklists({});
        setSummaryChecklists({});

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
    }, [pollSummaryJob, resolvedCaseId]);

    const refreshSuggestions = useCallback(async (
        { caseId: overrideCaseId, documents = [], maxSuggestions = 6 } = {}
    ) => {
        if (!summaryText.trim()) {
            setDocumentChecklists({});
            setSummaryChecklists({});
            return [];
        }

        setIsLoadingSuggestions(true);
        setSuggestionsError(null);
        try {
            const response = await fetchSuggestions(normaliseCaseId(overrideCaseId ?? resolvedCaseId), {
                summaryText,
                documents: buildDocumentPayload(documents),
                maxSuggestions
            });
            const normalised = normaliseSuggestions(response.suggestions);
            const documentChecklistPayload = response.documentChecklists ?? response.document_checklists ?? {};
            const summaryChecklistPayload = response.summaryChecklists ?? response.summary_checklists ?? {};
            setDocumentChecklists(documentChecklistPayload);
            setSummaryChecklists(summaryChecklistPayload);
            setSuggestions(normalised);
            return normalised;
        } catch (error) {
            console.error('Failed to fetch AI suggestions', error);
            setSuggestionsError(error);
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
        summaryChecklists,
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
        summaryChecklists,
        resolvedCaseId
    ]);

    return value;
};

export default useSummaryStore;

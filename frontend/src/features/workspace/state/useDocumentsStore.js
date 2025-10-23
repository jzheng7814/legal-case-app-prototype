import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { DEFAULT_CASE_ID, loadDocuments as loadCaseDocuments, loadDocumentsFromPublic } from '../../../services/documentService';

const normaliseCaseId = (value) => {
    const trimmed = (value || '').trim();
    return trimmed.length > 0 ? trimmed : DEFAULT_CASE_ID;
};

const useDocumentsStore = ({ caseId = DEFAULT_CASE_ID, initialUploads = [] } = {}) => {
    const [currentCaseId, setCurrentCaseId] = useState(normaliseCaseId(caseId));
    const [remoteDocuments, setRemoteDocuments] = useState([]);
    const [uploadedDocuments, setUploadedDocuments] = useState(initialUploads);
    const [selectedDocument, setSelectedDocument] = useState(null);
    const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
    const [lastError, setLastError] = useState(null);
    const [documentChecklists, setDocumentChecklists] = useState(null);
    const [documentChecklistStatus, setDocumentChecklistStatus] = useState('idle');
    const documentRef = useRef(null);

    const combinedDocuments = useMemo(
        () => [...remoteDocuments, ...uploadedDocuments],
        [remoteDocuments, uploadedDocuments]
    );

    const loadDocuments = useCallback(async (requestedCaseId = currentCaseId) => {
        const resolvedCaseId = normaliseCaseId(requestedCaseId);
        setIsLoadingDocuments(true);
        setLastError(null);
        setDocumentChecklists(null);
        setDocumentChecklistStatus('pending');

        try {
            const { documents: loadedDocs, documentChecklists: prefetchedChecklists, checklistStatus } =
                await loadCaseDocuments(resolvedCaseId);
            setRemoteDocuments(loadedDocs);
            setCurrentCaseId(resolvedCaseId);
            setDocumentChecklists(prefetchedChecklists ?? null);
            setDocumentChecklistStatus(checklistStatus ?? (loadedDocs.length > 0 ? 'ready' : 'empty'));
        } catch (error) {
            console.error('Failed to load documents from backend, falling back to public assets.', error);
            setLastError(error);
            try {
                const {
                    documents: fallbackDocs,
                    documentChecklists: prefetchedChecklists,
                    checklistStatus
                } = await loadDocumentsFromPublic();
                setRemoteDocuments(fallbackDocs);
                setCurrentCaseId(resolvedCaseId);
                setDocumentChecklists(prefetchedChecklists ?? null);
                setDocumentChecklistStatus(checklistStatus ?? (fallbackDocs.length > 0 ? 'fallback' : 'empty'));
            } catch (fallbackError) {
                console.error('Fallback document loading failed', fallbackError);
                setRemoteDocuments([]);
                setLastError(fallbackError);
                setDocumentChecklists(null);
                setDocumentChecklistStatus('error');
            }
        } finally {
            setIsLoadingDocuments(false);
        }
    }, [currentCaseId]);

    useEffect(() => {
        setUploadedDocuments(initialUploads);
    }, [initialUploads]);

    useEffect(() => {
        const resolved = normaliseCaseId(caseId);
        setCurrentCaseId(resolved);
    }, [caseId]);

    useEffect(() => {
        loadDocuments(currentCaseId);
    }, [currentCaseId, loadDocuments]);

    useEffect(() => {
        if (documentChecklistStatus !== 'pending') {
            return undefined;
        }

        let cancelled = false;
        const POLL_INTERVAL_MS = 2000;

        let pollTimeoutId = null;

        const pollForChecklists = async () => {
            try {
                const {
                    documents: loadedDocs,
                    documentChecklists: prefetchedChecklists,
                    checklistStatus
                } = await loadCaseDocuments(currentCaseId);
                if (cancelled) {
                    return;
                }

                if (Array.isArray(loadedDocs) && loadedDocs.length) {
                    setRemoteDocuments(loadedDocs);
                }

                if (prefetchedChecklists) {
                    setDocumentChecklists(prefetchedChecklists);
                    setDocumentChecklistStatus(checklistStatus ?? 'ready');
                    return;
                }

                if (checklistStatus && checklistStatus !== 'pending') {
                    setDocumentChecklistStatus(checklistStatus);
                    return;
                }
            } catch (error) {
                if (!cancelled) {
                    console.error('Checklist polling failed', error);
                }
            }

            if (!cancelled) {
                scheduleNext();
            }
        };

        const scheduleNext = () => {
            if (pollTimeoutId) {
                window.clearTimeout(pollTimeoutId);
            }
            pollTimeoutId = window.setTimeout(pollForChecklists, POLL_INTERVAL_MS);
        };

        scheduleNext();
        pollForChecklists();

        return () => {
            cancelled = true;
            if (pollTimeoutId) {
                window.clearTimeout(pollTimeoutId);
            }
        };
    }, [currentCaseId, documentChecklistStatus]);

    useEffect(() => {
        setSelectedDocument((current) => {
            if (current != null && combinedDocuments.some((doc) => doc.id === current)) {
                return current;
            }
            return combinedDocuments.length > 0 ? combinedDocuments[0].id : null;
        });
    }, [combinedDocuments]);

    const getCurrentDocument = useCallback(() => {
        if (isLoadingDocuments) {
            return 'Loading documents...';
        }
        const doc = combinedDocuments.find((d) => d.id === selectedDocument);
        if (doc) {
            return doc.content;
        }
        if (combinedDocuments.length === 0) {
            return lastError
                ? 'Failed to load documents. Please try again later or upload files manually.'
                : 'No documents available.';
        }
        return 'No document selected';
    }, [combinedDocuments, isLoadingDocuments, lastError, selectedDocument]);

    const value = useMemo(() => ({
        caseId: currentCaseId,
        documents: combinedDocuments,
        selectedDocument,
        setSelectedDocument,
        isLoadingDocuments,
        loadDocuments,
        documentRef,
        getCurrentDocument,
        uploadedDocuments,
        setUploadedDocuments,
        remoteDocuments,
        lastError,
        documentChecklists,
        documentChecklistStatus
    }), [
        combinedDocuments,
        currentCaseId,
        getCurrentDocument,
        isLoadingDocuments,
        loadDocuments,
        remoteDocuments,
        selectedDocument,
        uploadedDocuments,
        lastError,
        documentChecklists,
        documentChecklistStatus
    ]);

    return value;
};

export default useDocumentsStore;

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
    const [selectedDocument, setSelectedDocument] = useState('');
    const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
    const [lastError, setLastError] = useState(null);
    const documentRef = useRef(null);

    const combinedDocuments = useMemo(
        () => [...remoteDocuments, ...uploadedDocuments],
        [remoteDocuments, uploadedDocuments]
    );

    const loadDocuments = useCallback(async (requestedCaseId = currentCaseId) => {
        const resolvedCaseId = normaliseCaseId(requestedCaseId);
        setIsLoadingDocuments(true);
        setLastError(null);

        try {
            const loadedDocs = await loadCaseDocuments(resolvedCaseId);
            setRemoteDocuments(loadedDocs);
            setCurrentCaseId(resolvedCaseId);
        } catch (error) {
            console.error('Failed to load documents from backend, falling back to public assets.', error);
            setLastError(error);
            try {
                const fallbackDocs = await loadDocumentsFromPublic();
                setRemoteDocuments(fallbackDocs);
                setCurrentCaseId(resolvedCaseId);
            } catch (fallbackError) {
                console.error('Fallback document loading failed', fallbackError);
                setRemoteDocuments([]);
                setLastError(fallbackError);
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
        setSelectedDocument((current) => {
            if (current && combinedDocuments.some((doc) => doc.id === current)) {
                return current;
            }
            return combinedDocuments[0]?.id || '';
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
        lastError
    }), [
        combinedDocuments,
        currentCaseId,
        getCurrentDocument,
        isLoadingDocuments,
        loadDocuments,
        remoteDocuments,
        selectedDocument,
        uploadedDocuments,
        lastError
    ]);

    return value;
};

export default useDocumentsStore;

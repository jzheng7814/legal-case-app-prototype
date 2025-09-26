import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { DEFAULT_CASE_ID, loadDocuments as loadCaseDocuments, loadDocumentsFromPublic } from '../../../services/documentService';

const useDocumentsStore = () => {
    const [documents, setDocuments] = useState([]);
    const [selectedDocument, setSelectedDocument] = useState('');
    const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
    const documentRef = useRef(null);

    const loadDocuments = useCallback(async (caseId = DEFAULT_CASE_ID) => {
        setIsLoadingDocuments(true);
        try {
            const loadedDocs = await loadCaseDocuments(caseId);
            setDocuments(loadedDocs);
            if (loadedDocs.length > 0) {
                setSelectedDocument((current) => current || loadedDocs[0].id);
            }
        } catch (error) {
            console.error('Failed to load documents from backend, falling back to public assets.', error);
            try {
                const fallbackDocs = await loadDocumentsFromPublic();
                setDocuments(fallbackDocs);
                if (fallbackDocs.length > 0) {
                    setSelectedDocument((current) => current || fallbackDocs[0].id);
                }
            } catch (fallbackError) {
                console.error('Fallback document loading failed', fallbackError);
            }
        } finally {
            setIsLoadingDocuments(false);
        }
    }, []);

    useEffect(() => {
        loadDocuments();
    }, [loadDocuments]);

    const getCurrentDocument = useCallback(() => {
        if (isLoadingDocuments) {
            return 'Loading documents...';
        }
        const doc = documents.find((d) => d.id === selectedDocument);
        return doc ? doc.content : 'No document selected';
    }, [documents, isLoadingDocuments, selectedDocument]);

    const value = useMemo(() => ({
        documents,
        setDocuments,
        selectedDocument,
        setSelectedDocument,
        isLoadingDocuments,
        loadDocuments,
        documentRef,
        getCurrentDocument
    }), [documents, isLoadingDocuments, loadDocuments, selectedDocument]);

    return value;
};

export default useDocumentsStore;

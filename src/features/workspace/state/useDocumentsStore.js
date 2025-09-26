import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { loadDocumentsFromPublic } from '../../../services/documentService';

const useDocumentsStore = () => {
    const [documents, setDocuments] = useState([]);
    const [selectedDocument, setSelectedDocument] = useState('');
    const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
    const documentRef = useRef(null);

    const loadDocuments = useCallback(async () => {
        setIsLoadingDocuments(true);
        try {
            const loadedDocs = await loadDocumentsFromPublic();
            setDocuments(loadedDocs);
            if (loadedDocs.length > 0) {
                setSelectedDocument((current) => current || loadedDocs[0].id);
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

import { fetchDocuments as fetchDocumentsFromApi } from './apiClient';

export const DEFAULT_CASE_ID = 'demo-case';

const LEGACY_DOCUMENTS = [
    { id: 'main-case', name: 'Johnson v. XYZ Corporation', type: 'Case File', filename: 'main-case.txt' },
    { id: 'contract', name: 'Software Licensing Agreement', type: 'Contract', filename: 'contract.txt' },
    { id: 'correspondence', name: 'Email Correspondence', type: 'Communications', filename: 'correspondence.txt' }
];

export const getDefaultDocumentList = () => LEGACY_DOCUMENTS;

export const loadDocuments = async (caseId = DEFAULT_CASE_ID) => {
    try {
        const documents = await fetchDocumentsFromApi(caseId);
        if (Array.isArray(documents) && documents.length > 0) {
            return documents;
        }
    } catch (error) {
        console.warn('Falling back to static public documents due to API error:', error);
        return loadDocumentsFromPublic();
    }
    return loadDocumentsFromPublic();
};

export const loadDocumentsFromPublic = async () => {
    const loadedDocs = [];

    for (const doc of LEGACY_DOCUMENTS) {
        try {
            const response = await fetch(`/documents/${doc.filename}`);
            if (response.ok) {
                const content = await response.text();
                loadedDocs.push({ ...doc, content });
            } else {
                loadedDocs.push({
                    ...doc,
                    content: `Failed to load document: ${doc.filename}`
                });
            }
        } catch (error) {
            loadedDocs.push({
                ...doc,
                content: `Error loading document: ${doc.filename}. ${error.message}`
            });
        }
    }

    return loadedDocs;
};

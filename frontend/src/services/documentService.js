import { fetchDocuments as fetchDocumentsFromApi } from './apiClient';

// Reminder: '-1' is the reserved fallback case id for bundled mock documents.
export const DEFAULT_CASE_ID = '-1';

const LEGACY_DOCUMENTS = [
    { id: 1, title: 'Johnson v. XYZ Corporation', type: 'Case File', filename: 'main-case.txt' },
    { id: 2, title: 'Software Licensing Agreement', type: 'Contract', filename: 'contract.txt' },
    { id: 3, title: 'Email Correspondence', type: 'Communications', filename: 'correspondence.txt' }
];

export const getDefaultDocumentList = () => LEGACY_DOCUMENTS;

const coerceDocumentId = (value) => {
    if (typeof value === 'number' && Number.isFinite(value)) {
        return value;
    }
    if (typeof value === 'string') {
        const trimmed = value.trim();
        if (trimmed.length > 0) {
            const parsed = Number.parseInt(trimmed, 10);
            if (!Number.isNaN(parsed)) {
                return parsed;
            }
        }
    }
    throw new Error(`Document id "${value}" is not a valid integer identifier.`);
};

const normaliseDocument = (doc = {}) => {
    if (!doc || typeof doc !== 'object') {
        return doc;
    }
    const id = coerceDocumentId(doc.id);
    const defaultTitle = `Document ${id}`;
    const title = doc.title ?? doc.name ?? defaultTitle;
    const { name: _LEGACY_NAME, ...rest } = doc;
    return { ...rest, id, title };
};

export const loadDocuments = async (caseId = DEFAULT_CASE_ID) => {
    try {
        const payload = await fetchDocumentsFromApi(caseId);
        const fetchedDocuments = Array.isArray(payload?.documents) ? payload.documents : [];
        if (fetchedDocuments.length > 0) {
            return {
                documents: fetchedDocuments.map((doc) => normaliseDocument(doc)),
                documentChecklists: payload?.documentChecklists ?? payload?.document_checklists ?? null,
                checklistStatus:
                    payload?.checklistStatus ??
                    payload?.checklist_status ??
                    'pending'
            };
        }
        return {
            documents: [],
            documentChecklists: payload?.documentChecklists ?? payload?.document_checklists ?? null,
            checklistStatus:
                payload?.checklistStatus ??
                payload?.checklist_status ??
                'empty'
        };
    } catch (error) {
        console.warn('Falling back to static public documents due to API error:', error);
        return loadDocumentsFromPublic();
    }
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

    return {
        documents: loadedDocs.map((doc) => normaliseDocument(doc)),
        documentChecklists: null,
        checklistStatus: loadedDocs.length > 0 ? 'fallback' : 'empty'
    };
};

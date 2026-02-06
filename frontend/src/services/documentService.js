import { fetchDocuments as fetchDocumentsFromApi } from './apiClient';

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

const resolveCaseId = (caseId) => {
    const trimmed = String(caseId ?? '').trim();
    if (!trimmed) {
        throw new Error('Case ID is required to load documents.');
    }
    return trimmed;
};

export const loadDocuments = async (caseId) => {
    const resolvedCaseId = resolveCaseId(caseId);
    const payload = await fetchDocumentsFromApi(resolvedCaseId);
    const fetchedDocuments = Array.isArray(payload?.documents) ? payload.documents : [];
    if (fetchedDocuments.length > 0) {
        return {
            documents: fetchedDocuments.map((doc) => normaliseDocument(doc)),
            checklistStatus:
                payload?.checklistStatus ??
                payload?.checklist_status ??
                'pending'
        };
    }
    return {
        documents: [],
        checklistStatus:
            payload?.checklistStatus ??
            payload?.checklist_status ??
            'empty'
    };
};

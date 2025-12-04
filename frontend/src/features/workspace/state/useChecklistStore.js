import { useCallback, useEffect, useMemo, useState } from 'react';
import {
    addChecklistItem,
    deleteChecklistItem,
    fetchChecklist
} from '../../../services/apiClient';
import { DEFAULT_CASE_ID } from '../../../services/documentService';

const normaliseCaseId = (value) => {
    const trimmed = (value || '').trim();
    return trimmed.length > 0 ? trimmed : DEFAULT_CASE_ID;
};

const parseDocumentId = (value) => {
    if (value == null) {
        return null;
    }
    const parsed = Number.parseInt(value, 10);
    return Number.isNaN(parsed) ? null : parsed;
};

const normaliseCategories = (payload) => {
    if (!payload) {
        return [];
    }
    const categories = Array.isArray(payload?.categories) ? payload.categories : [];
    return categories.map((category) => ({
        id: category.id,
        label: category.label,
        color: category.color,
        values: Array.isArray(category.values)
            ? category.values.map((value) => ({
                id: value.id,
                value: value.value ?? '',
                text: value.text ?? value.value ?? '',
                documentId: parseDocumentId(value.documentId ?? value.document_id),
                startOffset: value.startOffset ?? value.start_offset ?? null,
                endOffset: value.endOffset ?? value.end_offset ?? null
            }))
            : []
    }));
};

const useChecklistStore = ({ caseId = DEFAULT_CASE_ID } = {}) => {
    const [categories, setCategories] = useState([]);
    const [signature, setSignature] = useState(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);

    const resolvedCaseId = useMemo(() => normaliseCaseId(caseId), [caseId]);

    const hydrateResponse = useCallback((response) => {
        if (!response) {
            setCategories([]);
            setSignature(null);
            return;
        }
        setCategories(normaliseCategories(response));
        setSignature(response.signature ?? null);
    }, []);

    const refreshChecklist = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            const response = await fetchChecklist(resolvedCaseId);
            hydrateResponse(response);
            return response;
        } catch (err) {
            setError(err);
            throw err;
        } finally {
            setIsLoading(false);
        }
    }, [hydrateResponse, resolvedCaseId]);

    const addItem = useCallback(async (payload) => {
        setIsLoading(true);
        setError(null);
        try {
            const response = await addChecklistItem(resolvedCaseId, payload);
            hydrateResponse(response);
            return response;
        } catch (err) {
            setError(err);
            throw err;
        } finally {
            setIsLoading(false);
        }
    }, [hydrateResponse, resolvedCaseId]);

    const deleteItem = useCallback(async (valueId) => {
        if (!valueId) {
            return null;
        }
        setIsLoading(true);
        setError(null);
        try {
            const response = await deleteChecklistItem(resolvedCaseId, valueId);
            hydrateResponse(response);
            return response;
        } catch (err) {
            setError(err);
            throw err;
        } finally {
            setIsLoading(false);
        }
    }, [hydrateResponse, resolvedCaseId]);

    useEffect(() => {
        refreshChecklist();
    }, [refreshChecklist]);

    const highlightsByDocument = useMemo(() => {
        const lookup = {};
        categories.forEach((category) => {
            category.values.forEach((value) => {
                if (
                    value.documentId == null ||
                    value.startOffset == null ||
                    value.endOffset == null ||
                    value.endOffset <= value.startOffset
                ) {
                    return;
                }
                const key = value.documentId;
                if (!lookup[key]) {
                    lookup[key] = [];
                }
                lookup[key].push({
                    id: value.id,
                    categoryId: category.id,
                    color: category.color,
                    label: category.label,
                    startOffset: value.startOffset,
                    endOffset: value.endOffset,
                    text: value.text || value.value
                });
            });
        });
        Object.values(lookup).forEach((entries) => {
            entries.sort((a, b) => a.startOffset - b.startOffset || a.endOffset - b.endOffset);
        });
        return lookup;
    }, [categories]);

    return {
        categories,
        signature,
        isLoading,
        error,
        refreshChecklist,
        addItem,
        deleteItem,
        highlightsByDocument
    };
};

export default useChecklistStore;

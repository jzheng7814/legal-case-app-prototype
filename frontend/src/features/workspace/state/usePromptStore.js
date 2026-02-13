import { useCallback, useEffect, useState } from 'react';
import { fetchSummaryPrompt } from '../../../services/apiClient';

const STORAGE_KEY = 'legal_case_summary_prompt_v1';

const loadStoredPrompt = () => {
    if (typeof window === 'undefined') {
        return null;
    }
    try {
        const stored = window.localStorage.getItem(STORAGE_KEY);
        return stored && stored.length ? stored : null;
    } catch (error) {
        console.warn('Unable to access localStorage for prompt', error);
        return null;
    }
};

const saveStoredPrompt = (prompt) => {
    if (typeof window === 'undefined') {
        return;
    }
    try {
        window.localStorage.setItem(STORAGE_KEY, prompt);
    } catch (error) {
        console.warn('Unable to store prompt in localStorage', error);
    }
};

const clearStoredPrompt = () => {
    if (typeof window === 'undefined') {
        return;
    }
    try {
        window.localStorage.removeItem(STORAGE_KEY);
    } catch (error) {
        console.warn('Unable to clear prompt from localStorage', error);
    }
};

const usePromptStore = () => {
    const storedPrompt = loadStoredPrompt();
    const [prompt, setPrompt] = useState(storedPrompt ?? '');
    const [defaultPrompt, setDefaultPrompt] = useState('');
    const [hasCustomPrompt, setHasCustomPrompt] = useState(Boolean(storedPrompt));
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        let isMounted = true;
        setIsLoading(true);
        setError(null);
        fetchSummaryPrompt()
            .then((response) => {
                if (!isMounted) {
                    return;
                }
                const fetched = response?.prompt ?? '';
                setDefaultPrompt(fetched);
                if (!hasCustomPrompt) {
                    setPrompt(fetched);
                }
            })
            .catch((err) => {
                if (!isMounted) {
                    return;
                }
                setError(err);
            })
            .finally(() => {
                if (isMounted) {
                    setIsLoading(false);
                }
            });
        return () => {
            isMounted = false;
        };
    }, [hasCustomPrompt]);

    const savePrompt = useCallback((nextPrompt) => {
        const value = typeof nextPrompt === 'string' ? nextPrompt : '';
        setPrompt(value);
        setHasCustomPrompt(true);
        saveStoredPrompt(value);
    }, []);

    const clearCustomPrompt = useCallback(() => {
        setHasCustomPrompt(false);
        clearStoredPrompt();
        setPrompt(defaultPrompt);
    }, [defaultPrompt]);

    const commitPrompt = useCallback((nextPrompt) => {
        const value = typeof nextPrompt === 'string' ? nextPrompt : '';
        if (defaultPrompt && value === defaultPrompt) {
            clearCustomPrompt();
            return;
        }
        savePrompt(value);
    }, [clearCustomPrompt, defaultPrompt, savePrompt]);

    return {
        prompt,
        defaultPrompt,
        hasCustomPrompt,
        isLoading,
        error,
        savePrompt,
        clearCustomPrompt,
        commitPrompt
    };
};

export default usePromptStore;

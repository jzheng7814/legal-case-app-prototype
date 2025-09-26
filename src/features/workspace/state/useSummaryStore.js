import { useCallback, useMemo, useRef, useState } from 'react';
import { generateMockSummary, getMockSuggestions } from '../../../services/mockAi';

const useSummaryStore = () => {
    const [summaryText, setSummaryText] = useState('');
    const [isEditMode, setIsEditMode] = useState(false);
    const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
    const summaryRef = useRef(null);
    const suggestions = useMemo(() => getMockSuggestions(), []);

    const toggleEditMode = useCallback(() => {
        setIsEditMode((prev) => !prev);
    }, []);

    const generateAISummary = useCallback(async () => {
        setIsGeneratingSummary(true);
        setSummaryText('Generating AI summary...');
        try {
            const summary = await generateMockSummary();
            setSummaryText(summary);
        } catch (error) {
            console.error('Failed to generate summary', error);
            setSummaryText('Failed to generate AI summary. Please try again.');
        } finally {
            setIsGeneratingSummary(false);
        }
    }, []);

    const value = useMemo(() => ({
        summaryText,
        setSummaryText,
        isEditMode,
        setIsEditMode,
        toggleEditMode,
        isGeneratingSummary,
        generateAISummary,
        summaryRef,
        suggestions
    }), [generateAISummary, isEditMode, isGeneratingSummary, summaryText, suggestions, toggleEditMode]);

    return value;
};

export default useSummaryStore;

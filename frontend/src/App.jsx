import React, { useCallback, useMemo, useState } from 'react';
import HomeScreen from './features/home/HomeScreen';
import SummaryWorkspace from './features/workspace/SummaryWorkspace';

const App = () => {
    const [currentPage, setCurrentPage] = useState('home');
    const [caseId, setCaseId] = useState('');
    const [caseIdError, setCaseIdError] = useState('');
    const [activeCaseId, setActiveCaseId] = useState('');

    const handleProceed = useCallback(() => {
        const normalisedCaseId = (caseId || '').trim();
        if (!normalisedCaseId) {
            setCaseIdError('Please enter a valid case ID to continue.');
            return;
        }

        setCaseIdError('');
        setActiveCaseId(normalisedCaseId);
        setCurrentPage('summary');
    }, [caseId]);

    const handleExitWorkspace = useCallback((error) => {
        setCurrentPage('home');
        if (error) {
            setCaseIdError(error.message || 'Failed to load the requested case.');
        }
    }, []);

    const canProceed = useMemo(() => {
        return caseId.trim().length > 0;
    }, [caseId]);

    if (currentPage === 'home') {
        return (
            <HomeScreen
                caseId={caseId}
                caseIdError={caseIdError}
                onCaseIdChange={(value) => {
                    setCaseId(value);
                    if (caseIdError) {
                        setCaseIdError('');
                    }
                }}
                onProceed={handleProceed}
                canProceed={canProceed}
            />
        );
    }

    return (
        <SummaryWorkspace
            onExit={handleExitWorkspace}
            caseId={activeCaseId}
        />
    );
};

export default App;

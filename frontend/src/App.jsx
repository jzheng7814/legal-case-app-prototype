import React, { useCallback, useState } from 'react';
import HomeScreen from './features/home/HomeScreen';
import SummaryWorkspace from './features/workspace/SummaryWorkspace';

const App = () => {
    const [currentPage, setCurrentPage] = useState('home');
    const [caseId, setCaseId] = useState('');
    const [uploadedFiles, setUploadedFiles] = useState([]);

    const handleFileUpload = useCallback((event) => {
        setUploadedFiles(Array.from(event.target.files || []));
    }, []);

    const handleProceed = useCallback(() => {
        if (uploadedFiles.length > 0 || caseId.trim()) {
            setCurrentPage('summary');
        }
    }, [uploadedFiles.length, caseId]);

    const handleExitWorkspace = useCallback(() => {
        setCurrentPage('home');
    }, []);

    if (currentPage === 'home') {
        return (
            <HomeScreen
                caseId={caseId}
                onCaseIdChange={setCaseId}
                uploadedFiles={uploadedFiles}
                onFileUpload={handleFileUpload}
                onProceed={handleProceed}
                canProceed={uploadedFiles.length > 0 || caseId.trim().length > 0}
            />
        );
    }

    return <SummaryWorkspace onExit={handleExitWorkspace} />;
};

export default App;

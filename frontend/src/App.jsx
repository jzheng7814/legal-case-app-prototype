import React, { useCallback, useMemo, useState } from 'react';
import HomeScreen from './features/home/HomeScreen';
import SummaryWorkspace from './features/workspace/SummaryWorkspace';
import { DEFAULT_CASE_ID } from './services/documentService';

const App = () => {
    const [currentPage, setCurrentPage] = useState('home');
    const [caseId, setCaseId] = useState('');
    const [uploadedFiles, setUploadedFiles] = useState([]);
    const [uploadedDocuments, setUploadedDocuments] = useState([]);
    const [isProcessingUploads, setIsProcessingUploads] = useState(false);
    const [activeCaseId, setActiveCaseId] = useState(DEFAULT_CASE_ID);
    const [activeUploads, setActiveUploads] = useState([]);

    const handleFileUpload = useCallback(async (event) => {
        const files = Array.from(event.target.files || []);
        setUploadedFiles(files);
        if (files.length === 0) {
            setUploadedDocuments([]);
            return;
        }

        setIsProcessingUploads(true);
        try {
            const docs = await Promise.all(
                files.map(async (file, index) => {
                    const content = await file.text();
                    const extension = file.name.split('.').pop()?.toUpperCase() || 'FILE';
                    const uniqueId =
                        typeof crypto !== 'undefined' && crypto.randomUUID
                            ? crypto.randomUUID()
                            : `upload-${Date.now()}-${index}`;
                    return {
                        id: uniqueId,
                        name: file.name,
                        type: `Uploaded ${extension}`,
                        description: `Uploaded file ${file.name}`,
                        source: 'upload',
                        content
                    };
                })
            );
            setUploadedDocuments(docs);
        } catch (error) {
            console.error('Failed to read uploaded files', error);
            setUploadedDocuments([]);
        } finally {
            setIsProcessingUploads(false);
        }
    }, []);

    const handleProceed = useCallback(() => {
        const normalisedCaseId = (caseId || '').trim();
        const hasUploads = uploadedDocuments.length > 0;
        if (!hasUploads && !normalisedCaseId) {
            return;
        }

        setActiveCaseId(normalisedCaseId || DEFAULT_CASE_ID);
        setActiveUploads(hasUploads ? uploadedDocuments.map((doc) => ({ ...doc })) : []);
        setCurrentPage('summary');
    }, [caseId, uploadedDocuments]);

    const handleExitWorkspace = useCallback(() => {
        setCurrentPage('home');
    }, []);

    const canProceed = useMemo(() => {
        const hasCaseId = caseId.trim().length > 0;
        return !isProcessingUploads && (uploadedDocuments.length > 0 || hasCaseId);
    }, [caseId, isProcessingUploads, uploadedDocuments.length]);

    if (currentPage === 'home') {
        return (
            <HomeScreen
                caseId={caseId}
                onCaseIdChange={setCaseId}
                uploadedFiles={uploadedFiles}
                onFileUpload={handleFileUpload}
                onProceed={handleProceed}
                canProceed={canProceed}
                isProcessingUploads={isProcessingUploads}
            />
        );
    }

    return (
        <SummaryWorkspace
            onExit={handleExitWorkspace}
            caseId={activeCaseId}
            uploadedDocuments={activeUploads}
        />
    );
};

export default App;

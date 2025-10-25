import React from 'react';
import { Upload, FileText } from 'lucide-react';

const HomeScreen = ({
    caseId,
    onCaseIdChange,
    uploadedFiles,
    onFileUpload,
    onProceed,
    canProceed,
    isProcessingUploads = false
}) => (
    <div className="min-h-screen bg-gray-50 p-6">
        <div className="max-w-2xl mx-auto">
            <h1 className="text-3xl font-bold text-gray-900 mb-8 text-center">
                Legal Case Summarization
            </h1>

            <div className="bg-white rounded-lg shadow-md p-6 mb-6">
                <h2 className="text-xl font-semibold mb-4">Upload Case Documents</h2>

                <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 mb-4">
                    <div className="flex flex-col items-center text-center space-y-4">
                        <Upload className="h-12 w-12 text-gray-400" />
                        <div className="flex items-center justify-center gap-2 text-sm text-gray-600">
                            <label className="relative cursor-pointer bg-white rounded-md font-medium text-blue-600 hover:text-blue-500">
                                <span>Upload case files</span>
                                <input
                                    type="file"
                                    className="sr-only"
                                    multiple
                                    accept=".pdf,.doc,.docx,.txt"
                                    onChange={onFileUpload}
                                />
                            </label>
                            <span>or drag and drop</span>
                        </div>
                        <p className="text-xs text-gray-500">PDF, DOC, DOCX, TXT up to 10MB</p>
                        {isProcessingUploads && (
                            <p className="text-xs text-blue-600">Processing uploaded files...</p>
                        )}
                    </div>
                </div>

                {uploadedFiles.length > 0 && (
                    <div className="space-y-2 mb-4">
                        {uploadedFiles.map((file, index) => (
                            <div key={index} className="flex items-center p-3 bg-blue-50 rounded-md">
                                <FileText className="h-5 w-5 text-blue-600 mr-2" />
                                <span className="text-sm text-blue-900">{file.name}</span>
                            </div>
                        ))}
                    </div>
                )}

                <div className="mt-4">
                    <div className="text-center text-gray-500 mb-4">OR</div>
                    <input
                        type="text"
                        placeholder="Enter Case ID (e.g., -1)"
                        value={caseId}
                        onChange={(e) => onCaseIdChange(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                </div>
            </div>

            <button
                onClick={onProceed}
                disabled={!canProceed}
                className="w-full bg-blue-600 text-white py-3 px-4 rounded-md font-medium hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
                {isProcessingUploads ? 'Preparing documents...' : 'Proceed to Summary Editor'}
            </button>
        </div>
    </div>
);

export default HomeScreen;

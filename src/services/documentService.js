const DOCUMENT_LIST = [
    { id: 'main-case', name: 'Johnson v. XYZ Corporation', type: 'Case File', filename: 'main-case.txt' },
    { id: 'contract', name: 'Software Licensing Agreement', type: 'Contract', filename: 'contract.txt' },
    { id: 'correspondence', name: 'Email Correspondence', type: 'Communications', filename: 'correspondence.txt' }
];

export const getDefaultDocumentList = () => DOCUMENT_LIST;

export const loadDocumentsFromPublic = async () => {
    const loadedDocs = [];

    for (const doc of DOCUMENT_LIST) {
        try {
            const response = await fetch(`/documents/${doc.filename}`);
            if (response.ok) {
                const content = await response.text();
                loadedDocs.push({ ...doc, content });
            } else {
                console.warn(`Failed to load ${doc.filename}`);
                loadedDocs.push({
                    ...doc,
                    content: `Failed to load document: ${doc.filename}`
                });
            }
        } catch (error) {
            console.error(`Error loading ${doc.filename}:`, error);
            loadedDocs.push({
                ...doc,
                content: `Error loading document: ${doc.filename}`
            });
        }
    }

    return loadedDocs;
};

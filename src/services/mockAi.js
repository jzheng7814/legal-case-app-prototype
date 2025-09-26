const MOCK_SUMMARY_TEXT = `The plaintiff, Sarah Johnson, filed a breach of contract claim against XYZ Corporation on March 15, 2024. The dispute centers around a software licensing agreement signed in January 2024, where Johnson alleges that XYZ Corporation failed to deliver the promised software updates and technical support as outlined in Section 4.2 of the contract.

The defendant argues that delays were caused by unforeseen technical difficulties and that they provided alternative solutions that met the contractual obligations. Key evidence includes email correspondence between the parties from February 2024 and technical documentation showing attempted deliveries.

The court found that while XYZ Corporation did experience legitimate technical challenges, their failure to communicate these issues promptly and provide adequate alternative solutions constituted a material breach. Damages awarded to plaintiff totaled $45,000 in direct costs and lost business revenue.`;

const MOCK_SUGGESTIONS = [
    {
        id: 1,
        type: 'edit',
        originalText: 'unforeseen',
        suggestedText: 'unforeseeable',
        comment: 'Spelling correction for legal accuracy',
        position: { start: 445, end: 454 },
        sourceDocument: 'main-case'
    },
    {
        id: 2,
        type: 'addition',
        text: 'pursuant to the terms specified in the original agreement',
        comment: 'Add legal precision to contractual reference',
        insertAfter: 'Section 4.2 of the contract',
        position: { start: 320, end: 349 },
        sourceDocument: 'contract'
    },
    {
        id: 3,
        type: 'edit',
        originalText: 'Key evidence includes',
        suggestedText: 'The evidentiary record demonstrates',
        comment: 'More formal legal language',
        position: { start: 520, end: 540 },
        sourceDocument: 'main-case'
    }
];

export const getMockSuggestions = () => MOCK_SUGGESTIONS.map((suggestion) => ({ ...suggestion }));

export const generateMockSummary = (delayMs = 1500) =>
    new Promise((resolve) => {
        setTimeout(() => resolve(MOCK_SUMMARY_TEXT), delayMs);
    });

export const getMockSummaryText = () => MOCK_SUMMARY_TEXT;

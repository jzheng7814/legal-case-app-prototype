const DEFAULT_BASE_URL = 'http://localhost:8000';
const API_BASE_URL = (import.meta.env?.VITE_BACKEND_URL || DEFAULT_BASE_URL).replace(/\/$/, '');

const DEFAULT_HEADERS = {
    'Content-Type': 'application/json'
};

async function request(path, options = {}) {
    const response = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        headers: {
            ...DEFAULT_HEADERS,
            ...(options.headers || {})
        }
    });

    if (!response.ok) {
        const payload = await safeJson(response);
        const detail = payload?.detail || response.statusText;
        throw new Error(`API request failed (${response.status}): ${detail}`);
    }

    if (response.status === 204) {
        return null;
    }

    return response.json();
}

async function safeJson(response) {
    try {
        return await response.json();
    } catch {
        return null;
    }
}

export async function fetchDocuments(caseId) {
    return request(`/cases/${caseId}/documents`);
}

export async function startSummaryJob(caseId, body) {
    return request(`/cases/${caseId}/summary`, {
        method: 'POST',
        body: JSON.stringify(body)
    });
}

export async function getSummaryJob(caseId, jobId) {
    return request(`/cases/${caseId}/summary/${jobId}`);
}

export async function fetchSuggestions(caseId, body) {
    return request(`/cases/${caseId}/suggestions`, {
        method: 'POST',
        body: JSON.stringify(body)
    });
}

export async function fetchChecklist(caseId) {
    return request(`/cases/${caseId}/checklist`);
}

export async function fetchChecklistStatus(caseId) {
    return request(`/cases/${caseId}/checklist/status`);
}

export async function addChecklistItem(caseId, body) {
    return request(`/cases/${caseId}/checklist/items`, {
        method: 'POST',
        body: JSON.stringify(body)
    });
}

export async function deleteChecklistItem(caseId, valueId) {
    return request(`/cases/${caseId}/checklist/items/${encodeURIComponent(valueId)}`, {
        method: 'DELETE'
    });
}

export async function createChatSession() {
    return request('/chat/session', { method: 'POST' });
}

export async function getChatSession(sessionId) {
    return request(`/chat/session/${sessionId}`);
}

export async function sendChatMessage(sessionId, body) {
    return request(`/chat/session/${sessionId}/message`, {
        method: 'POST',
        body: JSON.stringify(body)
    });
}

export function getApiBaseUrl() {
    return API_BASE_URL;
}

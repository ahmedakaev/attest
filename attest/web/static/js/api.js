/**
 * Attest Web Dashboard — API & Core Utilities
 */

export function safeConfirm(msg) {
    if (typeof window !== 'undefined' && (window.navigator.webdriver || window.__ATTEST_AUTO_CONFIRM__)) {
        return true;
    }
    return window.confirm(msg);
}

export function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

export function formatDate(dateStr) {
    if (!dateStr) return '—';
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
        return dateStr;
    }
}

export async function apiFetch(url, options = {}) {
    try {
        const resp = await fetch(url, options);
        if (!resp.ok) {
            const errData = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(errData.detail || `HTTP Error ${resp.status}`);
        }
        return await resp.json();
    } catch (err) {
        console.error(`API Error on ${url}:`, err);
        throw err;
    }
}

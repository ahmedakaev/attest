/**
 * Attest Web Dashboard — Targets & Telemetry Grid Module
 */

import { apiFetch, escapeHtml, formatDate, safeConfirm } from './api.js';
import { t } from './i18n.js';
import { startTaskPolling } from './tasks.js';
import { loadRunDetails } from './inspector.js';
import { openEstimateModal, openHistoryModal, updateKnownTargets } from './modals.js';
import { updateStudioBaselineStatus } from './studio.js';

let currentTargets = [];

// DOM Elements — Stats
const statTotalTargets = document.getElementById('stat-total-targets');
const statActiveBaselines = document.getElementById('stat-active-baselines');
const statTotalAudits = document.getElementById('stat-total-audits');
const statPasses = document.getElementById('stat-passes');
const statFailures = document.getElementById('stat-failures');

// DOM Elements — Grid & Actions
const targetsGrid = document.getElementById('targets-grid');
const btnRefresh = document.getElementById('btn-refresh');
const btnAuditAll = document.getElementById('btn-audit-all');

export function initTargets() {
    if (btnRefresh) {
        btnRefresh.onclick = () => refreshDashboard();
    }

    if (btnAuditAll) {
        btnAuditAll.onclick = async () => {
            if (!safeConfirm('Run verification audits across all ready targets?')) return;
            try {
                const res = await apiFetch('/api/audit-all', { method: 'POST' });
                if (res.triggered && res.triggered.length > 0) {
                    startTaskPolling(res.triggered[0].task_id, `Auditing All (${res.count} targets queued)`, () => {
                        refreshDashboard();
                    });
                } else {
                    alert('No ready targets found with an active or linked baseline.');
                }
            } catch (err) {
                alert(`Audit all failed: ${err.message}`);
            }
        };
    }
}

export async function refreshDashboard() {
    try {
        const [stats, targets] = await Promise.all([
            apiFetch('/api/stats'),
            apiFetch('/api/targets')
        ]);
        renderStats(stats);
        renderTargets(targets);
    } catch (err) {
        console.error('Failed to load dashboard data:', err);
    }
}

export function renderStats(stats) {
    if (!stats) return;
    if (statTotalTargets) statTotalTargets.textContent = stats.total_targets ?? 0;
    if (statActiveBaselines) statActiveBaselines.textContent = stats.active_baselines ?? 0;
    if (statTotalAudits) statTotalAudits.textContent = stats.total_audits ?? 0;
    if (statPasses) statPasses.textContent = stats.passes ?? 0;
    if (statFailures) statFailures.textContent = stats.failures ?? 0;
}

export function renderTargets(targets) {
    currentTargets = targets || [];
    updateKnownTargets(currentTargets);
    updateStudioBaselineStatus();

    if (!targetsGrid) return;
    if (!targets || targets.length === 0) {
        targetsGrid.innerHTML = `
            <div class="loading-placeholder">
                <p style="font-size: 1.1rem; color: var(--text-primary); margin-bottom: 0.5rem;">${t('no_targets_configured')}</p>
                <p style="font-size: 0.875rem; color: var(--text-muted);">${t('click_add_target')}</p>
            </div>
        `;
        return;
    }

    targetsGrid.innerHTML = targets.map(tgt => {
        const hasBaseline = !!tgt.active_baseline;
        const latest = tgt.latest_run;
        let statusClass = 'pending';
        let statusLabel = t('card_status_none');

        if (latest) {
            if (latest.verdict === 'PASS') {
                statusClass = 'pass';
                statusLabel = t('card_status_pass');
            } else if (latest.verdict === 'WARN') {
                statusClass = 'warn';
                statusLabel = t('card_status_warn');
            } else if (latest.verdict === 'FAIL') {
                statusClass = 'fail';
                statusLabel = t('card_status_fail');
            }
        }

        return `
            <div class="target-card status-${statusClass}" data-target-id="${escapeHtml(tgt.id)}">
                <div class="target-card-top">
                    <div>
                        <div class="target-card-title">${escapeHtml(tgt.model)}</div>
                        <div class="target-model-pill" title="Target Endpoint ID: ${escapeHtml(tgt.id)}">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"></path>
                                <line x1="4" y1="22" x2="4" y2="15"></line>
                            </svg>
                            ${escapeHtml(tgt.id)}
                        </div>
                    </div>
                    <span class="target-status-pill ${statusClass} ${latest ? 'btn-action-view' : ''}" ${latest ? `data-run-id="${latest.id}" style="cursor:pointer;" title="Открыть подробный отчет с расшифровкой"` : ''}>${statusLabel}${latest ? ' ↗' : ''}</span>
                </div>

                <div class="target-meta-list">
                    <div class="target-meta-item">
                        <span class="target-meta-label">${t('lbl_base_url')}</span>
                        <span class="target-meta-val font-mono" title="${escapeHtml(tgt.base_url)}">${escapeHtml(tgt.base_url)}</span>
                    </div>
                    <div class="target-meta-item">
                        <span class="target-meta-label">${t('lbl_api_key')}</span>
                        <span class="target-meta-val font-mono">
                            ${tgt.has_key ? escapeHtml(tgt.key_preview) : `<span style="color:#ef4444">${t('key_not_set')}</span>`} 
                            <span style="font-size:0.75rem; color:var(--text-muted)">(${escapeHtml(tgt.key_source || 'none')})</span>
                        </span>
                    </div>
                    <div class="target-meta-item">
                        <span class="target-meta-label">${t('lbl_active_baseline')}</span>
                        <span class="target-meta-val">
                            ${hasBaseline 
                                ? (tgt.active_baseline.is_inherited
                                    ? `<span style="color:#10b981; font-weight:600;" title="${t('tooltip_linked', { id: escapeHtml(tgt.active_baseline.source_target_id) })}">${t('badge_linked')} (${escapeHtml(tgt.active_baseline.source_target_id)})</span>`
                                    : `<span style="color:#10b981; font-weight:600;">${t('badge_ready')} (${escapeHtml(tgt.active_baseline.battery_version)})</span>`)
                                : `<span style="color:#f59e0b; font-weight:600;" title="${t('tooltip_need_snapshot')}">${t('badge_need_snapshot')}</span>`}
                        </span>
                    </div>
                    ${latest ? `
                    <div class="target-meta-item">
                        <span class="target-meta-label">${t('lbl_last_audit')}</span>
                        <span class="target-meta-val" style="font-size: 0.8rem; color: var(--text-muted);">
                            ${formatDate(latest.finished_at || latest.started_at)}
                        </span>
                    </div>
                    ` : ''}
                </div>

                <div class="target-actions-bar" style="flex-wrap: wrap; gap: 0.4rem;">
                    ${hasBaseline ? `
                        <button class="btn btn-primary btn-sm btn-action-audit" data-id="${escapeHtml(tgt.id)}" title="${t('title_action_audit')}">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="5 3 19 12 5 21 5 3"></polygon>
                            </svg>
                            ${t('btn_card_audit')}
                        </button>
                        <button class="btn btn-ghost btn-sm btn-action-baseline" data-id="${escapeHtml(tgt.id)}" title="${t('title_action_recapture')}">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
                                <circle cx="12" cy="13" r="4"></circle>
                            </svg>
                        </button>
                    ` : `
                        <button class="btn btn-outline btn-sm btn-action-baseline" data-id="${escapeHtml(tgt.id)}" title="${t('title_action_capture_first')}">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
                                <circle cx="12" cy="13" r="4"></circle>
                            </svg>
                            ${t('btn_card_baseline')}
                        </button>
                    `}
                    ${latest ? `
                        <button class="btn btn-outline btn-sm btn-action-view" data-run-id="${latest.id}" title="Открыть подробные результаты теста с расшифровкой" style="font-weight: 600; border-color: rgba(56, 189, 248, 0.4); color: #38bdf8;">
                            📊 Отчет
                        </button>
                    ` : ''}
                    <button class="btn btn-ghost btn-sm btn-action-estimate" data-id="${escapeHtml(tgt.id)}" title="${t('title_action_estimate')}">
                        ${t('btn_card_budget')}
                    </button>
                    <button class="btn btn-ghost btn-sm btn-action-history" data-id="${escapeHtml(tgt.id)}" title="${t('title_action_history')}">
                        ${t('btn_card_history')}
                    </button>
                    <button class="btn btn-ghost btn-danger btn-sm btn-action-delete" data-id="${escapeHtml(tgt.id)}" title="${t('title_action_delete')}" style="margin-left: auto;">
                        ✕
                    </button>
                </div>
            </div>
        `;
    }).join('');

    attachCardEventHandlers();
}

function attachCardEventHandlers() {
    document.querySelectorAll('.btn-action-audit').forEach(btn => {
        btn.onclick = () => startAudit(btn.dataset.id);
    });
    document.querySelectorAll('.btn-action-baseline').forEach(btn => {
        btn.onclick = () => startBaseline(btn.dataset.id);
    });
    document.querySelectorAll('.btn-action-estimate').forEach(btn => {
        btn.onclick = () => openEstimateModal(btn.dataset.id);
    });
    document.querySelectorAll('.btn-action-history').forEach(btn => {
        btn.onclick = () => openHistoryModal(btn.dataset.id);
    });
    document.querySelectorAll('.btn-action-view').forEach(btn => {
        btn.onclick = () => loadRunDetails(btn.dataset.runId);
    });
    document.querySelectorAll('.btn-action-delete').forEach(btn => {
        btn.onclick = () => deleteTarget(btn.dataset.id);
    });
}

export async function startBaseline(targetId) {
    if (!safeConfirm(t('confirm_capture_endpoint_baseline', { target: targetId }))) {
        return;
    }
    try {
        const resp = await apiFetch(`/api/targets/${encodeURIComponent(targetId)}/baseline`, { method: 'POST' });
        startTaskPolling(resp.task_id, `Capturing Baseline for '${targetId}'`, () => {
            refreshDashboard();
        });
    } catch (err) {
        alert(`Failed to start baseline capture: ${err.message}`);
    }
}

export async function startAudit(targetId) {
    try {
        const resp = await apiFetch(`/api/targets/${encodeURIComponent(targetId)}/run`, { method: 'POST' });
        startTaskPolling(resp.task_id, `Auditing Endpoint '${targetId}'`, (task) => {
            refreshDashboard();
            if (task?.result?.run_id) {
                loadRunDetails(task.result.run_id);
            }
        });
    } catch (err) {
        alert(`Failed to start audit: ${err.message}`);
    }
}

export async function deleteTarget(targetId) {
    if (!safeConfirm(t('confirm_delete_target', { id: targetId }))) {
        return;
    }
    try {
        await apiFetch(`/api/targets/${encodeURIComponent(targetId)}`, { method: 'DELETE' });
        await refreshDashboard();
    } catch (err) {
        alert(`Failed to delete target: ${err.message}`);
    }
}

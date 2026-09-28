/**
 * Attest Web Dashboard — Modals Management Module
 * (Baselines Archive, Monitoring Schedules, Add Target, Cost Estimate, History)
 */

import { apiFetch, escapeHtml, formatDate, safeConfirm } from './api.js';
import { t } from './i18n.js';
import { startTaskPolling } from './tasks.js';
import { loadRunDetails } from './inspector.js';
import { 
    loadModelBaselines, 
    onStudioBaselineChanged, 
    pinBaseline, 
    updateCandidateModelCall, 
    updateStudioFooter 
} from './studio.js';

let onTargetAddedCallback = null;
let currentTargetsList = [];

// DOM Elements — Baselines Archive Modal
const btnOpenBaselinesModal = document.getElementById('btn-open-baselines-modal');
const modalBaselines = document.getElementById('modal-baselines');
const baselinesTbody = document.getElementById('baselines-tbody');
const lblBaselinesCount = document.getElementById('lbl-baselines-count');
const btnCloseBaselinesModal = document.getElementById('btn-close-baselines-modal');
const btnCloseBaselinesModalFooter = document.getElementById('btn-close-baselines-modal-footer');

// DOM Elements — Schedules Modal
const btnOpenSchedulesModal = document.getElementById('btn-open-schedules-modal');
const modalSchedules = document.getElementById('modal-schedules');
const formAddSchedule = document.getElementById('form-add-schedule');
const selectSchedTarget = document.getElementById('sched-target');
const selectSchedInterval = document.getElementById('sched-interval');
const selectSchedBattery = document.getElementById('sched-battery');
const schedulesTbody = document.getElementById('schedules-tbody');
const btnCloseSchedulesModal = document.getElementById('btn-close-schedules-modal');
const btnCloseSchedulesModalFooter = document.getElementById('btn-close-schedules-modal-footer');

// DOM Elements — Estimate Modal
const modalEstimate = document.getElementById('modal-estimate');
const estimateModalTitle = document.getElementById('estimate-modal-title');
const estimateModalBody = document.getElementById('estimate-modal-body');
const btnCloseEstimateModal = document.getElementById('btn-close-estimate-modal');
const btnOkEstimate = document.getElementById('btn-ok-estimate');

// DOM Elements — History Modal
const modalHistory = document.getElementById('modal-history');
const historyModalTitle = document.getElementById('history-modal-title');
const historyTbody = document.getElementById('history-tbody');
const historyCharts = document.getElementById('history-charts');
const btnCloseHistoryModal = document.getElementById('btn-close-history-modal');
const btnOkHistory = document.getElementById('btn-ok-history');

export function initModals({ onTargetAdded } = {}) {
    onTargetAddedCallback = onTargetAdded;

    // Baselines Archive
    if (btnOpenBaselinesModal) btnOpenBaselinesModal.onclick = () => openBaselinesArchiveModal();
    if (btnCloseBaselinesModal) btnCloseBaselinesModal.onclick = () => modalBaselines?.classList.add('hidden');
    if (btnCloseBaselinesModalFooter) btnCloseBaselinesModalFooter.onclick = () => modalBaselines?.classList.add('hidden');

    // Schedules
    if (btnOpenSchedulesModal) btnOpenSchedulesModal.onclick = () => openSchedulesModal();
    if (btnCloseSchedulesModal) btnCloseSchedulesModal.onclick = () => modalSchedules?.classList.add('hidden');
    if (btnCloseSchedulesModalFooter) btnCloseSchedulesModalFooter.onclick = () => modalSchedules?.classList.add('hidden');

    if (formAddSchedule) {
        formAddSchedule.onsubmit = async (e) => {
            e.preventDefault();
            const target_id = selectSchedTarget.value;
            const interval_hours = parseInt(selectSchedInterval.value, 10);
            const battery = selectSchedBattery.value;
            try {
                await apiFetch('/api/schedules', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target_id, interval_hours, battery, enabled: true })
                });
                const updated = await apiFetch('/api/schedules');
                renderSchedulesTable(updated);
            } catch (err) {
                alert(`Failed to save schedule: ${err.message}`);
            }
        };
    }

    // Estimate
    if (btnCloseEstimateModal) btnCloseEstimateModal.onclick = () => modalEstimate?.classList.add('hidden');
    if (btnOkEstimate) btnOkEstimate.onclick = () => modalEstimate?.classList.add('hidden');

    // History
    if (btnCloseHistoryModal) btnCloseHistoryModal.onclick = () => modalHistory?.classList.add('hidden');
    if (btnOkHistory) btnOkHistory.onclick = () => modalHistory?.classList.add('hidden');
}

export function updateKnownTargets(targets) {
    currentTargetsList = targets || [];
}

export async function openBaselinesArchiveModal() {
    if (!modalBaselines) return;
    try {
        const baselines = await apiFetch('/api/baselines');
        renderBaselinesArchiveTable(baselines);
        modalBaselines.classList.remove('hidden');
    } catch (err) {
        alert(`Failed to load baselines archive: ${err.message}`);
    }
}

export function renderBaselinesArchiveTable(baselines) {
    if (!baselinesTbody) return;
    if (lblBaselinesCount) {
        lblBaselinesCount.textContent = t('snapshots_stored', { count: baselines.length });
    }

    if (!baselines || baselines.length === 0) {
        baselinesTbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding:2.5rem;">${t('no_baselines_captured')}</td></tr>`;
        return;
    }

    baselinesTbody.innerHTML = baselines.map(b => {
        const statusClass = b.status === 'active' ? 'pass' : 'archived';
        const statusLabel = b.status === 'active' ? t('status_active') : t('status_superseded');
        const qLabel = t('queries_count');
        const btnDriftText = t('btn_check_drift');
        const btnDriftTooltip = t('tooltip_check_drift');
        return `
            <tr>
                <td><strong>#${b.id}</strong></td>
                <td>
                    <strong>${escapeHtml(b.model)}</strong>
                    <div style="font-size:0.75rem; color:var(--text-muted);">${escapeHtml(b.target_id)}</div>
                </td>
                <td>${formatDate(b.captured_at)}</td>
                <td>
                    <span class="font-mono" style="color:var(--text-primary); font-weight:600;">${b.samples_count}</span> ${qLabel}
                    <span class="badge badge-neutral" style="font-size:0.7rem; margin-left:0.25rem;">${escapeHtml(b.battery_version)}</span>
                </td>
                <td><span class="target-status-pill ${statusClass}">${statusLabel}</span></td>
                <td style="font-size:0.8rem; color:var(--text-muted); max-width:220px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${escapeHtml(b.notes || '')}">
                    ${escapeHtml(b.notes || '—')}
                </td>
                <td>
                    <button class="btn btn-outline btn-sm btn-action-drift" data-id="${b.id}" data-model="${escapeHtml(b.model)}" data-target="${escapeHtml(b.target_id)}" data-url="${escapeHtml(b.base_url || '')}" data-battery="${escapeHtml(b.battery_version || '')}" title="${escapeHtml(btnDriftTooltip)}">
                        ${btnDriftText}
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    document.querySelectorAll('.btn-action-drift').forEach(btn => {
        btn.onclick = () => selectBaselineForDrift(btn.dataset.id, btn.dataset.model, btn.dataset.target, btn.dataset.url, btn.dataset.battery);
    });
}

export async function selectBaselineForDrift(baselineId, model, targetId, baseUrl, batteryVersion) {
    if (modalBaselines) modalBaselines.classList.add('hidden');

    // Show the chosen reference in the visible fields and keep the choice pinned:
    // before, only hidden selects changed and the audit fell back to the active
    // baseline of whatever model the visible field still held
    pinBaseline(baselineId, batteryVersion);
    const refModelCall = document.getElementById('studio-ref-model-call');
    const refUrl = document.getElementById('studio-ref-url');
    if (refModelCall) {
        refModelCall.value = model;
        refModelCall.dispatchEvent(new Event('input'));
    }
    if (refUrl && baseUrl) {
        refUrl.value = baseUrl;
        refUrl.dispatchEvent(new Event('input'));
    }

    const studioRefModel = document.getElementById('studio-ref-model');
    const studioRefBaseline = document.getElementById('studio-ref-baseline');
    const studioCandidateUrl = document.getElementById('studio-candidate-url');
    const studioCandidateModelCall = document.getElementById('studio-candidate-model-call');

    // Switch to Saved tab in Channel A
    const tabChannelASaved = document.getElementById('tab-channel-a-saved');
    if (tabChannelASaved) tabChannelASaved.click();

    if (studioRefModel) {
        let opt = Array.from(studioRefModel.options).find(o => o.value === model);
        if (!opt) {
            opt = document.createElement('option');
            opt.value = model;
            opt.textContent = `${model}`;
            studioRefModel.insertBefore(opt, studioRefModel.lastElementChild);
        }
        studioRefModel.value = model;
        await loadModelBaselines(model);
    }

    if (studioRefBaseline) {
        studioRefBaseline.value = String(baselineId);
        onStudioBaselineChanged();
    }

    const matchingTarget = currentTargetsList.find(t => t.id === targetId);
    if (matchingTarget && studioCandidateUrl) {
        studioCandidateUrl.value = matchingTarget.base_url;
        if (studioCandidateModelCall) studioCandidateModelCall.value = matchingTarget.model;
    } else if (baseUrl && studioCandidateUrl) {
        studioCandidateUrl.value = baseUrl;
    }

    updateCandidateModelCall();
    updateStudioFooter();

    const studioSec = document.getElementById('verification-studio');
    if (studioSec) {
        studioSec.scrollIntoView({ behavior: 'smooth' });
    }
}

export async function openSchedulesModal() {
    if (!modalSchedules) return;
    try {
        const [schedules, targets] = await Promise.all([
            apiFetch('/api/schedules'),
            apiFetch('/api/targets')
        ]);
        currentTargetsList = targets || [];

        if (selectSchedTarget) {
            selectSchedTarget.innerHTML = currentTargetsList.map(t => 
                `<option value="${escapeHtml(t.id)}">${escapeHtml(t.id)} (${escapeHtml(t.model)})</option>`
            ).join('');
        }
        renderSchedulesTable(schedules);
        modalSchedules.classList.remove('hidden');
    } catch (err) {
        alert(`Failed to load schedules: ${err.message}`);
    }
}

export function renderSchedulesTable(schedules) {
    if (!schedulesTbody) return;
    if (!schedules || schedules.length === 0) {
        schedulesTbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--text-muted); padding:2.5rem;">${t('no_schedules_configured')}</td></tr>`;
        return;
    }

    schedulesTbody.innerHTML = schedules.map(s => {
        const statusBadge = s.enabled 
            ? `<span class="target-status-pill pass">${t('status_active')}</span>` 
            : `<span class="target-status-pill superseded">${t('status_paused')}</span>`;
        const battBadge = /^level[1-4]$/.test(s.battery || '')
            ? `<span class="badge badge-neutral" style="font-size:0.7rem; font-weight:600;">${escapeHtml(t('batt_' + s.battery))}</span>`
            : s.battery === 'iris'
            ? '<span class="badge badge-neutral" style="font-size:0.7rem;">IRIS</span>'
            : s.battery === 'quick' 
            ? `<span class="badge badge-neutral" style="font-size:0.7rem;">${t('badge_quick_short')}</span>` 
            : s.battery === 'anti_spoof'
            ? '<span class="badge badge-neutral" style="font-size:0.7rem;">Anti-Spoof</span>'
            : s.battery === 'reasoning'
            ? '<span class="badge badge-neutral" style="font-size:0.7rem;">Reasoning</span>'
            : s.battery === 'frontier_probe'
            ? '<span class="badge badge-neutral" style="font-size:0.7rem; font-weight:600;">Frontier</span>'
            : `<span class="badge badge-neutral" style="font-size:0.7rem;">${t('badge_deep_short')}</span>`;
        const intervalText = t('every_hours', { hours: s.interval_hours });
        const runBtnTitle = t('title_sched_run_now');
        const delBtnTitle = t('title_sched_delete');
        const runBtnText = t('btn_sched_run');
        return `
            <tr>
                <td><strong>${escapeHtml(s.target_id)}</strong></td>
                <td class="font-mono" style="font-size:0.85rem;">${escapeHtml(s.target_model)}</td>
                <td>${intervalText}</td>
                <td>${battBadge} ${statusBadge}</td>
                <td style="font-size:0.8rem;">${formatDate(s.next_run_at)}</td>
                <td style="font-size:0.8rem; color:var(--text-muted);">${formatDate(s.last_run_at)}</td>
                <td>
                    <div style="display:flex; gap:0.4rem;">
                        <button class="btn btn-outline btn-sm btn-trigger-sched" data-id="${s.id}" data-target="${escapeHtml(s.target_id)}" title="${runBtnTitle}">
                            ${runBtnText}
                        </button>
                        <button class="btn btn-ghost btn-sm btn-delete-sched" data-id="${s.id}" title="${delBtnTitle}" style="color:#ef4444;">
                            ✕
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    document.querySelectorAll('.btn-trigger-sched').forEach(btn => {
        btn.onclick = async () => {
            const sId = btn.dataset.id;
            const tgtId = btn.dataset.target;
            try {
                const res = await apiFetch(`/api/schedules/${sId}/trigger`, { method: 'POST' });
                modalSchedules.classList.add('hidden');
                startTaskPolling(res.task_id, `Scheduled Drift Audit: ${tgtId}`);
            } catch (err) {
                alert(`Failed to trigger schedule: ${err.message}`);
            }
        };
    });

    document.querySelectorAll('.btn-delete-sched').forEach(btn => {
        btn.onclick = async () => {
            const sId = btn.dataset.id;
            if (!safeConfirm(t('confirm_delete_schedule'))) return;
            try {
                await apiFetch(`/api/schedules/${sId}`, { method: 'DELETE' });
                const updated = await apiFetch('/api/schedules');
                renderSchedulesTable(updated);
            } catch (err) {
                alert(`Failed to delete schedule: ${err.message}`);
            }
        };
    });
}

export async function openEstimateModal(targetId, selectedBattery = 'level1') {
    try {
        const est = await apiFetch(`/api/targets/${encodeURIComponent(targetId)}/estimate?battery=${encodeURIComponent(selectedBattery)}`);
        if (estimateModalTitle) {
            estimateModalTitle.textContent = t('modal_estimate_title_target', { target: targetId, battery: est.battery_version });
        }
        if (estimateModalBody) {
            estimateModalBody.innerHTML = `
                <div class="estimate-stat-grid">
                    <div class="est-box">
                        <div class="est-box-lbl">${t('lbl_est_probes')}</div>
                        <div class="est-box-val">${est.total_prompts}</div>
                    </div>
                    <div class="est-box">
                        <div class="est-box-lbl">${t('lbl_est_total_queries')}</div>
                        <div class="est-box-val">${est.total_requests}</div>
                    </div>
                    <div class="est-box">
                        <div class="est-box-lbl">${t('lbl_est_tokens')}</div>
                        <div class="est-box-val">${(est.est_total_tokens || 0).toLocaleString()}</div>
                    </div>
                </div>
                <div style="background: var(--bg-hover); border: 1px solid var(--border-color); border-radius: 8px; padding: 1rem; font-size: 0.875rem;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                        <span>${t('lbl_est_cost_rates')}</span>
                        <strong style="color: #10b981; font-size: 1.1rem;">~$${est.est_cost_usd} USD</strong>
                    </div>
                    <p style="color: var(--text-muted); font-size: 0.775rem; margin: 0;">
                        ${t('desc_est_probes')}
                    </p>
                </div>
            `;
        }
        modalEstimate?.classList.remove('hidden');
    } catch (err) {
        alert(t('err_failed_estimate', { error: err.message }));
    }
}

function historySparkline(history, key, label, fmt = v => Number(v).toFixed(0)) {
    const pts = history.map((h, i) => [i, h[key]]).filter(([, v]) => v !== null && v !== undefined);
    if (pts.length < 2) return '';
    const w = 220, h = 48, pad = 4;
    const vals = pts.map(([, v]) => v);
    const min = Math.min(...vals), max = Math.max(...vals);
    const span = max - min || 1;
    const x = i => pad + (i / Math.max(history.length - 1, 1)) * (w - 2 * pad);
    const y = v => h - pad - ((v - min) / span) * (h - 2 * pad);
    const line = pts.map(([i, v]) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
    const [li, lv] = pts[pts.length - 1];
    return `
        <div class="history-chart">
            <div class="history-chart-label">${escapeHtml(label)}: <strong>${escapeHtml(fmt(lv))}</strong>
                <span class="history-chart-range">${escapeHtml(fmt(min))} – ${escapeHtml(fmt(max))}</span></div>
            <svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none" role="img" aria-label="${escapeHtml(label)}">
                <polyline points="${line}" fill="none" stroke="var(--accent-brand)" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
                <circle cx="${x(li).toFixed(1)}" cy="${y(lv).toFixed(1)}" r="2.5" fill="var(--accent-brand)"/>
            </svg>
        </div>`;
}

export async function openHistoryModal(targetId) {
    try {
        // Oldest first: charts read left to right, the table shows newest on top
        const history = await apiFetch(`/api/targets/${encodeURIComponent(targetId)}/history`);
        const runs = [...history].reverse();
        if (historyModalTitle) {
            historyModalTitle.textContent = t('modal_history_title_target', { target: targetId });
        }
        if (historyCharts) {
            historyCharts.innerHTML = history.length >= 2
                ? [
                    historySparkline(history, 'ttft_ms', t('th_hist_ttft')),
                    historySparkline(history, 'tps', t('th_hist_tps')),
                    historySparkline(history, 'overcharge', t('th_hist_overcharge'), v => `${(v * 100).toFixed(0)}%`),
                ].join('')
                : '';
        }
        const num = (v, digits = 0) => (v === null || v === undefined ? '—' : Number(v).toFixed(digits));
        const pct = v => (v === null || v === undefined ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}%`);
        if (historyTbody) {
            if (!runs || runs.length === 0) {
                historyTbody.innerHTML = `<tr><td colspan="10" style="text-align:center; color:var(--text-muted); padding:2rem;">${t('no_history_runs')}</td></tr>`;
            } else {
                historyTbody.innerHTML = runs.map(r => `
                    <tr>
                        <td>#${r.run_id}</td>
                        <td>${formatDate(r.started_at)}</td>
                        <td>${escapeHtml(r.baseline_id || '—')}</td>
                        <td><span class="target-status-pill ${r.verdict.toLowerCase()}">${escapeHtml(r.verdict)}</span></td>
                        <td>${num(r.ttft_ms)}</td>
                        <td title="${r.tps_decode_only ? '' : escapeHtml(t('hist_tps_end_to_end'))}">${num(r.tps, 1)}${r.tps_decode_only ? '' : '*'}</td>
                        <td>${num(r.latency_ms)}</td>
                        <td>${pct(r.overcharge)}</td>
                        <td>${r.iris_dilution === null || r.iris_dilution === undefined ? '—' : `${(r.iris_dilution * 100).toFixed(0)}%`}</td>
                        <td>
                            <button class="btn btn-outline btn-sm btn-inspect-history" data-run-id="${r.run_id}">
                                ${t('btn_inspect_run')}
                            </button>
                        </td>
                    </tr>
                `).join('');

                historyTbody.querySelectorAll('.btn-inspect-history').forEach(btn => {
                    btn.onclick = () => {
                        modalHistory?.classList.add('hidden');
                        loadRunDetails(btn.dataset.runId);
                    };
                });
            }
        }
        modalHistory?.classList.remove('hidden');
    } catch (err) {
        alert(t('err_failed_history', { error: err.message }));
    }
}

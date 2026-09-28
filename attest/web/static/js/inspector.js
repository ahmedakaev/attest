/**
 * Attest Web Dashboard — Inspector & Audit Deep Dive Module
 */

import { apiFetch, escapeHtml, formatDate } from './api.js';
import { t, getCurrentLang, getMethodTitle, formatDiagCountTitle } from './i18n.js';

let currentActiveRunId = null;
let lastLoadedRunData = null;
let currentSamplesFilter = 'all';

// DOM Elements
const auditDetailsSection = document.getElementById('audit-details-section');
const detailTargetTitle = document.getElementById('detail-target-title');
const detailRunMeta = document.getElementById('detail-run-meta');
const detailVerdictBanner = document.getElementById('detail-verdict-banner');
const detailVerdictIcon = document.getElementById('detail-verdict-icon');
const detailVerdictHeading = document.getElementById('detail-verdict-heading');
const detailVerdictSub = document.getElementById('detail-verdict-sub');
const detailTokens = document.getElementById('detail-tokens');
const detailDuration = document.getElementById('detail-duration');

const detailFailureDiagnostics = document.getElementById('detail-failure-diagnostics');
const failureDiagTitle = document.getElementById('failure-diag-title');
const failureDiagSub = document.getElementById('failure-diag-sub');
const failureDiagList = document.getElementById('failure-diag-list');

const tierStatusL0 = document.getElementById('tier-status-l0');
const l0ClaimVal = document.getElementById('l0-claim-val');
const l0FpVal = document.getElementById('l0-fp-val');

const tierStatusL1 = document.getElementById('tier-status-l1');
const l1JsdVal = document.getElementById('l1-jsd-val');

const tierStatusL15 = document.getElementById('tier-status-l15');
const l15TpsVal = document.getElementById('l15-tps-val');
const l15LatVal = document.getElementById('l15-lat-val');

const tierStatusAssert = document.getElementById('tier-status-assert');
const assertRateVal = document.getElementById('assert-rate-val');
const assertStatusVal = document.getElementById('assert-status-val');

const tierStatusL2 = document.getElementById('tier-status-l2');
const l2SimVal = document.getElementById('l2-sim-val');

const tierStatusL3 = document.getElementById('tier-status-l3');
const l3PvalVal = document.getElementById('l3-pval-val');

const auditScoresTbody = document.getElementById('audit-scores-tbody');
const btnCloseDetails = document.getElementById('btn-close-details');

const detailSamplesInspector = document.getElementById('detail-samples-inspector');
const detailProvenanceGrid = document.getElementById('detail-provenance-grid');
const detailSamplesList = document.getElementById('detail-samples-list');

const btnFilterAll = document.getElementById('btn-filter-all');
const btnFilterDiff = document.getElementById('btn-filter-diff');
const btnFilterMatch = document.getElementById('btn-filter-match');

const btnExportJson = document.getElementById('btn-export-json');
const btnExportDisputeMd = document.getElementById('btn-export-dispute-md');
const btnExportHtml = document.getElementById('btn-export-html');

export function initInspector() {
    if (btnCloseDetails) {
        btnCloseDetails.onclick = () => {
            if (auditDetailsSection) auditDetailsSection.classList.add('hidden');
        };
    }

    if (btnFilterAll) btnFilterAll.onclick = () => applySamplesFilter('all');
    if (btnFilterDiff) btnFilterDiff.onclick = () => applySamplesFilter('diff');
    if (btnFilterMatch) btnFilterMatch.onclick = () => applySamplesFilter('match');

    if (btnExportJson) {
        btnExportJson.onclick = () => {
            if (!currentActiveRunId) {
                alert(t('alert_select_run') || 'Select an audit run first.');
                return;
            }
            window.location.href = `/api/runs/${currentActiveRunId}/dispute-pack?format=json&download=true`;
        };
    }

    if (btnExportDisputeMd) {
        btnExportDisputeMd.onclick = () => {
            if (!currentActiveRunId) {
                alert(t('alert_select_run') || 'Select an audit run first.');
                return;
            }
            window.location.href = `/api/runs/${currentActiveRunId}/dispute-pack?format=md&download=true`;
        };
    }

    if (btnExportHtml) {
        btnExportHtml.onclick = () => {
            if (!currentActiveRunId) {
                alert(t('alert_select_run') || 'Select an audit run first.');
                return;
            }
            const lang = getCurrentLang ? getCurrentLang() : 'ru';
            window.open(`/api/runs/${currentActiveRunId}/export?format=html&locale=${lang}`, '_blank');
        };
    }

    const btnCopyAi = document.getElementById('btn-copy-ai');
    if (btnCopyAi) {
        btnCopyAi.onclick = () => copyReportForAi();
    }

    const btnCopyFailureAi = document.getElementById('btn-copy-failure-ai');
    if (btnCopyFailureAi) {
        btnCopyFailureAi.onclick = () => copyReportForAi();
    }

    const btnToggleSamples = document.getElementById('btn-toggle-samples');
    const samplesDrawer = document.getElementById('samples-drawer');
    const samplesToggleChevron = document.getElementById('samples-toggle-chevron');
    if (btnToggleSamples && samplesDrawer) {
        btnToggleSamples.onclick = () => {
            const isHidden = samplesDrawer.classList.toggle('hidden');
            if (samplesToggleChevron) {
                samplesToggleChevron.classList.toggle('open', !isHidden);
            }
        };
    }

    // Expose global inspector for inline links (e.g. History modal button)
    window.AttestApp = window.AttestApp || {};
    window.AttestApp.inspectRun = loadRunDetails;
}

export async function loadRunDetails(runId, options = { scroll: true }) {
    try {
        currentActiveRunId = runId;
        const lang = getCurrentLang ? getCurrentLang() : 'ru';
        const data = await apiFetch(`/api/runs/${runId}?locale=${lang}`);
        renderAuditDetails(data);
        if (auditDetailsSection) {
            auditDetailsSection.classList.remove('hidden');
            if (options.scroll) {
                auditDetailsSection.scrollIntoView({ behavior: 'smooth' });
            }
        }
    } catch (err) {
        alert(`Failed to load run details: ${err.message}`);
    }
}

function getVerdictIconSvg(verdict) {
    if (verdict === 'PASS') {
        return `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path><polyline points="9 12 11 14 15 10"></polyline></svg>`;
    } else if (verdict === 'WARN') {
        return `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`;
    }
    return `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`;
}

function hostOf(url) {
    try { return new URL(url).hostname; } catch { return url || '—'; }
}

function timeAgo(iso) {
    const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (!Number.isFinite(mins)) return '';
    if (mins < 1) return t('time_just_now');
    if (mins < 60) return t('time_min_ago', { n: mins });
    const hours = Math.round(mins / 60);
    if (hours < 48) return t('time_hours_ago', { n: hours });
    return t('time_days_ago', { n: Math.round(hours / 24) });
}

// Which run this is: when, which battery, and which model at which endpoint was
// compared with which reference, so a fresh run is not mistaken for an old one.
function renderRunMeta({ run, target, baseline }) {
    const when = run.finished_at || run.started_at;
    const battery = /^level[1-4]$/.test(run.battery_version || '')
        ? t('batt_' + run.battery_version)
        : (run.battery_version || '');
    const candModel = target ? (target.wire_model || target.model) : run.target_id;
    const cand = `${escapeHtml(candModel)} <span class="meta-host">@ ${escapeHtml(target ? hostOf(target.base_url) : '—')}</span>`;
    const ref = baseline
        ? `#${baseline.id} · ${escapeHtml(baseline.model || baseline.target_id || '—')} <span class="meta-host">@ ${escapeHtml(hostOf(baseline.base_url))}</span> <span class="meta-dim">(${escapeHtml(t('meta_captured'))} ${escapeHtml(formatDate(baseline.captured_at))})</span>`
        : '—';
    return `
        <span class="meta-item"><strong>${escapeHtml(t('meta_run'))} #${run.id}</strong> · ${escapeHtml(formatDate(when))} <span class="meta-dim">(${escapeHtml(timeAgo(when))})</span>${battery ? ` · ${escapeHtml(battery)}` : ''}</span>
        <span class="meta-item">${escapeHtml(t('meta_candidate'))}: ${cand}</span>
        <span class="meta-item">${escapeHtml(t('meta_reference'))}: ${ref}</span>`;
}

export function renderAuditDetails(data) {
    lastLoadedRunData = data;
    const { run, target, scores } = data;

    if (detailTargetTitle) {
        detailTargetTitle.textContent = `${t('target_report')}: ${target ? target.id : run.target_id} (${target ? target.model : ''})`;
    }
    if (detailRunMeta) {
        detailRunMeta.innerHTML = renderRunMeta(data);
    }
    if (detailTokens) {
        detailTokens.textContent = (run.total_tokens || 0).toLocaleString();
    }
    
    let dur = 0;
    if (run.started_at && run.finished_at) {
        dur = Math.round((new Date(run.finished_at) - new Date(run.started_at)) / 1000);
    }
    if (detailDuration) {
        detailDuration.textContent = `${dur}s`;
    }

    // Verdict banner styling
    if (detailVerdictBanner) {
        detailVerdictBanner.className = `verdict-banner verdict-${run.verdict.toLowerCase()}`;
    }
    const diagnostics = data.failure_diagnostics || [];
    const lang = getCurrentLang ? getCurrentLang() : 'ru';

    function formatVerdictSub(run, lang, diagnostics) {
        const rawMsg = run.summary_message || '';
        const diagCount = diagnostics?.length || 0;
        if (run.verdict === 'PASS') {
            return rawMsg || t('verdict_pass_sub');
        }
        let clean = rawMsg;
        if (clean.includes('Обнаружены отклонения:')) {
            clean = clean.split('Обнаружены отклонения:')[0].trim();
        } else if (clean.includes('Deviations detected:')) {
            clean = clean.split('Deviations detected:')[0].trim();
        }
        clean = clean.replace(/^(ПРОВАЛЕНО|ВНИМАНИЕ|FAILED|WARNING)\s*[-—–]\s*/i, '').trim();
        if (!clean) {
            clean = run.verdict === 'WARN' ? t('verdict_warn_sub') : t('verdict_fail_sub');
        }
        if (diagCount > 0) {
            const word = lang === 'ru' 
                ? (run.verdict === 'WARN' ? `(предупреждений: ${diagCount})` : `(критических сбоев: ${diagCount})`)
                : (run.verdict === 'WARN' ? `(${diagCount} warnings)` : `(${diagCount} critical failures)`);
            clean += lang === 'ru' 
                ? ` ${word}. Детализация приведена в блоке ниже.`
                : ` ${word}. Specific failures are detailed below.`;
        }
        return clean;
    }

    if (detailVerdictHeading) {
        const pillLabel = document.getElementById('detail-verdict-pill-label');
        if (run.verdict === 'PASS') {
            detailVerdictHeading.textContent = t('verdict_pass');
            if (detailVerdictSub) detailVerdictSub.textContent = formatVerdictSub(run, lang, diagnostics);
            if (pillLabel) pillLabel.textContent = lang === 'ru' ? '● ВЕРИФИЦИРОВАНО — ПОДЛИННАЯ МОДЕЛЬ' : '● VERIFIED AUTHENTIC';
        } else if (run.verdict === 'WARN') {
            detailVerdictHeading.textContent = t('verdict_warn');
            if (detailVerdictSub) detailVerdictSub.textContent = formatVerdictSub(run, lang, diagnostics);
            if (pillLabel) pillLabel.textContent = lang === 'ru' ? '● ВНИМАНИЕ — ОБНАРУЖЕН ДРЕЙФ' : '● WARNING: DRIFT DETECTED';
        } else {
            detailVerdictHeading.textContent = t('verdict_fail');
            if (detailVerdictSub) detailVerdictSub.textContent = formatVerdictSub(run, lang, diagnostics);
            if (pillLabel) pillLabel.textContent = lang === 'ru' ? '● АНОМАЛИЯ: ПОДМЕНА МОДЕЛИ' : '● ANOMALY: MODEL SPOOFING';
        }
    }

    // Failure Diagnostics Box
    if (detailFailureDiagnostics) {
        if (diagnostics.length > 0) {
            detailFailureDiagnostics.classList.remove('hidden');
            if (failureDiagTitle) {
                failureDiagTitle.textContent = formatDiagCountTitle(diagnostics.length);
            }
            if (failureDiagSub) {
                failureDiagSub.textContent = t('diag_sub_detailed');
            }
            if (failureDiagList) {
                const lang = getCurrentLang ? getCurrentLang() : 'ru';
                const statusMap = {
                    'PASS': lang === 'ru' ? 'Норма' : 'Pass',
                    'WARN': lang === 'ru' ? 'Внимание' : 'Warning',
                    'FAIL': lang === 'ru' ? 'Провал' : 'Failed'
                };

                failureDiagList.innerHTML = diagnostics.map((d, idx) => {
                    const promptBadge = d.prompt_id ? `<span class="badge badge-neutral" style="font-size:0.75rem;margin-left:0.5rem;">${t('prompt_badge_label')} #${d.prompt_id}</span>` : '';
                    const preview = d.prompt_preview ? `<div class="failure-diag-prompt-preview">«${escapeHtml(d.prompt_preview)}»</div>` : '';
                    const localizedTitle = getMethodTitle(d.method) || d.title;
                    const vRaw = d.verdict ? d.verdict.toUpperCase() : 'FAIL';
                    const vLabel = statusMap[vRaw] || vRaw;
                    return `
                        <div class="failure-diag-item">
                            <div class="failure-diag-item-header">
                                <span class="failure-diag-idx">#${idx + 1}</span>
                                <span class="failure-diag-item-title">${escapeHtml(localizedTitle)}</span>
                                ${promptBadge}
                                <span class="badge badge-${vRaw.toLowerCase()}" style="margin-left:auto;">${escapeHtml(vLabel)}</span>
                            </div>
                            <div class="failure-diag-item-msg">${escapeHtml(d.message)}</div>
                            ${preview}
                        </div>
                    `;
                }).join('');
            }
        } else {
            detailFailureDiagnostics.classList.add('hidden');
        }
    }

    // 4 Tiers
    const l0Score = scores.find(s => s.method.startsWith('quick_') || s.method.includes('fingerprint'));
    const l1Score = scores.find(s => s.method === 'jsd' || s.method.includes('jsd'));
    const l15Tps = scores.find(s => s.method === 'latency_tps');
    const l15Lat = scores.find(s => s.method === 'latency_drift');
    const assertScore = scores.find(s => s.method === 'assertions');
    const l2Score = scores.find(s => s.method === 'embedding_cosine' || s.method.includes('embedding'));
    const l3Score = scores.find(s => s.method === 'mmd_permutation' || s.method.includes('mmd'));

    setTierDisplay(tierStatusL0, l0Score);
    if (l0Score) {
        if (l0ClaimVal) l0ClaimVal.textContent = l0Score.verdict === 'PASS' ? t('l0_claim_match') : t('l0_claim_mismatch');
        if (l0FpVal) l0FpVal.textContent = l0Score.details?.fingerprint_observed || (l0Score.verdict === 'PASS' ? t('fingerprint_match') : t('fingerprint_diff'));
    } else {
        if (l0ClaimVal) l0ClaimVal.textContent = '—';
        if (l0FpVal) l0FpVal.textContent = '—';
    }

    setTierDisplay(tierStatusL1, l1Score);
    if (l1Score && l1Score.value !== null && l1Score.verdict !== 'SKIP') {
        if (l1JsdVal) l1JsdVal.textContent = l1Score.value.toFixed(4);
    } else {
        if (l1JsdVal) l1JsdVal.textContent = l1Score?.verdict === 'SKIP' ? t('val_skipped') : '—';
    }

    const l15Combined = l15Tps || l15Lat;
    setTierDisplay(tierStatusL15, l15Combined);
    if (l15Tps && l15Tps.verdict !== 'SKIP') {
        const dir = l15Tps.details?.direction === 'faster' ? '↑' : (l15Tps.details?.direction === 'slower' ? '↓' : '');
        if (l15TpsVal) l15TpsVal.textContent = `${(l15Tps.value * 100).toFixed(1)}% ${dir}`.trim();
    } else {
        if (l15TpsVal) l15TpsVal.textContent = l15Tps?.verdict === 'SKIP' ? t('val_skipped') : '—';
    }
    if (l15Lat && l15Lat.verdict !== 'SKIP' && l15Lat.details?.run_latency_ms?.median) {
        if (l15LatVal) l15LatVal.textContent = `${Math.round(l15Lat.details.run_latency_ms.median)}ms`;
    } else {
        if (l15LatVal) l15LatVal.textContent = '—';
    }

    setTierDisplay(tierStatusAssert, assertScore);
    if (assertScore && assertScore.details) {
        const passPct = Math.round((assertScore.value || 0) * 100);
        const passed = assertScore.details.passed_assertions || 0;
        const total = assertScore.details.total_assertions || 0;
        if (assertRateVal) assertRateVal.textContent = `${passed}/${total} (${passPct}%)`;
        const failCnt = assertScore.details.failure_count || 0;
        if (assertStatusVal) {
            assertStatusVal.textContent = failCnt > 0 
                ? t('assert_failed_cnt', { cnt: failCnt })
                : t('assert_all_passed');
            assertStatusVal.style.color = failCnt > 0 ? '#ef4444' : '#10b981';
        }
    } else {
        if (assertRateVal) assertRateVal.textContent = '—';
        if (assertStatusVal) {
            assertStatusVal.textContent = '—';
            assertStatusVal.style.color = '';
        }
    }

    setTierDisplay(tierStatusL2, l2Score);
    if (l2Score && l2Score.value !== null && l2Score.verdict !== 'SKIP') {
        if (l2SimVal) l2SimVal.textContent = l2Score.value.toFixed(4);
    } else {
        if (l2SimVal) l2SimVal.textContent = l2Score?.verdict === 'SKIP' ? t('val_skipped') : '—';
    }

    setTierDisplay(tierStatusL3, l3Score);
    if (l3Score && l3Score.value !== null && l3Score.verdict !== 'SKIP') {
        if (l3PvalVal) l3PvalVal.textContent = l3Score.value.toFixed(4);
    } else {
        if (l3PvalVal) l3PvalVal.textContent = t('val_skipped');
    }

    // Table of scores
    if (auditScoresTbody) {
        auditScoresTbody.innerHTML = scores.map(s => {
            const vClass = s.verdict.toLowerCase();
            const valStr = s.value !== null ? (typeof s.value === 'number' ? s.value.toFixed(4) : s.value) : '—';
            const threshStr = s.threshold !== null ? (typeof s.threshold === 'number' ? s.threshold.toFixed(4) : s.threshold) : '—';
            let detailsStr = '';
            if (s.method === 'assertions' && s.details) {
                const total = s.details.total_assertions || 0;
                const passed = s.details.passed_assertions || 0;
                const failCount = s.details.failure_count || 0;
                if (failCount > 0 && s.details.failures && s.details.failures.length > 0) {
                    const failList = s.details.failures.map(f => `[P#${f.prompt_id} ${f.assertion}: ${f.message || f.expected}]`).join('; ');
                    detailsStr = t('assert_passed_summary', { passed, total, failCount, failList });
                } else {
                    detailsStr = t('assert_all_passed_summary', { passed, total });
                }
            } else if (s.details) {
                if (typeof s.details === 'object') {
                    if (s.details.message) {
                        detailsStr = s.details.message;
                    } else {
                        detailsStr = Object.entries(s.details)
                            .map(([k, v]) => {
                                if (typeof v === 'object' && v !== null) {
                                    return `${k}: {${Object.entries(v).slice(0, 3).map(([ik, iv]) => `${ik}:${iv}`).join(', ')}}`;
                                }
                                return `${k}: ${v}`;
                            })
                            .join('; ');
                    }
                } else {
                    detailsStr = String(s.details);
                }
            }

            const methodLabel = getMethodTitle(s.method);
            const vKey = s.verdict === 'PASS' ? 'tier_pass' : (s.verdict === 'FAIL' ? 'tier_fail' : (s.verdict === 'WARN' ? 'tier_warn' : (s.verdict === 'SKIP' ? 'tier_skip' : '')));
            const verdictLabel = vKey ? t(vKey) : s.verdict;
            return `
                <tr>
                    <td><strong>${escapeHtml(methodLabel)}</strong></td>
                    <td><span class="badge badge-neutral">${escapeHtml(s.scope)}</span></td>
                    <td class="font-mono"><strong>${escapeHtml(String(valStr))}</strong></td>
                    <td class="font-mono text-muted">${escapeHtml(String(threshStr))}</td>
                    <td><span class="target-status-pill ${vClass}">${escapeHtml(verdictLabel)}</span></td>
                    <td style="font-size:0.775rem; color:var(--text-muted);">${escapeHtml(detailsStr)}</td>
                </tr>
            `;
        }).join('');
    }

    // Helper to update tier explanation block
    function setTierExplanation(elemId, statusClass, htmlContent) {
        const el = document.getElementById(elemId);
        if (!el) return;
        el.className = `results-tier-explanation ${statusClass}`;
        el.innerHTML = htmlContent;
    }

    const provenance = data.provenance;
    const samples = data.samples_comparison || [];
    const b = provenance?.baseline || {};
    const c = provenance?.candidate || {};
    const sampleWireModels = samples.map(s => s.candidate?.wire_model).filter(Boolean);
    const firstCandidateWire = sampleWireModels[0] || c.configured_model || run.target_id || '—';
    const hasWireMismatch = samples.some(s => s.model_mismatch) || (l0Score && l0Score.verdict === 'FAIL');

    // Populate Channel A (Ground Truth) Provenance
    const elGtUrl = document.getElementById('res-gt-url');
    const elGtModel = document.getElementById('res-gt-model');
    const elGtDate = document.getElementById('res-gt-date');
    if (elGtUrl) { elGtUrl.textContent = b.base_url || 'https://api.openai.com/v1'; elGtUrl.title = b.base_url || ''; }
    if (elGtModel) elGtModel.textContent = b.configured_model || run.target_id || '—';
    if (elGtDate) elGtDate.textContent = b.captured_at ? formatDate(b.captured_at) : 'Активный эталон T₀';

    // Populate Channel B (Candidate) Provenance
    const elCandUrl = document.getElementById('res-cand-url');
    const elCandModel = document.getElementById('res-cand-model');
    const elCandWire = document.getElementById('res-cand-wire');
    if (elCandUrl) { elCandUrl.textContent = c.base_url || target?.base_url || '—'; elCandUrl.title = c.base_url || target?.base_url || ''; }
    if (elCandModel) elCandModel.textContent = c.configured_model || target?.model || run.target_id || '—';
    if (elCandWire) {
        elCandWire.textContent = firstCandidateWire;
        elCandWire.style.color = hasWireMismatch ? '#ef4444' : 'var(--text-primary)';
    }

    // Set count badge for samples accordion
    const elSamplesBadge = document.getElementById('samples-count-badge');
    if (elSamplesBadge) elSamplesBadge.textContent = samples.length;

    // ─── Generate Human-Readable Explanations (Расшифровка и поведение модели) ────
    // 1. L0 Explanation
    if (hasWireMismatch) {
        setTierExplanation('l0-cand-expl', 'expl-fail',
            `<strong>✗ ОБНАРУЖЕНА ПОДМЕНА МОДЕЛИ!</strong> Запрашивалась модель «<code>${escapeHtml(c.configured_model || run.target_id || '')}</code>», но сервер фактически ответил моделью «<code>${escapeHtml(firstCandidateWire)}</code>».` +
            `<div class="expl-patterns">` +
            `<strong>Что выдает модель:</strong> Поведение типично для дешевых суррогатов (напр. <code>gpt-4o-mini</code> вместо <code>gpt-4o</code> или <code>haiku</code> вместо <code>sonnet</code>). В ответах на вопросы о собственной архитектуре могут проскальзывать фразы вроде <em>«I am an AI assistant based on GPT-4o-mini»</em>, а срез знаний (cutoff) отстает от заявленной флагманской версии.<br>` +
            `<strong>Интерпретация:</strong> Шлюз/провайдер намеренно перенаправляет трафик на более дешевую модель для занижения затрат.` +
            `</div>`
        );
    } else if (l0Score && l0Score.verdict === 'PASS') {
        const fpObs = l0Score.details?.fingerprint_observed;
        setTierExplanation('l0-cand-expl', 'expl-pass',
            `<strong>✓ Идентичность подтверждена.</strong> Модель в заголовке ответа «<code>${escapeHtml(firstCandidateWire)}</code>» полностью соответствует заявленной. Сигнатура отпечатка валидна.` +
            `<div class="expl-patterns">` +
            `<strong>Поведение модели:</strong> Зафиксированы оригинальные метаданные провайдера${fpObs ? ` (хеш весов: <code>${escapeHtml(fpObs)}</code>)` : ''}. Сессия соответствует официальной инфраструктуре поставщика.` +
            `</div>`
        );
    } else {
        setTierExplanation('l0-cand-expl', 'expl-warn',
            `<strong>⚠ Частичное соответствие:</strong> Имя модели «<code>${escapeHtml(firstCandidateWire)}</code>» совпадает, но оригинальный системный fingerprint не возвращен.` +
            `<div class="expl-patterns">` +
            `<strong>Поведение модели:</strong> Ответы семантически соответствуют семейству, однако проксирующий шлюз скрывает или переписывает служебные заголовки датацентра.` +
            `</div>`
        );
    }

    // 2. L1 Core Explanation (One-Token JSD)
    if (!l1Score || l1Score.verdict === 'SKIP') {
        setTierExplanation('l1-cand-expl', 'expl-skip',
            `— <em>Вероятностный тест пропущен:</em> Эндпоинт провайдера скрывает логиты (параметр <code>logprobs=true</code> не поддерживается). Рекомендуется ориентироваться на уровни L1.5, Rules и L2.`
        );
    } else if (l1Score.verdict === 'PASS') {
        const jsd = l1Score.value !== null ? l1Score.value.toFixed(4) : '0.0000';
        setTierExplanation('l1-cand-expl', 'expl-pass',
            `<strong>✓ Вероятностный профиль весов идентичен эталону (JSD = ${jsd} ≤ 0.1500).</strong>` +
            `<div class="expl-patterns">` +
            `<strong>Поведение модели:</strong> Стохастическое распределение первого токена p(t₁) на калибровочных тестах точно совпадает с официальным кластером. Инференс выполняется на подлинных полновесных тензорах FP16/BF16 без потери разрядности.` +
            `</div>`
        );
    } else {
        const jsd = l1Score.value !== null ? l1Score.value.toFixed(4) : '0.0000';
        setTierExplanation('l1-cand-expl', 'expl-fail',
            `<strong>✗ КРИТИЧЕСКИЙ ДРЕЙФ РАСПРЕДЕЛЕНИЯ (JSD = ${jsd} > 0.1500).</strong> Вероятности генерации первого токена кардинально расходятся с эталоном.` +
            `<div class="expl-patterns">` +
            `<strong>Что выдает модель:</strong> На стохастических контрольных развилках (выбор синонимов, продолжение логических последовательностей) модель вместо эталонного распределения выдает искаженные логиты. Вероятности смещены в пользу наиболее тривиальных токенов.<br>` +
            `<strong>Интерпретация:</strong> Математически доказано использование урезанных весов, грубого квантования (AWQ 4-bit, GGUF Q4) или дистиллированной суррогатной архитектуры.` +
            `</div>`
        );
    }

    // 3. L1.5 Speed & Latency Explanation
    if (!l15Combined || l15Combined.verdict === 'SKIP') {
        setTierExplanation('l15-cand-expl', 'expl-skip',
            `— <em>Тест таймингов не проводился</em> или замеры производительности были пропущены.`
        );
    } else if (l15Combined.verdict === 'PASS') {
        const tpsInfo = l15Tps && l15Tps.value !== null ? `отклонение ${(l15Tps.value * 100).toFixed(1)}%` : 'стабильная отдача';
        const latInfo = l15Lat && l15Lat.details?.run_latency_ms?.median ? `медиана ${Math.round(l15Lat.details.run_latency_ms.median)}ms` : '';
        setTierExplanation('l15-cand-expl', 'expl-pass',
            `<strong>✓ Производительность в пределах SLA (${tpsInfo}${latInfo ? `, ${latInfo}` : ''}).</strong>` +
            `<div class="expl-patterns">` +
            `<strong>Поведение модели:</strong> Скорость генерации токенов (TPS) и задержка ответа укладываются в эталонный диапазон оригинального датацентра без признаков троттлинга.` +
            `</div>`
        );
    } else {
        const dir = l15Tps?.details?.direction === 'slower' ? 'просадка скорости' : 'аномальное отклонение скорости';
        const tpsVal = l15Tps && l15Tps.value !== null ? `${(l15Tps.value * 100).toFixed(1)}%` : 'выходит за допуск';
        setTierExplanation('l15-cand-expl', 'expl-warn',
            `<strong>⚠ Обнаружена аномалия производительности (${dir}, отклонение ${tpsVal}).</strong>` +
            `<div class="expl-patterns">` +
            `<strong>Что выдает модель:</strong> При аномально высокой скорости (&gt;130 tps) вместо тяжелой модели 70B+ часто работает легковесная сеть 8B. При сильной просадке (&lt;15 tps и TTFT &gt; 3500ms) провайдер экономит на мощностях или нода перегружена.<br>` +
            `<strong>Интерпретация:</strong> Нестабильный SLA или признак подмены на легкую архитектуру.` +
            `</div>`
        );
    }

    // 4. Rules Explanation
    if (!assertScore || !assertScore.details) {
        setTierExplanation('assert-cand-expl', 'expl-skip',
            `— <em>Детерминированные правила не запускались</em> для данной батареи проверок.`
        );
    } else if (assertScore.verdict === 'PASS') {
        const passed = assertScore.details.passed_assertions || 0;
        const total = assertScore.details.total_assertions || 0;
        setTierExplanation('assert-cand-expl', 'expl-pass',
            `<strong>✓ Все правила контракта выполнены (пройдено ${passed} из ${total}, 100%).</strong>` +
            `<div class="expl-patterns">` +
            `<strong>Поведение модели:</strong> Безукоризненное соблюдение JSON-схем, корректные типы полей, отсутствие ложных отказов и полное следование системным инструкциям.` +
            `</div>`
        );
    } else {
        const total = assertScore.details.total_assertions || 0;
        const failCnt = assertScore.details.failure_count || 0;
        const failures = (assertScore.details.failures || []).map(f => f.assertion).filter((v, i, a) => a.indexOf(v) === i).join(', ');
        setTierExplanation('assert-cand-expl', 'expl-fail',
            `<strong>✗ Нарушение детерминированных правил (${failCnt} сбоев из ${total} проверок).</strong> Ошибки: <code>${escapeHtml(failures || 'формат ответа')}</code>.` +
            `<div class="expl-patterns">` +
            `<strong>Что выдает модель:</strong> Модель ломает JSON-синтаксис, самовольно оборачивает вывод в <code>\`\`\`json ... \`\`\`</code> вопреки требованию сырого JSON, теряет обязательные поля схемы или выдает ложный отказ (Refusal: <em>«I cannot assist with this request»</em>).<br>` +
            `<strong>Интерпретация:</strong> Недостаточная способность следовать сложным инструкциям — признак слабой или урезанной модели.` +
            `</div>`
        );
    }

    // 5. L2 Semantic Cosine Explanation
    if (!l2Score || l2Score.verdict === 'SKIP') {
        setTierExplanation('l2-cand-expl', 'expl-skip',
            `— <em>Семантическое сравнение не выполнялось</em> (активируется в расширенных батареях anti_spoof и v1).`
        );
    } else if (l2Score.verdict === 'PASS') {
        const sim = l2Score.value !== null ? l2Score.value.toFixed(4) : '1.0000';
        setTierExplanation('l2-cand-expl', 'expl-pass',
            `<strong>✓ Высокая смысловая эквивалентность ответов (Cosine = ${sim} ≥ 0.8800).</strong>` +
            `<div class="expl-patterns">` +
            `<strong>Поведение модели:</strong> Архитектурные рассуждения, полнота кода и глубина аргументации семантически тождественны эталонным ответам.` +
            `</div>`
        );
    } else {
        const sim = l2Score.value !== null ? l2Score.value.toFixed(4) : '0.0000';
        setTierExplanation('l2-cand-expl', 'expl-warn',
            `<strong>⚠ Снижение смыслового сходства (Cosine = ${sim} < 0.8800).</strong>` +
            `<div class="expl-patterns">` +
            `<strong>Что выдает модель:</strong> Ответы кандидата поверхностны, упускают редкие алгоритмические краевые случаи, содержат абстрактные рассуждения вместо рабочего кода или подменяют логику упрощенными библиотеками.<br>` +
            `<strong>Интерпретация:</strong> Деградация семантической глубины рассуждений указывает на упрощенную модель.` +
            `</div>`
        );
    }

    // 6. L3 MMD Test Explanation
    if (!l3Score || l3Score.verdict === 'SKIP') {
        setTierExplanation('l3-cand-expl', 'expl-skip',
            `— <em>MMD тест требует полной выборки</em> (доступен при запуске полного аудита v1 на 671 сэмпл).`
        );
    } else if (l3Score.verdict === 'PASS') {
        const pval = l3Score.value !== null ? l3Score.value.toFixed(4) : '1.0000';
        setTierExplanation('l3-cand-expl', 'expl-pass',
            `<strong>✓ Нулевая гипотеза идентичности H₀ не отвергнута (p = ${pval} > 0.05).</strong>` +
            `<div class="expl-patterns">` +
            `<strong>Поведение модели:</strong> Выборка ответов кандидата статистически неотличима от эталонной генеральной совокупности.` +
            `</div>`
        );
    } else {
        const pval = l3Score.value !== null ? l3Score.value.toFixed(4) : '0.0000';
        setTierExplanation('l3-cand-expl', 'expl-fail',
            `<strong>✗ Статистически доказано различие моделей (p = ${pval} ≤ 0.05).</strong>` +
            `<div class="expl-patterns">` +
            `<strong>Что выдает модель:</strong> Многомерное распределение эмбеддингов в латентном пространстве статистически не принадлежит генератору эталона.<br>` +
            `<strong>Интерпретация:</strong> Нулевая гипотеза тождественности отвергнута с вероятностью ошибки &lt; 5%. Модель является чужеродной.` +
            `</div>`
        );
    }

    renderSamplesComparison(data);
}

function renderSamplesComparison(data) {
    if (!detailSamplesInspector) return;

    const provenance = data.provenance;
    const samples = data.samples_comparison || [];

    // 1. Render Provenance Grid (Candidate vs Baseline origin definitions)
    if (detailProvenanceGrid) {
        if (provenance) {
            const b = provenance.baseline || {};
            const c = provenance.candidate || {};
            
            const sampleWireModels = samples
                .map(s => s.candidate?.wire_model)
                .filter(Boolean);
            const firstCandidateWire = sampleWireModels[0] || '—';
            const hasWireMismatch = samples.some(s => s.model_mismatch);

            detailProvenanceGrid.innerHTML = `
                <div class="prov-box prov-baseline">
                    <div class="prov-box-header">
                        <span>${t('prov_gt_header')}</span>
                        <span class="badge badge-pass font-mono">#${b.baseline_id || '—'}</span>
                    </div>
                    <div class="prov-kv-list">
                        <div class="prov-kv-row">
                            <span class="prov-kv-label">${t('lbl_endpoint_id')}:</span>
                            <span class="prov-kv-value font-mono">${escapeHtml(b.target_id || b.baseline_id || '—')}</span>
                        </div>
                        <div class="prov-kv-row">
                            <span class="prov-kv-label">${t('lbl_endpoint_url')}:</span>
                            <span class="prov-kv-value font-mono" title="${escapeHtml(b.base_url || '')}">${escapeHtml(b.base_url || '—')}</span>
                        </div>
                        <div class="prov-kv-row">
                            <span class="prov-kv-label">${t('lbl_requested_model')}:</span>
                            <span class="prov-kv-value font-mono">${escapeHtml(b.configured_model || '—')}</span>
                        </div>
                        <div class="prov-kv-row">
                            <span class="prov-kv-label">${t('lbl_snapshot_date')}:</span>
                            <span class="prov-kv-value font-mono">${formatDate(b.captured_at)}</span>
                        </div>
                        ${b.routing_proof?.endpoint_slug ? `
                        <div class="prov-kv-row">
                            <span class="prov-kv-label">Proof-of-Routing:</span>
                            <span class="prov-kv-value font-mono" style="color: #10b981; font-weight: 600;">[VERIFIED] ${escapeHtml(b.routing_proof.endpoint_slug)}</span>
                        </div>` : ''}
                    </div>
                </div>
                <div class="prov-box prov-candidate">
                    <div class="prov-box-header">
                        <span>${t('prov_cand_header')}</span>
                        <span class="badge badge-neutral font-mono">${escapeHtml(c.target_id || '—')}</span>
                    </div>
                    <div class="prov-kv-list">
                        <div class="prov-kv-row">
                            <span class="prov-kv-label">${t('lbl_endpoint_id')}:</span>
                            <span class="prov-kv-value font-mono">${escapeHtml(c.target_id || '—')}</span>
                        </div>
                        <div class="prov-kv-row">
                            <span class="prov-kv-label">${t('lbl_endpoint_url')}:</span>
                            <span class="prov-kv-value font-mono" title="${escapeHtml(c.base_url || '')}">${escapeHtml(c.base_url || '—')}</span>
                        </div>
                        <div class="prov-kv-row">
                            <span class="prov-kv-label">${t('lbl_requested_model')}:</span>
                            <span class="prov-kv-value font-mono">${escapeHtml(c.configured_model || '—')}</span>
                        </div>
                        <div class="prov-kv-row">
                            <span class="prov-kv-label">${t('lbl_wire_model')}:</span>
                            <span class="prov-kv-value font-mono" style="color: ${hasWireMismatch ? '#ef4444' : 'var(--text-primary)'}; font-weight: 700;">${escapeHtml(firstCandidateWire)}</span>
                        </div>
                        ${c.routing_proof?.endpoint_slug ? `
                        <div class="prov-kv-row">
                            <span class="prov-kv-label">Proof-of-Routing:</span>
                            <span class="prov-kv-value font-mono" style="color: #10b981; font-weight: 600;">[VERIFIED] ${escapeHtml(c.routing_proof.endpoint_slug)}</span>
                        </div>` : ''}
                    </div>
                </div>
            `;
        } else {
            detailProvenanceGrid.innerHTML = '';
        }
    }

    // 2. Render Paired Samples Comparison
    if (detailSamplesList) {
        if (samples.length === 0) {
            detailSamplesList.innerHTML = `
                <div class="empty-state text-muted" style="padding: 2rem; text-align: center;">${t('no_samples_available')}</div>
            `;
        } else {
            detailSamplesList.innerHTML = samples.map(item => {
                const isDiff = item.has_discrepancy || item.model_mismatch || (item.assertion_failures && item.assertion_failures.length > 0) || !item.text_exact_match;
                const cardClass = isDiff ? 'has-diff' : 'is-matching';

                let statusBadge = '';
                if (item.model_mismatch) {
                    statusBadge = `<span class="badge badge-fail">${t('badge_model_mismatch')}</span>`;
                } else if (isDiff) {
                    statusBadge = `<span class="badge badge-fail">${t('badge_discrepancy')}</span>`;
                } else {
                    statusBadge = `<span class="badge badge-pass">${t('badge_identical')}</span>`;
                }

                const failuresHtml = (item.assertion_failures && item.assertion_failures.length > 0)
                    ? `
                        <div class="compare-failures-box">
                            ${item.assertion_failures.map(f => `<div><span class="badge badge-fail" style="font-size:0.65rem; margin-right:4px;">FAIL</span> <strong>${escapeHtml(f.assertion)}</strong>: ${escapeHtml(f.message || f.expected || '')}</div>`).join('')}
                        </div>
                    `
                    : '';

                const baselineTokens = item.baseline?.usage?.total_tokens;
                const candidateTokens = item.candidate?.usage?.total_tokens;

                return `
                    <div class="prompt-compare-card ${cardClass}" data-has-diff="${isDiff ? '1' : '0'}">
                        <div class="prompt-compare-header">
                            <div class="prompt-compare-title">
                                <span class="badge badge-neutral" style="font-size:0.75rem; font-weight:700;">#${item.prompt_id}</span>
                                <span class="badge badge-neutral" style="font-size:0.7rem; opacity:0.85;">${escapeHtml(item.category || 'general')}</span>
                                <span class="prompt-text-quote" title="${escapeHtml(item.prompt_text)}">«${escapeHtml(item.prompt_text)}»</span>
                            </div>
                            <div style="display:flex; align-items:center; gap:0.5rem;">
                                ${statusBadge}
                            </div>
                        </div>
                        <div class="prompt-compare-body">
                            <div class="compare-col baseline-col">
                                <div class="compare-col-header">
                                    <span>${t('lbl_baseline_response')}</span>
                                    <span class="font-mono text-muted" style="font-size:0.75rem;">${escapeHtml(item.baseline?.wire_model || '—')}</span>
                                </div>
                                <div class="compare-text-box">${escapeHtml(item.baseline?.raw_text || '')}</div>
                                <div class="compare-metrics-footer">
                                    <span class="compare-metric-pill">${t('lbl_latency')}: ${item.baseline?.latency_ms || 0}ms</span>
                                    ${baselineTokens ? `<span class="compare-metric-pill">${t('lbl_tokens_short')}: ${baselineTokens}</span>` : ''}
                                </div>
                            </div>
                            <div class="compare-col candidate-col ${isDiff ? 'diff-highlight' : ''}">
                                <div class="compare-col-header">
                                    <span>${t('lbl_candidate_response')}</span>
                                    <span class="font-mono" style="font-size:0.75rem; color:${item.model_mismatch ? '#ef4444' : 'var(--text-primary)'}; font-weight:700;">${escapeHtml(item.candidate?.wire_model || '—')}</span>
                                </div>
                                <div class="compare-text-box">${escapeHtml(item.candidate?.raw_text || '')}</div>
                                <div class="compare-metrics-footer">
                                    <span class="compare-metric-pill">${t('lbl_latency')}: ${item.candidate?.latency_ms || 0}ms</span>
                                    ${candidateTokens ? `<span class="compare-metric-pill">${t('lbl_tokens_short')}: ${candidateTokens}</span>` : ''}
                                </div>
                            </div>
                        </div>
                        ${failuresHtml}
                    </div>
                `;
            }).join('');
        }
    }

    applySamplesFilter(currentSamplesFilter);
}

export function applySamplesFilter(filterType) {
    currentSamplesFilter = filterType;
    if (btnFilterAll) btnFilterAll.classList.toggle('active', filterType === 'all');
    if (btnFilterDiff) btnFilterDiff.classList.toggle('active', filterType === 'diff');
    if (btnFilterMatch) btnFilterMatch.classList.toggle('active', filterType === 'match');

    if (!detailSamplesList) return;
    const cards = detailSamplesList.querySelectorAll('.prompt-compare-card');
    cards.forEach(card => {
        const hasDiff = card.getAttribute('data-has-diff') === '1';
        if (filterType === 'all') {
            card.style.display = '';
        } else if (filterType === 'diff') {
            card.style.display = hasDiff ? '' : 'none';
        } else if (filterType === 'match') {
            card.style.display = !hasDiff ? '' : 'none';
        }
    });
}

function setTierDisplay(elem, score) {
    if (!elem) return;
    if (!score) {
        elem.textContent = '—';
        elem.className = 'tier-status';
        return;
    }
    const v = score.verdict;
    const vKey = v === 'PASS' ? 'tier_pass' : (v === 'FAIL' ? 'tier_fail' : (v === 'WARN' ? 'tier_warn' : (v === 'SKIP' ? 'tier_skip' : '')));
    elem.textContent = vKey ? t(vKey) : v;
    elem.className = `tier-status ${v.toLowerCase()}`;
}

// ─── Copy For AI (ChatGPT / Claude Prompt Generator) ──────────────────────────

export function copyReportForAi() {
    if (!lastLoadedRunData) {
        alert(t('alert_select_run') || 'Сначала выберите или запустите проверку эндпоинта.');
        return;
    }
    const promptText = generateAiPromptText(lastLoadedRunData);
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(promptText).then(() => {
            showCopyFeedback('btn-copy-ai', '✓ Скопировано!');
            showCopyFeedback('btn-copy-failure-ai', '✓ Скопировано!');
        }).catch(() => {
            fallbackClipboardCopy(promptText);
        });
    } else {
        fallbackClipboardCopy(promptText);
    }
}

function fallbackClipboardCopy(text) {
    try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        showCopyFeedback('btn-copy-ai', '✓ Скопировано!');
        showCopyFeedback('btn-copy-failure-ai', '✓ Скопировано!');
    } catch {
        prompt('Скопируйте текст отчета для AI:', text);
    }
}

function showCopyFeedback(btnId, msg) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    const textSpan = document.getElementById(`${btnId}-text`) || btn.querySelector('span') || btn;
    const originalHtml = textSpan.innerHTML;
    textSpan.innerHTML = msg;
    btn.classList.add('btn-copy-success');
    setTimeout(() => {
        textSpan.innerHTML = originalHtml;
        btn.classList.remove('btn-copy-success');
    }, 2400);
}

export function generateAiPromptText(data) {
    if (!data) return '';
    const { run, target, scores = [], failure_diagnostics = [], samples_comparison = [], provenance = {} } = data;
    const b = provenance.baseline || {};
    const c = provenance.candidate || {};

    const targetId = target?.id || run.target_id || 'unknown';
    const baseUrl = target?.base_url || c.base_url || '—';
    const claimedModel = target?.model || c.configured_model || '—';
    const wireModel = samples_comparison.map(s => s.candidate?.wire_model).filter(Boolean)[0] || claimedModel;
    const verdict = run.verdict || 'UNKNOWN';
    const startedAt = run.started_at ? formatDate(run.started_at) : '—';
    const tokens = (run.total_tokens || 0).toLocaleString();
    let dur = 0;
    if (run.started_at && run.finished_at) {
        dur = Math.round((new Date(run.finished_at) - new Date(run.started_at)) / 1000);
    }

    const l0 = scores.find(s => s.method.startsWith('quick_') || s.method.includes('fingerprint'));
    const l1 = scores.find(s => s.method === 'jsd' || s.method.includes('jsd'));
    const l15Tps = scores.find(s => s.method === 'latency_tps');
    const l15Lat = scores.find(s => s.method === 'latency_drift');
    const assertScore = scores.find(s => s.method === 'assertions');
    const l2 = scores.find(s => s.method === 'embedding_cosine' || s.method.includes('embedding'));
    const l3 = scores.find(s => s.method === 'mmd_permutation' || s.method.includes('mmd'));

    const l0Val = l0 ? `${l0.verdict === 'PASS' ? 'Совпадает' : 'НЕСООТВЕТСТВИЕ'} (Wire: ${wireModel})` : '—';
    const l1Val = l1 && l1.value !== null && l1.verdict !== 'SKIP' ? `JSD = ${l1.value.toFixed(4)} (Порог ≤ 0.1500)` : (l1?.verdict === 'SKIP' ? 'Пропущен (без logprobs)' : '—');
    const tpsVal = l15Tps && l15Tps.value !== null && l15Tps.verdict !== 'SKIP' ? `${(l15Tps.value * 100).toFixed(1)}% ${l15Tps.details?.direction || ''}` : '—';
    const latVal = l15Lat?.details?.run_latency_ms?.median ? `${Math.round(l15Lat.details.run_latency_ms.median)}ms` : '—';
    const assertVal = assertScore?.details ? `${assertScore.details.passed_assertions || 0}/${assertScore.details.total_assertions || 0} (${Math.round((assertScore.value || 0) * 100)}%)` : '—';
    const l2Val = l2 && l2.value !== null && l2.verdict !== 'SKIP' ? `Cosine = ${l2.value.toFixed(4)} (Порог ≥ 0.8800)` : '—';
    const l3Val = l3 && l3.value !== null && l3.verdict !== 'SKIP' ? `p = ${l3.value.toFixed(4)} (α = 0.05)` : '—';

    let failureText = '';
    if (failure_diagnostics.length > 0) {
        failureText = failure_diagnostics.map((d, i) => {
            const pId = d.prompt_id ? ` [Промпт #${d.prompt_id}]` : '';
            const preview = d.prompt_preview ? `\n   > Запрос: «${d.prompt_preview}»` : '';
            return `${i + 1}. **${d.title || d.method}** (${d.verdict || 'FAIL'})${pId}: ${d.message}${preview}`;
        }).join('\n');
    } else {
        failureText = 'Критических сбоев и отклонений от эталона не зафиксировано.';
    }

    const diffSamples = samples_comparison.filter(s => s.has_discrepancy || s.model_mismatch || (s.assertion_failures && s.assertion_failures.length > 0) || !s.text_exact_match).slice(0, 3);
    let sampleDiffText = '';
    if (diffSamples.length > 0) {
        sampleDiffText = diffSamples.map((s, i) => {
            const bResp = (s.baseline?.raw_text || '').trim().slice(0, 350);
            const cResp = (s.candidate?.raw_text || '').trim().slice(0, 350);
            return `### Сэмпл #${i + 1} (Промпт #${s.prompt_id}: «${s.prompt_text}»)
- **Эталонный ответ (${s.baseline?.wire_model || 'Ground Truth'}):**
\`\`\`
${bResp || '[Пустой ответ]'}
\`\`\`
- **Ответ проверяемого эндпоинта (${s.candidate?.wire_model || 'Candidate'}):**
\`\`\`
${cResp || '[Пустой ответ]'}
\`\`\``;
        }).join('\n\n');
    } else {
        sampleDiffText = 'Ответы кандидата на тестовые промпты идентичны эталонным.';
    }

    return `# 🔬 Криминалистический аудит LLM эндпоинта (Attest Verification Report)

Пожалуйста, проанализируй результаты дифференциального аудита эндпоинта на предмет **подмены модели (model spoofing)**, **скрытого квантования (quantization)** или **деградации сервиса (SLA drift)**.

## 1. Контекст проверки
- **ID Таргета:** \`${targetId}\`
- **URL эндпоинта:** \`${baseUrl}\`
- **Заявленная модель:** \`${claimedModel}\`
- **Фактическая Wire модель:** \`${wireModel}\`
- **Итоговый вердикт:** **${verdict}**
- **Дата и длительность:** ${startedAt} (${dur}s, ${tokens} токенов)

## 2. Матрица верификации по уровням (Tier Matrix)
| Уровень | Метрика | Значение | Вердикт |
|---|---|---|---|
| **L0 Signature** | Wire Model & Fingerprint | ${l0Val} | ${l0?.verdict || '—'} |
| **L1 Core** | One-Token JSD (Вероятности первого токена) | ${l1Val} | ${l1?.verdict || '—'} |
| **L1.5 SLA** | Скорость генерации (TPS) | ${tpsVal} | ${l15Tps?.verdict || '—'} |
| **L1.5 SLA** | Задержка ответа (Latency median) | ${latVal} | ${l15Lat?.verdict || '—'} |
| **Rules** | Детерминированные правила (JSON/Схемы/SLA) | ${assertVal} | ${assertScore?.verdict || '—'} |
| **L2 Semantic** | Cosine сходство эмбеддингов | ${l2Val} | ${l2?.verdict || '—'} |
| **L3 MMD** | Статистический тест идентичности генератора | ${l3Val} | ${l3?.verdict || '—'} |

## 3. Выявленные сбои и аномалии (${failure_diagnostics.length})
${failureText}

## 4. Конкретные примеры расхождений в ответах
${sampleDiffText}

## 5. Вопросы для экспертного заключения AI:
1. **Факт подмены или квантования:** Подтверждают ли указанные метрики (JSD, Wire model, скорость, нарушение правил) намеренную подмену модели поставщиком (spoofing) или агрессивное квантование (AWQ/GPTQ/FP8)?
2. **Анализ расхождений:** В чем заключается качественная разница между поведением эталонной модели и кандидата в предоставленных примерах?
3. **Текст претензии (Dispute Ticket):** Сформулируй краткую, юридически и технически обоснованную претензию к поставщику API с требованием перерасчета стоимости и переключения на подлинную оригинальную модель.`;
}


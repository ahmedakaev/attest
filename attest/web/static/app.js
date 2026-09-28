/**
 * Attest Web Dashboard — Interactive Frontend Application (SPA)
 */

(function () {
    'use strict';

    // State
    let activeTaskId = null;
    let pollInterval = null;

    // Safe non-blocking confirm helper for automated and browser test environments
    function safeConfirm(msg) {
        if (window.navigator.webdriver || window.__ATTEST_AUTO_CONFIRM__) return true;
        return window.confirm(msg);
    }

    // DOM Elements
    const statTotalTargets = document.getElementById('stat-total-targets');
    const statActiveBaselines = document.getElementById('stat-active-baselines');
    const statTotalAudits = document.getElementById('stat-total-audits');
    const statPasses = document.getElementById('stat-passes');
    const statFailures = document.getElementById('stat-failures');
    const targetsGrid = document.getElementById('targets-grid');

    // Live Task Banner
    const liveTaskBanner = document.getElementById('live-task-banner');
    const taskBannerTitle = document.getElementById('task-banner-title');
    const taskBannerSub = document.getElementById('task-banner-sub');
    const taskBannerCounts = document.getElementById('task-banner-counts');
    const taskBannerPct = document.getElementById('task-banner-pct');
    const taskProgressFill = document.getElementById('task-progress-fill');
    const btnCloseTaskBanner = document.getElementById('btn-close-task-banner');

    // Details Section
    const auditDetailsSection = document.getElementById('audit-details-section');
    const detailTargetTitle = document.getElementById('detail-target-title');
    const detailVerdictBanner = document.getElementById('detail-verdict-banner');
    const detailVerdictIcon = document.getElementById('detail-verdict-icon');
    const detailVerdictHeading = document.getElementById('detail-verdict-heading');
    const detailVerdictSub = document.getElementById('detail-verdict-sub');
    const detailTokens = document.getElementById('detail-tokens');
    const detailDuration = document.getElementById('detail-duration');

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

    // Samples Comparison Inspector
    const detailSamplesInspector = document.getElementById('detail-samples-inspector');
    const detailProvenanceGrid = document.getElementById('detail-provenance-grid');
    const detailSamplesList = document.getElementById('detail-samples-list');
    const btnFilterAll = document.getElementById('btn-filter-all');
    const btnFilterDiff = document.getElementById('btn-filter-diff');
    const btnFilterMatch = document.getElementById('btn-filter-match');
    let currentSamplesFilter = 'all';

    // Modals
    const btnRefresh = document.getElementById('btn-refresh');

    const modalEstimate = document.getElementById('modal-estimate');
    const estimateModalTitle = document.getElementById('estimate-modal-title');
    const estimateModalBody = document.getElementById('estimate-modal-body');
    const btnCloseEstimateModal = document.getElementById('btn-close-estimate-modal');
    const btnOkEstimate = document.getElementById('btn-ok-estimate');

    const modalHistory = document.getElementById('modal-history');
    const historyModalTitle = document.getElementById('history-modal-title');
    const historyTbody = document.getElementById('history-tbody');
    const btnCloseHistoryModal = document.getElementById('btn-close-history-modal');
    const btnOkHistory = document.getElementById('btn-ok-history');

    // Baselines Archive Modal
    const btnOpenBaselinesModal = document.getElementById('btn-open-baselines-modal');
    const modalBaselines = document.getElementById('modal-baselines');
    const btnCloseBaselinesModal = document.getElementById('btn-close-baselines-modal');
    const btnCloseBaselinesModalFooter = document.getElementById('btn-close-baselines-modal-footer');
    const baselinesTbody = document.getElementById('baselines-tbody');
    const inputFilterBaselines = document.getElementById('input-filter-baselines');
    const lblBaselinesCount = document.getElementById('lbl-baselines-count');

    // Schedules Elements
    const btnOpenSchedulesModal = document.getElementById('btn-open-schedules-modal');
    const modalSchedules = document.getElementById('modal-schedules');
    const btnCloseSchedulesModal = document.getElementById('btn-close-schedules-modal');
    const btnCloseSchedulesModalFooter = document.getElementById('btn-close-schedules-modal-footer');
    const formAddSchedule = document.getElementById('form-add-schedule');
    const selectSchedTarget = document.getElementById('select-sched-target');
    const selectSchedInterval = document.getElementById('select-sched-interval');
    const selectSchedBattery = document.getElementById('select-sched-battery');
    const schedulesTbody = document.getElementById('schedules-tbody');

    // Export Buttons
    const btnExportJson = document.getElementById('btn-export-json');
    const btnExportDisputeMd = document.getElementById('btn-export-dispute-md');
    const btnExportHtml = document.getElementById('btn-export-html');
    let currentActiveRunId = null;

    // Language & Diagnostics State
    let currentLang = localStorage.getItem('attest_lang') || 'ru';
    const btnLangToggle = document.getElementById('btn-lang-toggle');
    const currentLangLabel = document.getElementById('current-lang-label');

    // Theme Management (Light & Dark Slate)
    let currentTheme = localStorage.getItem('attest_theme') || 'dark';
    const btnThemeToggle = document.getElementById('btn-theme-toggle');
    const themeLabel = document.getElementById('theme-label');
    const themeIconSun = document.querySelector('.theme-icon-sun');
    const themeIconMoon = document.querySelector('.theme-icon-moon');

    function applyTheme(theme) {
        currentTheme = theme;
        localStorage.setItem('attest_theme', theme);
        document.documentElement.setAttribute('data-theme', theme);
        if (themeLabel) {
            themeLabel.textContent = theme === 'light' ? t('theme_light') : t('theme_dark');
        }
        if (themeIconSun && themeIconMoon) {
            if (theme === 'light') {
                themeIconSun.classList.remove('hidden');
                themeIconMoon.classList.add('hidden');
            } else {
                themeIconSun.classList.add('hidden');
                themeIconMoon.classList.remove('hidden');
            }
        }
    }

    const detailFailureDiagnostics = document.getElementById('detail-failure-diagnostics');
    const failureDiagTitle = document.getElementById('failure-diag-title');
    const failureDiagSub = document.getElementById('failure-diag-sub');
    const failureDiagList = document.getElementById('failure-diag-list');

    let lastLoadedRunData = null;

    // Declarative i18n Cache & Bundled Fallbacks
    const I18N_CACHE = {};
    const I18N_FALLBACK = {
        ru: {
            title: 'Attest — Шлюз верификации и защиты от подмены нейросетей',
            brand_sub: 'Шлюз верификации LLM',
            server_online: 'Порт {port} • Онлайн',
            theme_light: 'Светлая',
            theme_dark: 'Тёмная',
            targets: 'Таргеты',
            baselines: 'Эталоны',
            audits: 'Проверки',
            passes: 'Успешно',
            failures: 'Сбои',
            refresh: 'Обновить',
            audit_all: 'Проверить все',
            baselines_archive: 'Архив эталонов',
            monitors: 'Мониторинг & Cron',
            add_target: 'Добавить таргет',
            quick_presets: 'Быстрый выбор:',
            studio_badge: 'Студия верификации',
            studio_title: 'Дифференциальная верификация',
            studio_desc: 'Аудит стороннего API провайдера против эталонных вероятностных распределений (Ground Truth ◄—► Кандидат)',
            tab_channel_a_saved: 'Из базы эталонов',
            tab_channel_a_live: 'Прямой API эндпоинт',
            lbl_models_path: 'Путь к API моделей',
            btn_capture_live_ref: 'Снять эталон с этого API',
            endpoints_title: 'Отслеживаемые эндпоинты',
            endpoints_desc: 'Активные LLM API эндпоинты, проверяемые против эталонных вероятностных распределений',
            deep_dive_title: 'Детализация проверки',
            target_report: 'Отчет о верификации эндпоинта',
            export_json: 'Экспорт JSON',
            dispute_pack: 'Претензия (.md)',
            print_pdf: 'Печать / PDF',
            close_report: '✕ Закрыть отчет',
            verdict_pass: 'ПРОВЕРКА ПРОЙДЕНА — ПОДЛИННАЯ МОДЕЛЬ',
            verdict_pass_sub: 'Все метрики отклонений и распределения токенов соответствуют эталону.',
            verdict_warn: 'ВНИМАНИЕ — ОБНАРУЖЕН ДРЕЙФ ПОВЕДЕНИЯ',
            verdict_warn_sub: 'Зафиксированы расхождения в задержках или незначительный дрейф распределений.',
            verdict_fail: 'ПОДМЕНА МОДЕЛИ ИЛИ ДЕГРАДАЦИЯ (ОТКЛОНЕНО)',
            verdict_fail_sub: 'Вероятностные распределения токенов существенно отклоняются от эталона!',
            diag_title: 'Диагностика сбоев: что пошло не так',
            diag_title_with_count: 'Диагностика сбоев: что пошло не так ({count} сбоев)',
            diag_sub: 'Детализированный отчет об отклонениях, непройденных проверках и затронутых промптах',
            diag_sub_detailed: 'Детализированный отчет об отклонениях, непройденных тестах и затронутых промптах:',
            prompt_badge_label: 'Промпт',
            card_status_pass: 'ПОДТВЕРЖДЕНО',
            card_status_warn: 'ВНИМАНИЕ',
            card_status_fail: 'ПОДМЕНА МОДЕЛИ',
            card_status_none: 'НЕ ПРОВЕРЯЛСЯ',
            lbl_base_url: 'URL эндпоинта',
            lbl_api_key: 'API ключ',
            lbl_active_baseline: 'Активный эталон',
            lbl_last_audit: 'Последняя проверка',
            btn_card_audit: 'Проверить',
            btn_card_baseline: 'Снять эталон',
            btn_card_budget: 'Бюджет',
            btn_card_history: 'История',
            btn_card_details: 'Детали',
            l0_claim_match: 'Совпадает',
            l0_claim_mismatch: 'Не совпадает',
            assert_all_passed: 'Все пройдены',
            assert_failed_cnt: 'Провалено: {cnt}',
            assert_passed_summary: '{passed}/{total} пройдено ({failCount} сбоев: {failList})',
            assert_all_passed_summary: 'Все {passed}/{total} правил пройдены.',
            methods: {
                quick_model: 'Соответствие модели',
                quick_fingerprint: 'Системный отпечаток',
                quick_seed: 'Детерминизм сида',
                jsd: 'Расхождение токенов JSD',
                latency_tps: 'Скорость генерации (TPS)',
                latency_drift: 'Задержка ответа',
                assertions: 'Детерминированные правила',
                embedding_cosine: 'Семантическое сходство',
                mmd_permutation: 'MMD тест идентичности',
            },
        },
        en: {
            title: 'Attest — LLM Anti-Spoofing & Verification Dashboard',
            brand_sub: 'AI Anti-Spoofing Gate',
            server_online: 'Port {port} • Online',
            theme_light: 'Light',
            theme_dark: 'Dark',
            targets: 'Targets',
            baselines: 'Baselines',
            audits: 'Audits',
            passes: 'Passes',
            failures: 'Failures',
            refresh: 'Refresh',
            audit_all: 'Audit All',
            baselines_archive: 'Baselines Archive',
            monitors: 'Monitors & Cron',
            add_target: 'Add Target',
            quick_presets: 'Quick Presets:',
            studio_badge: 'Anti-Spoofing Studio',
            studio_title: 'Differential Verification',
            studio_desc: 'Audit any API provider against verified Ground Truth distributions (Ground Truth ◄—► Candidate)',
            tab_channel_a_saved: 'From Saved Baselines',
            tab_channel_a_live: 'Live API Endpoint',
            lbl_models_path: 'Models API Path',
            btn_capture_live_ref: 'Capture Baseline from this API',
            endpoints_title: 'Monitored Endpoints',
            endpoints_desc: 'Active LLM API targets audited against behavioral single-token baseline distributions',
            deep_dive_title: 'Audit Deep Dive',
            target_report: 'Target Verification Report',
            export_json: 'Export JSON',
            dispute_pack: 'Dispute Pack (.md)',
            print_pdf: 'Print / Save PDF',
            close_report: '✕ Close Report',
            verdict_pass: 'VERIFICATION PASSED — AUTHENTIC MODEL',
            verdict_pass_sub: 'All behavioral divergence metrics and single-token distributions match genuine baseline.',
            verdict_warn: 'SUSPICIOUS DIVERGENCE DETECTED (WARNING)',
            verdict_warn_sub: 'Divergence observed in semantic consistency or slight drift from baseline.',
            verdict_fail: 'MODEL SPOOFING OR SUBSTITUTION DETECTED (FAIL)',
            verdict_fail_sub: 'Single-token probability distribution significantly deviates from genuine baseline.',
            diag_title: 'Failure Diagnostics: Root Cause Analysis',
            diag_title_with_count: 'Failure Diagnostics: Root Cause Analysis ({count} discrepancies)',
            diag_sub: 'Itemized breakdown of failed checks, affected prompts, and discrepancies',
            diag_sub_detailed: 'Specific causes of divergence, affected prompts, and threshold discrepancies:',
            prompt_badge_label: 'Prompt',
            card_status_pass: 'VERIFIED PASS',
            card_status_warn: 'SUSPICIOUS WARN',
            card_status_fail: 'SPOOF DETECTED',
            card_status_none: 'NOT AUDITED',
            lbl_base_url: 'Base URL',
            lbl_api_key: 'API Key',
            lbl_active_baseline: 'Active Baseline',
            lbl_last_audit: 'Last Audit',
            btn_card_audit: 'Run Audit',
            btn_card_baseline: 'Capture Baseline',
            btn_card_budget: 'Budget',
            btn_card_history: 'History',
            btn_card_details: 'Details',
            l0_claim_match: 'Match',
            l0_claim_mismatch: 'Mismatch',
            assert_all_passed: 'All passed',
            assert_failed_cnt: '{cnt} failed',
            assert_passed_summary: '{passed}/{total} passed ({failCount} failed: {failList})',
            assert_all_passed_summary: 'All {passed}/{total} deterministic assertions passed.',
            methods: {
                quick_model: 'Model Claim Match',
                quick_fingerprint: 'System Fingerprint',
                quick_seed: 'Seed Determinism',
                jsd: 'One-Token JSD',
                latency_tps: 'TPS Throughput',
                latency_drift: 'Latency Shift',
                assertions: 'Deterministic Rules',
                embedding_cosine: 'Semantic Cosine',
                mmd_permutation: 'MMD Permutation',
            },
        }
    };

    async function loadLocaleBundle(lang) {
        if (I18N_CACHE[lang]) return I18N_CACHE[lang];
        try {
            const res = await fetch(`/api/locales/${lang}`);
            if (res.ok) {
                const data = await res.json();
                I18N_CACHE[lang] = data;
                return data;
            }
        } catch (e) {
            console.warn('Could not load remote locale, using bundled fallback', e);
        }
        I18N_CACHE[lang] = I18N_FALLBACK[lang] || I18N_FALLBACK['ru'];
        return I18N_CACHE[lang];
    }

    function t(key, params) {
        const dict = I18N_CACHE[currentLang] || I18N_FALLBACK[currentLang] || I18N_FALLBACK['en'];
        let val = dict[key];
        if (!val) {
            const fbDict = I18N_FALLBACK['en'] || {};
            val = fbDict[key] || key;
        }
        if (params && typeof val === 'string') {
            for (const [k, v] of Object.entries(params)) {
                val = val.replace(new RegExp(`\\{${k}\\}`, 'g'), v);
            }
        }
        return val;
    }

    function getMethodTitle(method) {
        const dict = I18N_CACHE[currentLang] || I18N_FALLBACK[currentLang] || I18N_FALLBACK['en'];
        const methods = dict.methods || I18N_FALLBACK['en'].methods;
        return (methods && methods[method]) || method;
    }

    async function toggleLanguage() {
        currentLang = currentLang === 'ru' ? 'en' : 'ru';
        localStorage.setItem('attest_lang', currentLang);
        await loadLocaleBundle(currentLang);
        applyTranslations();
        if (studioRefModel && studioRefModel.value) {
            await loadModelBaselines(studioRefModel.value);
        }
        updateStudioBaselineStatus();
        updateStudioFooter();
        await refreshDashboard();
        if (currentActiveRunId) {
            await loadRunDetails(currentActiveRunId);
        }
    }

    function applyTranslations() {
        const lang = currentLang;
        document.documentElement.lang = lang;
        if (currentLangLabel) currentLangLabel.textContent = lang.toUpperCase();
        document.title = t('title');

        const currentPort = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');

        // Declarative pass for text content
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            const translated = key === 'server_online' ? t(key, { port: currentPort }) : t(key);
            if (!translated || translated === key) return;

            const icon = el.querySelector('svg, .pulse-dot, .fetch-icon');
            if (icon) {
                const cloned = icon.cloneNode(true);
                el.replaceChildren(cloned, document.createTextNode(' ' + translated));
            } else {
                el.textContent = translated;
            }
        });

        // Declarative pass for tooltips
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const key = el.getAttribute('data-i18n-title');
            el.setAttribute('title', t(key));
        });

        // Declarative pass for placeholders
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const key = el.getAttribute('data-i18n-placeholder');
            el.setAttribute('placeholder', t(key));
        });

        if (currentTargets && currentTargets.length > 0) {
            renderTargets(currentTargets);
        }

        if (lastLoadedRunData) {
            renderAuditDetails(lastLoadedRunData);
        }
    }

    // Studio Elements & State
    let KNOWN_PROVIDERS = [];
    let currentTargets = [];
    let selectedBattery = 'frontier_probe';
    let currentModelBaselines = [];
    let allHistoricalBaselines = [];

    const studioRefModel = document.getElementById('studio-ref-model');
    const studioRefBaseline = document.getElementById('studio-ref-baseline');
    const studioBaselineRevBadge = document.getElementById('studio-baseline-rev-badge');
    const studioRefBaselineHint = document.getElementById('studio-ref-baseline-hint');
    const studioRefIndicator = document.getElementById('studio-ref-indicator');
    const studioRefTitle = document.getElementById('studio-ref-title');
    const studioRefSub = document.getElementById('studio-ref-sub');
    const btnStudioCaptureRef = document.getElementById('btn-studio-capture-ref');

    // Channel A Mode Tabs
    const tabChannelASaved = document.getElementById('tab-channel-a-saved');
    const tabChannelALive = document.getElementById('tab-channel-a-live');
    const panelChannelASaved = document.getElementById('panel-channel-a-saved');
    const panelChannelALive = document.getElementById('panel-channel-a-live');

    // Channel A Live Endpoint Elements
    const studioRefProvider = document.getElementById('studio-ref-provider');
    const studioRefUrl = document.getElementById('studio-ref-url');
    const studioRefModelCall = document.getElementById('studio-ref-model-call');
    const studioRefModelsPath = document.getElementById('studio-ref-models-path');
    const btnFetchRefModels = document.getElementById('btn-fetch-ref-models');
    const refRemoteModelsPickerWrapper = document.getElementById('ref-remote-models-picker-wrapper');
    const refRemoteModelsCountBadge = document.getElementById('ref-remote-models-count-badge');
    const studioRefModelSelect = document.getElementById('studio-ref-model-select');
    const refRemoteModelsDatalist = document.getElementById('ref-remote-models-datalist');
    const refEnvKeyBadge = document.getElementById('ref-env-key-badge');
    const refEnvKeyBadgeText = document.getElementById('ref-env-key-badge-text');
    const studioRefKey = document.getElementById('studio-ref-key');
    const btnToggleRefKey = document.getElementById('btn-toggle-ref-key');
    const btnCaptureLiveRef = document.getElementById('btn-capture-live-ref');

    // Channel B Candidate Elements
    const studioCandidateProvider = document.getElementById('studio-candidate-provider');
    const studioCandidateModelCall = document.getElementById('studio-candidate-model-call');
    const studioCandidateUrl = document.getElementById('studio-candidate-url');
    const studioCandidateModelsPath = document.getElementById('studio-candidate-models-path');
    const studioCandidateKey = document.getElementById('studio-candidate-key');
    const btnToggleCandidateKey = document.getElementById('btn-toggle-candidate-key');
    const btnBatteryQuick = document.getElementById('btn-battery-quick');
    const btnBatteryDeep = document.getElementById('btn-battery-deep');
    const studioActionInfo = document.getElementById('studio-action-info') || document.getElementById('studio-action-summary');
    const studioActionSummary = studioActionInfo;
    const lblCandidateProv = document.getElementById('lbl-candidate-prov');
    const btnStudioRun = document.getElementById('btn-studio-run');

    // Quick Chips, Remote Models & Env Key Elements
    const studioCandidateModelSelect = document.getElementById('studio-candidate-model-select');
    const remoteModelsPickerWrapper = document.getElementById('remote-models-picker-wrapper');
    const quickModelChips = document.querySelectorAll('.btn-model-chip');
    const remoteModelsDatalist = document.getElementById('remote-models-datalist');
    const remoteModelsCountBadge = document.getElementById('remote-models-count-badge');
    const btnFetchModels = document.getElementById('btn-fetch-models');
    const candidateModelHint = document.getElementById('candidate-model-hint');
    const envKeyBadge = document.getElementById('env-key-badge');
    const envKeyBadgeText = document.getElementById('env-key-badge-text');
    const candidateKeyHint = document.getElementById('candidate-key-hint');

    let isFetchingModels = false;
    let isFetchingRefModels = false;

    // API Helpers
    async function apiFetch(url, options = {}) {
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

    // ==========================================
    // Verification Studio Logic
    // ==========================================

    async function initStudio() {
        try {
            KNOWN_PROVIDERS = await apiFetch('/api/providers');
            if (studioCandidateProvider && KNOWN_PROVIDERS && KNOWN_PROVIDERS.length > 0) {
                const hasOpenrouter = KNOWN_PROVIDERS.some(p => p.id === 'openrouter');
                const defaultProvId = hasOpenrouter ? 'openrouter' : KNOWN_PROVIDERS[0].id;
                studioCandidateProvider.innerHTML = KNOWN_PROVIDERS.map(p => 
                    `<option value="${escapeHtml(p.id)}" ${p.id === defaultProvId ? 'selected' : ''}>${escapeHtml(p.name)}</option>`
                ).join('') + `<option value="__add_custom__">＋ Добавить провайдера...</option>`;
                
                onCandidateProviderChanged();
            }

            if (studioRefProvider && KNOWN_PROVIDERS && KNOWN_PROVIDERS.length > 0) {
                const hasOpenai = KNOWN_PROVIDERS.some(p => p.id === 'openai');
                const defaultRefProvId = hasOpenai ? 'openai' : KNOWN_PROVIDERS[0].id;
                studioRefProvider.innerHTML = KNOWN_PROVIDERS.map(p => 
                    `<option value="${escapeHtml(p.id)}" ${p.id === defaultRefProvId ? 'selected' : ''}>${escapeHtml(p.name)}</option>`
                ).join('');

                onRefProviderChanged();
            }

            const urlPresets = document.getElementById('url-presets');
            if (urlPresets && KNOWN_PROVIDERS) {
                urlPresets.innerHTML = KNOWN_PROVIDERS
                    .filter(p => p.base_url && p.id !== 'custom')
                    .map(p => `<option value="${escapeHtml(p.base_url)}">${escapeHtml(p.name)}</option>`)
                    .join('');
            }
        } catch (err) {
            console.error('Failed to load known providers:', err);
        }

        // Channel A Mode Tab Switching
        if (tabChannelASaved && tabChannelALive && panelChannelASaved && panelChannelALive) {
            tabChannelASaved.onclick = () => {
                tabChannelASaved.classList.add('active');
                tabChannelALive.classList.remove('active');
                panelChannelASaved.classList.remove('hidden');
                panelChannelALive.classList.add('hidden');
            };
            tabChannelALive.onclick = () => {
                tabChannelALive.classList.add('active');
                tabChannelASaved.classList.remove('active');
                panelChannelALive.classList.remove('hidden');
                panelChannelASaved.classList.add('hidden');
            };
        }

        try {
            const curatedGroups = await apiFetch('/api/curated-models');
            if (curatedGroups) {
                const vendorIcons = {
                    'Anthropic': '── Anthropic (Claude 5) ──',
                    'OpenAI': '── OpenAI (GPT-6 / o3) ──',
                    'Google Gemini': '── Google Gemini (3.8) ──',
                    'xAI Grok': '── xAI Grok (4.7) ──',
                    'DeepSeek': '── DeepSeek (V4.1) ──',
                    'Open-Weights & Ecosystem': '── Open-Weights & Ecosystem ──',
                    'Configured Endpoints (DB)': '── Настроенные в БД эндпоинты ──',
                };
                let selectHtml = '';
                let datalistHtml = '';
                for (const [groupName, models] of Object.entries(curatedGroups)) {
                    const label = vendorIcons[groupName] || `── ${groupName} ──`;
                    selectHtml += `<optgroup label="${escapeHtml(label)}">`;
                    for (const m of models) {
                        const isSelected = m.id === 'claude-sonnet-5' ? 'selected' : '';
                        selectHtml += `<option value="${escapeHtml(m.id)}" ${isSelected}>${escapeHtml(m.name)}</option>`;
                        datalistHtml += `<option value="${escapeHtml(m.id)}">${escapeHtml(m.name)}</option>`;
                    }
                    selectHtml += `</optgroup>`;
                }
                selectHtml += `<optgroup label="── Custom ──"><option value="__custom__">Своя модель...</option></optgroup>`;

                if (studioRefModel) {
                    studioRefModel.innerHTML = selectHtml;
                    studioRefModel.value = 'claude-sonnet-5';
                }
                const modelPresets = document.getElementById('model-presets');
                if (modelPresets) {
                    modelPresets.innerHTML = datalistHtml;
                }
            }
        } catch (err) {
            console.error('Failed to load curated models:', err);
        }

        // Channel A Live Listeners
        if (studioRefProvider) {
            studioRefProvider.onchange = () => onRefProviderChanged();
        }
        if (btnFetchRefModels) {
            btnFetchRefModels.onclick = () => fetchRefRemoteModels(true);
        }
        if (studioRefModelSelect) {
            studioRefModelSelect.onchange = () => {
                if (studioRefModelSelect.value && studioRefModelCall) {
                    studioRefModelCall.value = studioRefModelSelect.value;
                }
            };
        }
        if (btnToggleRefKey && studioRefKey) {
            btnToggleRefKey.onclick = () => {
                studioRefKey.type = studioRefKey.type === 'password' ? 'text' : 'password';
            };
        }
        if (btnCaptureLiveRef) {
            btnCaptureLiveRef.onclick = () => captureReferenceBaseline(true);
        }
        if (refEnvKeyBadge) {
            refEnvKeyBadge.onclick = () => {
                fetchRefRemoteModels(true);
            };
        }

        // Channel B Candidate Listeners
        if (studioCandidateModelSelect) {
            studioCandidateModelSelect.onchange = () => {
                const picked = studioCandidateModelSelect.value;
                if (picked && studioCandidateModelCall) {
                    studioCandidateModelCall.value = picked;
                    onCandidateModelCallChanged();
                }
            };
        }

        if (studioCandidateProvider) {
            studioCandidateProvider.onchange = () => onCandidateProviderChanged();
        }

        // Quick Model Chips click handler
        if (quickModelChips && quickModelChips.length > 0) {
            quickModelChips.forEach(chip => {
                chip.onclick = async () => {
                    quickModelChips.forEach(c => c.classList.remove('active'));
                    chip.classList.add('active');
                    const model = chip.dataset.model;

                    if (studioRefModel) {
                        let opt = Array.from(studioRefModel.options).find(o => o.value === model);
                        if (!opt) {
                            opt = document.createElement('option');
                            opt.value = model;
                            opt.textContent = `${model} (Preset)`;
                            studioRefModel.insertBefore(opt, studioRefModel.lastElementChild);
                        }
                        studioRefModel.value = model;
                        updateCandidateModelCall();
                        await loadModelBaselines(model);
                        updateStudioBaselineStatus();
                    }
                    updateStudioFooter();
                };
            });
        }

        if (btnFetchModels) {
            btnFetchModels.onclick = () => fetchRemoteModels(true);
        }

        if (envKeyBadge) {
            envKeyBadge.onclick = () => {
                const provId = studioCandidateProvider ? studioCandidateProvider.value : '';
                const prov = KNOWN_PROVIDERS.find(p => p.id === provId);
                if (prov && prov.env_key && prov.env_key.has_key) {
                    fetchRemoteModels(true);
                }
            };
        }

        if (studioCandidateKey) {
            studioCandidateKey.onblur = () => {
                if (studioCandidateKey.value.trim().length > 6) {
                    fetchRemoteModels(false);
                }
            };
        }

        if (studioRefModel) {
            studioRefModel.onchange = async () => {
                if (studioRefModel.value === '__custom__') {
                    const customName = prompt('Enter custom model identifier (e.g. gpt-5.7, claude-3-5-sonnet, mistral-large):');
                    if (customName && customName.trim()) {
                        const trimmed = customName.trim();
                        let opt = Array.from(studioRefModel.options).find(o => o.value === trimmed);
                        if (!opt) {
                            opt = document.createElement('option');
                            opt.value = trimmed;
                            opt.textContent = `Custom: ${trimmed}`;
                            studioRefModel.insertBefore(opt, studioRefModel.lastElementChild);
                        }
                        studioRefModel.value = trimmed;
                    } else {
                        studioRefModel.value = 'gpt-4o';
                    }
                }
                updateCandidateModelCall();
                await loadModelBaselines(studioRefModel.value);
                updateStudioBaselineStatus();

                // Sync quick chip active state
                quickModelChips.forEach(chip => {
                    if (chip.dataset.model === studioRefModel.value) {
                        chip.classList.add('active');
                    } else {
                        chip.classList.remove('active');
                    }
                });
            };
        }
        if (studioRefBaseline) {
            studioRefBaseline.onchange = () => onStudioBaselineChanged();
        }
        if (studioCandidateModelCall) {
            studioCandidateModelCall.oninput = () => onCandidateModelCallChanged();
            studioCandidateModelCall.onchange = () => onCandidateModelCallChanged();
        }
        if (studioCandidateModelSelect) {
            studioCandidateModelSelect.onchange = () => {
                if (studioCandidateModelSelect.value && studioCandidateModelCall) {
                    studioCandidateModelCall.value = studioCandidateModelSelect.value;
                    onCandidateModelCallChanged();
                }
            };
        }
        if (btnToggleCandidateKey && studioCandidateKey) {
            btnToggleCandidateKey.onclick = () => {
                if (studioCandidateKey.type === 'password') {
                    studioCandidateKey.type = 'text';
                    btnToggleCandidateKey.textContent = '🔒';
                } else {
                    studioCandidateKey.type = 'password';
                    btnToggleCandidateKey.textContent = '👁';
                }
            };
        }
        const batteryBtns = document.querySelectorAll('.battery-toggle-group .btn-battery');
        if (batteryBtns && batteryBtns.length > 0) {
            batteryBtns.forEach(btn => {
                btn.onclick = () => {
                    selectedBattery = btn.dataset.battery || 'quick';
                    batteryBtns.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    updateStudioFooter();
                };
            });
        }
        if (btnStudioCaptureRef) {
            btnStudioCaptureRef.onclick = () => captureReferenceBaseline(false);
        }
        if (btnStudioRun) {
            btnStudioRun.onclick = () => runStudioVerification();
        }

        if (inputFilterBaselines) {
            inputFilterBaselines.oninput = () => {
                const term = inputFilterBaselines.value.trim().toLowerCase();
                const filtered = allHistoricalBaselines.filter(b => 
                    b.model.toLowerCase().includes(term) ||
                    b.target_id.toLowerCase().includes(term) ||
                    (b.notes && b.notes.toLowerCase().includes(term)) ||
                    String(b.id).includes(term)
                );
                renderBaselinesArchiveTable(filtered);
            };
        }

        if (studioRefModel) {
            await loadModelBaselines(studioRefModel.value);
        }
        updateStudioFooter();
    }

    function onRefProviderChanged() {
        if (!studioRefProvider) return;
        const provId = studioRefProvider.value;
        const prov = KNOWN_PROVIDERS.find(p => p.id === provId);
        if (!prov) return;

        const defaultUrl = prov.base_url || prov.default_base_url;
        if (defaultUrl && studioRefUrl) {
            studioRefUrl.value = defaultUrl;
        }

        if (studioRefModelCall) {
            const prefix = prov.model_prefix || '';
            const curModel = studioRefModel ? studioRefModel.value : 'gpt-4o';
            studioRefModelCall.value = `${prefix}${curModel}`;
        }

        if (prov.env_key && prov.env_key.has_key) {
            if (refEnvKeyBadge) {
                refEnvKeyBadge.classList.remove('hidden');
                if (refEnvKeyBadgeText) {
                    refEnvKeyBadgeText.textContent = `Ключ подключен (${prov.env_key.preview})`;
                }
                refEnvKeyBadge.title = `Используется ключ из ${prov.env_key.source}`;
            }
        } else if (refEnvKeyBadge) {
            refEnvKeyBadge.classList.add('hidden');
        }

        fetchRefRemoteModels(false);
    }

    async function fetchRefRemoteModels(userClicked = false) {
        if (isFetchingRefModels) return;
        const baseUrl = (studioRefUrl ? studioRefUrl.value : '').trim();
        if (!baseUrl) {
            if (userClicked) alert('Пожалуйста, укажите URL эндпоинта для эталона.');
            return;
        }
        const key = (studioRefKey ? studioRefKey.value : '').trim();
        const provId = studioRefProvider ? studioRefProvider.value : '';
        const modelsPath = (studioRefModelsPath ? studioRefModelsPath.value : '').trim();

        if (btnFetchRefModels) {
            btnFetchRefModels.classList.add('fetching');
        }
        isFetchingRefModels = true;

        try {
            const payload = {
                base_url: baseUrl,
                api_key: key || null,
                provider_id: provId || null,
                models_path: modelsPath || null,
            };
            const res = await apiFetch('/api/fetch-remote-models', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            if (res && res.ok && Array.isArray(res.models)) {
                if (refRemoteModelsDatalist) {
                    refRemoteModelsDatalist.innerHTML = res.models
                        .map(m => `<option value="${escapeHtml(m)}">`)
                        .join('');
                }
                if (studioRefModelSelect && refRemoteModelsPickerWrapper) {
                    const curVal = (studioRefModelCall ? studioRefModelCall.value : '').toLowerCase();
                    let optionsHtml = `<option value="">▼ Выбрать из ${res.count} моделей API провайдера...</option>`;
                    for (const m of res.models) {
                        const isCur = m.toLowerCase() === curVal ? 'selected' : '';
                        optionsHtml += `<option value="${escapeHtml(m)}" ${isCur}>${escapeHtml(m)}</option>`;
                    }
                    studioRefModelSelect.innerHTML = optionsHtml;
                    refRemoteModelsPickerWrapper.classList.remove('hidden');
                }
                if (refRemoteModelsCountBadge) {
                    refRemoteModelsCountBadge.textContent = `${res.count} моделей API`;
                    refRemoteModelsCountBadge.classList.remove('hidden');
                }
            } else if (userClicked && res && !res.ok) {
                alert(res.error || 'Не удалось получить модели через API.');
            }
        } catch (err) {
            if (userClicked) {
                alert('Ошибка подключения к эталону: ' + err.message);
            }
        } finally {
            if (btnFetchRefModels) {
                btnFetchRefModels.classList.remove('fetching');
            }
            isFetchingRefModels = false;
        }
    }

    async function fetchRemoteModels(userClicked = false) {
        if (isFetchingModels) return;
        const baseUrl = (studioCandidateUrl ? studioCandidateUrl.value : '').trim();
        if (!baseUrl) {
            if (userClicked) alert('Please enter or select a Base URL first.');
            return;
        }
        const key = (studioCandidateKey ? studioCandidateKey.value : '').trim();
        const provId = studioCandidateProvider ? studioCandidateProvider.value : '';
        const modelsPath = (studioCandidateModelsPath ? studioCandidateModelsPath.value : '').trim();

        if (btnFetchModels) {
            btnFetchModels.classList.add('fetching');
        }
        isFetchingModels = true;

        try {
            const payload = {
                base_url: baseUrl,
                api_key: key || null,
                provider_id: provId || null,
                models_path: modelsPath || null,
            };
            const res = await apiFetch('/api/fetch-remote-models', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            if (res && res.ok && Array.isArray(res.models)) {
                if (remoteModelsDatalist) {
                    remoteModelsDatalist.innerHTML = res.models
                        .map(m => `<option value="${escapeHtml(m)}">`)
                        .join('');
                }
                if (studioCandidateModelSelect && remoteModelsPickerWrapper) {
                    const curVal = (studioCandidateModelCall ? studioCandidateModelCall.value : '').toLowerCase();
                    let optionsHtml = `<option value="">▼ Выбрать из ${res.count} моделей API провайдера...</option>`;
                    for (const m of res.models) {
                        const isCur = m.toLowerCase() === curVal ? 'selected' : '';
                        optionsHtml += `<option value="${escapeHtml(m)}" ${isCur}>${escapeHtml(m)}</option>`;
                    }
                    studioCandidateModelSelect.innerHTML = optionsHtml;
                    remoteModelsPickerWrapper.classList.remove('hidden');
                }
                if (remoteModelsCountBadge) {
                    remoteModelsCountBadge.textContent = `${res.count} моделей API`;
                    remoteModelsCountBadge.classList.remove('hidden');
                }
                if (candidateModelHint) {
                    candidateModelHint.textContent = `✓ Загружено ${res.count} моделей напрямую из ${escapeHtml(res.base_url)}/models`;
                }
            } else if (userClicked && res && !res.ok) {
                alert(res.error || 'Failed to retrieve models from provider.');
            }
        } catch (err) {
            if (userClicked) {
                alert('Connection error: ' + err.message);
            }
        } finally {
            if (btnFetchModels) {
                btnFetchModels.classList.remove('fetching');
            }
            isFetchingModels = false;
        }
    }

    function onCandidateModelCallChanged() {
        updateStudioFooter();
        if (!studioCandidateModelCall || !studioRefModel) return;
        const val = studioCandidateModelCall.value.trim();
        if (!val) return;

        // Clean provider prefixes like "openai/gpt-6-astra" -> "gpt-6-astra"
        let clean = val;
        if (clean.includes('/')) {
            clean = clean.split('/').pop();
        }
        clean = clean.replace(/-20\d{2}-\d{2}-\d{2}$/, '');

        // Sync dropdown picker if option exists
        if (studioCandidateModelSelect) {
            const hasOption = Array.from(studioCandidateModelSelect.options).some(o => o.value === val);
            if (hasOption) {
                studioCandidateModelSelect.value = val;
            }
        }

        // Match against existing options in studioRefModel
        const existingOpt = Array.from(studioRefModel.options).find(o => 
            o.value.toLowerCase() === clean.toLowerCase() || o.value.toLowerCase() === val.toLowerCase()
        );
        if (existingOpt && studioRefModel.value !== existingOpt.value) {
            studioRefModel.value = existingOpt.value;
            loadModelBaselines(existingOpt.value);
            updateStudioBaselineStatus();
        }

        // Sync quick chips
        quickModelChips.forEach(chip => {
            const chipModel = chip.dataset.model;
            if (chipModel === clean || chipModel === val) {
                chip.classList.add('active');
            } else {
                chip.classList.remove('active');
            }
        });
    }

    function onCandidateProviderChanged() {
        if (!studioCandidateProvider) return;
        const provId = studioCandidateProvider.value;

        // Handle "Add custom provider" option
        if (provId === '__add_custom__') {
            studioCandidateProvider.value = KNOWN_PROVIDERS[0]?.id || 'custom';
            openAddCustomProviderModal();
            return;
        }

        const prov = KNOWN_PROVIDERS.find(p => p.id === provId);
        if (!prov) return;

        const defaultUrl = prov.base_url || prov.default_base_url;
        if (defaultUrl && studioCandidateUrl) {
            studioCandidateUrl.value = defaultUrl;
        }

        // Check detected env/db key
        if (prov.env_key && prov.env_key.has_key) {
            if (envKeyBadge) {
                envKeyBadge.classList.remove('hidden');
                if (envKeyBadgeText) {
                    envKeyBadgeText.textContent = `✓ Ключ подключен (${prov.env_key.preview})`;
                }
                envKeyBadge.title = `Используется ключ из ${prov.env_key.source}`;
            }
            if (candidateKeyHint) {
                candidateKeyHint.textContent = `✓ Ключ найден в ${prov.env_key.source}. Поле ввода можно оставить пустым.`;
            }
        } else {
            if (envKeyBadge) {
                envKeyBadge.classList.add('hidden');
            }
            if (candidateKeyHint) {
                candidateKeyHint.textContent = 'Шифруется Fernet. Всегда маскируется в логах и UI.';
            }
        }

        updateCandidateModelCall();
        updateStudioFooter();

        // Auto-fetch remote models for known provider
        fetchRemoteModels(false);
    }

    function updateCandidateModelCall() {
        if (!studioCandidateModelCall || !studioRefModel) return;
        const provId = studioCandidateProvider ? studioCandidateProvider.value : '';
        const prov = KNOWN_PROVIDERS.find(p => p.id === provId);
        const prefix = (prov && prov.model_prefix) ? prov.model_prefix : '';
        const refModel = studioRefModel.value || 'claude-sonnet-5';

        studioCandidateModelCall.value = `${prefix}${refModel}`;
    }

    async function loadModelBaselines(model) {
        if (!studioRefBaseline) return;
        const pickerRow = document.getElementById('studio-snapshot-picker-row');
        try {
            const baselines = await apiFetch(`/api/baselines?model=${encodeURIComponent(model)}`);
            currentModelBaselines = baselines || [];

            if (!baselines || baselines.length === 0) {
                studioRefBaseline.innerHTML = `<option value="">${t('opt_no_baseline_snapshot_required')}</option>`;
                if (studioBaselineRevBadge) {
                    studioBaselineRevBadge.textContent = t('badge_none');
                    studioBaselineRevBadge.className = 'badge badge-neutral';
                }
                if (studioRefBaselineHint) {
                    studioRefBaselineHint.textContent = t('hint_capture_first');
                }
                // Hide picker — no snapshots yet
                if (pickerRow) pickerRow.classList.add('hidden');
            } else {
                const activeB = baselines.find(b => b.status === 'active');
                const autoLabel = t('opt_auto_latest_active', { id: activeB ? '#' + activeB.id : '#' + baselines[0].id });
                const optionsHtml = [
                    `<option value="">${autoLabel}</option>`,
                    ...baselines.map(b => {
                        const statusIcon = b.status === 'active'
                            ? t('opt_status_active')
                            : t('opt_status_archived');
                        const qLabel = t('queries_count');
                        const notePart = b.notes ? ` • ${b.notes}` : '';
                        // Show provider hostname for temporal comparison context
                        const provHost = (() => { try { return new URL(b.base_url).hostname; } catch { return b.target_id; } })();
                        return `<option value="${b.id}">#${b.id} ${statusIcon} ${formatDate(b.captured_at)} · ${provHost} · ${b.samples_count} ${qLabel}${notePart}</option>`;
                    })
                ].join('');

                studioRefBaseline.innerHTML = optionsHtml;
                if (studioBaselineRevBadge) {
                    studioBaselineRevBadge.textContent = activeB
                        ? t('badge_active_with_id', { id: activeB.id })
                        : t('badge_auto');
                    studioBaselineRevBadge.className = 'badge badge-emerald';
                }
                if (studioRefBaselineHint) {
                    studioRefBaselineHint.textContent = activeB
                        ? t('hint_active_snapshot_captured', { id: activeB.id, date: formatDate(activeB.captured_at) })
                        : t('hint_select_historical_rev');
                }
                // Show picker — snapshots available
                if (pickerRow) pickerRow.classList.remove('hidden');
            }
        } catch (err) {
            console.error('Failed to load model baselines:', err);
            if (pickerRow) pickerRow.classList.add('hidden');
        }
    }

    function onStudioBaselineChanged() {
        if (!studioRefBaseline) return;
        const selId = studioRefBaseline.value;
        if (!selId) {
            const active = currentModelBaselines.find(b => b.status === 'active');
            if (studioBaselineRevBadge) {
                studioBaselineRevBadge.textContent = active 
                    ? t('badge_active_with_id', { id: active.id })
                    : t('badge_auto');
                studioBaselineRevBadge.className = active ? 'badge badge-emerald' : 'badge badge-neutral';
            }
            if (studioRefBaselineHint) {
                studioRefBaselineHint.textContent = active 
                    ? t('hint_auto_uses_latest_active', { id: active.id })
                    : t('hint_auto_resolves_latest');
            }
        } else {
            const chosen = currentModelBaselines.find(b => String(b.id) === String(selId));
            if (chosen) {
                if (studioBaselineRevBadge) {
                    const isActive = chosen.status === 'active';
                    studioBaselineRevBadge.textContent = isActive 
                        ? t('badge_active_with_id', { id: chosen.id })
                        : t('badge_archive_with_id', { id: chosen.id });
                    studioBaselineRevBadge.className = isActive ? 'badge badge-emerald' : 'badge badge-neutral';
                }
                if (studioRefBaselineHint) {
                    studioRefBaselineHint.textContent = chosen.status === 'active'
                        ? t('hint_using_active_baseline', { id: chosen.id, date: formatDate(chosen.captured_at) })
                        : t('hint_drift_check_mode', { id: chosen.id, date: formatDate(chosen.captured_at) });
                }
            }
        }
        updateStudioBaselineStatus();
    }

    function updateStudioBaselineStatus() {
        if (!studioRefModel || !studioRefIndicator || !studioRefTitle || !studioRefSub) return;
        const selectedModel = studioRefModel.value;
        const explicitId = studioRefBaseline ? studioRefBaseline.value : null;

        if (explicitId) {
            const chosen = currentModelBaselines.find(b => String(b.id) === String(explicitId));
            if (chosen) {
                const isActive = chosen.status === 'active';
                studioRefIndicator.textContent = isActive ? '✓' : '📦';
                studioRefIndicator.className = isActive ? 'status-box-indicator ready' : 'status-box-indicator archived';
                studioRefTitle.textContent = isActive 
                    ? t('title_active_baseline_with_id', { id: chosen.id })
                    : t('title_historical_rev_with_id', { id: chosen.id });
                const qLabel = t('queries_count');
                const capturedLabel = t('lbl_captured');
                studioRefSub.textContent = `${capturedLabel}: ${formatDate(chosen.captured_at)} • ${chosen.samples_count} ${qLabel} • ${chosen.notes || chosen.target_id}`;
                studioRefSub.style.color = isActive ? '#34d399' : '#94a3b8';
                updateStudioFooter();
                return;
            }
        }

        const activeB = currentModelBaselines.find(b => b.status === 'active');
        const matchingTarget = currentTargets.find(t => t.model === selectedModel && t.active_baseline);

        if (activeB || matchingTarget) {
            const bId = activeB ? activeB.id : matchingTarget.active_baseline.id;
            const bVer = activeB ? activeB.battery_version : matchingTarget.active_baseline.battery_version;
            const bTarget = activeB ? activeB.target_id : (matchingTarget.active_baseline.is_inherited ? matchingTarget.active_baseline.source_target_id : matchingTarget.id);

            studioRefIndicator.textContent = '✓';
            studioRefIndicator.className = 'status-box-indicator ready';
            studioRefTitle.textContent = t('title_baseline_ready', { id: bId, version: bVer || 'v1' });
            studioRefSub.textContent = t('sub_baseline_verified_via_target', { target: bTarget });
            studioRefSub.style.color = '#34d399';
        } else {
            studioRefIndicator.textContent = '⚠';
            studioRefIndicator.className = 'status-box-indicator missing';
            studioRefTitle.textContent = t('title_no_baseline_found');
            studioRefSub.textContent = t('sub_click_snapshot_to_calibrate', { model: selectedModel });
            studioRefSub.style.color = '#f59e0b';
        }

        updateStudioFooter();
    }

    function updateStudioFooter() {
        const provId = studioCandidateProvider ? studioCandidateProvider.value : '';
        const prov = KNOWN_PROVIDERS.find(p => p.id === provId);
        const provName = prov ? prov.name : t('lbl_selected_provider');
        if (lblCandidateProv) lblCandidateProv.textContent = provName;

        const candModel = studioCandidateModelCall ? studioCandidateModelCall.value : '';
        const refModel = studioRefModel ? studioRefModel.value : '';
        const explicitId = studioRefBaseline ? studioRefBaseline.value : null;

        const battLabels = {
            'frontier_probe': t('batt_frontier_probe'),
            'quick': t('batt_quick'),
            'anti_spoof': t('batt_anti_spoof'),
            'reasoning': t('batt_reasoning'),
            'v1': t('batt_deep')
        };
        const battText = battLabels[selectedBattery] || selectedBattery;

        if (explicitId) {
            const chosen = currentModelBaselines.find(b => String(b.id) === String(explicitId));
            if (chosen && chosen.status !== 'active') {
                if (btnStudioRun) {
                    btnStudioRun.innerHTML = `
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="23 4 23 10 17 10"></polyline>
                            <polyline points="1 20 1 14 7 14"></polyline>
                            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                        </svg>
                        ${t('btn_run_model_drift_audit')}
                    `;
                }
                if (studioActionInfo) {
                    studioActionInfo.innerHTML = t('info_drift_audit', {
                        model: escapeHtml(candModel || refModel),
                        id: chosen.id,
                        date: formatDate(chosen.captured_at),
                        battery: battText
                    });
                }
                return;
            }
        }

        if (btnStudioRun) {
            btnStudioRun.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
                ${t('btn_run_anti_spoof_audit')}
            `;
        }
        if (studioActionInfo) {
            studioActionInfo.innerHTML = t('info_diff_audit', {
                model: escapeHtml(candModel || refModel),
                provider: escapeHtml(provName),
                battery: battText
            });
        }
    }

    async function captureReferenceBaseline() {
        const model = studioRefModel.value;
        const url = studioCandidateUrl.value.trim();
        const key = studioCandidateKey.value.trim();

        if (!url) {
            alert('Please specify a Base URL on the right before capturing a Ground Truth snapshot.');
            return;
        }

        const confirmMsg = t('confirm_capture_baseline', { model, url });
        if (!safeConfirm(confirmMsg)) return;

        try {
            const safeModel = model.replace(/[^a-zA-Z0-9_-]/g, '-');
            const targetId = `ref-${safeModel}`;

            // Ensure target is saved
            await apiFetch('/api/targets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: targetId,
                    model: model,
                    base_url: url,
                    key: key || null,
                    description: `Official Ground Truth reference for ${model}`
                })
            });

            // Trigger baseline
            const resp = await apiFetch(`/api/targets/${encodeURIComponent(targetId)}/baseline?battery=${selectedBattery}`, {
                method: 'POST'
            });
            startTaskPolling(resp.task_id, `Capturing Ground Truth Baseline: ${model}`);
            setTimeout(async () => {
                await loadModelBaselines(model);
            }, 3000);
        } catch (err) {
            alert(`Failed to capture baseline: ${err.message}`);
        }
    }

    async function runStudioVerification() {
        const candidateProv = studioCandidateProvider.value;
        const candidateUrl = studioCandidateUrl.value.trim();
        const candidateKey = studioCandidateKey.value.trim();
        const candidateModelCall = studioCandidateModelCall.value.trim();
        const refModel = studioRefModel.value;

        if (!candidateUrl) {
            alert('Please provide a valid Candidate Base URL.');
            return;
        }
        if (!candidateModelCall) {
            alert('Please specify the Candidate Model Wire Call.');
            return;
        }

        try {
            const explicitId = studioRefBaseline && studioRefBaseline.value ? parseInt(studioRefBaseline.value, 10) : null;
            const payload = {
                candidate_provider: candidateProv,
                candidate_url: candidateUrl,
                candidate_key: candidateKey || null,
                candidate_model_call: candidateModelCall,
                reference_model: refModel,
                battery: selectedBattery,
                save_target: true,
                baseline_id: explicitId
            };

            const res = await apiFetch('/api/studio/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const taskTitle = explicitId 
                ? `Model Drift Audit: ${candidateModelCall} vs Baseline #${explicitId}`
                : `Anti-Spoofing Audit: ${candidateModelCall} vs Ground Truth (${refModel})`;
            startTaskPolling(res.task_id, taskTitle);
        } catch (err) {
            if (err.message && err.message.includes('No active reference baseline found')) {
                const promptMsg = t('prompt_missing_baseline_capture', { model: refModel });
                const doCapture = safeConfirm(promptMsg);
                if (doCapture) {
                    await captureReferenceBaseline();
                }
            } else {
                alert('Verification failed to start: ' + err.message);
            }
        }
    }

    // Baselines Archive Modal Functions
    async function openBaselinesArchiveModal() {
        if (!modalBaselines) return;
        try {
            allHistoricalBaselines = await apiFetch('/api/baselines');
            renderBaselinesArchiveTable(allHistoricalBaselines);
            modalBaselines.classList.remove('hidden');
        } catch (err) {
            alert(`Failed to load baselines archive: ${err.message}`);
        }
    }

    function renderBaselinesArchiveTable(baselines) {
        if (!baselinesTbody) return;
        if (lblBaselinesCount) {
            lblBaselinesCount.textContent = t('snapshots_stored', { count: baselines.length });
        }

        if (!baselines || baselines.length === 0) {
            baselinesTbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#64748b; padding:2.5rem;">${t('no_baselines_captured')}</td></tr>`;
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
                        <strong style="color:#ffffff;">${escapeHtml(b.model)}</strong>
                        <div style="font-size:0.75rem; color:#64748b;">${escapeHtml(b.target_id)}</div>
                    </td>
                    <td>${formatDate(b.captured_at)}</td>
                    <td>
                        <span class="font-mono" style="color:#34d399;">${b.samples_count}</span> ${qLabel}
                        <span class="badge badge-neutral" style="font-size:0.7rem; margin-left:0.25rem;">${escapeHtml(b.battery_version)}</span>
                    </td>
                    <td><span class="target-status-pill ${statusClass}">${statusLabel}</span></td>
                    <td style="font-size:0.8rem; color:#94a3b8; max-width:220px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${escapeHtml(b.notes || '')}">
                        ${escapeHtml(b.notes || '—')}
                    </td>
                    <td>
                        <button class="btn btn-emerald-outline btn-sm btn-action-drift" data-id="${b.id}" data-model="${escapeHtml(b.model)}" data-target="${escapeHtml(b.target_id)}" data-url="${escapeHtml(b.base_url || '')}" title="${escapeHtml(btnDriftTooltip)}">
                            ${btnDriftText}
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        document.querySelectorAll('.btn-action-drift').forEach(btn => {
            btn.onclick = () => selectBaselineForDrift(btn.dataset.id, btn.dataset.model, btn.dataset.target, btn.dataset.url);
        });
    }

    async function selectBaselineForDrift(baselineId, model, targetId, baseUrl) {
        if (modalBaselines) modalBaselines.classList.add('hidden');

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

        const matchingTarget = currentTargets.find(t => t.id === targetId);
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

    // Schedules Management
    async function openSchedulesModal() {
        if (!modalSchedules) return;
        try {
            const [schedules, targets] = await Promise.all([
                apiFetch('/api/schedules'),
                apiFetch('/api/targets')
            ]);
            currentTargets = targets || [];

            if (selectSchedTarget) {
                selectSchedTarget.innerHTML = currentTargets.map(t => 
                    `<option value="${escapeHtml(t.id)}">${escapeHtml(t.id)} (${escapeHtml(t.model)})</option>`
                ).join('');
            }
            renderSchedulesTable(schedules);
            modalSchedules.classList.remove('hidden');
        } catch (err) {
            alert(`Failed to load schedules: ${err.message}`);
        }
    }

    function renderSchedulesTable(schedules) {
        if (!schedulesTbody) return;
        if (!schedules || schedules.length === 0) {
            schedulesTbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#64748b; padding:2.5rem;">${t('no_schedules_configured')}</td></tr>`;
            return;
        }

        schedulesTbody.innerHTML = schedules.map(s => {
            const statusBadge = s.enabled 
                ? `<span class="target-status-pill pass">${t('status_active')}</span>` 
                : `<span class="target-status-pill superseded">${t('status_paused')}</span>`;
            const battBadge = s.battery === 'quick' 
                ? `<span class="badge badge-neutral" style="font-size:0.7rem;">${t('badge_quick_short')}</span>` 
                : s.battery === 'anti_spoof'
                ? '<span class="badge badge-amber" style="font-size:0.7rem;">🎯 Anti-Spoof</span>'
                : s.battery === 'reasoning'
                ? '<span class="badge badge-purple" style="font-size:0.7rem;">🧠 Reasoning</span>'
                : s.battery === 'frontier_probe'
                ? '<span class="badge badge-emerald" style="font-size:0.7rem;">🚀 Frontier</span>'
                : `<span class="badge badge-emerald" style="font-size:0.7rem;">${t('badge_deep_short')}</span>`;
            const intervalText = t('every_hours', { hours: s.interval_hours });
            const runBtnTitle = t('title_sched_run_now');
            const delBtnTitle = t('title_sched_delete');
            const runBtnText = t('btn_sched_run');
            return `
                <tr>
                    <td><strong style="color:#ffffff;">${escapeHtml(s.target_id)}</strong></td>
                    <td class="font-mono" style="font-size:0.85rem; color:#60a5fa;">${escapeHtml(s.target_model)}</td>
                    <td>${intervalText}</td>
                    <td>${battBadge} ${statusBadge}</td>
                    <td style="font-size:0.8rem; color:#34d399;">${formatDate(s.next_run_at)}</td>
                    <td style="font-size:0.8rem; color:#94a3b8;">${formatDate(s.last_run_at)}</td>
                    <td>
                        <div style="display:flex; gap:0.4rem;">
                            <button class="btn btn-emerald-outline btn-sm btn-trigger-sched" data-id="${s.id}" data-target="${escapeHtml(s.target_id)}" title="${runBtnTitle}">
                                ${runBtnText}
                            </button>
                            <button class="btn btn-ghost btn-sm btn-delete-sched" data-id="${s.id}" title="${delBtnTitle}" style="color:#f87171;">
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

    // Refresh Dashboard
    async function refreshDashboard() {
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

    function renderStats(stats) {
        if (statTotalTargets) statTotalTargets.textContent = stats.total_targets;
        if (statActiveBaselines) statActiveBaselines.textContent = stats.active_baselines;
        if (statTotalAudits) statTotalAudits.textContent = stats.total_audits;
        if (statPasses) statPasses.textContent = stats.passes;
        if (statFailures) statFailures.textContent = stats.failures;
    }

    function renderTargets(targets) {
        currentTargets = targets || [];
        updateStudioBaselineStatus();
        if (!targetsGrid) return;
        if (!targets || targets.length === 0) {
            targetsGrid.innerHTML = `
                <div class="loading-placeholder">
                    <p style="font-size: 1.1rem; color: #cbd5e1; margin-bottom: 0.5rem;">${t('no_targets_configured')}</p>
                    <p style="font-size: 0.875rem; color: #64748b;">${t('click_add_target')}</p>
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
                        <span class="target-status-pill ${statusClass}">${statusLabel}</span>
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
                                <span style="font-size:0.75rem; color:#64748b">(${escapeHtml(tgt.key_source || 'none')})</span>
                            </span>
                        </div>
                        <div class="target-meta-item">
                            <span class="target-meta-label">${t('lbl_active_baseline')}</span>
                            <span class="target-meta-val">
                                ${hasBaseline 
                                    ? (tgt.active_baseline.is_inherited
                                        ? `<span style="color:#34d399; font-weight:600;" title="${t('tooltip_linked', { id: escapeHtml(tgt.active_baseline.source_target_id) })}">${t('badge_linked')} (${escapeHtml(tgt.active_baseline.source_target_id)})</span>`
                                        : `<span style="color:#10b981; font-weight:600;">${t('badge_ready')} (${escapeHtml(tgt.active_baseline.battery_version)})</span>`)
                                    : `<span style="color:#f59e0b; font-weight:600;" title="${t('tooltip_need_snapshot')}">${t('badge_need_snapshot')}</span>`}
                            </span>
                        </div>
                        ${latest ? `
                        <div class="target-meta-item">
                            <span class="target-meta-label">${t('lbl_last_audit')}</span>
                            <span class="target-meta-val" style="font-size: 0.8rem; color: #cbd5e1;">
                                ${formatDate(latest.finished_at || latest.started_at)}
                            </span>
                        </div>
                        ` : ''}
                    </div>

                    <div class="target-actions-bar">
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
                            <button class="btn btn-emerald-outline btn-sm btn-action-baseline" data-id="${escapeHtml(tgt.id)}" title="${t('title_action_capture_first')}">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
                                    <circle cx="12" cy="13" r="4"></circle>
                                </svg>
                                ${t('btn_card_baseline')}
                            </button>
                        `}
                        <button class="btn btn-ghost btn-sm btn-action-estimate" data-id="${escapeHtml(tgt.id)}" title="${t('title_action_estimate')}">
                            ${t('btn_card_budget')}
                        </button>
                        <button class="btn btn-ghost btn-sm btn-action-history" data-id="${escapeHtml(tgt.id)}" title="${t('title_action_history')}">
                            ${t('btn_card_history')}
                        </button>
                        ${latest ? `
                            <button class="btn btn-ghost btn-sm btn-action-view" data-run-id="${latest.id}" title="${t('title_action_details')}">
                                ${t('btn_card_details')}
                            </button>
                        ` : ''}
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

    // Baseline & Audit Triggers
    async function startBaseline(targetId) {
        if (!safeConfirm(t('confirm_capture_endpoint_baseline', { target: targetId }))) {
            return;
        }
        try {
            const resp = await apiFetch(`/api/targets/${encodeURIComponent(targetId)}/baseline`, { method: 'POST' });
            startTaskPolling(resp.task_id, `Capturing Baseline for '${targetId}'`);
        } catch (err) {
            alert(`Failed to start baseline capture: ${err.message}`);
        }
    }

    async function startAudit(targetId) {
        try {
            const resp = await apiFetch(`/api/targets/${encodeURIComponent(targetId)}/run`, { method: 'POST' });
            startTaskPolling(resp.task_id, `Auditing Endpoint '${targetId}'`);
        } catch (err) {
            alert(`Failed to start audit: ${err.message}`);
        }
    }

    async function deleteTarget(targetId) {
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

    // Task Polling
    function startTaskPolling(taskId, title) {
        if (pollInterval) clearInterval(pollInterval);
        activeTaskId = taskId;

        liveTaskBanner.classList.remove('hidden');
        liveTaskBanner.classList.remove('is-failed');
        taskProgressFill.style.backgroundColor = '';
        taskBannerTitle.textContent = title;
        taskBannerSub.textContent = t('task_connecting');
        taskBannerCounts.textContent = '0 / -- queries';
        taskBannerPct.textContent = '0%';
        taskProgressFill.style.width = '0%';

        if (btnCloseTaskBanner) {
            btnCloseTaskBanner.onclick = () => {
                liveTaskBanner.classList.add('hidden');
                liveTaskBanner.classList.remove('is-failed');
                taskProgressFill.style.backgroundColor = '';
            };
        }

        pollInterval = setInterval(async () => {
            try {
                const task = await apiFetch(`/api/tasks/${taskId}`);
                const total = task.total || 1;
                const completed = task.completed || 0;
                const pct = Math.min(100, Math.round((completed / total) * 100));

                taskBannerCounts.textContent = `${completed} / ${total} queries`;
                taskBannerPct.textContent = `${pct}%`;
                taskProgressFill.style.width = `${pct}%`;

                if (task.status === 'completed') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    taskBannerTitle.textContent = `${t('task_completed')}: ${title}`;
                    taskBannerSub.textContent = task.result ? `Verdict: ${task.result.verdict} | Duration: ${task.result.duration_s}s` : 'Done successfully.';
                    taskProgressFill.style.width = '100%';

                    setTimeout(() => {
                        if (!liveTaskBanner.classList.contains('is-failed')) {
                            liveTaskBanner.classList.add('hidden');
                        }
                    }, 6000);

                    await refreshDashboard();
                    if (studioRefModel) {
                        await loadModelBaselines(studioRefModel.value);
                        updateStudioBaselineStatus();
                    }

                    // If it was an audit with a run_id, open report directly
                    if (task.result && task.result.run_id) {
                        await loadRunDetails(task.result.run_id);
                    }
                } else if (task.status === 'failed') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    taskBannerTitle.textContent = `${t('task_failed')}: ${title}`;
                    taskBannerSub.textContent = task.error || 'API Error';
                    taskProgressFill.style.backgroundColor = '#ef4444';
                    liveTaskBanner.classList.add('is-failed');
                    // Retain failed banner persistently so user can inspect and copy the error!
                }
            } catch (err) {
                console.error('Polling error:', err);
            }
        }, 750);
    }

    // Run Details Deep Dive
    async function loadRunDetails(runId) {
        try {
            currentActiveRunId = runId;
            const data = await apiFetch(`/api/runs/${runId}?locale=${currentLang}`);
            renderAuditDetails(data);
            auditDetailsSection.classList.remove('hidden');
            auditDetailsSection.scrollIntoView({ behavior: 'smooth' });
        } catch (err) {
            alert(`Failed to load run details: ${err.message}`);
        }
    }

    function renderAuditDetails(data) {
        lastLoadedRunData = data;
        const { run, target, baseline, scores } = data;

        detailTargetTitle.textContent = `${t('target_report')}: ${target ? target.id : run.target_id} (${target ? target.model : ''})`;
        detailTokens.textContent = (run.total_tokens || 0).toLocaleString();
        
        let dur = 0;
        if (run.started_at && run.finished_at) {
            dur = Math.round((new Date(run.finished_at) - new Date(run.started_at)) / 1000);
        }
        detailDuration.textContent = `${dur}s`;

        if (detailVerdictBanner) {
            detailVerdictBanner.className = `verdict-banner verdict-${run.verdict.toLowerCase()}`;
        }

        const diagnostics = data.failure_diagnostics || [];

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
                const word = currentLang === 'ru' 
                    ? (run.verdict === 'WARN' ? `(предупреждений: ${diagCount})` : `(критических сбоев: ${diagCount})`)
                    : (run.verdict === 'WARN' ? `(${diagCount} warnings)` : `(${diagCount} critical failures)`);
                clean += currentLang === 'ru' 
                    ? ` ${word}. Детализация приведена в блоке ниже.`
                    : ` ${word}. Specific failures are detailed below.`;
            }
            return clean;
        }

        if (run.verdict === 'PASS') {
            detailVerdictIcon.textContent = '🛡️';
            detailVerdictHeading.textContent = t('verdict_pass');
            detailVerdictSub.textContent = formatVerdictSub(run, currentLang, diagnostics);
        } else if (run.verdict === 'WARN') {
            detailVerdictIcon.textContent = '⚠️';
            detailVerdictHeading.textContent = t('verdict_warn');
            detailVerdictSub.textContent = formatVerdictSub(run, currentLang, diagnostics);
        } else {
            detailVerdictIcon.textContent = '🚨';
            detailVerdictHeading.textContent = t('verdict_fail');
            detailVerdictSub.textContent = formatVerdictSub(run, currentLang, diagnostics);
        }

        // Failure Diagnostics Box
        if (detailFailureDiagnostics) {
            if (diagnostics.length > 0) {
                detailFailureDiagnostics.classList.remove('hidden');
                if (failureDiagTitle) {
                    failureDiagTitle.textContent = t('diag_title_with_count', { count: diagnostics.length });
                }
                if (failureDiagSub) {
                    failureDiagSub.textContent = t('diag_sub_detailed');
                }
                if (failureDiagList) {
                    failureDiagList.innerHTML = diagnostics.map((d, idx) => {
                        const promptBadge = d.prompt_id ? `<span class="badge badge-neutral" style="font-size:0.75rem;margin-left:0.5rem;">${t('prompt_badge_label')} #${d.prompt_id}</span>` : '';
                        const preview = d.prompt_preview ? `<div class="failure-diag-prompt-preview">«${escapeHtml(d.prompt_preview)}»</div>` : '';
                        const localizedTitle = getMethodTitle(d.method) || d.title;
                        const vBadge = d.verdict ? d.verdict.toUpperCase() : 'FAIL';
                        return `
                            <div class="failure-diag-item">
                                <div class="failure-diag-item-header">
                                    <span style="color:#ef4444;font-weight:700;">#${idx + 1}</span>
                                    <span class="failure-diag-item-title">${escapeHtml(localizedTitle)}</span>
                                    ${promptBadge}
                                    <span class="badge badge-${vBadge.toLowerCase()}" style="margin-left:auto;">${escapeHtml(vBadge)}</span>
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

        // Tiers
        const l0Score = scores.find(s => s.method.startsWith('quick_') || s.method.includes('fingerprint'));
        const l1Score = scores.find(s => s.method === 'jsd' || s.method.includes('jsd'));
        const l15Tps = scores.find(s => s.method === 'latency_tps');
        const l15Lat = scores.find(s => s.method === 'latency_drift');
        const assertScore = scores.find(s => s.method === 'assertions');
        const l2Score = scores.find(s => s.method === 'embedding_cosine' || s.method.includes('embedding'));
        const l3Score = scores.find(s => s.method === 'mmd_permutation' || s.method.includes('mmd'));

        setTierDisplay(tierStatusL0, l0Score);
        if (l0Score) {
            l0ClaimVal.textContent = l0Score.verdict === 'PASS' ? t('l0_claim_match') : t('l0_claim_mismatch');
            l0FpVal.textContent = l0Score.details?.fingerprint_observed || (l0Score.verdict === 'PASS' ? t('fingerprint_match') : t('fingerprint_diff'));
        } else {
            l0ClaimVal.textContent = '—';
            l0FpVal.textContent = '—';
        }

        setTierDisplay(tierStatusL1, l1Score);
        if (l1Score && l1Score.value !== null && l1Score.verdict !== 'SKIP') {
            l1JsdVal.textContent = l1Score.value.toFixed(4);
        } else {
            l1JsdVal.textContent = l1Score?.verdict === 'SKIP' ? t('val_skipped') : '—';
        }

        const l15Combined = l15Tps || l15Lat;
        setTierDisplay(tierStatusL15, l15Combined);
        if (l15Tps && l15Tps.verdict !== 'SKIP') {
            const dir = l15Tps.details?.direction === 'faster' ? '↑' : (l15Tps.details?.direction === 'slower' ? '↓' : '');
            l15TpsVal.textContent = `${(l15Tps.value * 100).toFixed(1)}% ${dir}`.trim();
        } else {
            l15TpsVal.textContent = l15Tps?.verdict === 'SKIP' ? t('val_skipped') : '—';
        }
        if (l15Lat && l15Lat.verdict !== 'SKIP' && l15Lat.details?.run_latency_ms?.median) {
            l15LatVal.textContent = `${Math.round(l15Lat.details.run_latency_ms.median)}ms`;
        } else {
            l15LatVal.textContent = '—';
        }

        setTierDisplay(tierStatusAssert, assertScore);
        if (assertScore && assertScore.details) {
            const passPct = Math.round((assertScore.value || 0) * 100);
            const passed = assertScore.details.passed_assertions || 0;
            const total = assertScore.details.total_assertions || 0;
            assertRateVal.textContent = `${passed}/${total} (${passPct}%)`;
            const failCnt = assertScore.details.failure_count || 0;
            assertStatusVal.textContent = failCnt > 0 
                ? t('assert_failed_cnt', { cnt: failCnt })
                : t('assert_all_passed');
            assertStatusVal.style.color = failCnt > 0 ? '#f87171' : '#34d399';
        } else {
            assertRateVal.textContent = '—';
            assertStatusVal.textContent = '—';
            assertStatusVal.style.color = '';
        }

        setTierDisplay(tierStatusL2, l2Score);
        if (l2Score && l2Score.value !== null && l2Score.verdict !== 'SKIP') {
            l2SimVal.textContent = l2Score.value.toFixed(4);
        } else {
            l2SimVal.textContent = l2Score?.verdict === 'SKIP' ? t('val_skipped') : '—';
        }

        setTierDisplay(tierStatusL3, l3Score);
        if (l3Score && l3Score.value !== null && l3Score.verdict !== 'SKIP') {
            l3PvalVal.textContent = l3Score.value.toFixed(4);
        } else {
            l3PvalVal.textContent = t('val_skipped');
        }

        // Table
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
                    <td style="font-size:0.775rem; color:#94a3b8;">${escapeHtml(detailsStr)}</td>
                </tr>
            `;
        }).join('');

        // Visual Model Response Comparison: Candidate vs Baseline
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
                                <span class="prov-kv-value font-mono" style="color: #34d399; font-weight: 600;">🛡️ ${escapeHtml(b.routing_proof.endpoint_slug)}</span>
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
                                <span class="prov-kv-value font-mono" style="color: ${hasWireMismatch ? '#f87171' : '#38bdf8'}; font-weight: 700;">${escapeHtml(firstCandidateWire)}</span>
                            </div>
                            ${c.routing_proof?.endpoint_slug ? `
                            <div class="prov-kv-row">
                                <span class="prov-kv-label">Proof-of-Routing:</span>
                                <span class="prov-kv-value font-mono" style="color: #34d399; font-weight: 600;">🛡️ ${escapeHtml(c.routing_proof.endpoint_slug)}</span>
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
                                ${item.assertion_failures.map(f => `<div>❌ <strong>${escapeHtml(f.assertion)}</strong>: ${escapeHtml(f.message || f.expected || '')}</div>`).join('')}
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
                                        <span class="font-mono" style="font-size:0.75rem; color:${item.model_mismatch ? '#f87171' : '#60a5fa'}; font-weight:700;">${escapeHtml(item.candidate?.wire_model || '—')}</span>
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

    function applySamplesFilter(filterType) {
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

    // Modal: Cost Estimate
    async function openEstimateModal(targetId) {
        try {
            const est = await apiFetch(`/api/targets/${encodeURIComponent(targetId)}/estimate?battery=${encodeURIComponent(selectedBattery)}`);
            estimateModalTitle.textContent = t('modal_estimate_title_target', { target: targetId, battery: est.battery_version });
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
                <div style="background: rgba(99, 102, 241, 0.08); border: 1px solid rgba(99, 102, 241, 0.2); border-radius: 8px; padding: 1rem; font-size: 0.875rem;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                        <span>${t('lbl_est_cost_rates')}</span>
                        <strong style="color: #10b981; font-size: 1.1rem;">~$${est.est_cost_usd} USD</strong>
                    </div>
                    <p style="color: #94a3b8; font-size: 0.775rem; margin: 0;">
                        ${t('desc_est_probes')}
                    </p>
                </div>
            `;
            modalEstimate.classList.remove('hidden');
        } catch (err) {
            alert(t('err_failed_estimate', { error: err.message }));
        }
    }

    // Modal: Run History
    async function openHistoryModal(targetId) {
        try {
            const runs = await apiFetch(`/api/targets/${encodeURIComponent(targetId)}/runs`);
            historyModalTitle.textContent = t('modal_history_title_target', { target: targetId });
            if (!runs || runs.length === 0) {
                historyTbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:#64748b; padding:2rem;">${t('no_history_runs')}</td></tr>`;
            } else {
                historyTbody.innerHTML = runs.map(r => `
                    <tr>
                        <td>#${r.id}</td>
                        <td>${formatDate(r.finished_at || r.started_at)}</td>
                        <td>${escapeHtml(r.baseline_id || '—')}</td>
                        <td><span class="target-status-pill ${r.verdict.toLowerCase()}">${escapeHtml(r.verdict)}</span></td>
                        <td>
                            <button class="btn btn-outline btn-sm" onclick="AttestApp.inspectRun(${r.id})">
                                ${t('btn_inspect_run')}
                            </button>
                        </td>
                    </tr>
                `).join('');
            }
            modalHistory.classList.remove('hidden');
        } catch (err) {
            alert(t('err_failed_history', { error: err.message }));
        }
    }

    // Modal close hooks
    btnCloseEstimateModal.onclick = () => modalEstimate.classList.add('hidden');
    btnOkEstimate.onclick = () => modalEstimate.classList.add('hidden');

    btnCloseHistoryModal.onclick = () => modalHistory.classList.add('hidden');
    btnOkHistory.onclick = () => modalHistory.classList.add('hidden');

    if (btnOpenBaselinesModal) btnOpenBaselinesModal.onclick = () => openBaselinesArchiveModal();
    if (btnCloseBaselinesModal) btnCloseBaselinesModal.onclick = () => modalBaselines.classList.add('hidden');
    if (btnCloseBaselinesModalFooter) btnCloseBaselinesModalFooter.onclick = () => modalBaselines.classList.add('hidden');

    if (btnOpenSchedulesModal) btnOpenSchedulesModal.onclick = () => openSchedulesModal();
    if (btnCloseSchedulesModal) btnCloseSchedulesModal.onclick = () => modalSchedules.classList.add('hidden');
    if (btnCloseSchedulesModalFooter) btnCloseSchedulesModalFooter.onclick = () => modalSchedules.classList.add('hidden');

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

    if (btnExportJson) {
        btnExportJson.onclick = () => {
            if (!currentActiveRunId) {
                alert('Select an audit run first.');
                return;
            }
            window.location.href = `/api/runs/${currentActiveRunId}/dispute-pack?format=json&download=true`;
        };
    }
    if (btnExportDisputeMd) {
        btnExportDisputeMd.onclick = () => {
            if (!currentActiveRunId) {
                alert('Select an audit run first.');
                return;
            }
            window.location.href = `/api/runs/${currentActiveRunId}/dispute-pack?format=md&download=true`;
        };
    }
    if (btnExportHtml) {
        btnExportHtml.onclick = () => {
            if (!currentActiveRunId) {
                alert('Select an audit run first.');
                return;
            }
            window.open(`/api/runs/${currentActiveRunId}/export?format=html&locale=${currentLang}`, '_blank');
        };
    }

    btnCloseDetails.onclick = () => auditDetailsSection.classList.add('hidden');
    btnRefresh.onclick = () => refreshDashboard();

    if (btnFilterAll) {
        btnFilterAll.onclick = () => applySamplesFilter('all');
    }
    if (btnFilterDiff) {
        btnFilterDiff.onclick = () => applySamplesFilter('diff');
    }
    if (btnFilterMatch) {
        btnFilterMatch.onclick = () => applySamplesFilter('match');
    }

    const btnAuditAll = document.getElementById('btn-audit-all');
    if (btnAuditAll) {
        btnAuditAll.onclick = async () => {
            if (!safeConfirm('Run verification audits across all ready targets?')) return;
            try {
                const res = await apiFetch('/api/audit-all', { method: 'POST' });
                if (res.triggered && res.triggered.length > 0) {
                    startTaskPolling(res.triggered[0].task_id, `Auditing All (${res.count} targets queued)`);
                } else {
                    alert('No ready targets found with an active or linked baseline.');
                }
            } catch (err) {
                alert('Failed to trigger audit all: ' + err.message);
            }
        };
    }

    // Helper utilities
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function formatDate(dateStr) {
        if (!dateStr) return '—';
        try {
            const d = new Date(dateStr);
            return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch {
            return dateStr;
        }
    }

    // ============================================================
    // Custom Provider Modal (app.js inline version)
    // ============================================================
    function openAddCustomProviderModal() {
        document.getElementById('custom-provider-modal')?.remove();
        const modal = document.createElement('div');
        modal.id = 'custom-provider-modal';
        modal.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;';
        modal.innerHTML = `
            <div style="background:var(--bg-secondary,#1e1e2e);border:1px solid var(--border,#333);border-radius:12px;
                        padding:28px 32px;width:480px;max-width:95vw;box-shadow:0 8px 40px rgba(0,0,0,0.5);">
                <h3 style="margin:0 0 20px;font-size:1rem;font-weight:600;color:var(--text-primary,#e0e0e0);">＋ Добавить провайдера</h3>
                <div style="display:flex;flex-direction:column;gap:12px;">
                    <label style="font-size:.75rem;font-weight:600;letter-spacing:.08em;color:var(--text-secondary,#999);text-transform:uppercase;">
                        Название *
                        <input id="cpm-name" type="text" placeholder="Мой Gateway" style="display:block;width:100%;margin-top:4px;padding:8px 10px;border-radius:6px;border:1px solid var(--border,#444);background:var(--bg-input,#13131f);color:var(--text-primary,#e0e0e0);font-size:.875rem;box-sizing:border-box;">
                    </label>
                    <label style="font-size:.75rem;font-weight:600;letter-spacing:.08em;color:var(--text-secondary,#999);text-transform:uppercase;">
                        URL Эндпоинта *
                        <input id="cpm-url" type="url" placeholder="https://api.example.com/v1" style="display:block;width:100%;margin-top:4px;padding:8px 10px;border-radius:6px;border:1px solid var(--border,#444);background:var(--bg-input,#13131f);color:var(--text-primary,#e0e0e0);font-family:monospace;font-size:.875rem;box-sizing:border-box;">
                    </label>
                    <label style="font-size:.75rem;font-weight:600;letter-spacing:.08em;color:var(--text-secondary,#999);text-transform:uppercase;">
                        API Ключ (опционально)
                        <input id="cpm-key" type="password" placeholder="sk-..." style="display:block;width:100%;margin-top:4px;padding:8px 10px;border-radius:6px;border:1px solid var(--border,#444);background:var(--bg-input,#13131f);color:var(--text-primary,#e0e0e0);font-family:monospace;font-size:.875rem;box-sizing:border-box;">
                    </label>
                    <label style="font-size:.75rem;font-weight:600;letter-spacing:.08em;color:var(--text-secondary,#999);text-transform:uppercase;">
                        Префикс модели (опционально)
                        <input id="cpm-prefix" type="text" placeholder="openai/ — если нужен" style="display:block;width:100%;margin-top:4px;padding:8px 10px;border-radius:6px;border:1px solid var(--border,#444);background:var(--bg-input,#13131f);color:var(--text-primary,#e0e0e0);font-family:monospace;font-size:.875rem;box-sizing:border-box;">
                    </label>
                    <label style="font-size:.75rem;font-weight:600;letter-spacing:.08em;color:var(--text-secondary,#999);text-transform:uppercase;">
                        Описание
                        <input id="cpm-desc" type="text" placeholder="Необязательное описание" style="display:block;width:100%;margin-top:4px;padding:8px 10px;border-radius:6px;border:1px solid var(--border,#444);background:var(--bg-input,#13131f);color:var(--text-primary,#e0e0e0);font-size:.875rem;box-sizing:border-box;">
                    </label>
                </div>
                <div id="cpm-error" style="color:#f97316;font-size:.8rem;margin-top:8px;display:none;"></div>
                <div style="display:flex;gap:10px;margin-top:20px;justify-content:flex-end;">
                    <button id="cpm-cancel" style="padding:8px 18px;border-radius:6px;border:1px solid var(--border,#444);background:transparent;color:var(--text-secondary,#999);cursor:pointer;font-size:.875rem;">Отмена</button>
                    <button id="cpm-save" style="padding:8px 20px;border-radius:6px;border:none;background:var(--accent,#6366f1);color:#fff;cursor:pointer;font-size:.875rem;font-weight:600;">Сохранить</button>
                </div>
            </div>`;
        document.body.appendChild(modal);

        const nameEl = modal.querySelector('#cpm-name');
        const urlEl  = modal.querySelector('#cpm-url');
        const keyEl  = modal.querySelector('#cpm-key');
        const prefixEl = modal.querySelector('#cpm-prefix');
        const descEl = modal.querySelector('#cpm-desc');
        const errEl  = modal.querySelector('#cpm-error');

        modal.querySelector('#cpm-cancel').onclick = () => modal.remove();
        modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });

        modal.querySelector('#cpm-save').onclick = async () => {
            const name = nameEl.value.trim();
            const url  = urlEl.value.trim();
            if (!name || !url) {
                errEl.textContent = 'Название и URL обязательны.';
                errEl.style.display = 'block';
                return;
            }
            try {
                const saved = await apiFetch('/api/providers/custom', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name,
                        base_url: url,
                        api_key: keyEl.value.trim() || null,
                        model_prefix: prefixEl.value.trim() || null,
                        description: descEl.value.trim() || null,
                    }),
                });
                const existing = KNOWN_PROVIDERS.findIndex(p => p.id === saved.id);
                if (existing >= 0) KNOWN_PROVIDERS[existing] = saved;
                else KNOWN_PROVIDERS.push(saved);

                if (studioCandidateProvider) {
                    studioCandidateProvider.innerHTML = KNOWN_PROVIDERS.map(p =>
                        `<option value="${escapeHtml(p.id)}" ${p.id === saved.id ? 'selected' : ''}>${escapeHtml(p.name)}</option>`
                    ).join('') + `<option value="__add_custom__">＋ Добавить провайдера...</option>`;
                    studioCandidateProvider.value = saved.id;
                }
                if (studioCandidateUrl) studioCandidateUrl.value = saved.base_url;
                onCandidateProviderChanged();
                modal.remove();
            } catch (err) {
                errEl.textContent = 'Ошибка сохранения: ' + err.message;
                errEl.style.display = 'block';
            }
        };
        nameEl.focus();
    }

    // Expose inspectRun globally for inline buttons
    window.AttestApp = {
        inspectRun: (runId) => {
            modalHistory.classList.add('hidden');
            loadRunDetails(runId);
        }
    };

    if (btnLangToggle) {
        btnLangToggle.onclick = () => toggleLanguage();
    }

    // Initial load
    initStudio();
    applyTranslations();
    loadLocaleBundle(currentLang).then(() => applyTranslations());
    refreshDashboard();
})();

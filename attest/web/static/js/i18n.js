/**
 * Attest Web Dashboard — Internationalization (i18n) Engine
 */

let currentLang = 'ru';
const I18N_CACHE = {};

const I18N_FALLBACK = {
    ru: {
        title: 'Attest — Шлюз верификации и защиты от подмены нейросетей',
        brand_sub: 'Шлюз верификации LLM',
        server_online: 'Порт {port} • Онлайн',
        theme_light: 'Светлая',
        theme_dark: 'Тёмная',
        nav_workbench: 'Верификационный стенд',
        nav_antispoof: 'Антиспуфинг & Fingerprinting',
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
        copy_for_ai: 'Скопировать для AI',
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
        btn_card_details: 'Результаты',
        btn_card_results: 'Результаты',
        l0_claim_match: 'Совпадает',
        l0_claim_mismatch: 'Не совпадает',
        assert_all_passed: 'Все пройдены',
        assert_failed_cnt: 'Провалено: {cnt}',
        assert_passed_summary: '{passed}/{total} пройдено ({failCount} сбоев: {failList})',
        assert_all_passed_summary: 'Все {passed}/{total} правил пройдены.',
        btn_run_anti_spoof_audit: 'Запустить аудит на подмену',
        btn_run_model_drift_audit: 'Проверить дрейф модели',
        title_no_baseline_found: 'Эталон не найден',
        sub_click_snapshot_to_calibrate: 'Нажмите «Снять эталон», чтобы зафиксировать сигнатуру',
        title_baseline_ready: 'Активный эталон готов (#{id}, {version})',
        sub_baseline_verified_via_target: 'Верифицирован через таргет {target}',
        info_diff_audit: 'Дифференциальный аудит: проверка {model} через {provider} против эталона • Пакет: {battery}',
        info_drift_audit: 'Аудит дрейфа: сверка {model} с ревизией #{id} от {date} • Пакет: {battery}',
        batt_frontier_probe: 'Frontier Probe (5с)',
        batt_quick: 'Быстрый аудит (10с)',
        batt_anti_spoof: 'Anti-Spoof',
        batt_reasoning: 'Reasoning & CoT',
        batt_deep: 'Полный аудит (v1)',
        btn_battery_level1: '1 · Экспресс',
        btn_battery_level2: '2 · Стандарт',
        btn_battery_level3: '3 · Усиленный',
        btn_battery_level4: '4 · Максимум',
        batt_level1: 'Уровень 1 · Экспресс',
        batt_level2: 'Уровень 2 · Стандарт',
        batt_level3: 'Уровень 3 · Усиленный',
        batt_level4: 'Уровень 4 · Максимум',
        batt_iris: 'IRIS · случайные строки',
        batt_all_tests: 'Все тесты',
        opt_other_batteries: 'Отдельные наборы…',
        meta_run: 'Прогон',
        meta_candidate: 'Кандидат',
        meta_reference: 'Эталон',
        meta_captured: 'снят',
        time_just_now: 'только что',
        time_min_ago: '{n} мин назад',
        time_hours_ago: '{n} ч назад',
        time_days_ago: '{n} дн назад',
        warn_battery_mismatch: "Эталон #{id} снят набором {version} и не покрывает выбранный набор. Выберите «{fix}» или снимите эталон этим набором.",
        title_active_baseline_with_id: 'Активный эталон #{id}',
        title_historical_rev_with_id: 'Архивная ревизия #{id}',
        queries_count: 'запросов',
        lbl_captured: 'Снят',
        lbl_selected_provider: 'выбранный провайдер',
        badge_active_with_id: 'Активный #{id}',
        badge_archive_with_id: 'Архив #{id}',
        badge_auto: 'Авто',
        hint_auto_uses_latest_active: 'Используется последний активный эталон (#{id})',
        hint_auto_resolves_latest: 'Автовыбор актуального эталона',
        hint_using_active_baseline: 'Используется активный эталон #{id} от {date}',
        hint_drift_check_mode: 'Проверка дрейфа относительно ревизии #{id} от {date}',
        method_title_assertions: 'Детерминированные правила',
        method_title_cosine: 'Семантическое сходство',
        method_title_fingerprint: 'Системный отпечаток (Fingerprint)',
        method_title_latency_drift: 'Задержка и TTFT',
        method_title_latency_tps: 'Скорость генерации (TPS)',
        method_title_mmd: 'MMD тест идентичности',
        method_title_jsd: 'One-Token JSD (Логиты)',
        alert_select_run: 'Сначала выберите или запустите проверку эндпоинта.',
        btn_inspect_run: 'Результаты',
        copy_for_ai: 'Скопировать для AI',
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
            billing: 'Честность биллинга токенов',
            iris: 'Отпечаток случайных строк (IRIS)',
            latency_ttft: 'Время до первого токена (TTFT)',
            gateway_limits: 'Ограничения шлюза (max_tokens)',
            baseline_coverage: 'Покрытие эталоном',
        },
    },
    en: {
        title: 'Attest — LLM Anti-Spoofing & Verification Dashboard',
        brand_sub: 'AI Anti-Spoofing Gate',
        server_online: 'Port {port} • Online',
        theme_light: 'Light',
        theme_dark: 'Dark',
        nav_workbench: 'Precision Workbench',
        nav_antispoof: 'Anti-Spoofing & Fingerprinting',
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
        copy_for_ai: 'Copy for AI',
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
        btn_battery_level1: '1 · Express',
        btn_battery_level2: '2 · Standard',
        btn_battery_level3: '3 · Enhanced',
        btn_battery_level4: '4 · Maximum',
        batt_level1: 'Level 1 · Express',
        batt_level2: 'Level 2 · Standard',
        batt_level3: 'Level 3 · Enhanced',
        batt_level4: 'Level 4 · Maximum',
        batt_iris: 'IRIS · random strings',
        batt_all_tests: 'All tests',
        opt_other_batteries: 'Standalone batteries…',
        meta_run: 'Run',
        meta_candidate: 'Candidate',
        meta_reference: 'Reference',
        meta_captured: 'captured',
        time_just_now: 'just now',
        time_min_ago: '{n} min ago',
        time_hours_ago: '{n} h ago',
        time_days_ago: '{n} d ago',
        warn_battery_mismatch: "Baseline #{id} was captured with {version} and does not cover the selected battery. Pick “{fix}” or capture a baseline with this battery.",
        btn_card_details: 'Details',
        l0_claim_match: 'Match',
        l0_claim_mismatch: 'Mismatch',
        assert_all_passed: 'All passed',
        assert_failed_cnt: '{cnt} failed',
        assert_passed_summary: '{passed}/{total} passed ({failCount} failed: {failList})',
        assert_all_passed_summary: 'All {passed}/{total} deterministic assertions passed.',
        method_title_assertions: 'Deterministic Rules & Schemas',
        method_title_cosine: 'Semantic Cosine Similarity',
        method_title_fingerprint: 'System Fingerprint & Header',
        method_title_latency_drift: 'Latency & TTFT Shift',
        method_title_latency_tps: 'Generation Speed (TPS)',
        method_title_mmd: 'MMD Distribution Identity Test',
        method_title_jsd: 'One-Token Logit JSD',
        alert_select_run: 'Please select or run an endpoint audit first.',
        btn_inspect_run: 'Inspect',
        copy_for_ai: 'Copy for AI',
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
            billing: 'Token Billing Integrity',
            iris: 'Random-String Fingerprint (IRIS)',
            latency_ttft: 'Time to First Token (TTFT)',
            gateway_limits: 'Gateway Limits (max_tokens)',
            baseline_coverage: 'Baseline Coverage',
        },
    }
};

export function getCurrentLang() {
    return currentLang;
}

export async function loadLocaleBundle(lang) {
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

export function t(key, params) {
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

export function formatDiagCountTitle(count) {
    const lang = currentLang;
    if (lang === 'ru') {
        const abs = Math.abs(count) % 100;
        const rem = abs % 10;
        let word = 'сбоев';
        if (abs < 10 || abs > 20) {
            if (rem === 1) word = 'сбой';
            else if (rem >= 2 && rem <= 4) word = 'сбоя';
        }
        return `Диагностика сбоев: что пошло не так (${count} ${word})`;
    }
    const word = count === 1 ? 'discrepancy' : 'discrepancies';
    return `Failure Diagnostics: Root Cause Analysis (${count} ${word})`;
}

export function getMethodTitle(method) {
    const dict = I18N_CACHE[currentLang] || I18N_FALLBACK[currentLang] || I18N_FALLBACK['en'];
    // 1. Direct key check
    const cleanMethod = method ? method.replace(/^quick_/, '') : '';
    if (dict[`method_title_${method}`]) return dict[`method_title_${method}`];
    if (dict[`method_title_${cleanMethod}`]) return dict[`method_title_${cleanMethod}`];
    // 2. Methods dictionary
    const methods = dict.methods || (I18N_FALLBACK[currentLang] && I18N_FALLBACK[currentLang].methods) || I18N_FALLBACK['en'].methods;
    if (methods && methods[method]) return methods[method];
    // 3. Fallbacks
    const fallbackMap = {
        'jsd': 'One-Token JSD',
        'assertions': currentLang === 'ru' ? 'Детерминированные правила' : 'Deterministic Rules',
        'embedding_cosine': currentLang === 'ru' ? 'Семантическое сходство' : 'Semantic Cosine',
        'latency_drift': currentLang === 'ru' ? 'Задержка и TTFT' : 'Latency Shift',
        'latency_tps': currentLang === 'ru' ? 'Скорость генерации (TPS)' : 'Generation Speed (TPS)',
        'quick_fingerprint': currentLang === 'ru' ? 'Системный отпечаток' : 'System Fingerprint',
        'quick_model': currentLang === 'ru' ? 'Соответствие модели' : 'Model Match',
        'mmd_permutation': currentLang === 'ru' ? 'MMD тест идентичности' : 'MMD Permutation',
        'billing': currentLang === 'ru' ? 'Честность биллинга токенов' : 'Token Billing Integrity',
        'iris': currentLang === 'ru' ? 'Отпечаток случайных строк (IRIS)' : 'Random-String Fingerprint (IRIS)',
        'latency_ttft': currentLang === 'ru' ? 'Время до первого токена (TTFT)' : 'Time to First Token (TTFT)',
        'gateway_limits': currentLang === 'ru' ? 'Ограничения шлюза (max_tokens)' : 'Gateway Limits (max_tokens)'
    };
    return fallbackMap[method] || method;
}

export function applyTranslations() {
    const lang = currentLang;
    document.documentElement.lang = lang;
    const currentLangLabel = document.getElementById('current-lang-label');
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
        const translated = t(key);
        if (translated && translated !== key) {
            el.setAttribute('title', translated);
        }
    });

    // Declarative pass for placeholders
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        const translated = t(key);
        if (translated && translated !== key) {
            el.setAttribute('placeholder', translated);
        }
    });
}

export async function toggleLanguage(onLanguageChanged) {
    currentLang = currentLang === 'ru' ? 'en' : 'ru';
    try {
        localStorage.setItem('attest_lang', currentLang);
    } catch {}
    await loadLocaleBundle(currentLang);
    applyTranslations();
    if (typeof onLanguageChanged === 'function') {
        await onLanguageChanged(currentLang);
    }
}

export async function initI18n(onLanguageChanged) {
    try {
        currentLang = localStorage.getItem('attest_lang') || 'ru';
    } catch {
        currentLang = 'ru';
    }
    await loadLocaleBundle(currentLang);
    applyTranslations();
    const btnLangToggle = document.getElementById('btn-lang-toggle');
    if (btnLangToggle) {
        btnLangToggle.onclick = () => toggleLanguage(onLanguageChanged);
    }
}

/**
 * Attest Web Dashboard — Verification Studio Workbench (Dual-Channel Comparator)
 */

import { apiFetch, escapeHtml, formatDate, safeConfirm } from './api.js';
import { t } from './i18n.js';
import { startTaskPolling } from './tasks.js';

let KNOWN_PROVIDERS = [];
let currentModelBaselines = [];
let selectedBattery = 'level1';
let isFetchingModels = false;
let isFetchingRefModels = false;

// Callbacks
let onRunCompletedCallback = null;

// --- Session persistence helpers ---
const SS_KEYS = {
    refKey:            'attest_ref_key',
    refUrl:            'attest_ref_url',
    refModelsPath:     'attest_ref_models_path',
    refModelCall:      'attest_ref_model_call',
    candKey:           'attest_cand_key',
    candUrl:           'attest_cand_url',
    candModelsPath:    'attest_cand_models_path',
    candModelCall:     'attest_cand_model_call',
};

function ssPersist(input, storageKey) {
    if (!input) return;
    // Restore
    const saved = sessionStorage.getItem(storageKey);
    if (saved) input.value = saved;
    // Save on change
    input.addEventListener('input', () => sessionStorage.setItem(storageKey, input.value));
    input.addEventListener('change', () => sessionStorage.setItem(storageKey, input.value));
}

// DOM Elements — Channel A (Ground Truth)
const tabChannelASaved = document.getElementById('tab-channel-a-saved');
const tabChannelALive = document.getElementById('tab-channel-a-live');
const panelChannelASaved = document.getElementById('panel-channel-a-saved');
const panelChannelALive = document.getElementById('panel-channel-a-live');

const studioRefModel = document.getElementById('studio-ref-model');
const studioRefBaseline = document.getElementById('studio-ref-baseline');
const studioBaselineRevBadge = document.getElementById('studio-baseline-rev-badge');
const studioRefBaselineHint = document.getElementById('studio-ref-baseline-hint');
const studioRefIndicator = document.getElementById('studio-ref-indicator');
const studioRefTitle = document.getElementById('studio-ref-title');
const studioRefSub = document.getElementById('studio-ref-sub');
const btnStudioCaptureRef = document.getElementById('btn-studio-capture-ref');

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

// DOM Elements — Channel B (Candidate)
const studioCandidateProvider = document.getElementById('studio-candidate-provider');
const studioCandidateModelCall = document.getElementById('studio-candidate-model-call');
const studioCandidateUrl = document.getElementById('studio-candidate-url');
const studioCandidateModelsPath = document.getElementById('studio-candidate-models-path');
const studioCandidateKey = document.getElementById('studio-candidate-key');
const btnToggleCandidateKey = document.getElementById('btn-toggle-candidate-key');
const studioCandidateModelSelect = document.getElementById('studio-candidate-model-select');
const remoteModelsPickerWrapper = document.getElementById('remote-models-picker-wrapper');
const remoteModelsDatalist = document.getElementById('remote-models-datalist');
const remoteModelsCountBadge = document.getElementById('remote-models-count-badge');
const btnFetchModels = document.getElementById('btn-fetch-models');
const candidateModelHint = document.getElementById('candidate-model-hint');
const envKeyBadge = document.getElementById('env-key-badge');
const envKeyBadgeText = document.getElementById('env-key-badge-text');
const candidateKeyHint = document.getElementById('candidate-key-hint');

// General Workbench Elements
const quickModelChips = document.querySelectorAll('.btn-model-chip');
const studioActionInfo = document.getElementById('studio-action-info') || document.getElementById('studio-action-summary');
const lblCandidateProv = document.getElementById('lbl-candidate-prov');
const btnStudioRun = document.getElementById('btn-studio-run');

export async function initStudio(onRunCompleted) {
    onRunCompletedCallback = onRunCompleted;

    // Load Providers
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

    // Populate URL preset dropdowns
    initUrlPresets();

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

    // Load Curated Model Catalog
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
                // Same path as typing: saves the session value and reloads the
                // baseline panel for the picked model
                studioRefModelCall.dispatchEvent(new Event('input'));
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
        studioRefBaseline.onchange = () => {
            const chosen = currentModelBaselines.find(b => String(b.id) === studioRefBaseline.value);
            pinBaseline(studioRefBaseline.value || null, chosen ? chosen.battery_version : null);
            onStudioBaselineChanged();
        };
    }
    if (studioCandidateModelCall) {
        studioCandidateModelCall.oninput = () => onCandidateModelCallChanged();
        studioCandidateModelCall.onchange = () => onCandidateModelCallChanged();
    }
    if (btnToggleCandidateKey && studioCandidateKey) {
        btnToggleCandidateKey.onclick = () => {
            studioCandidateKey.type = studioCandidateKey.type === 'password' ? 'text' : 'password';
        };
    }

    // Battery Selector
    // Defence levels (each includes the ones below) or one standalone battery
    const batteryBtns = document.querySelectorAll('.battery-toggle-group .btn-battery');
    const batteryOther = document.getElementById('studio-battery-other');
    if (batteryBtns && batteryBtns.length > 0) {
        batteryBtns.forEach(btn => {
            btn.onclick = () => {
                selectedBattery = btn.dataset.battery || 'level1';
                batteryBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                if (batteryOther) batteryOther.value = '';
                updateStudioFooter();
            };
        });
    }
    if (batteryOther) {
        batteryOther.onchange = () => {
            if (!batteryOther.value) return;
            selectedBattery = batteryOther.value;
            batteryBtns.forEach(b => b.classList.remove('active'));
            updateStudioFooter();
        };
    }

    if (btnStudioCaptureRef) {
        btnStudioCaptureRef.onclick = () => captureReferenceBaseline();
    }
    if (btnStudioRun) {
        btnStudioRun.onclick = () => runStudioVerification();
    }

    // Restore persisted values from sessionStorage
    ssPersist(studioRefKey,         SS_KEYS.refKey);
    ssPersist(studioRefUrl,         SS_KEYS.refUrl);
    ssPersist(studioRefModelsPath,  SS_KEYS.refModelsPath);
    ssPersist(studioRefModelCall,   SS_KEYS.refModelCall);
    ssPersist(studioCandidateKey,   SS_KEYS.candKey);
    ssPersist(studioCandidateUrl,   SS_KEYS.candUrl);
    ssPersist(document.getElementById('studio-candidate-models-path'), SS_KEYS.candModelsPath);
    ssPersist(studioCandidateModelCall, SS_KEYS.candModelCall);
    if (studioRefModelCall) {
        // The visible field is what the audit sends as the reference model, so the
        // baseline panel (and the hidden selects behind it) must follow it
        let refModelTimer = null;
        studioRefModelCall.addEventListener('input', () => {
            clearTimeout(refModelTimer);
            refModelTimer = setTimeout(() => syncReferenceModel(studioRefModelCall.value.trim()), 300);
        });
    }
    if (studioCandidateUrl) {
        studioCandidateUrl.addEventListener('input', () => updateStudioFooter());
    }
    if (studioCandidateModelCall) {
        studioCandidateModelCall.addEventListener('input', () => updateStudioFooter());
    }

    const restoredRefModel = studioRefModelCall ? studioRefModelCall.value.trim() : '';
    if (restoredRefModel) {
        await syncReferenceModel(restoredRefModel);
    } else if (studioRefModel) {
        await loadModelBaselines(studioRefModel.value);
    }
    updateStudioFooter();
}

async function syncReferenceModel(model) {
    if (!model || !studioRefModel) return;
    if (!Array.from(studioRefModel.options).some(o => o.value === model)) {
        const opt = document.createElement('option');
        opt.value = model;
        opt.textContent = model;
        studioRefModel.insertBefore(opt, studioRefModel.lastElementChild);
    }
    studioRefModel.value = model;
    await loadModelBaselines(model);
    onStudioBaselineChanged();
}

export function onRefProviderChanged() {
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
        if (studioRefKey) {
            studioRefKey.placeholder = `✓ Ключ подключен из БД (${prov.env_key.preview})`;
            studioRefKey.title = `Используется ключ из ${prov.env_key.source}. Можно оставить пустым или ввести свой.`;
        }
        if (refEnvKeyBadgeText) {
            refEnvKeyBadgeText.textContent = `Ключ подключен (${prov.env_key.preview})`;
        }
    } else {
        if (studioRefKey) {
            studioRefKey.placeholder = 'sk-... (введите API ключ)';
            studioRefKey.title = '';
        }
    }

    fetchRefRemoteModels(false);
}

export async function fetchRefRemoteModels(userClicked = false) {
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
                let optionsHtml = `<option value="">▼ Каталог (${res.count})...</option>`;
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

export function onCandidateProviderChanged() {
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

    if (prov.env_key && prov.env_key.has_key) {
        if (studioCandidateKey) {
            studioCandidateKey.placeholder = `✓ Ключ подключен из БД (${prov.env_key.preview})`;
            studioCandidateKey.title = `Используется ключ из ${prov.env_key.source}. Можно оставить пустым или ввести свой.`;
        }
        if (envKeyBadgeText) {
            envKeyBadgeText.textContent = `Ключ подключен (${prov.env_key.preview})`;
        }
    } else {
        if (studioCandidateKey) {
            studioCandidateKey.placeholder = 'sk-... (введите API ключ)';
            studioCandidateKey.title = '';
        }
    }

    updateCandidateModelCall();
    updateStudioFooter();

    fetchRemoteModels(false);
}

export function updateCandidateModelCall() {
    if (!studioCandidateModelCall || !studioRefModel) return;
    const provId = studioCandidateProvider ? studioCandidateProvider.value : '';
    const prov = KNOWN_PROVIDERS.find(p => p.id === provId);
    const prefix = (prov && prov.model_prefix) ? prov.model_prefix : '';
    const refModel = studioRefModel.value || 'claude-sonnet-5';

    studioCandidateModelCall.value = `${prefix}${refModel}`;
}

export function onCandidateModelCallChanged() {
    updateStudioFooter();
    if (!studioCandidateModelCall || !studioRefModel) return;
    const val = studioCandidateModelCall.value.trim();
    if (!val) return;

    let clean = val;
    if (clean.includes('/')) {
        clean = clean.split('/').pop();
    }
    clean = clean.replace(/-20\d{2}-\d{2}-\d{2}$/, '');

    if (studioCandidateModelSelect) {
        const hasOption = Array.from(studioCandidateModelSelect.options).some(o => o.value === val);
        if (hasOption) {
            studioCandidateModelSelect.value = val;
        }
    }

    // The candidate never changes the reference: auditing model B against a
    // baseline of model A (a swap check) silently became "B against B" when the
    // hidden reference select followed the candidate field

    quickModelChips.forEach(chip => {
        const chipModel = chip.dataset.model;
        if (chipModel === clean || chipModel === val) {
            chip.classList.add('active');
        } else {
            chip.classList.remove('active');
        }
    });
}

export async function fetchRemoteModels(userClicked = false) {
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
                let optionsHtml = `<option value="">▼ Каталог (${res.count})...</option>`;
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
                candidateModelHint.textContent = `Загружено ${res.count} моделей напрямую из ${escapeHtml(res.base_url)}${modelsPath || '/models'}`;
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

// Only the latest request may update the panel: a slower reply for a previously
// selected model must not show that model's baseline as ready for the new one.
let baselinesRequestSeq = 0;

// A baseline picked in the archive stays chosen until the reference model changes;
// reloading the baseline list must not fall back to the active one silently.
let pinnedBaselineId = null;

// Battery each baseline family was captured with, so a pinned baseline is audited
// with prompts it actually covers
const BATTERY_BY_VERSION = {
    'levels-2026': null, // any defence level: keep the current tab
    'iris-2026': 'iris',
    'quick-v1': 'quick',
    'anti-spoof-2026-v2': 'anti_spoof',
    'frontier-probe-2026': 'frontier_probe',
    'reasoning-2026': 'reasoning',
    'all-tests-2026': 'all_tests',
    'v1': 'v1',
};

export function pinBaseline(baselineId, batteryVersion) {
    pinnedBaselineId = baselineId ? String(baselineId) : null;
    const battery = BATTERY_BY_VERSION[batteryVersion];
    if (battery) {
        const other = document.getElementById('studio-battery-other');
        selectedBattery = battery;
        document.querySelectorAll('.battery-toggle-group .btn-battery')
            .forEach(b => b.classList.remove('active'));
        if (other) other.value = battery;
    }
}

export async function loadModelBaselines(model) {
    if (!studioRefBaseline) return;
    const seq = ++baselinesRequestSeq;
    try {
        const baselines = await apiFetch(`/api/baselines?model=${encodeURIComponent(model)}`);
        if (seq !== baselinesRequestSeq) return;
        currentModelBaselines = baselines || [];
        // Snapshot picker: shown whenever this model has at least one baseline
        document.getElementById('studio-snapshot-picker-row')
            ?.classList.toggle('hidden', !baselines || baselines.length === 0);

        if (!baselines || baselines.length === 0) {
            studioRefBaseline.innerHTML = `<option value="">${t('opt_no_baseline_snapshot_required')}</option>`;
            if (studioBaselineRevBadge) {
                studioBaselineRevBadge.textContent = t('badge_none');
                studioBaselineRevBadge.className = 'badge badge-neutral';
            }
            if (studioRefBaselineHint) {
                studioRefBaselineHint.textContent = t('hint_capture_first');
            }
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
                    const batt = b.battery_version ? ` • ${b.battery_version}` : '';
                    const host = (() => { try { return ` • ${new URL(b.base_url).hostname}`; } catch { return ''; } })();
                    return `<option value="${b.id}">#${b.id} ${statusIcon} (${formatDate(b.captured_at)}) — ${b.samples_count} ${qLabel}${batt}${host}</option>`;
                })
            ].join('');

            studioRefBaseline.innerHTML = optionsHtml;
            if (pinnedBaselineId) {
                if (baselines.some(b => String(b.id) === pinnedBaselineId)) {
                    studioRefBaseline.value = pinnedBaselineId;
                } else {
                    pinnedBaselineId = null; // reference model changed: drop the pin
                }
            }
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
        }
    } catch (err) {
        console.error('Failed to load model baselines:', err);
    }
}

export function onStudioBaselineChanged() {
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

// Which model at which endpoint a baseline holds, e.g.
// "qwen/qwen3.8-flash @ openrouter.ai · levels-2026"
function baselineIdentity(b) {
    let host = '';
    try { host = b.base_url ? new URL(b.base_url).hostname : ''; } catch { host = ''; }
    const battery = b.battery_version ? ` · ${b.battery_version}` : '';
    return `${b.model || b.target_id}${host ? ' @ ' + host : ''}${battery}`;
}

export function updateStudioBaselineStatus() {
    if (!studioRefModel || !studioRefIndicator || !studioRefTitle || !studioRefSub) return;
    const selectedModel = studioRefModel.value;
    const explicitId = studioRefBaseline ? studioRefBaseline.value : null;

    if (explicitId) {
        const chosen = currentModelBaselines.find(b => String(b.id) === String(explicitId));
        if (chosen) {
            const isActive = chosen.status === 'active';
            studioRefIndicator.textContent = isActive ? '✓' : '📦';
            studioRefIndicator.className = isActive ? 'plate-indicator' : 'plate-indicator missing';
            studioRefTitle.textContent = isActive 
                ? t('title_active_baseline_with_id', { id: chosen.id })
                : t('title_historical_rev_with_id', { id: chosen.id });
            const qLabel = t('queries_count');
            const capturedLabel = t('lbl_captured');
            studioRefSub.textContent = `${baselineIdentity(chosen)} • ${capturedLabel}: ${formatDate(chosen.captured_at)} • ${chosen.samples_count} ${qLabel}`;
            updateStudioFooter();
            return;
        }
    }

    const activeB = currentModelBaselines.find(b => b.status === 'active');
    if (activeB) {
        studioRefIndicator.textContent = '✓';
        studioRefIndicator.className = 'plate-indicator';
        studioRefTitle.textContent = t('title_baseline_ready', { id: activeB.id, version: activeB.battery_version || 'v1' });
        studioRefSub.textContent = `${baselineIdentity(activeB)} • ${t('lbl_captured')}: ${formatDate(activeB.captured_at)}`;
    } else {
        studioRefIndicator.textContent = '⚠';
        studioRefIndicator.className = 'plate-indicator missing';
        studioRefTitle.textContent = t('title_no_baseline_found');
        studioRefSub.textContent = t('sub_click_snapshot_to_calibrate', { model: selectedModel });
    }

    updateStudioFooter();
}

// The provider dropdown may keep a stale choice after the URL was edited by hand:
// name the provider only when the URL is really on its host, else show the host.
function candidateProviderLabel(prov, fallback) {
    const url = studioCandidateUrl ? studioCandidateUrl.value.trim() : '';
    let host = '';
    try { host = url ? new URL(url).hostname : ''; } catch { host = ''; }
    if (prov) {
        let provHost = '';
        try { provHost = new URL(prov.base_url || prov.default_base_url || '').hostname; } catch { provHost = ''; }
        if (!host || host === provHost) return prov.name;
    }
    return host || fallback;
}

// Warn before the run when the chosen battery does not share prompts with the
// baseline in use: the server would refuse it ("covers none of the prompts")
function batteryMismatchNote() {
    const explicitId = studioRefBaseline ? studioRefBaseline.value : '';
    const baseline = explicitId
        ? currentModelBaselines.find(b => String(b.id) === String(explicitId))
        : currentModelBaselines.find(b => b.status === 'active');
    if (!baseline || !baseline.battery_version) return '';
    const selectedVersion = /^level[1-4]$/.test(selectedBattery)
        ? 'levels-2026'
        : Object.keys(BATTERY_BY_VERSION).find(v => BATTERY_BY_VERSION[v] === selectedBattery);
    if (!selectedVersion || selectedVersion === baseline.battery_version) return '';
    const fix = baseline.battery_version === 'levels-2026'
        ? t('batt_level1')
        : (BATTERY_BY_VERSION[baseline.battery_version] || baseline.battery_version);
    return `<div class="battery-mismatch-note">⚠ ${escapeHtml(t('warn_battery_mismatch', {
        id: baseline.id, version: baseline.battery_version, fix,
    }))}</div>`;
}

export function updateStudioFooter() {
    const provId = studioCandidateProvider ? studioCandidateProvider.value : '';
    const prov = KNOWN_PROVIDERS.find(p => p.id === provId);
    const provName = candidateProviderLabel(prov, t('lbl_selected_provider'));
    if (lblCandidateProv) lblCandidateProv.textContent = provName;

    const candModel = studioCandidateModelCall ? studioCandidateModelCall.value : '';
    const refModel = studioRefModel ? studioRefModel.value : '';
    const explicitId = studioRefBaseline ? studioRefBaseline.value : null;

    const battLabels = {
        'level1': t('batt_level1'),
        'level2': t('batt_level2'),
        'level3': t('batt_level3'),
        'level4': t('batt_level4'),
        'iris': t('batt_iris'),
        'all_tests': t('batt_all_tests'),
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
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
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
                }) + batteryMismatchNote();
            }
            return;
        }
    }

    if (btnStudioRun) {
        btnStudioRun.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
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
        }) + batteryMismatchNote();
    }

    updateCandidateStatusPlate();
}

export function updateCandidateStatusPlate() {
    const candIndicator = document.getElementById('studio-cand-indicator');
    const candTitle = document.getElementById('studio-cand-title');
    const candSub = document.getElementById('studio-cand-sub');
    const candBadge = document.getElementById('studio-cand-badge');
    if (!candTitle || !candSub || !candIndicator) return;

    const candUrl = studioCandidateUrl ? studioCandidateUrl.value.trim() : '';
    const candModel = studioCandidateModelCall ? studioCandidateModelCall.value.trim() : '';
    const provId = studioCandidateProvider ? studioCandidateProvider.value : '';
    const prov = KNOWN_PROVIDERS.find(p => p.id === provId);
    const provName = candidateProviderLabel(prov, 'Пользовательский эндпоинт');

    if (candUrl) {
        candIndicator.textContent = '✓';
        candIndicator.className = 'plate-indicator';
        candTitle.textContent = 'Эндпоинт готов к проверке';
        candSub.textContent = `Провайдер: ${provName} • Модель: ${candModel || 'не указана'}`;
        if (candBadge) {
            candBadge.textContent = 'Ready';
            candBadge.className = 'badge badge-emerald font-mono';
        }
    } else {
        candIndicator.textContent = '⚠';
        candIndicator.className = 'plate-indicator missing';
        candTitle.textContent = 'Укажите URL эндпоинта';
        candSub.textContent = 'Ожидание параметров кандидата';
        if (candBadge) {
            candBadge.textContent = 'Missing';
            candBadge.className = 'badge badge-neutral font-mono';
        }
    }
}

export async function captureReferenceBaseline() {
    // Always read from unified Channel A fields (tabs removed)
    const model = (studioRefModelCall ? studioRefModelCall.value : '').trim();
    const url = (studioRefUrl ? studioRefUrl.value : '').trim();
    const key = (studioRefKey ? studioRefKey.value : '').trim();

    if (!url) {
        alert('Пожалуйста, укажите URL эндпоинта эталона в Канале A.');
        if (studioRefUrl) studioRefUrl.focus();
        return;
    }
    if (!model) {
        alert('Пожалуйста, укажите модель в запросе для эталона в Канале A.');
        if (studioRefModelCall) studioRefModelCall.focus();
        return;
    }

    const confirmMsg = t('confirm_capture_baseline', { model, url });
    if (!safeConfirm(confirmMsg)) return;

    try {
        const safeModel = model.replace(/[^a-zA-Z0-9_-]/g, '-');
        const targetId = `ref-${safeModel}`;

        // Ensure reference target is saved in DB
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
        startTaskPolling(resp.task_id, `Снятие эталона Ground Truth: ${model}`, async () => {
            await loadModelBaselines(model);
            updateStudioBaselineStatus();
            if (typeof onRunCompletedCallback === 'function') {
                onRunCompletedCallback();
            }
        });
    } catch (err) {
        alert(`Ошибка при снятии эталона: ${err.message}`);
    }
}

export async function runStudioVerification() {
    const candidateProv = studioCandidateProvider ? studioCandidateProvider.value : '';
    const candidateUrl = studioCandidateUrl ? studioCandidateUrl.value.trim() : '';
    const candidateKey = studioCandidateKey ? studioCandidateKey.value.trim() : '';
    const candidateModelCall = studioCandidateModelCall ? studioCandidateModelCall.value.trim() : '';

    // Always read ref model from unified Channel A field (tabs removed)
    const refModel = (studioRefModelCall ? studioRefModelCall.value : '').trim();
    if (!refModel) {
        alert('Пожалуйста, укажите модель эталона в Канале A.');
        if (studioRefModelCall) studioRefModelCall.focus();
        return;
    }

    if (!candidateUrl) {
        alert('Пожалуйста, укажите URL эндпоинта кандидата в Канале B.');
        if (studioCandidateUrl) studioCandidateUrl.focus();
        return;
    }
    if (!candidateModelCall) {
        alert('Пожалуйста, укажите модель в запросе для кандидата в Канале B.');
        if (studioCandidateModelCall) studioCandidateModelCall.focus();
        return;
    }

    try {
        const explicitId = (studioRefBaseline && studioRefBaseline.value)
            ? parseInt(studioRefBaseline.value, 10)
            : null;
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
            ? `Дрейф модели: ${candidateModelCall} vs Эталон #${explicitId}`
            : `Антиспуфинг аудит: ${candidateModelCall} vs Ground Truth (${refModel})`;
        
        startTaskPolling(res.task_id, taskTitle, async (task) => {
            if (typeof onRunCompletedCallback === 'function') {
                onRunCompletedCallback(task);
            }
        });
    } catch (err) {
        if (err.message && err.message.includes('No active reference baseline found')) {
            const promptMsg = t('prompt_missing_baseline_capture', { model: refModel });
            const doCapture = safeConfirm(promptMsg);
            if (doCapture) {
                await captureReferenceBaseline(isLiveRef);
            }
        } else {
            alert('Не удалось запустить аудит: ' + err.message);
        }
    }
}

/**
 * Populate provider URL preset dropdowns in both channels.
 * On selection: auto-fills the URL field and models path.
 * Fields remain manually editable.
 */
async function initUrlPresets() {
    if (!KNOWN_PROVIDERS || KNOWN_PROVIDERS.length === 0) return;

    const hostOf = url => { try { return new URL(url).hostname; } catch { return ''; } };
    const knownHosts = new Set(KNOWN_PROVIDERS.map(p => hostOf(p.base_url)).filter(Boolean));

    // Endpoints already used by saved targets (e.g. a reseller typed by hand),
    // so they can be picked again without retyping
    let recent = [];
    try {
        const targets = await apiFetch('/api/targets');
        const seen = new Set();
        for (const t of targets || []) {
            const host = hostOf(t.base_url);
            if (!host || knownHosts.has(host) || seen.has(t.base_url)) continue;
            seen.add(t.base_url);
            recent.push({ url: t.base_url, label: host });
        }
    } catch { recent = []; }

    const opt = (url, label) => `<option value="${escapeHtml(url)}">${escapeHtml(label)}</option>`;
    const builtIn = KNOWN_PROVIDERS.filter(p => p.id !== 'custom' && !p.id.startsWith('custom_'));
    const saved = KNOWN_PROVIDERS.filter(p => p.id.startsWith('custom_'));
    const optionsHtml =
        `<optgroup label="Провайдеры">${builtIn.map(p => opt(p.base_url, p.name)).join('')}</optgroup>` +
        (saved.length ? `<optgroup label="Сохранённые">${saved.map(p => opt(p.base_url, p.name)).join('')}</optgroup>` : '') +
        (recent.length ? `<optgroup label="Недавние эндпоинты">${recent.map(r => opt(r.url, r.label)).join('')}</optgroup>` : '') +
        `<option value="__save_current__">＋ Сохранить текущий URL как провайдера…</option>`;

    function setupPreset(selectId, urlInputId, modelsPathId) {
        const sel = document.getElementById(selectId);
        const urlInput = document.getElementById(urlInputId);
        const pathInput = document.getElementById(modelsPathId);
        if (!sel || !urlInput) return;

        sel.innerHTML = `<option value="">— Выбрать —</option>${optionsHtml}`;

        sel.onchange = () => {
            const url = sel.value;
            if (!url) return;
            if (url === '__save_current__') {
                sel.value = '';
                openAddCustomProviderModal({ url: urlInput.value.trim() });
                return;
            }
            urlInput.value = url;
            urlInput.dispatchEvent(new Event('input')); // trigger sessionStorage save
            if (pathInput) {
                pathInput.value = '/v1/models';
                pathInput.dispatchEvent(new Event('input'));
            }
            updateStudioFooter();
            setTimeout(() => { sel.value = ''; }, 80); // reset to placeholder
        };
    }

    setupPreset('ref-provider-preset',  'studio-ref-url',       'studio-ref-models-path');
    setupPreset('cand-provider-preset', 'studio-candidate-url', 'studio-candidate-models-path');
}

// ============================================================
// Custom Provider Modal
// ============================================================

export function openAddCustomProviderModal(prefill = {}) {
    // Remove existing modal if any
    document.getElementById('custom-provider-modal')?.remove();

    const modal = document.createElement('div');
    modal.id = 'custom-provider-modal';
    modal.style.cssText = `
        position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.6);
        display:flex;align-items:center;justify-content:center;
    `;
    modal.innerHTML = `
        <div style="background:var(--bg-secondary,#1e1e2e);border:1px solid var(--border,#333);border-radius:12px;
                    padding:28px 32px;width:480px;max-width:95vw;box-shadow:0 8px 40px rgba(0,0,0,0.5);">
            <h3 style="margin:0 0 20px;font-size:1rem;font-weight:600;color:var(--text-primary,#e0e0e0);">
                ＋ Добавить провайдера
            </h3>
            <div style="display:flex;flex-direction:column;gap:12px;">
                <label style="font-size:.75rem;font-weight:600;letter-spacing:.08em;color:var(--text-secondary,#999);text-transform:uppercase;">
                    Название *
                    <input id="cpm-name" type="text" placeholder="Мой Gateway" style="
                        display:block;width:100%;margin-top:4px;padding:8px 10px;border-radius:6px;
                        border:1px solid var(--border,#444);background:var(--bg-input,#13131f);
                        color:var(--text-primary,#e0e0e0);font-size:.875rem;box-sizing:border-box;">
                </label>
                <label style="font-size:.75rem;font-weight:600;letter-spacing:.08em;color:var(--text-secondary,#999);text-transform:uppercase;">
                    URL Эндпоинта *
                    <input id="cpm-url" type="url" placeholder="https://api.example.com/v1" style="
                        display:block;width:100%;margin-top:4px;padding:8px 10px;border-radius:6px;
                        border:1px solid var(--border,#444);background:var(--bg-input,#13131f);
                        color:var(--text-primary,#e0e0e0);font-family:monospace;font-size:.875rem;box-sizing:border-box;">
                </label>
                <label style="font-size:.75rem;font-weight:600;letter-spacing:.08em;color:var(--text-secondary,#999);text-transform:uppercase;">
                    API Ключ (опционально)
                    <input id="cpm-key" type="password" placeholder="sk-..." style="
                        display:block;width:100%;margin-top:4px;padding:8px 10px;border-radius:6px;
                        border:1px solid var(--border,#444);background:var(--bg-input,#13131f);
                        color:var(--text-primary,#e0e0e0);font-family:monospace;font-size:.875rem;box-sizing:border-box;">
                </label>
                <label style="font-size:.75rem;font-weight:600;letter-spacing:.08em;color:var(--text-secondary,#999);text-transform:uppercase;">
                    Префикс модели (опционально)
                    <input id="cpm-prefix" type="text" placeholder='openai/ — если нужен (напр. для OpenRouter)' style="
                        display:block;width:100%;margin-top:4px;padding:8px 10px;border-radius:6px;
                        border:1px solid var(--border,#444);background:var(--bg-input,#13131f);
                        color:var(--text-primary,#e0e0e0);font-family:monospace;font-size:.875rem;box-sizing:border-box;">
                </label>
                <label style="font-size:.75rem;font-weight:600;letter-spacing:.08em;color:var(--text-secondary,#999);text-transform:uppercase;">
                    Описание
                    <input id="cpm-desc" type="text" placeholder="Необязательное описание" style="
                        display:block;width:100%;margin-top:4px;padding:8px 10px;border-radius:6px;
                        border:1px solid var(--border,#444);background:var(--bg-input,#13131f);
                        color:var(--text-primary,#e0e0e0);font-size:.875rem;box-sizing:border-box;">
                </label>
            </div>
            <div id="cpm-error" style="color:#f97316;font-size:.8rem;margin-top:8px;display:none;"></div>
            <div style="display:flex;gap:10px;margin-top:20px;justify-content:flex-end;">
                <button id="cpm-cancel" style="padding:8px 18px;border-radius:6px;border:1px solid var(--border,#444);
                    background:transparent;color:var(--text-secondary,#999);cursor:pointer;font-size:.875rem;">
                    Отмена
                </button>
                <button id="cpm-save" style="padding:8px 20px;border-radius:6px;border:none;
                    background:var(--accent,#6366f1);color:#fff;cursor:pointer;font-size:.875rem;font-weight:600;">
                    Сохранить
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    const nameEl   = modal.querySelector('#cpm-name');
    const urlEl    = modal.querySelector('#cpm-url');
    if (prefill.url) {
        urlEl.value = prefill.url;
        try { nameEl.value = new URL(prefill.url).hostname; } catch { /* keep empty */ }
    }
    const keyEl    = modal.querySelector('#cpm-key');
    const prefixEl = modal.querySelector('#cpm-prefix');
    const descEl   = modal.querySelector('#cpm-desc');
    const errEl    = modal.querySelector('#cpm-error');

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

            // Add to local KNOWN_PROVIDERS cache and update dropdown
            const existing = KNOWN_PROVIDERS.findIndex(p => p.id === saved.id);
            if (existing >= 0) {
                KNOWN_PROVIDERS[existing] = saved;
            } else {
                KNOWN_PROVIDERS.push(saved);
            }

            if (studioCandidateProvider) {
                // Rebuild dropdown options + keep "Add" option at end
                const currentVal = studioCandidateProvider.value;
                studioCandidateProvider.innerHTML = KNOWN_PROVIDERS.map(p =>
                    `<option value="${escapeHtml(p.id)}" ${p.id === saved.id ? 'selected' : ''}>${escapeHtml(p.name)}</option>`
                ).join('') + `<option value="__add_custom__">＋ Добавить провайдера...</option>`;
                studioCandidateProvider.value = saved.id;
            }

            if (studioCandidateUrl) {
                studioCandidateUrl.value = saved.base_url;
            }

            onCandidateProviderChanged();
            initUrlPresets();
            modal.remove();
        } catch (err) {
            errEl.textContent = 'Ошибка сохранения: ' + err.message;
            errEl.style.display = 'block';
        }
    };

    nameEl.focus();
}

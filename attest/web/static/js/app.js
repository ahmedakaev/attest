/**
 * Attest Web Dashboard — Main Orchestrator Application Entry Point
 * Modular zero-dependency ES Module architecture
 */

import { initTheme } from './theme.js';
import { initI18n } from './i18n.js';
import { initTasks } from './tasks.js';
import { initStudio } from './studio.js';
import { initInspector, loadRunDetails } from './inspector.js';
import { initModals } from './modals.js';
import { initTargets, refreshDashboard } from './targets.js';
import { apiFetch } from './api.js';

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Initialize Theme (Dark/Light palette with persistence)
    initTheme();

    // 2. Initialize Translations (EN/RU toggle and DOM string bindings)
    await initI18n();

    // 3. Initialize Background Task Progress Banner
    initTasks();

    // 4. Initialize Audit Deep Dive Inspector & Dispute Generator
    initInspector();

    // 5. Initialize Modals (Baselines, Schedules, Target Creation, Costing)
    initModals({
        onTargetAdded: async () => {
            await refreshDashboard();
        }
    });

    // 6. Initialize Targets Dashboard Grid & Action Handlers
    initTargets();

    // 7. Initialize Dual-Channel Verification Studio (Ground Truth vs Candidate)
    await initStudio(async (task) => {
        await refreshDashboard();
        if (task?.result?.run_id) {
            loadRunDetails(task.result.run_id);
        }
    });

    // 8. Fetch Initial Telemetry & Targets
    await refreshDashboard();

    // 9. Auto-display latest audit report so the dual-column results deck is immediately visible
    try {
        const targetsRes = await apiFetch('/api/targets');
        const withRun = targetsRes.find(t => t.latest_run?.id);
        if (withRun && withRun.latest_run?.id) {
            await loadRunDetails(withRun.latest_run.id, { scroll: false });
        }
    } catch (e) {
        console.warn('Auto-load latest run details failed', e);
    }
});

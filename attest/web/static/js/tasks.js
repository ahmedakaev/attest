/**
 * Attest Web Dashboard — Task Polling & Live Progress Banner
 */

import { apiFetch } from './api.js';

let activeTaskId = null;
let pollInterval = null;

const liveTaskBanner = document.getElementById('live-task-banner');
const taskBannerTitle = document.getElementById('task-banner-title');
const taskBannerSub = document.getElementById('task-banner-sub');
const taskBannerCounts = document.getElementById('task-banner-counts');
const taskBannerPct = document.getElementById('task-banner-pct');
const taskProgressFill = document.getElementById('task-progress-fill');
const btnCloseTaskBanner = document.getElementById('btn-close-task-banner');

export function initTasks() {
    if (btnCloseTaskBanner) {
        btnCloseTaskBanner.onclick = () => {
            closeTaskBanner();
        };
    }
}

export function closeTaskBanner() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
    activeTaskId = null;
    if (liveTaskBanner) {
        liveTaskBanner.classList.add('hidden');
    }
}

export function startTaskPolling(taskId, title = 'Проверка эндпоинта...', onCompleted = null) {
    if (pollInterval) {
        clearInterval(pollInterval);
    }
    activeTaskId = taskId;

    if (liveTaskBanner) {
        liveTaskBanner.classList.remove('hidden', 'is-failed');
    }
    if (taskBannerTitle) taskBannerTitle.textContent = title;
    if (taskBannerSub) taskBannerSub.textContent = 'Инициализация подключения к API...';
    if (taskBannerCounts) taskBannerCounts.textContent = '0 / 0 запросов';
    if (taskBannerPct) taskBannerPct.textContent = '0%';
    if (taskProgressFill) taskProgressFill.style.width = '0%';

    pollInterval = setInterval(async () => {
        try {
            const task = await apiFetch(`/api/tasks/${taskId}`);
            if (!task) return;

            const total = task.total || 0;
            const completed = task.completed || 0;
            const pct = total > 0 ? Math.round((completed / total) * 100) : (task.status === 'completed' ? 100 : 5);

            if (taskBannerCounts) taskBannerCounts.textContent = `${completed} / ${total} запросов`;
            if (taskBannerPct) taskBannerPct.textContent = `${pct}%`;
            if (taskProgressFill) taskProgressFill.style.width = `${pct}%`;

            if (task.status === 'running') {
                if (taskBannerSub) taskBannerSub.textContent = `Выполнение пакета тестов... (${completed}/${total})`;
            } else if (task.status === 'completed') {
                clearInterval(pollInterval);
                pollInterval = null;
                if (taskBannerSub) taskBannerSub.textContent = '✓ Проверка успешно завершена!';
                if (taskProgressFill) taskProgressFill.style.width = '100%';
                if (taskBannerPct) taskBannerPct.textContent = '100%';

                setTimeout(() => {
                    closeTaskBanner();
                }, 4000);

                if (typeof onCompleted === 'function') {
                    onCompleted(task);
                }
            } else if (task.status === 'failed') {
                clearInterval(pollInterval);
                pollInterval = null;
                if (liveTaskBanner) liveTaskBanner.classList.add('is-failed');
                if (taskBannerSub) taskBannerSub.textContent = `Ошибка выполнения: ${task.error || 'Неизвестная ошибка'}`;
            }
        } catch (err) {
            console.error('Task poll error:', err);
        }
    }, 1000);
}

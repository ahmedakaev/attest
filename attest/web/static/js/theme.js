/**
 * Attest Web Dashboard — Theme Management (Light & Dark Monochrome)
 */

let currentTheme = 'dark';

export function getCurrentTheme() {
    return currentTheme;
}

export function applyTheme(theme) {
    currentTheme = theme;
    try {
        localStorage.setItem('attest_theme', theme);
    } catch {
        // LocalStorage might be disabled in private mode
    }
    document.documentElement.setAttribute('data-theme', theme);

    const themeLabel = document.getElementById('theme-label');
    const themeIconSun = document.querySelector('.theme-icon-sun');
    const themeIconMoon = document.querySelector('.theme-icon-moon');

    if (themeLabel) {
        themeLabel.setAttribute('data-i18n', theme === 'light' ? 'theme_light' : 'theme_dark');
        themeLabel.textContent = theme === 'light' ? 'Светлая' : 'Тёмная';
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

export function initTheme() {
    let saved = 'dark';
    try {
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('theme')) {
            saved = urlParams.get('theme') === 'light' ? 'light' : 'dark';
        } else {
            saved = localStorage.getItem('attest_theme') || 'dark';
        }
    } catch {
        saved = 'dark';
    }
    applyTheme(saved);

    const btnThemeToggle = document.getElementById('btn-theme-toggle');
    if (btnThemeToggle) {
        btnThemeToggle.onclick = () => {
            const next = currentTheme === 'light' ? 'dark' : 'light';
            applyTheme(next);
        };
    }
}

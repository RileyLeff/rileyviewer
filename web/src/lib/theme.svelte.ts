import { browser } from '$app/environment';

export type ThemePreference = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'rileyviewer-theme';
const ORDER: ThemePreference[] = ['light', 'dark', 'system'];

function stored(): ThemePreference {
	if (!browser) return 'system';
	const v = localStorage.getItem(STORAGE_KEY);
	return ORDER.includes(v as ThemePreference) ? (v as ThemePreference) : 'system';
}

function systemIsDark(): boolean {
	if (!browser) return false;
	return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function apply(pref: ThemePreference) {
	if (!browser) return;
	const dark = pref === 'dark' || (pref === 'system' && systemIsDark());
	document.documentElement.classList.toggle('dark', dark);
}

let preference = $state<ThemePreference>(stored());

export function getPreference(): ThemePreference {
	return preference;
}

export function setPreference(next: ThemePreference) {
	preference = next;
	if (browser) {
		localStorage.setItem(STORAGE_KEY, next);
		apply(next);
	}
}

export function cycle() {
	const idx = ORDER.indexOf(preference);
	setPreference(ORDER[(idx + 1) % ORDER.length]);
}

export function initSystemListener() {
	if (!browser) return;
	const mq = window.matchMedia('(prefers-color-scheme: dark)');
	const handler = () => {
		if (preference === 'system') apply('system');
	};
	mq.addEventListener('change', handler);
	// Apply on init in case FOUC script and current state diverged
	apply(preference);
	return () => mq.removeEventListener('change', handler);
}

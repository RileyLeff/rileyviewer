import { browser } from '$app/environment';

// ── Theme ──

export type ThemePreference = 'light' | 'dark' | 'system';

const THEME_KEY = 'rileyviewer-theme';
const THEME_ORDER: ThemePreference[] = ['light', 'dark', 'system'];

function storedTheme(): ThemePreference {
	if (!browser) return 'system';
	const v = localStorage.getItem(THEME_KEY);
	return THEME_ORDER.includes(v as ThemePreference) ? (v as ThemePreference) : 'system';
}

function systemIsDark(): boolean {
	if (!browser) return false;
	return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function applyTheme(pref: ThemePreference) {
	if (!browser) return;
	const dark = pref === 'dark' || (pref === 'system' && systemIsDark());
	document.documentElement.classList.toggle('dark', dark);
}

let theme = $state<ThemePreference>(storedTheme());

export function getTheme(): ThemePreference {
	return theme;
}

export function setTheme(next: ThemePreference) {
	theme = next;
	if (browser) {
		localStorage.setItem(THEME_KEY, next);
		applyTheme(next);
	}
}

export function initSystemListener() {
	if (!browser) return;
	const mq = window.matchMedia('(prefers-color-scheme: dark)');
	const handler = () => {
		if (theme === 'system') applyTheme('system');
	};
	mq.addEventListener('change', handler);
	applyTheme(theme);
	return () => mq.removeEventListener('change', handler);
}

// ── Background ──

export type BackgroundMode = 'sticker' | 'blank' | 'mania';

const BG_KEY = 'rileyviewer-background';
const BG_OPTIONS: BackgroundMode[] = ['sticker', 'blank', 'mania'];

function storedBg(): BackgroundMode {
	if (!browser) return 'sticker';
	const v = localStorage.getItem(BG_KEY);
	return BG_OPTIONS.includes(v as BackgroundMode) ? (v as BackgroundMode) : 'sticker';
}

let background = $state<BackgroundMode>(storedBg());

export function getBackground(): BackgroundMode {
	return background;
}

export function setBackground(next: BackgroundMode) {
	background = next;
	if (browser) localStorage.setItem(BG_KEY, next);
}

// ── Link Logo ──

const LINK_KEY = 'rileyviewer-link-logo';

function storedLinkLogo(): boolean {
	if (!browser) return true;
	const v = localStorage.getItem(LINK_KEY);
	return v === null ? true : v === 'true';
}

let linkLogo = $state<boolean>(storedLinkLogo());

export function getLinkLogo(): boolean {
	return linkLogo;
}

export function setLinkLogo(next: boolean) {
	linkLogo = next;
	if (browser) localStorage.setItem(LINK_KEY, String(next));
}

// ── Thumbnail Position ──

export type ThumbnailPosition = 'bottom' | 'top' | 'left' | 'right';

const THUMB_KEY = 'rileyviewer-thumbnails';
const THUMB_OPTIONS: ThumbnailPosition[] = ['bottom', 'top', 'left', 'right'];

function storedThumbPos(): ThumbnailPosition {
	if (!browser) return 'bottom';
	const v = localStorage.getItem(THUMB_KEY);
	return THUMB_OPTIONS.includes(v as ThumbnailPosition) ? (v as ThumbnailPosition) : 'bottom';
}

let thumbPos = $state<ThumbnailPosition>(storedThumbPos());

export function getThumbPos(): ThumbnailPosition {
	return thumbPos;
}

export function setThumbPos(next: ThumbnailPosition) {
	thumbPos = next;
	if (browser) localStorage.setItem(THUMB_KEY, next);
}

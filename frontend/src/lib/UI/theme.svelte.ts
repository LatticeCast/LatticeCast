// src/lib/UI/theme.svelte.ts
// Centralized color tokens for light/dark mode and tag palette

import { browser } from '$app/environment';
import { settingsStore } from '$lib/stores/settings.store';

let _isDark = $state(false);
settingsStore.subscribe((s) => {
	_isDark = s.darkMode;
	if (browser) {
		document.documentElement.classList.toggle('dark', s.darkMode);
	}
});

/** Reactive dark-mode flag — true when dark mode is enabled in settings. */
export const isDark = {
	get value() {
		return _isDark;
	}
};

export interface ThemeTokens {
	// Gradients
	headerGradient: string;
	buttonGradient: string;

	// Backgrounds
	pageBg: string;
	settingsHeroBg: string;
	cardBg: string;
	inputBg: string;
	hoverBg: string;
	selectedBg: string;
	badgeBg: string;
	toggleTrackBg: string;
	tableHeaderBg: string;
	rowHoverBg: string;
	menuBg: string;
	editorBg: string;

	// Borders
	inputBorder: string;
	inputFocusBorder: string;
	selectedBorder: string;
	cardBorder: string;
	border: string;

	// Text
	heading: string;
	body: string;
	muted: string;
	placeholder: string;
	link: string;
	secondary: string;
	faint: string;

	// Badges
	badgeText: string;
	badgeBorder: string;

	// Dropdown / Menu
	menuItemHover: string;

	// Utilities
	divide: string;
	proseDark: string;
}

export const theme = {
	light: {
		// Gradients (Tailwind CSS 4 syntax)
		headerGradient: 'bg-linear-to-r from-blue-600 to-blue-500',
		buttonGradient: 'bg-linear-to-r from-blue-600 to-blue-500',

		// Backgrounds
		pageBg: 'bg-gray-50',
		settingsHeroBg: 'bg-linear-to-br from-blue-600 via-blue-500 to-sky-500',
		cardBg: 'bg-white',
		inputBg: 'bg-white',
		hoverBg: 'hover:bg-blue-50',
		selectedBg: 'bg-blue-50',
		badgeBg: 'bg-blue-100',
		toggleTrackBg: 'bg-gray-200',
		tableHeaderBg: 'bg-gray-50',
		rowHoverBg: 'hover:bg-blue-50/60',
		menuBg: 'bg-white',
		editorBg: 'bg-white',

		// Borders
		inputBorder: 'border-gray-200',
		inputFocusBorder: 'focus:border-blue-500',
		selectedBorder: 'border-blue-500',
		cardBorder: 'border-gray-100',
		border: 'border-gray-200',

		// Text
		heading: 'text-gray-900',
		body: 'text-gray-800',
		muted: 'text-gray-500',
		placeholder: 'placeholder-gray-400',
		link: 'text-blue-600 hover:text-blue-700',
		secondary: 'text-gray-700',
		faint: 'text-gray-300',

		// Badges
		badgeText: 'text-blue-700',
		badgeBorder: 'border-blue-200',

		// Dropdown / Menu
		menuItemHover: 'hover:bg-gray-50',

		// Utilities
		divide: 'divide-gray-200',
		proseDark: ''
	} satisfies Record<string, string>,

	dark: {
		// Gradients
		headerGradient: 'bg-linear-to-r from-blue-800 to-blue-700',
		buttonGradient: 'bg-linear-to-r from-blue-700 to-blue-600',

		// Backgrounds
		pageBg: 'bg-gray-900',
		settingsHeroBg: 'bg-gray-900',
		cardBg: 'bg-gray-800',
		inputBg: 'bg-gray-700',
		hoverBg: 'hover:bg-blue-900',
		selectedBg: 'bg-blue-900',
		badgeBg: 'bg-blue-900',
		toggleTrackBg: 'bg-gray-600',
		tableHeaderBg: 'bg-gray-800',
		rowHoverBg: 'hover:bg-gray-800',
		menuBg: 'bg-gray-800/95',
		editorBg: 'bg-gray-900',

		// Borders
		inputBorder: 'border-gray-600',
		inputFocusBorder: 'focus:border-blue-400',
		selectedBorder: 'border-blue-400',
		cardBorder: 'border-gray-700',
		border: 'border-gray-700',

		// Text
		heading: 'text-gray-100',
		body: 'text-gray-200',
		muted: 'text-gray-400',
		placeholder: 'placeholder-gray-500',
		link: 'text-blue-400 hover:text-blue-300',
		secondary: 'text-gray-300',
		faint: 'text-gray-600',

		// Badges
		badgeText: 'text-blue-300',
		badgeBorder: 'border-blue-700',

		// Dropdown / Menu
		menuItemHover: 'hover:bg-gray-700',

		// Utilities
		divide: 'divide-gray-700',
		proseDark: 'prose-invert'
	} satisfies Record<string, string>
} as const;

/** Reactive current theme tokens — auto-switches between light/dark.
 *  Usage: `{T.cardBg}` in templates — no .value needed. */
export const T: ThemeTokens = new Proxy({} as ThemeTokens, {
	get(_target, prop: string) {
		const tokens = _isDark ? theme.dark : theme.light;
		return tokens[prop as keyof ThemeTokens];
	}
});

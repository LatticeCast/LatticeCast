// src/lib/UI/theme.svelte.ts
// Centralized color tokens for light/dark mode and tag palette

import { settingsStore } from '$lib/stores/settings.store';

let _isDark = $state(false);
settingsStore.subscribe((s) => {
	_isDark = s.darkMode;
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
	cardBg: string;
	inputBg: string;
	hoverBg: string;
	selectedBg: string;
	badgeBg: string;

	// Borders
	inputBorder: string;
	inputFocusBorder: string;
	selectedBorder: string;
	cardBorder: string;

	// Text
	heading: string;
	body: string;
	muted: string;
	placeholder: string;
	link: string;

	// Badges
	badgeText: string;
	badgeBorder: string;
}

export const theme = {
	light: {
		// Gradients (Tailwind CSS 4 syntax)
		headerGradient: 'bg-linear-to-r from-blue-600 to-blue-500',
		buttonGradient: 'bg-linear-to-r from-blue-600 to-blue-500',

		// Backgrounds
		pageBg: 'bg-gray-50',
		cardBg: 'bg-white',
		inputBg: 'bg-white',
		hoverBg: 'hover:bg-blue-50',
		selectedBg: 'bg-blue-50',
		badgeBg: 'bg-blue-100',

		// Borders
		inputBorder: 'border-gray-200',
		inputFocusBorder: 'focus:border-blue-500',
		selectedBorder: 'border-blue-500',
		cardBorder: 'border-gray-100',

		// Text
		heading: 'text-gray-900',
		body: 'text-gray-800',
		muted: 'text-gray-500',
		placeholder: 'placeholder-gray-400',
		link: 'text-blue-600 hover:text-blue-700',

		// Badges
		badgeText: 'text-blue-700',
		badgeBorder: 'border-blue-200'
	} satisfies Record<string, string>,

	dark: {
		// Gradients
		headerGradient: 'bg-linear-to-r from-blue-800 to-blue-700',
		buttonGradient: 'bg-linear-to-r from-blue-700 to-blue-600',

		// Backgrounds
		pageBg: 'bg-gray-900',
		cardBg: 'bg-gray-800',
		inputBg: 'bg-gray-700',
		hoverBg: 'hover:bg-blue-900',
		selectedBg: 'bg-blue-900',
		badgeBg: 'bg-blue-900',

		// Borders
		inputBorder: 'border-gray-600',
		inputFocusBorder: 'focus:border-blue-400',
		selectedBorder: 'border-blue-400',
		cardBorder: 'border-gray-700',

		// Text
		heading: 'text-gray-100',
		body: 'text-gray-200',
		muted: 'text-gray-400',
		placeholder: 'placeholder-gray-500',
		link: 'text-blue-400 hover:text-blue-300',

		// Badges
		badgeText: 'text-blue-300',
		badgeBorder: 'border-blue-700'
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

// TAG_COLORS — 12 preset colors for auto-assigning to tags/select options.
// Each entry: { bg, text, border } as Tailwind classes.
export const TAG_COLORS = [
	{ bg: 'bg-blue-100', text: 'text-blue-700', border: 'border-blue-200' },
	{ bg: 'bg-green-100', text: 'text-green-700', border: 'border-green-200' },
	{ bg: 'bg-yellow-100', text: 'text-yellow-700', border: 'border-yellow-200' },
	{ bg: 'bg-red-100', text: 'text-red-700', border: 'border-red-200' },
	{ bg: 'bg-purple-100', text: 'text-purple-700', border: 'border-purple-200' },
	{ bg: 'bg-pink-100', text: 'text-pink-700', border: 'border-pink-200' },
	{ bg: 'bg-orange-100', text: 'text-orange-700', border: 'border-orange-200' },
	{ bg: 'bg-teal-100', text: 'text-teal-700', border: 'border-teal-200' },
	{ bg: 'bg-cyan-100', text: 'text-cyan-700', border: 'border-cyan-200' },
	{ bg: 'bg-indigo-100', text: 'text-indigo-700', border: 'border-indigo-200' },
	{ bg: 'bg-lime-100', text: 'text-lime-700', border: 'border-lime-200' },
	{ bg: 'bg-rose-100', text: 'text-rose-700', border: 'border-rose-200' }
] as const;

export type TagColor = (typeof TAG_COLORS)[number];

/**
 * Auto-assign a tag color from the palette by index (cycles through all 12).
 * Usage: getTagColor(choices.length) when adding a new choice.
 */
export function getTagColor(index: number): TagColor {
	return TAG_COLORS[index % TAG_COLORS.length];
}

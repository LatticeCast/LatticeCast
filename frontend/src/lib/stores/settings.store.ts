// lib/stores/settings.store.ts

import { writable, get } from 'svelte/store';
import { browser } from '$app/environment';
import { authStore } from '$lib/stores/auth.store';

export type SpeechLang = 'zh-TW' | 'en-US' | 'ja-JP';

export interface Settings {
	// Server-backed — mirrored into public.user_info.config
	darkMode: boolean;
	// Local-only — single-device preferences
	speechLang: SpeechLang;
	notificationEnabled: boolean;
	notificationIntervalMinutes: number;
}

const SAVE_FILE = 'settings.save';
const PATCH_DEBOUNCE_MS = 250;

const defaultSettings: Settings = {
	darkMode: false,
	speechLang: 'zh-TW',
	notificationEnabled: false,
	notificationIntervalMinutes: 60
};

function loadSync(): Settings {
	if (!browser) return defaultSettings;
	try {
		const stored = localStorage.getItem(SAVE_FILE);
		return stored ? { ...defaultSettings, ...JSON.parse(stored) } : defaultSettings;
	} catch {
		return defaultSettings;
	}
}

export const settingsStore = writable<Settings>(loadSync());

// Last-known server state of darkMode. Used to detect drift from local edits
// so we only PATCH when the user actually toggles.
let serverDarkMode: boolean | undefined;

let patchTimer: ReturnType<typeof setTimeout> | null = null;

function schedulePatch() {
	if (patchTimer) clearTimeout(patchTimer);
	patchTimer = setTimeout(flushPatch, PATCH_DEBOUNCE_MS);
}

async function flushPatch() {
	patchTimer = null;
	const auth = get(authStore);
	if (!auth?.accessToken) return;

	const current = get(settingsStore);
	if (current.darkMode === serverDarkMode) return;

	try {
		const res = await fetch('/api/v1/login/me/config', {
			method: 'PATCH',
			headers: {
				'Content-Type': 'application/json',
				Authorization: `Bearer ${auth.accessToken}`
			},
			body: JSON.stringify({ darkMode: current.darkMode })
		});
		if (res.ok) {
			const next = (await res.json()) as Record<string, unknown>;
			serverDarkMode = typeof next.darkMode === 'boolean' ? next.darkMode : undefined;
		}
	} catch {
		// best-effort — the next change will retry
	}
}

if (browser) {
	settingsStore.subscribe((v) => {
		try {
			localStorage.setItem(SAVE_FILE, JSON.stringify(v));
		} catch {
			// quota exceeded / disabled — ignore
		}
		if (get(authStore)?.accessToken) schedulePatch();
	});
}

/**
 * Apply the per-user config blob from `GET /api/v1/login/me` into the store.
 * Updates the tracker so the resulting store change does not echo back as
 * a PATCH. Call once after auth becomes valid.
 */
export function hydrateFromServer(serverConfig: Record<string, unknown> | null | undefined) {
	if (!serverConfig) return;
	const incomingDark =
		typeof serverConfig.darkMode === 'boolean' ? (serverConfig.darkMode as boolean) : undefined;
	serverDarkMode = incomingDark;
	if (incomingDark !== undefined) {
		settingsStore.update((s) => ({ ...s, darkMode: incomingDark }));
	}
}

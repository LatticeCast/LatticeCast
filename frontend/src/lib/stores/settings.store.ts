// lib/stores/settings.store.ts

import { writable } from 'svelte/store';
import { browser } from '$app/environment';

export type SpeechLang = 'zh-TW' | 'en-US' | 'ja-JP';

export interface Settings {
	speechLang: SpeechLang;
	notificationEnabled: boolean;
	notificationIntervalMinutes: number;
	darkMode: boolean;
}

const SAVE_FILE = 'settings.save';

const defaultSettings: Settings = {
	speechLang: 'zh-TW',
	notificationEnabled: false,
	notificationIntervalMinutes: 60,
	darkMode: false
};

/** Load settings synchronously from localStorage (used for initial store value) */
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

if (browser) {
	settingsStore.subscribe((v) => {
		localStorage.setItem(SAVE_FILE, JSON.stringify(v));
	});
}

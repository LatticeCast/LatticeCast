// lib/stores/settings.store.ts

import { writable, get } from 'svelte/store';
import { browser } from '$app/environment';
import { authStore } from '$lib/stores/auth.store';
import { browserZone } from '$lib/utils/temporal';

export type SpeechLang = 'zh-TW' | 'en-US' | 'ja-JP';

export interface Settings {
	// Server-backed — mirrored into public.user_info.config
	darkMode: boolean;
	// IANA zone name. Server times are UTC instants with no zone, so this is
	// what every date and datetime cell is read and written through. It is
	// per-user rather than per-device on purpose: the same board must read the
	// same way on a laptop and on a phone in another country.
	timezone: string;
	// Local-only — single-device preferences
	speechLang: SpeechLang;
	notificationEnabled: boolean;
	notificationIntervalMinutes: number;
}

/** Server-backed keys, in the shape `PATCH /login/me/config` expects. */
const SERVER_KEYS = ['darkMode', 'timezone'] as const;
type ServerKey = (typeof SERVER_KEYS)[number];

const SAVE_FILE = 'settings.save';
const PATCH_DEBOUNCE_MS = 250;

const defaultSettings: Settings = {
	darkMode: false,
	timezone: browserZone(),
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

// Last-known server state of the server-backed keys. Used to detect drift
// from local edits so we only PATCH what the user actually changed.
let serverState: Partial<Record<ServerKey, unknown>> = {};

// Nothing may be pushed to the server before we have read from it once.
// Without this the store's own defaults are indistinguishable from a user
// edit: on a fresh browser loadSync() falls back to browserZone(), the
// subscriber sees that differ from an empty serverState, and 250ms later it
// PATCHes the browser's zone over whatever the user had configured -- while
// hydrateFromServer is still waiting on GET /login/me. First write wins, and
// it is the wrong one. darkMode hid this because its default, false, usually
// matched the stored value already.
let hydrated = false;

let patchTimer: ReturnType<typeof setTimeout> | null = null;

function schedulePatch() {
	if (patchTimer) clearTimeout(patchTimer);
	patchTimer = setTimeout(flushPatch, PATCH_DEBOUNCE_MS);
}

async function flushPatch() {
	patchTimer = null;
	if (!hydrated) return;
	const auth = get(authStore);
	if (!auth?.accessToken) return;

	const current = get(settingsStore);
	const drifted: Record<string, unknown> = {};
	for (const key of SERVER_KEYS) {
		if (current[key] !== serverState[key]) drifted[key] = current[key];
	}
	if (Object.keys(drifted).length === 0) return;

	try {
		const res = await fetch('/api/v1/login/me/config', {
			method: 'PATCH',
			headers: {
				'Content-Type': 'application/json',
				Authorization: `Bearer ${auth.accessToken}`
			},
			body: JSON.stringify(drifted)
		});
		if (res.ok) {
			const next = (await res.json()) as Record<string, unknown>;
			for (const key of SERVER_KEYS) serverState[key] = next[key];
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
	// Called even for a user with no config yet. The gate is "we have read
	// from the server", not "the server had something to say" -- returning
	// early here would leave `hydrated` false forever and the client could
	// never save a setting at all.
	serverState = {};
	const patch: Partial<Settings> = {};

	const incomingDark = serverConfig?.darkMode;
	if (typeof incomingDark === 'boolean') {
		serverState.darkMode = incomingDark;
		patch.darkMode = incomingDark;
	}

	const incomingZone = serverConfig?.timezone;
	if (typeof incomingZone === 'string' && incomingZone) {
		serverState.timezone = incomingZone;
		patch.timezone = incomingZone;
	}

	if (Object.keys(patch).length > 0) {
		settingsStore.update((s) => ({ ...s, ...patch }));
	}

	// Set last: the update above notifies the subscriber, and it must not
	// schedule a patch for the values it has just been handed.
	hydrated = true;
}

/** The zone every temporal cell is read and written through. */
export function currentZone(): string {
	return get(settingsStore).timezone || browserZone();
}

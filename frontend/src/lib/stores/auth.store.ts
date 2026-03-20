// src/lib/stores/auth.store.ts

import { writable } from 'svelte/store';
import { browser } from '$app/environment';
import type { LoginInfo } from '$lib/types/auth';

const STORAGE_KEY = 'loginInfo';

function load(): LoginInfo | null {
	if (!browser) return null;
	try {
		return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null');
	} catch {
		return null;
	}
}

export const authStore = writable<LoginInfo | null>(load());

if (browser) {
	authStore.subscribe((v) =>
		v ? localStorage.setItem(STORAGE_KEY, JSON.stringify(v)) : localStorage.removeItem(STORAGE_KEY)
	);
}

export const logout = () => authStore.set(null);

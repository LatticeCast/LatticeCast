// lib/backend/http.ts
// Shared auth header helpers for backend API clients

import { get } from 'svelte/store';
import { authStore } from '$lib/stores/auth.store';

/** Returns auth headers with JSON content-type. Throws if not authenticated. */
export async function getAuthHeaders(): Promise<Record<string, string>> {
	const auth = get(authStore);
	if (!auth?.accessToken) {
		throw new Error('Not authenticated');
	}
	return {
		Authorization: `Bearer ${auth.accessToken}`,
		'Content-Type': 'application/json'
	};
}

/** Returns bare Authorization header only. Throws if not authenticated. */
export async function getBearerHeader(): Promise<Record<string, string>> {
	const auth = get(authStore);
	if (!auth?.accessToken) {
		throw new Error('Not authenticated');
	}
	return { Authorization: `Bearer ${auth.accessToken}` };
}

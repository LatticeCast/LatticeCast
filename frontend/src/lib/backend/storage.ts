// lib/backend/storage.ts
// Storage API client for persisting JSON data to backend

import { get } from 'svelte/store';
import { authStore } from '$lib/stores/auth.store';
import { BACKEND_URL } from './config';

async function getAuthHeaders(): Promise<HeadersInit> {
	const auth = get(authStore);
	if (!auth?.accessToken) {
		throw new Error('Not authenticated');
	}
	return {
		Authorization: `Bearer ${auth.accessToken}`
	};
}

/**
 * Load JSON data from storage
 */
export async function loadJson<T>(path: string): Promise<T | null> {
	try {
		const headers = await getAuthHeaders();
		const response = await fetch(`${BACKEND_URL}/api/storage/file/${path}`, {
			headers
		});

		if (response.status === 404) {
			return null;
		}

		if (!response.ok) {
			throw new Error(`Failed to load: ${response.statusText}`);
		}

		return response.json();
	} catch (error) {
		console.error(`[Storage] Failed to load ${path}:`, error);
		return null;
	}
}

/**
 * Save JSON data to storage
 */
export async function saveJson<T>(path: string, data: T): Promise<boolean> {
	try {
		const headers = await getAuthHeaders();
		const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
		const formData = new FormData();
		formData.append('file', blob, path.split('/').pop() || 'data.json');

		const response = await fetch(`${BACKEND_URL}/api/storage/file/${path}`, {
			method: 'PUT',
			headers,
			body: formData
		});

		if (!response.ok) {
			throw new Error(`Failed to save: ${response.statusText}`);
		}

		return true;
	} catch (error) {
		console.error(`[Storage] Failed to save ${path}:`, error);
		return false;
	}
}

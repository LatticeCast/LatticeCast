import { get } from 'svelte/store';

import { authStore } from '$lib/stores/auth.store';
import { BACKEND_URL } from './config';

export class BackendApiError extends Error {
	constructor(
		message: string,
		public readonly status: number
	) {
		super(message);
		this.name = 'BackendApiError';
	}
}

type JsonRequestOptions = Omit<RequestInit, 'body' | 'headers'> & {
	body?: unknown;
	headers?: HeadersInit;
	accessToken?: string;
};

function apiUrl(path: string): string {
	return `${BACKEND_URL}/api/v1${path}`;
}

async function apiError(response: Response): Promise<BackendApiError> {
	let message = response.statusText || `Request failed (${response.status})`;
	try {
		const body: unknown = await response.json();
		if (
			typeof body === 'object' &&
			body !== null &&
			'detail' in body &&
			typeof body.detail === 'string'
		) {
			message = body.detail;
		}
	} catch {
		// A non-JSON error still retains its HTTP status and status text.
	}
	return new BackendApiError(message, response.status);
}

/** Call a backend JSON endpoint without an authentication token. */
export async function requestJson<T>(path: string, options: JsonRequestOptions = {}): Promise<T> {
	const { body, headers: suppliedHeaders, accessToken, ...init } = options;
	const headers = new Headers(suppliedHeaders);
	if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);

	let requestBody: BodyInit | undefined;
	if (body !== undefined) {
		if (body instanceof FormData || body instanceof Blob || body instanceof URLSearchParams) {
			requestBody = body;
		} else {
			headers.set('Content-Type', 'application/json');
			requestBody = JSON.stringify(body);
		}
	}

	const response = await fetch(apiUrl(path), { ...init, headers, body: requestBody });
	if (!response.ok) throw await apiError(response);
	if (response.status === 204) return undefined as T;
	return (await response.json()) as T;
}

/** Call an authenticated backend JSON endpoint using the current access token. */
export async function authenticatedRequestJson<T>(
	path: string,
	options: Omit<JsonRequestOptions, 'accessToken'> = {}
): Promise<T> {
	const accessToken = get(authStore)?.accessToken;
	if (!accessToken) throw new Error('Not authenticated');
	return requestJson<T>(path, { ...options, accessToken });
}

/** Download an authenticated binary response from the backend API. */
export async function authenticatedRequestBlob(path: string): Promise<Blob> {
	const accessToken = get(authStore)?.accessToken;
	if (!accessToken) throw new Error('Not authenticated');
	const response = await fetch(apiUrl(path), {
		headers: { Authorization: `Bearer ${accessToken}` }
	});
	if (!response.ok) throw await apiError(response);
	return response.blob();
}

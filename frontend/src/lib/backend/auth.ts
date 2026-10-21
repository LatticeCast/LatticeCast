// lib/backend/auth.ts
// Backend auth API calls

import { BackendApiError, requestJson } from './client';

export interface TokenResponse {
	access_token: string;
	refresh_token?: string;
	id_token?: string;
	expires_in?: number;
	userinfo: {
		sub: string;
		email: string;
		name?: string;
		picture?: string;
	};
}

export interface MeResponse {
	user_id: string;
	sub?: string;
	email: string;
	name?: string;
	picture?: string;
	provider: 'none';
	role?: string;
	user_name?: string;
	config?: Record<string, unknown>;
}

/**
 * Username + password login; the backend issues an LC-local access JWT.
 */
export async function login(user_name: string, password: string): Promise<TokenResponse> {
	return requestJson<TokenResponse>('/login/password', {
		method: 'POST',
		body: { user_name, password }
	});
}

/**
 * Get user info and role from backend /me endpoint.
 */
export async function fetchMe(accessToken: string): Promise<MeResponse | null> {
	return requestJson<MeResponse>('/login/me', { accessToken });
}

/**
 * Update the current user's email. Throws on 409 with message "email already registered".
 */
export async function updateEmail(email: string, accessToken: string): Promise<MeResponse> {
	try {
		return await requestJson<MeResponse>('/login/me/email', {
			method: 'PUT',
			accessToken,
			body: { email }
		});
	} catch (error) {
		if (error instanceof BackendApiError && error.status === 409) {
			throw new Error('email already registered');
		}
		throw error;
	}
}

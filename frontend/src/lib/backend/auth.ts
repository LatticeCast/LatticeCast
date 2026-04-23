// lib/backend/auth.ts
// Backend auth API calls

import { BACKEND_URL } from './config';
import type { AuthProvider } from '$lib/types/auth';

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
	provider: 'google' | 'authentik' | 'none';
	role?: string;
	user_name?: string;
}

/**
 * Username + password login. In AUTH_REQUIRED=false mode the backend ignores
 * the password and returns the resolved user_id UUID as access_token.
 */
export async function login(user_name: string, password: string): Promise<TokenResponse> {
	const response = await fetch(`${BACKEND_URL}/api/v1/login/password`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ user_name, password })
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: 'Login failed' }));
		throw new Error(error.detail || 'Login failed');
	}

	return response.json();
}

/**
 * Exchange auth code for tokens via backend.
 */
export async function exchangeCodeViaBackend(
	provider: AuthProvider,
	code: string,
	redirectUri: string,
	codeVerifier: string
): Promise<TokenResponse> {
	const response = await fetch(`${BACKEND_URL}/api/v1/login/${provider}/token`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			code,
			redirect_uri: redirectUri,
			code_verifier: codeVerifier
		})
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: 'Token exchange failed' }));
		throw new Error(error.detail || 'Token exchange failed');
	}

	return response.json();
}

/**
 * Get user info and role from backend /me endpoint.
 */
export async function fetchMe(accessToken: string): Promise<MeResponse | null> {
	const response = await fetch(`${BACKEND_URL}/api/v1/login/me`, {
		headers: { Authorization: `Bearer ${accessToken}` }
	});

	if (!response.ok) {
		return null;
	}

	return response.json();
}

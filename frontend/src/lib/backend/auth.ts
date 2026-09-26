// lib/backend/auth.ts
// Backend auth API calls

import { LatticeCastError } from '@latticecast/lattice-cast';
import type { AuthProvider } from '$lib/types/auth';
import { latticeCast } from './client';

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
	config?: Record<string, unknown>;
}

/**
 * Username + password login. In AUTH_REQUIRED=false mode the backend ignores
 * the password and returns the resolved user_id UUID as access_token.
 */
export async function login(user_name: string, password: string): Promise<TokenResponse> {
	return (await latticeCast.loginPassword(user_name, password)) as TokenResponse;
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
	return latticeCast.requestJson<TokenResponse>(`/login/${provider}/token`, {
		method: 'POST',
		body: {
			code,
			redirect_uri: redirectUri,
			code_verifier: codeVerifier
		}
	});
}

/**
 * Get user info and role from backend /me endpoint.
 */
export async function fetchMe(accessToken: string): Promise<MeResponse | null> {
	return latticeCast.fetchMe<MeResponse>(accessToken);
}

/**
 * Update the current user's email. Throws on 409 with message "email already registered".
 */
export async function updateEmail(email: string, accessToken: string): Promise<MeResponse> {
	try {
		return await latticeCast.requestJson<MeResponse>('/login/me/email', {
			method: 'PUT',
			accessToken,
			body: { email }
		});
	} catch (error) {
		if (error instanceof LatticeCastError && error.status === 409) {
			throw new Error('email already registered');
		}
		throw error;
	}
}

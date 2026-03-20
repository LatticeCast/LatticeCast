// lib/auth/auth.service.ts

import { providers } from './providers';
import { generateRandomString, generateCodeChallenge } from './pkce';
import type { AuthProvider, LoginInfo } from '$lib/types/auth';
import { exchangeCodeViaBackend, fetchMe } from '$lib/backend/auth';

export async function startLogin(providerName: AuthProvider) {
	const provider = providers[providerName];

	const codeVerifier = generateRandomString(128);
	const codeChallenge = await generateCodeChallenge(codeVerifier);
	const nonce = generateRandomString(32);

	// Store PKCE in sessionStorage
	sessionStorage.setItem(`pkce_${providerName}`, codeVerifier);
	sessionStorage.setItem(`state_${providerName}`, nonce);

	const params = new URLSearchParams({
		response_type: 'code',
		client_id: provider.clientId,
		redirect_uri: provider.redirectUri,
		scope: provider.scope,
		state: nonce,
		code_challenge: codeChallenge,
		code_challenge_method: 'S256'
	});

	// Google-specific: request offline access for refresh tokens
	if (providerName === 'google') {
		params.set('access_type', 'offline');
		params.set('prompt', 'consent');
	}

	console.log(`[OAuth] Starting ${providerName} login`);
	window.location.href = `${provider.authorizeUrl}?${params.toString()}`;
}

export async function handleOAuthCallback(
	providerName: AuthProvider,
	code: string,
	state: string
): Promise<LoginInfo> {
	const provider = providers[providerName];

	const savedState = sessionStorage.getItem(`state_${providerName}`);
	const verifier = sessionStorage.getItem(`pkce_${providerName}`);

	if (!verifier || state !== savedState) {
		throw new Error('Invalid OAuth state');
	}

	// Exchange code via backend (backend has secrets)
	const tokens = await exchangeCodeViaBackend(providerName, code, provider.redirectUri, verifier);

	// Get user info and role from backend
	const me = await fetchMe(tokens.access_token);

	// Clean up PKCE storage
	sessionStorage.removeItem(`pkce_${providerName}`);
	sessionStorage.removeItem(`state_${providerName}`);

	return {
		provider: providerName,
		accessToken: tokens.access_token,
		refreshToken: tokens.refresh_token,
		idToken: tokens.id_token,
		expiresAt: tokens.expires_in ? Math.floor(Date.now() / 1000) + tokens.expires_in : undefined,
		userInfo: {
			sub: tokens.userinfo.sub,
			email: tokens.userinfo.email,
			name: tokens.userinfo.name,
			picture: tokens.userinfo.picture
		},
		role: me?.role
	};
}

// lib/auth/providers/google.ts

import type { OAuthProviderConfig } from '$lib/types/auth';

export const googleProvider: OAuthProviderConfig = {
	name: 'google',
	authorizeUrl: 'https://accounts.google.com/o/oauth2/v2/auth',
	clientId: import.meta.env.VITE_GOOGLE_CLIENT_ID,
	redirectUri: import.meta.env.VITE_GOOGLE_REDIRECT_URI,
	scope: 'openid profile email'
};

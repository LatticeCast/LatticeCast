// lib/auth/providers/authentik.ts

import type { OAuthProviderConfig } from '$lib/types/auth';

export const authentikProvider: OAuthProviderConfig = {
	name: 'authentik',
	authorizeUrl: `${import.meta.env.VITE_AUTHENTIK_URL}/application/o/authorize/`,
	clientId: import.meta.env.VITE_AUTHENTIK_CLIENT_ID,
	redirectUri: import.meta.env.VITE_AUTHENTIK_REDIRECT_URI,
	scope: 'openid profile email'
};

// src/lib/types/auth.ts

export type AuthProvider = 'authentik' | 'google';

export interface UserInfo {
	sub: string;
	email?: string;
	name?: string;
	picture?: string;
}

export interface LoginInfo {
	provider: AuthProvider;
	accessToken: string;
	refreshToken?: string;
	idToken?: string;
	expiresAt?: number;
	userInfo?: UserInfo;
	role?: string;
}

export interface OAuthProviderConfig {
	name: AuthProvider;
	authorizeUrl: string;
	clientId: string;
	redirectUri: string;
	scope: string;
}

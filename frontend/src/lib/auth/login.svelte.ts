// lib/auth/login.svelte.ts
// Password login state + orchestration. UI imports these runes and calls submit().

import { goto } from '$app/navigation';
import { authStore } from '$lib/stores/auth.store';
import { login } from '$lib/backend/auth';
import { validateUserName } from '$lib/auth/validation';

export const loginState = $state({
	userId: '',
	password: '',
	error: '',
	loggingIn: false
});

export function validationError(): string {
	return validateUserName(loginState.userId);
}

export async function submit(): Promise<void> {
	const id = loginState.userId.trim();
	if (!id || validationError() || loginState.loggingIn) return;
	loginState.loggingIn = true;
	loginState.error = '';
	try {
		const tokens = await login(id, loginState.password);
		authStore.set({
			provider: 'none',
			accessToken: tokens.access_token,
			userInfo: {
				sub: tokens.userinfo.sub,
				email: tokens.userinfo.email,
				name: tokens.userinfo.name ?? id
			},
			role: 'user'
		});
		await goto('/');
	} catch (err) {
		loginState.error = err instanceof Error ? err.message : 'Login failed';
		loginState.loggingIn = false;
	}
}

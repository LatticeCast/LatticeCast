import { get } from 'svelte/store';
import { redirect } from '@sveltejs/kit';
import { authStore } from '$lib/stores/auth.store';
import type { LayoutLoad } from './$types';

// SPA — set once here for every route.
export const ssr = false;

// Routes reachable while logged out. Everything else requires a session.
const PUBLIC_PREFIXES = ['/login', '/callback'];

// Single auth gate for the whole app. authStore hydrates synchronously from
// localStorage on import, so this is reliable on hard refresh too. Individual
// pages must NOT repeat this check.
export const load: LayoutLoad = ({ url }) => {
	const isPublic = PUBLIC_PREFIXES.some((p) => url.pathname.startsWith(p));
	const authed = !!get(authStore)?.role;

	if (!authed && !isPublic) redirect(302, '/login');
};

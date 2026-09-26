import { createAuthenticatedJsonClient, createLatticeCastClient } from '@latticecast/lattice-cast';
import { get } from 'svelte/store';

import { authStore } from '$lib/stores/auth.store';
import { BACKEND_URL } from './config';

/** Canonical Lattice Cast client for unauthenticated and auth-specific calls. */
export const latticeCast = createLatticeCastClient({ backendDomain: BACKEND_URL });

/** Shared JSON controller client; authStore retains ownership of the token. */
export const authenticatedLatticeCast = createAuthenticatedJsonClient({
	client: latticeCast,
	getAccessToken: () => get(authStore)?.accessToken
});

// lib/backend/table_schemas.ts — fetch the sidebar preload payload.

import { BACKEND_URL } from './config';
import { getAuthHeaders } from './http';
import { applySidebar, type SidebarPayload } from '$lib/stores/table_schemas.store';

export async function fetchSidebar(): Promise<SidebarPayload> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/sidebar`, { headers });
	if (!response.ok) throw new Error(`Failed to fetch sidebar: ${response.statusText}`);
	const payload: SidebarPayload = await response.json();
	applySidebar(payload);
	return payload;
}

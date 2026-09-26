// lib/backend/table_schemas.ts — fetch the sidebar preload payload.

import { authenticatedLatticeCast } from './client';
import { applySidebar, type SidebarPayload } from '$lib/stores/table_schemas.store';

export async function fetchSidebar(): Promise<SidebarPayload> {
	const payload = await authenticatedLatticeCast.requestJson<SidebarPayload>('/sidebar');
	applySidebar(payload);
	return payload;
}

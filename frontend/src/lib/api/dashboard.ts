import { BACKEND_URL } from '$lib/backend/config';
import type { WidgetRow } from '$lib/types/dashboard';
import { authStore } from '$lib/stores/auth.store';
import { get } from 'svelte/store';

export async function fetchWidget(
	tableId: string,
	viewName: string,
	widgetId: string,
	runtimeParams?: Record<string, unknown>
): Promise<WidgetRow[]> {
	const auth = get(authStore);
	const r = await fetch(
		`${BACKEND_URL}/api/v1/tables/${tableId}/views/${encodeURIComponent(viewName)}/widgets/${widgetId}/query`,
		{
			method: 'POST',
			headers: {
				Authorization: `Bearer ${auth?.accessToken}`,
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({ params: runtimeParams ?? {} })
		}
	);
	if (!r.ok) throw new Error(`Widget query failed: ${r.status}`);
	const j = await r.json();
	return j.rows;
}

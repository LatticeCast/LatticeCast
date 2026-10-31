import type { PageLoad } from './$types';
import { get } from 'svelte/store';
import { error } from '@sveltejs/kit';
import { tables } from '$lib/stores/table_schemas.store';
import { resolveTableForPath } from '$lib/utils/table-route';
import { fetchViews } from '$lib/backend/views';
import { fetchAllRows, fetchTable } from '$lib/backend/tables';
import { authStore } from '$lib/stores/auth.store';
import type { ViewConfig, Row, Table } from '$lib/types/table';

export const load: PageLoad = async ({ params, url }) => {
	const urlViewRaw = url.searchParams.get('view');
	const wsParam = params.workspace_id;
	const hasSession = !!get(authStore)?.accessToken;
	const resolved = hasSession ? await resolveTableForPath(wsParam, params.table_id) : null;
	if (hasSession && !resolved) throw error(404, 'Table not found');
	const tableParam = resolved?.table_id ?? 0;
	const resolvedWsId = resolved?.workspace_id ?? null;
	const cached = get(tables).find((table) => table.table_id === tableParam);

	let viewsP: Promise<ViewConfig[]> | null = null;
	let rowsP: Promise<Row[]> | null = null;
	let tableP: Promise<Table> | null = null;

	if (hasSession && resolved) {
		viewsP = fetchViews(tableParam);
		rowsP = fetchAllRows(tableParam);
		if (!cached) {
			tableP = fetchTable(tableParam, resolvedWsId ?? undefined);
		}
	}

	return {
		workspaceParam: wsParam,
		tableParam,
		urlViewId: urlViewRaw !== null ? Number(urlViewRaw) : NaN,
		cached,
		resolvedWsId,
		viewsP,
		rowsP,
		tableP
	};
};

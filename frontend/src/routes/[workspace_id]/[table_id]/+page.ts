import type { PageLoad } from './$types';
import { get } from 'svelte/store';
import { workspaces, tables, resolveWorkspaceParam } from '$lib/stores/table_schemas.store';
import { fetchViews } from '$lib/backend/views';
import { fetchRows, fetchTable } from '$lib/backend/tables';
import { authStore } from '$lib/stores/auth.store';
import type { ViewConfig, Row, Table } from '$lib/types/table';

export const load: PageLoad = ({ params, url }) => {
	const urlViewRaw = url.searchParams.get('view');
	const tableParam = params.table_id;
	const wsParam = params.workspace_id;

	const wsList = get(workspaces);
	const resolvedWsId = resolveWorkspaceParam(wsParam, wsList);
	const cached = get(tables).find(
		(t) => t.table_id === tableParam && (!resolvedWsId || t.workspace_id === resolvedWsId)
	);

	let viewsP: Promise<ViewConfig[]> | null = null;
	let rowsP: Promise<Row[]> | null = null;
	let tableP: Promise<Table> | null = null;

	if (get(authStore)?.accessToken) {
		viewsP = fetchViews(tableParam);
		rowsP = fetchRows(tableParam);
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

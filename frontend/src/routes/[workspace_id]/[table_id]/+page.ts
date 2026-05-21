import { get } from 'svelte/store';
import { redirect } from '@sveltejs/kit';
import { authStore } from '$lib/stores/auth.store';
import { fetchTable, fetchRows } from '$lib/backend/tables';
import { fetchWorkspaces } from '$lib/backend/workspaces';
import {
	currentWorkspaceId,
	currentTableId,
	resolveWorkspaceParam
} from '$lib/stores/table_schemas.store';
import type { PageLoad } from './$types';

export const ssr = false;

export const load: PageLoad = async ({ params, url }) => {
	const auth = get(authStore);
	if (!auth?.role) redirect(302, '/login');

	const wsList = await fetchWorkspaces();
	const resolvedWsId = resolveWorkspaceParam(params.workspace_id, wsList);
	const table = await fetchTable(params.table_id, resolvedWsId ?? undefined);
	await fetchRows(table.table_id);

	currentTableId.set(table.table_id);
	currentWorkspaceId.set(table.workspace_id);

	const urlViewRaw = url.searchParams.get('view');
	const urlViewId = urlViewRaw !== null ? Number(urlViewRaw) : NaN;

	return {
		table,
		urlViewId
	};
};

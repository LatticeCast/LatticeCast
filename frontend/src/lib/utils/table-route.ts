import { get } from 'svelte/store';

import { fetchWorkspacesTables } from '$lib/backend/table_schemas';
import { tables, workspaces, type PreloadTable } from '$lib/stores/table_schemas.store';
import type { Workspace } from '$lib/types/table';
import { findWorkspace, tableSlugs } from './slugs';

/** Resolve a browser path to the numeric identity used by the API. */
export function findTableForPath(
	workspaceParam: string,
	tableParam: string,
	workspaceList: Pick<Workspace, 'workspace_id' | 'workspace_name' | 'created_at'>[],
	tableList: Pick<PreloadTable, 'workspace_id' | 'table_id' | 'table_name'>[]
) {
	const tableName = decodeURIComponent(tableParam);
	const workspace = findWorkspace(workspaceParam, workspaceList);
	if (!workspace) return null;

	const candidates = tableList.filter((table) => table.workspace_id === workspace.workspace_id);
	// A name is always a name, even if it consists only of digits.
	for (const [table, slug] of tableSlugs(workspace.workspace_id, candidates)) {
		if (slug === tableName) return table;
	}

	// Keep existing numeric bookmarks readable while presenting named URLs.
	if (!/^[1-9]\d*$/.test(tableName)) return null;
	return candidates.find((table) => table.table_id === Number(tableName)) ?? null;
}

export async function resolveTableForPath(workspaceParam: string, tableParam: string) {
	let table = findTableForPath(workspaceParam, tableParam, get(workspaces), get(tables));
	if (table) return table;
	// The sidebar stores are empty on a direct browser visit. Fetch the same
	// authorised table list used by navigation before resolving the name.
	await fetchWorkspacesTables();
	table = findTableForPath(workspaceParam, tableParam, get(workspaces), get(tables));
	return table;
}

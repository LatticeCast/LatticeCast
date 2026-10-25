import { get } from 'svelte/store';

import { fetchSidebar } from '$lib/backend/table_schemas';
import { tables, workspaces, type SidebarTable } from '$lib/stores/table_schemas.store';
import type { Workspace } from '$lib/types/table';
import { isUuid } from './url';

/** Resolve a browser path to the numeric identity used by the API. */
export function findTableForPath(
	workspaceParam: string,
	tableParam: string,
	workspaceList: Pick<Workspace, 'workspace_id' | 'workspace_name'>[],
	tableList: Pick<SidebarTable, 'workspace_id' | 'table_id' | 'table_name'>[]
) {
	const workspaceName = decodeURIComponent(workspaceParam);
	const tableName = decodeURIComponent(tableParam);
	const matchingWorkspaces = workspaceList
		.filter((ws) =>
			isUuid(workspaceName)
				? ws.workspace_id === workspaceName
				: ws.workspace_name.toLowerCase() === workspaceName.toLowerCase()
		)
		.map((ws) => ws.workspace_id);
	if (matchingWorkspaces.length === 0) return null;

	const candidates = tableList.filter((table) => matchingWorkspaces.includes(table.workspace_id));
	// A name is always a name, even if it consists only of digits. When a
	// workspace name is shared, the first-created matching table wins.
	const byName = candidates
		.filter((table) => table.table_name === tableName)
		.sort((a, b) => a.table_id - b.table_id)[0];
	if (byName) return byName;

	// Keep existing numeric bookmarks readable while presenting named URLs.
	if (!/^[1-9]\d*$/.test(tableName)) return null;
	return candidates.find((table) => table.table_id === Number(tableName)) ?? null;
}

export async function resolveTableForPath(workspaceParam: string, tableParam: string) {
	let table = findTableForPath(workspaceParam, tableParam, get(workspaces), get(tables));
	if (table) return table;
	// The sidebar stores are empty on a direct browser visit. Fetch the same
	// authorised table list used by navigation before resolving the name.
	await fetchSidebar();
	table = findTableForPath(workspaceParam, tableParam, get(workspaces), get(tables));
	return table;
}

// src/lib/utils/url.ts

import { goto } from '$app/navigation';
import { get } from 'svelte/store';
import { tables, workspaces } from '$lib/stores/table_schemas.store';
import { tableSlugs, workspaceSlug } from './slugs';
import { isUuid } from './url-id';

export { isUuid };

/**
 * Canonical path to a table. Sidebar and workspace-home both navigate
 * through this so a table click behaves identically wherever it lives.
 * The API keeps the numeric table identity; browser paths use names.
 */
export function tablePath(workspaceId: string, tableId: number): string {
	const list = get(workspaces);
	const workspace = list.find((ws) => ws.workspace_id === workspaceId);
	const workspaceName = workspace ? workspaceSlug(workspace, list) : workspaceId;
	const tableName = [...tableSlugs(workspaceId, get(tables))].find(
		([table]) => table.table_id === tableId
	)?.[1];
	return `/${encodeURIComponent(workspaceName)}/${encodeURIComponent(tableName ?? String(tableId))}`;
}

export function navigate(path: string): void {
	goto(path);
}

export function navigateToTable(workspaceId: string, tableId: number): void {
	goto(tablePath(workspaceId, tableId));
}

export function prettifyWorkspacePathname(
	pathname: string,
	workspaceId: string,
	workspaceName: string
): string {
	const encoded = encodeURIComponent(workspaceName);
	if (pathname.startsWith(`/${workspaceId}`)) {
		return `/${encoded}${pathname.slice(workspaceId.length + 1)}`;
	}
	return pathname;
}

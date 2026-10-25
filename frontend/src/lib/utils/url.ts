// src/lib/utils/url.ts

import { goto } from '$app/navigation';
import { get } from 'svelte/store';
import { tables, workspaces } from '$lib/stores/table_schemas.store';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(s: string): boolean {
	return UUID_RE.test(s);
}

/**
 * Canonical path to a table. Sidebar and workspace-home both navigate
 * through this so a table click behaves identically wherever it lives.
 * The API keeps the numeric table identity; browser paths use names.
 */
export function tablePath(workspaceId: string, tableId: number): string {
	const workspaceName = get(workspaces).find(
		(ws) => ws.workspace_id === workspaceId
	)?.workspace_name;
	const tableName = get(tables).find(
		(table) => table.workspace_id === workspaceId && table.table_id === tableId
	)?.table_name;
	return `/${encodeURIComponent(workspaceName ?? workspaceId)}/${encodeURIComponent(tableName ?? String(tableId))}`;
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

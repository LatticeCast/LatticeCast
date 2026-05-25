// src/lib/utils/url.ts

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(s: string): boolean {
	return UUID_RE.test(s);
}

/**
 * Canonical path to a table. Sidebar and workspace-home both navigate
 * through this so a table click behaves identically wherever it lives.
 * Uses workspace_id (UUID) — stable across renames; the layout prettifies
 * the URL to the workspace name afterwards.
 */
export function tablePath(workspaceId: string, tableId: string): string {
	return `/${workspaceId}/${tableId}`;
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

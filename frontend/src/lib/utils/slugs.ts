// URL names. Workspace and table names are looked up from the address bar, so
// duplicates are told apart by creation order: the first keeps its name, the
// second is `name-1`, the third `name-2` (0-based, the 0 is not written).

import type { Workspace } from '$lib/types/table';
import { isUuid } from './url-id';

/** Unique URL name per item. `items` must already be in creation order. */
function urlNames<T>(
	items: T[],
	name: (item: T) => string,
	key: (value: string) => string
): Map<T, string> {
	const result = new Map<T, string>();
	const taken = new Set<string>();
	const duplicates: T[] = [];
	// Real names first, so a workspace literally called `seo-1` keeps its own.
	for (const item of items) {
		if (taken.has(key(name(item)))) duplicates.push(item);
		else {
			taken.add(key(name(item)));
			result.set(item, name(item));
		}
	}
	for (const item of duplicates) {
		let n = 1;
		while (taken.has(key(`${name(item)}-${n}`))) n += 1;
		taken.add(key(`${name(item)}-${n}`));
		result.set(item, `${name(item)}-${n}`);
	}
	return result;
}

type NamedWorkspace = Pick<Workspace, 'workspace_id' | 'workspace_name' | 'created_at'>;
type NamedTable = { workspace_id: string; table_id: number; table_name: string };

function workspaceNames<T extends NamedWorkspace>(list: T[]): Map<T, string> {
	const ordered = [...list].sort(
		(a, b) =>
			a.created_at.localeCompare(b.created_at) || a.workspace_id.localeCompare(b.workspace_id)
	);
	return urlNames(
		ordered,
		(ws) => ws.workspace_name,
		(value) => value.toLowerCase()
	);
}

/** The URL name of `ws` among `list` (`ws` replaces any stale entry with its id). */
export function workspaceSlug(ws: NamedWorkspace, list: NamedWorkspace[]): string {
	const others = list.filter((item) => item.workspace_id !== ws.workspace_id);
	const known = list.find((item) => item.workspace_id === ws.workspace_id);
	const entry = { ...ws, created_at: known?.created_at || ws.created_at };
	return workspaceNames([...others, entry]).get(entry) ?? ws.workspace_name;
}

export function workspacePath(ws: NamedWorkspace, list: NamedWorkspace[]): string {
	return `/${encodeURIComponent(workspaceSlug(ws, list))}`;
}

/** Resolve a route parameter (a UUID or a URL name) to its workspace. */
export function findWorkspace<T extends NamedWorkspace>(param: string, list: T[]): T | null {
	const wanted = decodeURIComponent(param);
	// A workspace may be *named* like a UUID, so an unknown id falls through to names.
	if (isUuid(wanted)) {
		const byId = list.find((ws) => ws.workspace_id === wanted);
		if (byId) return byId;
	}
	for (const [ws, slug] of workspaceNames(list)) {
		if (slug.toLowerCase() === wanted.toLowerCase()) return ws;
	}
	return null;
}

/** URL name per table of one workspace. Table names are case-sensitive. */
export function tableSlugs<T extends NamedTable>(workspaceId: string, list: T[]): Map<T, string> {
	const ordered = list
		.filter((table) => table.workspace_id === workspaceId)
		.sort((a, b) => a.table_id - b.table_id);
	return urlNames(
		ordered,
		(table) => table.table_name,
		(value) => value
	);
}

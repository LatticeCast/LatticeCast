// src/lib/stores/menu.ts
//
// Model: pure SSOT for sidebar navigation (workspaces + tables).
// Controllers write here after BE calls. Derived stores for UI.

import { writable, derived } from 'svelte/store';
import type { Table, Workspace } from '$lib/types/table';

export const workspaces = writable<Workspace[]>([]);
export const currentWorkspaceId = writable<string | null>(null);
export const tables = writable<Table[]>([]);
export const currentTableId = writable<string | null>(null);
export const menuOpen = writable<boolean>(true);

export const currentWorkspace = derived(
	[workspaces, currentWorkspaceId],
	([$workspaces, $id]) => $workspaces.find((w) => w.workspace_id === $id) ?? null
);

export const workspaceTables = derived([tables, currentWorkspaceId], ([$tables, $wsId]) =>
	$wsId ? $tables.filter((t) => t.workspace_id === $wsId) : []
);

export const currentTable = derived(
	[tables, currentTableId],
	([$tables, $id]) => $tables.find((t) => t.table_id === $id) ?? null
);

export function toggleMenu(): void {
	menuOpen.update((v) => !v);
}

export function resetMenu(): void {
	workspaces.set([]);
	currentWorkspaceId.set(null);
	tables.set([]);
	currentTableId.set(null);
}

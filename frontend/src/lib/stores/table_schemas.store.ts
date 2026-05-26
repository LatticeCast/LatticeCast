// src/lib/stores/table_schemas.store.ts
//
// SSOT for sidebar + home: one bulk fetch via GET /api/v1/sidebar
// hydrates the whole menu tree, so first-table-click no longer pays a
// schema round-trip. Two independent arrays — workspaces + tables —
// because empty workspaces (zero tables) still need to appear.
//
// Replaces the old `menu.store.ts` (one path → one file).

import { writable, derived, get } from 'svelte/store';
import type { Column, Table, TableSchema, ViewConfig, Workspace } from '$lib/types/table';

export interface SidebarTable {
	workspace_id: string;
	table_id: string;
	config: {
		columns: Column[];
		view_order: number[];
		default_view: number;
	};
}

export interface SidebarPayload {
	workspaces: { workspace_id: string; workspace_name: string }[];
	tables: SidebarTable[];
}

// ── Sidebar caches kept writable so per-mutation controllers can patch them
//    without re-running the bulk fetch. Hydrated by applySidebar().
export const workspaces = writable<Workspace[]>([]);
export const tables = writable<Table[]>([]);

// ── UI state ─────────────────────────────────────────────────────────────────
export const currentWorkspaceId = writable<string | null>(null);
export const currentTableId = writable<string | null>(null);
export const menuOpen = writable<boolean>(true);

// ── Derived helpers (same names as the old menu.store) ───────────────────
export const tablesByWorkspace = derived(tables, ($tables) => {
	const grouped: Record<string, Table[]> = {};
	for (const t of $tables) {
		if (!grouped[t.workspace_id]) grouped[t.workspace_id] = [];
		grouped[t.workspace_id].push(t);
	}
	return grouped;
});
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

// ── Per-table derived (all from tables + currentTableId) ─────────────────
export const columns = derived(currentTable, ($t) => $t?.columns ?? []);
export const viewOrder = derived(currentTable, ($t) => $t?.view_order ?? []);
export const defaultView = derived(currentTable, ($t) => $t?.default_view ?? 0);
export const views = derived(currentTable, ($t) => $t?.views ?? []);

export function applySchema(schema: TableSchema): void {
	const tid = get(currentTableId);
	if (!tid) return;
	patchTableCache(tid, {
		columns: schema.columns,
		view_order: schema.view_order,
		default_view: schema.default_view,
		views: schema.views
	});
}

export function applySidebar(payload: SidebarPayload): void {
	workspaces.set(
		payload.workspaces.map((w) => ({
			workspace_id: w.workspace_id,
			workspace_name: w.workspace_name,
			created_at: '',
			updated_at: ''
		}))
	);
	tables.update((existing) => {
		const byKey = new Map(existing.map((t) => [`${t.workspace_id}:${t.table_id}`, t]));
		return payload.tables.map((t) => {
			const prev = byKey.get(`${t.workspace_id}:${t.table_id}`);
			return {
				table_id: t.table_id,
				workspace_id: t.workspace_id,
				columns: t.config.columns ?? [],
				view_order: t.config.view_order ?? [],
				default_view: t.config.default_view ?? 0,
				views: prev?.views ?? [],
				created_at: prev?.created_at ?? '',
				updated_at: prev?.updated_at ?? ''
			};
		});
	});
}

export function patchTableCache(tableId: string, patch: Partial<Table>): void {
	tables.update((list) => {
		const idx = list.findIndex((t) => t.table_id === tableId);
		if (idx >= 0) return list.map((t) => (t.table_id === tableId ? { ...t, ...patch } : t));
		return list;
	});
}

export function toggleMenu(): void {
	menuOpen.update((v) => !v);
}

export function resolveWorkspaceParam(param: string, wsList: Workspace[]): string | null {
	if (/^[0-9a-f]{8}-/.test(param)) {
		return wsList.some((w) => w.workspace_id === param) ? param : null;
	}
	const decoded = decodeURIComponent(param);
	return wsList.find((w) => w.workspace_name === decoded)?.workspace_id ?? null;
}

export function resetMenu(): void {
	workspaces.set([]);
	tables.set([]);
	currentWorkspaceId.set(null);
	currentTableId.set(null);
}

export async function initSidebar(): Promise<void> {
	try {
		const { fetchSidebar } = await import('$lib/backend/table_schemas');
		await fetchSidebar();
	} catch {
		// best-effort
	}
}

export function resetSidebar(): void {
	workspaces.set([]);
	tables.set([]);
}

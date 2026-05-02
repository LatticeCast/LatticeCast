// src/lib/stores/tables.store.ts

import { writable } from 'svelte/store';
import type { Column, Row, Table, UpdateView, ViewConfig, Workspace } from '$lib/types/table';
import { fetchTables, fetchTable, fetchRows } from '$lib/backend/tables';
import {
	createView as apiCreateView,
	deleteView as apiDeleteView,
	fetchViewOrder,
	fetchViews,
	putViewOrder,
	updateView as apiUpdateView
} from '$lib/backend/views';
import { fetchWorkspaces } from '$lib/backend/workspaces';

export const workspaces = writable<Workspace[]>([]);
export const currentWorkspace = writable<Workspace | null>(null);
export const tables = writable<Table[]>([]);
export const currentTable = writable<Table | null>(null);
export const columns = writable<Column[]>([]);
export const rows = writable<Row[]>([]);
export const views = writable<ViewConfig[]>([]);
export const viewOrder = writable<string[]>([]);
export const loading = writable(false);
export const error = writable<string | null>(null);
export const pageTitle = writable<string>('');

export async function loadWorkspaces(): Promise<void> {
	loading.set(true);
	error.set(null);
	try {
		const result = await fetchWorkspaces();
		workspaces.set(result);
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Failed to load workspaces');
	} finally {
		loading.set(false);
	}
}

export async function switchWorkspace(workspace: Workspace): Promise<void> {
	currentWorkspace.set(workspace);
	currentTable.set(null);
	columns.set([]);
	rows.set([]);
	loading.set(true);
	error.set(null);
	try {
		const result = await fetchTables();
		tables.set(result.filter((t) => t.workspace_id === workspace.workspace_id));
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Failed to load tables for workspace');
	} finally {
		loading.set(false);
	}
}

export async function loadTables(): Promise<void> {
	loading.set(true);
	error.set(null);
	try {
		const result = await fetchTables();
		tables.set(result);
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Failed to load tables');
	} finally {
		loading.set(false);
	}
}

export async function loadTable(table: Table): Promise<void> {
	currentTable.set(table);
	loading.set(true);
	error.set(null);
	try {
		const cols: Column[] = table.columns ?? [];
		const [rws, vws, ord] = await Promise.all([
			fetchRows(table.table_id),
			fetchViews(table.table_id),
			fetchViewOrder(table.table_id)
		]);
		columns.set(cols);
		rows.set(rws);
		views.set(vws);
		viewOrder.set(ord);
		currentTable.update((t) => (t ? { ...t, views: vws } : null));
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Failed to load table data');
	} finally {
		loading.set(false);
	}
}

export async function refreshTable(tableId: string): Promise<void> {
	try {
		const table = await fetchTable(tableId);
		currentTable.set(table);
		columns.set(table.columns ?? []);
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Failed to refresh table');
	}
}

export async function refreshRows(tableId: string): Promise<void> {
	try {
		const result = await fetchRows(tableId);
		rows.set(result);
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Failed to refresh rows');
	}
}

// ─── Views: per-view splice (no full-table refetch) ────────────────────────

export async function createView(
	tableId: string,
	data: { name: string; type: string; config?: Record<string, unknown> }
): Promise<ViewConfig> {
	const created = await apiCreateView(tableId, data);
	views.update((arr) => [...arr, created]);
	viewOrder.update((arr) => (arr.includes(created.name) ? arr : [...arr, created.name]));
	return created;
}

export async function updateView(
	tableId: string,
	viewName: string,
	updates: UpdateView
): Promise<ViewConfig> {
	const updated = await apiUpdateView(tableId, viewName, updates);
	views.update((arr) => arr.map((v) => (v.name === viewName ? updated : v)));
	if (updates.name && updates.name !== viewName) {
		viewOrder.update((arr) => arr.map((n) => (n === viewName ? updated.name : n)));
	}
	return updated;
}

export async function deleteView(tableId: string, viewName: string): Promise<void> {
	await apiDeleteView(tableId, viewName);
	views.update((arr) => arr.filter((v) => v.name !== viewName));
	viewOrder.update((arr) => arr.filter((n) => n !== viewName));
}

export async function reorderViews(tableId: string, order: string[]): Promise<string[]> {
	const cleaned = await putViewOrder(tableId, order);
	viewOrder.set(cleaned);
	return cleaned;
}

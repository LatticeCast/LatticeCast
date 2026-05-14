// src/lib/stores/tables.store.ts
//
// v40 pattern: every schema mutation returns the full TableSchema.
// applySchema() replaces local stores from that one response — FE never
// derives or merges schema state.

import { writable } from 'svelte/store';
import type {
	Column,
	Row,
	Table,
	TableSchema,
	UpdateView,
	ViewConfig,
	Workspace
} from '$lib/types/table';
import { fetchTables, fetchTable, fetchRows, patchSchema } from '$lib/backend/tables';
import {
	createView as apiCreateView,
	deleteView as apiDeleteView,
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

function applySchema(schema: TableSchema): void {
	columns.set(schema.columns);
	views.set(schema.views);
	viewOrder.set(schema.view_order);
}

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
		const rws = await fetchRows(table.table_id);
		columns.set(table.columns ?? []);
		rows.set(rws);
		views.set(table.views ?? []);
		viewOrder.set(table.view_order ?? []);
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
		views.set(table.views ?? []);
		viewOrder.set(table.view_order ?? []);
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

// ─── View CRUD — every call returns full TableSchema ───────────────────────

export async function createView(
	tableId: string,
	data: { name: string; type: string; config?: Record<string, unknown> }
): Promise<TableSchema> {
	const schema = await apiCreateView(tableId, data);
	applySchema(schema);
	return schema;
}

export async function updateView(
	tableId: string,
	viewId: number,
	updates: UpdateView
): Promise<TableSchema> {
	const schema = await apiUpdateView(tableId, viewId, updates);
	applySchema(schema);
	return schema;
}

export async function deleteView(tableId: string, viewId: number): Promise<TableSchema> {
	const schema = await apiDeleteView(tableId, viewId);
	applySchema(schema);
	return schema;
}

export async function reorderViews(tableId: string, order: number[]): Promise<TableSchema> {
	const schema = await patchSchema(tableId, { view_order: order });
	applySchema(schema);
	return schema;
}

export async function setDefaultView(
	tableId: string,
	viewId: number | null
): Promise<TableSchema> {
	const schema = await patchSchema(tableId, { default_view: viewId });
	applySchema(schema);
	return schema;
}

export async function reorderColumns(tableId: string, colOrder: string[]): Promise<TableSchema> {
	const schema = await patchSchema(tableId, { col_order: colOrder });
	applySchema(schema);
	return schema;
}

// src/lib/stores/tables.store.ts
//
// Backward-compat shim — re-exports from SSOT stores + controllers.
// New code should import directly:
//   Model:      lib/stores/{table_schema, table_views, table_rows, menu}.ts
//   Controller: lib/backend/{tables, views, workspaces}.ts

import { writable, get } from 'svelte/store';
import type { Table, TableSchema, UpdateView, Workspace } from '$lib/types/table';

// Local imports for use in orchestrator functions
import { columns, viewOrder, applySchema } from './table_schema';
import { views } from './table_views';
import { rows } from './table_rows';
import { workspaces, tables } from './menu';
import {
	fetchTable as _fetchTable,
	fetchRows as _fetchRows,
	patchSchema as _patchSchema,
	batchDocsExist as _batchDocsExist,
	createRow as _createRow,
	createColumn as _createColumn,
	updateColumn as _updateColumn,
	deleteColumn as _deleteColumn,
	updateRow as _updateRow,
	deleteRow as _deleteRow
} from '$lib/backend/tables';
import {
	createView as _apiCreateView,
	updateView as _apiUpdateView,
	deleteView as _apiDeleteView
} from '$lib/backend/views';
import { fetchWorkspaces as _apiFetchWorkspaces } from '$lib/backend/workspaces';

// ─── Re-export Model stores ───────────────────────────────────────────────────
export { columns, viewOrder, applySchema };
export { views };
export { rows };
export { workspaces, tables };

// ─── Re-export Controller functions ───────────────────────────────────────────
export {
	_fetchTable as fetchTable,
	_fetchRows as fetchRows,
	_patchSchema as patchSchema,
	_batchDocsExist as batchDocsExist,
	_createRow as createRow,
	_createColumn as createColumn,
	_updateColumn as updateColumn,
	_deleteColumn as deleteColumn,
	_updateRow as updateRow,
	_deleteRow as deleteRow
};

// ─── Legacy stores (will be removed once all consumers migrate) ───────────────
export const currentWorkspace = writable<Workspace | null>(null);
export const currentTable = writable<Table | null>(null);
export const loading = writable(false);
export const error = writable<string | null>(null);
export const pageTitle = writable<string>('');

// ─── Orchestrator functions ───────────────────────────────────────────────────

export async function loadWorkspaces(): Promise<void> {
	loading.set(true);
	error.set(null);
	try {
		await _apiFetchWorkspaces();
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
		const { fetchTables } = await import('$lib/backend/tables');
		await fetchTables();
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
		const { fetchTables } = await import('$lib/backend/tables');
		await fetchTables();
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
		await _fetchRows(table.table_id);
		columns.set(table.columns ?? []);
		views.set(table.views ?? []);
		viewOrder.set(table.view_order ?? []);
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Failed to load table data');
	} finally {
		loading.set(false);
	}
}

export async function refreshTable(tableId: string, workspaceId?: string): Promise<void> {
	const wsId = workspaceId ?? get(currentTable)?.workspace_id;
	try {
		const table = await _fetchTable(tableId, wsId);
		currentTable.set(table);
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Failed to refresh table');
	}
}

export async function refreshRows(tableId: string): Promise<void> {
	try {
		await _fetchRows(tableId);
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Failed to refresh rows');
	}
}

// ─── Schema-level patches ─────────────────────────────────────────────────────

export async function reorderColumns(tableId: string, colOrder: string[]): Promise<TableSchema> {
	return _patchSchema(tableId, { col_order: colOrder });
}

export async function setDefaultView(tableId: string, viewId: number | null): Promise<TableSchema> {
	return _patchSchema(tableId, { default_view: viewId });
}

export async function reorderViews(tableId: string, order: number[]): Promise<TableSchema> {
	return _patchSchema(tableId, { view_order: order });
}

// ─── View CRUD ────────────────────────────────────────────────────────────────

export async function createView(
	tableId: string,
	data: { name: string; type: string; config?: Record<string, unknown> }
): Promise<TableSchema> {
	return _apiCreateView(tableId, data);
}

export async function updateView(
	tableId: string,
	viewId: number,
	updates: UpdateView
): Promise<TableSchema> {
	return _apiUpdateView(tableId, viewId, updates);
}

export async function deleteView(tableId: string, viewId: number): Promise<TableSchema> {
	return _apiDeleteView(tableId, viewId);
}

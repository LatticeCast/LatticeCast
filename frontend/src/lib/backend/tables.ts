// lib/backend/tables.ts
//
// Controller: API calls + store updates.
// Every mutation calls BE, gets response, writes to SSOT stores.
// .svelte View just calls these functions — stores auto-update → UI re-renders.

import { get } from 'svelte/store';
import { authStore } from '$lib/stores/auth.store';
import { BACKEND_URL } from './config';
import { getAuthHeaders, getBearerHeader } from './http';
import { columns, viewOrder, applySchema } from '$lib/stores/table_schema.store';
import { views } from '$lib/stores/table_views.store';
import { rows } from '$lib/stores/table_rows.store';
import { tables, currentTableId } from '$lib/stores/table_schemas.store';
import type {
	Table,
	TableSchema,
	Row,
	CreateTable,
	CreateColumn,
	CreateRow,
	UpdateTable,
	UpdateColumn,
	UpdateRow
} from '$lib/types/table';

// ─── Table CRUD ───────────────────────────────────────────────────────────────

export async function fetchTables(): Promise<Table[]> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables`, { headers });
	if (!response.ok) throw new Error(`Failed to fetch tables: ${response.statusText}`);
	const result: Table[] = await response.json();
	tables.set(result);
	return result;
}

export async function fetchTable(tableId: string, workspaceId?: string): Promise<Table> {
	const headers = await getAuthHeaders();
	const qs = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : '';
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}${qs}`, { headers });
	if (!response.ok) throw new Error(`Failed to fetch table: ${response.statusText}`);
	const table: Table = await response.json();
	currentTableId.set(table.table_id);
	columns.set(table.columns ?? []);
	views.set(table.views ?? []);
	viewOrder.set(table.view_order ?? []);
	return table;
}

export async function createTable(data: CreateTable): Promise<Table> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables`, {
		method: 'POST',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to create table: ${response.statusText}`);
	const table: Table = await response.json();
	tables.update((list) => [...list, table]);
	return table;
}

export async function updateTable(tableId: string, data: UpdateTable): Promise<Table> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}`, {
		method: 'PUT',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) {
		const body = await response.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to update table: ${response.statusText}`);
	}
	const table: Table = await response.json();
	tables.update((list) => list.map((t) => (t.table_id === tableId ? table : t)));
	return table;
}

export async function deleteTable(tableId: string): Promise<void> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}`, {
		method: 'DELETE',
		headers
	});
	if (!response.ok) throw new Error(`Failed to delete table: ${response.statusText}`);
	tables.update((list) => list.filter((t) => t.table_id !== tableId));
	if (get(currentTableId) === tableId) currentTableId.set(null);
}

// ─── Columns — mutations return full TableSchema → applySchema ────────────────

export async function createColumn(tableId: string, data: CreateColumn): Promise<TableSchema> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/columns`, {
		method: 'POST',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to create column: ${response.statusText}`);
	const schema: TableSchema = await response.json();
	applySchema(schema);
	return schema;
}

export async function updateColumn(
	tableId: string,
	columnId: string,
	data: UpdateColumn
): Promise<TableSchema> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/columns/${columnId}`, {
		method: 'PATCH',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to update column: ${response.statusText}`);
	const schema: TableSchema = await response.json();
	applySchema(schema);
	return schema;
}

export async function deleteColumn(tableId: string, columnId: string): Promise<TableSchema> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/columns/${columnId}`, {
		method: 'DELETE',
		headers
	});
	if (!response.ok) throw new Error(`Failed to delete column: ${response.statusText}`);
	const schema: TableSchema = await response.json();
	applySchema(schema);
	return schema;
}

export async function patchSchema(
	tableId: string,
	data: { view_order?: number[]; default_view?: number | null; col_order?: string[] }
): Promise<TableSchema> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/schema`, {
		method: 'PATCH',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to patch schema: ${response.statusText}`);
	const schema: TableSchema = await response.json();
	applySchema(schema);
	return schema;
}

// ─── Rows — mutations update rows store ───────────────────────────────────────

export async function fetchRows(tableId: string, offset = 0, limit = 100): Promise<Row[]> {
	const headers = await getAuthHeaders();
	const response = await fetch(
		`${BACKEND_URL}/api/v1/tables/${tableId}/rows?offset=${offset}&limit=${limit}`,
		{ headers }
	);
	if (!response.ok) throw new Error(`Failed to fetch rows: ${response.statusText}`);
	const result: Row[] = await response.json();
	rows.set(result);
	return result;
}

export async function createRow(tableId: string, data: CreateRow): Promise<Row> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/rows`, {
		method: 'POST',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to create row: ${response.statusText}`);
	const row: Row = await response.json();
	rows.update((r) => [...r, row]);
	return row;
}

export async function updateRow(tableId: string, rowNumber: number, data: UpdateRow): Promise<Row> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/rows/${rowNumber}`, {
		method: 'PUT',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to update row: ${response.statusText}`);
	const row: Row = await response.json();
	rows.update((r) => r.map((existing) => (existing.row_id === rowNumber ? row : existing)));
	return row;
}

export async function deleteRow(tableId: string, rowNumber: number): Promise<void> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/rows/${rowNumber}`, {
		method: 'DELETE',
		headers
	});
	if (!response.ok) throw new Error(`Failed to delete row: ${response.statusText}`);
	rows.update((r) => r.filter((row) => row.row_id !== rowNumber));
}

// ─── Docs ─────────────────────────────────────────────────────────────────────

export async function fetchDoc(tableId: string, rowNumber: number): Promise<string> {
	const headers = await getBearerHeader();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/rows/${rowNumber}/doc`, {
		headers
	});
	if (!response.ok) throw new Error(`Failed to fetch doc: ${response.statusText}`);
	return response.text();
}

export async function saveDoc(
	tableId: string,
	rowNumber: number,
	content: string
): Promise<string> {
	const headers = await getBearerHeader();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/rows/${rowNumber}/doc`, {
		method: 'PUT',
		headers: { ...headers, 'Content-Type': 'text/plain' },
		body: content
	});
	if (!response.ok) throw new Error(`Failed to save doc: ${response.statusText}`);
	return response.text();
}

export async function checkDocExists(tableId: string, rowNumber: number): Promise<boolean> {
	const auth = get(authStore);
	if (!auth?.accessToken) return false;
	try {
		const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/rows/${rowNumber}/doc`, {
			method: 'HEAD',
			headers: { Authorization: `Bearer ${auth.accessToken}` }
		});
		if (!response.ok) return false;
		const length = response.headers.get('content-length');
		return length !== null && parseInt(length, 10) > 0;
	} catch {
		return false;
	}
}

export async function batchDocsExist(tableId: string): Promise<Set<number>> {
	const auth = get(authStore);
	if (!auth?.accessToken) return new Set();
	try {
		const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/docs-exist`, {
			headers: { Authorization: `Bearer ${auth.accessToken}` }
		});
		if (!response.ok) return new Set();
		const data = await response.json();
		return new Set(data.row_ids as number[]);
	} catch {
		return new Set();
	}
}

// ─── Templates ────────────────────────────────────────────────────────────────

export async function createPmTemplate(table_id: string, workspaceId: string): Promise<Table> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/template/pm`, {
		method: 'POST',
		headers,
		body: JSON.stringify({ table_id: table_id, workspace_id: workspaceId })
	});
	if (!response.ok) throw new Error(`Failed to create PM template: ${response.statusText}`);
	const table: Table = await response.json();
	tables.update((list) => [...list, table]);
	return table;
}

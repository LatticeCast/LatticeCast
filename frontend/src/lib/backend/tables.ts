// lib/backend/tables.ts
//
// Controller: API calls + store updates.
// Every mutation calls BE, gets response, writes to SSOT stores.
// .svelte View just calls these functions — stores auto-update → UI re-renders.

import { get } from 'svelte/store';
import { authStore } from '$lib/stores/auth.store';
import { authenticatedLatticeCast, latticeCast } from './client';
import { BACKEND_URL } from './config';
import { getAuthHeaders, getBearerHeader } from './http';
import { applySchema } from '$lib/stores/table_schema.store';
import { rows } from '$lib/stores/table_rows.store';
import { tables, currentTableId } from '$lib/stores/table_schemas.store';
import type {
	Table,
	TableSchema,
	Row,
	BlobCellMetadata,
	CreateTable,
	CreateColumn,
	CreateRow,
	UpdateTable,
	UpdateColumn,
	UpdateRow
} from '$lib/types/table';

// ─── Table CRUD ───────────────────────────────────────────────────────────────

export async function fetchTables(): Promise<Table[]> {
	const result = await authenticatedLatticeCast.requestJson<Table[]>('/tables');
	tables.set(result);
	return result;
}

export async function fetchTable(tableId: string, workspaceId?: string): Promise<Table> {
	const qs = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : '';
	const table = await authenticatedLatticeCast.requestJson<Table>(`/tables/${tableId}${qs}`);
	currentTableId.set(table.table_id);
	tables.update((list) => {
		const idx = list.findIndex((t) => t.table_id === table.table_id);
		if (idx >= 0) return list.map((t) => (t.table_id === table.table_id ? table : t));
		return [...list, table];
	});
	return table;
}

export async function createTable(data: CreateTable): Promise<Table> {
	const table = await authenticatedLatticeCast.requestJson<Table>('/tables', {
		method: 'POST',
		body: data
	});
	tables.update((list) => [...list, table]);
	return table;
}

export async function updateTable(tableId: string, data: UpdateTable): Promise<Table> {
	const table = await authenticatedLatticeCast.requestJson<Table>(`/tables/${tableId}`, {
		method: 'PUT',
		body: data
	});
	tables.update((list) => list.map((t) => (t.table_id === tableId ? table : t)));
	return table;
}

export async function deleteTable(tableId: string): Promise<void> {
	await authenticatedLatticeCast.requestJson<void>(`/tables/${tableId}`, { method: 'DELETE' });
	tables.update((list) => list.filter((t) => t.table_id !== tableId));
	if (get(currentTableId) === tableId) currentTableId.set(null);
}

// ─── Columns — mutations return full TableSchema → applySchema ────────────────

export async function createColumn(tableId: string, data: CreateColumn): Promise<TableSchema> {
	const schema = await authenticatedLatticeCast.requestJson<TableSchema>(
		`/tables/${tableId}/columns`,
		{
			method: 'POST',
			body: data
		}
	);
	applySchema(schema);
	return schema;
}

export async function updateColumn(
	tableId: string,
	columnId: string,
	data: UpdateColumn
): Promise<TableSchema> {
	const schema = await authenticatedLatticeCast.requestJson<TableSchema>(
		`/tables/${tableId}/columns/${columnId}`,
		{
			method: 'PATCH',
			body: data
		}
	);
	applySchema(schema);
	return schema;
}

export async function deleteColumn(tableId: string, columnId: string): Promise<TableSchema> {
	const schema = await authenticatedLatticeCast.requestJson<TableSchema>(
		`/tables/${tableId}/columns/${columnId}`,
		{
			method: 'DELETE'
		}
	);
	applySchema(schema);
	return schema;
}

export async function patchSchema(
	tableId: string,
	data: { view_order?: number[]; default_view?: number; col_order?: string[] }
): Promise<TableSchema> {
	const schema = await authenticatedLatticeCast.requestJson<TableSchema>(`/tables/${tableId}`, {
		method: 'PATCH',
		body: data
	});
	applySchema(schema);
	return schema;
}

// ─── Rows — mutations update rows store ───────────────────────────────────────

export async function fetchRows(tableId: string, offset = 0, limit = 100): Promise<Row[]> {
	const result = await authenticatedLatticeCast.requestJson<Row[]>(
		`/tables/${tableId}/rows?offset=${offset}&limit=${limit}`
	);
	rows.set(result);
	return result;
}

export async function createRow(tableId: string, data: CreateRow): Promise<Row> {
	const row = await authenticatedLatticeCast.requestJson<Row>(`/tables/${tableId}/rows`, {
		method: 'POST',
		body: data
	});
	rows.update((r) => [...r, row]);
	return row;
}

export async function updateRow(tableId: string, rowNumber: number, data: UpdateRow): Promise<Row> {
	const row = await authenticatedLatticeCast.requestJson<Row>(
		`/tables/${tableId}/rows/${rowNumber}`,
		{
			method: 'PUT',
			body: data
		}
	);
	rows.update((r) => r.map((existing) => (existing.row_id === rowNumber ? row : existing)));
	return row;
}

export async function deleteRow(tableId: string, rowNumber: number): Promise<void> {
	await authenticatedLatticeCast.requestJson<void>(`/tables/${tableId}/rows/${rowNumber}`, {
		method: 'DELETE'
	});
	rows.update((r) => r.filter((row) => row.row_id !== rowNumber));
}

// ─── Docs ─────────────────────────────────────────────────────────────────────

/** Read the legacy default document attached to a row. */
export async function fetchDoc(tableId: string, rowNumber: number): Promise<string> {
	const headers = await getBearerHeader();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/rows/${rowNumber}/doc`, {
		headers
	});
	if (!response.ok) throw new Error(`Failed to fetch doc: ${response.statusText}`);
	return response.text();
}

/** Read a document from one explicitly selected blob cell. */
export async function fetchDocCell(
	tableId: string,
	rowNumber: number,
	columnId: string
): Promise<string> {
	const headers = await getBearerHeader();
	const response = await fetch(
		`${BACKEND_URL}/api/v1/tables/${tableId}/rows/${rowNumber}/blob/${columnId}/doc`,
		{ headers }
	);
	if (!response.ok) throw new Error(`Failed to fetch doc: ${response.statusText}`);
	return response.text();
}

/** Save the legacy default document attached to a row. */
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

/** Save a document into one explicitly selected blob cell. */
export async function saveDocCell(
	tableId: string,
	rowNumber: number,
	columnId: string,
	content: string
): Promise<BlobCellMetadata> {
	const headers = await getBearerHeader();
	const response = await fetch(
		`${BACKEND_URL}/api/v1/tables/${tableId}/rows/${rowNumber}/blob/${columnId}/doc`,
		{
			method: 'PUT',
			headers: { ...headers, 'Content-Type': 'text/plain' },
			body: content
		}
	);
	if (!response.ok) {
		const detail = await response.text();
		throw new Error(`Failed to save doc (${response.status}): ${detail || response.statusText}`);
	}
	const metadata: BlobCellMetadata = await response.json();
	rows.update((list) =>
		list.map((row) =>
			row.row_id === rowNumber
				? { ...row, row_data: { ...row.row_data, [columnId]: metadata } }
				: row
		)
	);
	return metadata;
}

/** Upload one arbitrary file into an explicitly selected blob cell. */
export async function uploadBlobCell(
	tableId: string,
	rowNumber: number,
	columnId: string,
	file: File
): Promise<BlobCellMetadata> {
	const accessToken = get(authStore)?.accessToken;
	if (!accessToken) throw new Error('Not authenticated');
	const metadata = await latticeCast.uploadTableBlob<BlobCellMetadata>(accessToken, {
		tableId,
		rowId: rowNumber,
		columnId,
		file,
		fileName: file.name
	});
	rows.update((list) =>
		list.map((row) =>
			row.row_id === rowNumber
				? { ...row, row_data: { ...row.row_data, [columnId]: metadata } }
				: row
		)
	);
	return metadata;
}

/** Download an explicitly selected blob cell using the current authenticated session. */
export async function downloadBlobCell(
	tableId: string,
	rowNumber: number,
	columnId: string,
	filename: string
): Promise<void> {
	const accessToken = get(authStore)?.accessToken;
	if (!accessToken) throw new Error('Not authenticated');
	const blob = await latticeCast.downloadTableBlob(accessToken, {
		tableId,
		rowId: rowNumber,
		columnId
	});

	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = filename;
	link.style.display = 'none';
	document.body.appendChild(link);
	link.click();
	link.remove();
	window.setTimeout(() => URL.revokeObjectURL(url), 0);
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
		const data = await authenticatedLatticeCast.requestJson<{ row_ids: number[] }>(
			`/tables/${tableId}/docs-exist`
		);
		return new Set(data.row_ids as number[]);
	} catch {
		return new Set();
	}
}

// ─── Templates ────────────────────────────────────────────────────────────────

export async function createFromTemplate(
	kind: string,
	table_id: string,
	workspaceId: string
): Promise<Table> {
	const table = await authenticatedLatticeCast.requestJson<Table>(
		`/tables/template/${encodeURIComponent(kind)}`,
		{ method: 'POST', body: { table_id, workspace_id: workspaceId } }
	);
	tables.update((list) => [...list, table]);
	return table;
}

export async function createPmTemplate(table_id: string, workspaceId: string): Promise<Table> {
	return createFromTemplate('pm', table_id, workspaceId);
}

// lib/backend/tables.ts
//
// Controller: API calls + store updates.
// Every mutation calls BE, gets response, writes to SSOT stores.
// .svelte View just calls these functions — stores auto-update → UI re-renders.

import { get } from 'svelte/store';
import { BackendApiError, authenticatedRequestBlob, authenticatedRequestJson } from './client';
import { applySchema, columns } from '$lib/stores/table_schema.store';
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
	const result = await authenticatedRequestJson<Table[]>('/tables');
	tables.set(result);
	return result;
}

export async function fetchTable(tableId: string, workspaceId?: string): Promise<Table> {
	const qs = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : '';
	const table = await authenticatedRequestJson<Table>(`/tables/${tableId}${qs}`);
	currentTableId.set(table.table_id);
	tables.update((list) => {
		const idx = list.findIndex((t) => t.table_id === table.table_id);
		if (idx >= 0) return list.map((t) => (t.table_id === table.table_id ? table : t));
		return [...list, table];
	});
	return table;
}

export async function createTable(data: CreateTable): Promise<Table> {
	const table = await authenticatedRequestJson<Table>('/tables', {
		method: 'POST',
		body: data
	});
	tables.update((list) => [...list, table]);
	return table;
}

export async function updateTable(tableId: string, data: UpdateTable): Promise<Table> {
	const table = await authenticatedRequestJson<Table>(`/tables/${tableId}`, {
		method: 'PUT',
		body: data
	});
	tables.update((list) => list.map((t) => (t.table_id === tableId ? table : t)));
	return table;
}

export async function deleteTable(tableId: string): Promise<void> {
	await authenticatedRequestJson<void>(`/tables/${tableId}`, { method: 'DELETE' });
	tables.update((list) => list.filter((t) => t.table_id !== tableId));
	if (get(currentTableId) === tableId) currentTableId.set(null);
}

// ─── Columns — mutations return full TableSchema → applySchema ────────────────

export async function createColumn(tableId: string, data: CreateColumn): Promise<TableSchema> {
	const schema = await authenticatedRequestJson<TableSchema>(`/tables/${tableId}/columns`, {
		method: 'POST',
		body: data
	});
	applySchema(schema);
	return schema;
}

export async function updateColumn(
	tableId: string,
	columnId: string,
	data: UpdateColumn
): Promise<TableSchema> {
	const schema = await authenticatedRequestJson<TableSchema>(
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
	const schema = await authenticatedRequestJson<TableSchema>(
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
	const schema = await authenticatedRequestJson<TableSchema>(`/tables/${tableId}`, {
		method: 'PATCH',
		body: data
	});
	applySchema(schema);
	return schema;
}

// ─── Rows — mutations update rows store ───────────────────────────────────────

/** Blob descriptors can only be changed through the addressed blob API. */
function nonBlobRowData(data: Record<string, unknown>): Record<string, unknown> {
	const blobColumns = new Set(
		get(columns)
			.filter((column) => column.type === 'blob')
			.map((column) => column.column_id)
	);
	return Object.fromEntries(
		Object.entries(data).filter(([columnId]) => !blobColumns.has(columnId))
	);
}

export async function fetchRows(tableId: string, offset = 0, limit = 100): Promise<Row[]> {
	const result = await authenticatedRequestJson<Row[]>(
		`/tables/${tableId}/rows?offset=${offset}&limit=${limit}`
	);
	rows.set(result);
	return result;
}

export async function createRow(tableId: string, data: CreateRow): Promise<Row> {
	const row = await authenticatedRequestJson<Row>(`/tables/${tableId}/rows`, {
		method: 'POST',
		body: { ...data, row_data: nonBlobRowData(data.row_data ?? {}) }
	});
	rows.update((r) => [...r, row]);
	return row;
}

export async function updateRow(tableId: string, rowNumber: number, data: UpdateRow): Promise<Row> {
	const row = await authenticatedRequestJson<Row>(`/tables/${tableId}/rows/${rowNumber}`, {
		method: 'PATCH',
		body: { ...data, row_data: nonBlobRowData(data.row_data) }
	});
	rows.update((r) => r.map((existing) => (existing.row_id === rowNumber ? row : existing)));
	return row;
}

export async function deleteRow(tableId: string, rowNumber: number): Promise<void> {
	await authenticatedRequestJson<void>(`/tables/${tableId}/rows/${rowNumber}`, {
		method: 'DELETE'
	});
	rows.update((r) => r.filter((row) => row.row_id !== rowNumber));
}

// ─── Blob cells ───────────────────────────────────────────────────────────────

/** Fetch the original bytes from one explicitly selected blob cell. */
export async function fetchBlobCell(
	tableId: string,
	rowNumber: number,
	columnId: string
): Promise<Blob | null> {
	try {
		return await authenticatedRequestBlob(`/tables/${tableId}/rows/${rowNumber}/blob/${columnId}`);
	} catch (error) {
		if (error instanceof BackendApiError && error.status === 404) return null;
		throw error;
	}
}

/** Upload one arbitrary file into an explicitly selected blob cell. */
export async function uploadBlobCell(
	tableId: string,
	rowNumber: number,
	columnId: string,
	file: Blob,
	fileName = file instanceof File ? file.name : 'blob'
): Promise<BlobCellMetadata> {
	const formData = new FormData();
	formData.append('file', file, fileName);
	const metadata = await authenticatedRequestJson<BlobCellMetadata>(
		`/tables/${tableId}/rows/${rowNumber}/blob/${columnId}`,
		{ method: 'PUT', body: formData }
	);
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
	const blob = await authenticatedRequestBlob(
		`/tables/${tableId}/rows/${rowNumber}/blob/${columnId}`
	);

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

// ─── Templates ────────────────────────────────────────────────────────────────

export async function createFromTemplate(
	kind: string,
	table_id: string,
	workspaceId: string
): Promise<Table> {
	const table = await authenticatedRequestJson<Table>(
		`/tables/template/${encodeURIComponent(kind)}`,
		{ method: 'POST', body: { table_id, workspace_id: workspaceId } }
	);
	tables.update((list) => [...list, table]);
	return table;
}

export async function createPmTemplate(table_id: string, workspaceId: string): Promise<Table> {
	return createFromTemplate('pm', table_id, workspaceId);
}

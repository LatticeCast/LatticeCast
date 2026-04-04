// lib/backend/tables.ts
// API client for tables/rows CRUD (columns come from table.columns)

import { get } from 'svelte/store';
import { authStore } from '$lib/stores/auth.store';
import { BACKEND_URL } from './config';
import type {
	Table,
	Column,
	Row,
	CreateTable,
	CreateColumn,
	CreateRow,
	UpdateTable,
	UpdateColumn,
	UpdateRow
} from '$lib/types/table';

async function getAuthHeaders(): Promise<HeadersInit> {
	const auth = get(authStore);
	if (!auth?.accessToken) {
		throw new Error('Not authenticated');
	}
	return {
		Authorization: `Bearer ${auth.accessToken}`,
		'Content-Type': 'application/json'
	};
}

// Tables

export async function fetchTables(): Promise<Table[]> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/tables`, { headers });
	if (!response.ok) throw new Error(`Failed to fetch tables: ${response.statusText}`);
	return response.json();
}

export async function createTable(data: CreateTable): Promise<Table> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/tables`, {
		method: 'POST',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to create table: ${response.statusText}`);
	return response.json();
}

export async function fetchTable(tableId: string): Promise<Table> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/tables/${tableId}`, { headers });
	if (!response.ok) throw new Error(`Failed to fetch table: ${response.statusText}`);
	return response.json();
}

export async function updateTable(tableId: string, data: UpdateTable): Promise<Table> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/tables/${tableId}`, {
		method: 'PUT',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to update table: ${response.statusText}`);
	return response.json();
}

export async function deleteTable(tableId: string): Promise<void> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/tables/${tableId}`, {
		method: 'DELETE',
		headers
	});
	if (!response.ok) throw new Error(`Failed to delete table: ${response.statusText}`);
}

// Columns (mutations only — column list comes from table.columns)

export async function createColumn(tableId: string, data: CreateColumn): Promise<Column> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/tables/${tableId}/columns`, {
		method: 'POST',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to create column: ${response.statusText}`);
	return response.json();
}

export async function updateColumn(
	tableId: string,
	columnId: string,
	data: UpdateColumn
): Promise<Column> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/tables/${tableId}/columns/${columnId}`, {
		method: 'PUT',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to update column: ${response.statusText}`);
	return response.json();
}

export async function deleteColumn(tableId: string, columnId: string): Promise<void> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/tables/${tableId}/columns/${columnId}`, {
		method: 'DELETE',
		headers
	});
	if (!response.ok) throw new Error(`Failed to delete column: ${response.statusText}`);
}

// Rows

export async function fetchRows(tableId: string, offset = 0, limit = 100): Promise<Row[]> {
	const headers = await getAuthHeaders();
	const response = await fetch(
		`${BACKEND_URL}/api/tables/${tableId}/rows?offset=${offset}&limit=${limit}`,
		{ headers }
	);
	if (!response.ok) throw new Error(`Failed to fetch rows: ${response.statusText}`);
	return response.json();
}

export async function createRow(tableId: string, data: CreateRow): Promise<Row> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/tables/${tableId}/rows`, {
		method: 'POST',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to create row: ${response.statusText}`);
	return response.json();
}

export async function updateRow(rowId: string, data: UpdateRow): Promise<Row> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/rows/${rowId}`, {
		method: 'PUT',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to update row: ${response.statusText}`);
	return response.json();
}

export async function deleteRow(rowId: string): Promise<void> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/rows/${rowId}`, {
		method: 'DELETE',
		headers
	});
	if (!response.ok) throw new Error(`Failed to delete row: ${response.statusText}`);
}

// Docs

export async function fetchDoc(tableId: string, rowId: string): Promise<string> {
	const auth = get(authStore);
	if (!auth?.accessToken) throw new Error('Not authenticated');
	const response = await fetch(`${BACKEND_URL}/api/tables/${tableId}/rows/${rowId}/doc`, {
		headers: { Authorization: `Bearer ${auth.accessToken}` }
	});
	if (!response.ok) throw new Error(`Failed to fetch doc: ${response.statusText}`);
	return response.text();
}

export async function saveDoc(tableId: string, rowId: string, content: string): Promise<string> {
	const auth = get(authStore);
	if (!auth?.accessToken) throw new Error('Not authenticated');
	const response = await fetch(`${BACKEND_URL}/api/tables/${tableId}/rows/${rowId}/doc`, {
		method: 'PUT',
		headers: {
			Authorization: `Bearer ${auth.accessToken}`,
			'Content-Type': 'text/plain'
		},
		body: content
	});
	if (!response.ok) throw new Error(`Failed to save doc: ${response.statusText}`);
	return response.text();
}

export async function checkDocExists(tableId: string, rowId: string): Promise<boolean> {
	const auth = get(authStore);
	if (!auth?.accessToken) return false;
	try {
		const response = await fetch(`${BACKEND_URL}/api/tables/${tableId}/rows/${rowId}/doc`, {
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

export async function batchDocsExist(tableId: string): Promise<Set<string>> {
	const auth = get(authStore);
	if (!auth?.accessToken) return new Set();
	try {
		const response = await fetch(`${BACKEND_URL}/api/tables/${tableId}/docs-exist`, {
			headers: { Authorization: `Bearer ${auth.accessToken}` }
		});
		if (!response.ok) return new Set();
		const data = await response.json();
		return new Set(data.row_ids);
	} catch {
		return new Set();
	}
}

// Templates

export async function createPmTemplate(name: string, workspaceId: string): Promise<Table> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/tables/template/pm`, {
		method: 'POST',
		headers,
		body: JSON.stringify({ name, workspace_id: workspaceId })
	});
	if (!response.ok) throw new Error(`Failed to create PM template: ${response.statusText}`);
	return response.json();
}

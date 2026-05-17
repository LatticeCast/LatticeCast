// lib/backend/views.ts
//
// Controller: view CRUD → API call + applySchema to stores.

import { BACKEND_URL } from './config';
import { getAuthHeaders } from './http';
import { applySchema } from '$lib/stores/table_schema';
import type { TableSchema, UpdateView, ViewConfig } from '$lib/types/table';

// ── Reads ──────────────────────────────────────────────────────────────

export async function fetchViews(tableId: string): Promise<ViewConfig[]> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/views`, { headers });
	if (!response.ok) throw new Error(`Failed to fetch views: ${response.statusText}`);
	return response.json();
}

export async function fetchView(tableId: string, viewId: number): Promise<ViewConfig> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/views/${viewId}`, {
		headers
	});
	if (!response.ok) throw new Error(`Failed to fetch view: ${response.statusText}`);
	return response.json();
}

// ── Mutations — call API + applySchema ────────────────────────────────

export async function createView(
	tableId: string,
	data: { name: string; type: string; config?: Record<string, unknown> }
): Promise<TableSchema> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/views`, {
		method: 'POST',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to create view: ${response.statusText}`);
	const schema: TableSchema = await response.json();
	applySchema(schema);
	return schema;
}

export async function updateView(
	tableId: string,
	viewId: number,
	updates: UpdateView
): Promise<TableSchema> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/views/${viewId}`, {
		method: 'PUT',
		headers,
		body: JSON.stringify(updates)
	});
	if (!response.ok) throw new Error(`Failed to update view: ${response.statusText}`);
	const schema: TableSchema = await response.json();
	applySchema(schema);
	return schema;
}

export async function deleteView(tableId: string, viewId: number): Promise<TableSchema> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/views/${viewId}`, {
		method: 'DELETE',
		headers
	});
	if (!response.ok) throw new Error(`Failed to delete view: ${response.statusText}`);
	const schema: TableSchema = await response.json();
	applySchema(schema);
	return schema;
}

// lib/backend/views.ts
//
// V44+ pattern: every mutation endpoint returns the full TableSchema.
// The FE assigns the response directly to its store and never derives
// schema state locally.
//
// Schema-level reorder/default operations all go through one endpoint —
// PATCH /tables/{tid}/schema in $lib/backend/tables.ts (`patchSchema`).
// This module only handles view CRUD.

import { BACKEND_URL } from './config';
import { getAuthHeaders } from './http';
import type { TableSchema, UpdateView, ViewConfig } from '$lib/types/table';

// ── Read endpoints ──────────────────────────────────────────────────────

export async function fetchViews(tableId: string): Promise<ViewConfig[]> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/views`, { headers });
	if (!response.ok) throw new Error(`Failed to fetch views: ${response.statusText}`);
	return response.json();
}

// ── View CRUD — all return TableSchema ─────────────────────────────────

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
	return response.json();
}

export async function updateView(
	tableId: string,
	viewName: string,
	updates: UpdateView
): Promise<TableSchema> {
	const headers = await getAuthHeaders();
	const response = await fetch(
		`${BACKEND_URL}/api/v1/tables/${tableId}/views/${encodeURIComponent(viewName)}`,
		{ method: 'PUT', headers, body: JSON.stringify(updates) }
	);
	if (!response.ok) throw new Error(`Failed to update view: ${response.statusText}`);
	return response.json();
}

export async function deleteView(tableId: string, viewName: string): Promise<TableSchema> {
	const headers = await getAuthHeaders();
	const response = await fetch(
		`${BACKEND_URL}/api/v1/tables/${tableId}/views/${encodeURIComponent(viewName)}`,
		{ method: 'DELETE', headers }
	);
	if (!response.ok) throw new Error(`Failed to delete view: ${response.statusText}`);
	return response.json();
}

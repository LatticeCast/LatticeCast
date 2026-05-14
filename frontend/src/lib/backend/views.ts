// lib/backend/views.ts
//
// v40: view identity is view_id (number). Display name + type live
// inside config. Mutation endpoints return the full TableSchema; FE
// replaces its store from the response.

import { BACKEND_URL } from './config';
import { getAuthHeaders } from './http';
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

// ── Mutations — return TableSchema ─────────────────────────────────────

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
	return response.json();
}

export async function deleteView(tableId: string, viewId: number): Promise<TableSchema> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/views/${viewId}`, {
		method: 'DELETE',
		headers
	});
	if (!response.ok) throw new Error(`Failed to delete view: ${response.statusText}`);
	return response.json();
}

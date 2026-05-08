// lib/backend/views.ts
// API client for table views — one view, one JSON.
// Plus view-order CRUD: a single PUT replaces the whole order array.

import { BACKEND_URL } from './config';
import { getAuthHeaders } from './http';
import type { UpdateView, ViewConfig } from '$lib/types/table';

export async function fetchViews(tableId: string): Promise<ViewConfig[]> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/views`, { headers });
	if (!response.ok) throw new Error(`Failed to fetch views: ${response.statusText}`);
	return response.json();
}

export async function createView(
	tableId: string,
	data: { name: string; type: string; config?: Record<string, unknown> }
): Promise<ViewConfig> {
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
): Promise<ViewConfig> {
	const headers = await getAuthHeaders();
	const response = await fetch(
		`${BACKEND_URL}/api/v1/tables/${tableId}/views/${encodeURIComponent(viewName)}`,
		{ method: 'PUT', headers, body: JSON.stringify(updates) }
	);
	if (!response.ok) throw new Error(`Failed to update view: ${response.statusText}`);
	return response.json();
}

export async function deleteView(tableId: string, viewName: string): Promise<void> {
	const headers = await getAuthHeaders();
	const response = await fetch(
		`${BACKEND_URL}/api/v1/tables/${tableId}/views/${encodeURIComponent(viewName)}`,
		{ method: 'DELETE', headers }
	);
	if (!response.ok) throw new Error(`Failed to delete view: ${response.statusText}`);
}

export async function fetchViewOrder(tableId: string): Promise<string[]> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/view-order`, { headers });
	if (!response.ok) throw new Error(`Failed to fetch view order: ${response.statusText}`);
	return response.json();
}

export async function putViewOrder(tableId: string, order: string[]): Promise<string[]> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/view-order`, {
		method: 'PUT',
		headers,
		body: JSON.stringify({ order })
	});
	if (!response.ok) throw new Error(`Failed to update view order: ${response.statusText}`);
	return response.json();
}

/** Mark `viewName` as the table's default (V37 is_default flag). Refuses
 * the internal __schema__ / __order__ rows server-side. */
export async function putDefaultView(tableId: string, viewName: string): Promise<string | null> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/tables/${tableId}/default-view`, {
		method: 'PUT',
		headers,
		body: JSON.stringify({ name: viewName })
	});
	if (!response.ok) throw new Error(`Failed to set default view: ${response.statusText}`);
	const data = await response.json();
	return (data?.default_view as string | null) ?? null;
}

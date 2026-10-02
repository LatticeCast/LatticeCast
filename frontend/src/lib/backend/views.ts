// lib/backend/views.ts
//
// Controller: view CRUD → API call + applySchema to stores.

import { authenticatedRequestJson } from './client';
import { applySchema } from '$lib/stores/table_schema.store';
import type { TableSchema, UpdateView, ViewConfig } from '$lib/types/table';

// ── Reads ──────────────────────────────────────────────────────────────

export async function fetchViews(tableId: string): Promise<ViewConfig[]> {
	return authenticatedRequestJson<ViewConfig[]>(`/tables/${tableId}/views`);
}

export async function fetchView(tableId: string, viewId: number): Promise<ViewConfig> {
	return authenticatedRequestJson<ViewConfig>(`/tables/${tableId}/views/${viewId}`);
}

// ── Mutations — call API + applySchema ────────────────────────────────

export async function createView(
	tableId: string,
	data: { name: string; type: string; config?: Record<string, unknown> }
): Promise<TableSchema> {
	const schema = await authenticatedRequestJson<TableSchema>(`/tables/${tableId}/views`, {
		method: 'POST',
		body: data
	});
	applySchema(schema);
	return schema;
}

export async function updateView(
	tableId: string,
	viewId: number,
	updates: UpdateView
): Promise<TableSchema> {
	const schema = await authenticatedRequestJson<TableSchema>(`/tables/${tableId}/views/${viewId}`, {
		method: 'PUT',
		body: updates
	});
	applySchema(schema);
	return schema;
}

export async function deleteView(tableId: string, viewId: number): Promise<TableSchema> {
	const schema = await authenticatedRequestJson<TableSchema>(`/tables/${tableId}/views/${viewId}`, {
		method: 'DELETE'
	});
	applySchema(schema);
	return schema;
}

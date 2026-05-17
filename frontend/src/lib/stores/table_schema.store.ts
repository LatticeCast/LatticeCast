// src/lib/stores/table_schema.store.ts
//
// Model: pure SSOT for table schema (columns + view_order + default_view).
// No logic — just reactive state. Controllers write here after BE calls.

import { writable } from 'svelte/store';
import type { Column, TableSchema } from '$lib/types/table';
import { views } from './table_views.store';

export const columns = writable<Column[]>([]);
export const viewOrder = writable<number[]>([]);
export const defaultView = writable<number | null>(null);

export function applySchema(schema: TableSchema): void {
	columns.set(schema.columns);
	viewOrder.set(schema.view_order);
	defaultView.set(schema.default_view);
	views.set(schema.views);
}

export function resetSchema(): void {
	columns.set([]);
	viewOrder.set([]);
	defaultView.set(null);
}

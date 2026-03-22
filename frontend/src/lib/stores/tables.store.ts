// src/lib/stores/tables.store.ts

import { writable } from 'svelte/store';
import type { Table, Column, Row } from '$lib/types/table';
import { fetchTables, fetchColumns, fetchRows } from '$lib/backend/tables';

export const tables = writable<Table[]>([]);
export const currentTable = writable<Table | null>(null);
export const columns = writable<Column[]>([]);
export const rows = writable<Row[]>([]);
export const loading = writable(false);
export const error = writable<string | null>(null);

export async function loadTables(): Promise<void> {
	loading.set(true);
	error.set(null);
	try {
		const result = await fetchTables();
		tables.set(result);
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Failed to load tables');
	} finally {
		loading.set(false);
	}
}

export async function loadTable(table: Table): Promise<void> {
	currentTable.set(table);
	loading.set(true);
	error.set(null);
	try {
		const [cols, rws] = await Promise.all([fetchColumns(table.id), fetchRows(table.id)]);
		columns.set(cols);
		rows.set(rws);
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Failed to load table data');
	} finally {
		loading.set(false);
	}
}

export async function refreshColumns(tableId: string): Promise<void> {
	try {
		const result = await fetchColumns(tableId);
		columns.set(result);
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Failed to refresh columns');
	}
}

export async function refreshRows(tableId: string): Promise<void> {
	try {
		const result = await fetchRows(tableId);
		rows.set(result);
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Failed to refresh rows');
	}
}

// src/lib/stores/table_rows.store.ts
//
// Model: pure SSOT for table row data.
// Controllers write here after BE calls.

import { writable } from 'svelte/store';
import type { Row } from '$lib/types/table';

export const rows = writable<Row[]>([]);

export function resetRows(): void {
	rows.set([]);
}

// src/lib/stores/tables.store.ts
//
// Page-level UI state shared by the table route and its components.
// Server data lives in table_schemas.store / table_rows.store and is written
// only by lib/backend controllers.

import { writable } from 'svelte/store';
import type { ViewConfig } from '$lib/types/table';

export const error = writable<string | null>(null);

export const IMPLICIT_TABLE_VIEW: ViewConfig = {
	view_id: 0,
	name: 'Schema',
	type: 'table',
	config: {}
};

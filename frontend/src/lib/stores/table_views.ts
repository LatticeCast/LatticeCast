// src/lib/stores/table_views.ts
//
// Model: pure SSOT for table views.
// Written by applySchema() in table_schema.ts after BE responds.

import { writable } from 'svelte/store';
import type { ViewConfig } from '$lib/types/table';

export const views = writable<ViewConfig[]>([]);

export function resetViews(): void {
	views.set([]);
}

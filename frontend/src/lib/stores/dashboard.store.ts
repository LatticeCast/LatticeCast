// Shared dashboard-query cache. The backend controller is the only writer;
// dashboard blocks render a derived view of these authoritative responses.

import { writable } from 'svelte/store';
import type { BlockRow } from '$lib/types/dashboard';

export type DashboardBlockStatus = 'idle' | 'loading' | 'loaded' | 'error';

export interface DashboardBlockCacheEntry {
	rows: BlockRow[];
	status: DashboardBlockStatus;
	error: string | null;
}

export const dashboardBlocks = writable<Record<string, DashboardBlockCacheEntry>>({});

export function dashboardBlockKey(tableId: string, viewName: string, blockId: string): string {
	return JSON.stringify([tableId, viewName, blockId]);
}

export function setDashboardBlockLoading(key: string): void {
	dashboardBlocks.update((entries) => ({
		...entries,
		[key]: { rows: entries[key]?.rows ?? [], status: 'loading', error: null }
	}));
}

export function setDashboardBlockRows(key: string, rows: BlockRow[]): void {
	dashboardBlocks.update((entries) => ({
		...entries,
		[key]: { rows, status: 'loaded', error: null }
	}));
}

export function setDashboardBlockError(key: string, error: string): void {
	dashboardBlocks.update((entries) => ({
		...entries,
		[key]: { rows: entries[key]?.rows ?? [], status: 'error', error }
	}));
}

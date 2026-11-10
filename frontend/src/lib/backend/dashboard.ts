// Controller: dashboard block query → backend response → shared cache.

import { authenticatedRequestJson } from './client';
import {
	dashboardBlockKey,
	setDashboardBlockError,
	setDashboardBlockLoading,
	setDashboardBlockRows
} from '$lib/stores/dashboard.store';
import type { BlockRow } from '$lib/types/dashboard';

const latestRequestByBlock = new Map<string, number>();
let nextRequestId = 0;

export async function fetchDashboardBlockRows(
	tableId: number,
	workspaceId: string,
	viewName: string,
	blockId: string,
	lql: string
): Promise<BlockRow[]> {
	const key = dashboardBlockKey(tableId, viewName, blockId);
	const requestId = ++nextRequestId;
	latestRequestByBlock.set(key, requestId);
	setDashboardBlockLoading(key);
	try {
		const payload = await authenticatedRequestJson<{ rows: BlockRow[] }>(
			`/workspaces/${encodeURIComponent(workspaceId)}/lql`,
			{ method: 'POST', body: { lql } }
		);
		if (latestRequestByBlock.get(key) === requestId) setDashboardBlockRows(key, payload.rows);
		return payload.rows;
	} catch (error) {
		const message = error instanceof Error ? error.message : 'Failed to load dashboard block';
		if (latestRequestByBlock.get(key) === requestId) setDashboardBlockError(key, message);
		throw error;
	}
}

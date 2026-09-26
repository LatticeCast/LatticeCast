import { authenticatedLatticeCast } from '$lib/backend/client';
import type { BlockRow } from '$lib/types/dashboard';

export async function fetchBlockRows(
	tableId: string,
	viewName: string,
	blockId: string,
	runtimeParams?: Record<string, unknown>
): Promise<BlockRow[]> {
	const j = await authenticatedLatticeCast.requestJson<{ rows: BlockRow[] }>(
		`/tables/${tableId}/views/${encodeURIComponent(viewName)}/blocks/${blockId}/query`,
		{ method: 'POST', body: { params: runtimeParams ?? {} } }
	);
	return j.rows;
}

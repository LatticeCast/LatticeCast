import { get } from 'svelte/store';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { rows } from '$lib/stores/table_rows.store';
import type { Row, RowQueryResponse } from '$lib/types/table';
import { authenticatedRequestJson } from './client';
import { fetchAllRows, fetchRows, queryAllRows } from './tables';

vi.mock('./client', () => ({ authenticatedRequestJson: vi.fn() }));

const request = vi.mocked(authenticatedRequestJson);
const row = (id: number) => ({ table_id: 7, row_id: id, row_data: {} }) as Row;
const response = (
	items: Row[],
	page: number | null = null,
	pageSize: number | null = null
): RowQueryResponse => ({
	items,
	page,
	page_size: pageSize,
	has_more: false,
	total: null,
	total_pages: null
});

describe('table row loading', () => {
	afterEach(() => {
		rows.set([]);
		vi.resetAllMocks();
	});

	it('publishes all rows from the new query envelope in one request', async () => {
		const allRows = Array.from({ length: 101 }, (_, index) => row(101 - index));
		let finishRequest!: (value: RowQueryResponse) => void;
		request.mockImplementationOnce(
			() => new Promise<RowQueryResponse>((resolve) => (finishRequest = resolve))
		);
		rows.set([row(999)]);

		const loading = fetchAllRows(7);
		expect(request).toHaveBeenCalledWith('/rows?table_ids=%5B7%5D');
		expect(get(rows).map((item) => item.row_id)).toEqual([999]);

		finishRequest(response(allRows));
		expect(await loading).toEqual(allRows);
		expect(get(rows)).toEqual(allRows);
		expect(request).toHaveBeenCalledTimes(1);
	});

	it('loads an explicit page through the new query endpoint', async () => {
		request.mockResolvedValueOnce(response([row(42)], 2, 2));
		expect(await fetchRows(7, 2, 2)).toEqual(response([row(42)], 2, 2));
		expect(request).toHaveBeenCalledWith('/rows?table_ids=%5B7%5D&page=2&page_size=2');
		expect(get(rows)).toEqual([row(42)]);
	});

	it('does not replace the visible page when querying all rows for export', async () => {
		rows.set([row(99)]);
		request.mockResolvedValueOnce(response([row(2), row(1)]));
		expect(await queryAllRows(7)).toEqual([row(2), row(1)]);
		expect(get(rows)).toEqual([row(99)]);
	});
});

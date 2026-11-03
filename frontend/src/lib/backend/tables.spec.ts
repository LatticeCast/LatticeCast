import { get } from 'svelte/store';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { rows } from '$lib/stores/table_rows.store';
import type { Row } from '$lib/types/table';
import { authenticatedRequestJson } from './client';
import { fetchAllRows, fetchRows } from './tables';

vi.mock('./client', () => ({ authenticatedRequestJson: vi.fn() }));

const request = vi.mocked(authenticatedRequestJson);
const row = (id: number) => ({ table_id: 7, row_id: id, row_data: {} }) as Row;

describe('table row loading', () => {
	afterEach(() => {
		rows.set([]);
		vi.resetAllMocks();
	});

	it('publishes all 101 rows only after the final ordered page arrives', async () => {
		const firstPage = Array.from({ length: 100 }, (_, index) => row(index + 1));
		let finishSecondPage!: (value: Row[]) => void;
		request
			.mockResolvedValueOnce(firstPage)
			.mockImplementationOnce(() => new Promise<Row[]>((resolve) => (finishSecondPage = resolve)));
		rows.set([row(999)]);

		const loading = fetchAllRows(7);
		await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(2));
		expect(get(rows).map((item) => item.row_id)).toEqual([999]);
		expect(request.mock.calls.map(([url]) => url)).toEqual([
			'/tables/7/rows?offset=0&limit=100&sort=asc',
			'/tables/7/rows?offset=100&limit=100&sort=asc'
		]);

		finishSecondPage([row(101)]);
		const result = await loading;
		expect(result).toHaveLength(101);
		expect(result.at(0)?.row_id).toBe(101);
		expect(result.at(-1)?.row_id).toBe(1);
		expect(get(rows)).toEqual(result);
	});

	it('keeps explicit bounded page requests available', async () => {
		request.mockResolvedValueOnce([row(42)]);
		expect(await fetchRows(7, 40, 2)).toEqual([row(42)]);
		expect(request).toHaveBeenCalledWith('/tables/7/rows?offset=40&limit=2');
	});
});

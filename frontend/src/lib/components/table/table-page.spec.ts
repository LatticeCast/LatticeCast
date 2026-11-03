import { get } from 'svelte/store';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { currentTableId, tables } from '$lib/stores/table_schemas.store';
import type { Table, TableSchema, ViewConfig } from '$lib/types/table';
import { updateView } from '$lib/backend/views';
import { s } from './table-page.svelte';

vi.mock('$lib/backend/views', () => ({
	createView: vi.fn(),
	updateView: vi.fn(),
	deleteView: vi.fn()
}));

const mockedUpdateView = vi.mocked(updateView);

function tableWithView(): Table {
	return {
		table_id: 7,
		table_name: 'test',
		workspace_id: '00000000-0000-0000-0000-000000000007',
		columns: [],
		view_order: [1],
		default_view: 1,
		views: [{ view_id: 1, name: 'Grid', type: 'table', config: {} }],
		view_config: {},
		created_at: '',
		updated_at: ''
	};
}

describe('table view config writes', () => {
	afterEach(() => {
		s.reset();
		tables.set([]);
		currentTableId.set(null);
		vi.clearAllMocks();
	});

	it('merges a column reorder after an in-flight sort write', async () => {
		currentTableId.set(7);
		tables.set([tableWithView()]);
		s.activeViewId = 1;

		let releaseSort!: () => void;
		const sent: Record<string, unknown>[] = [];
		mockedUpdateView.mockImplementation(async (tableId, viewId, updates) => {
			const config = updates.config ?? {};
			sent.push(config);
			if (sent.length === 1) await new Promise<void>((resolve) => (releaseSort = resolve));
			const view: ViewConfig = { view_id: viewId, name: 'Grid', type: 'table', config };
			const schema: TableSchema = {
				columns: [],
				view_order: [viewId],
				default_view: viewId,
				views: [view],
				view_config: {}
			};
			tables.update((all) =>
				all.map((table) => (table.table_id === tableId ? { ...table, views: [view] } : table))
			);
			return schema;
		});

		const sort = s.changeSort({ colId: 'title', dir: 'asc' });
		const reorder = s.persistColumnOrder(['title', 'status']);
		await vi.waitFor(() => expect(sent).toHaveLength(1));
		expect(sent[0]).toMatchObject({ sort: { colId: 'title', dir: 'asc' } });
		releaseSort();
		await Promise.all([sort, reorder]);

		expect(sent).toHaveLength(2);
		expect(sent[1]).toMatchObject({
			sort: { colId: 'title', dir: 'asc' },
			colOrder: ['title', 'status']
		});
		expect(get(tables)[0].views?.[0].config).toEqual(sent[1]);
	});

	it('saves a debounced group change to the view where it was made', async () => {
		const table = tableWithView();
		table.views?.push({ view_id: 2, name: 'Other', type: 'table', config: {} });
		currentTableId.set(7);
		tables.set([table]);
		s.activeViewId = 1;
		mockedUpdateView.mockResolvedValue({
			columns: [],
			view_order: [1, 2],
			default_view: 2,
			views: table.views ?? [],
			view_config: {}
		});

		s.groupConfig = { colId: 'status' };
		s.activeViewId = 2;
		await vi.waitFor(() => expect(mockedUpdateView).toHaveBeenCalledTimes(1));

		expect(mockedUpdateView).toHaveBeenCalledWith(7, 1, {
			config: expect.objectContaining({ group: { colId: 'status' } })
		});
	});
});

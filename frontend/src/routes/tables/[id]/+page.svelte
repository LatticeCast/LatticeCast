<!-- routes/tables/[id]/+page.svelte -->

<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { authStore } from '$lib/stores/auth.store';
	import {
		currentTable,
		columns,
		rows,
		loading,
		error,
		loadTable,
		refreshRows,
		refreshColumns
	} from '$lib/stores/tables.store';
	import {
		fetchTables,
		createRow,
		createColumn,
		deleteColumn,
		updateColumn,
		updateRow,
		deleteRow
	} from '$lib/backend/tables';
	import type { Column, ColumnChoice, Row } from '$lib/types/table';
	import { TAG_COLORS } from '$lib/UI/theme.svelte';
	import { SvelteSet } from 'svelte/reactivity';

	const COLUMN_TYPES = [
		'text',
		'string',
		'number',
		'date',
		'select',
		'tags',
		'checkbox',
		'url'
	] as const;

	let addingRow = $state(false);
	let deletingRowId = $state<string | null>(null);

	// Add-column modal
	let showAddColumn = $state(false);
	let newColName = $state('');
	let newColType = $state<string>('text');
	let addingColumn = $state(false);

	// Inline rename
	let renamingColId = $state<string | null>(null);
	let renameValue = $state('');

	// Inline cell editing
	let editingCell = $state<{ rowId: string; colId: string } | null>(null);
	let editValue = $state<string>('');

	// Tags popup
	let tagsPopupCell = $state<{ rowId: string; colId: string } | null>(null);

	// Column header dropdown menu
	let colMenuId = $state<string | null>(null);

	// Client-side sort (Phase 8 will add toolbar sort; this is the column menu sort)
	let sortConfig = $state<{ colId: string; dir: 'asc' | 'desc' } | null>(null);

	// Multi-condition filter (Phase 8)
	interface FilterCondition {
		id: string;
		colId: string;
		operator: 'contains' | 'equals' | 'is_empty' | 'not_empty';
		value: string;
	}
	let filterConditions = $state<FilterCondition[]>([]);
	let showFilterPanel = $state(false);

	function addFilterCondition() {
		const firstCol = $columns[0];
		filterConditions = [
			...filterConditions,
			{ id: crypto.randomUUID(), colId: firstCol?.id ?? '', operator: 'contains', value: '' }
		];
	}

	function removeFilterCondition(id: string) {
		filterConditions = filterConditions.filter((c) => c.id !== id);
	}

	function clearAllFilters() {
		filterConditions = [];
	}

	// Hidden columns (local state)
	let hiddenCols = new SvelteSet<string>();

	function toggleHideCol(colId: string) {
		if (hiddenCols.has(colId)) hiddenCols.delete(colId);
		else hiddenCols.add(colId);
	}

	// Toolbar state (Phase 8 Ticket 1)
	let searchQuery = $state('');
	let showSortMenu = $state(false);
	let showGroupMenu = $state(false);
	let showHideMenu = $state(false);
	let groupConfig = $state<{ colId: string; granularity?: 'month' | 'day' } | null>(null);
	let collapsedGroups = new SvelteSet<string>();

	// Column resize
	let resizingColId = $state<string | null>(null);
	let resizeStartX = $state(0);
	let resizeStartWidth = $state(0);
	let localWidths = $state<Record<string, number>>({});

	function getColWidth(col: Column): number {
		return localWidths[col.id] ?? col.options?.width ?? 150;
	}

	function handleResizeStart(e: MouseEvent, col: Column) {
		e.preventDefault();
		e.stopPropagation();
		resizingColId = col.id;
		resizeStartX = e.clientX;
		resizeStartWidth = getColWidth(col);
	}

	onMount(() => {
		// Async table loading
		(async () => {
			if (!$authStore?.role) {
				goto('/login');
				return;
			}
			const tableId = $page.params.id;
			try {
				const all = await fetchTables();
				const table = all.find((t) => t.id === tableId);
				if (!table) {
					goto('/tables');
					return;
				}
				await loadTable(table);
			} catch (e) {
				error.set(e instanceof Error ? e.message : 'Failed to load table');
			}
		})();

		// Resize event handlers
		function onResizeMove(e: MouseEvent) {
			if (!resizingColId) return;
			const delta = e.clientX - resizeStartX;
			localWidths = { ...localWidths, [resizingColId]: Math.max(60, resizeStartWidth + delta) };
		}

		async function onResizeUp() {
			if (!resizingColId) return;
			const colId = resizingColId;
			const newWidth = localWidths[colId] ?? resizeStartWidth;
			resizingColId = null;
			const col = get(columns).find((c) => c.id === colId);
			if (!col) return;
			try {
				await updateColumn(colId, { options: { ...col.options, width: newWidth } });
				await refreshColumns(get(page).params.id);
			} catch (err) {
				error.set(err instanceof Error ? err.message : 'Failed to resize column');
			}
		}

		function onWindowClick() {
			colMenuId = null;
			showSortMenu = false;
			showGroupMenu = false;
			showHideMenu = false;
		}

		window.addEventListener('mousemove', onResizeMove);
		window.addEventListener('mouseup', onResizeUp);
		window.addEventListener('click', onWindowClick);

		return () => {
			window.removeEventListener('mousemove', onResizeMove);
			window.removeEventListener('mouseup', onResizeUp);
			window.removeEventListener('click', onWindowClick);
		};
	});

	async function handleAddRow() {
		const tableId = $page.params.id;
		addingRow = true;
		error.set(null);
		try {
			await createRow(tableId, { data: {} });
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to add row');
		} finally {
			addingRow = false;
		}
	}

	async function handleAddRowInGroup(groupKey: string, col: Column) {
		const tableId = $page.params.id;
		addingRow = true;
		error.set(null);
		try {
			const val: unknown = groupKey === '(empty)' ? null : groupKey;
			await createRow(tableId, { data: { [col.id]: val } });
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to add row');
		} finally {
			addingRow = false;
		}
	}

	async function handleDeleteRow(rowId: string) {
		const tableId = $page.params.id;
		deletingRowId = rowId;
		error.set(null);
		try {
			await deleteRow(rowId);
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to delete row');
		} finally {
			deletingRowId = null;
		}
	}

	async function handleAddColumn() {
		if (!newColName.trim()) return;
		const tableId = $page.params.id;
		addingColumn = true;
		error.set(null);
		try {
			await createColumn(tableId, { name: newColName.trim(), type: newColType });
			await refreshColumns(tableId);
			showAddColumn = false;
			newColName = '';
			newColType = 'text';
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to add column');
		} finally {
			addingColumn = false;
		}
	}

	async function handleDeleteColumn(colId: string) {
		const tableId = $page.params.id;
		error.set(null);
		try {
			await deleteColumn(colId);
			await refreshColumns(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to delete column');
		}
	}

	async function handleMoveColumn(col: Column, direction: 'up' | 'down') {
		const tableId = $page.params.id;
		const sorted = [...$columns].sort((a, b) => a.position - b.position);
		const idx = sorted.findIndex((c) => c.id === col.id);
		const swapIdx = direction === 'up' ? idx - 1 : idx + 1;
		if (swapIdx < 0 || swapIdx >= sorted.length) return;
		const swapCol = sorted[swapIdx];
		error.set(null);
		try {
			await Promise.all([
				updateColumn(col.id, { position: swapCol.position }),
				updateColumn(swapCol.id, { position: col.position })
			]);
			await refreshColumns(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to reorder column');
		}
	}

	function startRename(colId: string, currentName: string) {
		renamingColId = colId;
		renameValue = currentName;
	}

	async function commitRename(colId: string) {
		if (!renameValue.trim()) {
			renamingColId = null;
			return;
		}
		const tableId = $page.params.id;
		error.set(null);
		try {
			await updateColumn(colId, { name: renameValue.trim() });
			await refreshColumns(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to rename column');
		} finally {
			renamingColId = null;
		}
	}

	function getCellValue(row: { data: Record<string, unknown> }, colId: string): string {
		const val = row.data[colId];
		if (val === null || val === undefined) return '';
		if (typeof val === 'boolean') return val ? '✓' : '';
		return String(val);
	}

	function startEdit(rowId: string, col: Column, currentVal: unknown) {
		editingCell = { rowId, colId: col.id };
		if (col.type === 'checkbox') {
			editValue = String(!!currentVal);
		} else {
			editValue = currentVal === null || currentVal === undefined ? '' : String(currentVal);
		}
	}

	async function commitEdit(rowId: string, col: Column) {
		if (!editingCell) return;
		editingCell = null;

		const row = $rows.find((r) => r.id === rowId);
		if (!row) return;

		let parsed: unknown = editValue;
		if (col.type === 'number') {
			parsed = editValue === '' ? null : Number(editValue);
		} else if (col.type === 'checkbox') {
			parsed = editValue === 'true';
		} else if (editValue === '') {
			parsed = null;
		}

		const newData = { ...row.data, [col.id]: parsed };
		error.set(null);
		try {
			await updateRow(rowId, { data: newData });
			await refreshRows($page.params.id);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update cell');
		}
	}

	async function toggleCheckbox(rowId: string, col: Column) {
		const row = $rows.find((r) => r.id === rowId);
		if (!row) return;
		const current = !!row.data[col.id];
		const newData = { ...row.data, [col.id]: !current };
		error.set(null);
		try {
			await updateRow(rowId, { data: newData });
			await refreshRows($page.params.id);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update cell');
		}
	}

	function getChoices(col: Column): ColumnChoice[] {
		const choices = col.options?.choices;
		if (!Array.isArray(choices)) return [];
		return choices as ColumnChoice[];
	}

	function getChoiceColor(col: Column, value: string): (typeof TAG_COLORS)[number] {
		const choices = getChoices(col);
		const idx = choices.findIndex((c) => c.value === value);
		return TAG_COLORS[idx >= 0 ? idx % TAG_COLORS.length : 0];
	}

	/**
	 * Format a stored date value to YYYY-MM-DD or YYYY-MM-DD HH:mm:ss.
	 * Handles ISO strings, YYYYMMDD, and YYYYMMDDHHMMSS compact formats.
	 */
	function formatDate(raw: string): string {
		if (!raw) return '';
		// Already in YYYY-MM-DD or YYYY-MM-DD HH:mm:ss
		if (/^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?/.test(raw)) {
			// Normalize ISO T-separator and strip sub-seconds / timezone
			const normalized = raw.replace('T', ' ').replace(/(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$/, '');
			// Return YYYY-MM-DD if no time part, else YYYY-MM-DD HH:mm:ss
			return normalized.length > 10 ? normalized.slice(0, 19) : normalized.slice(0, 10);
		}
		// Compact YYYYMMDDHHMMSS (14 digits)
		if (/^\d{14}$/.test(raw)) {
			return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)} ${raw.slice(8, 10)}:${raw.slice(10, 12)}:${raw.slice(12, 14)}`;
		}
		// Compact YYMMDD (6 digits)
		if (/^\d{6}$/.test(raw)) {
			return `20${raw.slice(0, 2)}-${raw.slice(2, 4)}-${raw.slice(4, 6)}`;
		}
		// Compact YYYYMMDD (8 digits)
		if (/^\d{8}$/.test(raw)) {
			return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
		}
		return raw;
	}

	function getTagValues(row: { data: Record<string, unknown> }, colId: string): string[] {
		const val = row.data[colId];
		return Array.isArray(val) ? (val as string[]) : [];
	}

	async function removeTag(rowId: string, col: Column, tag: string) {
		const row = $rows.find((r) => r.id === rowId);
		if (!row) return;
		const current = getTagValues(row, col.id);
		const newData = { ...row.data, [col.id]: current.filter((t) => t !== tag) };
		try {
			await updateRow(rowId, { data: newData });
			await refreshRows($page.params.id);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update tags');
		}
	}

	async function addTag(rowId: string, col: Column, tag: string) {
		const row = $rows.find((r) => r.id === rowId);
		if (!row) return;
		const current = getTagValues(row, col.id);
		if (current.includes(tag)) return;
		const newData = { ...row.data, [col.id]: [...current, tag] };
		tagsPopupCell = null;
		try {
			await updateRow(rowId, { data: newData });
			await refreshRows($page.params.id);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update tags');
		}
	}

	const sortedColumns = $derived(
		[...$columns].sort((a, b) => a.position - b.position).filter((c) => !hiddenCols.has(c.id))
	);

	const sortedRows = $derived(
		(() => {
			let result = $rows;
			// Global search
			if (searchQuery.trim()) {
				const q = searchQuery.trim().toLowerCase();
				result = result.filter((r) =>
					Object.values(r.data).some((v) => {
						if (v === null || v === undefined) return false;
						if (Array.isArray(v)) return v.some((item) => String(item).toLowerCase().includes(q));
						return String(v).toLowerCase().includes(q);
					})
				);
			}
			for (const cond of filterConditions) {
				if (!cond.colId) continue;
				if (cond.operator !== 'is_empty' && cond.operator !== 'not_empty' && !cond.value.trim())
					continue;
				const lv = cond.value.toLowerCase();
				result = result.filter((r) => {
					const cell = r.data[cond.colId];
					const isEmpty =
						cell === null ||
						cell === undefined ||
						(typeof cell === 'string' && cell === '') ||
						(Array.isArray(cell) && cell.length === 0);
					if (cond.operator === 'is_empty') return isEmpty;
					if (cond.operator === 'not_empty') return !isEmpty;
					if (isEmpty) return false;
					if (cond.operator === 'equals') {
						if (Array.isArray(cell)) return cell.some((v) => String(v).toLowerCase() === lv);
						return String(cell).toLowerCase() === lv;
					}
					// contains
					if (Array.isArray(cell)) return cell.some((v) => String(v).toLowerCase().includes(lv));
					return String(cell).toLowerCase().includes(lv);
				});
			}
			if (!sortConfig) return result;
			const { colId, dir } = sortConfig;
			return [...result].sort((a, b) => {
				const av = a.data[colId];
				const bv = b.data[colId];
				const as = av === null || av === undefined ? '' : String(av);
				const bs = bv === null || bv === undefined ? '' : String(bv);
				const cmp = as.localeCompare(bs, undefined, { numeric: true, sensitivity: 'base' });
				return dir === 'asc' ? cmp : -cmp;
			});
		})()
	);

	// Total min-width: row# col (48px) + all column widths + actions col (40px) + add col button (40px)
	const tableMinWidth = $derived(
		48 + sortedColumns.reduce((sum, col) => sum + getColWidth(col), 0) + 40 + 40
	);

	function getGroupKey(row: Row, colId: string, col: Column): string {
		const val = row.data[colId];
		if (val === null || val === undefined || val === '') return '(empty)';
		if (col.type === 'date') {
			const normalized = formatDate(String(val));
			const granularity = groupConfig?.granularity ?? 'month';
			if (granularity === 'month') return normalized.slice(0, 7); // YYYY-MM
			return normalized.slice(0, 10); // YYYY-MM-DD
		}
		return String(val);
	}

	const groupedRows = $derived(
		(() => {
			if (!groupConfig) return null;
			const col = $columns.find((c) => c.id === groupConfig.colId);
			if (!col) return null;
			const keyOrder: string[] = [];
			const keyMap: Record<string, Row[]> = {};
			for (const row of sortedRows) {
				const key = getGroupKey(row, col.id, col);
				if (!keyMap[key]) {
					keyMap[key] = [];
					keyOrder.push(key);
				}
				keyMap[key].push(row);
			}
			return { groups: keyOrder.map((key) => ({ key, rows: keyMap[key] })), col };
		})()
	);

	interface GroupHeaderItem {
		type: 'group-header';
		key: string;
		count: number;
		col: Column;
	}
	interface DataRowItem {
		type: 'row';
		row: Row;
		rowIdx: number;
	}
	interface GroupAddItem {
		type: 'group-add';
		key: string;
		col: Column;
	}
	type RenderItem = GroupHeaderItem | DataRowItem | GroupAddItem;

	function getItemKey(item: RenderItem): string {
		if (item.type === 'row') return 'row-' + item.row.id;
		return item.type + '-' + item.key;
	}

	const renderItems = $derived(
		(() => {
			if (!groupedRows) {
				return sortedRows.map((row, rowIdx): RenderItem => ({ type: 'row', row, rowIdx }));
			}
			const items: RenderItem[] = [];
			for (const group of groupedRows.groups) {
				items.push({
					type: 'group-header',
					key: group.key,
					count: group.rows.length,
					col: groupedRows.col
				});
				if (!collapsedGroups.has(group.key)) {
					group.rows.forEach((row, rowIdx) => {
						items.push({ type: 'row', row, rowIdx });
					});
					items.push({ type: 'group-add', key: group.key, col: groupedRows.col });
				}
			}
			return items;
		})()
	);
</script>

<div
	class="min-h-screen bg-linear-to-br from-blue-600 via-blue-500 to-sky-500 {resizingColId
		? 'cursor-col-resize select-none'
		: ''}"
>
	<!-- Header -->
	<div class="flex items-center gap-4 px-6 py-4">
		<button
			onclick={() => goto('/tables')}
			class="rounded-xl p-2 text-white/70 transition hover:bg-white/10 hover:text-white"
			aria-label="Back to tables"
		>
			<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
			</svg>
		</button>
		<h1 class="text-2xl font-bold text-white">
			{$currentTable?.name ?? 'Loading...'}
		</h1>
		<div class="ml-auto flex gap-2">
			<button
				onclick={() => {
					showAddColumn = true;
				}}
				disabled={$loading}
				class="rounded-2xl bg-white/20 px-5 py-2 font-semibold text-white transition hover:bg-white/30 disabled:opacity-50"
			>
				+ Add Column
			</button>
			<button
				onclick={handleAddRow}
				disabled={addingRow || $loading}
				class="rounded-2xl bg-white px-5 py-2 font-semibold text-blue-600 transition hover:bg-white/90 disabled:opacity-50"
			>
				{addingRow ? 'Adding...' : '+ Add Row'}
			</button>
		</div>
	</div>

	{#if $error}
		<div class="mx-6 mb-4 rounded-xl bg-red-500/20 px-4 py-3 text-red-100">{$error}</div>
	{/if}

	<!-- Toolbar (Phase 8) -->
	<div class="mx-6 mb-2 flex items-center gap-1">
		<!-- Sort -->
		<div class="relative">
			<button
				onclick={(e) => {
					e.stopPropagation();
					showSortMenu = !showSortMenu;
					showGroupMenu = false;
					showHideMenu = false;
				}}
				class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition {sortConfig
					? 'bg-white/20 text-white'
					: 'text-white/70 hover:bg-white/10 hover:text-white'}"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12"
					/>
				</svg>
				Sort
				{#if sortConfig}
					<span
						class="flex h-4 w-4 items-center justify-center rounded-full bg-blue-400 text-xs font-bold text-white"
						>1</span
					>
				{/if}
			</button>
			{#if showSortMenu}
				<div
					class="absolute top-full left-0 z-30 mt-1 min-w-[200px] rounded-xl border border-gray-100 bg-white py-1 shadow-xl"
					onclick={(e) => e.stopPropagation()}
					role="menu"
				>
					<div class="px-3 py-1.5 text-xs font-semibold tracking-wide text-gray-400 uppercase">
						Sort by
					</div>
					{#each [...$columns].sort((a, b) => a.position - b.position) as col (col.id)}
						<button
							class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50 {sortConfig?.colId ===
							col.id
								? 'font-semibold text-blue-600'
								: ''}"
							onclick={() => {
								if (sortConfig?.colId === col.id) {
									sortConfig = { colId: col.id, dir: sortConfig.dir === 'asc' ? 'desc' : 'asc' };
								} else {
									sortConfig = { colId: col.id, dir: 'asc' };
								}
								showSortMenu = false;
							}}
							role="menuitem"
						>
							{col.name}
							{#if sortConfig?.colId === col.id}
								<span class="ml-auto text-xs text-blue-500"
									>{sortConfig.dir === 'asc' ? '↑ A→Z' : '↓ Z→A'}</span
								>
							{/if}
						</button>
					{/each}
					{#if sortConfig}
						<hr class="my-1 border-gray-100" />
						<button
							class="w-full px-3 py-1.5 text-left text-xs text-red-500 hover:bg-red-50"
							onclick={() => {
								sortConfig = null;
								showSortMenu = false;
							}}
							role="menuitem">Clear sort</button
						>
					{/if}
				</div>
			{/if}
		</div>

		<!-- Group -->
		<div class="relative">
			<button
				onclick={(e) => {
					e.stopPropagation();
					showGroupMenu = !showGroupMenu;
					showSortMenu = false;
					showHideMenu = false;
				}}
				class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition {groupConfig
					? 'bg-white/20 text-white'
					: 'text-white/70 hover:bg-white/10 hover:text-white'}"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M4 6h16M4 10h16M4 14h8M4 18h8"
					/>
				</svg>
				Group
				{#if groupConfig}
					<span
						class="flex h-4 w-4 items-center justify-center rounded-full bg-blue-400 text-xs font-bold text-white"
						>1</span
					>
				{/if}
			</button>
			{#if showGroupMenu}
				<div
					class="absolute top-full left-0 z-30 mt-1 min-w-[200px] rounded-xl border border-gray-100 bg-white py-1 shadow-xl"
					onclick={(e) => e.stopPropagation()}
					role="menu"
				>
					<div class="px-3 py-1.5 text-xs font-semibold tracking-wide text-gray-400 uppercase">
						Group by
					</div>
					{#each [...$columns]
						.sort((a, b) => a.position - b.position)
						.filter((c) => c.type === 'select' || c.type === 'date') as col (col.id)}
						{#if col.type === 'date'}
							<div class="px-3 py-1 text-xs font-medium text-gray-500">
								{col.name} <span class="text-gray-400">(date)</span>
							</div>
							<button
								class="flex w-full items-center gap-2 px-5 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50 {groupConfig?.colId ===
									col.id && groupConfig?.granularity === 'month'
									? 'font-semibold text-blue-600'
									: ''}"
								onclick={() => {
									groupConfig =
										groupConfig?.colId === col.id && groupConfig?.granularity === 'month'
											? null
											: { colId: col.id, granularity: 'month' };
									showGroupMenu = false;
								}}
								role="menuitem"
							>
								by month
								{#if groupConfig?.colId === col.id && groupConfig?.granularity === 'month'}
									<span class="ml-auto text-xs text-blue-500">✓</span>
								{/if}
							</button>
							<button
								class="flex w-full items-center gap-2 px-5 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50 {groupConfig?.colId ===
									col.id && groupConfig?.granularity === 'day'
									? 'font-semibold text-blue-600'
									: ''}"
								onclick={() => {
									groupConfig =
										groupConfig?.colId === col.id && groupConfig?.granularity === 'day'
											? null
											: { colId: col.id, granularity: 'day' };
									showGroupMenu = false;
								}}
								role="menuitem"
							>
								by day
								{#if groupConfig?.colId === col.id && groupConfig?.granularity === 'day'}
									<span class="ml-auto text-xs text-blue-500">✓</span>
								{/if}
							</button>
						{:else}
							<button
								class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50 {groupConfig?.colId ===
								col.id
									? 'font-semibold text-blue-600'
									: ''}"
								onclick={() => {
									groupConfig = groupConfig?.colId === col.id ? null : { colId: col.id };
									showGroupMenu = false;
								}}
								role="menuitem"
							>
								{col.name}
								<span class="ml-1 text-xs text-gray-400">({col.type})</span>
								{#if groupConfig?.colId === col.id}
									<span class="ml-auto text-xs text-blue-500">✓</span>
								{/if}
							</button>
						{/if}
					{:else}
						<div class="px-3 py-2 text-xs text-gray-400">No select or date columns</div>
					{/each}
					{#if groupConfig}
						<hr class="my-1 border-gray-100" />
						<button
							class="w-full px-3 py-1.5 text-left text-xs text-red-500 hover:bg-red-50"
							onclick={() => {
								groupConfig = null;
								showGroupMenu = false;
							}}
							role="menuitem">Clear group</button
						>
					{/if}
				</div>
			{/if}
		</div>

		<!-- Hide Fields -->
		<div class="relative">
			<button
				onclick={(e) => {
					e.stopPropagation();
					showHideMenu = !showHideMenu;
					showSortMenu = false;
					showGroupMenu = false;
				}}
				class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition {hiddenCols.size >
				0
					? 'bg-white/20 text-white'
					: 'text-white/70 hover:bg-white/10 hover:text-white'}"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"
					/>
				</svg>
				Hide Fields
				{#if hiddenCols.size > 0}
					<span
						class="flex h-4 w-4 items-center justify-center rounded-full bg-blue-400 text-xs font-bold text-white"
						>{hiddenCols.size}</span
					>
				{/if}
			</button>
			{#if showHideMenu}
				<div
					class="absolute top-full left-0 z-30 mt-1 min-w-[200px] rounded-xl border border-gray-100 bg-white py-1 shadow-xl"
					onclick={(e) => e.stopPropagation()}
					role="menu"
				>
					<div class="px-3 py-1.5 text-xs font-semibold tracking-wide text-gray-400 uppercase">
						Toggle columns
					</div>
					{#each [...$columns].sort((a, b) => a.position - b.position) as col (col.id)}
						<label class="flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-gray-50">
							<input
								type="checkbox"
								checked={!hiddenCols.has(col.id)}
								onchange={() => toggleHideCol(col.id)}
								class="accent-blue-500"
							/>
							<span class="text-sm text-gray-700">{col.name}</span>
						</label>
					{/each}
					{#if hiddenCols.size > 0}
						<hr class="my-1 border-gray-100" />
						<button
							class="w-full px-3 py-1.5 text-left text-xs text-blue-500 hover:bg-blue-50"
							onclick={() => {
								hiddenCols.clear();
							}}
							role="menuitem">Show all fields</button
						>
					{/if}
				</div>
			{/if}
		</div>

		<!-- Filter -->
		<button
			onclick={() => (showFilterPanel = !showFilterPanel)}
			class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition {filterConditions.length >
			0
				? 'bg-white/20 text-white'
				: 'text-white/70 hover:bg-white/10 hover:text-white'}"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z"
				/>
			</svg>
			Filter
			{#if filterConditions.length > 0}
				<span
					class="flex h-4 w-4 items-center justify-center rounded-full bg-blue-400 text-xs font-bold text-white"
				>
					{filterConditions.length}
				</span>
			{/if}
		</button>

		<!-- Spacer -->
		<div class="flex-1"></div>

		<!-- Search -->
		<div class="relative flex items-center">
			<svg
				class="absolute left-2.5 h-4 w-4 text-white/40"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0"
				/>
			</svg>
			<input
				type="text"
				placeholder="Search..."
				bind:value={searchQuery}
				class="rounded-lg border border-white/20 bg-white/10 py-1.5 pr-3 pl-8 text-sm text-white placeholder-white/40 outline-none focus:border-white/40 focus:bg-white/20 {searchQuery
					? 'w-48'
					: 'w-36'}"
			/>
			{#if searchQuery}
				<button
					onclick={() => (searchQuery = '')}
					class="absolute right-2 text-white/40 hover:text-white/70"
					aria-label="Clear search">×</button
				>
			{/if}
		</div>
	</div>

	<!-- Filter panel -->
	{#if showFilterPanel}
		<div class="mx-6 mb-3 rounded-xl bg-white/10 p-3">
			<div class="mb-2 flex items-center justify-between">
				<span class="text-xs font-semibold tracking-wide text-white/60 uppercase"
					>Filters (AND)</span
				>
				<div class="flex gap-3">
					{#if filterConditions.length > 0}
						<button onclick={clearAllFilters} class="text-xs text-white/50 hover:text-white/80"
							>Clear all</button
						>
					{/if}
					<button
						onclick={() => (showFilterPanel = false)}
						class="text-xs text-white/50 hover:text-white/80"
						aria-label="Close filter panel">✕</button
					>
				</div>
			</div>
			{#each filterConditions as cond (cond.id)}
				<div class="mb-2 flex items-center gap-2">
					<!-- Column picker -->
					<select
						bind:value={cond.colId}
						class="rounded-lg bg-white/20 px-2 py-1 text-sm text-white outline-none focus:ring-1 focus:ring-white/40"
					>
						{#each $columns as col (col.id)}
							<option value={col.id} style="background:#1e40af;">{col.name}</option>
						{/each}
					</select>
					<!-- Operator picker -->
					<select
						bind:value={cond.operator}
						class="rounded-lg bg-white/20 px-2 py-1 text-sm text-white outline-none focus:ring-1 focus:ring-white/40"
					>
						<option value="contains" style="background:#1e40af;">contains</option>
						<option value="equals" style="background:#1e40af;">equals</option>
						<option value="is_empty" style="background:#1e40af;">is empty</option>
						<option value="not_empty" style="background:#1e40af;">is not empty</option>
					</select>
					<!-- Value input (hidden for is_empty/not_empty) -->
					{#if cond.operator !== 'is_empty' && cond.operator !== 'not_empty'}
						<input
							class="min-w-0 flex-1 rounded-lg bg-white/20 px-2 py-1 text-sm text-white placeholder-white/40 outline-none focus:ring-1 focus:ring-white/40"
							bind:value={cond.value}
							placeholder="Value…"
						/>
					{:else}
						<span class="flex-1"></span>
					{/if}
					<!-- Remove condition -->
					<button
						onclick={() => removeFilterCondition(cond.id)}
						class="shrink-0 rounded p-1 text-white/40 hover:text-white/80"
						aria-label="Remove condition"
					>
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M6 18L18 6M6 6l12 12"
							/>
						</svg>
					</button>
				</div>
			{/each}
			<button onclick={addFilterCondition} class="mt-1 text-sm text-white/50 hover:text-white/80"
				>+ Add condition</button
			>
		</div>
	{/if}

	<!-- Spreadsheet -->
	<div class="overflow-x-auto px-6 pb-6">
		{#if $loading}
			<div class="pt-16 text-center text-white/70">Loading...</div>
		{:else if $columns.length === 0}
			<div class="rounded-3xl bg-white/10 p-8 text-center text-white/70">
				No columns defined yet. Click "+ Add Column" to start.
			</div>
		{:else}
			<table
				class="border-collapse text-white"
				style="table-layout: fixed; min-width: {tableMinWidth}px;"
			>
				<thead>
					<tr>
						<!-- Row number header — sticky at left-0 -->
						<th
							class="sticky left-0 z-20 border-r border-b border-white/20 bg-blue-700 px-2 py-3 text-center text-xs font-semibold text-white/60"
							style="width: 48px;"
						>
							#
						</th>
						{#each sortedColumns as col, i (col.id)}
							<th
								class="relative border-b border-white/20 px-4 py-3 text-left text-sm font-semibold tracking-wide text-white/80 uppercase
									{i === 0 ? 'sticky left-12 z-10 border-r border-white/20 bg-blue-600' : 'bg-blue-500/30'}"
								style="width: {getColWidth(col)}px;"
							>
								<div class="flex items-center gap-1">
									{#if renamingColId === col.id}
										<input
											class="min-w-0 flex-1 rounded bg-white/20 px-2 py-0.5 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
											bind:value={renameValue}
											onblur={() => commitRename(col.id)}
											onkeydown={(e) => {
												if (e.key === 'Enter') commitRename(col.id);
												if (e.key === 'Escape') renamingColId = null;
											}}
											autofocus
										/>
									{:else}
										<!-- Column header — click to open dropdown -->
										<button
											onclick={(e) => {
												e.stopPropagation();
												colMenuId = colMenuId === col.id ? null : col.id;
											}}
											class="min-w-0 flex-1 cursor-pointer truncate text-left"
											title="Click for column options"
										>
											{col.name}
											<span class="ml-1 text-xs font-normal text-white/40">({col.type})</span>
										</button>
										<!-- Dropdown chevron indicator -->
										<svg
											class="h-3 w-3 shrink-0 text-white/30 transition {colMenuId === col.id
												? 'rotate-180'
												: ''}"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
											aria-hidden="true"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M19 9l-7 7-7-7"
											/>
										</svg>
									{/if}
								</div>
								<!-- Column dropdown menu -->
								{#if colMenuId === col.id}
									<div
										class="absolute top-full left-0 z-30 mt-1 min-w-[168px] rounded-xl border border-gray-100 bg-white py-1 shadow-xl"
										onclick={(e) => e.stopPropagation()}
										role="menu"
									>
										<button
											class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
											onclick={() => {
												startRename(col.id, col.name);
												colMenuId = null;
											}}
											role="menuitem"
										>
											<svg
												class="h-4 w-4 text-gray-400"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
												/>
											</svg>
											Rename
										</button>
										<button
											class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
											disabled={i === 0}
											onclick={() => {
												handleMoveColumn(col, 'up');
												colMenuId = null;
											}}
											role="menuitem"
										>
											<svg
												class="h-4 w-4 text-gray-400"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M15 19l-7-7 7-7"
												/>
											</svg>
											Move Left
										</button>
										<button
											class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
											disabled={i === sortedColumns.length - 1}
											onclick={() => {
												handleMoveColumn(col, 'down');
												colMenuId = null;
											}}
											role="menuitem"
										>
											<svg
												class="h-4 w-4 text-gray-400"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M9 5l7 7-7 7"
												/>
											</svg>
											Move Right
										</button>
										<hr class="my-1 border-gray-100" />
										<button
											class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 {sortConfig?.colId ===
												col.id && sortConfig?.dir === 'asc'
												? 'font-semibold text-blue-600'
												: ''}"
											onclick={() => {
												sortConfig = { colId: col.id, dir: 'asc' };
												colMenuId = null;
											}}
											role="menuitem"
										>
											<svg
												class="h-4 w-4 text-gray-400"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12"
												/>
											</svg>
											Sort A → Z
										</button>
										<button
											class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 {sortConfig?.colId ===
												col.id && sortConfig?.dir === 'desc'
												? 'font-semibold text-blue-600'
												: ''}"
											onclick={() => {
												sortConfig = { colId: col.id, dir: 'desc' };
												colMenuId = null;
											}}
											role="menuitem"
										>
											<svg
												class="h-4 w-4 text-gray-400"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M3 4h13M3 8h9m-9 4h9m5-4v12m0 0l-4-4m4 4l4-4"
												/>
											</svg>
											Sort Z → A
										</button>
										<button
											class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 {filterConditions.some(
												(c) => c.colId === col.id
											)
												? 'font-semibold text-blue-600'
												: ''}"
											onclick={() => {
												const existing = filterConditions.find((c) => c.colId === col.id);
												if (!existing) {
													filterConditions = [
														...filterConditions,
														{
															id: crypto.randomUUID(),
															colId: col.id,
															operator: 'contains',
															value: ''
														}
													];
												}
												showFilterPanel = true;
												colMenuId = null;
											}}
											role="menuitem"
										>
											<svg
												class="h-4 w-4 text-gray-400"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z"
												/>
											</svg>
											Filter by this column
										</button>
										<hr class="my-1 border-gray-100" />
										<button
											class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-500 hover:bg-gray-50"
											onclick={() => {
												hiddenCols.add(col.id);
												colMenuId = null;
											}}
											role="menuitem"
										>
											<svg
												class="h-4 w-4 text-gray-400"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"
												/>
											</svg>
											Hide
										</button>
										<hr class="my-1 border-gray-100" />
										<button
											class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50"
											onclick={() => {
												handleDeleteColumn(col.id);
												colMenuId = null;
											}}
											role="menuitem"
										>
											<svg
												class="h-4 w-4 text-red-400"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
												/>
											</svg>
											Delete
										</button>
									</div>
								{/if}
								<!-- Resize handle -->
								<div
									class="absolute top-0 right-0 h-full w-1.5 cursor-col-resize hover:bg-white/40 {resizingColId ===
									col.id
										? 'bg-white/40'
										: ''}"
									onmousedown={(e) => handleResizeStart(e, col)}
									role="separator"
									aria-label="Resize column {col.name}"
								></div>
							</th>
						{/each}
						<!-- Actions column header (delete) -->
						<th class="border-b border-white/20 bg-blue-500/30" style="width: 40px;"></th>
						<!-- Add column "+" header -->
						<th class="border-b border-white/20 bg-blue-500/20" style="width: 40px;">
							<button
								onclick={() => {
									showAddColumn = true;
								}}
								class="flex h-full w-full items-center justify-center rounded p-1 text-white/40 hover:bg-white/20 hover:text-white/80"
								title="Add column"
								aria-label="Add column"
							>
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M12 4v16m8-8H4"
									/>
								</svg>
							</button>
						</th>
					</tr>
				</thead>
				<tbody>
					{#each renderItems as item (getItemKey(item))}
						{#if item.type === 'group-header'}
							<tr class="border-b border-white/20">
								<td colspan={sortedColumns.length + 3} class="bg-white/5 py-0.5">
									<div class="flex items-center gap-2 px-3 py-1">
										<button
											onclick={() => {
												if (collapsedGroups.has(item.key)) collapsedGroups.delete(item.key);
												else collapsedGroups.add(item.key);
											}}
											class="rounded p-0.5 text-white/50 hover:text-white/80"
											aria-label={collapsedGroups.has(item.key) ? 'Expand group' : 'Collapse group'}
										>
											<svg
												class="h-4 w-4 transition {collapsedGroups.has(item.key)
													? '-rotate-90'
													: ''}"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M19 9l-7 7-7-7"
												/>
											</svg>
										</button>
										{#if item.col.type === 'select' && item.key !== '(empty)'}
											{@const color = getChoiceColor(item.col, item.key)}
											<span
												class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
											>
												{item.key}
											</span>
										{:else}
											<span class="text-sm font-medium text-white/90">{item.key}</span>
										{/if}
										<span class="text-xs text-white/50"
											>{item.count} {item.count === 1 ? 'row' : 'rows'}</span
										>
									</div>
								</td>
							</tr>
						{:else if item.type === 'group-add'}
							<tr class="border-b border-white/10">
								<td colspan={sortedColumns.length + 3} class="px-4 py-1">
									<button
										onclick={() => handleAddRowInGroup(item.key, item.col)}
										disabled={addingRow}
										class="rounded px-2 py-0.5 text-xs text-white/40 hover:bg-white/10 hover:text-white/70 disabled:opacity-50"
									>
										+ Add row
									</button>
								</td>
							</tr>
						{:else}
							{@const row = item.row}
							{@const rowIdx = item.rowIdx}
							<tr
								class="border-b border-white/10 transition hover:bg-white/5 {deletingRowId ===
								row.id
									? 'opacity-50'
									: ''}"
							>
								<!-- Row number — sticky at left-0 -->
								<td
									class="sticky left-0 z-20 border-r border-white/10 bg-blue-700 px-2 py-1 text-center text-xs text-white/40"
									style="width: 48px;"
								>
									{rowIdx + 1}
								</td>
								{#each sortedColumns as col, i (col.id)}
									<td
										class="overflow-hidden py-1 text-sm text-white/90
										{i === 0 ? 'sticky left-12 z-10 border-r border-white/10 bg-blue-600 px-2' : 'px-2'}"
										style="width: {getColWidth(col)}px;"
										onclick={() => {
											if (
												col.type !== 'checkbox' &&
												col.type !== 'tags' &&
												!(editingCell?.rowId === row.id && editingCell?.colId === col.id)
											) {
												startEdit(row.id, col, row.data[col.id]);
											}
										}}
									>
										{#if editingCell?.rowId === row.id && editingCell?.colId === col.id}
											{#if col.type === 'select'}
												{@const choices = getChoices(col)}
												<select
													class="w-full rounded bg-white/20 px-2 py-1 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
													bind:value={editValue}
													onblur={() => commitEdit(row.id, col)}
													onchange={() => commitEdit(row.id, col)}
													autofocus
												>
													<option value="">—</option>
													{#each choices as choice (choice.value)}
														<option value={choice.value}>{choice.value}</option>
													{/each}
												</select>
											{:else if col.type === 'number'}
												<input
													type="number"
													class="w-full rounded bg-white/20 px-2 py-1 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
													bind:value={editValue}
													onblur={() => commitEdit(row.id, col)}
													onkeydown={(e) => {
														if (e.key === 'Enter') commitEdit(row.id, col);
														if (e.key === 'Escape') editingCell = null;
													}}
													autofocus
												/>
											{:else if col.type === 'date'}
												<input
													type="date"
													class="w-full rounded bg-white/20 px-2 py-1 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
													bind:value={editValue}
													onblur={() => commitEdit(row.id, col)}
													onkeydown={(e) => {
														if (e.key === 'Enter') commitEdit(row.id, col);
														if (e.key === 'Escape') editingCell = null;
													}}
													autofocus
												/>
											{:else}
												<input
													type={col.type === 'url' ? 'url' : 'text'}
													class="w-full rounded bg-white/20 px-2 py-1 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
													bind:value={editValue}
													onblur={() => commitEdit(row.id, col)}
													onkeydown={(e) => {
														if (e.key === 'Enter') commitEdit(row.id, col);
														if (e.key === 'Escape') editingCell = null;
													}}
													autofocus
												/>
											{/if}
										{:else if col.type === 'checkbox'}
											<!-- Styled toggle -->
											<button
												class="relative inline-flex h-5 w-9 items-center rounded-full transition {row
													.data[col.id]
													? 'bg-blue-500'
													: 'bg-white/20'}"
												onclick={(e) => {
													e.stopPropagation();
													toggleCheckbox(row.id, col);
												}}
												aria-label="Toggle"
												role="switch"
												aria-checked={!!row.data[col.id]}
											>
												<span
													class="inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition {row
														.data[col.id]
														? 'translate-x-4'
														: 'translate-x-1'}"
												></span>
											</button>
										{:else if col.type === 'url'}
											{@const urlVal = (row.data[col.id] as string) ?? ''}
											{#if urlVal}
												<a
													href={urlVal}
													target="_blank"
													rel="noopener noreferrer"
													class="block max-w-full truncate text-sky-300 underline hover:text-sky-100"
													onclick={(e) => e.stopPropagation()}
													title={urlVal}>{urlVal}</a
												>
											{:else}
												<span class="block min-h-[1.5rem] cursor-text py-1 text-white/30">—</span>
											{/if}
										{:else if col.type === 'select'}
											{@const selVal = (row.data[col.id] as string) ?? ''}
											{#if selVal}
												{@const color = getChoiceColor(col, selVal)}
												<span
													class="inline-flex cursor-pointer items-center rounded-full border px-2 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
												>
													{selVal}
												</span>
											{:else}
												<span class="block min-h-[1.5rem] cursor-pointer py-1 text-white/30">—</span
												>
											{/if}
										{:else if col.type === 'tags'}
											{@const tagVals = getTagValues(row, col.id)}
											{@const choices = getChoices(col)}
											{@const available = choices.filter((c) => !tagVals.includes(c.value))}
											<div
												class="flex min-h-[1.75rem] flex-wrap items-center gap-1"
												onclick={(e) => e.stopPropagation()}
											>
												{#each tagVals as tag (tag)}
													{@const color = getChoiceColor(col, tag)}
													<span
														class="inline-flex items-center gap-0.5 rounded-full border px-2 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
													>
														{tag}
														<button
															class="ml-0.5 rounded-full leading-none hover:opacity-60"
															onclick={() => removeTag(row.id, col, tag)}
															aria-label="Remove {tag}">×</button
														>
													</span>
												{/each}
												{#if available.length > 0}
													<div class="relative">
														<button
															class="rounded-full border border-white/30 px-2 py-0.5 text-xs text-white/50 hover:border-white/60 hover:text-white/80"
															onclick={() => {
																tagsPopupCell =
																	tagsPopupCell?.rowId === row.id && tagsPopupCell?.colId === col.id
																		? null
																		: { rowId: row.id, colId: col.id };
															}}>+</button
														>
														{#if tagsPopupCell?.rowId === row.id && tagsPopupCell?.colId === col.id}
															<div
																class="absolute top-full left-0 z-20 mt-1 min-w-[120px] rounded-xl border border-gray-100 bg-white py-1 shadow-xl"
															>
																{#each available as choice (choice.value)}
																	{@const color =
																		TAG_COLORS[choices.indexOf(choice) % TAG_COLORS.length]}
																	<button
																		class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-gray-50"
																		onclick={() => addTag(row.id, col, choice.value)}
																	>
																		<span
																			class="inline-flex items-center rounded-full border px-2 py-0.5 font-medium {color.bg} {color.text} {color.border}"
																			>{choice.value}</span
																		>
																	</button>
																{/each}
															</div>
														{/if}
													</div>
												{/if}
											</div>
										{:else if col.type === 'date'}
											{@const dateVal = row.data[col.id]
												? formatDate(String(row.data[col.id]))
												: ''}
											{#if dateVal}
												<span class="block cursor-text py-1 font-mono text-xs text-white/90"
													>{dateVal}</span
												>
											{:else}
												<span class="block min-h-[1.5rem] cursor-text py-1 text-white/30">—</span>
											{/if}
										{:else}
											<!-- text / string / number -->
											<span
												class="block min-h-[1.5rem] cursor-text truncate py-1"
												title="Click to edit"
											>
												{getCellValue(row, col.id)}
											</span>
										{/if}
									</td>
								{/each}
								<!-- Row delete button -->
								<td class="px-1 py-1 text-center" style="width: 40px;">
									<button
										onclick={() => handleDeleteRow(row.id)}
										disabled={deletingRowId === row.id}
										class="rounded p-1 text-white/30 transition hover:bg-red-500/30 hover:text-red-300 disabled:opacity-50"
										aria-label="Delete row"
										title="Delete row"
									>
										<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
											/>
										</svg>
									</button>
								</td>
								<!-- Empty cell for "+" add column header -->
								<td style="width: 40px;"></td>
							</tr>
						{/if}
					{:else}
						<tr>
							<td
								colspan={sortedColumns.length + 3}
								class="px-4 py-8 text-center text-sm text-white/50"
							>
								No rows yet. Click "+ Add Row" to start.
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</div>

<!-- Add Column Modal -->
{#if showAddColumn}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
		onclick={(e) => {
			if (e.target === e.currentTarget) showAddColumn = false;
		}}
		role="dialog"
		aria-modal="true"
		aria-label="Add column"
	>
		<div class="w-full max-w-sm rounded-3xl bg-white p-8 shadow-2xl">
			<h2 class="mb-6 text-xl font-bold text-gray-800">Add Column</h2>
			<div class="mb-4">
				<label class="mb-1 block text-sm font-medium text-gray-600" for="col-name">Name</label>
				<input
					id="col-name"
					class="w-full rounded-xl border border-gray-200 px-4 py-2 text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
					bind:value={newColName}
					placeholder="Column name"
					onkeydown={(e) => {
						if (e.key === 'Enter') handleAddColumn();
					}}
					autofocus
				/>
			</div>
			<div class="mb-6">
				<label class="mb-1 block text-sm font-medium text-gray-600" for="col-type">Type</label>
				<select
					id="col-type"
					class="w-full rounded-xl border border-gray-200 px-4 py-2 text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
					bind:value={newColType}
				>
					{#each COLUMN_TYPES as t (t)}
						<option value={t}>{t}</option>
					{/each}
				</select>
			</div>
			<div class="flex gap-3">
				<button
					onclick={() => {
						showAddColumn = false;
						newColName = '';
						newColType = 'text';
					}}
					class="flex-1 rounded-2xl border border-gray-200 px-4 py-2 font-semibold text-gray-600 transition hover:bg-gray-50"
				>
					Cancel
				</button>
				<button
					onclick={handleAddColumn}
					disabled={addingColumn || !newColName.trim()}
					class="flex-1 rounded-2xl bg-linear-to-r from-blue-600 to-blue-500 px-4 py-2 font-semibold text-white transition hover:shadow-lg disabled:opacity-50"
				>
					{addingColumn ? 'Adding...' : 'Add Column'}
				</button>
			</div>
		</div>
	</div>
{/if}

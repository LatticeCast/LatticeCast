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
	import type { Column, ColumnChoice, ColumnOptions, ColumnType, Row } from '$lib/types/table';
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

	// Row expand panel
	let expandedRow = $state<Row | null>(null);
	let expandEditField = $state<string | null>(null);
	let expandEditVal = $state('');

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
	let showExportMenu = $state(false);

	// Export / Import state
	let showImportModal = $state(false);
	let importPreviewHeaders = $state<string[]>([]);
	let importPreviewRows = $state<Record<string, string>[]>([]);
	let importNewColumns = $state<{ name: string; type: string }[]>([]);
	let importingData = $state(false);
	let importError = $state<string | null>(null);
	let groupConfig = $state<{ colId: string; granularity?: 'month' | 'day' } | null>(null);
	let collapsedGroups = new SvelteSet<string>();

	// Context menu (right-click)
	interface ContextMenuState {
		type: 'row' | 'col';
		id: string;
		x: number;
		y: number;
	}
	let contextMenu = $state<ContextMenuState | null>(null);

	function openContextMenu(e: MouseEvent, type: 'row' | 'col', id: string) {
		e.preventDefault();
		e.stopPropagation();
		colMenuId = null;
		contextMenu = { type, id, x: e.clientX, y: e.clientY };
	}

	async function handleDuplicateRow(rowId: string) {
		const row = $rows.find((r) => r.id === rowId);
		if (!row) return;
		const tableId = $page.params.id;
		error.set(null);
		try {
			await createRow(tableId, { data: { ...row.data } });
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to duplicate row');
		}
		contextMenu = null;
	}

	// Template export / import
	let showImportTemplateModal = $state(false);
	let importTemplateError = $state<string | null>(null);
	let importingTemplate = $state(false);

	function handleExportTemplate() {
		const template = [...$columns]
			.sort((a, b) => a.position - b.position)
			.map((col) => ({
				name: col.name,
				type: col.type,
				options: col.options,
				position: col.position
			}));
		const blob = new Blob([JSON.stringify(template, null, 2)], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `${$currentTable?.name ?? 'table'}-template.json`;
		a.click();
		URL.revokeObjectURL(url);
	}

	async function handleImportTemplate(file: File) {
		importingTemplate = true;
		importTemplateError = null;
		const tableId = $page.params.id;
		try {
			const text = await file.text();
			const template = JSON.parse(text) as Array<{
				name: string;
				type: string;
				options?: ColumnOptions;
				position?: number;
			}>;
			if (!Array.isArray(template)) throw new Error('Invalid template: expected an array');
			await Promise.all([...$columns].map((col) => deleteColumn(col.id)));
			for (const col of template) {
				await createColumn(tableId, {
					name: col.name,
					type: col.type as ColumnType,
					options: col.options ?? {},
					position: col.position ?? 0
				});
			}
			await refreshColumns(tableId);
			showImportTemplateModal = false;
		} catch (e) {
			importTemplateError = e instanceof Error ? e.message : 'Failed to import template';
		} finally {
			importingTemplate = false;
		}
	}

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
			showExportMenu = false;
			contextMenu = null;
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

	function openExpand(row: Row) {
		expandedRow = row;
		expandEditField = null;
		expandEditVal = '';
	}

	function startExpandEdit(col: Column, row: Row) {
		expandEditField = col.id;
		const val = row.data[col.id];
		expandEditVal = val === null || val === undefined ? '' : String(val);
	}

	async function commitExpandEdit(col: Column) {
		if (!expandedRow || expandEditField !== col.id) return;
		expandEditField = null;

		let parsed: unknown = expandEditVal;
		if (col.type === 'number') {
			parsed = expandEditVal === '' ? null : Number(expandEditVal);
		} else if (col.type === 'checkbox') {
			parsed = expandEditVal === 'true';
		} else if (expandEditVal === '') {
			parsed = null;
		}

		const newData = { ...expandedRow.data, [col.id]: parsed };
		error.set(null);
		try {
			await updateRow(expandedRow.id, { data: newData });
			expandedRow = { ...expandedRow, data: newData };
			await refreshRows($page.params.id);
			// Keep expandedRow in sync with latest data
			const latestRow = $rows.find((r) => r.id === expandedRow!.id);
			if (latestRow) expandedRow = latestRow;
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update field');
		}
	}

	async function toggleExpandCheckbox(col: Column) {
		if (!expandedRow) return;
		const current = !!expandedRow.data[col.id];
		const newData = { ...expandedRow.data, [col.id]: !current };
		error.set(null);
		try {
			await updateRow(expandedRow.id, { data: newData });
			expandedRow = { ...expandedRow, data: newData };
			await refreshRows($page.params.id);
			const latestRow = $rows.find((r) => r.id === expandedRow!.id);
			if (latestRow) expandedRow = latestRow;
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update field');
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
	function exportCSV() {
		const cols = [...$columns].sort((a, b) => a.position - b.position);
		const headers = cols.map((c) => c.name);
		const escapeCSV = (v: string) => `"${v.replace(/"/g, '""')}"`;
		const csvRows = [
			headers.map(escapeCSV).join(','),
			...$rows.map((row) =>
				cols
					.map((col) => {
						const val = row.data[col.id];
						if (val === null || val === undefined) return '';
						if (Array.isArray(val)) return escapeCSV(val.join(','));
						return escapeCSV(String(val));
					})
					.join(',')
			)
		];
		const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `${$currentTable?.name ?? 'table'}.csv`;
		a.click();
		URL.revokeObjectURL(url);
	}

	function exportJSON() {
		const cols = [...$columns].sort((a, b) => a.position - b.position);
		const data = $rows.map((row) => {
			const obj: Record<string, unknown> = {};
			for (const col of cols) obj[col.name] = row.data[col.id] ?? null;
			return obj;
		});
		const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `${$currentTable?.name ?? 'table'}-data.json`;
		a.click();
		URL.revokeObjectURL(url);
	}

	function parseCSV(text: string): string[][] {
		const lines = text.split(/\r?\n/).filter((l) => l.trim());
		return lines.map((line) => {
			const fields: string[] = [];
			let i = 0;
			while (i < line.length) {
				if (line[i] === '"') {
					let j = i + 1;
					let field = '';
					while (j < line.length) {
						if (line[j] === '"' && line[j + 1] === '"') {
							field += '"';
							j += 2;
						} else if (line[j] === '"') {
							j++;
							break;
						} else {
							field += line[j++];
						}
					}
					fields.push(field);
					i = j;
					if (line[i] === ',') i++;
				} else {
					const end = line.indexOf(',', i);
					if (end === -1) {
						fields.push(line.slice(i));
						break;
					} else {
						fields.push(line.slice(i, end));
						i = end + 1;
					}
				}
			}
			return fields;
		});
	}

	function handleImportFile(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		const reader = new FileReader();
		reader.onload = (ev) => {
			const text = ev.target?.result as string;
			const parsed = parseCSV(text);
			if (parsed.length < 1) return;
			const headers = parsed[0];
			importPreviewHeaders = headers;
			importPreviewRows = parsed.slice(1).map((cells) => {
				const obj: Record<string, string> = {};
				headers.forEach((h, i) => {
					obj[h] = cells[i] ?? '';
				});
				return obj;
			});
			importNewColumns = [];
			for (const h of headers) {
				const m = h.match(/^(.+)\{\{(\w+)\}\}$/);
				if (m) {
					const colName = m[1].trim();
					const colType = m[2].toLowerCase();
					const exists = $columns.some((c) => c.name === colName);
					if (!exists) {
						importNewColumns = [...importNewColumns, { name: colName, type: colType }];
					}
				}
			}
			importError = null;
			showImportModal = true;
		};
		reader.readAsText(file);
		input.value = '';
	}

	async function commitImport() {
		importingData = true;
		importError = null;
		const tableId = $page.params.id;
		try {
			for (let i = 0; i < importNewColumns.length; i++) {
				const nc = importNewColumns[i];
				await createColumn(tableId, {
					name: nc.name,
					type: nc.type as 'text',
					options: { choices: [] }
				});
			}
			await refreshColumns(tableId);
			const currentCols = get(columns);

			function headerColName(h: string): string {
				const m = h.match(/^(.+)\{\{(\w+)\}\}$/);
				return m ? m[1].trim() : h;
			}

			for (const previewRow of importPreviewRows) {
				const data: Record<string, unknown> = {};
				for (const h of importPreviewHeaders) {
					const colName = headerColName(h);
					const col = currentCols.find((c) => c.name === colName);
					if (!col) continue;
					const rawVal = previewRow[h];
					if (rawVal === '' || rawVal === undefined) continue;
					if (col.type === 'tags') {
						data[col.id] = rawVal
							.split(',')
							.map((v) => v.trim())
							.filter(Boolean);
					} else if (col.type === 'checkbox') {
						data[col.id] = rawVal.toLowerCase() === 'true' || rawVal === '1';
					} else if (col.type === 'number') {
						const n = Number(rawVal);
						data[col.id] = isNaN(n) ? null : n;
					} else {
						data[col.id] = rawVal;
					}
				}
				await createRow(tableId, { data });
			}
			await refreshRows(tableId);
			showImportModal = false;
			importPreviewRows = [];
			importPreviewHeaders = [];
			importNewColumns = [];
		} catch (e) {
			importError = e instanceof Error ? e.message : 'Import failed';
		} finally {
			importingData = false;
		}
	}
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

		<!-- Export Template -->
		<button
			onclick={handleExportTemplate}
			class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-white/70 transition hover:bg-white/10 hover:text-white"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
				/>
			</svg>
			Export Template
		</button>

		<!-- Import Template -->
		<button
			onclick={() => (showImportTemplateModal = true)}
			class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-white/70 transition hover:bg-white/10 hover:text-white"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l4-4m0 0l4 4m-4-4v12"
				/>
			</svg>
			Import Template
		</button>

		<!-- Export Data -->
		<div class="relative">
			<button
				onclick={(e) => {
					e.stopPropagation();
					showExportMenu = !showExportMenu;
					showSortMenu = false;
					showGroupMenu = false;
					showHideMenu = false;
				}}
				class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-white/70 transition hover:bg-white/10 hover:text-white"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
					/>
				</svg>
				Export
			</button>
			{#if showExportMenu}
				<div
					class="absolute top-full left-0 z-30 mt-1 min-w-[150px] rounded-xl border border-gray-100 bg-white py-1 shadow-xl"
					onclick={(e) => e.stopPropagation()}
					role="menu"
				>
					<button
						class="w-full px-3 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50"
						onclick={() => {
							exportCSV();
							showExportMenu = false;
						}}
						role="menuitem">Export CSV</button
					>
					<button
						class="w-full px-3 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50"
						onclick={() => {
							exportJSON();
							showExportMenu = false;
						}}
						role="menuitem">Export JSON</button
					>
				</div>
			{/if}
		</div>

		<!-- Import -->
		<label
			class="flex cursor-pointer items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-white/70 transition hover:bg-white/10 hover:text-white"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l4-4m0 0l4 4m-4-4v12"
				/>
			</svg>
			Import CSV
			<input type="file" accept=".csv" class="hidden" onchange={handleImportFile} />
		</label>

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
								oncontextmenu={(e) => openContextMenu(e, 'col', col.id)}
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
								oncontextmenu={(e) => openContextMenu(e, 'row', row.id)}
							>
								<!-- Row number — sticky at left-0, click to expand -->
								<td
									class="sticky left-0 z-20 border-r border-white/10 bg-blue-700 px-1 py-1 text-center"
									style="width: 48px;"
								>
									<button
										onclick={() => openExpand(row)}
										class="group relative flex h-full w-full items-center justify-center rounded px-1 py-0.5 text-xs text-white/40 hover:bg-white/10 hover:text-white/80"
										title="Expand row"
									>
										{rowIdx + 1}
										<svg
											class="absolute right-0.5 hidden h-3 w-3 group-hover:block"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
											aria-hidden="true"
										>
											<path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
											/>
										</svg>
									</button>
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

<!-- Context Menu (right-click) -->
{#if contextMenu}
	{@const ctxCol =
		contextMenu.type === 'col' ? $columns.find((c) => c.id === contextMenu.id) : null}

	<div
		class="fixed z-50 min-w-[180px] rounded-xl border border-gray-100 bg-white py-1 shadow-2xl"
		style="left: {contextMenu.x}px; top: {contextMenu.y}px;"
		onclick={(e) => e.stopPropagation()}
		role="menu"
	>
		{#if contextMenu.type === 'row'}
			<button
				class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
				onclick={() => {
					const row = $rows.find((r) => r.id === contextMenu!.id);
					if (row) openExpand(row);
					contextMenu = null;
				}}
				role="menuitem"
			>
				<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
					/>
				</svg>
				Expand
			</button>
			<button
				class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
				onclick={() => handleDuplicateRow(contextMenu.id)}
				role="menuitem"
			>
				<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
					/>
				</svg>
				Duplicate
			</button>
			<hr class="my-1 border-gray-100" />
			<button
				class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50"
				onclick={() => {
					handleDeleteRow(contextMenu.id);
					contextMenu = null;
				}}
				role="menuitem"
			>
				<svg class="h-4 w-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
					/>
				</svg>
				Delete
			</button>
		{:else if ctxCol}
			<button
				class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
				onclick={() => {
					startRename(ctxCol.id, ctxCol.name);
					contextMenu = null;
				}}
				role="menuitem"
			>
				<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
					/>
				</svg>
				Rename
			</button>
			<hr class="my-1 border-gray-100" />
			<button
				class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 {sortConfig?.colId ===
					ctxCol.id && sortConfig?.dir === 'asc'
					? 'font-semibold text-blue-600'
					: ''}"
				onclick={() => {
					sortConfig = { colId: ctxCol.id, dir: 'asc' };
					contextMenu = null;
				}}
				role="menuitem"
			>
				<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
					ctxCol.id && sortConfig?.dir === 'desc'
					? 'font-semibold text-blue-600'
					: ''}"
				onclick={() => {
					sortConfig = { colId: ctxCol.id, dir: 'desc' };
					contextMenu = null;
				}}
				role="menuitem"
			>
				<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
					(c) => c.colId === ctxCol.id
				)
					? 'font-semibold text-blue-600'
					: ''}"
				onclick={() => {
					if (!filterConditions.find((c) => c.colId === ctxCol.id)) {
						filterConditions = [
							...filterConditions,
							{ id: crypto.randomUUID(), colId: ctxCol.id, operator: 'contains', value: '' }
						];
					}
					showFilterPanel = true;
					contextMenu = null;
				}}
				role="menuitem"
			>
				<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z"
					/>
				</svg>
				Filter
			</button>
			<hr class="my-1 border-gray-100" />
			<button
				class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-500 hover:bg-gray-50"
				onclick={() => {
					hiddenCols.add(ctxCol.id);
					contextMenu = null;
				}}
				role="menuitem"
			>
				<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
					handleDeleteColumn(ctxCol.id);
					contextMenu = null;
				}}
				role="menuitem"
			>
				<svg class="h-4 w-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
					/>
				</svg>
				Delete
			</button>
		{/if}
	</div>
{/if}

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

<!-- Row Expand Panel -->
{#if expandedRow}
	<!-- Backdrop -->
	<div
		class="fixed inset-0 z-40 bg-black/30"
		onclick={() => {
			expandedRow = null;
			expandEditField = null;
		}}
		role="presentation"
	></div>
	<!-- Slide-out panel -->
	<div
		class="fixed top-0 right-0 z-50 flex h-full w-full max-w-md flex-col bg-white shadow-2xl"
		role="dialog"
		aria-modal="true"
		aria-label="Row details"
	>
		<!-- Panel header -->
		<div
			class="flex items-center justify-between border-b border-gray-100 bg-linear-to-r from-blue-600 to-blue-500 px-6 py-4"
		>
			<h2 class="text-lg font-semibold text-white">Row Details</h2>
			<button
				onclick={() => {
					expandedRow = null;
					expandEditField = null;
				}}
				class="rounded-lg p-1.5 text-white/70 transition hover:bg-white/20 hover:text-white"
				aria-label="Close panel"
			>
				<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M6 18L18 6M6 6l12 12"
					/>
				</svg>
			</button>
		</div>
		<!-- Fields list -->
		<div class="flex-1 overflow-y-auto px-6 py-4">
			{#each [...$columns].sort((a, b) => a.position - b.position) as col (col.id)}
				<div class="mb-5">
					<label class="mb-1 block text-xs font-semibold tracking-wide text-gray-400 uppercase">
						{col.name}
						<span class="ml-1 font-normal text-gray-300 normal-case">({col.type})</span>
					</label>
					{#if col.type === 'checkbox'}
						<button
							class="relative inline-flex h-6 w-10 items-center rounded-full transition {expandedRow
								.data[col.id]
								? 'bg-blue-500'
								: 'bg-gray-200'}"
							onclick={() => toggleExpandCheckbox(col)}
							role="switch"
							aria-checked={!!expandedRow.data[col.id]}
						>
							<span
								class="inline-block h-4 w-4 transform rounded-full bg-white shadow transition {expandedRow
									.data[col.id]
									? 'translate-x-5'
									: 'translate-x-1'}"
							></span>
						</button>
					{:else if col.type === 'select'}
						{@const choices = getChoices(col)}
						{#if expandEditField === col.id}
							<select
								class="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
								bind:value={expandEditVal}
								onblur={() => commitExpandEdit(col)}
								onchange={() => commitExpandEdit(col)}
								autofocus
							>
								<option value="">—</option>
								{#each choices as choice (choice.value)}
									<option value={choice.value}>{choice.value}</option>
								{/each}
							</select>
						{:else}
							{@const selVal = (expandedRow.data[col.id] as string) ?? ''}
							<button
								class="flex min-h-[2.25rem] w-full items-center rounded-xl border border-gray-200 px-3 py-2 text-left text-sm hover:border-blue-300"
								onclick={() => startExpandEdit(col, expandedRow!)}
							>
								{#if selVal}
									{@const color = getChoiceColor(col, selVal)}
									<span
										class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
										>{selVal}</span
									>
								{:else}
									<span class="text-gray-400">—</span>
								{/if}
							</button>
						{/if}
					{:else if col.type === 'tags'}
						{@const tagVals = getTagValues(expandedRow, col.id)}
						{@const choices = getChoices(col)}
						{@const available = choices.filter((c) => !tagVals.includes(c.value))}
						<div
							class="flex min-h-[2.25rem] flex-wrap items-center gap-1 rounded-xl border border-gray-200 px-3 py-2"
						>
							{#each tagVals as tag (tag)}
								{@const color = getChoiceColor(col, tag)}
								<span
									class="inline-flex items-center gap-0.5 rounded-full border px-2 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
								>
									{tag}
									<button
										class="ml-0.5 rounded-full leading-none hover:opacity-60"
										onclick={() => {
											const current = tagVals.filter((t) => t !== tag);
											const newData = { ...expandedRow!.data, [col.id]: current };
											updateRow(expandedRow!.id, { data: newData }).then(() => {
												expandedRow = { ...expandedRow!, data: newData };
												refreshRows($page.params.id);
											});
										}}
										aria-label="Remove {tag}">×</button
									>
								</span>
							{/each}
							{#if available.length > 0}
								<div class="relative">
									<button
										class="rounded-full border border-gray-300 px-2 py-0.5 text-xs text-gray-400 hover:border-blue-400 hover:text-blue-600"
										onclick={() => {
											tagsPopupCell =
												tagsPopupCell?.rowId === expandedRow!.id && tagsPopupCell?.colId === col.id
													? null
													: { rowId: expandedRow!.id, colId: col.id };
										}}>+</button
									>
									{#if tagsPopupCell?.rowId === expandedRow.id && tagsPopupCell?.colId === col.id}
										<div
											class="absolute top-full left-0 z-20 mt-1 min-w-[120px] rounded-xl border border-gray-100 bg-white py-1 shadow-xl"
										>
											{#each available as choice (choice.value)}
												{@const color = TAG_COLORS[choices.indexOf(choice) % TAG_COLORS.length]}
												<button
													class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-gray-50"
													onclick={() => {
														const current = getTagValues(expandedRow!, col.id);
														if (!current.includes(choice.value)) {
															const newData = {
																...expandedRow!.data,
																[col.id]: [...current, choice.value]
															};
															tagsPopupCell = null;
															updateRow(expandedRow!.id, { data: newData }).then(() => {
																expandedRow = { ...expandedRow!, data: newData };
																refreshRows($page.params.id);
															});
														}
													}}
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
					{:else if col.type === 'url'}
						{#if expandEditField === col.id}
							<input
								type="url"
								class="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
								bind:value={expandEditVal}
								onblur={() => commitExpandEdit(col)}
								onkeydown={(e) => {
									if (e.key === 'Enter') commitExpandEdit(col);
									if (e.key === 'Escape') expandEditField = null;
								}}
								autofocus
							/>
						{:else}
							{@const urlVal = (expandedRow.data[col.id] as string) ?? ''}
							<button
								class="flex min-h-[2.25rem] w-full items-center rounded-xl border border-gray-200 px-3 py-2 text-left text-sm hover:border-blue-300"
								onclick={() => startExpandEdit(col, expandedRow!)}
							>
								{#if urlVal}
									<a
										href={urlVal}
										target="_blank"
										rel="noopener noreferrer"
										class="truncate text-sky-600 underline hover:text-sky-800"
										onclick={(e) => e.stopPropagation()}
										title={urlVal}>{urlVal}</a
									>
								{:else}
									<span class="text-gray-400">—</span>
								{/if}
							</button>
						{/if}
					{:else if col.type === 'date'}
						{#if expandEditField === col.id}
							<input
								type="date"
								class="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
								bind:value={expandEditVal}
								onblur={() => commitExpandEdit(col)}
								onkeydown={(e) => {
									if (e.key === 'Enter') commitExpandEdit(col);
									if (e.key === 'Escape') expandEditField = null;
								}}
								autofocus
							/>
						{:else}
							{@const dateVal = expandedRow.data[col.id]
								? formatDate(String(expandedRow.data[col.id]))
								: ''}
							<button
								class="flex min-h-[2.25rem] w-full items-center rounded-xl border border-gray-200 px-3 py-2 text-left font-mono text-sm hover:border-blue-300"
								onclick={() => startExpandEdit(col, expandedRow!)}
							>
								{#if dateVal}
									{dateVal}
								{:else}
									<span class="font-sans text-gray-400">—</span>
								{/if}
							</button>
						{/if}
					{:else if col.type === 'number'}
						{#if expandEditField === col.id}
							<input
								type="number"
								class="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
								bind:value={expandEditVal}
								onblur={() => commitExpandEdit(col)}
								onkeydown={(e) => {
									if (e.key === 'Enter') commitExpandEdit(col);
									if (e.key === 'Escape') expandEditField = null;
								}}
								autofocus
							/>
						{:else}
							<button
								class="flex min-h-[2.25rem] w-full items-center rounded-xl border border-gray-200 px-3 py-2 text-left text-sm hover:border-blue-300"
								onclick={() => startExpandEdit(col, expandedRow!)}
							>
								{#if expandedRow.data[col.id] !== null && expandedRow.data[col.id] !== undefined}
									<span class="text-gray-800">{String(expandedRow.data[col.id])}</span>
								{:else}
									<span class="text-gray-400">—</span>
								{/if}
							</button>
						{/if}
					{:else}
						<!-- text / string -->
						{#if expandEditField === col.id}
							<textarea
								class="w-full resize-none rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
								rows="3"
								bind:value={expandEditVal}
								onblur={() => commitExpandEdit(col)}
								onkeydown={(e) => {
									if (e.key === 'Enter' && !e.shiftKey) commitExpandEdit(col);
									if (e.key === 'Escape') expandEditField = null;
								}}
								autofocus
							></textarea>
						{:else}
							<button
								class="flex min-h-[2.25rem] w-full items-start rounded-xl border border-gray-200 px-3 py-2 text-left text-sm hover:border-blue-300"
								onclick={() => startExpandEdit(col, expandedRow!)}
							>
								{#if expandedRow.data[col.id] !== null && expandedRow.data[col.id] !== undefined && String(expandedRow.data[col.id]) !== ''}
									<span class="break-words whitespace-pre-wrap text-gray-800"
										>{String(expandedRow.data[col.id])}</span
									>
								{:else}
									<span class="text-gray-400">—</span>
								{/if}
							</button>
						{/if}
					{/if}
				</div>
			{/each}
		</div>
	</div>
{/if}

<!-- Import Template Modal -->
{#if showImportTemplateModal}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
		onclick={(e) => {
			if (e.target === e.currentTarget) {
				showImportTemplateModal = false;
				importTemplateError = null;
			}
		}}
		role="dialog"
		aria-modal="true"
		aria-label="Import template"
	>
		<div class="w-full max-w-sm rounded-3xl bg-white p-8 shadow-2xl">
			<h2 class="mb-2 text-xl font-bold text-gray-800">Import Template</h2>
			<p class="mb-6 text-sm text-gray-500">
				Select a <code class="rounded bg-gray-100 px-1 py-0.5 text-xs">template.json</code> file to restore
				column layout, types, and options. Existing rows will not be modified.
			</p>
			{#if importTemplateError}
				<div class="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600">
					{importTemplateError}
				</div>
			{/if}
			<div class="mb-6">
				<label class="mb-1 block text-sm font-medium text-gray-600" for="template-file"
					>Template JSON file</label
				>
				<input
					id="template-file"
					type="file"
					accept=".json,application/json"
					class="w-full rounded-xl border border-gray-200 px-4 py-2 text-sm text-gray-800 outline-none file:mr-3 file:rounded-lg file:border-0 file:bg-blue-50 file:px-3 file:py-1 file:text-sm file:font-medium file:text-blue-600 hover:file:bg-blue-100 focus:border-blue-500"
					onchange={async (e) => {
						const file = (e.currentTarget as HTMLInputElement).files?.[0];
						if (file) await handleImportTemplate(file);
					}}
					disabled={importingTemplate}
				/>
			</div>
			{#if importingTemplate}
				<p class="mb-4 text-center text-sm text-blue-500">Importing…</p>
			{/if}
			<button
				onclick={() => {
					showImportTemplateModal = false;
					importTemplateError = null;
				}}
				disabled={importingTemplate}
				class="w-full rounded-2xl border border-gray-200 px-4 py-2 font-semibold text-gray-600 transition hover:bg-gray-50 disabled:opacity-50"
			>
				Cancel
			</button>
		</div>
	</div>
{/if}

<!-- Import Preview Modal -->
{#if showImportModal}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
		onclick={() => (showImportModal = false)}
	>
		<div
			class="max-h-[80vh] w-full max-w-3xl overflow-auto rounded-2xl bg-white p-6 shadow-2xl"
			onclick={(e) => e.stopPropagation()}
			role="dialog"
			aria-modal="true"
			aria-label="Import CSV preview"
		>
			<h2 class="mb-4 text-lg font-bold text-gray-900">Import CSV Preview</h2>

			{#if importNewColumns.length > 0}
				<div class="mb-4 rounded-xl border border-blue-200 bg-blue-50 p-3">
					<p class="mb-1 text-sm font-semibold text-blue-700">New columns to create:</p>
					<ul class="space-y-0.5">
						{#each importNewColumns as nc (nc.name)}
							<li class="text-sm text-blue-600">
								<span class="font-medium">{nc.name}</span>
								<span class="text-blue-400"> ({nc.type})</span>
							</li>
						{/each}
					</ul>
				</div>
			{/if}

			<p class="mb-2 text-sm text-gray-500">
				{importPreviewRows.length} row{importPreviewRows.length === 1 ? '' : 's'} to import. Preview
				(first 5):
			</p>

			<div class="mb-4 overflow-x-auto rounded-xl border border-gray-200">
				<table class="w-full text-sm">
					<thead class="bg-gray-50">
						<tr>
							{#each importPreviewHeaders as h (h)}
								<th class="border-b border-gray-200 px-3 py-2 text-left font-semibold text-gray-600"
									>{h}</th
								>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each importPreviewRows.slice(0, 5) as row, i (i)}
							<tr class={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
								{#each importPreviewHeaders as h (h)}
									<td class="border-b border-gray-100 px-3 py-1.5 text-gray-700">{row[h] ?? ''}</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			{#if importError}
				<div class="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{importError}</div>
			{/if}

			<div class="flex justify-end gap-3">
				<button
					onclick={() => (showImportModal = false)}
					class="rounded-xl border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
					>Cancel</button
				>
				<button
					onclick={commitImport}
					disabled={importingData}
					class="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
				>
					{importingData ? 'Importing...' : `Import ${importPreviewRows.length} rows`}
				</button>
			</div>
		</div>
	</div>
{/if}

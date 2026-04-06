<!-- routes/[workspace_id]/[table_id]/+page.svelte -->

<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { authStore } from '$lib/stores/auth.store';
	import {
		currentTable,
		currentWorkspace,
		workspaces,
		columns,
		rows,
		loading,
		error,
		loadTable,
		loadWorkspaces,
		refreshRows,
		refreshTable
	} from '$lib/stores/tables.store';
	import {
		fetchTable,
		createRow,
		createColumn,
		deleteColumn,
		updateColumn,
		updateRow,
		deleteRow,
		checkDocExists
	} from '$lib/backend/tables';
	import type {
		Column,
		ColumnChoice,
		ColumnOptions,
		ColumnType,
		Row,
		ViewConfig
	} from '$lib/types/table';
	import { TAG_COLORS } from '$lib/UI/theme.svelte';
	import { createView, updateView } from '$lib/backend/views';
	import { SvelteSet } from 'svelte/reactivity';
	import {
		type FilterCondition,
		type ContextMenuState,
		type RenderItem,
		getItemKey,
		getChoices,
		getChoiceColor,
		getTagValues,
		formatDate,
		parseCSV
	} from '$lib/components/table/table.utils';

	// Components
	import TableToolbar from '$lib/components/table/TableToolbar.svelte';
	import TableGrid from '$lib/components/table/TableGrid.svelte';
	import ViewSwitcher from '$lib/components/table/ViewSwitcher.svelte';
	import KanbanBoard from '$lib/components/table/KanbanBoard.svelte';
	import TimelineView from '$lib/components/table/TimelineView.svelte';
	import ContextMenu from '$lib/components/table/ContextMenu.svelte';
	import AddColumnModal from '$lib/components/table/AddColumnModal.svelte';
	import RowExpandPanel from '$lib/components/table/RowExpandPanel.svelte';
	import ImportTemplateModal from '$lib/components/table/ImportTemplateModal.svelte';
	import ImportPreviewModal from '$lib/components/table/ImportPreviewModal.svelte';
	import ManageOptionsModal from '$lib/components/table/ManageOptionsModal.svelte';
	import CreateTicketModal from '$lib/components/table/CreateTicketModal.svelte';

	// ─── State ───────────────────────────────────────────────────────────────────

	let addingRow = $state(false);
	let showCreateTicket = $state(false);
	let createTicketInitialData = $state<Record<string, unknown>>({});
	let deletingRowId = $state<number | null>(null);
	let expandedRow = $state<Row | null>(null);
	let showAddColumn = $state(false);
	let renamingColId = $state<string | null>(null);
	let renameValue = $state('');
	let editingCell = $state<{ rowId: number; colId: string } | null>(null);
	let editValue = $state<string>('');
	let tagsPopupCell = $state<{ rowId: number; colId: string } | null>(null);
	let colMenuId = $state<string | null>(null);
	let sortConfig = $state<{ colId: string; dir: 'asc' | 'desc' } | null>(null);
	let filterConditions = $state<FilterCondition[]>([]);
	let showFilterPanel = $state(false);
	let hiddenCols = new SvelteSet<string>();
	let searchQuery = $state('');
	let groupConfig = $state<{ colId: string; granularity?: 'month' | 'day' } | null>(null);
	let collapsedGroups = new SvelteSet<string>();
	let contextMenu = $state<ContextMenuState | null>(null);
	let showImportTemplateModal = $state(false);
	let showImportModal = $state(false);
	let importPreviewHeaders = $state<string[]>([]);
	let importPreviewRows = $state<Record<string, string>[]>([]);
	let importNewColumns = $state<{ name: string; type: string; values?: string[] }[]>([]);
	let importingData = $state(false);
	let importError = $state<string | null>(null);
	let managingOptionsCol = $state<Column | null>(null);
	let rowsWithDocs = new SvelteSet<string>();

	// View state
	let activeViewName = $state('');
	let _applyingConfig = false;
	let viewColOrder = $state<string[] | null>(null);

	// Column resize
	let resizingColId = $state<string | null>(null);
	let resizeStartX = $state(0);
	let resizeStartWidth = $state(0);
	let localWidths = $state<Record<string, number>>({});

	function getColWidth(col: Column): number {
		return localWidths[col.column_id] ?? col.options?.width ?? 150;
	}

	// ─── Derived ─────────────────────────────────────────────────────────────────

	const sortedColumns = $derived(
		[...$columns]
			.sort((a, b) => {
				if (viewColOrder && viewColOrder.length > 0) {
					const ai = viewColOrder.indexOf(a.column_id);
					const bi = viewColOrder.indexOf(b.column_id);
					return (ai === -1 ? 9999 : ai) - (bi === -1 ? 9999 : bi);
				}
				return a.position - b.position;
			})
			.filter((c) => !hiddenCols.has(c.column_id))
	);

	const sortedRows = $derived(
		(() => {
			let result = $rows;
			if (searchQuery.trim()) {
				const q = searchQuery.trim().toLowerCase();
				result = result.filter((r) =>
					Object.values(r.row_data).some((v) => {
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
					const cell = r.row_data[cond.colId];
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
					if (Array.isArray(cell)) return cell.some((v) => String(v).toLowerCase().includes(lv));
					return String(cell).toLowerCase().includes(lv);
				});
			}
			if (!sortConfig) return result;
			const { colId, dir } = sortConfig;
			const sortCol = $columns.find((c) => c.column_id === colId);
			const choiceOrder =
				sortCol?.type === 'select'
					? getChoices(sortCol).map((c) => c.value)
					: null;
			return [...result].sort((a, b) => {
				const av = a.row_data[colId];
				const bv = b.row_data[colId];
				if (choiceOrder) {
					const getIdx = (v: unknown) => {
						if (v == null) return choiceOrder!.length;
						const i = choiceOrder!.indexOf(String(v));
						return i === -1 ? choiceOrder!.length : i;
					};
					const cmp = getIdx(av) - getIdx(bv);
					return dir === 'asc' ? cmp : -cmp;
				}
				const as = av === null || av === undefined ? '' : String(av);
				const bs = bv === null || bv === undefined ? '' : String(bv);
				const cmp = as.localeCompare(bs, undefined, { numeric: true, sensitivity: 'base' });
				return dir === 'asc' ? cmp : -cmp;
			});
		})()
	);

	const tableMinWidth = $derived(
		48 + sortedColumns.reduce((sum, col) => sum + getColWidth(col), 0) + 40 + 40
	);

	const activeView = $derived(
		($currentTable?.views ?? []).find((v) => v.name === activeViewName) ??
			($currentTable?.views ?? [])[0] ??
			({ name: 'Table', type: 'table', config: {} } satisfies ViewConfig)
	);

	function getGroupKey(row: Row, colId: string, col: Column): string {
		const val = row.row_data[colId];
		if (val === null || val === undefined || val === '') return '(empty)';
		if (col.type === 'date') {
			const normalized = formatDate(String(val));
			const granularity = groupConfig?.granularity ?? 'month';
			if (granularity === 'month') return normalized.slice(0, 7);
			return normalized.slice(0, 10);
		}
		return String(val);
	}

	const groupedRows = $derived(
		(() => {
			if (!groupConfig) return null;
			const { colId: gcColId, granularity: gcGranularity } = groupConfig;
			const col = $columns.find((c) => c.column_id === gcColId);
			if (!col) return null;
			const keyOrder: string[] = [];
			const keyMap: Record<string, Row[]> = {};
			for (const row of sortedRows) {
				const key = getGroupKey(row, col.column_id, col);
				if (!keyMap[key]) {
					keyMap[key] = [];
					keyOrder.push(key);
				}
				keyMap[key].push(row);
			}
			return { groups: keyOrder.map((key) => ({ key, rows: keyMap[key] })), col };
		})()
	);

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

	// ─── Lifecycle ───────────────────────────────────────────────────────────────

	$effect(() => {
		const tableId = $page.params.table_id!;
		(async () => {
			if (!$authStore?.role) {
				goto('/login');
				return;
			}
			try {
				const [table] = await Promise.all([fetchTable(tableId), loadWorkspaces()]);
				await loadTable(table);
				// Non-blocking: load doc flags in background, don't block page render
				loadDocFlags(table.table_id, get(rows)).catch(() => {});
				const ws = get(workspaces).find((w) => w.workspace_id === table.workspace_id);
				if (ws) currentWorkspace.set(ws);
				// Guard against effect persisting during initial view config apply
				_applyingConfig = true;
				// Restore active view from URL param or localStorage
				const urlView = new URL(window.location.href).searchParams.get('view');
				const savedView = urlView ?? localStorage.getItem(`view:${tableId}`);
				if (savedView && table.views.some((v) => v.name === savedView)) {
					activeViewName = savedView;
				} else if (table.views.length > 0) {
					activeViewName = table.views[0].name;
				}
				// Apply sort/group/filter from active view config
				const initView = table.views.find((v) => v.name === activeViewName);
				if (initView) applyViewConfig(initView);  // also sets _applyingConfig = true and schedules reset
			} catch (e) {
				error.set(e instanceof Error ? e.message : 'Failed to load table');
			}
		})();
	});

	onMount(() => {
		function onResizeMove(e: MouseEvent) {
			if (!resizingColId) return;
			const delta = e.clientX - resizeStartX;
			localWidths = { ...localWidths, [resizingColId]: Math.max(60, resizeStartWidth + delta) };
		}

		function onResizeUp() {
			if (!resizingColId) return;
			resizingColId = null;
			// localWidths already updated by onResizeMove; $effect will persist to view config
		}

		function onWindowClick() {
			colMenuId = null;
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

	// ─── Handlers ────────────────────────────────────────────────────────────────

	async function handleAddRow() {
		const tableId = $page.params.table_id!;
		addingRow = true;
		error.set(null);
		try {
			await createRow(tableId, { row_data: {} });
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to add row');
		} finally {
			addingRow = false;
		}
	}

	function openCreateTicket(initialData: Record<string, unknown> = {}) {
		createTicketInitialData = initialData;
		showCreateTicket = true;
	}

	async function handleCreateTicket(rowData: Record<string, unknown>) {
		const tableId = $page.params.table_id!;
		showCreateTicket = false;
		addingRow = true;
		error.set(null);
		try {
			await createRow(tableId, { row_data: rowData });
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to create ticket');
		} finally {
			addingRow = false;
		}
	}

	async function handleAddRowInGroup(groupKey: string, col: Column) {
		const tableId = $page.params.table_id!;
		addingRow = true;
		error.set(null);
		try {
			const val: unknown = groupKey === '(empty)' ? null : groupKey;
			await createRow(tableId, { row_data: { [col.column_id]: val } });
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to add row');
		} finally {
			addingRow = false;
		}
	}

	async function handleDeleteRow(rowId: number) {
		const tableId = $page.params.table_id!;
		const row = $rows.find((r) => r.row_number === rowId);
		if (!row) return;
		deletingRowId = rowId;
		error.set(null);
		try {
			await deleteRow(tableId, row.row_number);
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to delete row');
		} finally {
			deletingRowId = null;
		}
	}

	async function handleAddColumn(name: string, type: string) {
		const tableId = $page.params.table_id!;
		error.set(null);
		try {
			await createColumn(tableId, { name, type: type as ColumnType });
			await refreshTable(tableId);
			showAddColumn = false;
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to add column');
		}
	}

	async function handleDeleteColumn(colId: string) {
		const tableId = $page.params.table_id!;
		error.set(null);
		try {
			await deleteColumn(tableId, colId);
			await refreshTable(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to delete column');
		}
	}

	function handleMoveColumn(col: Column, direction: 'up' | 'down') {
		// Build current ordered list using viewColOrder if available, else col.position
		const ordered = [...$columns]
			.sort((a, b) => {
				if (viewColOrder && viewColOrder.length > 0) {
					const ai = viewColOrder.indexOf(a.column_id);
					const bi = viewColOrder.indexOf(b.column_id);
					return (ai === -1 ? 9999 : ai) - (bi === -1 ? 9999 : bi);
				}
				return a.position - b.position;
			})
			.map((c) => c.column_id);
		const idx = ordered.indexOf(col.column_id);
		const swapIdx = direction === 'up' ? idx - 1 : idx + 1;
		if (swapIdx < 0 || swapIdx >= ordered.length) return;
		[ordered[idx], ordered[swapIdx]] = [ordered[swapIdx], ordered[idx]];
		viewColOrder = ordered;
		// $effect will call persistViewConfig()
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
		const tableId = $page.params.table_id!;
		error.set(null);
		try {
			await updateColumn(tableId, colId, { name: renameValue.trim() });
			await refreshTable(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to rename column');
		} finally {
			renamingColId = null;
		}
	}

	function startEdit(rowId: number, col: Column, currentVal: unknown) {
		editingCell = { rowId, colId: col.column_id };
		editValue = currentVal === null || currentVal === undefined ? '' : String(currentVal);
	}

	async function commitEdit(rowId: number, col: Column) {
		if (!editingCell) return;
		editingCell = null;
		const tableId = $page.params.table_id!;
		const row = $rows.find((r) => r.row_number === rowId);
		if (!row) return;
		let parsed: unknown = editValue;
		if (col.type === 'number') parsed = editValue === '' ? null : Number(editValue);
		else if (col.type === 'checkbox') parsed = editValue === 'true';
		else if (editValue === '') parsed = null;
		const newData = { ...row.row_data, [col.column_id]: parsed };
		error.set(null);
		try {
			await updateRow(tableId, row.row_number, { row_data: newData });
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update cell');
		}
	}

	async function toggleCheckbox(rowId: number, col: Column) {
		const tableId = $page.params.table_id!;
		const row = $rows.find((r) => r.row_number === rowId);
		if (!row) return;
		const newData = { ...row.row_data, [col.column_id]: !row.row_data[col.column_id] };
		error.set(null);
		try {
			await updateRow(tableId, row.row_number, { row_data: newData });
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update cell');
		}
	}

	async function removeTag(rowId: number, col: Column, tag: string) {
		const tableId = $page.params.table_id!;
		const row = $rows.find((r) => r.row_number === rowId);
		if (!row) return;
		const current = getTagValues(row, col.column_id);
		const newData = { ...row.row_data, [col.column_id]: current.filter((t) => t !== tag) };
		try {
			await updateRow(tableId, row.row_number, { row_data: newData });
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update tags');
		}
	}

	async function addTag(rowId: number, col: Column, tag: string) {
		const tableId = $page.params.table_id!;
		const row = $rows.find((r) => r.row_number === rowId);
		if (!row) return;
		const current = getTagValues(row, col.column_id);
		if (current.includes(tag)) return;
		const newData = { ...row.row_data, [col.column_id]: [...current, tag] };
		tagsPopupCell = null;
		try {
			await updateRow(tableId, row.row_number, { row_data: newData });
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update tags');
		}
	}

	async function handleUpdateRow(rowId: number, data: Record<string, unknown>) {
		const tableId = $page.params.table_id!;
		const row = $rows.find((r) => r.row_number === rowId);
		if (!row) return;
		await updateRow(tableId, row.row_number, { row_data: data });
	}

	async function loadDocFlags(tableId: string, _rowList: import('$lib/types/table').Row[]) {
		const { batchDocsExist } = await import('$lib/backend/tables');
		const docSet = await batchDocsExist(tableId);
		rowsWithDocs.clear();
		for (const rowNumber of docSet) {
			rowsWithDocs.add(String(rowNumber));
		}
	}

	async function handleRefreshRows(tableId: string) {
		await refreshRows(tableId);
		loadDocFlags(tableId, get(rows));
	}

	function openExpand(row: Row) {
		expandedRow = row;
	}

	function openContextMenu(e: MouseEvent, type: 'row' | 'col', id: string) {
		e.preventDefault();
		e.stopPropagation();
		colMenuId = null;
		contextMenu = { type, id, x: e.clientX, y: e.clientY };
	}

	async function handleDuplicateRow(rowId: number) {
		const row = $rows.find((r) => r.row_number === rowId);
		if (!row) return;
		const tableId = $page.params.table_id!;
		error.set(null);
		try {
			await createRow(tableId, { row_data: { ...row.row_data } });
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to duplicate row');
		}
		contextMenu = null;
	}

	async function handleSaveOptions(
		colId: string,
		choices: import('$lib/types/table').ColumnChoice[]
	) {
		const tableId = $page.params.table_id!;
		const col = $columns.find((c) => c.column_id === colId);
		if (!col) return;
		error.set(null);
		try {
			await updateColumn(tableId, colId, { options: { ...col.options, choices } });
			await refreshTable(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update options');
		}
	}

	function handleResizeStart(e: MouseEvent, col: Column) {
		e.preventDefault();
		e.stopPropagation();
		resizingColId = col.column_id;
		resizeStartX = e.clientX;
		resizeStartWidth = getColWidth(col);
	}

	// Filter helpers
	function addFilterCondition() {
		const firstCol = $columns[0];
		filterConditions = [
			...filterConditions,
			{ id: crypto.randomUUID(), colId: firstCol?.column_id ?? '', operator: 'contains', value: '' }
		];
	}

	function removeFilterCondition(id: string) {
		filterConditions = filterConditions.filter((c) => c.id !== id);
	}

	function toggleHideCol(colId: string) {
		if (hiddenCols.has(colId)) hiddenCols.delete(colId);
		else hiddenCols.add(colId);
	}

	function toggleCollapseGroup(key: string) {
		if (collapsedGroups.has(key)) collapsedGroups.delete(key);
		else collapsedGroups.add(key);
	}

	function addFilterForColumn(colId: string) {
		if (!filterConditions.find((c) => c.colId === colId)) {
			filterConditions = [
				...filterConditions,
				{ id: crypto.randomUUID(), colId, operator: 'contains', value: '' }
			];
		}
		showFilterPanel = true;
	}

	// View config helpers
	function applyViewConfig(view: ViewConfig) {
		_applyingConfig = true;
		// Sort
		if (view.config?.sort) {
			const s = view.config.sort as { colId: string; dir: 'asc' | 'desc' };
			if (s.colId && s.dir) sortConfig = s;
			else sortConfig = null;
		} else {
			sortConfig = null;
		}
		// Group
		if (view.config?.group) {
			const g = view.config.group as { colId: string; granularity?: 'month' | 'day' };
			if (g.colId) groupConfig = g;
			else groupConfig = null;
		} else {
			groupConfig = null;
		}
		// Filter
		if (view.config?.filter && Array.isArray(view.config.filter)) {
			const saved = view.config.filter as { colId: string; operator: string; value: string }[];
			filterConditions = saved.map((f) => ({
				id: crypto.randomUUID(),
				colId: f.colId,
				operator: f.operator as FilterCondition['operator'],
				value: f.value
			}));
		} else {
			filterConditions = [];
		}
		// Hidden cols
		hiddenCols.clear();
		if (view.config?.hidden && Array.isArray(view.config.hidden)) {
			for (const colId of view.config.hidden as string[]) {
				hiddenCols.add(colId);
			}
		}
		// Col widths (per-view override)
		if (view.config?.widths && typeof view.config.widths === 'object' && !Array.isArray(view.config.widths)) {
			localWidths = { ...(view.config.widths as Record<string, number>) };
		} else {
			localWidths = {};
		}
		// Col order (per-view override)
		if (view.config?.colOrder && Array.isArray(view.config.colOrder)) {
			viewColOrder = view.config.colOrder as string[];
		} else {
			viewColOrder = null;
		}
		Promise.resolve().then(() => { _applyingConfig = false; });
	}

	function persistViewConfig() {
		const tableId = $page.params.table_id!;
		const view = ($currentTable?.views ?? []).find((v) => v.name === activeViewName);
		if (!view) return;
		const newConfig = {
			...view.config,
			sort: sortConfig ?? undefined,
			group: groupConfig ?? undefined,
			filter: filterConditions.length > 0
				? filterConditions.map(({ colId, operator, value }) => ({ colId, operator, value }))
				: undefined,
			hidden: hiddenCols.size > 0 ? [...hiddenCols] : undefined,
			widths: Object.keys(localWidths).length > 0 ? { ...localWidths } : undefined,
			colOrder: viewColOrder ?? undefined
		};
		updateView(tableId, view.name, newConfig).catch(() => {});
	}

	// Auto-persist view config when any view-local state changes (but not during applyViewConfig)
	$effect(() => {
		// Establish reactive dependencies
		const _s = JSON.stringify(sortConfig);
		const _g = JSON.stringify(groupConfig);
		const _f = JSON.stringify(filterConditions);
		const _h = [...hiddenCols].sort().join(',');
		const _w = JSON.stringify(localWidths);
		const _o = JSON.stringify(viewColOrder);
		if (!_applyingConfig && activeViewName) {
			persistViewConfig();
		}
	});

	// View handlers
	function handleViewChange(view: ViewConfig) {
		activeViewName = view.name;
		const tableId = $page.params.table_id!;
		localStorage.setItem(`view:${tableId}`, view.name);
		const url = new URL(window.location.href);
		url.searchParams.set('view', view.name);
		history.replaceState(history.state, '', url.toString());
		applyViewConfig(view);
	}

	async function handleAddView(type: string, name: string) {
		const tableId = $page.params.table_id!;
		error.set(null);
		try {
			await createView(tableId, { name, type, config: {} });
			await refreshTable(tableId);
			activeViewName = name;
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to create view');
		}
	}

	async function handleViewUpdate(_updated: ViewConfig) {
		await refreshTable($page.params.table_id!);
	}

	// Export / Import
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
		const tableId = $page.params.table_id!;
		const text = await file.text();
		const template = JSON.parse(text) as Array<{
			name: string;
			type: string;
			options?: ColumnOptions;
			position?: number;
		}>;
		if (!Array.isArray(template)) throw new Error('Invalid template: expected an array');
		await Promise.all([...$columns].map((col) => deleteColumn(tableId, col.column_id)));
		for (const col of template) {
			await createColumn(tableId, {
				name: col.name,
				type: col.type as ColumnType,
				options: col.options ?? {},
				position: col.position ?? 0
			});
		}
		await refreshTable(tableId);
		showImportTemplateModal = false;
	}

	function exportCSV() {
		const cols = [...$columns].sort((a, b) => a.position - b.position);
		const headers = cols.map((c) => c.name);
		const escapeCSV = (v: string) => `"${v.replace(/"/g, '""')}"`;
		const csvRows = [
			headers.map(escapeCSV).join(','),
			...$rows.map((row) =>
				cols
					.map((col) => {
						const val = row.row_data[col.column_id];
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
			for (const col of cols) obj[col.name] = row.row_data[col.column_id] ?? null;
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
			const newColValueSets: Record<string, Set<string>> = {};
			for (const h of headers) {
				const m = h.match(/^(.+)\{\{(\w+)\}\}$/);
				if (m) {
					const colName = m[1].trim();
					const colType = m[2].toLowerCase();
					const exists = $columns.some((c) => c.name === colName);
					if (!exists) {
						newColValueSets[colName] = new Set<string>();
						importNewColumns = [...importNewColumns, { name: colName, type: colType }];
					}
				}
			}
			const dataRows = parsed.slice(1);
			for (const cells of dataRows) {
				headers.forEach((h, i) => {
					const m = h.match(/^(.+)\{\{(\w+)\}\}$/);
					if (!m) return;
					const colName = m[1].trim();
					const colType = m[2].toLowerCase();
					if (!newColValueSets[colName]) return;
					const val = (cells[i] ?? '').trim();
					if (!val) return;
					if (colType === 'tags')
						val
							.split(',')
							.map((v) => v.trim())
							.filter(Boolean)
							.forEach((v) => newColValueSets[colName].add(v));
					else if (colType === 'select') newColValueSets[colName].add(val);
				});
			}
			importNewColumns = importNewColumns.map((nc) => ({
				...nc,
				values: newColValueSets[nc.name] ? [...newColValueSets[nc.name]] : []
			}));
			importError = null;
			showImportModal = true;
		};
		reader.readAsText(file);
		input.value = '';
	}

	async function commitImport() {
		importingData = true;
		importError = null;
		const tableId = $page.params.table_id!;
		try {
			for (let i = 0; i < importNewColumns.length; i++) {
				const nc = importNewColumns[i];
				const choices =
					nc.values && nc.values.length > 0
						? nc.values.map((v, vi) => ({ value: v, color: TAG_COLORS[vi % TAG_COLORS.length].bg }))
						: [];
				await createColumn(tableId, {
					name: nc.name,
					type: nc.type as ColumnType,
					options: { choices }
				});
			}
			await refreshTable(tableId);
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
					if (col.type === 'tags')
						data[col.column_id] = rawVal
							.split(',')
							.map((v) => v.trim())
							.filter(Boolean);
					else if (col.type === 'checkbox')
						data[col.column_id] = rawVal.toLowerCase() === 'true' || rawVal === '1';
					else if (col.type === 'number') {
						const n = Number(rawVal);
						data[col.column_id] = isNaN(n) ? null : n;
					} else data[col.column_id] = rawVal;
				}
				await createRow(tableId, { row_data: data });
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
	class="flex h-full flex-col bg-white {resizingColId ? 'cursor-col-resize select-none' : ''}"
>
	{#if $error}
		<div class="mx-4 mt-2 rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">{$error}</div>
	{/if}

	<ViewSwitcher
		views={$currentTable?.views ?? []}
		activeViewName={activeView.name}
		onViewChange={handleViewChange}
		onAddRow={() => openCreateTicket()}
		onAddView={handleAddView}
	/>

	{#if activeView.type === 'table'}
		<TableToolbar
			columns={$columns}
			{sortConfig}
			{groupConfig}
			{hiddenCols}
			{filterConditions}
			{showFilterPanel}
			{searchQuery}
			onSortChange={(c) => (sortConfig = c)}
			onGroupChange={(c) => (groupConfig = c)}
			onToggleHideCol={toggleHideCol}
			onClearHiddenCols={() => hiddenCols.clear()}
			onFilterConditionsChange={(c) => (filterConditions = c)}
			onShowFilterPanelChange={(s) => (showFilterPanel = s)}
			onSearchQueryChange={(q) => (searchQuery = q)}
			onExportTemplate={handleExportTemplate}
			onShowImportTemplate={() => (showImportTemplateModal = true)}
			onExportCSV={exportCSV}
			onExportJSON={exportJSON}
			onImportFile={handleImportFile}
			onAddFilterCondition={addFilterCondition}
			onRemoveFilterCondition={removeFilterCondition}
			onClearAllFilters={() => (filterConditions = [])}
		/>

		<TableGrid
			columns={$columns}
			{sortedColumns}
			{renderItems}
			loading={$loading}
			{tableMinWidth}
			{addingRow}
			{deletingRowId}
			{rowsWithDocs}
			{editingCell}
			{editValue}
			{renamingColId}
			{renameValue}
			{colMenuId}
			{tagsPopupCell}
			{sortConfig}
			{filterConditions}
			{resizingColId}
			{hiddenCols}
			{collapsedGroups}
			{localWidths}
			onStartEdit={startEdit}
			onCommitEdit={commitEdit}
			onEditValueChange={(v) => (editValue = v)}
			onEditingCellChange={(c) => (editingCell = c)}
			onToggleCheckbox={toggleCheckbox}
			onRemoveTag={removeTag}
			onAddTag={addTag}
			onTagsPopupChange={(c) => (tagsPopupCell = c)}
			onDeleteRow={handleDeleteRow}
			onOpenExpand={openExpand}
			onOpenContextMenu={openContextMenu}
			onStartRename={startRename}
			onCommitRename={commitRename}
			onRenameValueChange={(v) => (renameValue = v)}
			onRenamingColIdChange={(id) => (renamingColId = id)}
			onColMenuChange={(id) => (colMenuId = id)}
			onSortChange={(c) => (sortConfig = c)}
			onFilterAdd={addFilterForColumn}
			onShowFilterPanel={() => (showFilterPanel = true)}
			onHideCol={(id) => hiddenCols.add(id)}
			onDeleteColumn={handleDeleteColumn}
			onMoveColumn={handleMoveColumn}
			onResizeStart={handleResizeStart}
			onShowAddColumn={() => (showAddColumn = true)}
			onAddRow={() => openCreateTicket()}
			onAddRowInGroup={handleAddRowInGroup}
			onToggleCollapseGroup={toggleCollapseGroup}
			onManageOptions={(col) => (managingOptionsCol = col)}
			onNavigateRow={(rowId) => {
				const r = $rows.find((row) => row.row_number === rowId);
				if (r) goto(`/${$page.params.workspace_id}/${$page.params.table_id}/${r.row_number}`);
			}}
		/>
	{:else if activeView.type === 'kanban'}
		<KanbanBoard
			tableId={$page.params.table_id!}
			columns={$columns}
			rows={$rows}
			viewConfig={activeView}
			onOpenExpand={openExpand}
			onRowsRefresh={() => refreshRows($page.params.table_id!)}
			onViewUpdate={handleViewUpdate}
			onAddRow={openCreateTicket}
		/>
	{:else if activeView.type === 'timeline'}
		<TimelineView
			tableId={$page.params.table_id!}
			columns={$columns}
			rows={$rows}
			viewConfig={activeView}
			onOpenExpand={openExpand}
			onRowsRefresh={() => refreshRows($page.params.table_id!)}
			onViewUpdate={handleViewUpdate}
			onAddRow={openCreateTicket}
		/>
	{/if}
</div>

<!-- Overlays -->
{#if contextMenu}
	<ContextMenu
		{contextMenu}
		columns={$columns}
		rows={$rows}
		{sortConfig}
		{filterConditions}
		onClose={() => (contextMenu = null)}
		onExpandRow={openExpand}
		onDuplicateRow={handleDuplicateRow}
		onDeleteRow={handleDeleteRow}
		onRenameColumn={startRename}
		onSortChange={(c) => (sortConfig = c)}
		onAddFilter={addFilterForColumn}
		onHideColumn={(id) => hiddenCols.add(id)}
		onDeleteColumn={handleDeleteColumn}
	/>
{/if}

<AddColumnModal
	show={showAddColumn}
	onClose={() => (showAddColumn = false)}
	onAdd={handleAddColumn}
/>

{#if expandedRow}
	<RowExpandPanel
		row={expandedRow}
		columns={$columns}
		onClose={() => (expandedRow = null)}
		onUpdateRow={handleUpdateRow}
		onRefreshRows={handleRefreshRows}
		tableId={$page.params.table_id!}
		workspaceId={$page.params.workspace_id!}
	/>
{/if}

<ImportTemplateModal
	show={showImportTemplateModal}
	onClose={() => (showImportTemplateModal = false)}
	onImport={handleImportTemplate}
/>

<ImportPreviewModal
	show={showImportModal}
	headers={importPreviewHeaders}
	previewRows={importPreviewRows}
	newColumns={importNewColumns}
	importing={importingData}
	error={importError}
	onClose={() => (showImportModal = false)}
	onConfirm={commitImport}
/>

{#if managingOptionsCol}
	<ManageOptionsModal
		col={managingOptionsCol}
		onClose={() => (managingOptionsCol = null)}
		onSave={handleSaveOptions}
	/>
{/if}

<CreateTicketModal
	show={showCreateTicket}
	columns={$columns}
	initialData={createTicketInitialData}
	onClose={() => (showCreateTicket = false)}
	onSubmit={handleCreateTicket}
/>

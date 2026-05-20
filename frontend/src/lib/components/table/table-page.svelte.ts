// src/lib/components/table/table-page.svelte.ts
// Reactive UI state + handlers for the [table_id] page.
// Uses $state() runes — must be .svelte.ts.

import { SvelteSet } from 'svelte/reactivity';
import { get } from 'svelte/store';
import { replaceState } from '$app/navigation';
import { page } from '$app/stores';
import { columns } from '$lib/stores/table_schema.store';
import { views as viewsStore } from '$lib/stores/table_views.store';
import { rows } from '$lib/stores/table_rows.store';
import { error, IMPLICIT_TABLE_VIEW } from '$lib/stores/tables.store';
import {
	createRow,
	createColumn,
	deleteColumn as deleteColumnApi,
	updateColumn,
	deleteRow as deleteRowApi,
	updateRow,
	fetchRows,
	fetchTable,
	patchSchema,
	batchDocsExist
} from '$lib/backend/tables';
import { createView, updateView, deleteView } from '$lib/backend/views';

function randomHex(): string {
	const h = Math.floor(Math.random() * 360);
	const s = 60 + Math.random() * 15;
	const l = 55 + Math.random() * 10;
	const f = (n: number) => {
		const k = (n + h / 30) % 12;
		const a = (s / 100) * Math.min(l / 100, 1 - l / 100);
		return Math.round(255 * (l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))));
	};
	return `#${[f(0), f(8), f(4)].map((v) => v.toString(16).padStart(2, '0')).join('')}`;
}

import {
	type FilterCondition,
	type ContextMenuState,
	parseCSV,
	applyEditToRowData,
	toggleCheckboxInRowData,
	removeTagFromRowData,
	addTagToRowData,
	buildTemplateJSON,
	buildCSV,
	buildExportJSON,
	triggerDownload
} from '$lib/components/table/table.utils';
import type {
	Column,
	ColumnChoice,
	ColumnOptions,
	ColumnType,
	Row,
	ViewConfig
} from '$lib/types/table';

class TablePageStore {
	// ─── UI State ──────────────────────────────────────────────────────────────
	addingRow = $state(false);
	addingColumn = $state(false);
	scrollToRowId = $state<number | null>(null);
	scrollToColTrigger = $state(0);
	showCreateTicket = $state(false);
	createTicketInitialData = $state<Record<string, unknown>>({});
	deletingRowId = $state<number | null>(null);
	expandedRow = $state<Row | null>(null);
	docCellState = $state<{ row: Row; col: Column } | null>(null);
	showAddColumn = $state(false);
	renamingColId = $state<string | null>(null);
	renameValue = $state('');
	editingCell = $state<{ rowId: number; colId: string } | null>(null);
	editValue = $state<string>('');
	tagsPopupCell = $state<{ rowId: number; colId: string } | null>(null);
	colMenuId = $state<string | null>(null);
	sortConfig = $state<{ colId: string; dir: 'asc' | 'desc' } | null>(null);
	filterConditions = $state<FilterCondition[]>([]);
	showFilterPanel = $state(false);
	searchQuery = $state('');
	groupConfig = $state<{ colId: string; granularity?: 'month' | 'day' } | null>(null);
	collapsedGroups = new SvelteSet<string>();
	contextMenu = $state<ContextMenuState | null>(null);
	showImportTemplateModal = $state(false);
	showImportModal = $state(false);
	importPreviewHeaders = $state<string[]>([]);
	importPreviewRows = $state<Record<string, string>[]>([]);
	importNewColumns = $state<{ name: string; type: string; values?: string[] }[]>([]);
	importingData = $state(false);
	importError = $state<string | null>(null);
	managingOptionsCol = $state<Column | null>(null);
	rowsWithDocs = new SvelteSet<string>();
	activeViewId = $state<number>(0);
	private _suppressPersist = 0;
	viewColOrder = $state<string[] | null>(null);
	resizingColId = $state<string | null>(null);
	resizeStartX = $state(0);
	resizeStartWidth = $state(0);
	localWidths = $state<Record<string, number>>({});

	get tableId(): string {
		return get(page).params.table_id ?? '';
	}

	getColWidth(col: Column): number {
		return this.localWidths[col.column_id] ?? col.options?.width ?? 150;
	}

	reset() {
		this.addingRow = false;
		this.addingColumn = false;
		this.scrollToRowId = null;
		this.scrollToColTrigger = 0;
		this.showCreateTicket = false;
		this.createTicketInitialData = {};
		this.deletingRowId = null;
		this.expandedRow = null;
		this.docCellState = null;
		this.showAddColumn = false;
		this.renamingColId = null;
		this.renameValue = '';
		this.editingCell = null;
		this.editValue = '';
		this.tagsPopupCell = null;
		this.colMenuId = null;
		this.sortConfig = null;
		this.filterConditions = [];
		this.showFilterPanel = false;
		this.searchQuery = '';
		this.groupConfig = null;
		this.collapsedGroups.clear();
		this.contextMenu = null;
		this.showImportTemplateModal = false;
		this.showImportModal = false;
		this.importPreviewHeaders = [];
		this.importPreviewRows = [];
		this.importNewColumns = [];
		this.importError = null;
		this.managingOptionsCol = null;
		this.rowsWithDocs.clear();
		this.activeViewId = 0;
		this._suppressPersist = 0;
		this.viewColOrder = null;
		this.localWidths = {};
	}

	// ─── Row handlers ──────────────────────────────────────────────────────────

	async handleAddRow(editColId?: string) {
		if (this.addingRow) return;
		const tableId = this.tableId;
		this.addingRow = true;
		error.set(null);
		try {
			const newRow = await createRow(tableId, { row_data: {} });
			this.scrollToRowId = newRow.row_id;
			if (editColId) {
				this.editingCell = { rowId: newRow.row_id, colId: editColId };
				this.editValue = '';
			}
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to add row');
		} finally {
			this.addingRow = false;
		}
	}

	openCreateTicket(initialData: Record<string, unknown> = {}) {
		this.createTicketInitialData = initialData;
		this.showCreateTicket = true;
	}

	async handleCreateTicket(rowData: Record<string, unknown>) {
		const tableId = this.tableId;
		this.showCreateTicket = false;
		this.addingRow = true;
		error.set(null);
		try {
			await createRow(tableId, { row_data: rowData });
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to create ticket');
		} finally {
			this.addingRow = false;
		}
	}

	async handleAddRowInGroup(groupKey: string, col: Column) {
		if (this.addingRow) return;
		const tableId = this.tableId;
		this.addingRow = true;
		error.set(null);
		const val: unknown = groupKey === '(empty)' ? null : groupKey;
		try {
			await createRow(tableId, { row_data: { [col.column_id]: val } });
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to add row');
		} finally {
			this.addingRow = false;
		}
	}

	async handleDeleteRow(rowId: number) {
		const tableId = this.tableId;
		this.deletingRowId = rowId;
		error.set(null);
		try {
			await deleteRowApi(tableId, rowId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to delete row');
		} finally {
			this.deletingRowId = null;
		}
	}

	async handleDuplicateRow(rowId: number) {
		const row = get(rows).find((r) => r.row_id === rowId);
		if (!row) return;
		const tableId = this.tableId;
		error.set(null);
		try {
			await createRow(tableId, { row_data: { ...row.row_data } });
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to duplicate row');
		}
		this.contextMenu = null;
	}

	async handleUpdateRow(rowId: number, data: Record<string, unknown>) {
		const row = get(rows).find((r) => r.row_id === rowId);
		if (!row) return;
		await updateRow(this.tableId, row.row_id, { row_data: data });
	}

	async loadDocFlags(tableId: string) {
		const docSet = await batchDocsExist(tableId);
		this.rowsWithDocs.clear();
		for (const rowNumber of docSet) this.rowsWithDocs.add(String(rowNumber));
	}

	async handleRefreshRows(tableId: string) {
		await fetchRows(tableId);
		this.loadDocFlags(tableId).catch(() => {});
	}

	// ─── Cell edit handlers ────────────────────────────────────────────────────

	startEdit(rowId: number, col: Column, currentVal: unknown) {
		this.editingCell = { rowId, colId: col.column_id };
		this.editValue = currentVal === null || currentVal === undefined ? '' : String(currentVal);
	}

	async commitEdit(rowId: number, col: Column) {
		if (!this.editingCell) return;
		this.editingCell = null;
		const row = get(rows).find((r) => r.row_id === rowId);
		if (!row) return;
		const newData = applyEditToRowData(row.row_data, col.column_id, this.editValue, col.type);
		error.set(null);
		try {
			await updateRow(this.tableId, row.row_id, { row_data: newData });
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update cell');
		}
	}

	async toggleCheckbox(rowId: number, col: Column) {
		const row = get(rows).find((r) => r.row_id === rowId);
		if (!row) return;
		const newData = toggleCheckboxInRowData(row.row_data, col.column_id);
		error.set(null);
		try {
			await updateRow(this.tableId, row.row_id, { row_data: newData });
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update cell');
		}
	}

	async removeTag(rowId: number, col: Column, tag: string) {
		const row = get(rows).find((r) => r.row_id === rowId);
		if (!row) return;
		const newData = removeTagFromRowData(row.row_data, col.column_id, tag);
		try {
			await updateRow(this.tableId, row.row_id, { row_data: newData });
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update tags');
		}
	}

	async addTag(rowId: number, col: Column, tag: string) {
		const row = get(rows).find((r) => r.row_id === rowId);
		if (!row) return;
		const newData = addTagToRowData(row.row_data, col.column_id, tag);
		if (newData === row.row_data) return;
		this.tagsPopupCell = null;
		try {
			await updateRow(this.tableId, row.row_id, { row_data: newData });
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update tags');
		}
	}

	// ─── Column handlers ───────────────────────────────────────────────────────

	async handleAddColumn(name: string, type: string) {
		const tableId = this.tableId;
		this.addingColumn = true;
		error.set(null);
		try {
			await createColumn(tableId, { name, type: type as ColumnType });
			await fetchTable(tableId);
			this.showAddColumn = false;
			this.scrollToColTrigger += 1;
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to add column');
		} finally {
			this.addingColumn = false;
		}
	}

	async handleDeleteColumn(colId: string) {
		error.set(null);
		try {
			await deleteColumnApi(this.tableId, colId);
			await fetchTable(this.tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to delete column');
		}
	}

	startRename(colId: string, currentName: string) {
		this.renamingColId = colId;
		this.renameValue = currentName;
	}

	async commitRename(colId: string) {
		if (!this.renameValue.trim()) {
			this.renamingColId = null;
			return;
		}
		error.set(null);
		try {
			await updateColumn(this.tableId, colId, { name: this.renameValue.trim() });
			await fetchTable(this.tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to rename column');
		} finally {
			this.renamingColId = null;
		}
	}

	async handleSaveOptions(colId: string, choices: ColumnChoice[]) {
		const col = get(columns).find((c) => c.column_id === colId);
		if (!col) return;
		error.set(null);
		try {
			await updateColumn(this.tableId, colId, { options: { ...col.options, choices } });
			await fetchTable(this.tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update options');
		}
	}

	handleResizeStart(e: MouseEvent, col: Column) {
		e.preventDefault();
		e.stopPropagation();
		this.resizingColId = col.column_id;
		this.resizeStartX = e.clientX;
		this.resizeStartWidth = this.getColWidth(col);
	}

	// ─── UI helpers ────────────────────────────────────────────────────────────

	addFilterCondition() {
		const firstCol = get(columns)[0];
		this.filterConditions = [
			...this.filterConditions,
			{ id: crypto.randomUUID(), colId: firstCol?.column_id ?? '', operator: 'contains', value: '' }
		];
	}

	removeFilterCondition(id: string) {
		this.filterConditions = this.filterConditions.filter((c) => c.id !== id);
	}

	toggleCollapseGroup(key: string) {
		if (this.collapsedGroups.has(key)) this.collapsedGroups.delete(key);
		else this.collapsedGroups.add(key);
	}

	addFilterForColumn(colId: string) {
		if (!this.filterConditions.find((c) => c.colId === colId)) {
			this.filterConditions = [
				...this.filterConditions,
				{ id: crypto.randomUUID(), colId, operator: 'contains', value: '' }
			];
		}
		this.showFilterPanel = true;
	}

	openExpand(row: Row) {
		this.expandedRow = row;
	}

	openContextMenu(e: MouseEvent, type: 'row' | 'col', id: string) {
		e.preventDefault();
		e.stopPropagation();
		this.colMenuId = null;
		this.contextMenu = { type, id, x: e.clientX, y: e.clientY };
	}

	// ─── View config ───────────────────────────────────────────────────────────

	applyViewConfig(view: ViewConfig) {
		if (view.type !== 'table') return;
		this._suppressPersist++;
		if (view.config?.sort) {
			const s = view.config.sort as { colId: string; dir: 'asc' | 'desc' };
			this.sortConfig = s.colId && s.dir ? s : null;
		} else {
			this.sortConfig = null;
		}
		if (view.config?.group) {
			const g = view.config.group as { colId: string; granularity?: 'month' | 'day' };
			this.groupConfig = g.colId ? g : null;
		} else {
			this.groupConfig = null;
		}
		if (view.config?.filter && Array.isArray(view.config.filter)) {
			const saved = view.config.filter as { colId: string; operator: string; value: string }[];
			this.filterConditions = saved.map((f) => ({
				id: crypto.randomUUID(),
				colId: f.colId,
				operator: f.operator as FilterCondition['operator'],
				value: f.value
			}));
		} else {
			this.filterConditions = [];
		}
		if (
			view.config?.widths &&
			typeof view.config.widths === 'object' &&
			!Array.isArray(view.config.widths)
		) {
			this.localWidths = { ...(view.config.widths as Record<string, number>) };
		} else {
			this.localWidths = {};
		}
		if (view.config?.colOrder && Array.isArray(view.config.colOrder)) {
			this.viewColOrder = view.config.colOrder as string[];
		} else {
			this.viewColOrder = null;
		}
		queueMicrotask(() => this._suppressPersist--);
	}

	persistViewConfig() {
		if (this._suppressPersist > 0) return;
		const view = get(viewsStore).find((v) => v.view_id === this.activeViewId);
		if (!view || view.type !== 'table') return;
		const newConfig = {
			...view.config,
			sort: this.sortConfig ?? undefined,
			group: this.groupConfig ?? undefined,
			filter:
				this.filterConditions.length > 0
					? this.filterConditions.map(({ colId, operator, value }) => ({ colId, operator, value }))
					: undefined,
			widths: Object.keys(this.localWidths).length > 0 ? { ...this.localWidths } : undefined,
			colOrder: this.viewColOrder ?? undefined
		};
		updateView(this.tableId, view.view_id, { config: newConfig }).catch(() => {});
	}

	// ─── View handlers ─────────────────────────────────────────────────────────

	handleViewChange(view: ViewConfig) {
		this.activeViewId = view.view_id;
		const url = new URL(window.location.href);
		url.searchParams.set('view', String(view.view_id));
		replaceState(url.toString(), {});
		this.applyViewConfig(view);
		const isImplicitTable = view.view_id === IMPLICIT_TABLE_VIEW.view_id;
		if (!isImplicitTable) patchSchema(this.tableId, { default_view: view.view_id }).catch(() => {});
	}

	async handleAddView(type: string, name: string) {
		error.set(null);
		const config = type === 'dashboard' ? { layout: [], blocks: {} } : {};
		try {
			const schema = await createView(this.tableId, { name, type, config });
			const created = schema.views.find((v) => v.name === name);
			if (created) this.activeViewId = created.view_id;
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to create view');
		}
	}

	async handleDeleteView(view: ViewConfig) {
		error.set(null);
		try {
			await deleteView(this.tableId, view.view_id);
			if (this.activeViewId === view.view_id) {
				const remaining = get(viewsStore);
				this.activeViewId = remaining[0]?.view_id ?? IMPLICIT_TABLE_VIEW.view_id;
			}
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to delete view');
		}
	}

	async handleRenameView(viewId: number, newName: string) {
		error.set(null);
		try {
			await updateView(this.tableId, viewId, { name: newName });
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to rename view');
		}
	}

	handleViewUpdate(updated: ViewConfig) {
		viewsStore.update((arr) => arr.map((v) => (v.view_id === updated.view_id ? updated : v)));
	}

	// ─── Export / Import ───────────────────────────────────────────────────────

	handleExportTemplate() {
		const tableId = this.tableId || 'table';
		triggerDownload(
			buildTemplateJSON(get(columns)),
			`${tableId}-template.json`,
			'application/json'
		);
	}

	async handleImportTemplate(file: File) {
		const tableId = this.tableId;
		const text = await file.text();
		const template = JSON.parse(text) as Array<{
			name: string;
			type: string;
			options?: ColumnOptions;
		}>;
		if (!Array.isArray(template)) throw new Error('Invalid template: expected an array');
		await Promise.all([...get(columns)].map((col) => deleteColumnApi(tableId, col.column_id)));
		for (const col of template) {
			await createColumn(tableId, {
				name: col.name,
				type: col.type as ColumnType,
				options: col.options ?? {}
			});
		}
		await fetchTable(tableId);
		this.showImportTemplateModal = false;
	}

	exportCSV() {
		const tableId = this.tableId || 'table';
		triggerDownload(buildCSV(get(columns), get(rows)), `${tableId}.csv`, 'text/csv');
	}

	exportJSON() {
		const tableId = this.tableId || 'table';
		triggerDownload(
			buildExportJSON(get(columns), get(rows)),
			`${tableId}-data.json`,
			'application/json'
		);
	}

	handleImportFile(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		const currentCols = get(columns);
		const reader = new FileReader();
		reader.onload = (ev) => {
			const text = ev.target?.result as string;
			const parsed = parseCSV(text);
			if (parsed.length < 1) return;
			const headers = parsed[0];
			this.importPreviewHeaders = headers;
			this.importPreviewRows = parsed.slice(1).map((cells) => {
				const obj: Record<string, string> = {};
				headers.forEach((h, i) => {
					obj[h] = cells[i] ?? '';
				});
				return obj;
			});
			this.importNewColumns = [];
			const newColValueSets: Record<string, Set<string>> = {};
			for (const h of headers) {
				const m = h.match(/^(.+)\{\{(\w+)\}\}$/);
				if (m) {
					const colName = m[1].trim();
					const colType = m[2].toLowerCase();
					if (!currentCols.some((c) => c.name === colName)) {
						newColValueSets[colName] = new Set<string>();
						this.importNewColumns = [...this.importNewColumns, { name: colName, type: colType }];
					}
				}
			}
			for (const cells of parsed.slice(1)) {
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
			this.importNewColumns = this.importNewColumns.map((nc) => ({
				...nc,
				values: newColValueSets[nc.name] ? [...newColValueSets[nc.name]] : []
			}));
			this.importError = null;
			this.showImportModal = true;
		};
		reader.readAsText(file);
		input.value = '';
	}

	async commitImport() {
		this.importingData = true;
		this.importError = null;
		const tableId = this.tableId;
		try {
			for (const nc of this.importNewColumns) {
				const choices =
					nc.values && nc.values.length > 0
						? nc.values.map((v) => ({ value: v, color: randomHex() }))
						: [];
				await createColumn(tableId, {
					name: nc.name,
					type: nc.type as ColumnType,
					options: { choices }
				});
			}
			await fetchTable(tableId);
			const currentCols = get(columns);
			const headerColName = (h: string) => {
				const m = h.match(/^(.+)\{\{(\w+)\}\}$/);
				return m ? m[1].trim() : h;
			};
			for (const previewRow of this.importPreviewRows) {
				const data: Record<string, unknown> = {};
				for (const h of this.importPreviewHeaders) {
					const col = currentCols.find((c) => c.name === headerColName(h));
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
			this.showImportModal = false;
			this.importPreviewRows = [];
			this.importPreviewHeaders = [];
			this.importNewColumns = [];
		} catch (e) {
			this.importError = e instanceof Error ? e.message : 'Import failed';
		} finally {
			this.importingData = false;
		}
	}

	// ─── Mouse event setup ─────────────────────────────────────────────────────

	setupMouseListeners(): () => void {
		const onResizeMove = (e: MouseEvent) => {
			if (!this.resizingColId) return;
			const delta = e.clientX - this.resizeStartX;
			this.localWidths = {
				...this.localWidths,
				[this.resizingColId]: Math.max(60, this.resizeStartWidth + delta)
			};
		};
		const onResizeUp = () => {
			if (this.resizingColId) this.resizingColId = null;
		};
		const onWindowClick = () => {
			this.colMenuId = null;
			this.contextMenu = null;
		};

		window.addEventListener('mousemove', onResizeMove);
		window.addEventListener('mouseup', onResizeUp);
		window.addEventListener('click', onWindowClick);
		return () => {
			window.removeEventListener('mousemove', onResizeMove);
			window.removeEventListener('mouseup', onResizeUp);
			window.removeEventListener('click', onWindowClick);
		};
	}
}

export const s = new TablePageStore();

// src/lib/components/table/table-page.svelte.ts
// Reactive UI state + handlers for the [table_id] page.
// Uses $state() runes — must be .svelte.ts.

import { SvelteSet } from 'svelte/reactivity';
import { get } from 'svelte/store';
import { page } from '$app/stores';
import { columns, views as viewsStore } from '$lib/stores/table_schema.store';
import { currentTableId, patchTableCache, tables } from '$lib/stores/table_schemas.store';
import { rows } from '$lib/stores/table_rows.store';
import { error, IMPLICIT_TABLE_VIEW } from '$lib/stores/tables.store';
import {
	createRow,
	createColumn,
	deleteColumn as deleteColumnApi,
	updateColumn,
	deleteRow as deleteRowApi,
	updateRow,
	fetchAllRows,
	fetchTable,
	patchSchema
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
	parseWidths,
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
	textCellState = $state<{ row: Row; col: Column } | null>(null);
	showAddColumn = $state(false);
	renamingColId = $state<string | null>(null);
	renameValue = $state('');
	editingCell = $state<{ rowId: number; colId: string } | null>(null);
	editValue = $state<string>('');
	tagsPopupCell = $state<{ rowId: number; colId: string } | null>(null);
	colMenuId = $state<string | null>(null);

	private _filterConditions = $state<FilterCondition[]>([]);
	get filterConditions() {
		return this._filterConditions;
	}
	set filterConditions(v) {
		this._filterConditions = v;
		this.schedulePersist();
	}

	showFilterPanel = $state(false);
	searchQuery = $state('');

	private _groupConfig = $state<{ colId: string; granularity?: 'month' | 'day' } | null>(null);
	get groupConfig() {
		return this._groupConfig;
	}
	set groupConfig(v) {
		this._groupConfig = v;
		this.schedulePersist();
	}
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
	private _persistTimer: ReturnType<typeof setTimeout> | null = null;

	private _viewColOrder = $state<string[] | null>(null);
	get viewColOrder() {
		return this._viewColOrder;
	}
	set viewColOrder(v) {
		this._viewColOrder = v;
		this.schedulePersist();
	}

	// Column resize: the drag preview is ephemeral local UI state (calling the
	// BE on every mousemove isn't reasonable), but the committed width is not
	// — it only becomes true once the BE call that follows mouseup resolves
	// and patches the store (see onResizeUp in setupMouseListeners below).
	resizingColId = $state<string | null>(null);
	resizeStartX = $state(0);
	resizeStartWidth = $state(0);
	dragWidth = $state(0);
	/** True from mouseup until the width PATCH resolves — drives a wait cursor
	 * so a resize doesn't look "done" before the store actually reflects it. */
	persistingWidth = $state(false);

	get tableId(): number {
		// The browser route has a name; controllers call the API by numeric id.
		return get(currentTableId) ?? Number(get(page).params.table_id ?? 0);
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
		this.textCellState = null;
		this.showAddColumn = false;
		this.renamingColId = null;
		this.renameValue = '';
		this.editingCell = null;
		this.editValue = '';
		this._cancellingEdit = false;
		this.tagsPopupCell = null;
		this.colMenuId = null;
		this._filterConditions = [];
		this.showFilterPanel = false;
		this.searchQuery = '';
		this._groupConfig = null;
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
		this._viewColOrder = null;
		this.resizingColId = null;
		this.dragWidth = 0;
		this.persistingWidth = false;
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

	async handleRefreshRows(tableId: number) {
		await fetchAllRows(tableId);
	}

	// ─── Cell edit handlers ────────────────────────────────────────────────────

	private _cancellingEdit = false;

	startEdit(rowId: number, col: Column, currentVal: unknown) {
		this._cancellingEdit = false;
		this.editingCell = { rowId, colId: col.column_id };
		this.editValue = currentVal === null || currentVal === undefined ? '' : String(currentVal);
	}

	/** Escape: discard the in-progress edit instead of committing it on the
	 * blur that unmounting the input triggers (same end state as clicking
	 * away — unfocused, not editing — but without writing editValue). */
	cancelEdit() {
		this._cancellingEdit = true;
		this.editingCell = null;
		this.editValue = '';
	}

	async commitEdit(rowId: number, col: Column) {
		if (this._cancellingEdit) {
			this._cancellingEdit = false;
			return;
		}
		if (!this.editingCell) return;
		this.editingCell = null;
		const row = get(rows).find((r) => r.row_id === rowId);
		if (!row) return;
		const newData = applyEditToRowData(row.row_data, col.column_id, this.editValue, col.type);
		error.set(null);
		try {
			await updateRow(this.tableId, row.row_id, {
				row_data: { [col.column_id]: newData[col.column_id] }
			});
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
			await updateRow(this.tableId, row.row_id, {
				row_data: { [col.column_id]: newData[col.column_id] }
			});
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update cell');
		}
	}

	async removeTag(rowId: number, col: Column, tag: string) {
		const row = get(rows).find((r) => r.row_id === rowId);
		if (!row) return;
		const newData = removeTagFromRowData(row.row_data, col.column_id, tag);
		try {
			await updateRow(this.tableId, row.row_id, {
				row_data: { [col.column_id]: newData[col.column_id] }
			});
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
			await updateRow(this.tableId, row.row_id, {
				row_data: { [col.column_id]: newData[col.column_id] }
			});
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update tags');
		}
	}

	// ─── Column handlers ───────────────────────────────────────────────────────

	async handleAddColumn(name: string, type: string, options?: ColumnOptions) {
		const tableId = this.tableId;
		this.addingColumn = true;
		error.set(null);
		try {
			await createColumn(tableId, { name, type: type as ColumnType, options });
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

	/** currentWidth is the width currently on screen (persisted width or the
	 * column's own default) — the caller resolves it, since that value is
	 * itself derived from the store, not something this class tracks. */
	handleResizeStart(e: MouseEvent, col: Column, currentWidth: number) {
		e.preventDefault();
		e.stopPropagation();
		this.resizingColId = col.column_id;
		this.resizeStartX = e.clientX;
		this.resizeStartWidth = currentWidth;
		this.dragWidth = currentWidth;
	}

	// ─── UI helpers ────────────────────────────────────────────────────────────

	addFilterCondition() {
		const firstCol = get(columns)[0];
		this.filterConditions = [
			...this.filterConditions,
			{ id: crypto.randomUUID(), colId: firstCol?.column_id ?? '', operator: 'contains', value: '' }
		];
	}

	// Filter fields are edited in place via `bind:value` on the condition
	// objects, which mutates the array elements without re-assigning the
	// array — so the `filterConditions` setter never runs. Call this on
	// every field edit (colId/operator/value) to persist the change.
	onFilterConditionEdited() {
		this.schedulePersist();
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

	/**
	 * group/filter/colOrder only — sort and widths are no longer mirrored
	 * into local state at all. They're $derived straight from the active
	 * view's config in +page.svelte (parseSortConfig/parseWidths), so BE
	 * response -> store -> derived is the only path that ever sets them.
	 */
	applyViewConfig(view: ViewConfig) {
		if (view.type !== 'table') return;
		// The implicit Schema tab (view_id 0) has no table_views row of its
		// own — its config lives on the table schema instead.
		const config: Record<string, unknown> =
			(view.view_id === IMPLICIT_TABLE_VIEW.view_id
				? get(tables).find((t) => t.table_id === this.tableId)?.view_config
				: view.config) ?? {};
		if (config.group) {
			const g = config.group as { colId: string; granularity?: 'month' | 'day' };
			this._groupConfig = g.colId ? g : null;
		} else {
			this._groupConfig = null;
		}
		if (config.filter && Array.isArray(config.filter)) {
			const saved = config.filter as { colId: string; operator: string; value: string }[];
			this._filterConditions = saved.map((f) => ({
				id: crypto.randomUUID(),
				colId: f.colId,
				operator: f.operator as FilterCondition['operator'],
				value: f.value
			}));
		} else {
			this._filterConditions = [];
		}
		// Column order for the implicit tab is the physical `columns` array
		// order (reordered via col_order on the table schema, see
		// handleDragReorderColumns) — never view_config, so colOrder stays
		// scoped to view.config here.
		if (view.config?.colOrder && Array.isArray(view.config.colOrder)) {
			this._viewColOrder = view.config.colOrder as string[];
		} else {
			this._viewColOrder = null;
		}
	}

	/** The active view's config as it currently stands in the store — read
	 * fresh (never cached locally) so a patch always merges onto the latest
	 * server truth instead of a possibly-stale local copy. */
	private currentViewConfig(): Record<string, unknown> {
		if (this.activeViewId === IMPLICIT_TABLE_VIEW.view_id) {
			return get(tables).find((t) => t.table_id === this.tableId)?.view_config ?? {};
		}
		return get(viewsStore).find((v) => v.view_id === this.activeViewId)?.config ?? {};
	}

	/**
	 * The one write path for view config: merge `patch` onto the current
	 * server config and PATCH/PUT it. The call's own response triggers
	 * applySchema() (in backend/tables.ts + backend/views.ts), which writes
	 * the `tables` store — every $derived reading that store (sortConfig,
	 * persistedWidths, viewsStore, ...) updates from there, not from this
	 * method's caller. Errors surface through the shared `error` store.
	 */
	private async persistViewConfigPatch(patch: Record<string, unknown>): Promise<void> {
		try {
			if (this.activeViewId === IMPLICIT_TABLE_VIEW.view_id) {
				const newConfig = { ...this.currentViewConfig(), ...patch };
				await patchSchema(this.tableId, { view_config: newConfig });
				return;
			}
			const view = get(viewsStore).find((v) => v.view_id === this.activeViewId);
			if (!view || view.type !== 'table') return;
			const newConfig = { ...view.config, ...patch };
			await updateView(this.tableId, view.view_id, { config: newConfig });
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update view');
		}
	}

	/** Sort click: call BE, await it, done — no local optimistic mirror. The
	 * $derived sortConfig in +page.svelte picks it up once the store updates. */
	async changeSort(config: { colId: string; dir: 'asc' | 'desc' } | null): Promise<void> {
		await this.persistViewConfigPatch({ sort: config ?? undefined });
	}

	private schedulePersist() {
		if (this._suppressPersist > 0 || this.resizingColId) return;
		if (this._persistTimer) clearTimeout(this._persistTimer);
		this._persistTimer = setTimeout(() => this.persistViewConfig(), 100);
	}

	/** group/filter/colOrder still use the debounced local-optimistic path —
	 * typing into a filter value or dragging a column reorder fires this on
	 * every keystroke/step, and round-tripping the BE that often isn't
	 * reasonable. Sort and widths were pulled out of this (see changeSort
	 * and onResizeUp) because they're discrete, infrequent actions. */
	persistViewConfig() {
		if (this._suppressPersist > 0) return;
		const patch: Record<string, unknown> = {
			group: this.groupConfig ?? undefined,
			filter:
				this.filterConditions.length > 0
					? this.filterConditions.map(({ colId, operator, value }) => ({ colId, operator, value }))
					: undefined
		};
		// colOrder is per-view and only meaningful for real views — the
		// implicit tab's column order is the physical col_order mechanism
		// (see handleDragReorderColumns), never view_config.
		if (this.activeViewId !== IMPLICIT_TABLE_VIEW.view_id) {
			patch.colOrder = this.viewColOrder ?? undefined;
		}
		this.persistViewConfigPatch(patch);
	}

	// ─── View handlers ─────────────────────────────────────────────────────────

	handleViewChange(view: ViewConfig) {
		this.activeViewId = view.view_id;
		const url = new URL(window.location.href);
		url.searchParams.set('view', String(view.view_id));
		history.replaceState(history.state, '', url.toString());
		this.applyViewConfig(view);
		patchSchema(this.tableId, { default_view: view.view_id }).catch(() => {});
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
		const tid = get(currentTableId);
		if (!tid) return;
		patchTableCache(tid, {
			views: get(viewsStore).map((v) => (v.view_id === updated.view_id ? updated : v))
		});
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

	async exportCSV() {
		const tableId = this.tableId || 'table';
		try {
			const allRows = await fetchAllRows(this.tableId);
			triggerDownload(buildCSV(get(columns), allRows), `${tableId}.csv`, 'text/csv');
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to export CSV');
		}
	}

	async exportJSON() {
		const tableId = this.tableId || 'table';
		try {
			const allRows = await fetchAllRows(this.tableId);
			triggerDownload(
				buildExportJSON(get(columns), allRows),
				`${tableId}-data.json`,
				'application/json'
			);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to export JSON');
		}
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
			// Ephemeral drag preview only — not persisted, not read by
			// anything outside the live drag (+page.svelte overlays this on
			// the store's widths only while resizingColId is set).
			this.dragWidth = Math.max(60, this.resizeStartWidth + delta);
		};
		const onResizeUp = () => {
			if (!this.resizingColId) return;
			const colId = this.resizingColId;
			const width = this.dragWidth;
			const startWidth = this.resizeStartWidth;
			this.resizingColId = null;
			if (width === startWidth) return;
			this.persistingWidth = true;
			const widths = { ...parseWidths(this.currentViewConfig()), [colId]: width };
			this.persistViewConfigPatch({ widths }).finally(() => {
				this.persistingWidth = false;
			});
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

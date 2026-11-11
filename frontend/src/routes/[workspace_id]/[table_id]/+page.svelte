<!-- routes/[workspace_id]/[table_id]/+page.svelte -->

<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { get } from 'svelte/store';

	// Model (SSOT stores)
	import {
		columns,
		defaultView,
		views as viewsStore,
		viewConfig as tableViewConfig
	} from '$lib/stores/table_schema.store';
	import { rows } from '$lib/stores/table_rows.store';

	// Controller
	import { patchSchema, fetchRows, fetchAllRows, ROW_PAGE_SIZE } from '$lib/backend/tables';
	import {
		currentWorkspaceId,
		currentTableId,
		patchTableCache
	} from '$lib/stores/table_schemas.store';
	import { error, IMPLICIT_TABLE_VIEW } from '$lib/stores/tables.store';
	import { s } from '$lib/components/table/table-page.svelte';

	// Utils
	import {
		applyFilters,
		sortRows,
		buildGroupedRows,
		buildRenderItems,
		buildSortedColumns,
		parseSortConfig,
		parseWidths
	} from '$lib/components/table/table.utils';

	// Components
	import TableToolbar from '$lib/components/table/TableToolbar.svelte';
	import TableGrid from '$lib/components/table/TableGrid.svelte';
	import { T } from '$lib/UI/theme.svelte';
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
	import TextCellEditor from '$lib/components/table/TextCellEditor.svelte';
	import DashboardView from '$lib/components/dashboard/DashboardView.svelte';
	import type { DashboardView as DashboardViewType } from '$lib/types/dashboard';
	import WorkflowView from '$lib/components/workflow/WorkflowView.svelte';

	// --- Page data from +page.ts load (stores already populated) ---

	let { data } = $props();

	// --- Derived (from SSOT stores + view state) ---

	const allViews = $derived(
		$viewsStore.some((v) => v.view_id === IMPLICIT_TABLE_VIEW.view_id)
			? $viewsStore
			: [IMPLICIT_TABLE_VIEW, ...$viewsStore]
	);

	const activeView = $derived(
		allViews.find((v) => v.view_id === s.activeViewId) ?? allViews[0] ?? IMPLICIT_TABLE_VIEW
	);

	// Sort/widths: BE response -> tables store (applySchema) -> this derived
	// -> render. No local mirror — the implicit Schema tab's config lives on
	// the table itself ($tableViewConfig), a real view's on its own row.
	const activeViewConfig = $derived(
		s.activeViewId === IMPLICIT_TABLE_VIEW.view_id &&
			!$viewsStore.some((v) => v.view_id === IMPLICIT_TABLE_VIEW.view_id)
			? $tableViewConfig
			: (activeView.config ?? {})
	);
	const sortConfig = $derived(parseSortConfig(activeViewConfig));
	const persistedWidths = $derived(parseWidths(activeViewConfig));
	// While actively dragging, overlay the live (unsaved) preview for just
	// the column being resized — everything else still reads the store.
	const displayWidths = $derived(
		s.resizingColId ? { ...persistedWidths, [s.resizingColId]: s.dragWidth } : persistedWidths
	);
	function colWidth(col: { column_id: string; options?: { width?: number } }): number {
		return displayWidths[col.column_id] ?? col.options?.width ?? 150;
	}

	const sortedColumns = $derived(buildSortedColumns($columns, s.viewColOrder));

	let rowPage = $state(1);
	let rowHasMore = $state(false);
	let rowMode = $state<'paged' | 'all'>('paged');
	let requestedMode = $state<'paged' | 'all' | null>(null);
	let rowLoading = $state(false);
	let rowRequestId = 0;
	const needsAllRows = $derived(
		(activeView.type === 'table' &&
			(sortConfig !== null ||
				s.groupConfig !== null ||
				s.filterConditions.length > 0 ||
				s.searchQuery.trim().length > 0)) ||
			activeView.type === 'kanban' ||
			activeView.type === 'timeline' ||
			activeView.type === 'workflow'
	);

	const filteredRows = $derived(applyFilters($rows, s.filterConditions, s.searchQuery));
	const sortedRows = $derived(sortRows(filteredRows, sortConfig, $columns));

	const tableMinWidth = $derived(
		48 + sortedColumns.reduce((sum, col) => sum + colWidth(col), 0) + 40 + 40
	);

	const visibleRows = $derived(
		activeView.type === 'table' && rowMode === 'all'
			? sortedRows.slice((rowPage - 1) * ROW_PAGE_SIZE, rowPage * ROW_PAGE_SIZE)
			: sortedRows
	);
	const groupedRows = $derived(buildGroupedRows(visibleRows, s.groupConfig, $columns, sortConfig));
	const renderItems = $derived(buildRenderItems(visibleRows, groupedRows, s.collapsedGroups));
	const canGoNext = $derived(
		rowMode === 'all' ? rowPage * ROW_PAGE_SIZE < sortedRows.length : rowHasMore
	);

	const tableId = $derived($currentTableId ?? 0);
	const wsId = $derived($currentWorkspaceId ?? '');

	let loading = $state(true);

	async function loadRowPage(targetPage: number) {
		const requestId = ++rowRequestId;
		rowLoading = true;
		requestedMode = 'paged';
		try {
			const result = await fetchRows(tableId, targetPage, ROW_PAGE_SIZE);
			if (requestId !== rowRequestId) return;
			if (targetPage > 1 && result.items.length === 0) {
				await loadRowPage(targetPage - 1);
				return;
			}
			rowPage = targetPage;
			rowHasMore = result.has_more;
			rowMode = 'paged';
			requestedMode = null;
		} catch (e) {
			if (requestId === rowRequestId)
				error.set(e instanceof Error ? e.message : 'Failed to load rows');
		} finally {
			if (requestId === rowRequestId) rowLoading = false;
		}
	}

	async function loadFullRows() {
		// Page 1 is complete when the API reports no next page.
		// A filter or search can then use the current rows without blanking the grid.
		if (rowMode === 'paged' && requestedMode === null && rowPage === 1 && !rowHasMore) {
			rowMode = 'all';
			return;
		}
		const requestId = ++rowRequestId;
		rowLoading = true;
		requestedMode = 'all';
		try {
			await fetchAllRows(tableId);
			if (requestId !== rowRequestId) return;
			rowPage = 1;
			rowMode = 'all';
			requestedMode = null;
		} catch (e) {
			if (requestId === rowRequestId)
				error.set(e instanceof Error ? e.message : 'Failed to load rows');
		} finally {
			if (requestId === rowRequestId) rowLoading = false;
		}
	}

	function changeRowPage(delta: number) {
		if (rowLoading || rowPage + delta < 1 || (delta > 0 && !canGoNext)) return;
		if (rowMode === 'all') rowPage += delta;
		else void loadRowPage(rowPage + delta);
	}

	async function handleAddRow(editColId?: string) {
		await s.handleAddRow(editColId);
		if (rowMode === 'paged') await loadRowPage(1);
		else rowPage = 1;
	}

	async function handleDeleteRow(rowId: number) {
		await s.handleDeleteRow(rowId);
		if (rowMode === 'paged') await loadRowPage(rowPage);
	}

	async function handleDuplicateRow(rowId: number) {
		await s.handleDuplicateRow(rowId);
		if (rowMode === 'paged') await loadRowPage(1);
		else rowPage = 1;
	}

	async function handleOpenTextCell(
		row: import('$lib/types/table').Row,
		col: import('$lib/types/table').Column
	) {
		s.textCellState = { row, col };
	}

	$effect(() => {
		const { tableParam, urlViewId, cached, resolvedWsId, viewsP, rowsP, tableP } = data;

		untrack(() => {
			s.reset();
			error.set('');
			loading = true;
			rowRequestId++;
			rowPage = 1;
			rowHasMore = false;
			rowMode = 'paged';
			requestedMode = null;
			rowLoading = false;
		});

		if (cached) {
			untrack(() => {
				currentTableId.set(cached.table_id);
				currentWorkspaceId.set(cached.workspace_id);
			});
		}

		let cancelled = false;
		(async () => {
			try {
				if (!viewsP || !rowsP) return;
				const [viewsList, firstRows] = await Promise.all([
					viewsP,
					rowsP,
					...(tableP ? [tableP] : [])
				]);
				if (cancelled) return;

				let initialNeedsAll = false;
				untrack(() => {
					rowHasMore = firstRows.has_more;
					if (!cached) {
						if (resolvedWsId) currentWorkspaceId.set(resolvedWsId);
						currentTableId.set(tableParam);
					}

					patchTableCache(tableParam, { views: viewsList });

					const loadedViews = viewsList;
					const hasUserTable = loadedViews.some((v) => v.view_id === IMPLICIT_TABLE_VIEW.view_id);
					const candidates = hasUserTable ? loadedViews : [IMPLICIT_TABLE_VIEW, ...loadedViews];
					const dv = get(defaultView);

					let targetViewId: number;
					if (!isNaN(urlViewId) && candidates.some((v) => v.view_id === urlViewId)) {
						targetViewId = urlViewId;
					} else if (dv !== null && candidates.some((v) => v.view_id === dv)) {
						targetViewId = dv;
					} else if (candidates.length > 0) {
						targetViewId = candidates[0].view_id;
					} else {
						targetViewId = 0;
					}

					s.activeViewId = targetViewId;
					const initView = candidates.find((v) => v.view_id === targetViewId);
					if (initView) s.applyViewConfig(initView);
					const config =
						initView?.view_id === IMPLICIT_TABLE_VIEW.view_id
							? get(tableViewConfig)
							: initView?.config;
					initialNeedsAll =
						initView?.type === 'kanban' ||
						initView?.type === 'timeline' ||
						initView?.type === 'workflow' ||
						(initView?.type === 'table' &&
							(s.filterConditions.length > 0 ||
								s.groupConfig !== null ||
								parseSortConfig(config) !== null));
				});
				if (initialNeedsAll) {
					if (firstRows.has_more) await fetchAllRows(tableParam);
					if (cancelled) return;
					untrack(() => {
						rowMode = 'all';
					});
				}
				untrack(() => {
					loading = false;
				});
			} catch (e) {
				if (cancelled) return;
				untrack(() => {
					error.set(e instanceof Error ? e.message : 'Failed to load table');
					loading = false;
				});
			}
		})();

		return () => {
			cancelled = true;
		};
	});

	$effect(() => {
		if (loading || !tableId) return;
		const desiredMode = needsAllRows ? 'all' : 'paged';
		if (desiredMode === requestedMode) return;
		if (desiredMode === rowMode && requestedMode === null) return;
		// Keep the full cache when clearing a filter or search.
		if (desiredMode === 'paged' && rowMode === 'all' && requestedMode === null) return;
		untrack(() => {
			if (desiredMode === 'all') void loadFullRows();
			else void loadRowPage(1);
		});
	});

	$effect(() => {
		if (rowMode !== 'all' || activeView.type !== 'table') return;
		const lastPage = Math.max(1, Math.ceil(sortedRows.length / ROW_PAGE_SIZE));
		if (rowPage > lastPage) rowPage = lastPage;
	});

	onMount(() => s.setupMouseListeners());

	// --- Page-specific handlers (not yet in store class) ---

	async function handleDragReorderColumns(fromId: string, toId: string) {
		const ordered = [...$columns]
			.sort((a, b) => {
				if (s.viewColOrder && s.viewColOrder.length > 0) {
					const ai = s.viewColOrder.indexOf(a.column_id);
					const bi = s.viewColOrder.indexOf(b.column_id);
					return (ai === -1 ? 9999 : ai) - (bi === -1 ? 9999 : bi);
				}
				return 0;
			})
			.map((c) => c.column_id);
		const fromIdx = ordered.indexOf(fromId);
		const toIdx = ordered.indexOf(toId);
		if (fromIdx === -1 || toIdx === -1 || fromIdx === toIdx) return;
		ordered.splice(fromIdx, 1);
		ordered.splice(toIdx, 0, fromId);
		s.viewColOrder = ordered;
		const persisted = await s.persistColumnOrder(ordered);
		// A table's col_order comes back in the schema, so the store already
		// carries it. A view's order lives in that view's config, which nothing
		// re-applies here — keep the local order for it. On failure drop the
		// optimistic order so the grid shows what actually persisted.
		if (persisted !== 'view') s.viewColOrder = null;
	}

	async function handleReorderViews(fromId: number, toId: number) {
		const userViewIds = $viewsStore.map((v) => v.view_id);
		const fromIdx = userViewIds.indexOf(fromId);
		if (fromIdx === -1) return;
		const toIdx = userViewIds.indexOf(toId);
		if (toIdx === -1) return;
		const reordered = [...userViewIds];
		reordered.splice(fromIdx, 1);
		reordered.splice(toIdx, 0, fromId);
		await patchSchema(s.tableId, { view_order: reordered }).catch(() => {});
	}
</script>

<div
	class="flex h-full flex-col bg-white {s.resizingColId
		? 'cursor-col-resize select-none'
		: s.persistingWidth
			? 'cursor-wait'
			: ''}"
	data-table-loaded={!loading}
>
	{#if $error}
		<div class="mx-4 mt-2 rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">{$error}</div>
	{/if}

	{#if loading}
		<div
			class="flex flex-1 items-center justify-center gap-2 text-sm text-gray-400"
			data-testid="table-loading"
		>
			<svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"
				></circle>
				<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path>
			</svg>
			Loading…
		</div>
	{:else}
		<ViewSwitcher
			views={allViews}
			activeViewId={activeView.view_id}
			onViewChange={(v) => s.handleViewChange(v)}
			onAddView={(type, name) => s.handleAddView(type, name)}
			onDeleteView={(v) => s.handleDeleteView(v)}
			onRenameView={(id, name) => s.handleRenameView(id, name)}
			isRenameable={(v) => $viewsStore.some((uv) => uv.view_id === v.view_id)}
			onReorderViews={handleReorderViews}
		/>

		{#if rowLoading && activeView.type !== 'table'}
			<div class="flex flex-1 items-center justify-center text-sm {T.muted}">Loading rows...</div>
		{:else if activeView.type === 'table'}
			<TableToolbar
				columns={$columns}
				{sortConfig}
				groupConfig={s.groupConfig}
				filterConditions={s.filterConditions}
				showFilterPanel={s.showFilterPanel}
				searchQuery={s.searchQuery}
				onSortChange={(c) => s.changeSort(c)}
				onGroupChange={(c) => (s.groupConfig = c)}
				onShowFilterPanelChange={(v) => (s.showFilterPanel = v)}
				onSearchQueryChange={(q) => (s.searchQuery = q)}
				onExportTemplate={() => s.handleExportTemplate()}
				onShowImportTemplate={() => (s.showImportTemplateModal = true)}
				onExportCSV={() => s.exportCSV()}
				onExportJSON={() => s.exportJSON()}
				onImportFile={(e) => s.handleImportFile(e)}
				onAddFilterCondition={() => s.addFilterCondition()}
				onRemoveFilterCondition={(id) => s.removeFilterCondition(id)}
				onClearAllFilters={() => (s.filterConditions = [])}
				onFilterChange={() => s.onFilterConditionEdited()}
			/>

			<TableGrid
				{sortedColumns}
				{renderItems}
				loading={rowLoading}
				{tableMinWidth}
				addingRow={s.addingRow}
				addingColumn={s.addingColumn}
				scrollToRowId={s.scrollToRowId}
				scrollToColTrigger={s.scrollToColTrigger}
				deletingRowId={s.deletingRowId}
				rowsWithDocs={s.rowsWithDocs}
				editingCell={s.editingCell}
				editValue={s.editValue}
				renamingColId={s.renamingColId}
				renameValue={s.renameValue}
				colMenuId={s.colMenuId}
				tagsPopupCell={s.tagsPopupCell}
				{sortConfig}
				collapsedGroups={s.collapsedGroups}
				localWidths={displayWidths}
				onStartEdit={(rowId, col, val) => s.startEdit(rowId, col, val)}
				onCommitEdit={(rowId, col) => s.commitEdit(rowId, col)}
				onCancelEdit={() => s.cancelEdit()}
				onEditValueChange={(v) => (s.editValue = v)}
				onToggleCheckbox={(rowId, col) => s.toggleCheckbox(rowId, col)}
				onRemoveTag={(rowId, col, tag) => s.removeTag(rowId, col, tag)}
				onAddTag={(rowId, col, tag) => s.addTag(rowId, col, tag)}
				onTagsPopupChange={(c) => (s.tagsPopupCell = c)}
				onDeleteRow={(id) => handleDeleteRow(id)}
				onOpenExpand={(row) => s.openExpand(row)}
				onOpenContextMenu={(e, type, id) => s.openContextMenu(e, type, id)}
				onStartRename={(id, name) => s.startRename(id, name)}
				onCommitRename={(id) => s.commitRename(id)}
				onRenameValueChange={(v) => (s.renameValue = v)}
				onRenamingColIdChange={(id) => (s.renamingColId = id)}
				onColMenuChange={(id) => (s.colMenuId = id)}
				onSortChange={(c) => s.changeSort(c)}
				onFilterAdd={(id) => s.addFilterForColumn(id)}
				onShowFilterPanel={() => (s.showFilterPanel = true)}
				onDeleteColumn={(id) => s.handleDeleteColumn(id)}
				onDragReorderColumns={handleDragReorderColumns}
				onResizeStart={(e, col) => s.handleResizeStart(e, col, colWidth(col))}
				onShowAddColumn={() => (s.showAddColumn = true)}
				onAddRow={() => handleAddRow()}
				onAddRowAndEdit={(colId) => handleAddRow(colId)}
				onAddRowInGroup={(key, col) => s.handleAddRowInGroup(key, col)}
				onToggleCollapseGroup={(key) => s.toggleCollapseGroup(key)}
				onManageOptions={(col) => (s.managingOptionsCol = col)}
				onOpenTextCell={(row, col) => void handleOpenTextCell(row, col)}
			/>
			<div
				class="flex items-center justify-end gap-3 border-t px-4 py-2 text-sm {T.cardBg} {T.border}"
				data-testid="table-pagination"
				data-row-page-loading={rowLoading}
			>
				<span class={T.muted}>
					Page {rowPage}{#if rowMode === 'all'}
						of {Math.max(1, Math.ceil(sortedRows.length / ROW_PAGE_SIZE))}{/if}
				</span>
				<button
					type="button"
					class="rounded border px-3 py-1 disabled:opacity-40 {T.border} {T.body}"
					disabled={rowLoading || rowPage <= 1}
					onclick={() => changeRowPage(-1)}>Previous</button
				>
				<button
					type="button"
					class="rounded border px-3 py-1 disabled:opacity-40 {T.border} {T.body}"
					disabled={rowLoading || !canGoNext}
					onclick={() => changeRowPage(1)}>Next</button
				>
			</div>
		{:else if activeView.type === 'kanban'}
			<KanbanBoard
				{tableId}
				columns={$columns}
				rows={$rows}
				viewConfig={activeView}
				onOpenExpand={(row) => s.openExpand(row)}
				onRowsRefresh={() => fetchAllRows(tableId)}
				onAddRow={(data) => s.openCreateTicket(data)}
			/>
		{:else if activeView.type === 'timeline'}
			<TimelineView
				{tableId}
				columns={$columns}
				rows={$rows}
				viewConfig={activeView}
				onOpenExpand={(row) => s.openExpand(row)}
				onRowsRefresh={() => fetchAllRows(tableId)}
				onAddRow={(data) => s.openCreateTicket(data)}
			/>
		{:else if activeView.type === 'dashboard'}
			<DashboardView
				view={activeView as unknown as DashboardViewType & { view_id: number }}
				workspaceId={wsId}
				{tableId}
			/>
		{:else if activeView.type === 'workflow'}
			<WorkflowView
				{tableId}
				columns={$columns}
				rows={$rows}
				onOpenExpand={(row) => s.openExpand(row)}
			/>
		{/if}
	{/if}
</div>

<!-- Overlays -->
{#if s.contextMenu}
	<ContextMenu
		contextMenu={s.contextMenu}
		columns={$columns}
		rows={$rows}
		{sortConfig}
		filterConditions={s.filterConditions}
		onClose={() => (s.contextMenu = null)}
		onExpandRow={(row) => s.openExpand(row)}
		onDuplicateRow={(id) => handleDuplicateRow(id)}
		onDeleteRow={(id) => handleDeleteRow(id)}
		onRenameColumn={(id, name) => s.startRename(id, name)}
		onSortChange={(c) => s.changeSort(c)}
		onAddFilter={(id) => s.addFilterForColumn(id)}
		onDeleteColumn={(id) => s.handleDeleteColumn(id)}
	/>
{/if}

<AddColumnModal
	show={s.showAddColumn}
	onClose={() => (s.showAddColumn = false)}
	onAdd={(name, type, options) => s.handleAddColumn(name, type, options)}
	pending={s.addingColumn}
/>

{#if s.expandedRow}
	<RowExpandPanel
		row={s.expandedRow}
		columns={$columns}
		onClose={() => (s.expandedRow = null)}
		onUpdateRow={(id, data) => s.handleUpdateRow(id, data)}
		{tableId}
		workspaceId={wsId}
	/>
{/if}

{#if s.textCellState}
	{#key `${s.textCellState.row.row_id}:${s.textCellState.col.column_id}`}
		<TextCellEditor
			row={s.textCellState.row}
			column={s.textCellState.col}
			{tableId}
			onClose={() => (s.textCellState = null)}
		/>
	{/key}
{/if}

<ImportTemplateModal
	show={s.showImportTemplateModal}
	onClose={() => (s.showImportTemplateModal = false)}
	onImport={(file) => s.handleImportTemplate(file)}
/>

<ImportPreviewModal
	show={s.showImportModal}
	headers={s.importPreviewHeaders}
	previewRows={s.importPreviewRows}
	newColumns={s.importNewColumns}
	importing={s.importingData}
	error={s.importError}
	onClose={() => (s.showImportModal = false)}
	onConfirm={() => s.commitImport()}
/>

{#if s.managingOptionsCol}
	<ManageOptionsModal
		col={s.managingOptionsCol}
		onClose={() => (s.managingOptionsCol = null)}
		onSave={(id, choices) => s.handleSaveOptions(id, choices)}
	/>
{/if}

{#if s.showCreateTicket}
	<CreateTicketModal
		columns={$columns}
		initialData={s.createTicketInitialData}
		onClose={() => (s.showCreateTicket = false)}
		onSubmit={(data) => s.handleCreateTicket(data)}
	/>
{/if}

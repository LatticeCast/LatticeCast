<!-- routes/[workspace_id]/[table_id]/+page.svelte -->

<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { get } from 'svelte/store';

	// Model (SSOT stores)
	import { columns, defaultView, views as viewsStore } from '$lib/stores/table_schema.store';
	import { rows } from '$lib/stores/table_rows.store';

	// Controller
	import { patchSchema, fetchRows } from '$lib/backend/tables';
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
		buildSortedColumns
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
	import DocCellEditor from '$lib/components/table/DocCellEditor.svelte';
	import DashboardView from '$lib/components/dashboard/DashboardView.svelte';
	import type { DashboardView as DashboardViewType } from '$lib/types/dashboard';
	import WorkflowView from '$lib/components/workflow/WorkflowView.svelte';

	// --- Page data from +page.ts load (stores already populated) ---

	let { data } = $props();

	// --- Derived (from SSOT stores + view state) ---

	const sortedColumns = $derived(buildSortedColumns($columns, s.viewColOrder));

	const filteredRows = $derived(applyFilters($rows, s.filterConditions, s.searchQuery));
	const sortedRows = $derived(sortRows(filteredRows, s.sortConfig, $columns));

	const tableMinWidth = $derived(
		48 + sortedColumns.reduce((sum, col) => sum + s.getColWidth(col), 0) + 40 + 40
	);

	const allViews = $derived(
		$viewsStore.some((v) => v.view_id === IMPLICIT_TABLE_VIEW.view_id)
			? $viewsStore
			: [IMPLICIT_TABLE_VIEW, ...$viewsStore]
	);

	const activeView = $derived(
		allViews.find((v) => v.view_id === s.activeViewId) ?? allViews[0] ?? IMPLICIT_TABLE_VIEW
	);

	const groupedRows = $derived(
		buildGroupedRows(filteredRows, s.groupConfig, $columns, s.sortConfig)
	);

	const renderItems = $derived(buildRenderItems(sortedRows, groupedRows, s.collapsedGroups));

	const tableId = $derived($currentTableId ?? '');
	const wsId = $derived($currentWorkspaceId ?? '');

	let loading = $state(true);

	$effect(() => {
		const { tableParam, urlViewId, cached, resolvedWsId, viewsP, rowsP, tableP } = data;

		untrack(() => {
			s.reset();
			error.set('');
			loading = true;
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
				const [viewsList] = await Promise.all([viewsP, rowsP, ...(tableP ? [tableP] : [])]);
				if (cancelled) return;

				untrack(() => {
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

					s.loadDocFlags(tableParam).catch(() => {});
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
		const isImplicitTable =
			s.activeViewId === IMPLICIT_TABLE_VIEW.view_id &&
			!$viewsStore.some((v) => v.view_id === IMPLICIT_TABLE_VIEW.view_id);
		if (isImplicitTable) {
			try {
				await patchSchema(s.tableId, { col_order: ordered });
				s.viewColOrder = null;
			} catch (e) {
				error.set(e instanceof Error ? e.message : 'Failed to save column order');
			}
		}
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
	class="flex h-full flex-col bg-white {s.resizingColId ? 'cursor-col-resize select-none' : ''}"
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

		{#if activeView.type === 'table'}
			<TableToolbar
				columns={$columns}
				sortConfig={s.sortConfig}
				groupConfig={s.groupConfig}
				filterConditions={s.filterConditions}
				showFilterPanel={s.showFilterPanel}
				searchQuery={s.searchQuery}
				onSortChange={(c) => (s.sortConfig = c)}
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
				loading={false}
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
				sortConfig={s.sortConfig}
				collapsedGroups={s.collapsedGroups}
				localWidths={s.localWidths}
				onStartEdit={(rowId, col, val) => s.startEdit(rowId, col, val)}
				onCommitEdit={(rowId, col) => s.commitEdit(rowId, col)}
				onEditValueChange={(v) => (s.editValue = v)}
				onEditingCellChange={(c) => (s.editingCell = c)}
				onToggleCheckbox={(rowId, col) => s.toggleCheckbox(rowId, col)}
				onRemoveTag={(rowId, col, tag) => s.removeTag(rowId, col, tag)}
				onAddTag={(rowId, col, tag) => s.addTag(rowId, col, tag)}
				onTagsPopupChange={(c) => (s.tagsPopupCell = c)}
				onDeleteRow={(id) => s.handleDeleteRow(id)}
				onOpenExpand={(row) => s.openExpand(row)}
				onOpenContextMenu={(e, type, id) => s.openContextMenu(e, type, id)}
				onStartRename={(id, name) => s.startRename(id, name)}
				onCommitRename={(id) => s.commitRename(id)}
				onRenameValueChange={(v) => (s.renameValue = v)}
				onRenamingColIdChange={(id) => (s.renamingColId = id)}
				onColMenuChange={(id) => (s.colMenuId = id)}
				onSortChange={(c) => (s.sortConfig = c)}
				onFilterAdd={(id) => s.addFilterForColumn(id)}
				onShowFilterPanel={() => (s.showFilterPanel = true)}
				onDeleteColumn={(id) => s.handleDeleteColumn(id)}
				onDragReorderColumns={handleDragReorderColumns}
				onResizeStart={(e, col) => s.handleResizeStart(e, col)}
				onShowAddColumn={() => (s.showAddColumn = true)}
				onAddRow={() => s.handleAddRow()}
				onAddRowAndEdit={(colId) => s.handleAddRow(colId)}
				onAddRowInGroup={(key, col) => s.handleAddRowInGroup(key, col)}
				onToggleCollapseGroup={(key) => s.toggleCollapseGroup(key)}
				onManageOptions={(col) => (s.managingOptionsCol = col)}
				onOpenDocCell={(row, col) => (s.docCellState = { row, col })}
			/>
		{:else if activeView.type === 'kanban'}
			<KanbanBoard
				{tableId}
				columns={$columns}
				rows={$rows}
				viewConfig={activeView}
				onOpenExpand={(row) => s.openExpand(row)}
				onRowsRefresh={() => fetchRows(tableId)}
				onAddRow={(data) => s.openCreateTicket(data)}
			/>
		{:else if activeView.type === 'timeline'}
			<TimelineView
				{tableId}
				columns={$columns}
				rows={$rows}
				viewConfig={activeView}
				onOpenExpand={(row) => s.openExpand(row)}
				onRowsRefresh={() => fetchRows(tableId)}
				onAddRow={(data) => s.openCreateTicket(data)}
			/>
		{:else if activeView.type === 'dashboard'}
			<DashboardView
				view={activeView as unknown as DashboardViewType & { view_id: number }}
				{tableId}
			/>
		{:else if activeView.type === 'workflow'}
			<WorkflowView
				{tableId}
				columns={$columns}
				rows={$rows}
				viewConfig={activeView}
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
		sortConfig={s.sortConfig}
		filterConditions={s.filterConditions}
		onClose={() => (s.contextMenu = null)}
		onExpandRow={(row) => s.openExpand(row)}
		onDuplicateRow={(id) => s.handleDuplicateRow(id)}
		onDeleteRow={(id) => s.handleDeleteRow(id)}
		onRenameColumn={(id, name) => s.startRename(id, name)}
		onSortChange={(c) => (s.sortConfig = c)}
		onAddFilter={(id) => s.addFilterForColumn(id)}
		onDeleteColumn={(id) => s.handleDeleteColumn(id)}
	/>
{/if}

<AddColumnModal
	show={s.showAddColumn}
	onClose={() => (s.showAddColumn = false)}
	onAdd={(name, type) => s.handleAddColumn(name, type)}
	pending={s.addingColumn}
/>

{#if s.expandedRow}
	<RowExpandPanel
		row={s.expandedRow}
		columns={$columns}
		onClose={() => (s.expandedRow = null)}
		onUpdateRow={(id, data) => s.handleUpdateRow(id, data)}
		onRefreshRows={(tid) => s.handleRefreshRows(tid)}
		{tableId}
		workspaceId={wsId}
		onOpenDocCell={(row, col) => {
			s.expandedRow = null;
			s.docCellState = { row, col };
		}}
	/>
{/if}

{#if s.docCellState}
	<DocCellEditor
		row={s.docCellState.row}
		column={s.docCellState.col}
		{tableId}
		workspaceId={wsId}
		onClose={() => (s.docCellState = null)}
	/>
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

<CreateTicketModal
	show={s.showCreateTicket}
	columns={$columns}
	initialData={s.createTicketInitialData}
	onClose={() => (s.showCreateTicket = false)}
	onSubmit={(data) => s.handleCreateTicket(data)}
/>

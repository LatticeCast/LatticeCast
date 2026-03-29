<script lang="ts">
	import type { Column, Row } from '$lib/types/table';
	import { TAG_COLORS } from '$lib/UI/theme.svelte';
	import {
		type RenderItem,
		getItemKey,
		getChoices,
		getChoiceColor,
		getTagValues,
		formatDate
	} from './table.utils';
	import { SvelteSet } from 'svelte/reactivity';

	let {
		columns,
		sortedColumns,
		renderItems,
		loading,
		tableMinWidth,
		addingRow,
		deletingRowId,
		rowsWithDocs,
		editingCell,
		editValue,
		renamingColId,
		renameValue,
		colMenuId,
		tagsPopupCell,
		sortConfig,
		filterConditions,
		resizingColId,
		hiddenCols,
		collapsedGroups,
		localWidths,
		onStartEdit,
		onCommitEdit,
		onEditValueChange,
		onEditingCellChange,
		onToggleCheckbox,
		onRemoveTag,
		onAddTag,
		onTagsPopupChange,
		onDeleteRow,
		onOpenExpand,
		onOpenContextMenu,
		onStartRename,
		onCommitRename,
		onRenameValueChange,
		onRenamingColIdChange,
		onColMenuChange,
		onSortChange,
		onFilterAdd,
		onShowFilterPanel,
		onHideCol,
		onDeleteColumn,
		onMoveColumn,
		onResizeStart,
		onShowAddColumn,
		onAddRow,
		onAddRowInGroup,
		onToggleCollapseGroup,
		onManageOptions
	}: {
		columns: Column[];
		sortedColumns: Column[];
		renderItems: RenderItem[];
		loading: boolean;
		tableMinWidth: number;
		addingRow: boolean;
		deletingRowId: string | null;
		rowsWithDocs: SvelteSet<string>;
		editingCell: { rowId: string; colId: string } | null;
		editValue: string;
		renamingColId: string | null;
		renameValue: string;
		colMenuId: string | null;
		tagsPopupCell: { rowId: string; colId: string } | null;
		sortConfig: { colId: string; dir: 'asc' | 'desc' } | null;
		filterConditions: { id: string; colId: string; operator: string; value: string }[];
		resizingColId: string | null;
		hiddenCols: SvelteSet<string>;
		collapsedGroups: SvelteSet<string>;
		localWidths: Record<string, number>;
		onStartEdit: (rowId: string, col: Column, currentVal: unknown) => void;
		onCommitEdit: (rowId: string, col: Column) => void;
		onEditValueChange: (val: string) => void;
		onEditingCellChange: (cell: { rowId: string; colId: string } | null) => void;
		onToggleCheckbox: (rowId: string, col: Column) => void;
		onRemoveTag: (rowId: string, col: Column, tag: string) => void;
		onAddTag: (rowId: string, col: Column, tag: string) => void;
		onTagsPopupChange: (cell: { rowId: string; colId: string } | null) => void;
		onDeleteRow: (rowId: string) => void;
		onOpenExpand: (row: Row) => void;
		onOpenContextMenu: (e: MouseEvent, type: 'row' | 'col', id: string) => void;
		onStartRename: (colId: string, name: string) => void;
		onCommitRename: (colId: string) => void;
		onRenameValueChange: (val: string) => void;
		onRenamingColIdChange: (id: string | null) => void;
		onColMenuChange: (colId: string | null) => void;
		onSortChange: (config: { colId: string; dir: 'asc' | 'desc' } | null) => void;
		onFilterAdd: (colId: string) => void;
		onShowFilterPanel: () => void;
		onHideCol: (colId: string) => void;
		onDeleteColumn: (colId: string) => void;
		onMoveColumn: (col: Column, dir: 'up' | 'down') => void;
		onResizeStart: (e: MouseEvent, col: Column) => void;
		onShowAddColumn: () => void;
		onAddRow: () => void;
		onAddRowInGroup: (key: string, col: Column) => void;
		onToggleCollapseGroup: (key: string) => void;
		onManageOptions: (col: Column) => void;
	} = $props();

	function getColWidth(col: Column): number {
		return localWidths[col.column_id] ?? col.options?.width ?? 150;
	}
</script>

<div class="min-h-[calc(100vh-6rem)] flex-1 overflow-x-auto bg-white">
	{#if loading}
		<div class="pt-16 text-center text-gray-400">Loading...</div>
	{:else if sortedColumns.length === 0}
		<div
			class="mx-4 my-4 rounded-xl border border-gray-200 bg-gray-50 p-8 text-center text-gray-400"
		>
			No columns defined yet. Click "+ Column" to start.
		</div>
	{:else}
		<table
			class="border-collapse text-gray-800"
			style="table-layout: fixed; width: {tableMinWidth}px;"
		>
			<thead>
				<tr>
					<!-- Row number header -->
					<th
						class="sticky left-0 z-20 border-r border-b border-gray-200 bg-gray-50 px-2 py-2 text-center text-xs font-semibold text-gray-400"
						style="width: 48px;"
					>
						#
					</th>
					{#each sortedColumns as col, i (col.column_id)}
						<th
							class="relative border-b border-gray-200 px-3 py-2 text-left text-xs font-semibold tracking-wide text-gray-500 uppercase
								{i === 0 ? 'sticky left-12 z-10 border-r border-gray-200 bg-gray-50' : 'bg-gray-50'}"
							style="width: {getColWidth(col)}px;"
							oncontextmenu={(e) => onOpenContextMenu(e, 'col', col.column_id)}
						>
							<div class="flex items-center gap-1">
								{#if renamingColId === col.column_id}
									<input
										class="min-w-0 flex-1 rounded border border-blue-400 bg-white px-2 py-0.5 text-sm text-gray-800 outline-none"
										value={renameValue}
										oninput={(e) =>
											onRenameValueChange((e.currentTarget as HTMLInputElement).value)}
										onblur={() => onCommitRename(col.column_id)}
										onkeydown={(e) => {
											if (e.key === 'Enter') onCommitRename(col.column_id);
											if (e.key === 'Escape') onRenamingColIdChange(null);
										}}
										autofocus
									/>
								{:else}
									<button
										onclick={(e) => {
											e.stopPropagation();
											onColMenuChange(colMenuId === col.column_id ? null : col.column_id);
										}}
										class="min-w-0 flex-1 cursor-pointer truncate text-left"
										title="Click for column options"
									>
										{col.name}
										<span class="ml-1 text-xs font-normal text-gray-400 normal-case"
											>({col.type})</span
										>
									</button>
									<svg
										class="h-3 w-3 shrink-0 text-gray-300 transition {colMenuId === col.column_id
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
							{#if colMenuId === col.column_id}
								<div
									class="absolute top-full left-0 z-30 mt-1 min-w-[168px] rounded-xl border border-gray-200 bg-white py-1 shadow-xl"
									onclick={(e) => e.stopPropagation()}
									role="menu"
								>
									<button
										class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
										onclick={() => {
											onStartRename(col.column_id, col.name);
											onColMenuChange(null);
										}}
										role="menuitem"
									>
										<svg
											class="h-4 w-4 text-gray-400"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
											><path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
											/></svg
										>
										Rename
									</button>
									{#if col.type === 'select' || col.type === 'tags'}
										<button
											class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
											onclick={() => {
												onManageOptions(col);
												onColMenuChange(null);
											}}
											role="menuitem"
										>
											<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a4 4 0 014-4z" /></svg>
											Manage Options
										</button>
									{/if}
									<hr class="my-1 border-gray-100" />
									<button
										class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
										onclick={() => {
											onMoveColumn(col, 'up');
											onColMenuChange(null);
										}}
										role="menuitem"
									>
										<svg
											class="h-4 w-4 text-gray-400"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
											><path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M7 16l-4-4m0 0l4-4m-4 4h18"
											/></svg
										>
										Move Left
									</button>
									<button
										class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
										onclick={() => {
											onMoveColumn(col, 'down');
											onColMenuChange(null);
										}}
										role="menuitem"
									>
										<svg
											class="h-4 w-4 text-gray-400"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
											><path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M17 8l4 4m0 0l-4 4m4-4H3"
											/></svg
										>
										Move Right
									</button>
									<hr class="my-1 border-gray-100" />
									<button
										class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 {sortConfig?.colId ===
											col.column_id && sortConfig?.dir === 'asc'
											? 'font-semibold text-blue-600'
											: ''}"
										onclick={() => {
											onSortChange({ colId: col.column_id, dir: 'asc' });
											onColMenuChange(null);
										}}
										role="menuitem"
									>
										<svg
											class="h-4 w-4 text-gray-400"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
											><path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12"
											/></svg
										>
										Sort A → Z
									</button>
									<button
										class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 {sortConfig?.colId ===
											col.column_id && sortConfig?.dir === 'desc'
											? 'font-semibold text-blue-600'
											: ''}"
										onclick={() => {
											onSortChange({ colId: col.column_id, dir: 'desc' });
											onColMenuChange(null);
										}}
										role="menuitem"
									>
										<svg
											class="h-4 w-4 text-gray-400"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
											><path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M3 4h13M3 8h9m-9 4h9m5-4v12m0 0l-4-4m4 4l4-4"
											/></svg
										>
										Sort Z → A
									</button>
									<button
										class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
										onclick={() => {
											onFilterAdd(col.column_id);
											onShowFilterPanel();
											onColMenuChange(null);
										}}
										role="menuitem"
									>
										<svg
											class="h-4 w-4 text-gray-400"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
											><path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z"
											/></svg
										>
										Filter
									</button>
									<hr class="my-1 border-gray-100" />
									<button
										class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-500 hover:bg-gray-50"
										onclick={() => {
											onHideCol(col.column_id);
											onColMenuChange(null);
										}}
										role="menuitem"
									>
										<svg
											class="h-4 w-4 text-gray-400"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
											><path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"
											/></svg
										>
										Hide
									</button>
									<hr class="my-1 border-gray-100" />
									<button
										class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50"
										onclick={() => {
											onDeleteColumn(col.column_id);
											onColMenuChange(null);
										}}
										role="menuitem"
									>
										<svg
											class="h-4 w-4 text-red-400"
											fill="none"
											stroke="currentColor"
											viewBox="0 0 24 24"
											><path
												stroke-linecap="round"
												stroke-linejoin="round"
												stroke-width="2"
												d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
											/></svg
										>
										Delete
									</button>
								</div>
							{/if}

							<!-- Resize handle -->
							<div
								class="absolute top-0 right-0 h-full w-1.5 cursor-col-resize hover:bg-blue-400"
								onmousedown={(e) => onResizeStart(e, col)}
								role="separator"
								aria-label="Resize column"
							></div>
						</th>
					{/each}
					<!-- Actions col header -->
					<th class="border-b border-gray-200 bg-gray-50" style="width: 40px;"></th>
					<!-- "+" add column -->
					<th class="border-b border-gray-200 bg-gray-50" style="width: 40px;">
						<button
							onclick={onShowAddColumn}
							class="flex h-full w-full items-center justify-center rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
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
						<tr class="border-b border-gray-200">
							<td colspan={sortedColumns.length + 3} class="bg-gray-50 py-0.5">
								<div class="flex items-center gap-2 px-3 py-1">
									<button
										onclick={() => onToggleCollapseGroup(item.key)}
										class="rounded p-0.5 text-gray-400 hover:text-gray-600"
										aria-label={collapsedGroups.has(item.key) ? 'Expand group' : 'Collapse group'}
									>
										<svg
											class="h-4 w-4 transition {collapsedGroups.has(item.key) ? '-rotate-90' : ''}"
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
											>{item.key}</span
										>
									{:else}
										<span class="text-sm font-medium text-gray-700">{item.key}</span>
									{/if}
									<span class="text-xs text-gray-400"
										>{item.count} {item.count === 1 ? 'row' : 'rows'}</span
									>
								</div>
							</td>
						</tr>
					{:else if item.type === 'group-add'}
						<tr class="border-b border-gray-100">
							<td colspan={sortedColumns.length + 3} class="px-4 py-1">
								<button
									onclick={() => onAddRowInGroup(item.key, item.col)}
									disabled={addingRow}
									class="rounded px-2 py-0.5 text-xs text-gray-400 hover:bg-gray-100 hover:text-gray-600 disabled:opacity-50"
								>
									+ Add row
								</button>
							</td>
						</tr>
					{:else}
						{@const row = item.row}
						{@const rowIdx = item.rowIdx}
						<tr
							class="border-b border-gray-100 transition hover:bg-blue-50/50 {deletingRowId ===
							row.row_id
								? 'opacity-50'
								: ''}"
							oncontextmenu={(e) => onOpenContextMenu(e, 'row', row.row_id)}
						>
							<!-- Row number -->
							<td
								class="sticky left-0 z-20 border-r border-gray-100 bg-gray-50 px-1 py-1 text-center"
								style="width: 48px;"
							>
								<button
									onclick={() => onOpenExpand(row)}
									class="group relative flex h-full w-full items-center justify-center rounded px-1 py-0.5 text-xs text-gray-400 hover:bg-gray-200 hover:text-gray-600"
									title="Expand row"
								>
									{rowIdx + 1}
									{#if rowsWithDocs.has(row.row_id)}
										<svg
											class="absolute left-0.5 h-3 w-3 text-blue-400 group-hover:hidden"
											fill="currentColor"
											viewBox="0 0 20 20"
											aria-label="Has doc"
										>
											<path
												fill-rule="evenodd"
												d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
												clip-rule="evenodd"
											/>
										</svg>
									{/if}
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

							<!-- Data cells -->
							{#each sortedColumns as col, i (col.column_id)}
								<td
									class="overflow-hidden py-1 text-sm text-gray-800
									{i === 0 ? 'sticky left-12 z-10 border-r border-gray-100 bg-white px-2' : 'px-2'}"
									style="width: {getColWidth(col)}px;"
									onclick={() => {
										if (
											col.type !== 'checkbox' &&
											col.type !== 'tags' &&
											!(editingCell?.rowId === row.row_id && editingCell?.colId === col.column_id)
										) {
											onStartEdit(row.row_id, col, row.row_data[col.column_id]);
										}
									}}
								>
									{#if editingCell?.rowId === row.row_id && editingCell?.colId === col.column_id}
										{#if col.type === 'select'}
											{@const choices = getChoices(col)}
											<select
												class="w-full rounded border border-blue-400 bg-white px-2 py-1 text-sm text-gray-800 outline-none"
												value={editValue}
												onchange={(e) => {
													onEditValueChange((e.currentTarget as HTMLSelectElement).value);
													onCommitEdit(row.row_id, col);
												}}
												onblur={() => onCommitEdit(row.row_id, col)}
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
												class="w-full rounded border border-blue-400 bg-white px-2 py-1 text-sm text-gray-800 outline-none"
												value={editValue}
												oninput={(e) =>
													onEditValueChange((e.currentTarget as HTMLInputElement).value)}
												onblur={() => onCommitEdit(row.row_id, col)}
												onkeydown={(e) => {
													if (e.key === 'Enter') onCommitEdit(row.row_id, col);
													if (e.key === 'Escape') onEditingCellChange(null);
												}}
												autofocus
											/>
										{:else if col.type === 'date'}
											<input
												type="date"
												class="w-full rounded border border-blue-400 bg-white px-2 py-1 text-sm text-gray-800 outline-none"
												value={editValue}
												oninput={(e) =>
													onEditValueChange((e.currentTarget as HTMLInputElement).value)}
												onblur={() => onCommitEdit(row.row_id, col)}
												onkeydown={(e) => {
													if (e.key === 'Enter') onCommitEdit(row.row_id, col);
													if (e.key === 'Escape') onEditingCellChange(null);
												}}
												autofocus
											/>
										{:else}
											<input
												type={col.type === 'url' ? 'url' : 'text'}
												class="w-full rounded border border-blue-400 bg-white px-2 py-1 text-sm text-gray-800 outline-none"
												value={editValue}
												oninput={(e) =>
													onEditValueChange((e.currentTarget as HTMLInputElement).value)}
												onblur={() => onCommitEdit(row.row_id, col)}
												onkeydown={(e) => {
													if (e.key === 'Enter') onCommitEdit(row.row_id, col);
													if (e.key === 'Escape') onEditingCellChange(null);
												}}
												autofocus
											/>
										{/if}
									{:else if col.type === 'checkbox'}
										<button
											class="relative inline-flex h-5 w-9 items-center rounded-full transition {row
												.row_data[col.column_id]
												? 'bg-blue-500'
												: 'bg-gray-200'}"
											onclick={(e) => {
												e.stopPropagation();
												onToggleCheckbox(row.row_id, col);
											}}
											aria-label="Toggle"
											role="switch"
											aria-checked={!!row.row_data[col.column_id]}
										>
											<span
												class="inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition {row
													.row_data[col.column_id]
													? 'translate-x-4'
													: 'translate-x-1'}"
											></span>
										</button>
									{:else if col.type === 'url'}
										{@const urlVal = (row.row_data[col.column_id] as string) ?? ''}
										{#if urlVal}
											<a
												href={urlVal}
												target="_blank"
												rel="noopener noreferrer"
												class="block max-w-full truncate text-blue-600 underline hover:text-blue-800"
												onclick={(e) => e.stopPropagation()}
												title={urlVal}>{urlVal}</a
											>
										{:else}
											<span class="block min-h-[1.5rem] cursor-text py-1 text-gray-300">—</span>
										{/if}
									{:else if col.type === 'select'}
										{@const selVal = (row.row_data[col.column_id] as string) ?? ''}
										{#if selVal}
											{@const color = getChoiceColor(col, selVal)}
											<span
												class="inline-flex cursor-pointer items-center rounded-full border px-2 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
												>{selVal}</span
											>
										{:else}
											<span class="block min-h-[1.5rem] cursor-pointer py-1 text-gray-300">—</span>
										{/if}
									{:else if col.type === 'tags'}
										{@const tagVals = getTagValues(row, col.column_id)}
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
														onclick={() => onRemoveTag(row.row_id, col, tag)}
														aria-label="Remove {tag}">×</button
													>
												</span>
											{/each}
											{#if available.length > 0}
												<div class="relative">
													<button
														class="rounded-full border border-gray-300 px-1.5 py-0.5 text-xs text-gray-400 hover:border-blue-400 hover:text-blue-600"
														onclick={() =>
															onTagsPopupChange(
																tagsPopupCell?.rowId === row.row_id && tagsPopupCell?.colId === col.column_id
																	? null
																	: { rowId: row.row_id, colId: col.column_id }
															)}>+</button
													>
													{#if tagsPopupCell?.rowId === row.row_id && tagsPopupCell?.colId === col.column_id}
														<div
															class="absolute top-full left-0 z-20 mt-1 min-w-[120px] rounded-xl border border-gray-100 bg-white py-1 shadow-xl"
														>
															{#each available as choice (choice.value)}
																{@const color =
																	TAG_COLORS[choices.indexOf(choice) % TAG_COLORS.length]}
																<button
																	class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-gray-50"
																	onclick={() => onAddTag(row.row_id, col, choice.value)}
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
										{@const raw = row.row_data[col.column_id]}
										<span class="font-mono text-sm">{raw ? formatDate(String(raw)) : ''}</span>
									{:else}
										{@const cellVal = row.row_data[col.column_id]}
										{#if cellVal !== null && cellVal !== undefined && String(cellVal) !== ''}
											<span class="block truncate">{String(cellVal)}</span>
										{:else}
											<span class="block min-h-[1.5rem] cursor-text py-1 text-gray-300">—</span>
										{/if}
									{/if}
								</td>
							{/each}

							<!-- Actions (delete) -->
							<td class="px-1 py-1 text-center" style="width: 40px;">
								<button
									onclick={() => onDeleteRow(row.row_id)}
									disabled={deletingRowId === row.row_id}
									class="rounded p-1 text-gray-300 transition hover:bg-red-50 hover:text-red-500 disabled:opacity-50"
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
							<td style="width: 40px;"></td>
						</tr>
					{/if}
				{:else}
					<!-- empty -->
				{/each}
				<!-- "+" row at bottom — click any cell to add new row -->
				<tr class="border-b border-gray-100 transition hover:bg-blue-50/30">
					<td
						class="sticky left-0 z-20 border-r border-gray-100 bg-gray-50 px-1 py-1 text-center"
						style="width: 48px;"
					>
						<button
							onclick={onAddRow}
							disabled={addingRow}
							class="flex h-full w-full items-center justify-center rounded px-1 py-0.5 text-sm font-medium text-blue-500 hover:bg-blue-100 hover:text-blue-700 disabled:opacity-50"
							title="Add row"
						>
							+
						</button>
					</td>
					{#each sortedColumns as col, i (col.column_id)}
						<td
							class="cursor-pointer py-1 text-sm text-gray-300
							{i === 0 ? 'sticky left-12 z-10 border-r border-gray-100 bg-white px-2' : 'px-2'}"
							style="width: {getColWidth(col)}px;"
							onclick={() => onAddRow()}
						>
							<span class="block min-h-[1.5rem] py-1">—</span>
						</td>
					{/each}
					<td style="width: 40px;"></td>
					<td style="width: 40px;"></td>
				</tr>
			</tbody>
		</table>
	{/if}
</div>

<script lang="ts">
	import type { Column } from '$lib/types/table';
	import { isDark } from '$lib/UI/theme.svelte';
	import { sortLabels } from './table.utils';

	let {
		sortedColumns,
		colMenuId,
		renamingColId,
		renameValue,
		sortConfig,
		addingColumn,
		localWidths,
		onOpenContextMenu,
		onRenameValueChange,
		onCommitRename,
		onRenamingColIdChange,
		onColMenuChange,
		onStartRename,
		onManageOptions,
		onMoveColumn,
		onSortChange,
		onFilterAdd,
		onShowFilterPanel,
		onHideCol,
		onDeleteColumn,
		onResizeStart,
		onShowAddColumn
	}: {
		sortedColumns: Column[];
		colMenuId: string | null;
		renamingColId: string | null;
		renameValue: string;
		sortConfig: { colId: string; dir: 'asc' | 'desc' } | null;
		addingColumn: boolean;
		localWidths: Record<string, number>;
		onOpenContextMenu: (e: MouseEvent, type: 'row' | 'col', id: string) => void;
		onRenameValueChange: (val: string) => void;
		onCommitRename: (colId: string) => void;
		onRenamingColIdChange: (id: string | null) => void;
		onColMenuChange: (colId: string | null) => void;
		onStartRename: (colId: string, name: string) => void;
		onManageOptions: (col: Column) => void;
		onMoveColumn: (col: Column, dir: 'up' | 'down') => void;
		onSortChange: (config: { colId: string; dir: 'asc' | 'desc' } | null) => void;
		onFilterAdd: (colId: string) => void;
		onShowFilterPanel: () => void;
		onHideCol: (colId: string) => void;
		onDeleteColumn: (colId: string) => void;
		onResizeStart: (e: MouseEvent, col: Column) => void;
		onShowAddColumn: () => void;
	} = $props();

	function getColWidth(col: Column): number {
		return localWidths[col.column_id] ?? col.options?.width ?? 150;
	}
</script>

<thead>
	<tr>
		<!-- Row number header -->
		<th
			class="sticky left-0 z-20 border-r border-b px-2 py-2 text-center text-xs font-semibold {isDark.value
				? 'border-gray-700 bg-gray-800 text-gray-500'
				: 'border-gray-200 bg-gray-50 text-gray-400'}"
			style="width: 48px;"
		>
			#
		</th>
		{#each sortedColumns as col, i (col.column_id)}
			<th
				class="relative border-b px-3 py-2 text-left text-xs font-semibold tracking-wide uppercase {isDark.value
					? 'border-gray-700 text-gray-400'
					: 'border-gray-200 text-gray-500'}
					{i === 0
					? isDark.value
						? 'sticky left-12 border-r border-gray-700 bg-gray-800'
						: 'sticky left-12 border-r border-gray-200 bg-gray-50'
					: isDark.value
						? 'bg-gray-800'
						: 'bg-gray-50'}
					{colMenuId === col.column_id ? 'z-30' : i === 0 ? 'z-10' : ''}"
				style="width: {getColWidth(col)}px;"
				oncontextmenu={(e) => onOpenContextMenu(e, 'col', col.column_id)}
			>
				<div class="flex items-center gap-1">
					{#if renamingColId === col.column_id}
						<input
							class="min-w-0 flex-1 rounded border border-blue-400 bg-white px-2 py-0.5 text-sm text-gray-800 outline-none"
							value={renameValue}
							oninput={(e) => onRenameValueChange((e.currentTarget as HTMLInputElement).value)}
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
							<span class="ml-1 text-xs font-normal text-gray-400 normal-case">({col.type})</span>
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
					{@const sl = sortLabels(col.type)}
					<div
						class="absolute top-full left-0 z-30 mt-1 min-w-[168px] rounded-xl border py-1 shadow-xl {isDark.value
							? 'border-gray-700 bg-gray-800'
							: 'border-gray-200 bg-white'}"
						onclick={(e) => e.stopPropagation()}
						role="menu"
					>
						<button
							class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm {isDark.value
								? 'text-gray-300 hover:bg-gray-700'
								: 'text-gray-700 hover:bg-gray-50'}"
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
								class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm {isDark.value
									? 'text-gray-300 hover:bg-gray-700'
									: 'text-gray-700 hover:bg-gray-50'}"
								onclick={() => {
									onManageOptions(col);
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
										d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a4 4 0 014-4z"
									/></svg
								>
								Manage Options
							</button>
						{/if}
						<hr class={isDark.value ? 'my-1 border-gray-700' : 'my-1 border-gray-100'} />
						<button
							class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm {isDark.value
								? 'text-gray-300 hover:bg-gray-700'
								: 'text-gray-700 hover:bg-gray-50'}"
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
							class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm {isDark.value
								? 'text-gray-300 hover:bg-gray-700'
								: 'text-gray-700 hover:bg-gray-50'}"
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
						<hr class={isDark.value ? 'my-1 border-gray-700' : 'my-1 border-gray-100'} />
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
							Sort {sl.asc}
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
							Sort {sl.desc}
						</button>
						<button
							class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm {isDark.value
								? 'text-gray-300 hover:bg-gray-700'
								: 'text-gray-700 hover:bg-gray-50'}"
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
						<hr class={isDark.value ? 'my-1 border-gray-700' : 'my-1 border-gray-100'} />
						<button
							class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm {isDark.value
								? 'text-gray-400 hover:bg-gray-700'
								: 'text-gray-500 hover:bg-gray-50'}"
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
						<hr class={isDark.value ? 'my-1 border-gray-700' : 'my-1 border-gray-100'} />
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
		<th
			class="border-b {isDark.value ? 'border-gray-700 bg-gray-800' : 'border-gray-200 bg-gray-50'}"
			style="width: 40px;"
		></th>
		<!-- "+" add column -->
		<th
			class="border-b {isDark.value ? 'border-gray-700 bg-gray-800' : 'border-gray-200 bg-gray-50'}"
			style="width: 40px;"
		>
			<button
				data-testid="grid-add-column-btn"
				onclick={onShowAddColumn}
				disabled={addingColumn}
				class="flex h-full w-full items-center justify-center rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 disabled:opacity-50"
				title="Add column"
				aria-label="Add column"
			>
				{#if addingColumn}
					<svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
						<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"
						></circle>
						<path
							class="opacity-75"
							fill="currentColor"
							d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
						></path>
					</svg>
				{:else}
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M12 4v16m8-8H4"
						/>
					</svg>
				{/if}
			</button>
		</th>
	</tr>
</thead>

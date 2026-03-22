<script lang="ts">
	import type { Column, Row } from '$lib/types/table';
	import type { ContextMenuState, FilterCondition } from './table.utils';

	let { contextMenu, columns, rows, sortConfig, filterConditions,
		onClose, onExpandRow, onDuplicateRow, onDeleteRow,
		onRenameColumn, onSortChange, onAddFilter, onHideColumn, onDeleteColumn
	}: {
		contextMenu: ContextMenuState;
		columns: Column[];
		rows: Row[];
		sortConfig: { colId: string; dir: 'asc' | 'desc' } | null;
		filterConditions: FilterCondition[];
		onClose: () => void;
		onExpandRow: (row: Row) => void;
		onDuplicateRow: (rowId: string) => void;
		onDeleteRow: (rowId: string) => void;
		onRenameColumn: (colId: string, name: string) => void;
		onSortChange: (config: { colId: string; dir: 'asc' | 'desc' }) => void;
		onAddFilter: (colId: string) => void;
		onHideColumn: (colId: string) => void;
		onDeleteColumn: (colId: string) => void;
	} = $props();

	const ctxCol = $derived(
		contextMenu.type === 'col' ? columns.find((c) => c.id === contextMenu.id) : null
	);
</script>

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
				const row = rows.find((r) => r.id === contextMenu.id);
				if (row) onExpandRow(row);
				onClose();
			}}
			role="menuitem"
		>
			<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
			</svg>
			Expand
		</button>
		<button
			class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
			onclick={() => onDuplicateRow(contextMenu.id)}
			role="menuitem"
		>
			<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
			</svg>
			Duplicate
		</button>
		<hr class="my-1 border-gray-100" />
		<button
			class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50"
			onclick={() => { onDeleteRow(contextMenu.id); onClose(); }}
			role="menuitem"
		>
			<svg class="h-4 w-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
			</svg>
			Delete
		</button>
	{:else if ctxCol}
		<button
			class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
			onclick={() => { onRenameColumn(ctxCol.id, ctxCol.name); onClose(); }}
			role="menuitem"
		>
			<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
			</svg>
			Rename
		</button>
		<hr class="my-1 border-gray-100" />
		<button
			class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 {sortConfig?.colId === ctxCol.id && sortConfig?.dir === 'asc' ? 'font-semibold text-blue-600' : ''}"
			onclick={() => { onSortChange({ colId: ctxCol.id, dir: 'asc' }); onClose(); }}
			role="menuitem"
		>
			<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12" />
			</svg>
			Sort A → Z
		</button>
		<button
			class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 {sortConfig?.colId === ctxCol.id && sortConfig?.dir === 'desc' ? 'font-semibold text-blue-600' : ''}"
			onclick={() => { onSortChange({ colId: ctxCol.id, dir: 'desc' }); onClose(); }}
			role="menuitem"
		>
			<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4h13M3 8h9m-9 4h9m5-4v12m0 0l-4-4m4 4l4-4" />
			</svg>
			Sort Z → A
		</button>
		<button
			class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 {filterConditions.some((c) => c.colId === ctxCol.id) ? 'font-semibold text-blue-600' : ''}"
			onclick={() => { onAddFilter(ctxCol.id); onClose(); }}
			role="menuitem"
		>
			<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z" />
			</svg>
			Filter
		</button>
		<hr class="my-1 border-gray-100" />
		<button
			class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-gray-500 hover:bg-gray-50"
			onclick={() => { onHideColumn(ctxCol.id); onClose(); }}
			role="menuitem"
		>
			<svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
			</svg>
			Hide
		</button>
		<hr class="my-1 border-gray-100" />
		<button
			class="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50"
			onclick={() => { onDeleteColumn(ctxCol.id); onClose(); }}
			role="menuitem"
		>
			<svg class="h-4 w-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
			</svg>
			Delete
		</button>
	{/if}
</div>

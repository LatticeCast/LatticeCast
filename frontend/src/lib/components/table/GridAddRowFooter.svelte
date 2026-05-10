<script lang="ts">
	import type { Column } from '$lib/types/table';
	import { isDark } from '$lib/UI/theme.svelte';

	let {
		sortedColumns,
		addingRow,
		localWidths,
		onAddRow,
		onAddRowAndEdit
	}: {
		sortedColumns: Column[];
		addingRow: boolean;
		localWidths: Record<string, number>;
		onAddRow: () => void;
		onAddRowAndEdit?: (colId: string) => void;
	} = $props();

	function getColWidth(col: Column): number {
		return localWidths[col.column_id] ?? col.options?.width ?? 150;
	}
</script>

<tr
	class="border-b transition {isDark.value
		? 'border-gray-700 hover:bg-blue-900/10'
		: 'border-gray-100 hover:bg-blue-50/30'}"
>
	<td
		class="sticky left-0 z-20 border-r px-1 py-1 text-center {isDark.value
			? 'border-gray-700 bg-gray-800'
			: 'border-gray-100 bg-gray-50'}"
		style="width: 48px;"
	>
		<button
			data-testid="grid-add-row-btn"
			onclick={onAddRow}
			disabled={addingRow}
			class="flex h-full w-full items-center justify-center rounded px-1 py-0.5 text-sm font-medium text-blue-500 hover:bg-blue-100 hover:text-blue-700 disabled:opacity-50"
			title="Add row"
		>
			{#if addingRow}
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
				+
			{/if}
		</button>
	</td>
	{#each sortedColumns as col, i (col.column_id)}
		<td
			class="cursor-pointer py-1 text-sm {isDark.value ? 'text-gray-600' : 'text-gray-300'}
			{i === 0
				? isDark.value
					? 'sticky left-12 z-10 border-r border-gray-700 bg-gray-800 px-2'
					: 'sticky left-12 z-10 border-r border-gray-100 bg-white px-2'
				: 'px-2'}"
			style="width: {getColWidth(col)}px;"
			onclick={() => (onAddRowAndEdit ? onAddRowAndEdit(col.column_id) : onAddRow())}
		>
			<span class="block min-h-[1.5rem] py-1">—</span>
		</td>
	{/each}
	<td style="width: 40px;"></td>
	<td style="width: 40px;"></td>
</tr>

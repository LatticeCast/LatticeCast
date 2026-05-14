<script lang="ts">
	import type { Column, Row } from '$lib/types/table';
	import { isDark } from '$lib/UI/theme.svelte';
	import { getChoices, getChoiceColor, getTagValues, colorToStyle } from '../table.utils';

	let {
		row,
		column,
		tagsPopupCell,
		onTagsPopupChange,
		onRemoveTag,
		onAddTag
	}: {
		row: Row;
		column: Column;
		tagsPopupCell: { rowId: number; colId: string } | null;
		onTagsPopupChange: (cell: { rowId: number; colId: string } | null) => void;
		onRemoveTag: (tag: string) => void;
		onAddTag: (tag: string) => void;
	} = $props();

	const tagVals = $derived(getTagValues(row, column.column_id));
	const choices = $derived(getChoices(column));
	const available = $derived(choices.filter((c) => !tagVals.includes(c.value)));
	const isPopupOpen = $derived(
		tagsPopupCell?.rowId === row.row_id && tagsPopupCell?.colId === column.column_id
	);
</script>

<div class="flex min-h-[1.75rem] flex-wrap items-center gap-1" onclick={(e) => e.stopPropagation()}>
	{#each tagVals as tag (tag)}
		{@const cs = getChoiceColor(column, tag)}
		<span
			class="inline-flex items-center gap-0.5 rounded-full border px-2 py-0.5 text-xs font-medium {cs.cls}"
			style={cs.style}
		>
			{tag}
			<button
				class="ml-0.5 rounded-full leading-none hover:opacity-60"
				onclick={() => onRemoveTag(tag)}
				aria-label="Remove {tag}">×</button
			>
		</span>
	{/each}
	{#if available.length > 0}
		<div class="relative">
			<button
				class="rounded-full border border-gray-300 px-1.5 py-0.5 text-xs text-gray-400 hover:border-blue-400 hover:text-blue-600"
				onclick={() =>
					onTagsPopupChange(isPopupOpen ? null : { rowId: row.row_id, colId: column.column_id })}
				>+</button
			>
			{#if isPopupOpen}
				<div
					class="absolute top-full left-0 z-20 mt-1 min-w-[120px] rounded-xl border py-1 shadow-xl {isDark.value
						? 'border-gray-700 bg-gray-800'
						: 'border-gray-100 bg-white'}"
				>
					{#each available as choice (choice.value)}
						{@const cs = colorToStyle(choice.color)}
						<button
							class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-gray-50"
							onclick={() => onAddTag(choice.value)}
						>
							<span
								class="inline-flex items-center rounded-full border px-2 py-0.5 font-medium {cs.cls}"
								style={cs.style}>{choice.value}</span
							>
						</button>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</div>

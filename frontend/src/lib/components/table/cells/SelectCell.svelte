<script lang="ts">
	import type { Column } from '$lib/types/table';
	import { getChoices, getChoiceColor } from '../table.utils';

	let {
		value,
		column,
		isEditing,
		editValue,
		onEditValueChange,
		onCommit
	}: {
		value: unknown;
		column: Column;
		isEditing: boolean;
		editValue: string;
		onEditValueChange: (val: string) => void;
		onCommit: () => void;
	} = $props();

	const choices = $derived(getChoices(column));
	const selVal = $derived((value as string) ?? '');
	const color = $derived(selVal ? getChoiceColor(column, selVal) : null);
</script>

{#if isEditing}
	<select
		class="w-full rounded border border-blue-400 bg-white px-2 py-1 text-sm text-gray-800 outline-none"
		value={editValue}
		onchange={(e) => {
			onEditValueChange((e.currentTarget as HTMLSelectElement).value);
			onCommit();
		}}
		onblur={onCommit}
		autofocus
	>
		<option value="">—</option>
		{#each choices as choice (choice.value)}
			<option value={choice.value}>{choice.value}</option>
		{/each}
	</select>
{:else if selVal && color}
	<span
		class="inline-flex cursor-pointer items-center rounded-full border px-2 py-0.5 text-xs font-medium {color.cls}"
		style={color.style}>{selVal}</span
	>
{:else}
	<span class="block min-h-[1.5rem] cursor-pointer py-1 text-gray-300">—</span>
{/if}

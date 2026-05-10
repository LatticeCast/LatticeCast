<script lang="ts">
	import type { Column } from '$lib/types/table';

	let {
		value,
		column,
		isEditing,
		editValue,
		onEditValueChange,
		onCommit,
		onCancel,
		onAddRowIfLast
	}: {
		value: unknown;
		column: Column;
		isEditing: boolean;
		editValue: string;
		onEditValueChange: (val: string) => void;
		onCommit: () => void;
		onCancel: () => void;
		onAddRowIfLast: (() => void) | null;
	} = $props();
</script>

{#if isEditing}
	<input
		type="text"
		class="w-full rounded border border-blue-400 bg-white px-2 py-1 text-sm text-gray-800 outline-none"
		value={editValue}
		oninput={(e) => onEditValueChange((e.currentTarget as HTMLInputElement).value)}
		onblur={onCommit}
		onkeydown={(e) => {
			if (e.key === 'Enter') {
				onCommit();
				onAddRowIfLast?.();
			}
			if (e.key === 'Escape') onCancel();
		}}
		autofocus
	/>
{:else if column.name === 'Key'}
	{#if value !== null && value !== undefined && String(value) !== ''}
		<span class="block cursor-pointer truncate font-medium text-blue-600 hover:underline"
			>{String(value)}</span
		>
	{:else}
		<span class="block min-h-[1.5rem] cursor-pointer py-1 text-gray-300">—</span>
	{/if}
{:else if value !== null && value !== undefined && String(value) !== ''}
	<span class="block truncate">{String(value)}</span>
{:else}
	<span class="block min-h-[1.5rem] cursor-text py-1 text-gray-300">—</span>
{/if}

<script lang="ts">
	import { formatDate } from '../table.utils';

	let {
		value,
		isEditing,
		editValue,
		onEditValueChange,
		onCommit,
		onCancel,
		onAddRowIfLast
	}: {
		value: unknown;
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
		type="date"
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
{:else}
	<span class="font-mono text-sm">{value ? formatDate(String(value)) : ''}</span>
{/if}

<script lang="ts">
	import { formatCellDate } from '../table.utils';
	import { toInput } from '$lib/utils/temporal';
	import { currentZone } from '$lib/stores/settings.store';
	import type { TemporalType } from '$lib/utils/temporal';

	let {
		value,
		type = 'date',
		isEditing,
		editValue,
		onEditValueChange,
		onCommit,
		onCancel,
		onAddRowIfLast
	}: {
		value: unknown;
		type?: TemporalType;
		isEditing: boolean;
		editValue: string;
		onEditValueChange: (val: string) => void;
		onCommit: () => void;
		onCancel: () => void;
		onAddRowIfLast: (() => void) | null;
	} = $props();

	// The picker works in the user's configured zone, so what they choose is
	// the instant that moment starts for them. The stored value is UTC.
	const inputValue = $derived(editValue !== '' ? editValue : toInput(value, type, currentZone()));
</script>

{#if isEditing}
	<input
		type={type === 'date' ? 'date' : 'datetime-local'}
		class="w-full rounded border border-blue-400 bg-white px-2 py-1 text-sm text-gray-800 outline-none"
		value={inputValue}
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
	<span class="font-mono text-sm">{formatCellDate(value, type)}</span>
{/if}

<script lang="ts">
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

	const urlVal = $derived((value as string) ?? '');
</script>

{#if isEditing}
	<input
		type="url"
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
{:else if urlVal && (urlVal.startsWith('http://') || urlVal.startsWith('https://'))}
	<a
		href={urlVal}
		target="_blank"
		rel="noopener noreferrer"
		class="block max-w-full truncate text-blue-600 underline hover:text-blue-800"
		onclick={(e) => e.stopPropagation()}
		title={urlVal}>{urlVal}</a
	>
{:else if urlVal}
	<a
		href="/{urlVal}"
		class="block max-w-full truncate text-blue-600 underline hover:text-blue-800"
		onclick={(e) => e.stopPropagation()}
		title={urlVal}>{urlVal}</a
	>
{:else}
	<span class="block min-h-[1.5rem] cursor-text py-1 text-gray-300">—</span>
{/if}

<script lang="ts">
	import type { Column } from '$lib/types/table';
	import { T } from '$lib/UI/theme.svelte';

	let {
		columns,
		value,
		onchange
	}: {
		columns: Column[];
		value: string | null;
		onchange: (colId: string | null) => void;
	} = $props();

	const selectColumns = $derived(columns.filter((c) => c.type === 'select'));
</script>

<div class="flex items-center gap-2">
	<span class="text-xs font-medium {T.muted}">Group by</span>
	<select
		data-testid="group-by-selector"
		class="rounded-md border px-2 py-1 text-xs focus:outline-none {T.inputBorder} {T.inputBg} {T.body} {T.inputFocusBorder}"
		value={value ?? ''}
		onchange={(e) => onchange((e.target as HTMLSelectElement).value || null)}
	>
		<option value="">— none —</option>
		{#each selectColumns as col (col.column_id)}
			<option value={col.column_id}>{col.name}</option>
		{/each}
	</select>
</div>

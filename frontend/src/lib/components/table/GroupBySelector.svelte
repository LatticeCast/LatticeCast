<script lang="ts">
	import type { Column } from '$lib/types/table';
	import { isDark } from '$lib/UI/theme.svelte';

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
	<span class="text-xs font-medium {isDark.value ? 'text-gray-400' : 'text-gray-500'}">Group by</span>
	<select
		data-testid="group-by-selector"
		class="rounded-md border px-2 py-1 text-xs focus:outline-none {isDark.value
			? 'border-gray-600 bg-gray-700 text-gray-200 focus:border-blue-400'
			: 'border-gray-200 bg-white text-gray-700 focus:border-blue-500'}"
		value={value ?? ''}
		onchange={(e) => onchange((e.target as HTMLSelectElement).value || null)}
	>
		<option value="">— none —</option>
		{#each selectColumns as col (col.column_id)}
			<option value={col.column_id}>{col.name}</option>
		{/each}
	</select>
</div>

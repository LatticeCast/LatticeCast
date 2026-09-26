<script lang="ts">
	import type { ListBlock } from '$lib/types/dashboard';
	import { dashboardBlockKey, dashboardBlocks } from '$lib/stores/dashboard.store';
	import { T } from '$lib/UI/theme.svelte';

	let {
		block,
		tableId,
		viewName,
		blockId
	}: {
		block: ListBlock;
		tableId: string;
		viewName: string;
		blockId: string;
	} = $props();

	const cacheKey = $derived(dashboardBlockKey(tableId, viewName, blockId));
	const result = $derived($dashboardBlocks[cacheKey] ?? { rows: [], status: 'idle', error: null });
	const rows = $derived(result.rows);

	let cols = $derived(
		block.columns.length > 0
			? block.columns
			: Object.keys(rows[0] ?? {}).map((k) => ({ key: k, label: k }))
	);
</script>

<div class="flex h-full flex-col gap-2" data-testid="block-list" data-status={result.status}>
	<span class="text-sm font-medium {T.body} opacity-70">{block.title}</span>
	{#if result.error}
		<span class="text-sm text-red-500" data-testid="block-error">{result.error}</span>
	{:else}
		<div class="overflow-auto">
			<table class="w-full text-sm {T.body}" data-testid="list-table">
				{#if cols.length > 0}
					<thead>
						<tr>
							{#each cols as col (col.key)}
								<th class="px-2 py-1 text-left font-medium opacity-60">{col.label}</th>
							{/each}
						</tr>
					</thead>
				{/if}
				<tbody>
					{#each rows as row, i (i)}
						<tr class="border-opacity-10 border-t border-current" data-testid="list-row-{i}">
							{#each cols as col (col.key)}
								<td class="px-2 py-1">{String(row[col.key] ?? '')}</td>
							{/each}
						</tr>
					{/each}
				</tbody>
			</table>
			{#if rows.length === 0 && result.status === 'loaded'}
				<p class="py-4 text-center text-sm opacity-50" data-testid="list-empty">No data</p>
			{/if}
		</div>
	{/if}
</div>

<script lang="ts">
	import type { NumberBlock } from '$lib/types/dashboard';
	import { dashboardBlockKey, dashboardBlocks } from '$lib/stores/dashboard.store';
	import { T } from '$lib/UI/theme.svelte';

	let {
		block,
		tableId,
		viewName,
		blockId
	}: {
		block: NumberBlock;
		tableId: string;
		viewName: string;
		blockId: string;
	} = $props();

	const cacheKey = $derived(dashboardBlockKey(tableId, viewName, blockId));
	const result = $derived($dashboardBlocks[cacheKey] ?? { rows: [], status: 'idle', error: null });
	const value = $derived.by(() => {
		const raw = result.rows[0]?.[block.field];
		return raw !== undefined && raw !== null ? (raw as number) : '—';
	});
</script>

<div
	class="flex h-full flex-col justify-between"
	data-testid="block-number"
	data-status={result.status}
>
	<span class="text-sm font-medium {T.body} opacity-70">{block.title}</span>
	{#if result.error}
		<span class="text-sm text-red-500" data-testid="block-error">{result.error}</span>
	{:else}
		<span class="text-4xl font-bold {T.body}" data-testid="number-value">{value}</span>
	{/if}
</div>

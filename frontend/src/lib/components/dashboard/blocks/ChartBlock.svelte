<script lang="ts">
	import type { ChartBlock } from '$lib/types/dashboard';
	import { dashboardBlockKey, dashboardBlocks } from '$lib/stores/dashboard.store';
	import { applyInjects } from '$lib/charts/inject';
	import EChart from '$lib/charts/EChart.svelte';
	import { T } from '$lib/UI/theme.svelte';

	let {
		block,
		tableId,
		viewName,
		blockId
	}: {
		block: ChartBlock;
		tableId: string;
		viewName: string;
		blockId: string;
	} = $props();

	const cacheKey = $derived(dashboardBlockKey(tableId, viewName, blockId));
	const result = $derived($dashboardBlocks[cacheKey] ?? { rows: [], status: 'idle', error: null });
	const rows = $derived(result.rows);

	let option = $derived(applyInjects(block.echarts, { rows }));
</script>

<div class="flex h-full flex-col gap-2" data-testid="block-chart" data-status={result.status}>
	<span class="text-sm font-medium {T.body} opacity-70">{block.title}</span>
	{#if result.error}
		<span class="text-sm text-red-500" data-testid="block-error">{result.error}</span>
	{:else}
		<div class="min-h-0 flex-1">
			<EChart {option} />
		</div>
	{/if}
</div>

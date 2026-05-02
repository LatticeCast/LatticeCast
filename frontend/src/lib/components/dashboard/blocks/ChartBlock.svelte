<script lang="ts">
	import type { ChartBlock, BlockRow } from '$lib/types/dashboard';
	import { fetchBlockRows } from '$lib/api/dashboard';
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

	let rows = $state<BlockRow[]>([]);
	let error = $state<string | null>(null);
	let status = $state<'loading' | 'loaded'>('loading');

	$effect(() => {
		fetchBlockRows(tableId, viewName, blockId)
			.then((r: BlockRow[]) => {
				rows = r;
			})
			.catch((e: Error) => {
				error = e.message;
			})
			.finally(() => {
				status = 'loaded';
			});
	});

	let option = $derived(applyInjects(block.echarts, { rows }));
</script>

<div class="flex h-full flex-col gap-2" data-testid="block-chart" data-status={status}>
	<span class="text-sm font-medium {T.body} opacity-70">{block.title}</span>
	{#if error}
		<span class="text-sm text-red-500" data-testid="block-error">{error}</span>
	{:else}
		<div class="min-h-0 flex-1">
			<EChart {option} />
		</div>
	{/if}
</div>

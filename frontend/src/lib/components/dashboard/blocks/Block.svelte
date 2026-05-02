<script lang="ts">
	import type { Block } from '$lib/types/dashboard';
	import ChartBlock from './ChartBlock.svelte';
	import NumberBlock from './NumberBlock.svelte';
	import ListBlock from './ListBlock.svelte';

	let {
		block,
		tableId,
		viewName,
		blockId
	}: {
		block: Block;
		tableId: string;
		viewName: string;
		blockId: string;
	} = $props();
</script>

{#if block.kind === 'chart'}
	<ChartBlock {block} {tableId} {viewName} {blockId} />
{:else if block.kind === 'number'}
	<NumberBlock {block} {tableId} {viewName} {blockId} />
{:else if block.kind === 'list'}
	<ListBlock {block} {tableId} {viewName} {blockId} />
{/if}

<script lang="ts">
	import type { DashboardView } from '$lib/types/dashboard';
	import Block from './blocks/Block.svelte';
	import { T } from '$lib/UI/theme.svelte';

	let { view, tableId }: { view: DashboardView; tableId: string } = $props();
</script>

<div class="grid grid-cols-12 gap-4 p-4 {T.body}" data-testid="dashboard-grid">
	{#each view.config.layout as item (item.id)}
		{@const block = view.config.blocks[item.id]}
		{#if block}
			<div
				class="col-span-{item.w} row-span-{item.h} {T.cardBg} rounded-lg p-4"
				data-testid="dashboard-block-{item.id}"
			>
				<Block {block} {tableId} viewName={view.name} blockId={item.id} />
			</div>
		{/if}
	{/each}
</div>

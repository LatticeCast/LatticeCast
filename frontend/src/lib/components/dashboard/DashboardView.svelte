<script lang="ts">
	import type { DashboardView } from '$lib/types/dashboard';
	import Block from './blocks/Block.svelte';
	import { T } from '$lib/UI/theme.svelte';

	let { view, tableId }: { view: DashboardView; tableId: string } = $props();
</script>

<!--
  V0.27.2: positions are honored via inline `grid-column` / `grid-row`.
  Tailwind v4 purges dynamic class names like `col-span-{item.w}`, so we
  cannot interpolate Tailwind classes from layout values at runtime.
  Inline styles with explicit grid-column/grid-row lines are the fix.
-->
<div
	class="grid grid-cols-12 gap-4 p-4 {T.body}"
	style="grid-auto-rows: minmax(80px, auto);"
	data-testid="dashboard-grid"
>
	{#each view.config.layout as item (item.id)}
		{@const block = view.config.blocks[item.id]}
		{#if block}
			<div
				class="{T.cardBg} flex flex-col overflow-hidden rounded-lg p-4 shadow-sm"
				style="grid-column: {item.x + 1} / span {item.w}; grid-row: {item.y + 1} / span {item.h};"
				data-testid="dashboard-block-{item.id}"
			>
				<Block {block} {tableId} viewName={view.name} blockId={item.id} />
			</div>
		{/if}
	{/each}
</div>

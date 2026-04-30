<script lang="ts">
	import type { DashboardView } from '$lib/types/dashboard';
	import NumberWidget from './widgets/NumberWidget.svelte';
	import BarWidget from './widgets/BarWidget.svelte';
	import PieWidget from './widgets/PieWidget.svelte';
	import LineWidget from './widgets/LineWidget.svelte';
	import ListWidget from './widgets/ListWidget.svelte';
	import { T } from '$lib/UI/theme.svelte';

	let { view, tableId }: { view: DashboardView; tableId: string } = $props();

	const widgetComponents = {
		number: NumberWidget,
		bar: BarWidget,
		pie: PieWidget,
		line: LineWidget,
		list: ListWidget
	};
</script>

<div class="grid grid-cols-12 gap-4 p-4 {T.body}" data-testid="dashboard-grid">
	{#each view.config.layout as item (item.widget_id)}
		{@const w = view.config.widgets[item.widget_id]}
		{#if w}
			{@const Cmp = widgetComponents[w.chart]}
			<div
				class="col-span-{item.w} row-span-{item.h} {T.cardBg} rounded-lg p-4"
				data-testid="dashboard-widget-{item.widget_id}"
			>
				<Cmp widget={w} {tableId} viewName={view.name} widgetId={item.widget_id} />
			</div>
		{/if}
	{/each}
</div>

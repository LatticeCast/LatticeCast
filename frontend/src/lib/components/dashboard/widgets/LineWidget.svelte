<script lang="ts">
	import type { Widget, WidgetRow } from '$lib/types/dashboard';
	import { fetchWidget } from '$lib/api/dashboard';
	import { T } from '$lib/UI/theme.svelte';
	import { Line } from 'svelte-chartjs';
	import {
		Chart as ChartJS,
		CategoryScale,
		LinearScale,
		PointElement,
		LineElement,
		Title,
		Tooltip,
		Legend
	} from 'chart.js';

	ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

	let {
		widget,
		tableId,
		viewName,
		widgetId
	}: {
		widget: Widget;
		tableId: string;
		viewName: string;
		widgetId: string;
	} = $props();

	let rows = $state<WidgetRow[]>([]);
	let error = $state<string | null>(null);
	let status = $state<'loading' | 'loaded'>('loading');

	$effect(() => {
		fetchWidget(tableId, viewName, widgetId)
			.then((r: WidgetRow[]) => {
				rows = r;
			})
			.catch((e: Error) => {
				error = e.message;
			})
			.finally(() => {
				status = 'loaded';
			});
	});

	const chartData = $derived({
		labels: rows.map((r) => String(r[widget.binding.x ?? 'dim_0'] ?? '')),
		datasets: [
			{
				label: widget.title,
				data: rows.map((r) => Number(r[widget.binding.y ?? 'value'] ?? 0)),
				borderColor: 'rgba(139,92,246,1)',
				backgroundColor: 'rgba(139,92,246,0.1)',
				fill: true,
				tension: 0.3
			}
		]
	});

	const chartOptions = { responsive: true, maintainAspectRatio: false };
</script>

<div class="flex h-full flex-col gap-2" data-testid="widget-line" data-status={status}>
	<span class="text-sm font-medium {T.body} opacity-70">{widget.title}</span>
	{#if error}
		<span class="text-sm text-red-500" data-testid="widget-error">{error}</span>
	{:else}
		<div class="min-h-0 flex-1">
			<Line data={chartData} options={chartOptions} />
		</div>
	{/if}
</div>

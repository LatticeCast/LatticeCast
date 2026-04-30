<script lang="ts">
	import type { Widget, WidgetRow } from '$lib/types/dashboard';
	import { fetchWidget } from '$lib/api/dashboard';
	import { T } from '$lib/UI/theme.svelte';
	import { Pie } from 'svelte-chartjs';
	import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';

	ChartJS.register(ArcElement, Tooltip, Legend);

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

	const COLORS = [
		'rgba(139,92,246,0.8)',
		'rgba(59,130,246,0.8)',
		'rgba(16,185,129,0.8)',
		'rgba(245,158,11,0.8)',
		'rgba(239,68,68,0.8)',
		'rgba(236,72,153,0.8)'
	];

	const chartData = $derived({
		labels: rows.map((r) => String(r[widget.binding.label ?? 'dim_0'] ?? '')),
		datasets: [
			{
				data: rows.map((r) => Number(r[widget.binding.value ?? 'value'] ?? 0)),
				backgroundColor: rows.map((_, i) => COLORS[i % COLORS.length])
			}
		]
	});

	const chartOptions = { responsive: true, maintainAspectRatio: false };
</script>

<div class="flex h-full flex-col gap-2" data-testid="widget-pie" data-status={status}>
	<span class="text-sm font-medium {T.body} opacity-70">{widget.title}</span>
	{#if error}
		<span class="text-sm text-red-500" data-testid="widget-error">{error}</span>
	{:else}
		<div class="min-h-0 flex-1">
			<Pie data={chartData} options={chartOptions} />
		</div>
	{/if}
</div>

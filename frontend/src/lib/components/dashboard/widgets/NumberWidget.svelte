<script lang="ts">
	import type { Widget, WidgetRow } from '$lib/types/dashboard';
	import { fetchWidget } from '$lib/api/dashboard';
	import { T } from '$lib/UI/theme.svelte';

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

	let value = $state<number | string>('—');
	let error = $state<string | null>(null);
	let status = $state<'loading' | 'loaded'>('loading');

	$effect(() => {
		fetchWidget(tableId, viewName, widgetId)
			.then((rows: WidgetRow[]) => {
				const key = widget.binding.value ?? Object.keys(rows[0] ?? {})[0];
				value = (rows[0]?.[key] as number) ?? '—';
			})
			.catch((e: Error) => {
				error = e.message;
			})
			.finally(() => {
				status = 'loaded';
			});
	});
</script>

<div class="flex h-full flex-col justify-between" data-testid="widget-number" data-status={status}>
	<span class="text-sm font-medium {T.body} opacity-70">{widget.title}</span>
	{#if error}
		<span class="text-sm text-red-500" data-testid="widget-error">{error}</span>
	{:else}
		<span class="text-4xl font-bold {T.body}" data-testid="number-value">{value}</span>
	{/if}
</div>

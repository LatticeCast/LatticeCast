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
</script>

<div class="flex h-full flex-col gap-2" data-testid="widget-list" data-status={status}>
	<span class="text-sm font-medium {T.body} opacity-70">{widget.title}</span>
	{#if error}
		<span class="text-sm text-red-500" data-testid="widget-error">{error}</span>
	{:else}
		<div class="overflow-auto">
			<table class="w-full text-sm {T.body}" data-testid="list-table">
				{#if rows.length > 0}
					<thead>
						<tr>
							{#each Object.keys(rows[0]) as col (col)}
								<th class="px-2 py-1 text-left font-medium opacity-60">{col}</th>
							{/each}
						</tr>
					</thead>
				{/if}
				<tbody>
					{#each rows as row, i (i)}
						<tr class="border-opacity-10 border-t border-current" data-testid="widget-list-row-{i}">
							{#each Object.values(row) as cell, ci (ci)}
								<td class="px-2 py-1">{String(cell ?? '')}</td>
							{/each}
						</tr>
					{/each}
				</tbody>
			</table>
			{#if rows.length === 0}
				<p class="py-4 text-center text-sm opacity-50" data-testid="list-empty">No data</p>
			{/if}
		</div>
	{/if}
</div>

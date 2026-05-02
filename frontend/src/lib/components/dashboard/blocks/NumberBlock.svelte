<script lang="ts">
	import type { NumberBlock, BlockRow } from '$lib/types/dashboard';
	import { fetchBlockRows } from '$lib/api/dashboard';
	import { T } from '$lib/UI/theme.svelte';

	let {
		block,
		tableId,
		viewName,
		blockId
	}: {
		block: NumberBlock;
		tableId: string;
		viewName: string;
		blockId: string;
	} = $props();

	let value = $state<number | string>('—');
	let error = $state<string | null>(null);
	let status = $state<'loading' | 'loaded'>('loading');

	$effect(() => {
		fetchBlockRows(tableId, viewName, blockId)
			.then((rows: BlockRow[]) => {
				const raw = rows[0]?.[block.field];
				value = raw !== undefined && raw !== null ? (raw as number) : '—';
			})
			.catch((e: Error) => {
				error = e.message;
			})
			.finally(() => {
				status = 'loaded';
			});
	});
</script>

<div class="flex h-full flex-col justify-between" data-testid="block-number" data-status={status}>
	<span class="text-sm font-medium {T.body} opacity-70">{block.title}</span>
	{#if error}
		<span class="text-sm text-red-500" data-testid="block-error">{error}</span>
	{:else}
		<span class="text-4xl font-bold {T.body}" data-testid="number-value">{value}</span>
	{/if}
</div>

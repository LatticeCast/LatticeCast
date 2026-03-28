<script lang="ts">
	import type { Column, Row, ViewConfig } from '$lib/types/table';
	import { getChoices, getChoiceColor, getTagValues, formatDate } from './table.utils';

	let {
		columns,
		rows,
		viewConfig,
		onOpenExpand
	}: {
		columns: Column[];
		rows: Row[];
		viewConfig: ViewConfig;
		onOpenExpand: (row: Row) => void;
	} = $props();

	const groupByColId = $derived(viewConfig.config.group_by as string | undefined);
	const cardFields = $derived((viewConfig.config.card_fields as string[]) ?? []);

	const groupCol = $derived(groupByColId ? columns.find((c) => c.id === groupByColId) : undefined);

	const choices = $derived(groupCol ? getChoices(groupCol) : []);

	const lanes = $derived.by(() => {
		if (!groupByColId || !groupCol) return [];

		const buckets = new Map<string, Row[]>();
		for (const c of choices) buckets.set(c.value, []);
		buckets.set('', []);

		for (const row of rows) {
			const val = row.row_data[groupByColId];
			const key = val === null || val === undefined || val === '' ? '' : String(val);
			if (buckets.has(key)) {
				buckets.get(key)!.push(row);
			} else {
				buckets.get('')!.push(row);
			}
		}

		const result = choices.map((c) => ({ value: c.value, rows: buckets.get(c.value) ?? [] }));
		const uncategorized = buckets.get('') ?? [];
		if (uncategorized.length > 0) {
			result.push({ value: '', rows: uncategorized });
		}
		return result;
	});

	const cardColumns = $derived(
		cardFields.length > 0
			? cardFields.map((id) => columns.find((c) => c.id === id)).filter(Boolean)
			: (columns.slice(0, 3) as Column[])
	);

	function getLaneColor(value: string) {
		if (!groupCol || !value) return { bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-200' };
		return getChoiceColor(groupCol, value);
	}

	function renderFieldValue(col: Column, row: Row): string {
		const val = row.row_data[col.id];
		if (val === null || val === undefined) return '';
		if (col.type === 'checkbox') return val ? '✓' : '✗';
		if (col.type === 'date') return formatDate(String(val));
		if (col.type === 'tags') return getTagValues(row, col.id).join(', ');
		return String(val);
	}
</script>

{#if !groupByColId || !groupCol}
	<div class="flex h-64 items-center justify-center text-gray-400">
		<div class="text-center">
			<p class="text-sm">No group-by column configured.</p>
			<p class="mt-1 text-xs">Edit this view's config to set a group-by column.</p>
		</div>
	</div>
{:else}
	<div class="flex h-full gap-4 overflow-x-auto p-4">
		{#each lanes as lane (lane.value)}
			{@const color = getLaneColor(lane.value)}
			<div class="flex w-72 shrink-0 flex-col rounded-xl border border-gray-200 bg-gray-50">
				<!-- Lane header -->
				<div class="flex items-center gap-2 border-b border-gray-200 px-3 py-2.5">
					<span
						class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
					>
						{lane.value || 'Uncategorized'}
					</span>
					<span class="ml-auto text-xs text-gray-400">{lane.rows.length}</span>
				</div>

				<!-- Cards -->
				<div class="flex flex-col gap-2 overflow-y-auto p-2">
					{#if lane.rows.length === 0}
						<div class="rounded-lg border border-dashed border-gray-200 px-3 py-4 text-center">
							<p class="text-xs text-gray-400">No items</p>
						</div>
					{:else}
						{#each lane.rows as row (row.row_id)}
							<button
								class="w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-left shadow-sm transition hover:border-blue-300 hover:shadow-md"
								onclick={() => onOpenExpand(row)}
							>
								{#each cardColumns as col (col!.id)}
									{@const val = row.row_data[col!.id]}
									<div class="mb-1 last:mb-0">
										{#if col!.type === 'select' && val}
											{@const choiceColor = getChoiceColor(col!, String(val))}
											<span
												class="inline-flex items-center rounded-full border px-1.5 py-0.5 text-xs font-medium {choiceColor.bg} {choiceColor.text} {choiceColor.border}"
											>
												{val}
											</span>
										{:else if col!.type === 'tags'}
											<div class="flex flex-wrap gap-1">
												{#each getTagValues(row, col!.id) as tag, i (tag)}
													{@const tc = getChoiceColor(col!, tag)}
													<span
														class="inline-flex items-center rounded-full border px-1.5 py-0.5 text-xs {tc.bg} {tc.text} {tc.border}"
													>
														{tag}
													</span>
												{/each}
											</div>
										{:else if col!.type === 'checkbox'}
											<span class="text-sm {val ? 'text-green-600' : 'text-gray-300'}">
												{val ? '✓' : '✗'}
											</span>
										{:else if col!.type === 'url' && val}
											<a
												href={String(val)}
												target="_blank"
												rel="noopener noreferrer"
												class="truncate text-xs text-blue-600 hover:underline"
												onclick={(e) => e.stopPropagation()}
											>
												{val}
											</a>
										{:else if val !== null && val !== undefined && val !== ''}
											<span class="block truncate text-sm text-gray-700">
												{col!.type === 'date' ? formatDate(String(val)) : String(val)}
											</span>
										{/if}
									</div>
								{/each}
							</button>
						{/each}
					{/if}
				</div>
			</div>
		{/each}
	</div>
{/if}

<!-- routes/[workspace_id]/[table_id]/[row_id]/+page.svelte -->

<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { fetchTable, fetchRows, createRow } from '$lib/backend/tables';
	import {
		getChoiceColor,
		getTagValues,
		formatCellDate,
		isTemporalType
	} from '$lib/components/table/table.utils';
	import { BRAND } from '$lib/UI/brand';
	import type { Row, Table } from '$lib/types/table';
	import CreateTicketModal from '$lib/components/table/CreateTicketModal.svelte';

	const tableId = $derived($page.params.table_id ?? '');
	const rowNumberParam = $derived(parseInt($page.params.row_id ?? '0', 10));
	const workspaceId = $derived($page.params.workspace_id ?? '');

	let table = $state<Table | null>(null);
	let row = $state<Row | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let showCreateTicket = $state(false);

	const sortedCols = $derived(table ? table.columns : []);

	const badgeCols = $derived(
		sortedCols.filter((c) => ['select', 'tags', 'text', 'number', 'date', 'url'].includes(c.type))
	);

	const isTicketTable = $derived(!!table?.columns.find((c) => c.name === 'Key'));

	onMount(async () => {
		try {
			const [t, rows] = await Promise.all([
				fetchTable(tableId, $page.params.workspace_id),
				fetchRows(tableId, 0, 200)
			]);
			table = t;
			row = rows.find((r) => r.row_id === rowNumberParam) ?? null;
			if (!row) {
				error = 'Row not found';
				return;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load';
		} finally {
			loading = false;
		}
	});

	async function handleCreateTicket(rowData: Record<string, unknown>) {
		showCreateTicket = false;
		try {
			await createRow(tableId, { row_data: rowData });
		} catch {
			// best-effort
		}
	}

	function getRowTitle(): string {
		if (!row || !table) return String(rowNumberParam);
		const titleCol = table.columns.find((c) => c.name === 'Title');
		const keyCol = table.columns.find((c) => c.name === 'Key');
		const key = keyCol ? ((row.row_data[keyCol.column_id] as string) ?? '') : '';
		const title = titleCol ? ((row.row_data[titleCol.column_id] as string) ?? '') : '';
		if (key && title) return `${key}: ${title}`;
		return title || key || String(rowNumberParam);
	}
</script>

<svelte:head>
	<title>{getRowTitle()} — {BRAND}</title>
</svelte:head>

<div class="min-h-screen bg-gray-50">
	{#if loading}
		<div class="flex h-64 items-center justify-center text-sm text-gray-400">Loading…</div>
	{:else if error}
		<div class="flex h-64 items-center justify-center text-sm text-red-500">{error}</div>
	{:else if row && table}
		<div class="mx-auto max-w-4xl px-6 py-6">
			<!-- Actions bar -->
			<div class="mb-4 flex items-center justify-between">
				<a href="/{workspaceId}/{tableId}" class="text-sm text-blue-600 hover:underline">← Back</a>
				<button
					onclick={() => (showCreateTicket = true)}
					class="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-700 transition hover:bg-blue-100"
				>
					+ {isTicketTable ? 'New ticket' : 'Add row'}
				</button>
			</div>

			<!-- Badge fields at top -->
			<div class="mb-6 flex flex-wrap gap-2">
				{#each badgeCols as col (col.column_id)}
					{@const val = row.row_data[col.column_id]}
					{#if val !== null && val !== undefined && String(val) !== '' && !(Array.isArray(val) && val.length === 0)}
						{#if col.type === 'select'}
							{@const strVal = val as string}
							{@const color = getChoiceColor(col, strVal)}
							<span
								class="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium {color.cls}"
								style={color.style}
							>
								<span class="text-xs font-normal text-gray-400">{col.name}:</span>
								{strVal}
							</span>
						{:else if col.type === 'tags'}
							{@const tags = getTagValues(row, col.column_id)}
							{#each tags as tag (tag)}
								{@const color = getChoiceColor(col, tag)}
								<span
									class="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium {color.cls}"
									style={color.style}
								>
									{tag}
								</span>
							{/each}
						{:else if isTemporalType(col.type)}
							<span
								class="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2.5 py-0.5 text-xs text-gray-600"
							>
								<span class="font-normal text-gray-400">{col.name}:</span>
								{formatCellDate(val, col.type)}
							</span>
						{:else if col.type === 'url'}
							<!-- skip URL badges — shown in doc or fields section -->
						{:else}
							<span
								class="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2.5 py-0.5 text-xs text-gray-700"
							>
								<span class="font-normal text-gray-400">{col.name}:</span>
								{String(val)}
							</span>
						{/if}
					{/if}
				{/each}
			</div>

		</div>
	{/if}
</div>

{#if table}
	<CreateTicketModal
		show={showCreateTicket}
		columns={table.columns}
		onClose={() => (showCreateTicket = false)}
		onSubmit={handleCreateTicket}
	/>
{/if}

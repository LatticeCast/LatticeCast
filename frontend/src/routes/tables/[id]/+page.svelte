<!-- routes/tables/[id]/+page.svelte -->

<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { authStore } from '$lib/stores/auth.store';
	import {
		currentTable,
		columns,
		rows,
		loading,
		error,
		loadTable,
		refreshRows
	} from '$lib/stores/tables.store';
	import { fetchTables, createRow } from '$lib/backend/tables';

	let addingRow = $state(false);

	onMount(async () => {
		if (!$authStore?.role) {
			goto('/login');
			return;
		}
		const tableId = $page.params.id;
		try {
			const all = await fetchTables();
			const table = all.find((t) => t.id === tableId);
			if (!table) {
				goto('/tables');
				return;
			}
			await loadTable(table);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to load table');
		}
	});

	async function handleAddRow() {
		const tableId = $page.params.id;
		addingRow = true;
		error.set(null);
		try {
			await createRow(tableId, { data: {} });
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to add row');
		} finally {
			addingRow = false;
		}
	}

	function getCellValue(row: { data: Record<string, unknown> }, colId: string): string {
		const val = row.data[colId];
		if (val === null || val === undefined) return '';
		if (typeof val === 'boolean') return val ? '✓' : '';
		return String(val);
	}
</script>

<div class="min-h-screen bg-linear-to-br from-violet-600 via-purple-600 to-fuchsia-600">
	<!-- Header -->
	<div class="flex items-center gap-4 px-6 py-4">
		<button
			onclick={() => goto('/tables')}
			class="rounded-xl p-2 text-white/70 transition hover:bg-white/10 hover:text-white"
			aria-label="Back to tables"
		>
			<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
			</svg>
		</button>
		<h1 class="text-2xl font-bold text-white">
			{$currentTable?.name ?? 'Loading...'}
		</h1>
		<div class="ml-auto">
			<button
				onclick={handleAddRow}
				disabled={addingRow || $loading}
				class="rounded-2xl bg-white px-5 py-2 font-semibold text-purple-600 transition hover:bg-white/90 disabled:opacity-50"
			>
				{addingRow ? 'Adding...' : '+ Add Row'}
			</button>
		</div>
	</div>

	{#if $error}
		<div class="mx-6 mb-4 rounded-xl bg-red-500/20 px-4 py-3 text-red-100">{$error}</div>
	{/if}

	<!-- Spreadsheet -->
	<div class="overflow-x-auto px-6 pb-6">
		{#if $loading}
			<div class="pt-16 text-center text-white/70">Loading...</div>
		{:else if $columns.length === 0}
			<div class="rounded-3xl bg-white/10 p-8 text-center text-white/70">
				No columns defined yet.
			</div>
		{:else}
			<table class="w-full border-collapse rounded-2xl bg-white/10 text-white">
				<thead>
					<tr>
						{#each $columns.sort((a, b) => a.position - b.position) as col (col.id)}
							<th
								class="border-b border-white/20 px-4 py-3 text-left text-sm font-semibold uppercase tracking-wide text-white/80"
							>
								{col.name}
								<span class="ml-1 text-xs font-normal text-white/40">({col.type})</span>
							</th>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each $rows as row (row.id)}
						<tr class="border-b border-white/10 transition hover:bg-white/10">
							{#each $columns.sort((a, b) => a.position - b.position) as col (col.id)}
								<td class="px-4 py-3 text-sm text-white/90">
									{getCellValue(row, col.id)}
								</td>
							{/each}
						</tr>
					{:else}
						<tr>
							<td
								colspan={$columns.length}
								class="px-4 py-8 text-center text-sm text-white/50"
							>
								No rows yet. Click "+ Add Row" to start.
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</div>

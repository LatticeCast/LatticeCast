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
		refreshRows,
		refreshColumns
	} from '$lib/stores/tables.store';
	import { fetchTables, createRow, createColumn, deleteColumn, updateColumn, updateRow } from '$lib/backend/tables';
	import type { Column } from '$lib/types/table';

	const COLUMN_TYPES = ['text', 'number', 'date', 'select', 'checkbox', 'url'] as const;

	let addingRow = $state(false);

	// Add-column modal
	let showAddColumn = $state(false);
	let newColName = $state('');
	let newColType = $state<string>('text');
	let addingColumn = $state(false);

	// Inline rename
	let renamingColId = $state<string | null>(null);
	let renameValue = $state('');

	// Inline cell editing
	let editingCell = $state<{ rowId: string; colId: string } | null>(null);
	let editValue = $state<string>('');

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

	async function handleAddColumn() {
		if (!newColName.trim()) return;
		const tableId = $page.params.id;
		addingColumn = true;
		error.set(null);
		try {
			await createColumn(tableId, { name: newColName.trim(), type: newColType });
			await refreshColumns(tableId);
			showAddColumn = false;
			newColName = '';
			newColType = 'text';
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to add column');
		} finally {
			addingColumn = false;
		}
	}

	async function handleDeleteColumn(colId: string) {
		const tableId = $page.params.id;
		error.set(null);
		try {
			await deleteColumn(colId);
			await refreshColumns(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to delete column');
		}
	}

	function startRename(colId: string, currentName: string) {
		renamingColId = colId;
		renameValue = currentName;
	}

	async function commitRename(colId: string) {
		if (!renameValue.trim()) {
			renamingColId = null;
			return;
		}
		const tableId = $page.params.id;
		error.set(null);
		try {
			await updateColumn(colId, { name: renameValue.trim() });
			await refreshColumns(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to rename column');
		} finally {
			renamingColId = null;
		}
	}

	function getCellValue(row: { data: Record<string, unknown> }, colId: string): string {
		const val = row.data[colId];
		if (val === null || val === undefined) return '';
		if (typeof val === 'boolean') return val ? '✓' : '';
		return String(val);
	}

	function startEdit(rowId: string, col: Column, currentVal: unknown) {
		editingCell = { rowId, colId: col.id };
		if (col.type === 'checkbox') {
			editValue = String(!!currentVal);
		} else {
			editValue = currentVal === null || currentVal === undefined ? '' : String(currentVal);
		}
	}

	async function commitEdit(rowId: string, col: Column) {
		if (!editingCell) return;
		editingCell = null;

		const row = $rows.find((r) => r.id === rowId);
		if (!row) return;

		let parsed: unknown = editValue;
		if (col.type === 'number') {
			parsed = editValue === '' ? null : Number(editValue);
		} else if (col.type === 'checkbox') {
			parsed = editValue === 'true';
		} else if (editValue === '') {
			parsed = null;
		}

		const newData = { ...row.data, [col.id]: parsed };
		error.set(null);
		try {
			await updateRow(rowId, { data: newData });
			await refreshRows($page.params.id);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update cell');
		}
	}

	async function toggleCheckbox(rowId: string, col: Column) {
		const row = $rows.find((r) => r.id === rowId);
		if (!row) return;
		const current = !!row.data[col.id];
		const newData = { ...row.data, [col.id]: !current };
		error.set(null);
		try {
			await updateRow(rowId, { data: newData });
			await refreshRows($page.params.id);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update cell');
		}
	}

	function getSelectOptions(col: Column): string[] {
		const opts = col.options;
		if (Array.isArray(opts?.choices)) return opts.choices as string[];
		return [];
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
		<div class="ml-auto flex gap-2">
			<button
				onclick={() => { showAddColumn = true; }}
				disabled={$loading}
				class="rounded-2xl bg-white/20 px-5 py-2 font-semibold text-white transition hover:bg-white/30 disabled:opacity-50"
			>
				+ Add Column
			</button>
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
				No columns defined yet. Click "+ Add Column" to start.
			</div>
		{:else}
			<table class="w-full border-collapse rounded-2xl bg-white/10 text-white">
				<thead>
					<tr>
						{#each $columns.sort((a, b) => a.position - b.position) as col (col.id)}
							<th
								class="border-b border-white/20 px-4 py-3 text-left text-sm font-semibold uppercase tracking-wide text-white/80"
							>
								<div class="flex items-center gap-2">
									{#if renamingColId === col.id}
										<input
											class="rounded bg-white/20 px-2 py-0.5 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
											bind:value={renameValue}
											onblur={() => commitRename(col.id)}
											onkeydown={(e) => {
												if (e.key === 'Enter') commitRename(col.id);
												if (e.key === 'Escape') renamingColId = null;
											}}
											autofocus
										/>
									{:else}
										<span
											ondblclick={() => startRename(col.id, col.name)}
											class="cursor-text"
											title="Double-click to rename"
										>
											{col.name}
											<span class="ml-1 text-xs font-normal text-white/40">({col.type})</span>
										</span>
									{/if}
									<button
										onclick={() => handleDeleteColumn(col.id)}
										class="ml-auto rounded p-0.5 text-white/30 transition hover:bg-red-500/30 hover:text-red-300"
										aria-label="Delete column {col.name}"
										title="Delete column"
									>
										<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
										</svg>
									</button>
								</div>
							</th>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each $rows as row (row.id)}
						<tr class="border-b border-white/10 transition hover:bg-white/5">
							{#each $columns.sort((a, b) => a.position - b.position) as col (col.id)}
								<td
									class="px-2 py-1 text-sm text-white/90"
									onclick={() => {
										if (col.type !== 'checkbox' && !(editingCell?.rowId === row.id && editingCell?.colId === col.id)) {
											startEdit(row.id, col, row.data[col.id]);
										}
									}}
								>
									{#if editingCell?.rowId === row.id && editingCell?.colId === col.id}
										{#if col.type === 'select'}
											{@const opts = getSelectOptions(col)}
											<select
												class="w-full rounded bg-white/20 px-2 py-1 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
												bind:value={editValue}
												onblur={() => commitEdit(row.id, col)}
												onchange={() => commitEdit(row.id, col)}
												autofocus
											>
												<option value="">—</option>
												{#each opts as opt}
													<option value={opt}>{opt}</option>
												{/each}
											</select>
										{:else if col.type === 'number'}
											<input
												type="number"
												class="w-full rounded bg-white/20 px-2 py-1 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
												bind:value={editValue}
												onblur={() => commitEdit(row.id, col)}
												onkeydown={(e) => {
													if (e.key === 'Enter') commitEdit(row.id, col);
													if (e.key === 'Escape') editingCell = null;
												}}
												autofocus
											/>
										{:else if col.type === 'date'}
											<input
												type="date"
												class="w-full rounded bg-white/20 px-2 py-1 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
												bind:value={editValue}
												onblur={() => commitEdit(row.id, col)}
												onkeydown={(e) => {
													if (e.key === 'Enter') commitEdit(row.id, col);
													if (e.key === 'Escape') editingCell = null;
												}}
												autofocus
											/>
										{:else}
											<input
												type={col.type === 'url' ? 'url' : 'text'}
												class="w-full rounded bg-white/20 px-2 py-1 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
												bind:value={editValue}
												onblur={() => commitEdit(row.id, col)}
												onkeydown={(e) => {
													if (e.key === 'Enter') commitEdit(row.id, col);
													if (e.key === 'Escape') editingCell = null;
												}}
												autofocus
											/>
										{/if}
									{:else if col.type === 'checkbox'}
										<input
											type="checkbox"
											class="h-4 w-4 cursor-pointer accent-fuchsia-400"
											checked={!!row.data[col.id]}
											onchange={() => toggleCheckbox(row.id, col)}
										/>
									{:else}
										<span
											class="block min-h-[1.5rem] min-w-[4rem] cursor-text px-2 py-1"
											title="Click to edit"
										>
											{getCellValue(row, col.id)}
										</span>
									{/if}
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

<!-- Add Column Modal -->
{#if showAddColumn}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
		onclick={(e) => { if (e.target === e.currentTarget) showAddColumn = false; }}
		role="dialog"
		aria-modal="true"
		aria-label="Add column"
	>
		<div class="w-full max-w-sm rounded-3xl bg-white p-8 shadow-2xl">
			<h2 class="mb-6 text-xl font-bold text-gray-800">Add Column</h2>
			<div class="mb-4">
				<label class="mb-1 block text-sm font-medium text-gray-600" for="col-name">Name</label>
				<input
					id="col-name"
					class="w-full rounded-xl border border-gray-200 px-4 py-2 text-gray-800 outline-none focus:border-purple-400 focus:ring-1 focus:ring-purple-400"
					bind:value={newColName}
					placeholder="Column name"
					onkeydown={(e) => { if (e.key === 'Enter') handleAddColumn(); }}
					autofocus
				/>
			</div>
			<div class="mb-6">
				<label class="mb-1 block text-sm font-medium text-gray-600" for="col-type">Type</label>
				<select
					id="col-type"
					class="w-full rounded-xl border border-gray-200 px-4 py-2 text-gray-800 outline-none focus:border-purple-400 focus:ring-1 focus:ring-purple-400"
					bind:value={newColType}
				>
					{#each COLUMN_TYPES as t}
						<option value={t}>{t}</option>
					{/each}
				</select>
			</div>
			<div class="flex gap-3">
				<button
					onclick={() => { showAddColumn = false; newColName = ''; newColType = 'text'; }}
					class="flex-1 rounded-2xl border border-gray-200 px-4 py-2 font-semibold text-gray-600 transition hover:bg-gray-50"
				>
					Cancel
				</button>
				<button
					onclick={handleAddColumn}
					disabled={addingColumn || !newColName.trim()}
					class="flex-1 rounded-2xl bg-linear-to-r from-violet-500 to-fuchsia-500 px-4 py-2 font-semibold text-white transition hover:shadow-lg disabled:opacity-50"
				>
					{addingColumn ? 'Adding...' : 'Add Column'}
				</button>
			</div>
		</div>
	</div>
{/if}

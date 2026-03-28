<!-- routes/tables/+page.svelte -->

<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { authStore } from '$lib/stores/auth.store';
	import { fetchTables, createTable, deleteTable } from '$lib/backend/tables';
	import { fetchWorkspaces } from '$lib/backend/workspaces';
	import type { Table, Workspace } from '$lib/types/table';

	let tables = $state<Table[]>([]);
	let workspaces = $state<Workspace[]>([]);
	let currentWorkspace = $state<Workspace | null>(null);
	let loading = $state(true);
	let error = $state('');
	let creating = $state(false);
	let newTableName = $state('');

	const filteredTables = $derived(
		currentWorkspace
			? tables.filter((t) => t.workspace_id === currentWorkspace!.workspace_id)
			: tables
	);

	onMount(async () => {
		if (!$authStore?.role) {
			goto('/login');
			return;
		}
		await loadData();
	});

	async function loadData() {
		loading = true;
		error = '';
		try {
			const [ws, tbls] = await Promise.all([fetchWorkspaces(), fetchTables()]);
			workspaces = ws;
			tables = tbls;
			if (ws.length > 0 && !currentWorkspace) {
				currentWorkspace = ws[0];
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load data';
		} finally {
			loading = false;
		}
	}

	async function handleCreate() {
		const name = newTableName.trim();
		if (!name || !currentWorkspace) return;
		creating = true;
		error = '';
		try {
			const table = await createTable({ name, workspace_id: currentWorkspace.workspace_id });
			tables = [...tables, table];
			newTableName = '';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create table';
		} finally {
			creating = false;
		}
	}

	async function handleDelete(tableId: string) {
		error = '';
		try {
			await deleteTable(tableId);
			tables = tables.filter((t) => t.table_id !== tableId);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete table';
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') handleCreate();
	}
</script>

<div class="min-h-screen bg-gray-50 p-6">
	<div class="mx-auto max-w-2xl pt-16">
		<div class="mb-6 rounded-2xl bg-linear-to-r from-blue-600 to-blue-500 px-6 py-5">
			<h1 class="text-3xl font-bold text-white">Tables</h1>
		</div>

		<!-- Workspace Selector -->
		{#if workspaces.length > 0}
			<div class="mb-4 flex flex-wrap gap-2">
				{#each workspaces as ws (ws.workspace_id)}
					<button
						onclick={() => (currentWorkspace = ws)}
						class="rounded-xl px-4 py-2 text-sm font-medium shadow-sm transition {currentWorkspace?.workspace_id === ws.workspace_id
							? 'bg-blue-600 text-white'
							: 'bg-white text-gray-700 hover:bg-blue-50 hover:text-blue-600'}"
					>
						{ws.name}
					</button>
				{/each}
			</div>
		{/if}

		<!-- Create Table -->
		<div class="mb-6 flex gap-2">
			<input
				type="text"
				bind:value={newTableName}
				onkeydown={handleKeydown}
				placeholder="New table name..."
				class="flex-1 rounded-2xl border-2 border-gray-200 bg-white px-4 py-3 text-gray-800 placeholder-gray-400 focus:border-blue-500 focus:outline-none"
			/>
			<button
				onclick={handleCreate}
				disabled={creating || !newTableName.trim() || !currentWorkspace}
				class="rounded-2xl bg-blue-600 px-6 py-3 font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
			>
				{creating ? 'Creating...' : 'Create'}
			</button>
		</div>

		{#if error}
			<div class="mb-4 rounded-xl bg-red-50 px-4 py-3 text-red-600">{error}</div>
		{/if}

		<!-- Tables List -->
		{#if loading}
			<div class="text-center text-gray-500">Loading...</div>
		{:else if filteredTables.length === 0}
			<div class="rounded-3xl bg-white p-8 text-center text-gray-400 shadow-sm">
				No tables yet. Create one above.
			</div>
		{:else}
			<div class="space-y-2">
				{#each filteredTables as table (table.table_id)}
					<div
						class="flex items-center gap-3 rounded-2xl bg-white px-4 py-4 shadow-sm transition hover:bg-blue-50"
					>
						<button
							onclick={() => goto(`/${table.workspace_id}/${table.table_id}`)}
							class="flex-1 text-left font-medium text-gray-800"
						>
							{table.name}
						</button>
						<button
							onclick={() => handleDelete(table.table_id)}
							class="rounded-xl p-2 text-gray-400 transition hover:bg-red-50 hover:text-red-500"
							aria-label="Delete table"
						>
							<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
								/>
							</svg>
						</button>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>

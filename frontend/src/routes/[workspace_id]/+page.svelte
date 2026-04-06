<!-- routes/[workspace_id]/+page.svelte — tables list filtered to this workspace -->

<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { authStore } from '$lib/stores/auth.store';
	import { fetchTables, createTable, updateTable, deleteTable, createPmTemplate } from '$lib/backend/tables';
	import { fetchWorkspaces, updateWorkspace, deleteWorkspace } from '$lib/backend/workspaces';
	import { currentTable, pageTitle } from '$lib/stores/tables.store';
	import type { Table, Workspace } from '$lib/types/table';

	function wsSlug(name: string): string {
		return name.toLowerCase().replace(/\s+/g, '-');
	}

	let tables = $state<Table[]>([]);
	let workspaces = $state<Workspace[]>([]);
	let currentWorkspace = $state<Workspace | null>(null);
	let loading = $state(true);
	let error = $state('');
	let creating = $state(false);
	let newTableName = $state('');
	let showTemplateModal = $state(false);
	let templateName = $state('');
	let creatingTemplate = $state(false);

	// Workspace settings dialog
	let wsSettingsTarget = $state<Workspace | null>(null);
	let wsRenameValue = $state('');
	let wsSaving = $state(false);
	let wsSettingsError = $state('');

	function openWsSettings(ws: Workspace, e: MouseEvent) {
		e.stopPropagation();
		wsSettingsTarget = ws;
		wsRenameValue = ws.workspace_name;
		wsSettingsError = '';
	}

	function closeWsSettings() {
		wsSettingsTarget = null;
		wsRenameValue = '';
		wsSettingsError = '';
	}

	async function handleWsRename() {
		if (!wsSettingsTarget) return;
		const name = wsRenameValue.trim();
		if (!name || name === wsSettingsTarget.workspace_name) { closeWsSettings(); return; }
		wsSaving = true;
		wsSettingsError = '';
		try {
			const updated = await updateWorkspace(wsSettingsTarget.workspace_id, { name });
			workspaces = workspaces.map((w) => w.workspace_id === updated.workspace_id ? updated : w);
			if (currentWorkspace?.workspace_id === updated.workspace_id) {
				currentWorkspace = updated;
				goto(`/${wsSlug(updated.workspace_name)}`, { replaceState: true });
			}
			closeWsSettings();
		} catch (e) {
			wsSettingsError = e instanceof Error ? e.message : 'Failed to rename workspace';
		} finally {
			wsSaving = false;
		}
	}

	async function handleWsDelete() {
		if (!wsSettingsTarget) return;
		if (!confirm(`Delete workspace "${wsSettingsTarget.workspace_name}"? This cannot be undone.`)) return;
		wsSaving = true;
		wsSettingsError = '';
		try {
			await deleteWorkspace(wsSettingsTarget.workspace_id);
			workspaces = workspaces.filter((w) => w.workspace_id !== wsSettingsTarget!.workspace_id);
			tables = tables.filter((t) => t.workspace_id !== wsSettingsTarget!.workspace_id);
			if (currentWorkspace?.workspace_id === wsSettingsTarget.workspace_id) {
				const next = workspaces[0] ?? null;
				currentWorkspace = next;
				if (next) {
					goto(`/${wsSlug(next.workspace_name)}`, { replaceState: true });
				} else {
					goto('/tables', { replaceState: true });
				}
			}
			closeWsSettings();
		} catch (e) {
			wsSettingsError = e instanceof Error ? e.message : 'Failed to delete workspace';
		} finally {
			wsSaving = false;
		}
	}

	const filteredTables = $derived(
		currentWorkspace
			? tables.filter((t) => t.workspace_id === currentWorkspace!.workspace_id)
			: tables
	);

	function switchWorkspace(ws: Workspace) {
		currentWorkspace = ws;
		goto(`/${wsSlug(ws.workspace_name)}`);
	}

	onMount(async () => {
		if (!$authStore?.role) {
			goto('/login');
			return;
		}
		currentTable.set(null);
		pageTitle.set('Tables');
		await loadData();
	});

	onDestroy(() => {
		pageTitle.set('');
	});

	async function loadData() {
		loading = true;
		error = '';
		try {
			const [ws, tbls] = await Promise.all([fetchWorkspaces(), fetchTables()]);
			workspaces = ws;
			tables = tbls;

			// Resolve workspace from URL param
			const urlParam = $page.params.workspace_id;
			const matched =
				ws.find((w) => w.workspace_id === urlParam) ??
				ws.find((w) => wsSlug(w.workspace_name) === urlParam) ??
				ws[0] ??
				null;
			currentWorkspace = matched;

			// Correct URL if slug drifted (e.g. user typed UUID or old slug)
			if (matched && wsSlug(matched.workspace_name) !== urlParam) {
				goto(`/${wsSlug(matched.workspace_name)}`, { replaceState: true });
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

	// Table settings dialog
	let tableSettingsTarget = $state<Table | null>(null);
	let tableRenameValue = $state('');
	let tableSaving = $state(false);
	let tableSettingsError = $state('');

	function openTableSettings(table: Table, e: MouseEvent) {
		e.stopPropagation();
		tableSettingsTarget = table;
		tableRenameValue = table.name;
		tableSettingsError = '';
	}

	function closeTableSettings() {
		tableSettingsTarget = null;
		tableRenameValue = '';
		tableSettingsError = '';
	}

	async function handleTableRename() {
		if (!tableSettingsTarget) return;
		const name = tableRenameValue.trim();
		if (!name || name === tableSettingsTarget.name) { closeTableSettings(); return; }
		const wsId = tableSettingsTarget.workspace_id;
		const duplicate = tables.some(
			(t) => t.workspace_id === wsId && t.name === name && t.table_id !== tableSettingsTarget!.table_id
		);
		if (duplicate) {
			tableSettingsError = `A table named "${name}" already exists in this workspace.`;
			return;
		}
		tableSaving = true;
		tableSettingsError = '';
		try {
			const updated = await updateTable(tableSettingsTarget.table_id, { name });
			tables = tables.map((t) => t.table_id === updated.table_id ? updated : t);
			closeTableSettings();
		} catch (e) {
			tableSettingsError = e instanceof Error ? e.message : 'Failed to rename table';
		} finally {
			tableSaving = false;
		}
	}

	async function handleTableDelete() {
		if (!tableSettingsTarget) return;
		if (!confirm(`Delete table "${tableSettingsTarget.name}"? This cannot be undone.`)) return;
		tableSaving = true;
		tableSettingsError = '';
		try {
			await deleteTable(tableSettingsTarget.table_id);
			tables = tables.filter((t) => t.table_id !== tableSettingsTarget!.table_id);
			closeTableSettings();
		} catch (e) {
			tableSettingsError = e instanceof Error ? e.message : 'Failed to delete table';
		} finally {
			tableSaving = false;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') handleCreate();
	}

	async function handlePmTemplate() {
		const name = templateName.trim();
		if (!name || !currentWorkspace) return;
		creatingTemplate = true;
		error = '';
		try {
			const table = await createPmTemplate(name, currentWorkspace.workspace_id);
			tables = [...tables, table];
			showTemplateModal = false;
			templateName = '';
			goto(`/${table.workspace_id}/${table.table_id}`);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create template';
		} finally {
			creatingTemplate = false;
		}
	}
</script>

<div class="min-h-screen bg-gray-50 p-6">
	<div class="mx-auto max-w-2xl pt-4">

		<!-- Workspace Selector -->
		{#if workspaces.length > 0}
			<div class="mb-4 flex flex-wrap gap-2">
				{#each workspaces as ws (ws.workspace_id)}
					<div class="flex items-center rounded-xl shadow-sm {currentWorkspace?.workspace_id === ws.workspace_id ? 'bg-blue-600' : 'bg-white'}">
						<button
							onclick={() => switchWorkspace(ws)}
							class="rounded-l-xl px-4 py-2 text-sm font-medium transition {currentWorkspace?.workspace_id === ws.workspace_id
								? 'text-white'
								: 'text-gray-700 hover:bg-blue-50 hover:text-blue-600'}"
						>
							{ws.workspace_name}
						</button>
						<button
							onclick={(e) => openWsSettings(ws, e)}
							class="rounded-r-xl px-2 py-2 text-sm transition {currentWorkspace?.workspace_id === ws.workspace_id
								? 'text-blue-200 hover:text-white'
								: 'text-gray-400 hover:bg-gray-100 hover:text-gray-600'}"
							aria-label="Workspace settings"
							title="Workspace settings"
						>
							<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
									d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
							</svg>
						</button>
					</div>
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
			<button
				onclick={() => { showTemplateModal = true; templateName = ''; }}
				disabled={!currentWorkspace}
				class="rounded-2xl border-2 border-blue-200 bg-white px-4 py-3 font-semibold text-blue-600 transition hover:bg-blue-50 disabled:opacity-50"
			>
				From Template
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
							onclick={(e) => openTableSettings(table, e)}
							class="rounded-xl p-2 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
							aria-label="Table settings"
							title="Table settings"
						>
							<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
									d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
							</svg>
						</button>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>

<!-- Table Settings Dialog -->
{#if tableSettingsTarget}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
		onclick={closeTableSettings}
		role="dialog"
		aria-modal="true"
	>
		<div
			class="w-full max-w-sm rounded-3xl bg-white p-6 shadow-xl"
			onclick={(e) => e.stopPropagation()}
		>
			<h2 class="mb-4 text-lg font-bold text-gray-900">Table Settings</h2>

			<div class="mb-4">
				<label class="mb-1 block text-sm font-medium text-gray-700" for="table-rename-input">Name</label>
				<input
					id="table-rename-input"
					type="text"
					bind:value={tableRenameValue}
					onkeydown={(e) => { if (e.key === 'Enter') handleTableRename(); if (e.key === 'Escape') closeTableSettings(); }}
					class="w-full rounded-xl border-2 border-gray-200 px-3 py-2 text-gray-800 focus:border-blue-500 focus:outline-none"
				/>
			</div>

			{#if tableSettingsError}
				<div class="mb-3 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-600">{tableSettingsError}</div>
			{/if}

			<div class="flex items-center justify-between gap-2">
				<button
					onclick={handleTableDelete}
					disabled={tableSaving}
					class="rounded-xl px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
				>
					Delete table
				</button>
				<div class="flex gap-2">
					<button
						onclick={closeTableSettings}
						class="rounded-xl px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
					>
						Cancel
					</button>
					<button
						onclick={handleTableRename}
						disabled={tableSaving || !tableRenameValue.trim()}
						class="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
					>
						{tableSaving ? 'Saving...' : 'Save'}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

<!-- Workspace Settings Dialog -->
{#if wsSettingsTarget}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
		onclick={closeWsSettings}
		role="dialog"
		aria-modal="true"
	>
		<div
			class="w-full max-w-sm rounded-3xl bg-white p-6 shadow-xl"
			onclick={(e) => e.stopPropagation()}
		>
			<h2 class="mb-4 text-lg font-bold text-gray-900">Workspace Settings</h2>

			<div class="mb-4">
				<label class="mb-1 block text-sm font-medium text-gray-700" for="ws-rename-input">Name</label>
				<input
					id="ws-rename-input"
					type="text"
					bind:value={wsRenameValue}
					onkeydown={(e) => { if (e.key === 'Enter') handleWsRename(); if (e.key === 'Escape') closeWsSettings(); }}
					class="w-full rounded-xl border-2 border-gray-200 px-3 py-2 text-gray-800 focus:border-blue-500 focus:outline-none"
				/>
			</div>

			{#if wsSettingsError}
				<div class="mb-3 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-600">{wsSettingsError}</div>
			{/if}

			<div class="flex items-center justify-between gap-2">
				<button
					onclick={handleWsDelete}
					disabled={wsSaving}
					class="rounded-xl px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
				>
					Delete workspace
				</button>
				<div class="flex gap-2">
					<button
						onclick={closeWsSettings}
						class="rounded-xl px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
					>
						Cancel
					</button>
					<button
						onclick={handleWsRename}
						disabled={wsSaving || !wsRenameValue.trim()}
						class="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
					>
						{wsSaving ? 'Saving...' : 'Save'}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

<!-- Template Gallery Modal -->
{#if showTemplateModal}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
		onclick={() => (showTemplateModal = false)}
		role="dialog"
		aria-modal="true"
	>
		<div
			class="w-full max-w-md rounded-3xl bg-white p-6 shadow-xl"
			onclick={(e) => e.stopPropagation()}
		>
			<h2 class="mb-4 text-xl font-bold text-gray-900">New from Template</h2>

			<!-- PM Project Option -->
			<div class="mb-5 rounded-2xl border-2 border-blue-200 bg-blue-50 p-4">
				<div class="mb-1 flex items-center gap-2">
					<span class="text-lg">📋</span>
					<span class="font-semibold text-blue-800">PM Project</span>
				</div>
				<p class="mb-3 text-sm text-blue-700">
					Project management with Key, Title, Status, Priority, Assignee, dates, and Sprint Board + Roadmap views.
				</p>
				<input
					type="text"
					bind:value={templateName}
					placeholder="Project name..."
					class="w-full rounded-xl border-2 border-blue-200 bg-white px-3 py-2 text-gray-800 placeholder-gray-400 focus:border-blue-500 focus:outline-none"
				/>
			</div>

			<div class="flex justify-end gap-2">
				<button
					onclick={() => (showTemplateModal = false)}
					class="rounded-2xl px-4 py-2 text-gray-600 hover:bg-gray-100"
				>
					Cancel
				</button>
				<button
					onclick={handlePmTemplate}
					disabled={creatingTemplate || !templateName.trim()}
					class="rounded-2xl bg-linear-to-r from-blue-600 to-blue-500 px-5 py-2 font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
				>
					{creatingTemplate ? 'Creating...' : 'Create PM Project'}
				</button>
			</div>
		</div>
	</div>
{/if}

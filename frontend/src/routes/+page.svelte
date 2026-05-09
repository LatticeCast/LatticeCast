<!--routes/+page.svelte — redirects to /<workspace_name>/ or shows empty state-->

<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { authStore } from '$lib/stores/auth.store';
	import { fetchWorkspaces } from '$lib/backend/workspaces';
	import { currentTable, pageTitle } from '$lib/stores/tables.store';
	import { T } from '$lib/UI/theme.svelte';
	import CreateWorkspaceModal from '$lib/components/sidebar/CreateWorkspaceModal.svelte';
	import type { Workspace } from '$lib/types/table';

	let workspaces = $state<Workspace[]>([]);
	let loading = $state(true);
	let error = $state('');
	let showCreateWorkspace = $state(false);

	onMount(async () => {
		if (!$authStore?.role) {
			goto('/login');
			return;
		}
		currentTable.set(null);
		pageTitle.set('');
		try {
			const ws = await fetchWorkspaces();
			workspaces = ws;
			if (ws.length > 0) {
				const lastName =
					typeof localStorage !== 'undefined' ? localStorage.getItem('lastWorkspace') : null;
				const target = lastName ? (ws.find((w) => w.workspace_name === lastName) ?? ws[0]) : ws[0];
				goto(`/${encodeURIComponent(target.workspace_name)}/`, { replaceState: true });
				return;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load workspaces';
		} finally {
			loading = false;
		}
	});

	onDestroy(() => {
		pageTitle.set('');
	});
</script>

<div class="{T.pageBg} min-h-screen p-6">
	<div class="mx-auto max-w-2xl pt-4">
		{#if error}
			<div class="mb-4 rounded-xl bg-red-50 px-4 py-3 text-red-600">{error}</div>
		{/if}
		{#if loading}
			<div class="text-center {T.muted}">Loading...</div>
		{:else if workspaces.length === 0}
			<div class="rounded-3xl {T.cardBg} p-8 text-center {T.muted} shadow-sm">
				<p class="mb-4">No workspaces yet.</p>
				<button
					data-testid="new-workspace-btn"
					onclick={() => (showCreateWorkspace = true)}
					class="rounded-2xl bg-blue-600 px-5 py-2.5 font-semibold text-white transition hover:bg-blue-700"
				>
					+ New Workspace
				</button>
			</div>
		{/if}
	</div>
</div>

<CreateWorkspaceModal
	show={showCreateWorkspace}
	onClose={() => (showCreateWorkspace = false)}
	onCreated={(ws) => {
		showCreateWorkspace = false;
		goto(`/${encodeURIComponent(ws.workspace_name)}/`);
	}}
/>

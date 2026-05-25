<!--routes/+page.svelte — redirects to /<workspace_name>/ or shows empty state-->

<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import {
		currentTableId,
		workspaces as workspacesStore,
		initSidebar
	} from '$lib/stores/table_schemas.store';
	import { get } from 'svelte/store';
	import { T } from '$lib/UI/theme.svelte';
	import CreateWorkspaceModal from '$lib/components/sidebar/CreateWorkspaceModal.svelte';

	let loading = $state(true);
	let error = $state('');
	let showCreateWorkspace = $state(false);

	onMount(async () => {
		currentTableId.set(null);
		try {
			await initSidebar();
			const ws = get(workspacesStore);
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

	onDestroy(() => {});
</script>

<div class="{T.pageBg} min-h-screen p-6">
	<div class="mx-auto max-w-2xl pt-4">
		{#if error}
			<div class="mb-4 rounded-xl bg-red-50 px-4 py-3 text-red-600">{error}</div>
		{/if}
		{#if loading}
			<div class="text-center {T.muted}">Loading...</div>
		{:else if $workspacesStore.length === 0}
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

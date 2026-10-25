<!--routes/+layout.svelte-->

<script lang="ts">
	import '../app.css';
	import { goto, afterNavigate } from '$app/navigation';
	import { page, navigating } from '$app/stores';
	import { authStore, logout } from '$lib/stores/auth.store';
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import {
		workspaces,
		tables,
		tablesByWorkspace,
		initSidebar,
		resetSidebar
	} from '$lib/stores/table_schemas.store';
	import { SvelteSet } from 'svelte/reactivity';
	import { hydrateFromServer } from '$lib/stores/settings.store';
	import { fetchMe } from '$lib/backend/auth';
	import { fetchAnnouncements } from '$lib/backend/announcements';
	import { setAnnouncements } from '$lib/stores/announcement.store';
	import type { Workspace } from '$lib/types/table';
	import CreateWorkspaceModal from '$lib/components/sidebar/CreateWorkspaceModal.svelte';
	import Sidebar from '$lib/components/sidebar/Sidebar.svelte';
	import TopBar from '$lib/components/layout/TopBar.svelte';
	import { isUuid, prettifyWorkspacePathname, navigate } from '$lib/utils/url';
	import { findTableForPath } from '$lib/utils/table-route';

	let { children } = $props();
	let menuOpen = $state(false);
	let showCreateWorkspace = $state(false);

	const expandedWorkspaces = new SvelteSet<string>();

	async function refreshSidebar() {
		await initSidebar();
		expandedWorkspaces.clear();
		for (const ws of $workspaces) {
			if ($tablesByWorkspace[ws.workspace_id]?.length) expandedWorkspaces.add(ws.workspace_id);
		}
		prettifyCurrentUrl();
	}

	function prettifyCurrentUrl() {
		if (!browser) return;
		const wsParam = $page.params.workspace_id;
		if (!wsParam) return;
		const ws = isUuid(wsParam)
			? $workspaces.find((w) => w.workspace_id === wsParam)
			: $workspaces.find((w) => w.workspace_name.toLowerCase() === wsParam.toLowerCase());
		if (!ws) return;
		let newPathname = prettifyWorkspacePathname($page.url.pathname, wsParam, ws.workspace_name);
		const tableParam = $page.params.table_id;
		if (tableParam) {
			const table = findTableForPath(wsParam, tableParam, $workspaces, $tables);
			if (!table) return;
			newPathname = `/${encodeURIComponent(ws.workspace_name)}/${encodeURIComponent(table.table_name)}`;
			if ($page.params.row_id) newPathname += `/${encodeURIComponent($page.params.row_id)}`;
		}
		if (newPathname !== $page.url.pathname) {
			history.replaceState(history.state, '', newPathname + $page.url.search + $page.url.hash);
		}
	}

	// Store subscription and initial announcement request are integrations with
	// external state. Keeping them in onMount avoids reactive effects that
	// accidentally re-fetch when unrelated render dependencies change.
	onMount(() => {
		void fetchAnnouncements().catch(() => {
			// Announcements are best-effort; the shared layout remains usable without them.
			setAnnouncements([]);
		});

		return authStore.subscribe((auth) => {
			if (auth?.accessToken) {
				void refreshSidebar();
				void hydrateUserConfig(auth.accessToken);
				return;
			}
			resetSidebar();
			expandedWorkspaces.clear();
		});
	});

	async function hydrateUserConfig(accessToken: string) {
		try {
			const me = await fetchMe(accessToken);
			// Always call it, config or not: it is what marks the settings store
			// as safe to write back from (see settings.store.ts).
			hydrateFromServer(me?.config);
		} catch {
			// best-effort — local cache stays in effect
		}
	}

	function toggleWorkspace(wsId: string) {
		if (expandedWorkspaces.has(wsId)) expandedWorkspaces.delete(wsId);
		else expandedWorkspaces.add(wsId);
	}

	function onWorkspaceCreated(ws: Workspace) {
		showCreateWorkspace = false;
		navigate(`/${encodeURIComponent(ws.workspace_name)}/`);
	}

	afterNavigate(({ from }) => {
		prettifyCurrentUrl();
		if (!from || !$authStore?.accessToken) return;
		const wsId = $page.params.workspace_id;
		if (!wsId) return;
		const decoded = decodeURIComponent(wsId);
		const ws = $workspaces.find((w) => w.workspace_id === wsId || w.workspace_name === decoded);
		if (!ws) {
			refreshSidebar();
			return;
		}
		const tableParam = $page.params.table_id;
		if (tableParam) {
			const known = !!findTableForPath(wsId, tableParam, $workspaces, $tables);
			if (!known) refreshSidebar();
		}
	});

	const handleLogout = () => {
		logout();
		menuOpen = false;
		goto('/login');
	};
</script>

<svelte:head></svelte:head>

<div class="flex h-screen overflow-hidden" class:navigating-wait={!!$navigating}>
	<!-- Sidebar: full height, beside top bar (VS Code/Notion style) -->
	<Sidebar
		{menuOpen}
		{expandedWorkspaces}
		onToggleWorkspace={toggleWorkspace}
		onCreateWorkspace={() => (showCreateWorkspace = true)}
		onLogout={handleLogout}
	/>

	<!-- Right column: top bar + content -->
	<div class="flex min-w-0 flex-1 flex-col">
		<TopBar bind:menuOpen />

		<!-- Main content -->
		<main class="flex-1 overflow-auto dark:bg-gray-950">
			{@render children?.()}
		</main>
	</div>
</div>

{#if showCreateWorkspace}
	<CreateWorkspaceModal
		onClose={() => (showCreateWorkspace = false)}
		onCreated={onWorkspaceCreated}
	/>
{/if}

<!--routes/+layout.svelte-->

<script lang="ts">
	import '../app.css';
	import { goto, afterNavigate } from '$app/navigation';
	import { page } from '$app/stores';
	import { authStore, logout } from '$lib/stores/auth.store';
	import { browser } from '$app/environment';
	import {
		workspaces,
		tablesByWorkspace,
		initSidebar,
		resetSidebar
	} from '$lib/stores/table_schemas.store';
	import { SvelteSet } from 'svelte/reactivity';
	import { hydrateFromServer } from '$lib/stores/settings.store';
	import { fetchMe } from '$lib/backend/auth';
	import type { Workspace } from '$lib/types/table';
	import CreateWorkspaceModal from '$lib/components/sidebar/CreateWorkspaceModal.svelte';
	import Sidebar from '$lib/components/sidebar/Sidebar.svelte';
	import TopBar from '$lib/components/layout/TopBar.svelte';
	import { isUuid, prettifyWorkspacePathname } from '$lib/utils/url';

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
	}

	$effect(() => {
		if ($authStore?.accessToken) {
			refreshSidebar();
			hydrateUserConfig($authStore.accessToken);
		} else {
			resetSidebar();
			expandedWorkspaces.clear();
		}
	});

	// Cosmetic: replace UUID in URL bar with workspace_name
	$effect(() => {
		if (!browser) return;
		const wsId = $page.params.workspace_id;
		if (!wsId || !isUuid(wsId)) return;
		const ws = $workspaces.find((w) => w.workspace_id === wsId);
		if (!ws) return;
		const newPathname = prettifyWorkspacePathname($page.url.pathname, wsId, ws.workspace_name);
		if (newPathname !== $page.url.pathname) {
			history.replaceState(history.state, '', newPathname + $page.url.search);
		}
	});

	async function hydrateUserConfig(accessToken: string) {
		try {
			const me = await fetchMe(accessToken);
			if (me?.config) hydrateFromServer(me.config);
		} catch {
			// best-effort — local cache stays in effect
		}
	}

	function toggleWorkspace(wsId: string) {
		if (expandedWorkspaces.has(wsId)) expandedWorkspaces.delete(wsId);
		else expandedWorkspaces.add(wsId);
	}

	function onWorkspaceCreated(ws: Workspace) {
		workspaces.update((list) => [...list, ws]);
		showCreateWorkspace = false;
		navigate(`/${encodeURIComponent(ws.workspace_name)}/`);
	}

	afterNavigate(({ from }) => {
		if (!from || !$authStore?.accessToken) return;
		const wsId = $page.params.workspace_id;
		if (!wsId) return;
		const decoded = decodeURIComponent(wsId);
		const ws = $workspaces.find((w) => w.workspace_id === wsId || w.workspace_name === decoded);
		if (!ws) {
			refreshSidebar();
			return;
		}
		const tableId = $page.params.table_id;
		if (tableId) {
			const known = $tablesByWorkspace[ws.workspace_id]?.some((t) => t.table_id === tableId);
			if (!known) refreshSidebar();
		}
	});

	const handleLogout = () => {
		logout();
		menuOpen = false;
		goto('/login');
	};

	const navigate = (path: string) => {
		goto(path);
	};
</script>

<svelte:head></svelte:head>

<div class="flex h-screen overflow-hidden">
	<!-- Sidebar: full height, beside top bar (VS Code/Notion style) -->
	<Sidebar
		{menuOpen}
		{expandedWorkspaces}
		{navigate}
		onToggleWorkspace={toggleWorkspace}
		onCreateWorkspace={() => (showCreateWorkspace = true)}
		onLogout={handleLogout}
	/>

	<!-- Right column: top bar + content -->
	<div class="flex min-w-0 flex-1 flex-col">
		<TopBar bind:menuOpen {navigate} />

		<!-- Main content -->
		<main class="flex-1 overflow-auto dark:bg-gray-950">
			{@render children?.()}
		</main>
	</div>
</div>

<CreateWorkspaceModal
	show={showCreateWorkspace}
	onClose={() => (showCreateWorkspace = false)}
	onCreated={onWorkspaceCreated}
/>

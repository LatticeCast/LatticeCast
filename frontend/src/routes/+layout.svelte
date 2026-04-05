<!--routes/+layout.svelte-->

<script lang="ts">
	import '../app.css';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { authStore, logout } from '$lib/stores/auth.store';
	import { isDark } from '$lib/UI/theme.svelte';
	import { browser } from '$app/environment';
	import { currentTable, pageTitle } from '$lib/stores/tables.store';
	import { fetchWorkspaces } from '$lib/backend/workspaces';
	import { fetchTables } from '$lib/backend/tables';
	import type { Workspace, Table } from '$lib/types/table';

	let { children } = $props();
	let menuOpen = $state(false);

	let workspaces = $state<Workspace[]>([]);
	let tablesByWorkspace = $state<Record<string, Table[]>>({});
	let expandedWorkspaces = $state<Set<string>>(new Set());


	$effect(() => {
		if (browser) {
			document.documentElement.classList.toggle('dark', isDark.value);
		}
	});

	$effect(() => {
		if ($authStore?.accessToken) {
			loadSidebarData();
		} else {
			workspaces = [];
			tablesByWorkspace = {};
		}
	});

	async function loadSidebarData() {
		try {
			const [wsList, tableList] = await Promise.all([fetchWorkspaces(), fetchTables()]);
			workspaces = wsList;
			const grouped: Record<string, Table[]> = {};
			for (const t of tableList) {
				if (!grouped[t.workspace_id]) grouped[t.workspace_id] = [];
				grouped[t.workspace_id].push(t);
			}
			tablesByWorkspace = grouped;
			// Auto-expand workspaces that have tables
			const expanded = new Set<string>();
			for (const ws of wsList) {
				if (grouped[ws.workspace_id]?.length) expanded.add(ws.workspace_id);
			}
			expandedWorkspaces = expanded;
		} catch {
			// silently ignore — sidebar tree is best-effort
		}
	}

	function toggleWorkspace(wsId: string) {
		const next = new Set(expandedWorkspaces);
		if (next.has(wsId)) next.delete(wsId);
		else next.add(wsId);
		expandedWorkspaces = next;
	}

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
	<aside
		class="flex shrink-0 flex-col overflow-hidden bg-white shadow-lg transition-all duration-300 ease-in-out dark:bg-gray-900"
		style="width: {menuOpen ? 208 : 0}px;"
	>
		<div class="flex h-full w-52 flex-col">
			<!-- Navigation -->
			<nav data-testid="menu-nav" class="flex-1 space-y-1 overflow-y-auto px-4 pt-3">
				<!-- Workspace → Tables tree -->
				{#if workspaces.length > 0}
					<div>
						<p
							class="mb-1 px-3 text-xs font-semibold tracking-wide text-gray-400 uppercase dark:text-gray-500"
						>
							Workspaces
						</p>
						{#each workspaces as ws (ws.workspace_id)}
							{@const wsTables = tablesByWorkspace[ws.workspace_id] ?? []}
							{@const isExpanded = expandedWorkspaces.has(ws.workspace_id)}
							<div>
								<button
									onclick={() => toggleWorkspace(ws.workspace_id)}
									class="flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-left text-sm text-gray-700 transition hover:bg-blue-50 hover:text-blue-600 dark:text-gray-200 dark:hover:bg-gray-800 dark:hover:text-blue-400"
								>
									<svg
										class="h-3.5 w-3.5 shrink-0 transition-transform {isExpanded ? 'rotate-90' : ''}"
										fill="none"
										stroke="currentColor"
										viewBox="0 0 24 24"
									>
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M9 5l7 7-7 7"
										/>
									</svg>
									<span class="truncate font-medium">{ws.workspace_name}</span>
									<span class="ml-auto shrink-0 text-xs text-gray-400">{wsTables.length}</span>
								</button>
								{#if isExpanded}
									<div
										class="mt-0.5 ml-3 space-y-0.5 border-l border-gray-200 pl-2 dark:border-gray-700"
									>
										{#each wsTables as table (table.table_id)}
											<button
												onclick={() => {
													navigate(`/${ws.workspace_id}/${table.table_id}`);
													menuOpen = false;
												}}
												class="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs text-gray-600 transition hover:bg-blue-50 hover:text-blue-600 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-blue-400 {$currentTable?.table_id ===
												table.table_id
													? 'bg-blue-50 font-semibold text-blue-600 dark:bg-gray-800 dark:text-blue-400'
													: ''}"
											>
												<svg
													class="h-3 w-3 shrink-0 text-gray-400"
													fill="none"
													stroke="currentColor"
													viewBox="0 0 24 24"
												>
													<path
														stroke-linecap="round"
														stroke-linejoin="round"
														stroke-width="2"
														d="M3 10h18M3 14h18M10 3v18M6 3h12a1 1 0 011 1v16a1 1 0 01-1 1H6a1 1 0 01-1-1V4a1 1 0 011-1z"
													/>
												</svg>
												<span class="truncate">{table.name}</span>
											</button>
										{:else}
											<p class="px-2 py-1 text-xs text-gray-400 dark:text-gray-500">No tables</p>
										{/each}
									</div>
								{/if}
							</div>
						{/each}
					</div>
				{/if}
			</nav>

			<!-- Bottom: Settings, Debug, then user + logout -->
			<div class="border-t border-gray-200 dark:border-gray-700">
				<!-- Settings & Debug -->
				<div class="space-y-0.5 px-4 pt-2 pb-1">
					<button
						onclick={() => navigate('/config')}
						data-testid="nav-settings"
						class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-gray-700 transition hover:bg-blue-50 hover:text-blue-600 dark:text-gray-200 dark:hover:bg-gray-800 dark:hover:text-blue-400"
					>
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
							/>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
							/>
						</svg>
						Settings
					</button>
					<button
						onclick={() => navigate('/debug')}
						data-testid="nav-debug"
						class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-gray-700 transition hover:bg-blue-50 hover:text-blue-600 dark:text-gray-200 dark:hover:bg-gray-800 dark:hover:text-blue-400"
					>
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
							/>
						</svg>
						Debug
					</button>
				</div>

				<!-- User identity + logout -->
				<div class="border-t border-gray-200 px-4 py-3 dark:border-gray-700">
					{#if $authStore?.role}
						<div class="flex items-center gap-2">
							<!-- Avatar -->
							{#if $authStore.userInfo?.picture}
								<img src={$authStore.userInfo.picture} alt="Profile" class="h-7 w-7 shrink-0 rounded-full" />
							{:else}
								<div
									class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs text-blue-600 dark:bg-blue-900 dark:text-blue-300"
								>
									{($authStore.userInfo?.name || $authStore.userInfo?.email || '?')
										.charAt(0)
										.toUpperCase()}
								</div>
							{/if}
							<!-- Name + role -->
							<div class="min-w-0 flex-1">
								<p class="truncate text-xs font-medium text-gray-900 dark:text-gray-100">
									{$authStore.userInfo?.name || $authStore.userInfo?.email || 'User'}
								</p>
								<p class="truncate text-xs text-gray-400 dark:text-gray-500">
									{$authStore.userInfo?.sub ?? ''}
								</p>
							</div>
							<!-- Logout icon button -->
							<button
								onclick={handleLogout}
								data-testid="nav-logout"
								class="shrink-0 rounded-lg p-1.5 text-gray-400 transition hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20 dark:hover:text-red-400"
								title="Logout"
								aria-label="Logout"
							>
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
									/>
								</svg>
							</button>
						</div>
					{:else}
						<button
							onclick={() => navigate('/login')}
							data-testid="nav-login"
							class="flex w-full items-center gap-3 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-600"
						>
							<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"
								/>
							</svg>
							Login
						</button>
					{/if}
				</div>
			</div>
		</div>
	</aside>

	<!-- Right column: top bar + content -->
	<div class="flex min-w-0 flex-1 flex-col">
	<!-- Top bar -->
	<header class="z-30 flex h-12 shrink-0 items-center bg-blue-600 px-3 shadow">
		{#if menuOpen}
			<button
				onclick={() => (menuOpen = false)}
				data-testid="menu-close"
				class="relative h-8 w-8 shrink-0 rounded-md text-white hover:bg-blue-500 focus:outline-none"
				aria-label="Close menu"
			>
				<span class="absolute inset-0 flex items-center justify-center">«</span>
			</button>
		{:else}
			<button
				onclick={() => (menuOpen = true)}
				data-testid="menu-toggle"
				class="relative h-8 w-8 shrink-0 rounded-md text-white hover:bg-blue-500 focus:outline-none"
				aria-label="Open menu"
			>
				<span class="absolute inset-0 flex items-center justify-center">☰</span>
			</button>
		{/if}
		<!-- Home icon — always visible next to ☰ -->
		<button
			onclick={() => navigate('/')}
			data-testid="nav-home"
			class="relative h-8 w-8 shrink-0 rounded-md text-white hover:bg-blue-500 focus:outline-none"
			aria-label="Home"
		>
			<span class="absolute inset-0 flex items-center justify-center">
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
				</svg>
			</span>
		</button>
		<!-- Tables icon — always visible next to Home -->
		<button
			onclick={() => navigate('/tables')}
			data-testid="nav-tables-topbar"
			class="relative h-8 w-8 shrink-0 rounded-md text-white hover:bg-blue-500 focus:outline-none"
			aria-label="Tables"
			title="Tables"
		>
			<span class="absolute inset-0 flex items-center justify-center">
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M3 14h18M10 3v18M6 3h12a1 1 0 011 1v16a1 1 0 01-1 1H6a1 1 0 01-1-1V4a1 1 0 011-1z" />
				</svg>
			</span>
		</button>
		<nav class="ml-1 flex min-w-0 items-center gap-1 overflow-hidden" aria-label="Breadcrumb">
			{#if $page.params.workspace_id}
				{@const wsId = $page.params.workspace_id}
				{@const wsName = workspaces.find((w) => w.workspace_id === wsId)?.workspace_name ?? wsId}
				<button
					onclick={() => navigate('/tables')}
					data-testid="breadcrumb-workspace"
					class="min-w-0 truncate rounded px-1 py-0.5 text-sm text-white/70 hover:text-white"
				>{wsName}</button>
				{#if $page.params.table_id}
					{@const tableId = $page.params.table_id}
					{@const tableName = tablesByWorkspace[wsId]?.find((t) => t.table_id === tableId)?.name ?? $currentTable?.name ?? tableId}
					<span class="shrink-0 text-white/40">/</span>
					<button
						onclick={() => navigate(`/${wsId}/${tableId}`)}
						data-testid="breadcrumb-table"
						class="min-w-0 truncate rounded px-1 py-0.5 text-sm font-semibold text-white hover:text-white/80"
					>{tableName}</button>
					{#if $page.params.row_number}
						<span class="shrink-0 text-white/40">/</span>
						<button
							onclick={() => navigate(`/${wsId}/${tableId}/${$page.params.row_number}`)}
							data-testid="breadcrumb-row"
							class="min-w-0 truncate rounded px-1 py-0.5 text-sm text-white/70 hover:text-white"
						>{$page.params.row_number}</button>
					{/if}
				{/if}
			{:else if $pageTitle}
				<span class="shrink-0 text-white/40">/</span>
				<span class="min-w-0 truncate rounded px-1 py-0.5 text-sm font-semibold text-white">{$pageTitle}</span>
			{/if}
		</nav>
	</header>

	<!-- Main content -->
	<main class="flex-1 overflow-auto dark:bg-gray-950">
		{@render children?.()}
	</main>
	</div>
</div>

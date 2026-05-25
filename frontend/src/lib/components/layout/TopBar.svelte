<!-- $lib/components/layout/TopBar.svelte — menu toggle, home, breadcrumb -->
<script lang="ts">
	import { page } from '$app/stores';
	import { currentTable, workspaces, tablesByWorkspace } from '$lib/stores/table_schemas.store';

	let {
		menuOpen = $bindable(),
		navigate
	}: {
		menuOpen: boolean;
		navigate: (path: string) => void;
	} = $props();
</script>

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
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
				/>
			</svg>
		</span>
	</button>
	<nav class="ml-1 flex min-w-0 items-center gap-1 overflow-hidden" aria-label="Breadcrumb">
		<span class="shrink-0 text-white/40">/</span>
		{#if $page.params.workspace_id}
			{@const wsId = $page.params.workspace_id}
			{@const wsName = $workspaces.find((w) => w.workspace_id === wsId)?.workspace_name ?? wsId}
			<button
				onclick={() => navigate(`/${wsId}`)}
				data-testid="breadcrumb-workspace"
				class="min-w-0 truncate rounded px-1 py-0.5 text-sm text-white/70 hover:text-white"
				>{wsName}</button
			>
			{#if $page.params.table_id}
				{@const tableId = $page.params.table_id}
				{@const tableName =
					$tablesByWorkspace[wsId]?.find((t) => t.table_id === tableId)?.table_id ??
					$currentTable?.table_id ??
					tableId}
				<span class="shrink-0 text-white/40">/</span>
				<button
					onclick={() => navigate(`/${wsId}/${tableId}`)}
					data-testid="breadcrumb-table"
					class="min-w-0 truncate rounded px-1 py-0.5 text-sm font-semibold text-white hover:text-white/80"
					>{tableName}</button
				>
				{#if $page.params.row_id}
					<span class="shrink-0 text-white/40">/</span>
					<button
						onclick={() => navigate(`/${wsId}/${tableId}/${$page.params.row_id}`)}
						data-testid="breadcrumb-row"
						class="min-w-0 truncate rounded px-1 py-0.5 text-sm text-white/70 hover:text-white"
						>{$page.params.row_id}</button
					>
				{/if}
			{/if}
		{/if}
	</nav>
</header>

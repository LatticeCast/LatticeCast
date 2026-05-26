<!-- $lib/components/sidebar/Sidebar.svelte — workspace→table tree + user footer -->
<script lang="ts">
	import { authStore } from '$lib/stores/auth.store';
	import { currentTable, workspaces, tablesByWorkspace } from '$lib/stores/table_schemas.store';
	import { navigate, navigateToTable } from '$lib/utils/url';
	import type { SvelteSet } from 'svelte/reactivity';

	let {
		menuOpen,
		expandedWorkspaces,
		onToggleWorkspace,
		onCreateWorkspace,
		onLogout
	}: {
		menuOpen: boolean;
		expandedWorkspaces: SvelteSet<string>;
		onToggleWorkspace: (wsId: string) => void;
		onCreateWorkspace: () => void;
		onLogout: () => void;
	} = $props();
</script>

<aside
	class="flex shrink-0 flex-col overflow-hidden bg-white shadow-lg transition-all duration-300 ease-in-out dark:bg-gray-900"
	style="width: {menuOpen ? 208 : 0}px;"
>
	<div class="flex h-full w-52 flex-col">
		<!-- Navigation -->
		<nav data-testid="menu-nav" class="flex-1 space-y-1 overflow-y-auto px-4 pt-3">
			<!-- Workspace → Tables tree -->
			{#if $workspaces.length > 0}
				<div>
					<p
						class="mb-1 px-3 text-xs font-semibold tracking-wide text-gray-400 uppercase dark:text-gray-500"
					>
						Workspaces
					</p>
					{#each $workspaces as ws (ws.workspace_id)}
						{@const wsTables = $tablesByWorkspace[ws.workspace_id] ?? []}
						{@const isExpanded = expandedWorkspaces.has(ws.workspace_id)}
						<div>
							<div
								class="flex w-full items-center rounded-lg text-sm text-gray-700 dark:text-gray-200"
							>
								<button
									data-testid="sidebar-workspace-toggle-{ws.workspace_id}"
									onclick={() => onToggleWorkspace(ws.workspace_id)}
									class="flex shrink-0 items-center justify-center rounded-l-lg px-1.5 py-1.5 transition hover:bg-blue-50 hover:text-blue-600 dark:hover:bg-gray-800 dark:hover:text-blue-400"
								>
									<svg
										class="h-3.5 w-3.5 transition-transform {isExpanded ? 'rotate-90' : ''}"
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
								</button>
								<button
									data-testid="sidebar-workspace-{ws.workspace_id}"
									onclick={() => navigate(`/${encodeURIComponent(ws.workspace_name)}/`)}
									class="flex min-w-0 flex-1 items-center gap-2 rounded-r-lg px-1.5 py-1.5 text-left transition hover:bg-blue-50 hover:text-blue-600 dark:hover:bg-gray-800 dark:hover:text-blue-400"
								>
									<span class="truncate font-medium">{ws.workspace_name}</span>
									<span class="ml-auto shrink-0 text-xs text-gray-400">{wsTables.length}</span>
								</button>
							</div>
							{#if isExpanded}
								<div
									class="mt-0.5 ml-3 space-y-0.5 border-l border-gray-200 pl-2 dark:border-gray-700"
								>
									<!-- Members link -->
									<button
										onclick={() => navigate(`/${ws.workspace_id}/members`)}
										data-testid="nav-members-{ws.workspace_id}"
										class="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs text-gray-600 transition hover:bg-blue-50 hover:text-blue-600 dark:text-gray-300 dark:hover:bg-gray-800 dark:hover:text-blue-400"
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
												d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"
											/>
										</svg>
										<span class="truncate">Members</span>
									</button>
									{#each wsTables as table (table.table_id)}
										<button
											data-testid="sidebar-table-{table.table_id}"
											onclick={() => navigateToTable(ws.workspace_id, table.table_id)}
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
											<span class="truncate">{table.table_id}</span>
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

			<!-- New Workspace button -->
			{#if $authStore?.accessToken}
				<button
					data-testid="create-workspace-btn"
					onclick={onCreateWorkspace}
					class="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-left text-sm text-gray-400 transition hover:bg-blue-50 hover:text-blue-600 dark:text-gray-500 dark:hover:bg-gray-800 dark:hover:text-blue-400"
				>
					<svg class="h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M12 4v16m8-8H4"
						/>
					</svg>
					<span>New Workspace</span>
				</button>
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
							<img
								src={$authStore.userInfo.picture}
								alt="Profile"
								class="h-7 w-7 shrink-0 rounded-full"
							/>
						{:else}
							<div
								class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs text-blue-600 dark:bg-blue-900 dark:text-blue-300"
							>
								{($authStore.userInfo?.name || $authStore.userInfo?.email || '?')
									.charAt(0)
									.toUpperCase()}
							</div>
						{/if}
						<!-- Name + role (clickable → /settings) -->
						<button
							onclick={() => navigate('/settings')}
							data-testid="nav-profile"
							class="min-w-0 flex-1 text-left"
							title="Edit profile"
						>
							<p
								class="truncate text-xs font-medium text-gray-900 hover:text-blue-600 dark:text-gray-100 dark:hover:text-blue-400"
							>
								{$authStore.userInfo?.name || $authStore.userInfo?.email || 'User'}
							</p>
							<p class="truncate text-xs text-gray-400 dark:text-gray-500">
								{$authStore.userInfo?.sub ?? ''}
							</p>
						</button>
						<!-- Logout icon button -->
						<button
							onclick={onLogout}
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

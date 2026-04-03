<!--routes/+layout.svelte-->

<script lang="ts">
	import '../app.css';
	import { goto } from '$app/navigation';
	import { authStore, logout } from '$lib/stores/auth.store';
	import { isDark } from '$lib/UI/theme.svelte';
	import { browser } from '$app/environment';

	let { children } = $props();
	let menuOpen = $state(false);

	$effect(() => {
		if (browser) {
			document.documentElement.classList.toggle('dark', isDark.value);
		}
	});

	const handleLogout = () => {
		logout();
		menuOpen = false;
		goto('/login');
	};

	const navigate = (path: string) => {
		menuOpen = false;
		goto(path);
	};
</script>

<svelte:head></svelte:head>

<div class="relative flex min-h-screen flex-col">
	<!-- Top bar -->
	<header class="fixed top-0 left-0 right-0 z-30 flex h-12 items-center bg-blue-600 px-3 shadow">
		<button
			onclick={() => (menuOpen = !menuOpen)}
			data-testid="menu-toggle"
			class="relative h-8 w-8 rounded-md text-white hover:bg-blue-500 focus:outline-none"
			aria-label={menuOpen ? 'Close menu' : 'Open menu'}
		>
			<span class="menu-icon absolute inset-0 flex items-center justify-center transition-all duration-300 {menuOpen ? 'opacity-100 scale-100' : 'opacity-0 scale-75'}">«</span>
			<span class="menu-icon absolute inset-0 flex items-center justify-center transition-all duration-300 {menuOpen ? 'opacity-0 scale-75' : 'opacity-100 scale-100'}">☰</span>
		</button>
	</header>

	<!-- Sliding sidebar (from left, below top bar) -->
	<div
		class="fixed top-12 left-0 z-20 flex h-[calc(100vh-3rem)] w-52 flex-col bg-white shadow-lg transition-transform duration-300 ease-in-out dark:bg-gray-900"
		style="transform: translateX({menuOpen ? 0 : -208}px);"
	>
		<!-- Navigation -->
		<nav data-testid="menu-nav" class="flex-1 space-y-1 px-4">
			<button
				onclick={() => navigate('/')}
				data-testid="nav-home"
				class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-gray-700 transition hover:bg-blue-50 hover:text-blue-600 dark:text-gray-200 dark:hover:bg-gray-800 dark:hover:text-blue-400"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
				</svg>
				Home
			</button>

			<button
				onclick={() => navigate('/tables')}
				data-testid="nav-tables"
				class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-gray-700 transition hover:bg-blue-50 hover:text-blue-600 dark:text-gray-200 dark:hover:bg-gray-800 dark:hover:text-blue-400"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h18M3 14h18M10 3v18M6 3h12a1 1 0 011 1v16a1 1 0 01-1 1H6a1 1 0 01-1-1V4a1 1 0 011-1z" />
				</svg>
				Tables
			</button>

			<button
				onclick={() => navigate('/config')}
				data-testid="nav-settings"
				class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-gray-700 transition hover:bg-blue-50 hover:text-blue-600 dark:text-gray-200 dark:hover:bg-gray-800 dark:hover:text-blue-400"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
				</svg>
				Settings
			</button>

			<button
				onclick={() => navigate('/debug')}
				data-testid="nav-debug"
				class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-gray-700 transition hover:bg-blue-50 hover:text-blue-600 dark:text-gray-200 dark:hover:bg-gray-800 dark:hover:text-blue-400"
			>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
				</svg>
				Debug
			</button>
		</nav>

		<!-- Bottom: user info + logout -->
		<div class="border-t border-gray-200 p-4 dark:border-gray-700">
			{#if $authStore?.role}
				{#if $authStore.userInfo}
					<div class="mb-3 flex items-center gap-2 px-2">
						{#if $authStore.userInfo.picture}
							<img src={$authStore.userInfo.picture} alt="Profile" class="h-7 w-7 rounded-full" />
						{:else}
							<div class="flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-xs text-blue-600 dark:bg-blue-900 dark:text-blue-300">
								{($authStore.userInfo.name || $authStore.userInfo.email || '?').charAt(0).toUpperCase()}
							</div>
						{/if}
						<div class="min-w-0 flex-1">
							<p class="truncate text-xs font-medium text-gray-900 dark:text-gray-100">
								{$authStore.userInfo.name || $authStore.userInfo.email || 'User'}
							</p>
							<p class="truncate text-xs text-gray-500 dark:text-gray-400">
								{$authStore.provider}
								<span class={`ml-1 rounded px-1 text-xs ${$authStore.role === 'admin' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
									{$authStore.role}
								</span>
							</p>
						</div>
					</div>
				{/if}
				<button
					onclick={handleLogout}
					data-testid="nav-logout"
					class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-gray-700 transition hover:bg-blue-50 hover:text-blue-600 dark:text-gray-200 dark:hover:bg-gray-800 dark:hover:text-blue-400"
				>
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
					</svg>
					Logout
				</button>
			{:else}
				<button
					onclick={() => navigate('/login')}
					data-testid="nav-login"
					class="flex w-full items-center gap-3 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-600"
				>
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1" />
					</svg>
					Login
				</button>
			{/if}
		</div>
	</div>

	<!-- Main content: shifts right when sidebar opens, padded below top bar -->
	<main class="content-area flex-1 pt-12 dark:bg-gray-950" style="margin-left: {menuOpen ? '208px' : '0'};">
		{@render children?.()}
	</main>
</div>

<style>
	.content-area {
		transition: margin-left 0.3s ease-in-out;
	}
</style>

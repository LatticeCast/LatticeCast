<!--routes/+layout.svelte-->

<script lang="ts">
	import '../app.css';
	import { goto } from '$app/navigation';
	import { authStore, logout } from '$lib/stores/auth.store';

	let { children } = $props();
	let menuOpen = $state(false);

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

<!-- Floating Menu Button -->
<button
	onclick={() => (menuOpen = !menuOpen)}
	data-testid="menu-toggle"
	class="fixed top-4 right-4 z-50 flex h-12 w-12 items-center justify-center rounded-full bg-white/20 shadow-lg backdrop-blur-sm transition-all hover:scale-105 hover:bg-white/30"
	aria-label="Toggle menu"
>
	{#if menuOpen}
		<svg class="h-6 w-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				stroke-width="2"
				d="M6 18L18 6M6 6l12 12"
			/>
		</svg>
	{:else}
		<svg class="h-6 w-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				stroke-width="2"
				d="M4 6h16M4 12h16M4 18h16"
			/>
		</svg>
	{/if}
</button>

<!-- Slide-out Menu -->
{#if menuOpen}
	<!-- Backdrop -->
	<button
		data-testid="menu-backdrop"
		class="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
		onclick={() => (menuOpen = false)}
		aria-label="Close menu"
	></button>

	<!-- Menu Panel -->
	<div
		class="fixed top-0 right-0 z-50 h-full w-64 bg-gradient-to-b from-violet-600 via-purple-600 to-fuchsia-600 shadow-2xl"
	>
		<div class="flex h-full flex-col pt-20">
			<nav data-testid="menu-nav" class="flex-1 space-y-1 px-4">
				<button
					onclick={() => navigate('/')}
					data-testid="nav-home"
					class="flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left text-white/90 transition hover:bg-white/20"
				>
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
						/>
					</svg>
					Home
				</button>

				<button
					onclick={() => navigate('/config')}
					data-testid="nav-settings"
					class="flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left text-white/90 transition hover:bg-white/20"
				>
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
					class="flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left text-white/90 transition hover:bg-white/20"
				>
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
						/>
					</svg>
					Debug
				</button>

				<button
					onclick={() => navigate('/tables')}
					data-testid="nav-tables"
					class="flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left text-white/90 transition hover:bg-white/20"
				>
					<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M3 10h18M3 14h18M10 3v18M6 3h12a1 1 0 011 1v16a1 1 0 01-1 1H6a1 1 0 01-1-1V4a1 1 0 011-1z"
						/>
					</svg>
					Tables
				</button>

				</nav>

			<!-- Bottom Section -->
			<div class="border-t border-white/20 p-4">
				{#if $authStore?.role}
					{#if $authStore.userInfo}
						<div class="mb-3 flex items-center gap-3 px-2">
							{#if $authStore.userInfo.picture}
								<img src={$authStore.userInfo.picture} alt="Profile" class="h-8 w-8 rounded-full" />
							{:else}
								<div
									class="flex h-8 w-8 items-center justify-center rounded-full bg-white/20 text-white"
								>
									{($authStore.userInfo.name || $authStore.userInfo.email || '?')
										.charAt(0)
										.toUpperCase()}
								</div>
							{/if}
							<div class="min-w-0 flex-1">
								<p class="truncate text-sm font-medium text-white">
									{$authStore.userInfo.name || $authStore.userInfo.email || 'User'}
								</p>
								<p class="truncate text-xs text-white/70">
									{$authStore.provider}
									<span
										class={`ml-1 rounded px-1 text-xs ${$authStore.role === 'admin' ? 'bg-red-400/30 text-red-100' : 'bg-green-400/30 text-green-100'}`}
									>
										{$authStore.role}
									</span>
								</p>
							</div>
						</div>
					{/if}
					<button
						onclick={handleLogout}
						data-testid="nav-logout"
						class="flex w-full items-center gap-3 rounded-xl bg-white/10 px-4 py-3 text-white transition hover:bg-white/20"
					>
						<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
							/>
						</svg>
						Logout
					</button>
				{:else}
					<button
						onclick={() => navigate('/login')}
						data-testid="nav-login"
						class="flex w-full items-center gap-3 rounded-xl bg-white px-4 py-3 font-semibold text-purple-600 transition hover:bg-white/90"
					>
						<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
{/if}

<main>
	{@render children?.()}
</main>

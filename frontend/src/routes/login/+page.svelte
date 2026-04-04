<!-- src/routes/login/+page.svelte -->
<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { authStore } from '$lib/stores/auth.store';
	import { startLogin } from '$lib/auth/auth.service';
	import { fetchMe } from '$lib/backend/auth';

	const authRequired = import.meta.env.VITE_AUTH_REQUIRED !== 'false';
	let userId = $state('');
	let loginError = $state('');
	let loggingIn = $state(false);

	onMount(() => {
		if ($authStore?.role) {
			goto('/');
		}
	});

	async function simpleLogin() {
		const id = userId.trim();
		if (!id) return;
		loggingIn = true;
		loginError = '';
		try {
			// Call backend /me to create/resolve user in DB (auto-created when auth_required=false)
			// Returns resolved user_id UUID regardless of whether input was UUID or display_id
			const me = await fetchMe(id);
			authStore.set({
				provider: 'none',
				accessToken: me?.user_id ?? id,
				userInfo: { sub: me?.user_id ?? id, email: me?.email ?? id, name: me?.name ?? id },
				role: me?.role ?? 'user'
			});
			goto('/');
		} catch {
			loginError = 'Failed to connect to server';
			loggingIn = false;
		}
	}
</script>

<div
	class="flex min-h-screen items-center justify-center bg-linear-to-br from-blue-600 via-blue-500 to-sky-500 p-4"
>
	<div class="mx-auto w-full max-w-sm">
		<div class="mb-8 text-center">
			<h1 class="mb-2 text-4xl font-bold text-white">Lattice Cast</h1>
			<p class="text-white/80">Sign in to continue</p>
		</div>

		{#if !authRequired}
			<!-- Simple user_id login -->
			<div class="rounded-3xl bg-white p-8 shadow-2xl">
				<div class="space-y-4">
					<input
						type="text"
						bind:value={userId}
						placeholder="Enter your user ID"
						data-testid="login-userid"
						disabled={loggingIn}
						onkeydown={(e) => e.key === 'Enter' && simpleLogin()}
						class="w-full rounded-2xl border-2 border-gray-200 bg-gray-50 px-4 py-4 text-center text-lg text-gray-800 placeholder-gray-400 focus:border-blue-500 focus:outline-none disabled:opacity-50"
					/>
					{#if loginError}
						<p class="text-center text-sm text-red-500">{loginError}</p>
					{/if}
					<button
						onclick={simpleLogin}
						data-testid="login-start"
						disabled={!userId.trim() || loggingIn}
						class="w-full rounded-2xl bg-linear-to-r from-blue-600 to-sky-500 px-4 py-4 font-semibold text-white transition hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-40"
					>
						{loggingIn ? 'Connecting...' : 'Start'}
					</button>
				</div>
			</div>
		{:else}
			<!-- OAuth login -->
			<div class="rounded-3xl bg-white p-8 shadow-2xl">
				<div class="space-y-4">
					<button
						onclick={() => startLogin('authentik')}
						data-testid="login-authentik"
						class="flex w-full items-center justify-center gap-3 rounded-2xl bg-linear-to-r from-blue-600 to-sky-500 px-4 py-4 font-semibold text-white transition hover:shadow-lg"
					>
						Authentik
					</button>

					<div class="flex items-center gap-4">
						<div class="h-px flex-1 bg-gray-200"></div>
						<span class="text-sm text-gray-400">or</span>
						<div class="h-px flex-1 bg-gray-200"></div>
					</div>

					<button
						onclick={() => startLogin('google')}
						data-testid="login-google"
						class="flex w-full items-center justify-center gap-3 rounded-2xl border-2 border-gray-200 bg-white px-4 py-4 font-semibold text-gray-700 transition hover:border-gray-300 hover:bg-gray-50"
					>
						<svg class="h-5 w-5" viewBox="0 0 24 24">
							<path
								fill="#4285F4"
								d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
							/>
							<path
								fill="#34A853"
								d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
							/>
							<path
								fill="#FBBC05"
								d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
							/>
							<path
								fill="#EA4335"
								d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
							/>
						</svg>
						Google
					</button>
				</div>
			</div>
		{/if}
	</div>
</div>

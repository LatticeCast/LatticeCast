<!-- src/routes/debug/+page.svelte -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { authStore, logout } from '$lib/stores/auth.store';

	const handleLogout = () => {
		logout();
		goto('/login');
	};

	const getRoleBadge = (role: string | undefined) => {
		if (role === 'admin')
			return { class: 'bg-red-100 text-red-800 border-red-200', label: 'Admin' };
		if (role === 'user')
			return { class: 'bg-green-100 text-green-800 border-green-200', label: 'User' };
		return { class: 'bg-gray-100 text-gray-800 border-gray-200', label: 'Unregistered' };
	};

	const getProviderBadgeColor = (provider: string) => {
		const colors: Record<string, string> = {
			authentik: 'bg-blue-100 text-blue-800 border-blue-200',
			google: 'bg-red-100 text-red-800 border-red-200',
			microsoft: 'bg-sky-100 text-sky-800 border-sky-200',
			local: 'bg-green-100 text-green-800 border-green-200'
		};
		return colors[provider] || 'bg-gray-100 text-gray-800 border-gray-200';
	};

	// Environment config for debugging
	const envConfig = {
		backendUrl: import.meta.env.VITE_BACKEND_URL,
		googleClientId: import.meta.env.VITE_GOOGLE_CLIENT_ID ? '✓ Set' : '✗ Missing',
		googleRedirectUri: import.meta.env.VITE_GOOGLE_REDIRECT_URI
	};

	$: roleBadge = getRoleBadge($authStore?.role);
</script>

<div class="min-h-screen bg-gray-50 p-8">
	<div class="mx-auto max-w-4xl">
		<div class="rounded-lg bg-white p-8 shadow-lg">
			<div class="mb-8 flex items-center justify-between">
				<div class="flex items-center gap-4">
					<h1 class="text-3xl font-bold text-gray-900">Debug Info</h1>
					<span class={`rounded-full border px-3 py-1 text-sm font-semibold ${roleBadge.class}`}>
						{roleBadge.label}
					</span>
					{#if $authStore?.provider}
						<span
							class={`rounded-full border px-3 py-1 text-sm font-semibold ${getProviderBadgeColor($authStore.provider)}`}
						>
							{$authStore.provider.charAt(0).toUpperCase() + $authStore.provider.slice(1)}
						</span>
					{/if}
				</div>
				{#if $authStore}
					<button
						onclick={handleLogout}
						class="rounded-lg bg-red-600 px-4 py-2 text-white transition hover:bg-red-700"
					>
						Logout
					</button>
				{/if}
			</div>

			<div class="space-y-6">
				{#if $authStore}
					{#if $authStore.userInfo}
						<div class="rounded-lg border border-blue-200 bg-blue-50 p-4">
							<h3 class="mb-2 font-semibold text-blue-900">User Info</h3>
							<div class="space-y-1 text-sm">
								{#if $authStore.userInfo.name}
									<p><span class="font-medium">Name:</span> {$authStore.userInfo.name}</p>
								{/if}
								{#if $authStore.userInfo.email}
									<p><span class="font-medium">Email:</span> {$authStore.userInfo.email}</p>
								{/if}
								{#if $authStore.userInfo.picture}
									<div class="mt-3 flex items-center gap-3">
										<span class="font-medium">Avatar:</span>
										<img
											src={$authStore.userInfo.picture}
											alt="Profile"
											class="h-12 w-12 rounded-full border-2 border-blue-300"
										/>
									</div>
								{/if}
								<p><span class="font-medium">Subject:</span> {$authStore.userInfo.sub}</p>
							</div>
						</div>
					{/if}

					<div class="rounded-lg border border-green-200 bg-green-50 p-4">
						<h3 class="mb-2 font-semibold text-green-900">Access Token</h3>
						<p class="font-mono text-xs break-all text-gray-700">{$authStore.accessToken}</p>
					</div>

					{#if $authStore.refreshToken}
						<div class="rounded-lg border border-purple-200 bg-purple-50 p-4">
							<h3 class="mb-2 font-semibold text-purple-900">Refresh Token</h3>
							<p class="font-mono text-xs break-all text-gray-700">{$authStore.refreshToken}</p>
						</div>
					{/if}

					{#if $authStore.idToken}
						<div class="rounded-lg border border-yellow-200 bg-yellow-50 p-4">
							<h3 class="mb-2 font-semibold text-yellow-900">ID Token</h3>
							<p class="font-mono text-xs break-all text-gray-700">{$authStore.idToken}</p>
						</div>
					{/if}

					{#if $authStore.expiresAt}
						<div class="rounded-lg border border-gray-200 bg-gray-50 p-4">
							<h3 class="mb-2 font-semibold text-gray-900">Token Expiration</h3>
							<p class="text-sm text-gray-700">
								Expires at: {new Date($authStore.expiresAt * 1000).toLocaleString()}
							</p>
						</div>
					{/if}
				{:else}
					<div class="rounded-lg border border-yellow-200 bg-yellow-50 p-4">
						<p class="text-yellow-800">Not logged in</p>
					</div>
				{/if}

				<div class="rounded-lg border border-orange-200 bg-orange-50 p-4">
					<h3 class="mb-2 font-semibold text-orange-900">Environment Config</h3>
					<div class="space-y-1 text-sm">
						<p><span class="font-medium">Backend URL:</span> {envConfig.backendUrl}</p>
						<p><span class="font-medium">Google Client ID:</span> {envConfig.googleClientId}</p>
						<p><span class="font-medium">Google Redirect:</span> {envConfig.googleRedirectUri}</p>
					</div>
				</div>

				{#if !$authStore}
					<a
						href="/login"
						class="inline-block rounded-lg bg-purple-600 px-6 py-3 text-white transition hover:bg-purple-700"
					>
						Go to Login
					</a>
				{/if}
			</div>
		</div>
	</div>
</div>

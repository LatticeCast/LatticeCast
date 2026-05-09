<!-- src/routes/settings/+page.svelte -->
<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { authStore } from '$lib/stores/auth.store';
	import { fetchMe, updateEmail } from '$lib/backend/auth';

	const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

	let userInfo = $state<{ user_id: string; user_name?: string; email: string } | null>(null);
	let emailInput = $state('');
	let saving = $state(false);
	let successMsg = $state('');
	let errorMsg = $state('');

	onMount(async () => {
		const token = $authStore?.accessToken;
		if (!token) {
			goto('/login');
			return;
		}
		const me = await fetchMe(token);
		if (!me) {
			goto('/login');
			return;
		}
		userInfo = { user_id: me.user_id, user_name: me.user_name, email: me.email };
		emailInput = me.email;
	});

	function validateEmail(v: string): string {
		if (!v.trim()) return 'Email is required';
		if (!EMAIL_RE.test(v.trim())) return 'Enter a valid email address';
		return '';
	}

	let validationError = $derived(validateEmail(emailInput));
	let isDirty = $derived(userInfo !== null && emailInput.trim() !== userInfo.email);

	async function save() {
		if (validationError || !isDirty) return;
		const token = $authStore?.accessToken;
		if (!token) return;

		saving = true;
		successMsg = '';
		errorMsg = '';
		try {
			const updated = await updateEmail(emailInput.trim(), token);
			userInfo = { ...userInfo!, email: updated.email };
			emailInput = updated.email;
			successMsg = 'Email updated successfully';
		} catch (e: unknown) {
			const msg = e instanceof Error ? e.message : 'Update failed';
			errorMsg = msg === 'email already registered' ? 'Email already registered' : msg;
		} finally {
			saving = false;
		}
	}
</script>

<div class="min-h-screen bg-linear-to-br from-blue-600 via-blue-500 to-sky-500 p-4">
	<div class="mx-auto max-w-md">
		<div class="mb-6 flex items-center justify-between pt-8">
			<button
				onclick={() => goto('/')}
				class="flex items-center gap-2 rounded-xl bg-white/20 px-4 py-2 text-white backdrop-blur-sm transition-all hover:bg-white/30"
			>
				← Back
			</button>
			<h1 class="text-2xl font-bold text-white">Profile</h1>
			<div class="w-20"></div>
		</div>

		{#if userInfo}
			<!-- Read-only identity -->
			<div class="mb-4 rounded-3xl bg-white p-6 shadow-2xl">
				<h2 class="mb-4 text-xl font-bold text-gray-800">Account Info</h2>
				<div class="space-y-3">
					<div>
						<label class="mb-1 block text-xs font-semibold tracking-wide text-gray-400 uppercase">
							User ID
						</label>
						<p
							data-testid="settings-user-id"
							class="rounded-xl bg-gray-50 px-4 py-2.5 font-mono text-sm break-all text-gray-600"
						>
							{userInfo.user_id}
						</p>
					</div>
					{#if userInfo.user_name}
						<div>
							<label class="mb-1 block text-xs font-semibold tracking-wide text-gray-400 uppercase">
								Username
							</label>
							<p
								data-testid="settings-user-name"
								class="rounded-xl bg-gray-50 px-4 py-2.5 text-sm text-gray-700"
							>
								{userInfo.user_name}
							</p>
						</div>
					{/if}
				</div>
			</div>

			<!-- Editable email -->
			<div class="mb-4 rounded-3xl bg-white p-6 shadow-2xl">
				<h2 class="mb-4 text-xl font-bold text-gray-800">Email Address</h2>
				<div class="space-y-3">
					<input
						type="email"
						bind:value={emailInput}
						data-testid="settings-email-input"
						placeholder="your@email.com"
						disabled={saving}
						class="w-full rounded-2xl border-2 bg-gray-50 px-4 py-3 text-gray-800 placeholder-gray-400 focus:outline-none disabled:opacity-50
							{validationError && emailInput.trim()
							? 'border-red-400 focus:border-red-400'
							: 'border-gray-200 focus:border-blue-500'}"
					/>

					{#if validationError && emailInput.trim()}
						<p data-testid="settings-validation-error" class="text-sm text-red-500">
							{validationError}
						</p>
					{/if}

					{#if errorMsg}
						<p data-testid="settings-error" class="text-sm text-red-500">{errorMsg}</p>
					{/if}

					{#if successMsg}
						<p data-testid="settings-success" class="text-sm text-green-600">{successMsg}</p>
					{/if}

					<button
						onclick={save}
						data-testid="settings-save-btn"
						disabled={!!validationError || !isDirty || saving}
						class="w-full rounded-2xl bg-linear-to-r from-blue-600 to-sky-500 px-4 py-3 font-semibold text-white transition hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-40"
					>
						{saving ? 'Saving…' : 'Save'}
					</button>
				</div>
			</div>
		{:else}
			<div class="flex justify-center pt-12">
				<div
					class="h-8 w-8 animate-spin rounded-full border-4 border-white/30 border-t-white"
				></div>
			</div>
		{/if}
	</div>
</div>

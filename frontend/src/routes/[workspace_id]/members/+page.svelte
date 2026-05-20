<!-- routes/[workspace_id]/members/+page.svelte -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { authStore } from '$lib/stores/auth.store';
	import { fetchMe } from '$lib/backend/auth';
	import { fetchMembers, addMember, removeMember, updateMemberRole } from '$lib/backend/workspaces';
	import type { WorkspaceMemberFull } from '$lib/types/table';
	import { get } from 'svelte/store';
	import { fetchWorkspaces } from '$lib/backend/workspaces';
	import {
		currentWorkspace,
		workspaces,
		currentWorkspaceId
	} from '$lib/stores/table_schemas.store';

	let workspaceId = $derived($page.params.workspace_id ?? '');
	let members = $state<WorkspaceMemberFull[]>([]);
	let loading = $state(true);
	let errorMsg = $state('');
	let currentUserId = $state('');

	let currentRole = $derived(members.find((m) => m.user_id === currentUserId)?.role ?? 'member');
	let isOwner = $derived(currentRole === 'owner');

	let newEmail = $state('');
	let newRole = $state<'owner' | 'member'>('member');
	let adding = $state(false);
	let addError = $state('');

	// Plain boolean (not reactive) so changing it does not re-trigger the effect.
	// Lets us skip fetchMe on subsequent workspace switches after the first auth check.
	let initialized = false;

	$effect(() => {
		const wsId = workspaceId; // track reactive dep
		if (!wsId) return;

		const token = $authStore?.accessToken;
		if (!token) {
			goto('/login');
			return;
		}

		(async () => {
			if (!initialized) {
				const me = await fetchMe(token);
				if (!me) {
					goto('/login');
					return;
				}
				currentUserId = me.user_id;
				initialized = true;
			}

			if (get(currentWorkspace)?.workspace_id !== wsId) {
				await fetchWorkspaces();
				const ws = get(workspaces).find(
					(w) => w.workspace_id === wsId || w.workspace_name === wsId
				);
				if (!ws) {
					goto('/');
					return;
				}
				currentWorkspaceId.set(ws.workspace_id);
			}

			await loadMembers();
		})();
	});

	async function loadMembers() {
		loading = true;
		errorMsg = '';
		try {
			members = await fetchMembers(workspaceId);
		} catch (e) {
			const msg = e instanceof Error ? e.message : '';
			if (msg.includes('403') || msg.includes('Forbidden')) {
				goto('/');
				return;
			}
			errorMsg = 'Failed to load members';
		} finally {
			loading = false;
		}
	}

	async function handleAdd() {
		if (!newEmail.trim()) return;
		adding = true;
		addError = '';
		try {
			const added = await addMember(workspaceId, { user_email: newEmail.trim(), role: newRole });
			members = [...members, added];
			newEmail = '';
			newRole = 'member';
		} catch (e) {
			const msg = e instanceof Error ? e.message : 'Failed to add member';
			addError =
				msg.includes('not found') || msg.includes('404')
					? 'User not found — they must register first'
					: msg;
		} finally {
			adding = false;
		}
	}

	async function handleRoleChange(userId: string, role: string) {
		const prev = members.map((m) => ({ ...m }));
		members = members.map((m) => (m.user_id === userId ? { ...m, role } : m));
		errorMsg = '';
		try {
			await updateMemberRole(workspaceId, userId, role);
		} catch (e) {
			members = prev;
			errorMsg = e instanceof Error ? e.message : 'Failed to update role';
		}
	}

	async function handleRemove(userId: string) {
		const prev = members.map((m) => ({ ...m }));
		members = members.filter((m) => m.user_id !== userId);
		errorMsg = '';
		try {
			await removeMember(workspaceId, userId);
		} catch (e) {
			members = prev;
			errorMsg = e instanceof Error ? e.message : 'Failed to remove member';
		}
	}

	function displayName(m: WorkspaceMemberFull): string {
		if (m.user_name && m.email) return `${m.user_name} (${m.email})`;
		if (m.user_name) return m.user_name;
		if (m.email) return m.email;
		return m.user_id;
	}
</script>

<div class="min-h-screen bg-linear-to-br from-blue-600 via-blue-500 to-sky-500 p-4">
	<div class="mx-auto max-w-2xl">
		<div class="mb-6 flex items-center justify-between pt-8">
			<button
				onclick={() => goto(`/${workspaceId}`)}
				class="flex items-center gap-2 rounded-xl bg-white/20 px-4 py-2 text-white backdrop-blur-sm transition-all hover:bg-white/30"
			>
				← Back
			</button>
			<h1 data-testid="members-heading" class="text-2xl font-bold text-white">
				{$currentWorkspace?.workspace_name ?? 'Workspace'} Members
			</h1>
			<div class="w-20"></div>
		</div>

		{#if errorMsg}
			<div
				data-testid="members-error"
				class="mb-4 rounded-2xl bg-red-100 px-4 py-3 text-sm text-red-700"
			>
				{errorMsg}
			</div>
		{/if}

		<!-- Add member panel (owner only) -->
		{#if isOwner}
			<div class="mb-4 rounded-3xl bg-white p-6 shadow-2xl">
				<h2 class="mb-4 text-lg font-bold text-gray-800">Add Member</h2>
				<div class="flex gap-2">
					<input
						type="email"
						bind:value={newEmail}
						data-testid="member-email-input"
						placeholder="user@example.com"
						disabled={adding}
						class="flex-1 rounded-2xl border-2 bg-gray-50 px-4 py-2.5 text-gray-800 placeholder-gray-400 focus:outline-none disabled:opacity-50
							{addError ? 'border-red-400' : 'border-gray-200 focus:border-blue-500'}"
					/>
					<select
						bind:value={newRole}
						data-testid="member-role-select"
						disabled={adding}
						class="rounded-2xl border-2 border-gray-200 bg-gray-50 px-3 py-2.5 text-sm text-gray-700 focus:border-blue-500 focus:outline-none disabled:opacity-50"
					>
						<option value="member">member</option>
						<option value="owner">owner</option>
					</select>
					<button
						onclick={handleAdd}
						data-testid="member-add-btn"
						disabled={adding || !newEmail.trim()}
						class="rounded-2xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
					>
						{adding ? 'Adding…' : 'Add'}
					</button>
				</div>
				{#if addError}
					<p data-testid="member-add-error" class="mt-2 text-sm text-red-500">{addError}</p>
				{/if}
			</div>
		{/if}

		<!-- Members list -->
		<div class="rounded-3xl bg-white shadow-2xl">
			<div class="border-b border-gray-100 px-6 py-4">
				<h2 class="text-lg font-bold text-gray-800">
					{loading ? 'Loading…' : `${members.length} member${members.length !== 1 ? 's' : ''}`}
				</h2>
			</div>

			{#if loading}
				<div class="flex justify-center py-12">
					<div
						class="h-8 w-8 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600"
					></div>
				</div>
			{:else if members.length === 0}
				<p class="px-6 py-8 text-center text-sm text-gray-400">No members found</p>
			{:else}
				<ul data-testid="members-list">
					{#each members as member (member.user_id)}
						<li
							data-testid="member-row-{member.user_id}"
							class="flex items-center gap-3 border-b border-gray-50 px-6 py-4 last:border-0"
						>
							<!-- Avatar -->
							<div
								class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-100 text-sm font-semibold text-blue-600"
							>
								{(member.user_name || member.email || '?').charAt(0).toUpperCase()}
							</div>

							<!-- Name + email -->
							<div class="min-w-0 flex-1">
								<p class="truncate text-sm font-medium text-gray-800">
									{displayName(member)}
									{#if member.user_id === currentUserId}
										<span class="ml-1 text-xs text-gray-400">(you)</span>
									{/if}
								</p>
								<p class="truncate text-xs text-gray-400">{member.user_id}</p>
							</div>

							<!-- Role dropdown (owner only) -->
							{#if isOwner}
								<select
									value={member.role}
									data-testid="role-select-{member.user_id}"
									onchange={(e) =>
										handleRoleChange(member.user_id, (e.target as HTMLSelectElement).value)}
									class="rounded-lg border border-gray-200 bg-gray-50 px-2 py-1 text-xs text-gray-700 focus:outline-none"
								>
									<option value="member">member</option>
									<option value="owner">owner</option>
								</select>
							{:else}
								<span
									class="rounded-full px-2.5 py-0.5 text-xs font-medium
										{member.role === 'owner' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600'}"
								>
									{member.role}
								</span>
							{/if}

							<!-- Remove button (owner only, not self) -->
							{#if isOwner && member.user_id !== currentUserId}
								<button
									onclick={() => handleRemove(member.user_id)}
									data-testid="remove-btn-{member.user_id}"
									class="shrink-0 rounded-lg p-1.5 text-gray-300 transition hover:bg-red-50 hover:text-red-500"
									title="Remove member"
									aria-label="Remove member"
								>
									<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M6 18L18 6M6 6l12 12"
										/>
									</svg>
								</button>
							{:else}
								<div class="w-7"></div>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	</div>
</div>

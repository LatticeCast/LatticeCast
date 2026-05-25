<!--lib/components/sidebar/CreateWorkspaceModal.svelte-->

<script lang="ts">
	import { T } from '$lib/UI/theme.svelte';
	import { createWorkspace } from '$lib/backend/workspaces';
	import type { Workspace } from '$lib/types/table';

	let {
		show,
		onClose,
		onCreated
	}: {
		show: boolean;
		onClose: () => void;
		onCreated: (ws: Workspace) => void;
	} = $props();

	let name = $state('');
	let pending = $state(false);
	let errorMsg = $state('');
	let inputEl = $state<HTMLInputElement | null>(null);

	$effect(() => {
		if (show) {
			name = '';
			errorMsg = '';
			pending = false;
			setTimeout(() => inputEl?.focus(), 50);
		}
	});

	async function submit() {
		if (!name.trim() || pending) return;
		pending = true;
		errorMsg = '';
		try {
			const ws = await createWorkspace({ workspace_name: name.trim() });
			onCreated(ws);
		} catch (e) {
			errorMsg = e instanceof Error ? e.message : 'Failed to create workspace';
		} finally {
			pending = false;
		}
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') submit();
		if (e.key === 'Escape') onClose();
	}
</script>

{#if show}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
		onclick={(e) => {
			if (e.target === e.currentTarget) onClose();
		}}
		role="dialog"
		aria-modal="true"
		aria-label="Create workspace"
		tabindex="-1"
	>
		<div class="w-full max-w-sm rounded-3xl p-6 shadow-2xl {T.cardBg} {T.heading}">
			<h2 class="mb-4 text-base font-semibold">New Workspace</h2>

			<input
				bind:this={inputEl}
				bind:value={name}
				data-testid="create-workspace-name-input"
				type="text"
				placeholder="Workspace name"
				onkeydown={onKeydown}
				class="mb-3 w-full rounded-lg border px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 {T.inputBorder} {T.inputBg} {T.heading} {T.placeholder}"
			/>

			{#if errorMsg}
				<p data-testid="create-workspace-error" class="mb-3 text-xs text-red-500">{errorMsg}</p>
			{/if}

			<div class="flex justify-end gap-2">
				<button
					data-testid="create-workspace-cancel"
					onclick={onClose}
					class="rounded-lg px-4 py-2 text-sm transition {T.secondary} {T.menuItemHover}"
				>
					Cancel
				</button>
				<button
					data-testid="create-workspace-submit"
					onclick={submit}
					disabled={!name.trim() || pending}
					class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
				>
					{pending ? 'Creating…' : 'Create'}
				</button>
			</div>
		</div>
	</div>
{/if}

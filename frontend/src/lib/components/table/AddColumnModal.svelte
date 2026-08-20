<script lang="ts">
	import { BLOB_KIND_OPTIONS, COLUMN_TYPES } from './table.utils';
	import type { BlobKind, ColumnOptions } from '$lib/types/table';

	let {
		show,
		onClose,
		onAdd,
		pending = false
	}: {
		show: boolean;
		onClose: () => void;
		onAdd: (name: string, type: string, options?: ColumnOptions) => void;
		pending?: boolean;
	} = $props();

	let newColName = $state('');
	let newColType = $state<string>('text');
	let newBlobKind = $state<BlobKind>('file');

	function handleAdd() {
		if (!newColName.trim()) return;
		const blobOption = BLOB_KIND_OPTIONS.find((option) => option.value === newBlobKind);
		onAdd(
			newColName.trim(),
			newColType,
			newColType === 'blob'
				? { kind: newBlobKind, ...(blobOption?.accept ? { accept: blobOption.accept } : {}) }
				: undefined
		);
		newColName = '';
		newColType = 'text';
		newBlobKind = 'file';
	}

	function handleClose() {
		newColName = '';
		newColType = 'text';
		newBlobKind = 'file';
		onClose();
	}
</script>

{#if show}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
		onclick={(e) => {
			if (e.target === e.currentTarget) handleClose();
		}}
		role="dialog"
		aria-modal="true"
		aria-label="Add column"
	>
		<div class="w-full max-w-sm rounded-3xl bg-white p-8 shadow-2xl">
			<h2 class="mb-6 text-xl font-bold text-gray-800">Add Column</h2>
			<div class="mb-4">
				<label class="mb-1 block text-sm font-medium text-gray-600" for="col-name">Name</label>
				<input
					id="col-name"
					data-testid="add-column-name-input"
					class="w-full rounded-xl border border-gray-200 px-4 py-2 text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
					bind:value={newColName}
					placeholder="Column name"
					onkeydown={(e) => {
						if (e.key === 'Enter') handleAdd();
					}}
					autofocus
				/>
			</div>
			<div class="mb-6">
				<label class="mb-1 block text-sm font-medium text-gray-600" for="col-type">Type</label>
				<select
					id="col-type"
					class="w-full rounded-xl border border-gray-200 px-4 py-2 text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
					bind:value={newColType}
				>
					{#each COLUMN_TYPES as t (t)}
						<option value={t}>{t}</option>
					{/each}
				</select>
			</div>
			{#if newColType === 'blob'}
				<div class="mb-6">
					<label class="mb-1 block text-sm font-medium text-gray-600" for="blob-kind">Blob category</label>
					<select
						id="blob-kind"
						data-testid="blob-kind-select"
						class="w-full rounded-xl border border-gray-200 px-4 py-2 text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
						bind:value={newBlobKind}
					>
						{#each BLOB_KIND_OPTIONS as option (option.value)}
							<option value={option.value}>{option.label}</option>
						{/each}
					</select>
					<p class="mt-1 text-xs text-gray-500">
						{BLOB_KIND_OPTIONS.find((option) => option.value === newBlobKind)?.description}
					</p>
				</div>
			{/if}
			<div class="flex gap-3">
				<button
					data-testid="add-column-cancel-btn"
					onclick={handleClose}
					class="flex-1 rounded-2xl border border-gray-200 px-4 py-2 font-semibold text-gray-600 transition hover:bg-gray-50"
				>
					Cancel
				</button>
				<button
					data-testid="add-column-submit-btn"
					onclick={handleAdd}
					disabled={!newColName.trim() || pending}
					class="flex flex-1 items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 py-2 font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
				>
					{#if pending}
						<svg class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
							<circle
								class="opacity-25"
								cx="12"
								cy="12"
								r="10"
								stroke="currentColor"
								stroke-width="4"
							></circle>
							<path
								class="opacity-75"
								fill="currentColor"
								d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
							></path>
						</svg>
						Adding…
					{:else}
						Add Column
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}

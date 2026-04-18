<script lang="ts">
	import { COLUMN_TYPES } from './table.utils';

	let {
		show,
		onClose,
		onAdd
	}: {
		show: boolean;
		onClose: () => void;
		onAdd: (name: string, type: string) => void;
	} = $props();

	let newColName = $state('');
	let newColType = $state<string>('text');

	function handleAdd() {
		if (!newColName.trim()) return;
		onAdd(newColName.trim(), newColType);
		newColName = '';
		newColType = 'text';
	}

	function handleClose() {
		newColName = '';
		newColType = 'text';
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
					disabled={!newColName.trim()}
					class="flex-1 rounded-2xl bg-blue-600 px-4 py-2 font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
				>
					Add Column
				</button>
			</div>
		</div>
	</div>
{/if}

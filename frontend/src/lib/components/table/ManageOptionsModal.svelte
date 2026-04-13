<script lang="ts">
	import type { Column, ColumnChoice } from '$lib/types/table';
	import { TAG_COLORS } from '$lib/UI/theme.svelte';
	import { getChoices } from './table.utils';

	let {
		col,
		onClose,
		onSave
	}: {
		col: Column;
		onClose: () => void;
		onSave: (colId: string, choices: ColumnChoice[]) => void;
	} = $props();

	let choices = $state<ColumnChoice[]>([...getChoices(col)]);
	let newValue = $state('');
	let draggedIdx = $state<number | null>(null);

	function onDragStart(i: number) {
		draggedIdx = i;
	}

	function onDragOver(e: DragEvent, i: number) {
		e.preventDefault();
		if (draggedIdx === null || draggedIdx === i) return;
		const updated = [...choices];
		const [item] = updated.splice(draggedIdx, 1);
		updated.splice(i, 0, item);
		choices = updated;
		draggedIdx = i;
	}

	function onDragEnd() {
		draggedIdx = null;
	}

	function addChoice() {
		const val = newValue.trim();
		if (!val || choices.some((c) => c.value === val)) return;
		const colorIdx = choices.length % TAG_COLORS.length;
		choices = [...choices, { value: val, color: TAG_COLORS[colorIdx].bg }];
		newValue = '';
	}

	function removeChoice(value: string) {
		choices = choices.filter((c) => c.value !== value);
	}

	function handleSave() {
		onSave(col.column_id, choices);
		onClose();
	}
</script>

<div
	class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
	onclick={(e) => {
		if (e.target === e.currentTarget) onClose();
	}}
	role="dialog"
	aria-modal="true"
	aria-label="Manage options"
>
	<div class="w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl">
		<h2 class="mb-1 text-lg font-bold text-gray-800">Manage Options</h2>
		<p class="mb-4 text-sm text-gray-500">
			{col.name} <span class="text-gray-400">({col.type})</span>
		</p>

		<!-- Existing choices -->
		<div class="mb-4 space-y-1.5">
			{#each choices as choice, i (choice.value)}
				{@const color = TAG_COLORS[i % TAG_COLORS.length]}
				<div
					class="flex items-center gap-2 rounded transition-opacity {draggedIdx === i
						? 'opacity-40'
						: ''}"
					draggable="true"
					ondragstart={() => onDragStart(i)}
					ondragover={(e) => onDragOver(e, i)}
					ondragend={onDragEnd}
				>
					<!-- drag handle -->
					<svg
						class="h-3.5 w-3.5 shrink-0 cursor-grab text-gray-300 active:cursor-grabbing"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M4 8h16M4 16h16"
						/>
					</svg>
					<span
						class="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
					>
						{choice.value}
					</span>
					<div class="flex-1"></div>
					<button
						onclick={() => removeChoice(choice.value)}
						class="rounded p-1 text-gray-300 hover:bg-red-50 hover:text-red-500"
						aria-label="Remove {choice.value}"
					>
						<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M6 18L18 6M6 6l12 12"
							/>
						</svg>
					</button>
				</div>
			{:else}
				<p class="text-sm text-gray-400">No options yet.</p>
			{/each}
		</div>

		<!-- Add new choice -->
		<div class="mb-5 flex gap-2">
			<input
				class="min-w-0 flex-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
				bind:value={newValue}
				placeholder="New option..."
				onkeydown={(e) => {
					if (e.key === 'Enter') addChoice();
				}}
			/>
			<button
				onclick={addChoice}
				disabled={!newValue.trim()}
				class="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
			>
				Add
			</button>
		</div>

		<!-- Actions -->
		<div class="flex gap-3">
			<button
				onclick={onClose}
				class="flex-1 rounded-xl border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 transition hover:bg-gray-50"
			>
				Cancel
			</button>
			<button
				onclick={handleSave}
				class="flex-1 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700"
			>
				Save
			</button>
		</div>
	</div>
</div>

<script lang="ts">
	import type { Column } from '$lib/types/table';
	import { getChoices } from './table.utils';
	import { T } from '$lib/UI/theme.svelte';

	let {
		show,
		columns,
		initialData = {},
		onClose,
		onSubmit
	}: {
		show: boolean;
		columns: Column[];
		initialData?: Record<string, unknown>;
		onClose: () => void;
		onSubmit: (rowData: Record<string, unknown>) => void;
	} = $props();

	// Primary text column for the ticket title (prefer "Title", fallback to first text/string col)
	const titleCol = $derived(
		columns.find((c) => c.name === 'Title' && (c.type === 'text' || c.type === 'string')) ??
			columns.find((c) => c.type === 'text' || c.type === 'string')
	);

	// Select columns to show (skip auto-generated "Key" column)
	const selectCols = $derived(
		columns.filter((c) => c.type === 'select' && c.name !== 'Key').slice(0, 4)
	);

	let titleValue = $state('');
	let selectValues = $state<Record<string, string>>({});

	$effect(() => {
		if (show) {
			titleValue = titleCol ? String(initialData[titleCol.column_id] ?? '') : '';
			const init: Record<string, string> = {};
			for (const col of selectCols) {
				init[col.column_id] = initialData[col.column_id] ? String(initialData[col.column_id]) : '';
			}
			selectValues = init;
		}
	});

	function handleSubmit() {
		const rowData: Record<string, unknown> = { ...initialData };
		if (titleCol && titleValue.trim()) {
			rowData[titleCol.column_id] = titleValue.trim();
		}
		for (const col of selectCols) {
			if (selectValues[col.column_id]) {
				rowData[col.column_id] = selectValues[col.column_id];
			}
		}
		onSubmit(rowData);
		titleValue = '';
		selectValues = {};
	}

	function handleClose() {
		titleValue = '';
		selectValues = {};
		onClose();
	}
</script>

{#if show}
	<div
		data-testid="create-ticket-modal"
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
		onclick={(e) => {
			if (e.target === e.currentTarget) handleClose();
		}}
		role="dialog"
		aria-modal="true"
		aria-label="Create ticket"
	>
		<div class="w-full max-w-sm rounded-3xl p-8 shadow-2xl {T.cardBg}">
			<h2 class="mb-6 text-xl font-bold {T.heading}">New Ticket</h2>

			{#if titleCol}
				<div class="mb-4">
					<label class="mb-1 block text-sm font-medium {T.secondary}" for="ticket-title"
						>{titleCol.name}</label
					>
					<input
						id="ticket-title"
						data-testid="create-ticket-title-input"
						class="w-full rounded-xl border px-4 py-2 outline-none focus:ring-1 focus:ring-blue-500 {T.inputBorder} {T.inputBg} {T.heading} {T.inputFocusBorder}"
						bind:value={titleValue}
						placeholder="Ticket title…"
						onkeydown={(e) => {
							if (e.key === 'Enter' && !e.shiftKey) handleSubmit();
							if (e.key === 'Escape') handleClose();
						}}
						autofocus
					/>
				</div>
			{/if}

			{#each selectCols as col (col.column_id)}
				{@const choices = getChoices(col)}
				<div class="mb-4">
					<label class="mb-1 block text-sm font-medium {T.secondary}" for="ticket-{col.column_id}"
						>{col.name}</label
					>
					<select
						id="ticket-{col.column_id}"
						data-testid="create-ticket-select-{col.column_id}"
						class="w-full rounded-xl border px-4 py-2 outline-none focus:ring-1 focus:ring-blue-500 {T.inputBorder} {T.inputBg} {T.heading} {T.inputFocusBorder}"
						value={selectValues[col.column_id] ?? ''}
						onchange={(e) => {
							selectValues = {
								...selectValues,
								[col.column_id]: (e.target as HTMLSelectElement).value
							};
						}}
					>
						<option value="">— none —</option>
						{#each choices as c (c.value)}
							<option value={c.value}>{c.value}</option>
						{/each}
					</select>
				</div>
			{/each}

			<div class="flex gap-3">
				<button
					onclick={handleClose}
					class="flex-1 rounded-2xl border px-4 py-2 font-semibold transition {T.inputBorder} {T.secondary} {T.menuItemHover}"
				>
					Cancel
				</button>
				<button
					data-testid="create-ticket-submit-btn"
					onclick={handleSubmit}
					class="flex-1 rounded-2xl bg-blue-600 px-4 py-2 font-semibold text-white transition hover:bg-blue-700"
				>
					Create
				</button>
			</div>
		</div>
	</div>
{/if}

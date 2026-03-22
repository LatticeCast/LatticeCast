<script lang="ts">
	import type { Column, Row } from '$lib/types/table';
	import { TAG_COLORS } from '$lib/UI/theme.svelte';
	import { getChoices, getChoiceColor, getTagValues, formatDate } from './table.utils';

	let {
		row,
		columns,
		onClose,
		onUpdateRow,
		onRefreshRows,
		tableId
	}: {
		row: Row;
		columns: Column[];
		onClose: () => void;
		onUpdateRow: (rowId: string, data: Record<string, unknown>) => Promise<void>;
		onRefreshRows: (tableId: string) => Promise<void>;
		tableId: string;
	} = $props();

	let editField = $state<string | null>(null);
	let editVal = $state('');
	let tagsPopup = $state<string | null>(null);

	// Local copy so we can update inline
	let localRow = $state<Row>(row);
	$effect(() => {
		localRow = row;
	});

	const sortedCols = $derived([...columns].sort((a, b) => a.position - b.position));

	function startEdit(col: Column) {
		editField = col.id;
		const val = localRow.data[col.id];
		editVal = val === null || val === undefined ? '' : String(val);
	}

	async function commitEdit(col: Column) {
		if (editField !== col.id) return;
		editField = null;
		let parsed: unknown = editVal;
		if (col.type === 'number') parsed = editVal === '' ? null : Number(editVal);
		else if (col.type === 'checkbox') parsed = editVal === 'true';
		else if (editVal === '') parsed = null;
		const newData = { ...localRow.data, [col.id]: parsed };
		localRow = { ...localRow, data: newData };
		await onUpdateRow(localRow.id, newData);
		await onRefreshRows(tableId);
	}

	async function toggleCheckbox(col: Column) {
		const current = !!localRow.data[col.id];
		const newData = { ...localRow.data, [col.id]: !current };
		localRow = { ...localRow, data: newData };
		await onUpdateRow(localRow.id, newData);
		await onRefreshRows(tableId);
	}

	async function removeTag(col: Column, tag: string) {
		const current = getTagValues(localRow, col.id);
		const newData = { ...localRow.data, [col.id]: current.filter((t) => t !== tag) };
		localRow = { ...localRow, data: newData };
		await onUpdateRow(localRow.id, newData);
		await onRefreshRows(tableId);
	}

	async function addTag(col: Column, tag: string) {
		const current = getTagValues(localRow, col.id);
		if (current.includes(tag)) return;
		const newData = { ...localRow.data, [col.id]: [...current, tag] };
		tagsPopup = null;
		localRow = { ...localRow, data: newData };
		await onUpdateRow(localRow.id, newData);
		await onRefreshRows(tableId);
	}
</script>

<!-- Backdrop -->
<div class="fixed inset-0 z-40 bg-black/30" onclick={onClose} role="presentation"></div>

<!-- Slide-out panel -->
<div
	class="fixed top-0 right-0 z-50 flex h-full w-full max-w-md flex-col bg-white shadow-2xl"
	role="dialog"
	aria-modal="true"
	aria-label="Row details"
>
	<!-- Panel header -->
	<div class="flex items-center justify-between border-b border-gray-200 bg-blue-600 px-6 py-3">
		<h2 class="text-lg font-semibold text-white">Row Details</h2>
		<button
			onclick={onClose}
			class="rounded-lg p-1.5 text-white/70 transition hover:bg-white/20 hover:text-white"
			aria-label="Close panel"
		>
			<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M6 18L18 6M6 6l12 12"
				/>
			</svg>
		</button>
	</div>

	<!-- Fields list -->
	<div class="flex-1 overflow-y-auto px-6 py-4">
		{#each sortedCols as col (col.id)}
			<div class="mb-5">
				<label class="mb-1 block text-xs font-semibold tracking-wide text-gray-400 uppercase">
					{col.name}
					<span class="ml-1 font-normal text-gray-300 normal-case">({col.type})</span>
				</label>

				{#if col.type === 'checkbox'}
					<button
						class="relative inline-flex h-6 w-10 items-center rounded-full transition {localRow
							.data[col.id]
							? 'bg-blue-500'
							: 'bg-gray-200'}"
						onclick={() => toggleCheckbox(col)}
						role="switch"
						aria-checked={!!localRow.data[col.id]}
					>
						<span
							class="inline-block h-4 w-4 transform rounded-full bg-white shadow transition {localRow
								.data[col.id]
								? 'translate-x-5'
								: 'translate-x-1'}"
						></span>
					</button>
				{:else if col.type === 'select'}
					{@const choices = getChoices(col)}
					{#if editField === col.id}
						<select
							class="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
							bind:value={editVal}
							onblur={() => commitEdit(col)}
							onchange={() => commitEdit(col)}
							autofocus
						>
							<option value="">—</option>
							{#each choices as choice (choice.value)}
								<option value={choice.value}>{choice.value}</option>
							{/each}
						</select>
					{:else}
						{@const selVal = (localRow.data[col.id] as string) ?? ''}
						<button
							class="flex min-h-[2.25rem] w-full items-center rounded-xl border border-gray-200 px-3 py-2 text-left text-sm hover:border-blue-300"
							onclick={() => startEdit(col)}
						>
							{#if selVal}
								{@const color = getChoiceColor(col, selVal)}
								<span
									class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
									>{selVal}</span
								>
							{:else}
								<span class="text-gray-400">—</span>
							{/if}
						</button>
					{/if}
				{:else if col.type === 'tags'}
					{@const tagVals = getTagValues(localRow, col.id)}
					{@const choices = getChoices(col)}
					{@const available = choices.filter((c) => !tagVals.includes(c.value))}
					<div
						class="flex min-h-[2.25rem] flex-wrap items-center gap-1 rounded-xl border border-gray-200 px-3 py-2"
					>
						{#each tagVals as tag (tag)}
							{@const color = getChoiceColor(col, tag)}
							<span
								class="inline-flex items-center gap-0.5 rounded-full border px-2 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
							>
								{tag}
								<button
									class="ml-0.5 rounded-full leading-none hover:opacity-60"
									onclick={() => removeTag(col, tag)}
									aria-label="Remove {tag}">×</button
								>
							</span>
						{/each}
						{#if available.length > 0}
							<div class="relative">
								<button
									class="rounded-full border border-gray-300 px-2 py-0.5 text-xs text-gray-400 hover:border-blue-400 hover:text-blue-600"
									onclick={() => {
										tagsPopup = tagsPopup === col.id ? null : col.id;
									}}>+</button
								>
								{#if tagsPopup === col.id}
									<div
										class="absolute top-full left-0 z-20 mt-1 min-w-[120px] rounded-xl border border-gray-100 bg-white py-1 shadow-xl"
									>
										{#each available as choice (choice.value)}
											{@const color = TAG_COLORS[choices.indexOf(choice) % TAG_COLORS.length]}
											<button
												class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-gray-50"
												onclick={() => addTag(col, choice.value)}
											>
												<span
													class="inline-flex items-center rounded-full border px-2 py-0.5 font-medium {color.bg} {color.text} {color.border}"
													>{choice.value}</span
												>
											</button>
										{/each}
									</div>
								{/if}
							</div>
						{/if}
					</div>
				{:else if col.type === 'url'}
					{#if editField === col.id}
						<input
							type="url"
							class="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
							bind:value={editVal}
							onblur={() => commitEdit(col)}
							onkeydown={(e) => {
								if (e.key === 'Enter') commitEdit(col);
								if (e.key === 'Escape') editField = null;
							}}
							autofocus
						/>
					{:else}
						{@const urlVal = (localRow.data[col.id] as string) ?? ''}
						<button
							class="flex min-h-[2.25rem] w-full items-center rounded-xl border border-gray-200 px-3 py-2 text-left text-sm hover:border-blue-300"
							onclick={() => startEdit(col)}
						>
							{#if urlVal}
								<a
									href={urlVal}
									target="_blank"
									rel="noopener noreferrer"
									class="truncate text-sky-600 underline hover:text-sky-800"
									onclick={(e) => e.stopPropagation()}
									title={urlVal}>{urlVal}</a
								>
							{:else}
								<span class="text-gray-400">—</span>
							{/if}
						</button>
					{/if}
				{:else if col.type === 'date'}
					{#if editField === col.id}
						<input
							type="date"
							class="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
							bind:value={editVal}
							onblur={() => commitEdit(col)}
							onkeydown={(e) => {
								if (e.key === 'Enter') commitEdit(col);
								if (e.key === 'Escape') editField = null;
							}}
							autofocus
						/>
					{:else}
						{@const dateVal = localRow.data[col.id]
							? formatDate(String(localRow.data[col.id]))
							: ''}
						<button
							class="flex min-h-[2.25rem] w-full items-center rounded-xl border border-gray-200 px-3 py-2 text-left font-mono text-sm hover:border-blue-300"
							onclick={() => startEdit(col)}
						>
							{#if dateVal}{dateVal}{:else}<span class="font-sans text-gray-400">—</span>{/if}
						</button>
					{/if}
				{:else if col.type === 'number'}
					{#if editField === col.id}
						<input
							type="number"
							class="w-full rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
							bind:value={editVal}
							onblur={() => commitEdit(col)}
							onkeydown={(e) => {
								if (e.key === 'Enter') commitEdit(col);
								if (e.key === 'Escape') editField = null;
							}}
							autofocus
						/>
					{:else}
						<button
							class="flex min-h-[2.25rem] w-full items-center rounded-xl border border-gray-200 px-3 py-2 text-left text-sm hover:border-blue-300"
							onclick={() => startEdit(col)}
						>
							{#if localRow.data[col.id] !== null && localRow.data[col.id] !== undefined}
								<span class="text-gray-800">{String(localRow.data[col.id])}</span>
							{:else}
								<span class="text-gray-400">—</span>
							{/if}
						</button>
					{/if}
				{:else if editField === col.id}
					<textarea
						class="w-full resize-none rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
						rows="3"
						bind:value={editVal}
						onblur={() => commitEdit(col)}
						onkeydown={(e) => {
							if (e.key === 'Enter' && !e.shiftKey) commitEdit(col);
							if (e.key === 'Escape') editField = null;
						}}
						autofocus
					></textarea>
				{:else}
					<button
						class="flex min-h-[2.25rem] w-full items-start rounded-xl border border-gray-200 px-3 py-2 text-left text-sm hover:border-blue-300"
						onclick={() => startEdit(col)}
					>
						{#if localRow.data[col.id] !== null && localRow.data[col.id] !== undefined && String(localRow.data[col.id]) !== ''}
							<span class="break-words whitespace-pre-wrap text-gray-800"
								>{String(localRow.data[col.id])}</span
							>
						{:else}
							<span class="text-gray-400">—</span>
						{/if}
					</button>
				{/if}
			</div>
		{/each}
	</div>
</div>

<script lang="ts">
	import type { Column, Row } from '$lib/types/table';
	import { T } from '$lib/UI/theme.svelte';
	import {
		getChoices,
		getChoiceColor,
		colorToStyle,
		getTagValues,
		formatCellDate,
		isTemporalType,
		formatBlobSize,
		getBlobCellMetadata,
		applyEditToRowData,
		toggleCheckboxInRowData,
		removeTagFromRowData,
		addTagToRowData
	} from './table.utils';
	import { downloadBlobCell, uploadBlobCell } from '$lib/backend/tables';
	import { rows } from '$lib/stores/table_rows.store';

	let {
		row,
		columns,
		onClose,
		onUpdateRow,
		tableId,
		workspaceId
	}: {
		row: Row;
		columns: Column[];
		onClose: () => void;
		onUpdateRow: (rowNumber: number, data: Record<string, unknown>) => Promise<void>;
		tableId: string;
		workspaceId: string;
	} = $props();

	let editField = $state<string | null>(null);
	let editVal = $state('');
	let tagsPopup = $state<string | null>(null);

	// The selected row may be replaced by an authoritative controller response.
	// Derive it from the shared cache instead of maintaining an optimistic copy.
	const currentRow = $derived($rows.find((candidate) => candidate.row_id === row.row_id) ?? row);

	const sortedCols = $derived(columns);

	function startEdit(col: Column) {
		editField = col.column_id;
		const val = currentRow.row_data[col.column_id];
		editVal = val === null || val === undefined ? '' : String(val);
	}

	async function commitEdit(col: Column) {
		if (editField !== col.column_id) return;
		editField = null;
		const newData = applyEditToRowData(currentRow.row_data, col.column_id, editVal, col.type);
		await onUpdateRow(currentRow.row_id, newData);
	}

	async function toggleCheckbox(col: Column) {
		const newData = toggleCheckboxInRowData(currentRow.row_data, col.column_id);
		await onUpdateRow(currentRow.row_id, newData);
	}

	async function removeTag(col: Column, tag: string) {
		const newData = removeTagFromRowData(currentRow.row_data, col.column_id, tag);
		await onUpdateRow(currentRow.row_id, newData);
	}

	async function addTag(col: Column, tag: string) {
		const newData = addTagToRowData(currentRow.row_data, col.column_id, tag);
		if (newData === currentRow.row_data) return; // tag already present
		tagsPopup = null;
		await onUpdateRow(currentRow.row_id, newData);
	}

	async function handleBlobDownload(col: Column, filename: string) {
		try {
			await downloadBlobCell(tableId, currentRow.row_id, col.column_id, filename);
		} catch {
			// The descriptor in the row store is still valid; the user can retry the download.
		}
	}

	function chooseBlobFile(col: Column) {
		const input = document.createElement('input');
		input.type = 'file';
		input.accept = col.options?.accept ?? '';
		input.onchange = () => {
			const file = input.files?.[0];
			input.remove();
			if (!file) return;
			void uploadBlobCell(tableId, currentRow.row_id, col.column_id, file);
		};
		document.body.appendChild(input);
		input.click();
	}
</script>

<!-- Backdrop -->
<div class="fixed inset-0 z-40 bg-black/30" onclick={onClose} role="presentation"></div>

<!-- Slide-out panel -->
<div
	class="fixed top-0 right-0 z-50 flex h-full w-full max-w-md flex-col shadow-2xl {T.cardBg}"
	role="dialog"
	aria-modal="true"
	aria-label="Row details"
>
	<!-- Panel header -->
	<div class="flex items-center justify-between border-b bg-blue-600 px-6 py-3 {T.border}">
		<h2 class="text-lg font-semibold text-white">Row Details</h2>
		<div class="flex items-center gap-2">
			<a
				data-testid="row-panel-open-fullpage-link"
				href="/{workspaceId}/{tableId}/{row.row_id}"
				class="rounded-lg px-3 py-1.5 text-sm font-medium text-white/80 transition hover:bg-white/20 hover:text-white"
				aria-label="Open full page">Open full page</a
			>
			<button
				data-testid="row-panel-close-btn"
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
	</div>

	<!-- Fields list -->
	<div class="flex-1 overflow-y-auto px-6 py-4">
		{#each sortedCols as col (col.column_id)}
			<div class="mb-5">
				<label class="mb-1 block text-xs font-semibold tracking-wide uppercase {T.muted}">
					{col.name}
					<span class="ml-1 font-normal text-gray-300 normal-case">({col.type})</span>
				</label>

				{#if col.type === 'checkbox'}
					<button
						data-testid="row-panel-field-{col.column_id}-toggle"
						class="relative inline-flex h-6 w-10 items-center rounded-full transition {currentRow
							.row_data[col.column_id]
							? 'bg-blue-500'
							: 'bg-gray-200'}"
						onclick={() => toggleCheckbox(col)}
						role="switch"
						aria-checked={!!currentRow.row_data[col.column_id]}
					>
						<span
							class="inline-block h-4 w-4 transform rounded-full bg-white shadow transition {currentRow
								.row_data[col.column_id]
								? 'translate-x-5'
								: 'translate-x-1'}"
						></span>
					</button>
				{:else if col.type === 'select'}
					{@const choices = getChoices(col)}
					{#if editField === col.column_id}
						<select
							class="w-full rounded-xl border px-3 py-2 text-sm outline-none focus:ring-1 {T.inputBorder} {T.inputBg} {T.body} {T.inputFocusBorder} focus:ring-blue-500"
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
						{@const selVal = (currentRow.row_data[col.column_id] as string) ?? ''}
						<button
							data-testid="row-panel-field-{col.column_id}-select-btn"
							class="flex min-h-[2.25rem] w-full items-center rounded-xl border px-3 py-2 text-left text-sm {T.inputBorder} hover:border-blue-400"
							onclick={() => startEdit(col)}
						>
							{#if selVal}
								{@const color = getChoiceColor(col, selVal)}
								<span
									class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium {color.cls}"
									style={color.style}>{selVal}</span
								>
							{:else}
								<span class="text-gray-400">—</span>
							{/if}
						</button>
					{/if}
				{:else if col.type === 'tags'}
					{@const tagVals = getTagValues(currentRow, col.column_id)}
					{@const choices = getChoices(col)}
					{@const available = choices.filter((c) => !tagVals.includes(c.value))}
					<div
						class="flex min-h-[2.25rem] flex-wrap items-center gap-1 rounded-xl border px-3 py-2 {T.inputBorder}"
					>
						{#each tagVals as tag (tag)}
							{@const color = getChoiceColor(col, tag)}
							<span
								class="inline-flex items-center gap-0.5 rounded-full border px-2 py-0.5 text-xs font-medium {color.cls}"
								style={color.style}
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
										tagsPopup = tagsPopup === col.column_id ? null : col.column_id;
									}}>+</button
								>
								{#if tagsPopup === col.column_id}
									<div
										class="absolute top-full left-0 z-20 mt-1 min-w-[120px] rounded-xl border py-1 shadow-xl {T.cardBorder} {T.cardBg}"
									>
										{#each available as choice (choice.value)}
											{@const cs = colorToStyle(choice.color)}
											<button
												class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs {T.menuItemHover}"
												onclick={() => addTag(col, choice.value)}
											>
												<span
													class="inline-flex items-center rounded-full border px-2 py-0.5 font-medium {cs.cls}"
													style={cs.style}>{choice.value}</span
												>
											</button>
										{/each}
									</div>
								{/if}
							</div>
						{/if}
					</div>
				{:else if col.type === 'url'}
					{#if editField === col.column_id}
						<input
							type="url"
							class="w-full rounded-xl border px-3 py-2 text-sm outline-none focus:ring-1 {T.inputBorder} {T.inputBg} {T.body} {T.inputFocusBorder} focus:ring-blue-500"
							bind:value={editVal}
							onblur={() => commitEdit(col)}
							onkeydown={(e) => {
								if (e.key === 'Enter') commitEdit(col);
								if (e.key === 'Escape') editField = null;
							}}
							autofocus
						/>
					{:else}
						{@const urlVal = (currentRow.row_data[col.column_id] as string) ?? ''}
						<button
							class="flex min-h-[2.25rem] w-full items-center rounded-xl border px-3 py-2 text-left text-sm {T.inputBorder} hover:border-blue-400"
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
				{:else if isTemporalType(col.type)}
					{#if editField === col.column_id}
						<input
							type={col.type === 'date' ? 'date' : 'datetime-local'}
							class="w-full rounded-xl border px-3 py-2 text-sm outline-none focus:ring-1 {T.inputBorder} {T.inputBg} {T.body} {T.inputFocusBorder} focus:ring-blue-500"
							bind:value={editVal}
							onblur={() => commitEdit(col)}
							onkeydown={(e) => {
								if (e.key === 'Enter') commitEdit(col);
								if (e.key === 'Escape') editField = null;
							}}
							autofocus
						/>
					{:else}
						{@const dateVal = formatCellDate(currentRow.row_data[col.column_id], col.type)}
						<button
							class="flex min-h-[2.25rem] w-full items-center rounded-xl border px-3 py-2 text-left font-mono text-sm {T.inputBorder} hover:border-blue-400"
							onclick={() => startEdit(col)}
						>
							{#if dateVal}{dateVal}{:else}<span class="font-sans text-gray-400">—</span>{/if}
						</button>
					{/if}
				{:else if col.type === 'number'}
					{#if editField === col.column_id}
						<input
							type="number"
							class="w-full rounded-xl border px-3 py-2 text-sm outline-none focus:ring-1 {T.inputBorder} {T.inputBg} {T.body} {T.inputFocusBorder} focus:ring-blue-500"
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
							class="flex min-h-[2.25rem] w-full items-center rounded-xl border px-3 py-2 text-left text-sm {T.inputBorder} hover:border-blue-400"
							onclick={() => startEdit(col)}
						>
							{#if currentRow.row_data[col.column_id] !== null && currentRow.row_data[col.column_id] !== undefined}
								<span class={T.body}>{String(currentRow.row_data[col.column_id])}</span>
							{:else}
								<span class="text-gray-400">—</span>
							{/if}
						</button>
					{/if}
				{:else if col.type === 'blob'}
					{@const blob = getBlobCellMetadata(currentRow, col.column_id)}
					{#if blob}
						<button
							type="button"
							data-testid="row-panel-blob-download-{col.column_id}"
							class="flex min-h-[2.25rem] w-full items-center gap-2 rounded-xl border px-3 py-2 text-left text-sm transition {T.inputBorder} hover:border-blue-400"
							title="Download {blob.filename}"
							onclick={() => void handleBlobDownload(col, blob.filename)}
						>
							<svg
								class="h-4 w-4 shrink-0 text-blue-500"
								fill="none"
								stroke="currentColor"
								viewBox="0 0 24 24"
								aria-hidden="true"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="2"
									d="M12 3v12m0 0l-4-4m4 4l4-4M5 21h14"
								/>
							</svg>
							<span class="min-w-0 flex-1 truncate {T.link}">{blob.filename}</span>
							<span class="shrink-0 text-xs {T.muted}"
								>{blob.content_type} · {formatBlobSize(blob.size)}</span
							>
						</button>
					{:else}
						<button
							type="button"
							class="flex min-h-[2.25rem] w-full items-center rounded-xl border px-3 py-2 text-left text-sm text-gray-400 {T.inputBorder} hover:border-blue-400"
							onclick={() => chooseBlobFile(col)}>Upload file</button
						>
					{/if}
				{:else if editField === col.column_id}
					<textarea
						class="w-full resize-none rounded-xl border px-3 py-2 text-sm outline-none focus:ring-1 {T.inputBorder} {T.inputBg} {T.body} {T.inputFocusBorder} focus:ring-blue-500"
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
						class="flex min-h-[2.25rem] w-full items-start rounded-xl border px-3 py-2 text-left text-sm {T.inputBorder} hover:border-blue-400"
						onclick={() => startEdit(col)}
					>
						{#if currentRow.row_data[col.column_id] !== null && currentRow.row_data[col.column_id] !== undefined && String(currentRow.row_data[col.column_id]) !== ''}
							<span class="break-words whitespace-pre-wrap {T.body}"
								>{String(currentRow.row_data[col.column_id])}</span
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

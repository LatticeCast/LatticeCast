<script lang="ts">
	import type { Column, Row } from '$lib/types/table';
	import { TAG_COLORS, isDark } from '$lib/UI/theme.svelte';
	import {
		getChoices,
		getChoiceColor,
		getTagValues,
		formatDate,
		applyEditToRowData,
		toggleCheckboxInRowData,
		removeTagFromRowData,
		addTagToRowData
	} from './table.utils';
	import { fetchDoc, saveDoc } from '$lib/backend/tables';
	import { marked } from 'marked';

	let {
		row,
		columns,
		onClose,
		onUpdateRow,
		onRefreshRows,
		tableId,
		workspaceId,
		onOpenDocCell
	}: {
		row: Row;
		columns: Column[];
		onClose: () => void;
		onUpdateRow: (rowNumber: number, data: Record<string, unknown>) => Promise<void>;
		onRefreshRows: (tableId: string) => Promise<void>;
		tableId: string;
		workspaceId: string;
		onOpenDocCell?: (row: Row, col: Column) => void;
	} = $props();

	let editField = $state<string | null>(null);
	let editVal = $state('');
	let tagsPopup = $state<string | null>(null);
	let activeTab = $state<'fields' | 'doc'>('fields');
	let docContent = $state('');
	let docLoading = $state(false);
	let docLoaded = $state(false);
	let docEditing = $state(false);
	let docSaving = $state(false);

	// Local copy so we can update inline
	let localRow = $state<Row>(row);
	$effect(() => {
		localRow = row;
	});

	$effect(() => {
		if (activeTab === 'doc' && !docLoaded && !docLoading) {
			docLoading = true;
			fetchDoc(tableId, row.row_number)
				.then((content) => {
					docContent = content;
				})
				.catch(() => {})
				.finally(() => {
					docLoading = false;
					docLoaded = true;
				});
		}
	});

	async function handleDocBlur() {
		if (docSaving) return;
		docSaving = true;
		try {
			await saveDoc(tableId, row.row_number, docContent);
		} catch {
			// best-effort
		} finally {
			docSaving = false;
		}
	}

	const docPreview = $derived(marked(docContent) as string);

	const sortedCols = $derived([...columns].sort((a, b) => a.position - b.position));

	function startEdit(col: Column) {
		editField = col.column_id;
		const val = localRow.row_data[col.column_id];
		editVal = val === null || val === undefined ? '' : String(val);
	}

	async function commitEdit(col: Column) {
		if (editField !== col.column_id) return;
		editField = null;
		const newData = applyEditToRowData(localRow.row_data, col.column_id, editVal, col.type);
		localRow = { ...localRow, row_data: newData };
		await onUpdateRow(localRow.row_number, newData);
		await onRefreshRows(tableId);
	}

	async function toggleCheckbox(col: Column) {
		const newData = toggleCheckboxInRowData(localRow.row_data, col.column_id);
		localRow = { ...localRow, row_data: newData };
		await onUpdateRow(localRow.row_number, newData);
		await onRefreshRows(tableId);
	}

	async function removeTag(col: Column, tag: string) {
		const newData = removeTagFromRowData(localRow.row_data, col.column_id, tag);
		localRow = { ...localRow, row_data: newData };
		await onUpdateRow(localRow.row_number, newData);
		await onRefreshRows(tableId);
	}

	async function addTag(col: Column, tag: string) {
		const newData = addTagToRowData(localRow.row_data, col.column_id, tag);
		if (newData === localRow.row_data) return; // tag already present
		tagsPopup = null;
		localRow = { ...localRow, row_data: newData };
		await onUpdateRow(localRow.row_number, newData);
		await onRefreshRows(tableId);
	}
</script>

<!-- Backdrop -->
<div class="fixed inset-0 z-40 bg-black/30" onclick={onClose} role="presentation"></div>

<!-- Slide-out panel -->
<div
	class="fixed top-0 right-0 z-50 flex h-full w-full flex-col shadow-2xl {isDark.value
		? 'bg-gray-800'
		: 'bg-white'} {activeTab === 'doc' ? 'max-w-4xl' : 'max-w-md'}"
	role="dialog"
	aria-modal="true"
	aria-label="Row details"
>
	<!-- Panel header -->
	<div
		class="flex items-center justify-between border-b bg-blue-600 px-6 py-3 {isDark.value
			? 'border-gray-700'
			: 'border-gray-200'}"
	>
		<h2 class="text-lg font-semibold text-white">Row Details</h2>
		<div class="flex items-center gap-2">
			<a
				data-testid="row-panel-open-fullpage-link"
				href="/{workspaceId}/{tableId}/{row.row_number}"
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

	<!-- Tabs -->
	<div class="flex border-b {isDark.value ? 'border-gray-700' : 'border-gray-200'}">
		<button
			data-testid="row-panel-tab-fields"
			class="px-5 py-2.5 text-sm font-medium transition {activeTab === 'fields'
				? 'border-b-2 border-blue-600 text-blue-600'
				: isDark.value
					? 'text-gray-400 hover:text-gray-200'
					: 'text-gray-500 hover:text-gray-800'}"
			onclick={() => (activeTab = 'fields')}
		>
			Fields
		</button>
		<button
			data-testid="row-panel-tab-doc"
			class="px-5 py-2.5 text-sm font-medium transition {activeTab === 'doc'
				? 'border-b-2 border-blue-600 text-blue-600'
				: isDark.value
					? 'text-gray-400 hover:text-gray-200'
					: 'text-gray-500 hover:text-gray-800'}"
			onclick={() => (activeTab = 'doc')}
		>
			Doc
		</button>
	</div>

	{#if activeTab === 'doc'}
		<!-- Doc tab — split view -->
		<div class="flex flex-1 flex-col overflow-hidden">
			<div
				class="flex items-center justify-between border-b px-4 py-2 {isDark.value
					? 'border-gray-700'
					: 'border-gray-100'}"
			>
				<span class="text-xs {isDark.value ? 'text-gray-500' : 'text-gray-400'}"
					>Markdown {docSaving ? '· saving…' : ''}</span
				>
				<a
					data-testid="row-panel-doc-full-editor-link"
					href="/{workspaceId}/{tableId}/{row.row_number}/doc"
					class="text-xs text-blue-500 transition hover:underline"
				>Edit full doc ↗</a>
			</div>
			{#if docLoading || !docLoaded}
				<div
					class="flex flex-1 items-center justify-center text-sm {isDark.value
						? 'text-gray-500'
						: 'text-gray-400'}"
				>
					Loading…
				</div>
			{:else if !docContent && !docEditing}
				<!-- Empty state -->
				<div class="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-12">
					<svg
						class="h-12 w-12 {isDark.value ? 'text-gray-600' : 'text-gray-300'}"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="1.5"
							d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
						/>
					</svg>
					<p class="text-sm {isDark.value ? 'text-gray-400' : 'text-gray-500'}">
						No doc yet for this row.
					</p>
					<button
						data-testid="row-panel-doc-start-btn"
						onclick={() => (docEditing = true)}
						class="rounded-lg px-4 py-2 text-sm font-medium text-blue-600 transition hover:bg-blue-50 hover:text-blue-700 {isDark.value
							? 'hover:bg-blue-900/20'
							: ''}"
					>
						Start writing →
					</button>
				</div>
			{:else}
				<div
					class="flex flex-1 divide-x overflow-hidden {isDark.value
						? 'divide-gray-700'
						: 'divide-gray-200'}"
				>
					<!-- Editor pane -->
					<textarea
						data-testid="row-panel-doc-textarea"
						class="flex-1 resize-none border-none px-5 py-4 font-mono text-sm outline-none {isDark.value
							? 'bg-gray-800 text-gray-200'
							: 'text-gray-800'}"
						placeholder="Write markdown here…"
						bind:value={docContent}
						onblur={handleDocBlur}
					></textarea>
					<!-- Preview pane -->
					<div
						class="prose prose-sm max-w-none flex-1 overflow-y-auto px-5 py-4 text-sm {isDark.value
							? 'text-gray-200 prose-invert'
							: 'text-gray-800'}"
					>
						{@html docPreview}
					</div>
				</div>
			{/if}
		</div>
	{:else}
		<!-- Fields list -->
		<div class="flex-1 overflow-y-auto px-6 py-4">
			{#each sortedCols as col (col.column_id)}
				<div class="mb-5">
					<label
						class="mb-1 block text-xs font-semibold tracking-wide uppercase {isDark.value
							? 'text-gray-500'
							: 'text-gray-400'}"
					>
						{col.name}
						<span class="ml-1 font-normal text-gray-300 normal-case">({col.type})</span>
					</label>

					{#if col.type === 'checkbox'}
						<button
							data-testid="row-panel-field-{col.column_id}-toggle"
							class="relative inline-flex h-6 w-10 items-center rounded-full transition {localRow
								.row_data[col.column_id]
								? 'bg-blue-500'
								: 'bg-gray-200'}"
							onclick={() => toggleCheckbox(col)}
							role="switch"
							aria-checked={!!localRow.row_data[col.column_id]}
						>
							<span
								class="inline-block h-4 w-4 transform rounded-full bg-white shadow transition {localRow
									.row_data[col.column_id]
									? 'translate-x-5'
									: 'translate-x-1'}"
							></span>
						</button>
					{:else if col.type === 'select'}
						{@const choices = getChoices(col)}
						{#if editField === col.column_id}
							<select
								class="w-full rounded-xl border px-3 py-2 text-sm outline-none focus:ring-1 {isDark.value
									? 'border-gray-600 bg-gray-700 text-gray-200 focus:border-blue-400 focus:ring-blue-400'
									: 'border-gray-200 text-gray-800 focus:border-blue-500 focus:ring-blue-500'}"
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
							{@const selVal = (localRow.row_data[col.column_id] as string) ?? ''}
							<button
								data-testid="row-panel-field-{col.column_id}-select-btn"
								class="flex min-h-[2.25rem] w-full items-center rounded-xl border px-3 py-2 text-left text-sm {isDark.value
									? 'border-gray-600 hover:border-blue-500'
									: 'border-gray-200 hover:border-blue-300'}"
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
						{@const tagVals = getTagValues(localRow, col.column_id)}
						{@const choices = getChoices(col)}
						{@const available = choices.filter((c) => !tagVals.includes(c.value))}
						<div
							class="flex min-h-[2.25rem] flex-wrap items-center gap-1 rounded-xl border px-3 py-2 {isDark.value
								? 'border-gray-600'
								: 'border-gray-200'}"
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
											tagsPopup = tagsPopup === col.column_id ? null : col.column_id;
										}}>+</button
									>
									{#if tagsPopup === col.column_id}
										<div
											class="absolute top-full left-0 z-20 mt-1 min-w-[120px] rounded-xl border py-1 shadow-xl {isDark.value
												? 'border-gray-700 bg-gray-800'
												: 'border-gray-100 bg-white'}"
										>
											{#each available as choice (choice.value)}
												{@const color = TAG_COLORS[choices.indexOf(choice) % TAG_COLORS.length]}
												<button
													class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs {isDark.value
														? 'hover:bg-gray-700'
														: 'hover:bg-gray-50'}"
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
						{#if editField === col.column_id}
							<input
								type="url"
								class="w-full rounded-xl border px-3 py-2 text-sm outline-none focus:ring-1 {isDark.value
									? 'border-gray-600 bg-gray-700 text-gray-200 focus:border-blue-400 focus:ring-blue-400'
									: 'border-gray-200 text-gray-800 focus:border-blue-500 focus:ring-blue-500'}"
								bind:value={editVal}
								onblur={() => commitEdit(col)}
								onkeydown={(e) => {
									if (e.key === 'Enter') commitEdit(col);
									if (e.key === 'Escape') editField = null;
								}}
								autofocus
							/>
						{:else}
							{@const urlVal = (localRow.row_data[col.column_id] as string) ?? ''}
							<button
								class="flex min-h-[2.25rem] w-full items-center rounded-xl border px-3 py-2 text-left text-sm {isDark.value
									? 'border-gray-600 hover:border-blue-500'
									: 'border-gray-200 hover:border-blue-300'}"
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
						{#if editField === col.column_id}
							<input
								type="date"
								class="w-full rounded-xl border px-3 py-2 text-sm outline-none focus:ring-1 {isDark.value
									? 'border-gray-600 bg-gray-700 text-gray-200 focus:border-blue-400 focus:ring-blue-400'
									: 'border-gray-200 text-gray-800 focus:border-blue-500 focus:ring-blue-500'}"
								bind:value={editVal}
								onblur={() => commitEdit(col)}
								onkeydown={(e) => {
									if (e.key === 'Enter') commitEdit(col);
									if (e.key === 'Escape') editField = null;
								}}
								autofocus
							/>
						{:else}
							{@const dateVal = localRow.row_data[col.column_id]
								? formatDate(String(localRow.row_data[col.column_id]))
								: ''}
							<button
								class="flex min-h-[2.25rem] w-full items-center rounded-xl border px-3 py-2 text-left font-mono text-sm {isDark.value
									? 'border-gray-600 hover:border-blue-500'
									: 'border-gray-200 hover:border-blue-300'}"
								onclick={() => startEdit(col)}
							>
								{#if dateVal}{dateVal}{:else}<span class="font-sans text-gray-400">—</span>{/if}
							</button>
						{/if}
					{:else if col.type === 'number'}
						{#if editField === col.column_id}
							<input
								type="number"
								class="w-full rounded-xl border px-3 py-2 text-sm outline-none focus:ring-1 {isDark.value
									? 'border-gray-600 bg-gray-700 text-gray-200 focus:border-blue-400 focus:ring-blue-400'
									: 'border-gray-200 text-gray-800 focus:border-blue-500 focus:ring-blue-500'}"
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
								class="flex min-h-[2.25rem] w-full items-center rounded-xl border px-3 py-2 text-left text-sm {isDark.value
									? 'border-gray-600 hover:border-blue-500'
									: 'border-gray-200 hover:border-blue-300'}"
								onclick={() => startEdit(col)}
							>
								{#if localRow.row_data[col.column_id] !== null && localRow.row_data[col.column_id] !== undefined}
									<span class={isDark.value ? 'text-gray-200' : 'text-gray-800'}
										>{String(localRow.row_data[col.column_id])}</span
									>
								{:else}
									<span class="text-gray-400">—</span>
								{/if}
							</button>
						{/if}
					{:else if col.type === 'doc'}
						<button
							class="flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm transition {isDark.value
								? 'border-gray-600 text-blue-400 hover:border-blue-500 hover:bg-blue-900/20'
								: 'border-gray-200 text-blue-600 hover:border-blue-300 hover:bg-blue-50'}"
							onclick={() => onOpenDocCell?.(localRow, col)}
						>
							<svg class="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
								<path
									fill-rule="evenodd"
									d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
									clip-rule="evenodd"
								/>
							</svg>
							Open doc
						</button>
					{:else if editField === col.column_id}
						<textarea
							class="w-full resize-none rounded-xl border px-3 py-2 text-sm outline-none focus:ring-1 {isDark.value
								? 'border-gray-600 bg-gray-700 text-gray-200 focus:border-blue-400 focus:ring-blue-400'
								: 'border-gray-200 text-gray-800 focus:border-blue-500 focus:ring-blue-500'}"
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
							class="flex min-h-[2.25rem] w-full items-start rounded-xl border px-3 py-2 text-left text-sm {isDark.value
								? 'border-gray-600 hover:border-blue-500'
								: 'border-gray-200 hover:border-blue-300'}"
							onclick={() => startEdit(col)}
						>
							{#if localRow.row_data[col.column_id] !== null && localRow.row_data[col.column_id] !== undefined && String(localRow.row_data[col.column_id]) !== ''}
								<span
									class="break-words whitespace-pre-wrap {isDark.value
										? 'text-gray-200'
										: 'text-gray-800'}">{String(localRow.row_data[col.column_id])}</span
								>
							{:else}
								<span class="text-gray-400">—</span>
							{/if}
						</button>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

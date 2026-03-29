<script lang="ts">
	import type { Column, Row } from '$lib/types/table';
	import { TAG_COLORS } from '$lib/UI/theme.svelte';
	import { getChoices, getChoiceColor, getTagValues, formatDate } from './table.utils';
	import { fetchDoc, saveDoc } from '$lib/backend/tables';

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
	let activeTab = $state<'fields' | 'doc'>('fields');
	let docContent = $state('');
	let docLoading = $state(false);
	let docSaving = $state(false);
	let showPreview = $state(false);

	// Local copy so we can update inline
	let localRow = $state<Row>(row);
	$effect(() => {
		localRow = row;
	});

	$effect(() => {
		if (activeTab === 'doc' && !docContent && !docLoading) {
			docLoading = true;
			fetchDoc(tableId, row.row_id)
				.then((content) => { docContent = content; })
				.catch(() => {})
				.finally(() => { docLoading = false; });
		}
	});

	async function handleDocBlur() {
		if (docSaving) return;
		docSaving = true;
		try {
			await saveDoc(tableId, row.row_id, docContent);
		} catch {
			// best-effort
		} finally {
			docSaving = false;
		}
	}

	function renderMarkdown(md: string): string {
		// Simple markdown rendering: headings, bold, italic, lists, code
		return md
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-3 mb-1">$1</h3>')
			.replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold mt-4 mb-1">$1</h2>')
			.replace(/^# (.+)$/gm, '<h1 class="text-xl font-bold mt-4 mb-2">$1</h1>')
			.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
			.replace(/\*(.+?)\*/g, '<em>$1</em>')
			.replace(/`(.+?)`/g, '<code class="bg-gray-100 px-1 rounded text-xs font-mono">$1</code>')
			.replace(/^- \[ \] (.+)$/gm, '<div class="flex items-start gap-1.5 my-0.5"><input type="checkbox" disabled class="mt-0.5"/> <span>$1</span></div>')
			.replace(/^- \[x\] (.+)$/gm, '<div class="flex items-start gap-1.5 my-0.5"><input type="checkbox" checked disabled class="mt-0.5"/> <span>$1</span></div>')
			.replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
			.replace(/^(\d+)\. (.+)$/gm, '<li class="ml-4 list-decimal">$2</li>')
			.replace(/\n\n/g, '</p><p class="mb-2">')
			.replace(/\n/g, '<br>');
	}

	const sortedCols = $derived([...columns].sort((a, b) => a.position - b.position));

	function startEdit(col: Column) {
		editField = col.column_id;
		const val = localRow.row_data[col.column_id];
		editVal = val === null || val === undefined ? '' : String(val);
	}

	async function commitEdit(col: Column) {
		if (editField !== col.column_id) return;
		editField = null;
		let parsed: unknown = editVal;
		if (col.type === 'number') parsed = editVal === '' ? null : Number(editVal);
		else if (col.type === 'checkbox') parsed = editVal === 'true';
		else if (editVal === '') parsed = null;
		const newData = { ...localRow.row_data, [col.column_id]: parsed };
		localRow = { ...localRow, row_data: newData };
		await onUpdateRow(localRow.row_id, newData);
		await onRefreshRows(tableId);
	}

	async function toggleCheckbox(col: Column) {
		const current = !!localRow.row_data[col.column_id];
		const newData = { ...localRow.row_data, [col.column_id]: !current };
		localRow = { ...localRow, row_data: newData };
		await onUpdateRow(localRow.row_id, newData);
		await onRefreshRows(tableId);
	}

	async function removeTag(col: Column, tag: string) {
		const current = getTagValues(localRow, col.column_id);
		const newData = { ...localRow.row_data, [col.column_id]: current.filter((t) => t !== tag) };
		localRow = { ...localRow, row_data: newData };
		await onUpdateRow(localRow.row_id, newData);
		await onRefreshRows(tableId);
	}

	async function addTag(col: Column, tag: string) {
		const current = getTagValues(localRow, col.column_id);
		if (current.includes(tag)) return;
		const newData = { ...localRow.row_data, [col.column_id]: [...current, tag] };
		tagsPopup = null;
		localRow = { ...localRow, row_data: newData };
		await onUpdateRow(localRow.row_id, newData);
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

	<!-- Tabs -->
	<div class="flex border-b border-gray-200">
		<button
			class="px-5 py-2.5 text-sm font-medium transition {activeTab === 'fields' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500 hover:text-gray-800'}"
			onclick={() => (activeTab = 'fields')}
		>
			Fields
		</button>
		<button
			class="px-5 py-2.5 text-sm font-medium transition {activeTab === 'doc' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500 hover:text-gray-800'}"
			onclick={() => (activeTab = 'doc')}
		>
			Doc
		</button>
	</div>

	{#if activeTab === 'doc'}
		<!-- Doc tab -->
		<div class="flex flex-1 flex-col overflow-hidden">
			<div class="flex items-center justify-between border-b border-gray-100 px-4 py-2">
				<span class="text-xs text-gray-400">Markdown {docSaving ? '· saving…' : ''}</span>
				<button
					class="rounded px-2 py-1 text-xs font-medium transition {showPreview ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:text-gray-800'}"
					onclick={() => (showPreview = !showPreview)}
				>
					{showPreview ? 'Edit' : 'Preview'}
				</button>
			</div>
			{#if docLoading}
				<div class="flex flex-1 items-center justify-center text-sm text-gray-400">Loading…</div>
			{:else if showPreview}
				<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
				<div class="prose prose-sm flex-1 overflow-y-auto px-5 py-4 text-sm text-gray-800">
					{@html renderMarkdown(docContent)}
				</div>
			{:else}
				<textarea
					class="flex-1 resize-none border-none px-5 py-4 font-mono text-sm text-gray-800 outline-none"
					placeholder="Write markdown here…"
					bind:value={docContent}
					onblur={handleDocBlur}
				></textarea>
			{/if}
		</div>
	{:else}
	<!-- Fields list -->
	<div class="flex-1 overflow-y-auto px-6 py-4">
		{#each sortedCols as col (col.column_id)}
			<div class="mb-5">
				<label class="mb-1 block text-xs font-semibold tracking-wide text-gray-400 uppercase">
					{col.name}
					<span class="ml-1 font-normal text-gray-300 normal-case">({col.type})</span>
				</label>

				{#if col.type === 'checkbox'}
					<button
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
						{@const selVal = (localRow.row_data[col.column_id] as string) ?? ''}
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
					{@const tagVals = getTagValues(localRow, col.column_id)}
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
										tagsPopup = tagsPopup === col.column_id ? null : col.column_id;
									}}>+</button
								>
								{#if tagsPopup === col.column_id}
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
					{#if editField === col.column_id}
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
						{@const urlVal = (localRow.row_data[col.column_id] as string) ?? ''}
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
					{#if editField === col.column_id}
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
						{@const dateVal = localRow.row_data[col.column_id]
							? formatDate(String(localRow.row_data[col.column_id]))
							: ''}
						<button
							class="flex min-h-[2.25rem] w-full items-center rounded-xl border border-gray-200 px-3 py-2 text-left font-mono text-sm hover:border-blue-300"
							onclick={() => startEdit(col)}
						>
							{#if dateVal}{dateVal}{:else}<span class="font-sans text-gray-400">—</span>{/if}
						</button>
					{/if}
				{:else if col.type === 'number'}
					{#if editField === col.column_id}
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
							{#if localRow.row_data[col.column_id] !== null && localRow.row_data[col.column_id] !== undefined}
								<span class="text-gray-800">{String(localRow.row_data[col.column_id])}</span>
							{:else}
								<span class="text-gray-400">—</span>
							{/if}
						</button>
					{/if}
				{:else if editField === col.column_id}
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
						{#if localRow.row_data[col.column_id] !== null && localRow.row_data[col.column_id] !== undefined && String(localRow.row_data[col.column_id]) !== ''}
							<span class="break-words whitespace-pre-wrap text-gray-800"
								>{String(localRow.row_data[col.column_id])}</span
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

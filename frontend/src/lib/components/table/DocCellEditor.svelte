<script lang="ts">
	import type { Column, Row } from '$lib/types/table';
	import { isDark } from '$lib/UI/theme.svelte';
	import { fetchColDoc, saveColDoc } from '$lib/backend/tables';
	import { marked } from 'marked';

	let {
		row,
		column,
		tableId,
		onClose
	}: {
		row: Row;
		column: Column;
		tableId: string;
		onClose: () => void;
	} = $props();

	let docContent = $state('');
	let docLoading = $state(true);
	let docLoaded = $state(false);
	let docSaving = $state(false);
	let docEditing = $state(false);

	$effect(() => {
		docLoading = true;
		fetchColDoc(tableId, row.row_number, column.column_id)
			.then((content) => {
				docContent = content;
				if (content) docEditing = true;
			})
			.catch(() => {})
			.finally(() => {
				docLoading = false;
				docLoaded = true;
			});
	});

	async function handleDocBlur() {
		if (docSaving) return;
		docSaving = true;
		try {
			await saveColDoc(tableId, row.row_number, column.column_id, docContent);
		} catch {
			// best-effort
		} finally {
			docSaving = false;
		}
	}

	async function handleClose() {
		await handleDocBlur();
		onClose();
	}

	const docPreview = $derived(marked(docContent) as string);
</script>

<!-- Backdrop -->
<div class="fixed inset-0 z-40 bg-black/30" onclick={handleClose} role="presentation"></div>

<!-- Editor panel -->
<div
	class="fixed top-1/2 left-1/2 z-50 flex h-[70vh] w-[80vw] max-w-5xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl shadow-2xl {isDark.value
		? 'bg-gray-800'
		: 'bg-white'}"
	role="dialog"
	aria-modal="true"
	aria-label="Doc editor"
>
	<!-- Header -->
	<div
		class="flex items-center justify-between rounded-t-xl border-b bg-blue-600 px-5 py-3 {isDark.value
			? 'border-gray-700'
			: 'border-gray-200'}"
	>
		<div class="flex items-center gap-2">
			<svg class="h-4 w-4 text-white/80" fill="currentColor" viewBox="0 0 20 20">
				<path
					fill-rule="evenodd"
					d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
					clip-rule="evenodd"
				/>
			</svg>
			<span class="text-sm font-semibold text-white">{column.name}</span>
			<span class="text-xs text-white/60">· Row {row.row_number}</span>
		</div>
		<div class="flex items-center gap-2">
			<span class="text-xs {isDark.value ? 'text-white/40' : 'text-white/60'}">
				{docSaving ? 'saving…' : 'Markdown'}
			</span>
			<button
				onclick={handleClose}
				class="rounded-lg p-1.5 text-white/70 transition hover:bg-white/20 hover:text-white"
				aria-label="Close"
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

	<!-- Body -->
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
			<p class="text-sm {isDark.value ? 'text-gray-400' : 'text-gray-500'}">No doc yet.</p>
			<button
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
			class="flex flex-1 divide-x overflow-hidden rounded-b-xl {isDark.value
				? 'divide-gray-700'
				: 'divide-gray-200'}"
		>
			<!-- Editor pane -->
			<textarea
				class="flex-1 resize-none border-none px-5 py-4 font-mono text-sm outline-none {isDark.value
					? 'bg-gray-800 text-gray-200'
					: 'text-gray-800'}"
				placeholder="Write markdown here…"
				bind:value={docContent}
				onblur={handleDocBlur}
				autofocus
			></textarea>
			<!-- Preview pane -->
			<div
				class="prose prose-sm max-w-none flex-1 overflow-y-auto px-5 py-4 text-sm {isDark.value
					? 'prose-invert text-gray-200'
					: 'text-gray-800'}"
			>
				{@html docPreview}
			</div>
		</div>
	{/if}
</div>

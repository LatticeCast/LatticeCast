<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { authStore } from '$lib/stores/auth.store';
	import { get } from 'svelte/store';
	import { fetchDoc, saveDoc, fetchTable, fetchRows } from '$lib/backend/tables';
	import { T } from '$lib/UI/theme.svelte';
	import { BRAND } from '$lib/UI/brand';
	import { marked } from 'marked';
	import type { Table, Row } from '$lib/types/table';

	const workspaceId = $derived($page.params.workspace_id ?? '');
	const tableId = $derived($page.params.table_id ?? '');
	const rowNumber = $derived(parseInt($page.params.row_id ?? '0', 10));

	let table = $state<Table | null>(null);
	let row = $state<Row | null>(null);
	let docContent = $state('');
	let loading = $state(true);
	let docSaving = $state(false);
	let unsaved = $state(false);
	let error = $state<string | null>(null);

	const docPreview = $derived(marked(docContent) as string);

	const rowTitle = $derived(
		(() => {
			if (!row || !table) return String(rowNumber);
			const keyCol = table.columns.find((c) => c.name === 'Key');
			const titleCol = table.columns.find((c) => c.name === 'Title');
			const key = keyCol ? ((row.row_data[keyCol.column_id] as string) ?? '') : '';
			const title = titleCol ? ((row.row_data[titleCol.column_id] as string) ?? '') : '';
			if (key && title) return `${key}: ${title}`;
			return title || key || String(rowNumber);
		})()
	);

	onMount(async () => {
		const auth = get(authStore);
		if (!auth?.accessToken) {
			goto('/login');
			return;
		}
		try {
			const [t, rows] = await Promise.all([
				fetchTable(tableId, $page.params.workspace_id),
				fetchRows(tableId, 0, 200)
			]);
			table = t;
			row = rows.find((r) => r.row_id === rowNumber) ?? null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load';
			loading = false;
			return;
		}
		try {
			docContent = await fetchDoc(tableId, rowNumber);
		} catch {
			// doc doesn't exist yet — start empty
		}
		loading = false;
	});

	function handleInput() {
		unsaved = true;
	}

	async function handleSave() {
		if (docSaving) return;
		docSaving = true;
		try {
			await saveDoc(tableId, rowNumber, docContent);
			unsaved = false;
		} catch {
			// best-effort
		} finally {
			docSaving = false;
		}
	}

	async function handleBlur() {
		if (unsaved) await handleSave();
	}
</script>

<svelte:head>
	<title>{rowTitle} · Doc — {BRAND}</title>
</svelte:head>

<div class="flex h-screen flex-col {T.editorBg} {T.heading}">
	<!-- Top bar -->
	<div
		class="flex shrink-0 items-center justify-between border-b px-5 py-3 {T.border} {T.tableHeaderBg}"
	>
		<!-- Breadcrumb -->
		<nav
			class="flex items-center gap-1 text-sm"
			aria-label="Breadcrumb"
			data-testid="doc-breadcrumb"
		>
			<a
				href="/{workspaceId}"
				class="text-blue-500 hover:underline"
				data-testid="doc-breadcrumb-workspace">{workspaceId}</a
			>
			<span class="text-gray-400">/</span>
			<a
				href="/{workspaceId}/{tableId}"
				class="text-blue-500 hover:underline"
				data-testid="doc-breadcrumb-table">{tableId}</a
			>
			<span class="text-gray-400">/</span>
			<a
				href="/{workspaceId}/{tableId}/{rowNumber}"
				class="text-blue-500 hover:underline"
				data-testid="doc-breadcrumb-row">{rowTitle}</a
			>
			<span class="text-gray-400">/</span>
			<span class={T.secondary}>Doc</span>
		</nav>

		<!-- Actions -->
		<div class="flex items-center gap-3">
			{#if unsaved}
				<span
					class="text-xs text-yellow-600 dark:text-yellow-400"
					data-testid="doc-unsaved-indicator"
				>
					Unsaved changes
				</span>
			{/if}
			{#if docSaving}
				<span class="text-xs text-gray-400" data-testid="doc-saving-indicator">Saving…</span>
			{/if}
			<button
				data-testid="doc-save-btn"
				onclick={handleSave}
				disabled={docSaving || !unsaved}
				class="rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-blue-700 disabled:opacity-40"
			>
				Save
			</button>
		</div>
	</div>

	<!-- Body -->
	{#if loading}
		<div
			class="flex flex-1 items-center justify-center text-sm text-gray-400"
			data-testid="doc-loading"
		>
			Loading…
		</div>
	{:else if error}
		<div
			class="flex flex-1 items-center justify-center text-sm text-red-500"
			data-testid="doc-error"
		>
			{error}
		</div>
	{:else}
		<!-- Split pane -->
		<div class="flex flex-1 divide-x overflow-hidden {T.divide}" data-testid="doc-split-pane">
			<!-- Editor pane -->
			<textarea
				data-testid="doc-editor-textarea"
				class="flex-1 resize-none border-none px-6 py-5 font-mono text-sm outline-none {T.editorBg} {T.body}"
				placeholder="Write markdown here…"
				bind:value={docContent}
				oninput={handleInput}
				onblur={handleBlur}
			></textarea>

			<!-- Preview pane -->
			<div
				data-testid="doc-preview-pane"
				class="prose prose-sm max-w-none flex-1 overflow-y-auto px-6 py-5 text-sm {T.editorBg} {T.body} {T.proseDark}"
			>
				{#if docContent}
					<!-- eslint-disable-next-line svelte/no-at-html-tags -->
					{@html docPreview}
				{:else}
					<p class="text-gray-400">Preview will appear here…</p>
				{/if}
			</div>
		</div>
	{/if}
</div>

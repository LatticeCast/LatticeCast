<!-- routes/[workspace_id]/[table_id]/[row_number]/+page.svelte -->

<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { authStore } from '$lib/stores/auth.store';
	import { get } from 'svelte/store';
	import { fetchTable, fetchRows, fetchDoc, saveDoc } from '$lib/backend/tables';
	import { fetchWorkspaces } from '$lib/backend/workspaces';
	import {
		getChoices,
		getChoiceColor,
		getTagValues,
		formatDate
	} from '$lib/components/table/table.utils';
	import type { Column, Row, Table, Workspace } from '$lib/types/table';
	import { marked } from 'marked';

	const tableId = $derived($page.params.table_id ?? '');
	const rowNumberParam = $derived(parseInt($page.params.row_number ?? '0', 10));
	const workspaceId = $derived($page.params.workspace_id ?? '');

	let table = $state<Table | null>(null);
	let workspace = $state<Workspace | null>(null);
	let row = $state<Row | null>(null);
	let docContent = $state('');
	let loading = $state(true);
	let docLoading = $state(false);
	let docSaving = $state(false);
	let editingDoc = $state(false);
	let error = $state<string | null>(null);

	const userDisplay = $derived(
		$authStore?.userInfo?.name ?? $authStore?.userInfo?.email ?? $authStore?.accessToken ?? 'Me'
	);

	const sortedCols = $derived(
		table ? [...table.columns].sort((a, b) => a.position - b.position) : []
	);

	const badgeCols = $derived(
		sortedCols.filter((c) => ['select', 'tags', 'text', 'number', 'date', 'url'].includes(c.type))
	);

	const docPreview = $derived(marked(docContent) as string);

	const ticketKey = $derived(
		(() => {
			if (!row || !table) return '';
			const keyCol = table.columns.find((c) => c.name === 'Key');
			return keyCol ? ((row.row_data[keyCol.column_id] as string) ?? '') : '';
		})()
	);

	onMount(async () => {
		const auth = get(authStore);
		if (!auth?.accessToken) {
			goto('/login');
			return;
		}
		try {
			const [t, rows, wsList] = await Promise.all([
				fetchTable(tableId),
				fetchRows(tableId, 0, 200),
				fetchWorkspaces()
			]);
			table = t;
			workspace = wsList.find((w) => w.workspace_id === t.workspace_id) ?? null;
			row = rows.find((r) => r.row_number === rowNumberParam) ?? null;
			if (!row) {
				error = 'Row not found';
				return;
			}
			// Fetch doc
			docLoading = true;
			docContent = await fetchDoc(tableId, rowNumberParam);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load';
		} finally {
			loading = false;
			docLoading = false;
		}
	});

	async function handleDocBlur() {
		if (docSaving) return;
		docSaving = true;
		try {
			await saveDoc(tableId, rowNumberParam, docContent);
		} catch {
			// best-effort
		} finally {
			docSaving = false;
		}
	}

	function getRowTitle(): string {
		if (!row || !table) return String(rowNumberParam);
		const titleCol = table.columns.find((c) => c.name === 'Title');
		const keyCol = table.columns.find((c) => c.name === 'Key');
		const key = keyCol ? ((row.row_data[keyCol.column_id] as string) ?? '') : '';
		const title = titleCol ? ((row.row_data[titleCol.column_id] as string) ?? '') : '';
		if (key && title) return `${key}: ${title}`;
		return title || key || String(rowNumberParam);
	}
</script>

<svelte:head>
	<title>{getRowTitle()} — LatticeCast</title>
</svelte:head>

<div class="min-h-screen bg-gray-50">
	<!-- Header bar -->
	<div class="sticky top-0 z-10 border-b border-gray-200 bg-white px-6 py-3 shadow-sm">
		<nav class="flex flex-wrap items-center gap-1 text-sm text-gray-500" aria-label="Breadcrumb">
			<a
				href="/tables"
				class="max-w-[150px] truncate transition hover:text-blue-600"
				title={userDisplay}>{userDisplay}</a
			>
			<span class="text-gray-300 select-none">/</span>
			<a
				href="/tables"
				class="max-w-[150px] truncate transition hover:text-blue-600"
				title={workspace?.workspace_name ?? workspaceId}>{workspace?.workspace_name ?? workspaceId}</a
			>
			<span class="text-gray-300 select-none">/</span>
			<a
				href="/{workspaceId}/{tableId}"
				class="max-w-[150px] truncate transition hover:text-blue-600"
				title={table?.name ?? tableId}>{table?.name ?? tableId}</a
			>
			<span class="text-gray-300 select-none">/</span>
			<span class="max-w-[200px] truncate font-semibold text-gray-900" title={getRowTitle()}>
				{ticketKey || getRowTitle()}
			</span>
		</nav>
	</div>

	{#if loading}
		<div class="flex h-64 items-center justify-center text-sm text-gray-400">Loading…</div>
	{:else if error}
		<div class="flex h-64 items-center justify-center text-sm text-red-500">{error}</div>
	{:else if row && table}
		<div class="mx-auto max-w-4xl px-6 py-6">
			<!-- Badge fields at top -->
			<div class="mb-6 flex flex-wrap gap-2">
				{#each badgeCols as col (col.column_id)}
					{@const val = row.row_data[col.column_id]}
					{#if val !== null && val !== undefined && String(val) !== '' && !(Array.isArray(val) && val.length === 0)}
						{#if col.type === 'select'}
							{@const strVal = val as string}
							{@const color = getChoiceColor(col, strVal)}
							<span
								class="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
							>
								<span class="text-xs font-normal text-gray-400">{col.name}:</span>
								{strVal}
							</span>
						{:else if col.type === 'tags'}
							{@const tags = getTagValues(row, col.column_id)}
							{#each tags as tag (tag)}
								{@const color = getChoiceColor(col, tag)}
								<span
									class="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
								>
									{tag}
								</span>
							{/each}
						{:else if col.type === 'date'}
							<span
								class="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2.5 py-0.5 text-xs text-gray-600"
							>
								<span class="font-normal text-gray-400">{col.name}:</span>
								{formatDate(String(val))}
							</span>
						{:else if col.type === 'url'}
							<!-- skip URL badges — shown in doc or fields section -->
						{:else}
							<span
								class="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2.5 py-0.5 text-xs text-gray-700"
							>
								<span class="font-normal text-gray-400">{col.name}:</span>
								{String(val)}
							</span>
						{/if}
					{/if}
				{/each}
			</div>

			<!-- Doc section -->
			<div class="rounded-xl border border-gray-200 bg-white shadow-sm">
				<div class="flex items-center justify-between border-b border-gray-100 px-5 py-3">
					<span class="text-sm font-medium text-gray-700">
						Doc
						{#if docSaving}<span class="ml-2 text-xs text-gray-400">saving…</span>{/if}
					</span>
					<button
						onclick={() => (editingDoc = !editingDoc)}
						class="rounded-lg border border-gray-200 px-3 py-1 text-xs font-medium text-gray-600 transition hover:bg-gray-50 hover:text-gray-900"
					>
						{editingDoc ? 'Preview' : 'Edit'}
					</button>
				</div>

				{#if docLoading}
					<div class="flex h-40 items-center justify-center text-sm text-gray-400">Loading…</div>
				{:else if editingDoc}
					<textarea
						class="min-h-[400px] w-full resize-none border-none px-5 py-4 font-mono text-sm text-gray-800 outline-none"
						placeholder="Write markdown here…"
						bind:value={docContent}
						onblur={handleDocBlur}
					></textarea>
				{:else if docContent}
					<div class="prose prose-sm max-w-none px-5 py-4 text-gray-800">
						{@html docPreview}
					</div>
				{:else}
					<div class="px-5 py-8 text-center text-sm text-gray-400">
						No doc yet.
						<button onclick={() => (editingDoc = true)} class="ml-1 text-blue-500 hover:underline"
							>Start writing</button
						>
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>

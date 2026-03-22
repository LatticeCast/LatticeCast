<!-- routes/tables/[id]/+page.svelte -->

<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { authStore } from '$lib/stores/auth.store';
	import {
		currentTable,
		columns,
		rows,
		loading,
		error,
		loadTable,
		refreshRows,
		refreshColumns
	} from '$lib/stores/tables.store';
	import {
		fetchTables,
		createRow,
		createColumn,
		deleteColumn,
		updateColumn,
		updateRow,
		deleteRow
	} from '$lib/backend/tables';
	import type { Column, ColumnChoice } from '$lib/types/table';
	import { TAG_COLORS } from '$lib/UI/theme.svelte';

	const COLUMN_TYPES = [
		'text',
		'string',
		'number',
		'date',
		'select',
		'tags',
		'checkbox',
		'url'
	] as const;

	let addingRow = $state(false);
	let deletingRowId = $state<string | null>(null);

	// Add-column modal
	let showAddColumn = $state(false);
	let newColName = $state('');
	let newColType = $state<string>('text');
	let addingColumn = $state(false);

	// Inline rename
	let renamingColId = $state<string | null>(null);
	let renameValue = $state('');

	// Inline cell editing
	let editingCell = $state<{ rowId: string; colId: string } | null>(null);
	let editValue = $state<string>('');

	// Tags popup
	let tagsPopupCell = $state<{ rowId: string; colId: string } | null>(null);

	// Column resize
	let resizingColId = $state<string | null>(null);
	let resizeStartX = $state(0);
	let resizeStartWidth = $state(0);
	let localWidths = $state<Record<string, number>>({});

	function getColWidth(col: Column): number {
		return localWidths[col.id] ?? col.options?.width ?? 150;
	}

	function handleResizeStart(e: MouseEvent, col: Column) {
		e.preventDefault();
		e.stopPropagation();
		resizingColId = col.id;
		resizeStartX = e.clientX;
		resizeStartWidth = getColWidth(col);
	}

	onMount(() => {
		// Async table loading
		(async () => {
			if (!$authStore?.role) {
				goto('/login');
				return;
			}
			const tableId = $page.params.id;
			try {
				const all = await fetchTables();
				const table = all.find((t) => t.id === tableId);
				if (!table) {
					goto('/tables');
					return;
				}
				await loadTable(table);
			} catch (e) {
				error.set(e instanceof Error ? e.message : 'Failed to load table');
			}
		})();

		// Resize event handlers
		function onResizeMove(e: MouseEvent) {
			if (!resizingColId) return;
			const delta = e.clientX - resizeStartX;
			localWidths = { ...localWidths, [resizingColId]: Math.max(60, resizeStartWidth + delta) };
		}

		async function onResizeUp() {
			if (!resizingColId) return;
			const colId = resizingColId;
			const newWidth = localWidths[colId] ?? resizeStartWidth;
			resizingColId = null;
			const col = get(columns).find((c) => c.id === colId);
			if (!col) return;
			try {
				await updateColumn(colId, { options: { ...col.options, width: newWidth } });
				await refreshColumns(get(page).params.id);
			} catch (err) {
				error.set(err instanceof Error ? err.message : 'Failed to resize column');
			}
		}

		window.addEventListener('mousemove', onResizeMove);
		window.addEventListener('mouseup', onResizeUp);

		return () => {
			window.removeEventListener('mousemove', onResizeMove);
			window.removeEventListener('mouseup', onResizeUp);
		};
	});

	async function handleAddRow() {
		const tableId = $page.params.id;
		addingRow = true;
		error.set(null);
		try {
			await createRow(tableId, { data: {} });
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to add row');
		} finally {
			addingRow = false;
		}
	}

	async function handleDeleteRow(rowId: string) {
		const tableId = $page.params.id;
		deletingRowId = rowId;
		error.set(null);
		try {
			await deleteRow(rowId);
			await refreshRows(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to delete row');
		} finally {
			deletingRowId = null;
		}
	}

	async function handleAddColumn() {
		if (!newColName.trim()) return;
		const tableId = $page.params.id;
		addingColumn = true;
		error.set(null);
		try {
			await createColumn(tableId, { name: newColName.trim(), type: newColType });
			await refreshColumns(tableId);
			showAddColumn = false;
			newColName = '';
			newColType = 'text';
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to add column');
		} finally {
			addingColumn = false;
		}
	}

	async function handleDeleteColumn(colId: string) {
		const tableId = $page.params.id;
		error.set(null);
		try {
			await deleteColumn(colId);
			await refreshColumns(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to delete column');
		}
	}

	async function handleMoveColumn(col: Column, direction: 'up' | 'down') {
		const tableId = $page.params.id;
		const sorted = [...$columns].sort((a, b) => a.position - b.position);
		const idx = sorted.findIndex((c) => c.id === col.id);
		const swapIdx = direction === 'up' ? idx - 1 : idx + 1;
		if (swapIdx < 0 || swapIdx >= sorted.length) return;
		const swapCol = sorted[swapIdx];
		error.set(null);
		try {
			await Promise.all([
				updateColumn(col.id, { position: swapCol.position }),
				updateColumn(swapCol.id, { position: col.position })
			]);
			await refreshColumns(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to reorder column');
		}
	}

	function startRename(colId: string, currentName: string) {
		renamingColId = colId;
		renameValue = currentName;
	}

	async function commitRename(colId: string) {
		if (!renameValue.trim()) {
			renamingColId = null;
			return;
		}
		const tableId = $page.params.id;
		error.set(null);
		try {
			await updateColumn(colId, { name: renameValue.trim() });
			await refreshColumns(tableId);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to rename column');
		} finally {
			renamingColId = null;
		}
	}

	function getCellValue(row: { data: Record<string, unknown> }, colId: string): string {
		const val = row.data[colId];
		if (val === null || val === undefined) return '';
		if (typeof val === 'boolean') return val ? '✓' : '';
		return String(val);
	}

	function startEdit(rowId: string, col: Column, currentVal: unknown) {
		editingCell = { rowId, colId: col.id };
		if (col.type === 'checkbox') {
			editValue = String(!!currentVal);
		} else {
			editValue = currentVal === null || currentVal === undefined ? '' : String(currentVal);
		}
	}

	async function commitEdit(rowId: string, col: Column) {
		if (!editingCell) return;
		editingCell = null;

		const row = $rows.find((r) => r.id === rowId);
		if (!row) return;

		let parsed: unknown = editValue;
		if (col.type === 'number') {
			parsed = editValue === '' ? null : Number(editValue);
		} else if (col.type === 'checkbox') {
			parsed = editValue === 'true';
		} else if (editValue === '') {
			parsed = null;
		}

		const newData = { ...row.data, [col.id]: parsed };
		error.set(null);
		try {
			await updateRow(rowId, { data: newData });
			await refreshRows($page.params.id);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update cell');
		}
	}

	async function toggleCheckbox(rowId: string, col: Column) {
		const row = $rows.find((r) => r.id === rowId);
		if (!row) return;
		const current = !!row.data[col.id];
		const newData = { ...row.data, [col.id]: !current };
		error.set(null);
		try {
			await updateRow(rowId, { data: newData });
			await refreshRows($page.params.id);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update cell');
		}
	}

	function getChoices(col: Column): ColumnChoice[] {
		const choices = col.options?.choices;
		if (!Array.isArray(choices)) return [];
		return choices as ColumnChoice[];
	}

	function getChoiceColor(col: Column, value: string): (typeof TAG_COLORS)[number] {
		const choices = getChoices(col);
		const idx = choices.findIndex((c) => c.value === value);
		return TAG_COLORS[idx >= 0 ? idx % TAG_COLORS.length : 0];
	}

	/**
	 * Format a stored date value to YYYY-MM-DD or YYYY-MM-DD HH:mm:ss.
	 * Handles ISO strings, YYYYMMDD, and YYYYMMDDHHMMSS compact formats.
	 */
	function formatDate(raw: string): string {
		if (!raw) return '';
		// Already in YYYY-MM-DD or YYYY-MM-DD HH:mm:ss
		if (/^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?/.test(raw)) {
			// Normalize ISO T-separator and strip sub-seconds / timezone
			const normalized = raw.replace('T', ' ').replace(/(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$/, '');
			// Return YYYY-MM-DD if no time part, else YYYY-MM-DD HH:mm:ss
			return normalized.length > 10 ? normalized.slice(0, 19) : normalized.slice(0, 10);
		}
		// Compact YYYYMMDDHHMMSS (14 digits)
		if (/^\d{14}$/.test(raw)) {
			return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)} ${raw.slice(8, 10)}:${raw.slice(10, 12)}:${raw.slice(12, 14)}`;
		}
		// Compact YYMMDD (6 digits)
		if (/^\d{6}$/.test(raw)) {
			return `20${raw.slice(0, 2)}-${raw.slice(2, 4)}-${raw.slice(4, 6)}`;
		}
		// Compact YYYYMMDD (8 digits)
		if (/^\d{8}$/.test(raw)) {
			return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
		}
		return raw;
	}

	function getTagValues(row: { data: Record<string, unknown> }, colId: string): string[] {
		const val = row.data[colId];
		return Array.isArray(val) ? (val as string[]) : [];
	}

	async function removeTag(rowId: string, col: Column, tag: string) {
		const row = $rows.find((r) => r.id === rowId);
		if (!row) return;
		const current = getTagValues(row, col.id);
		const newData = { ...row.data, [col.id]: current.filter((t) => t !== tag) };
		try {
			await updateRow(rowId, { data: newData });
			await refreshRows($page.params.id);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update tags');
		}
	}

	async function addTag(rowId: string, col: Column, tag: string) {
		const row = $rows.find((r) => r.id === rowId);
		if (!row) return;
		const current = getTagValues(row, col.id);
		if (current.includes(tag)) return;
		const newData = { ...row.data, [col.id]: [...current, tag] };
		tagsPopupCell = null;
		try {
			await updateRow(rowId, { data: newData });
			await refreshRows($page.params.id);
		} catch (e) {
			error.set(e instanceof Error ? e.message : 'Failed to update tags');
		}
	}

	const sortedColumns = $derived([...$columns].sort((a, b) => a.position - b.position));

	// Total min-width: row# col (48px) + all column widths + actions col (40px) + add col button (40px)
	const tableMinWidth = $derived(
		48 + sortedColumns.reduce((sum, col) => sum + getColWidth(col), 0) + 40 + 40
	);
</script>

<div
	class="min-h-screen bg-linear-to-br from-blue-600 via-blue-500 to-sky-500 {resizingColId
		? 'cursor-col-resize select-none'
		: ''}"
>
	<!-- Header -->
	<div class="flex items-center gap-4 px-6 py-4">
		<button
			onclick={() => goto('/tables')}
			class="rounded-xl p-2 text-white/70 transition hover:bg-white/10 hover:text-white"
			aria-label="Back to tables"
		>
			<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
			</svg>
		</button>
		<h1 class="text-2xl font-bold text-white">
			{$currentTable?.name ?? 'Loading...'}
		</h1>
		<div class="ml-auto flex gap-2">
			<button
				onclick={() => {
					showAddColumn = true;
				}}
				disabled={$loading}
				class="rounded-2xl bg-white/20 px-5 py-2 font-semibold text-white transition hover:bg-white/30 disabled:opacity-50"
			>
				+ Add Column
			</button>
			<button
				onclick={handleAddRow}
				disabled={addingRow || $loading}
				class="rounded-2xl bg-white px-5 py-2 font-semibold text-blue-600 transition hover:bg-white/90 disabled:opacity-50"
			>
				{addingRow ? 'Adding...' : '+ Add Row'}
			</button>
		</div>
	</div>

	{#if $error}
		<div class="mx-6 mb-4 rounded-xl bg-red-500/20 px-4 py-3 text-red-100">{$error}</div>
	{/if}

	<!-- Spreadsheet -->
	<div class="overflow-x-auto px-6 pb-6">
		{#if $loading}
			<div class="pt-16 text-center text-white/70">Loading...</div>
		{:else if $columns.length === 0}
			<div class="rounded-3xl bg-white/10 p-8 text-center text-white/70">
				No columns defined yet. Click "+ Add Column" to start.
			</div>
		{:else}
			<table
				class="border-collapse text-white"
				style="table-layout: fixed; min-width: {tableMinWidth}px;"
			>
				<thead>
					<tr>
						<!-- Row number header — sticky at left-0 -->
						<th
							class="sticky left-0 z-20 border-r border-b border-white/20 bg-blue-700 px-2 py-3 text-center text-xs font-semibold text-white/60"
							style="width: 48px;"
						>
							#
						</th>
						{#each sortedColumns as col, i (col.id)}
							<th
								class="relative border-b border-white/20 px-4 py-3 text-left text-sm font-semibold tracking-wide text-white/80 uppercase
									{i === 0 ? 'sticky left-12 z-10 border-r border-white/20 bg-blue-600' : 'bg-blue-500/30'}"
								style="width: {getColWidth(col)}px;"
							>
								<div class="flex items-center gap-1">
									<!-- Position arrows -->
									<div class="mr-1 flex flex-col">
										<button
											onclick={() => handleMoveColumn(col, 'up')}
											disabled={i === 0}
											class="rounded p-0.5 text-white/30 transition hover:bg-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-20"
											aria-label="Move column left"
											title="Move left"
										>
											<svg
												class="h-2.5 w-2.5"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M5 15l7-7 7 7"
												/>
											</svg>
										</button>
										<button
											onclick={() => handleMoveColumn(col, 'down')}
											disabled={i === sortedColumns.length - 1}
											class="rounded p-0.5 text-white/30 transition hover:bg-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-20"
											aria-label="Move column right"
											title="Move right"
										>
											<svg
												class="h-2.5 w-2.5"
												fill="none"
												stroke="currentColor"
												viewBox="0 0 24 24"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													stroke-width="2"
													d="M19 9l-7 7-7-7"
												/>
											</svg>
										</button>
									</div>
									{#if renamingColId === col.id}
										<input
											class="min-w-0 flex-1 rounded bg-white/20 px-2 py-0.5 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
											bind:value={renameValue}
											onblur={() => commitRename(col.id)}
											onkeydown={(e) => {
												if (e.key === 'Enter') commitRename(col.id);
												if (e.key === 'Escape') renamingColId = null;
											}}
											autofocus
										/>
									{:else}
										<span
											ondblclick={() => startRename(col.id, col.name)}
											class="min-w-0 flex-1 cursor-text truncate"
											title="Double-click to rename"
										>
											{col.name}
											<span class="ml-1 text-xs font-normal text-white/40">({col.type})</span>
										</span>
									{/if}
									<button
										onclick={() => handleDeleteColumn(col.id)}
										class="ml-1 shrink-0 rounded p-0.5 text-white/30 transition hover:bg-red-500/30 hover:text-red-300"
										aria-label="Delete column {col.name}"
										title="Delete column"
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
								<!-- Resize handle -->
								<div
									class="absolute top-0 right-0 h-full w-1.5 cursor-col-resize hover:bg-white/40 {resizingColId ===
									col.id
										? 'bg-white/40'
										: ''}"
									onmousedown={(e) => handleResizeStart(e, col)}
									role="separator"
									aria-label="Resize column {col.name}"
								></div>
							</th>
						{/each}
						<!-- Actions column header (delete) -->
						<th class="border-b border-white/20 bg-blue-500/30" style="width: 40px;"></th>
						<!-- Add column "+" header -->
						<th class="border-b border-white/20 bg-blue-500/20" style="width: 40px;">
							<button
								onclick={() => {
									showAddColumn = true;
								}}
								class="flex h-full w-full items-center justify-center rounded p-1 text-white/40 hover:bg-white/20 hover:text-white/80"
								title="Add column"
								aria-label="Add column"
							>
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M12 4v16m8-8H4"
									/>
								</svg>
							</button>
						</th>
					</tr>
				</thead>
				<tbody>
					{#each $rows as row, rowIdx (row.id)}
						<tr
							class="border-b border-white/10 transition hover:bg-white/5 {deletingRowId === row.id
								? 'opacity-50'
								: ''}"
						>
							<!-- Row number — sticky at left-0 -->
							<td
								class="sticky left-0 z-20 border-r border-white/10 bg-blue-700 px-2 py-1 text-center text-xs text-white/40"
								style="width: 48px;"
							>
								{rowIdx + 1}
							</td>
							{#each sortedColumns as col, i (col.id)}
								<td
									class="overflow-hidden py-1 text-sm text-white/90
										{i === 0 ? 'sticky left-12 z-10 border-r border-white/10 bg-blue-600 px-2' : 'px-2'}"
									style="width: {getColWidth(col)}px;"
									onclick={() => {
										if (
											col.type !== 'checkbox' &&
											col.type !== 'tags' &&
											!(editingCell?.rowId === row.id && editingCell?.colId === col.id)
										) {
											startEdit(row.id, col, row.data[col.id]);
										}
									}}
								>
									{#if editingCell?.rowId === row.id && editingCell?.colId === col.id}
										{#if col.type === 'select'}
											{@const choices = getChoices(col)}
											<select
												class="w-full rounded bg-white/20 px-2 py-1 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
												bind:value={editValue}
												onblur={() => commitEdit(row.id, col)}
												onchange={() => commitEdit(row.id, col)}
												autofocus
											>
												<option value="">—</option>
												{#each choices as choice (choice.value)}
													<option value={choice.value}>{choice.value}</option>
												{/each}
											</select>
										{:else if col.type === 'number'}
											<input
												type="number"
												class="w-full rounded bg-white/20 px-2 py-1 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
												bind:value={editValue}
												onblur={() => commitEdit(row.id, col)}
												onkeydown={(e) => {
													if (e.key === 'Enter') commitEdit(row.id, col);
													if (e.key === 'Escape') editingCell = null;
												}}
												autofocus
											/>
										{:else if col.type === 'date'}
											<input
												type="date"
												class="w-full rounded bg-white/20 px-2 py-1 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
												bind:value={editValue}
												onblur={() => commitEdit(row.id, col)}
												onkeydown={(e) => {
													if (e.key === 'Enter') commitEdit(row.id, col);
													if (e.key === 'Escape') editingCell = null;
												}}
												autofocus
											/>
										{:else}
											<input
												type={col.type === 'url' ? 'url' : 'text'}
												class="w-full rounded bg-white/20 px-2 py-1 text-sm text-white outline-none focus:ring-1 focus:ring-white/50"
												bind:value={editValue}
												onblur={() => commitEdit(row.id, col)}
												onkeydown={(e) => {
													if (e.key === 'Enter') commitEdit(row.id, col);
													if (e.key === 'Escape') editingCell = null;
												}}
												autofocus
											/>
										{/if}
									{:else if col.type === 'checkbox'}
										<!-- Styled toggle -->
										<button
											class="relative inline-flex h-5 w-9 items-center rounded-full transition {row
												.data[col.id]
												? 'bg-blue-500'
												: 'bg-white/20'}"
											onclick={(e) => {
												e.stopPropagation();
												toggleCheckbox(row.id, col);
											}}
											aria-label="Toggle"
											role="switch"
											aria-checked={!!row.data[col.id]}
										>
											<span
												class="inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition {row
													.data[col.id]
													? 'translate-x-4'
													: 'translate-x-1'}"
											></span>
										</button>
									{:else if col.type === 'url'}
										{@const urlVal = (row.data[col.id] as string) ?? ''}
										{#if urlVal}
											<a
												href={urlVal}
												target="_blank"
												rel="noopener noreferrer"
												class="block max-w-full truncate text-sky-300 underline hover:text-sky-100"
												onclick={(e) => e.stopPropagation()}
												title={urlVal}>{urlVal}</a
											>
										{:else}
											<span class="block min-h-[1.5rem] cursor-text py-1 text-white/30">—</span>
										{/if}
									{:else if col.type === 'select'}
										{@const selVal = (row.data[col.id] as string) ?? ''}
										{#if selVal}
											{@const color = getChoiceColor(col, selVal)}
											<span
												class="inline-flex cursor-pointer items-center rounded-full border px-2 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
											>
												{selVal}
											</span>
										{:else}
											<span class="block min-h-[1.5rem] cursor-pointer py-1 text-white/30">—</span>
										{/if}
									{:else if col.type === 'tags'}
										{@const tagVals = getTagValues(row, col.id)}
										{@const choices = getChoices(col)}
										{@const available = choices.filter((c) => !tagVals.includes(c.value))}
										<div
											class="flex min-h-[1.75rem] flex-wrap items-center gap-1"
											onclick={(e) => e.stopPropagation()}
										>
											{#each tagVals as tag (tag)}
												{@const color = getChoiceColor(col, tag)}
												<span
													class="inline-flex items-center gap-0.5 rounded-full border px-2 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
												>
													{tag}
													<button
														class="ml-0.5 rounded-full leading-none hover:opacity-60"
														onclick={() => removeTag(row.id, col, tag)}
														aria-label="Remove {tag}">×</button
													>
												</span>
											{/each}
											{#if available.length > 0}
												<div class="relative">
													<button
														class="rounded-full border border-white/30 px-2 py-0.5 text-xs text-white/50 hover:border-white/60 hover:text-white/80"
														onclick={() => {
															tagsPopupCell =
																tagsPopupCell?.rowId === row.id && tagsPopupCell?.colId === col.id
																	? null
																	: { rowId: row.id, colId: col.id };
														}}>+</button
													>
													{#if tagsPopupCell?.rowId === row.id && tagsPopupCell?.colId === col.id}
														<div
															class="absolute top-full left-0 z-20 mt-1 min-w-[120px] rounded-xl border border-gray-100 bg-white py-1 shadow-xl"
														>
															{#each available as choice (choice.value)}
																{@const color =
																	TAG_COLORS[choices.indexOf(choice) % TAG_COLORS.length]}
																<button
																	class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-gray-50"
																	onclick={() => addTag(row.id, col, choice.value)}
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
									{:else if col.type === 'date'}
										{@const dateVal = row.data[col.id] ? formatDate(String(row.data[col.id])) : ''}
										{#if dateVal}
											<span class="block cursor-text py-1 font-mono text-xs text-white/90"
												>{dateVal}</span
											>
										{:else}
											<span class="block min-h-[1.5rem] cursor-text py-1 text-white/30">—</span>
										{/if}
									{:else}
										<!-- text / string / number -->
										<span
											class="block min-h-[1.5rem] cursor-text truncate py-1"
											title="Click to edit"
										>
											{getCellValue(row, col.id)}
										</span>
									{/if}
								</td>
							{/each}
							<!-- Row delete button -->
							<td class="px-1 py-1 text-center" style="width: 40px;">
								<button
									onclick={() => handleDeleteRow(row.id)}
									disabled={deletingRowId === row.id}
									class="rounded p-1 text-white/30 transition hover:bg-red-500/30 hover:text-red-300 disabled:opacity-50"
									aria-label="Delete row"
									title="Delete row"
								>
									<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path
											stroke-linecap="round"
											stroke-linejoin="round"
											stroke-width="2"
											d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
										/>
									</svg>
								</button>
							</td>
							<!-- Empty cell for "+" add column header -->
							<td style="width: 40px;"></td>
						</tr>
					{:else}
						<tr>
							<td
								colspan={sortedColumns.length + 3}
								class="px-4 py-8 text-center text-sm text-white/50"
							>
								No rows yet. Click "+ Add Row" to start.
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</div>

<!-- Add Column Modal -->
{#if showAddColumn}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
		onclick={(e) => {
			if (e.target === e.currentTarget) showAddColumn = false;
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
					class="w-full rounded-xl border border-gray-200 px-4 py-2 text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
					bind:value={newColName}
					placeholder="Column name"
					onkeydown={(e) => {
						if (e.key === 'Enter') handleAddColumn();
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
					onclick={() => {
						showAddColumn = false;
						newColName = '';
						newColType = 'text';
					}}
					class="flex-1 rounded-2xl border border-gray-200 px-4 py-2 font-semibold text-gray-600 transition hover:bg-gray-50"
				>
					Cancel
				</button>
				<button
					onclick={handleAddColumn}
					disabled={addingColumn || !newColName.trim()}
					class="flex-1 rounded-2xl bg-linear-to-r from-blue-600 to-blue-500 px-4 py-2 font-semibold text-white transition hover:shadow-lg disabled:opacity-50"
				>
					{addingColumn ? 'Adding...' : 'Add Column'}
				</button>
			</div>
		</div>
	</div>
{/if}

<script lang="ts">
	import type { Column, Row, ViewConfig } from '$lib/types/table';
	import { getChoices, getChoiceColor, getTagValues, formatDate } from './table.utils';
	import { updateRow } from '$lib/backend/tables';
	import { updateView } from '$lib/backend/views';
	import { isDark } from '$lib/UI/theme.svelte';

	let {
		tableId,
		columns,
		rows,
		viewConfig,
		onOpenExpand,
		onRowsRefresh = () => {},
		onViewUpdate = () => {},
		onAddRow = () => {}
	}: {
		tableId: string;
		columns: Column[];
		rows: Row[];
		viewConfig: ViewConfig;
		onOpenExpand: (row: Row) => void;
		onRowsRefresh?: () => void;
		onViewUpdate?: (updated: ViewConfig) => void;
		onAddRow?: (initialData: Record<string, unknown>) => void;
	} = $props();

	// Config panel state
	let showCardFields = $state(false);

	async function saveConfig(patch: Record<string, unknown>) {
		const newConfig = { ...viewConfig.config, ...patch };
		const updated = await updateView(tableId, viewConfig.name, newConfig);
		onViewUpdate(updated);
	}

	async function handleGroupByChange(e: Event) {
		const val = (e.target as HTMLSelectElement).value;
		await saveConfig({ group_by: val || undefined, card_fields: [] });
	}

	async function toggleCardField(colId: string) {
		const current = (viewConfig.config.card_fields as string[]) ?? [];
		const next = current.includes(colId)
			? current.filter((id) => id !== colId)
			: [...current, colId];
		await saveConfig({ card_fields: next });
	}

	const selectColumns = $derived(columns.filter((c) => c.type === 'select'));

	// Drag state
	let dragRowId = $state<number | null>(null);
	let dragOverLane = $state<string | null>(null);

	function onDragStart(e: DragEvent, row: Row) {
		dragRowId = row.row_number;
		if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
	}

	function onDragEnd() {
		dragRowId = null;
		dragOverLane = null;
	}

	function onDragOver(e: DragEvent, laneValue: string) {
		e.preventDefault();
		if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
		dragOverLane = laneValue;
	}

	function onDragLeave(e: DragEvent) {
		const target = e.currentTarget as HTMLElement;
		const related = e.relatedTarget as Node | null;
		if (!related || !target.contains(related)) dragOverLane = null;
	}

	async function onDrop(e: DragEvent, laneValue: string) {
		e.preventDefault();
		dragOverLane = null;
		if (!dragRowId || !groupByColId) return;

		const row = rows.find((r) => r.row_number === dragRowId);
		dragRowId = null;
		if (!row) return;

		const currentVal = String(row.row_data[groupByColId] ?? '');
		if (currentVal === laneValue) return;

		await updateRow(tableId, row.row_number, {
			row_data: { ...row.row_data, [groupByColId]: laneValue }
		});
		onRowsRefresh();
	}

	const groupByColId = $derived(viewConfig.config.group_by as string | undefined);
	const cardFields = $derived((viewConfig.config.card_fields as string[]) ?? []);
	const sortColId = $derived(viewConfig.config.sort_col as string | undefined);
	const sortDir = $derived((viewConfig.config.sort_dir as 'asc' | 'desc') ?? 'asc');

	async function handleSortColChange(e: Event) {
		const val = (e.target as HTMLSelectElement).value;
		await saveConfig({ sort_col: val || undefined });
	}

	async function handleSortDirChange(e: Event) {
		const val = (e.target as HTMLSelectElement).value as 'asc' | 'desc';
		await saveConfig({ sort_dir: val });
	}

	function sortRows(rowList: Row[]): Row[] {
		if (!sortColId) return rowList;
		return [...rowList].sort((a, b) => {
			const av = a.row_data[sortColId];
			const bv = b.row_data[sortColId];
			const as = av === null || av === undefined ? '' : String(av);
			const bs = bv === null || bv === undefined ? '' : String(bv);
			const aNum = Number(as);
			const bNum = Number(bs);
			let cmp: number;
			if (!isNaN(aNum) && !isNaN(bNum)) {
				cmp = aNum - bNum;
			} else {
				cmp = as.localeCompare(bs);
			}
			return sortDir === 'asc' ? cmp : -cmp;
		});
	}

	const groupCol = $derived(
		groupByColId ? columns.find((c) => c.column_id === groupByColId) : undefined
	);

	// Prefer a column named "Priority" (select type) for card accent color; fall back to group col
	const priorityCol = $derived(
		columns.find((c) => c.name.toLowerCase() === 'priority' && c.type === 'select')
	);

	const choices = $derived(groupCol ? getChoices(groupCol) : []);

	const lanes = $derived.by(() => {
		if (!groupByColId || !groupCol) return [];

		const buckets = new Map<string, Row[]>();
		for (const c of choices) buckets.set(c.value, []);
		buckets.set('', []);

		for (const row of rows) {
			const val = row.row_data[groupByColId];
			const key = val === null || val === undefined || val === '' ? '' : String(val);
			if (buckets.has(key)) {
				buckets.get(key)!.push(row);
			} else {
				buckets.get('')!.push(row);
			}
		}

		const result = choices.map((c) => ({ value: c.value, rows: buckets.get(c.value) ?? [] }));
		const uncategorized = buckets.get('') ?? [];
		if (uncategorized.length > 0) {
			result.push({ value: '', rows: uncategorized });
		}
		return result;
	});

	const cardColumns = $derived(
		cardFields.length > 0
			? cardFields.map((id) => columns.find((c) => c.column_id === id)).filter(Boolean)
			: (columns.slice(0, 3) as Column[])
	);

	function getCardBorderStyle(row: Row): string {
		const accentCol = priorityCol ?? groupCol;
		if (!accentCol) return '';
		const val = row.row_data[accentCol.column_id];
		if (val === null || val === undefined || val === '') return '';
		const color = getChoiceColor(accentCol, String(val));
		// TAG_COLORS border class format: 'border-blue-200' → CSS var '--color-blue-200'
		const colorName = color.border.replace('border-', '');
		return `border-left: 4px solid var(--color-${colorName})`;
	}

	function getLaneColor(value: string) {
		if (!groupCol || !value)
			return { bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-200' };
		return getChoiceColor(groupCol, value);
	}
</script>

<!-- Config bar -->
<div
	class="flex items-center gap-4 border-b px-4 py-2 {isDark.value
		? 'border-gray-700 bg-gray-800'
		: 'border-gray-200 bg-white'}"
	onclick={(e) => {
		if (!(e.target as HTMLElement).closest('.card-fields-panel')) showCardFields = false;
	}}
>
	<!-- Group by -->
	<div class="flex items-center gap-2">
		<span class="text-xs font-medium {isDark.value ? 'text-gray-400' : 'text-gray-500'}"
			>Group by</span
		>
		<select
			class="rounded-md border px-2 py-1 text-xs focus:outline-none {isDark.value
				? 'border-gray-600 bg-gray-700 text-gray-200 focus:border-blue-400'
				: 'border-gray-200 bg-white text-gray-700 focus:border-blue-500'}"
			value={groupByColId ?? ''}
			onchange={handleGroupByChange}
		>
			<option value="">— none —</option>
			{#each selectColumns as col (col.column_id)}
				<option value={col.column_id}>{col.name}</option>
			{/each}
		</select>
	</div>

	<!-- Sort -->
	<div class="flex items-center gap-2">
		<span class="text-xs font-medium {isDark.value ? 'text-gray-400' : 'text-gray-500'}"
			>Sort by</span
		>
		<select
			class="rounded-md border px-2 py-1 text-xs focus:outline-none {isDark.value
				? 'border-gray-600 bg-gray-700 text-gray-200 focus:border-blue-400'
				: 'border-gray-200 bg-white text-gray-700 focus:border-blue-500'}"
			value={sortColId ?? ''}
			onchange={handleSortColChange}
		>
			<option value="">— none —</option>
			{#each columns as col (col.column_id)}
				<option value={col.column_id}>{col.name}</option>
			{/each}
		</select>
		{#if sortColId}
			<select
				class="rounded-md border px-2 py-1 text-xs focus:outline-none {isDark.value
					? 'border-gray-600 bg-gray-700 text-gray-200 focus:border-blue-400'
					: 'border-gray-200 bg-white text-gray-700 focus:border-blue-500'}"
				value={sortDir}
				onchange={handleSortDirChange}
			>
				<option value="asc">A → Z</option>
				<option value="desc">Z → A</option>
			</select>
		{/if}
	</div>

	<!-- Card fields -->
	<div class="card-fields-panel relative">
		<button
			class="flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs {isDark.value
				? 'border-gray-600 bg-gray-700 text-gray-200 hover:bg-gray-600'
				: 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'}"
			onclick={(e) => {
				e.stopPropagation();
				showCardFields = !showCardFields;
			}}
		>
			<svg class="h-3.5 w-3.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M4 6h16M4 12h16M4 18h16"
				/>
			</svg>
			Card fields
			{#if cardFields.length > 0}
				<span class="ml-0.5 rounded-full bg-blue-100 px-1.5 text-blue-700">{cardFields.length}</span
				>
			{/if}
		</button>
		{#if showCardFields}
			<div
				class="card-fields-panel absolute top-full left-0 z-30 mt-1 min-w-[200px] rounded-xl border py-1 shadow-xl {isDark.value
					? 'border-gray-700 bg-gray-800'
					: 'border-gray-200 bg-white'}"
				onclick={(e) => e.stopPropagation()}
				role="menu"
			>
				<div class="px-3 py-1.5 text-xs font-semibold tracking-wide text-gray-400 uppercase">
					Show on cards
				</div>
				{#each columns as col (col.column_id)}
					<label
						class="flex cursor-pointer items-center gap-2 px-3 py-1.5 {isDark.value
							? 'hover:bg-gray-700'
							: 'hover:bg-gray-50'}"
					>
						<input
							type="checkbox"
							class="accent-blue-500"
							checked={cardFields.includes(col.column_id)}
							onchange={() => toggleCardField(col.column_id)}
						/>
						<span class="text-sm {isDark.value ? 'text-gray-300' : 'text-gray-700'}"
							>{col.name}</span
						>
						<span class="ml-auto text-xs text-gray-400">{col.type}</span>
					</label>
				{/each}
			</div>
		{/if}
	</div>
</div>

{#if !groupByColId || !groupCol}
	<div
		class="flex h-64 items-center justify-center {isDark.value ? 'text-gray-500' : 'text-gray-400'}"
	>
		<div class="text-center">
			<p class="text-sm">Select a "Group by" column above to activate the Kanban view.</p>
		</div>
	</div>
{:else}
	<div class="flex h-full gap-4 overflow-x-auto p-4 {isDark.value ? 'bg-gray-900' : ''}">
		{#each lanes as lane (lane.value)}
			{@const color = getLaneColor(lane.value)}
			<div
				role="group"
				aria-label="{lane.value || 'Uncategorized'} lane"
				class="flex w-72 shrink-0 flex-col rounded-xl border transition-shadow {isDark.value
					? 'border-gray-700 bg-gray-800'
					: 'border-gray-200 bg-gray-50'} {dragOverLane === lane.value
					? 'ring-2 ring-blue-400 ring-offset-1'
					: ''}"
				ondragover={(e) => onDragOver(e, lane.value)}
				ondragleave={onDragLeave}
				ondrop={(e) => onDrop(e, lane.value)}
			>
				<!-- Lane header -->
				<div
					class="flex items-center gap-2 border-b px-3 py-2.5 {isDark.value
						? 'border-gray-700'
						: 'border-gray-200'}"
				>
					<span
						class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
					>
						{lane.value || 'Uncategorized'}
					</span>
					<span class="ml-auto text-xs text-gray-400">{lane.rows.length}</span>
				</div>

				<!-- Cards -->
				<div class="flex flex-col gap-2 overflow-y-auto p-2">
					{#if lane.rows.length === 0}
						<div
							class="rounded-lg border border-dashed px-3 py-4 text-center {isDark.value
								? 'border-gray-700'
								: 'border-gray-200'}"
						>
							<p class="text-xs {isDark.value ? 'text-gray-500' : 'text-gray-400'}">No items</p>
						</div>
					{:else}
						{#each sortRows(lane.rows) as row (row.row_number)}
							<button
								draggable="true"
								ondragstart={(e) => onDragStart(e, row)}
								ondragend={onDragEnd}
								class="w-full rounded-lg border px-3 py-2.5 text-left shadow-sm transition hover:shadow-md {isDark.value
									? 'border-gray-700 bg-gray-700'
									: 'border-gray-200 bg-white'} {dragRowId === row.row_number ? 'opacity-40' : ''}"
								style={getCardBorderStyle(row)}
								onclick={() => onOpenExpand(row)}
							>
								{#each cardColumns as col (col!.column_id)}
									{@const val = row.row_data[col!.column_id]}
									<div class="mb-1 last:mb-0">
										{#if col!.type === 'select' && val}
											{@const choiceColor = getChoiceColor(col!, String(val))}
											<span
												class="inline-flex items-center rounded-full border px-1.5 py-0.5 text-xs font-medium {choiceColor.bg} {choiceColor.text} {choiceColor.border}"
											>
												{val}
											</span>
										{:else if col!.type === 'tags'}
											<div class="flex flex-wrap gap-1">
												{#each getTagValues(row, col!.column_id) as tag, i (tag)}
													{@const tc = getChoiceColor(col!, tag)}
													<span
														class="inline-flex items-center rounded-full border px-1.5 py-0.5 text-xs {tc.bg} {tc.text} {tc.border}"
													>
														{tag}
													</span>
												{/each}
											</div>
										{:else if col!.type === 'checkbox'}
											<span class="text-sm {val ? 'text-green-600' : 'text-gray-300'}">
												{val ? '✓' : '✗'}
											</span>
										{:else if col!.type === 'url' && val}
											<a
												href={String(val)}
												target="_blank"
												rel="noopener noreferrer"
												class="truncate text-xs text-blue-600 hover:underline"
												onclick={(e) => e.stopPropagation()}
											>
												{val}
											</a>
										{:else if val !== null && val !== undefined && val !== ''}
											<span
												class="block truncate text-sm {isDark.value
													? 'text-gray-200'
													: 'text-gray-700'}"
											>
												{col!.type === 'date' ? formatDate(String(val)) : String(val)}
											</span>
										{/if}
									</div>
								{/each}
							</button>
						{/each}
					{/if}

					<!-- Add ticket button per lane -->
					<button
						onclick={() =>
							onAddRow(groupByColId && lane.value ? { [groupByColId]: lane.value } : {})}
						class="mt-1 w-full rounded-lg px-3 py-1.5 text-left text-xs transition {isDark.value
							? 'text-gray-500 hover:bg-gray-700 hover:text-gray-300'
							: 'text-gray-400 hover:bg-gray-100 hover:text-gray-600'}"
					>
						+ New ticket
					</button>
				</div>
			</div>
		{/each}
	</div>
{/if}

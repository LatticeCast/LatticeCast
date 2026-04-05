<script lang="ts">
	import type { Column, Row, ViewConfig } from '$lib/types/table';
	import { getChoices, getChoiceColor, formatDate } from './table.utils';
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
		onViewUpdate = () => {}
	}: {
		tableId: string;
		columns: Column[];
		rows: Row[];
		viewConfig: ViewConfig;
		onOpenExpand: (row: Row) => void;
		onRowsRefresh?: () => void;
		onViewUpdate?: (updated: ViewConfig) => void;
	} = $props();

	type Granularity = 'day' | 'week' | 'month';
	let granularity = $state<Granularity>('month');

	// Config
	const startColId = $derived(viewConfig.config.start_col as string | undefined);
	const endColId = $derived(viewConfig.config.end_col as string | undefined);
	const colorByColId = $derived(viewConfig.config.color_by as string | undefined);
	const groupByColId = $derived(viewConfig.config.group_by as string | undefined);

	const dateColumns = $derived(columns.filter((c) => c.type === 'date'));
	const selectColumns = $derived(columns.filter((c) => c.type === 'select'));

	const colorByCol = $derived(
		colorByColId ? columns.find((c) => c.column_id === colorByColId) : undefined
	);
	const groupByCol = $derived(
		groupByColId ? columns.find((c) => c.column_id === groupByColId) : undefined
	);
	const labelCol = $derived(columns.find((c) => c.type === 'text' || c.type === 'string'));

	async function saveConfig(patch: Record<string, unknown>) {
		const newConfig = { ...viewConfig.config, ...patch };
		const updated = await updateView(tableId, viewConfig.name, newConfig);
		onViewUpdate(updated);
	}

	function parseDate(raw: unknown): Date | null {
		if (!raw) return null;
		const normalized = formatDate(String(raw));
		const d = new Date(normalized.slice(0, 10));
		return isNaN(d.getTime()) ? null : d;
	}

	const rowsWithDates = $derived.by(() => {
		if (!startColId) return [];
		const result: { row: Row; startDate: Date; endDate: Date }[] = [];
		for (const r of rows) {
			const startDate = parseDate(r.row_data[startColId]);
			if (!startDate) continue;
			const rawEnd = endColId ? parseDate(r.row_data[endColId]) : null;
			result.push({ row: r, startDate, endDate: rawEnd ?? startDate });
		}
		return result;
	});

	const today = new Date();

	const viewportStart = $derived.by(() => {
		if (rowsWithDates.length === 0) {
			return new Date(today.getFullYear(), today.getMonth() - 1, 1);
		}
		const min = rowsWithDates.reduce(
			(m, r) => (r.startDate < m ? r.startDate : m),
			rowsWithDates[0].startDate
		);
		return new Date(min.getFullYear(), min.getMonth() - 1, 1);
	});

	const viewportEnd = $derived.by(() => {
		if (rowsWithDates.length === 0) {
			return new Date(today.getFullYear(), today.getMonth() + 3, 0);
		}
		const max = rowsWithDates.reduce(
			(m, r) => (r.endDate > m ? r.endDate : m),
			rowsWithDates[0].endDate
		);
		return new Date(max.getFullYear(), max.getMonth() + 2, 0);
	});

	function generateTimeColumns(start: Date, end: Date, gran: Granularity): Date[] {
		const cols: Date[] = [];
		let cur = start;
		while (cur <= end) {
			cols.push(cur);
			if (gran === 'day') {
				cur = new Date(cur.getFullYear(), cur.getMonth(), cur.getDate() + 1);
			} else if (gran === 'week') {
				cur = new Date(cur.getFullYear(), cur.getMonth(), cur.getDate() + 7);
			} else {
				cur = new Date(cur.getFullYear(), cur.getMonth() + 1, 1);
			}
		}
		return cols;
	}

	const timeColumns = $derived(generateTimeColumns(viewportStart, viewportEnd, granularity));

	const cellWidth = $derived(granularity === 'day' ? 40 : granularity === 'week' ? 80 : 120);
	const totalGridWidth = $derived(timeColumns.length * cellWidth);

	function dateToX(date: Date): number {
		const totalMs = viewportEnd.getTime() - viewportStart.getTime();
		if (totalMs === 0) return 0;
		const offsetMs = date.getTime() - viewportStart.getTime();
		return Math.max(0, Math.min(totalGridWidth, (offsetMs / totalMs) * totalGridWidth));
	}

	function getBarLeft(startDate: Date): number {
		return dateToX(startDate);
	}

	function getBarWidth(startDate: Date, endDate: Date): number {
		const endInclusive = new Date(endDate.getTime() + 86400000);
		return Math.max(cellWidth / 2, dateToX(endInclusive) - dateToX(startDate));
	}

	function getBarColorClasses(row: Row): string {
		if (!colorByCol || !colorByColId) return 'bg-blue-400 text-white';
		const val = row.row_data[colorByColId];
		if (!val) return 'bg-blue-400 text-white';
		const choices = getChoices(colorByCol);
		const idx = choices.findIndex((c) => c.value === String(val));
		// Map TAG_COLORS index to a saturated bar color
		const COLORS = [
			'bg-blue-400 text-white',
			'bg-green-400 text-white',
			'bg-yellow-400 text-gray-800',
			'bg-red-400 text-white',
			'bg-purple-400 text-white',
			'bg-pink-400 text-white',
			'bg-orange-400 text-white',
			'bg-teal-400 text-white',
			'bg-cyan-400 text-gray-800',
			'bg-indigo-400 text-white',
			'bg-lime-400 text-gray-800',
			'bg-rose-400 text-white'
		];
		return COLORS[idx >= 0 ? idx % COLORS.length : 0];
	}

	function formatColHeader(date: Date, gran: Granularity): string {
		if (gran === 'day') {
			return `${date.getMonth() + 1}/${date.getDate()}`;
		} else if (gran === 'week') {
			const weekNum = getWeekNumber(date);
			return `W${weekNum} ${date.getFullYear()}`;
		} else {
			return date.toLocaleString('default', { month: 'short', year: 'numeric' });
		}
	}

	function getWeekNumber(d: Date): number {
		const dayOfWeek =
			new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())).getUTCDay() || 7;
		const thursday = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate() + 4 - dayOfWeek));
		const yearStart = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 1));
		return Math.ceil(((thursday.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
	}

	function isToday(date: Date, gran: Granularity): boolean {
		if (gran === 'day') {
			return (
				date.getFullYear() === today.getFullYear() &&
				date.getMonth() === today.getMonth() &&
				date.getDate() === today.getDate()
			);
		} else if (gran === 'week') {
			const weekEnd = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 6);
			return today >= date && today <= weekEnd;
		} else {
			return date.getFullYear() === today.getFullYear() && date.getMonth() === today.getMonth();
		}
	}

	const groupedRows = $derived.by(() => {
		if (!groupByColId || !groupByCol) {
			return [{ key: '', label: '', rows: rowsWithDates }];
		}
		const grouped: Record<string, typeof rowsWithDates> = {};
		for (const r of rowsWithDates) {
			const val = String(r.row.row_data[groupByColId] ?? '');
			if (!grouped[val]) grouped[val] = [];
			grouped[val].push(r);
		}
		return Object.entries(grouped).map(([key, rs]) => ({
			key,
			label: key || 'Uncategorized',
			rows: rs
		}));
	});

	const todayX = $derived(dateToX(today));

	const SIDEBAR_WIDTH = 180;
	const ROW_HEIGHT = 44;
	const HEADER_HEIGHT = 36;

	const GRANULARITIES: Granularity[] = ['day', 'week', 'month'];

	// ── Drag resize ───────────────────────────────────────────────────────

	let dragState = $state<{
		rowId: string;
		handle: 'start' | 'end';
		startX: number;
		origDateStr: string;
		colId: string;
	} | null>(null);
	let dragDeltaDays = $state(0);

	function onResizeMouseDown(e: MouseEvent, row: Row, handle: 'start' | 'end') {
		e.stopPropagation();
		e.preventDefault();
		const colId = handle === 'start' ? startColId! : endColId!;
		const rawVal = row.row_data[colId];
		const origDateStr = rawVal ? formatDate(String(rawVal)).slice(0, 10) : '';
		dragState = { rowId: row.row_id, handle, startX: e.clientX, origDateStr, colId };
		dragDeltaDays = 0;
	}

	$effect(() => {
		if (!dragState) return;

		function onMove(e: MouseEvent) {
			if (!dragState) return;
			dragDeltaDays = Math.round((e.clientX - dragState.startX) / cellWidth);
		}

		async function onUp(e: MouseEvent) {
			window.removeEventListener('mousemove', onMove);
			window.removeEventListener('mouseup', onUp);
			if (!dragState) return;
			const delta = Math.round((e.clientX - dragState.startX) / cellWidth);
			if (delta !== 0 && dragState.origDateStr) {
				const orig = new Date(dragState.origDateStr + 'T00:00:00Z');
				if (!isNaN(orig.getTime())) {
					const newDate = new Date(orig);
					newDate.setUTCDate(newDate.getUTCDate() + delta);
					const newDateStr = newDate.toISOString().slice(0, 10);
					const row = rows.find((r) => r.row_id === dragState!.rowId);
					if (row) {
						await updateRow(tableId, row.row_number, {
							row_data: { ...row.row_data, [dragState.colId]: newDateStr }
						});
						onRowsRefresh();
					}
				}
			}
			dragState = null;
			dragDeltaDays = 0;
		}

		window.addEventListener('mousemove', onMove);
		window.addEventListener('mouseup', onUp);
		return () => {
			window.removeEventListener('mousemove', onMove);
			window.removeEventListener('mouseup', onUp);
		};
	});

	function getEffectiveDates(
		row: Row,
		startDate: Date,
		endDate: Date
	): { startDate: Date; endDate: Date } {
		if (!dragState || dragState.rowId !== row.row_id || dragDeltaDays === 0) {
			return { startDate, endDate };
		}
		const orig = new Date(dragState.origDateStr + 'T00:00:00Z');
		if (isNaN(orig.getTime())) return { startDate, endDate };
		const shifted = new Date(orig);
		shifted.setUTCDate(shifted.getUTCDate() + dragDeltaDays);
		if (dragState.handle === 'start') return { startDate: shifted, endDate };
		return { startDate, endDate: shifted };
	}
</script>

<!-- Config bar -->
<div class="flex flex-wrap items-center gap-3 border-b px-4 py-2 {isDark.value ? 'border-gray-700 bg-gray-800' : 'border-gray-200 bg-white'}">
	<!-- Start date -->
	<div class="flex items-center gap-2">
		<span class="text-xs font-medium {isDark.value ? 'text-gray-400' : 'text-gray-500'}">Start</span>
		<select
			class="rounded-md border px-2 py-1 text-xs focus:outline-none {isDark.value ? 'border-gray-600 bg-gray-700 text-gray-200 focus:border-blue-400' : 'border-gray-200 bg-white text-gray-700 focus:border-blue-500'}"
			value={startColId ?? ''}
			onchange={(e) =>
				saveConfig({ start_col: (e.target as HTMLSelectElement).value || undefined })}
		>
			<option value="">— none —</option>
			{#each dateColumns as col (col.column_id)}
				<option value={col.column_id}>{col.name}</option>
			{/each}
		</select>
	</div>

	<!-- End date -->
	<div class="flex items-center gap-2">
		<span class="text-xs font-medium {isDark.value ? 'text-gray-400' : 'text-gray-500'}">End</span>
		<select
			class="rounded-md border px-2 py-1 text-xs focus:outline-none {isDark.value ? 'border-gray-600 bg-gray-700 text-gray-200 focus:border-blue-400' : 'border-gray-200 bg-white text-gray-700 focus:border-blue-500'}"
			value={endColId ?? ''}
			onchange={(e) => saveConfig({ end_col: (e.target as HTMLSelectElement).value || undefined })}
		>
			<option value="">— none —</option>
			{#each dateColumns as col (col.column_id)}
				<option value={col.column_id}>{col.name}</option>
			{/each}
		</select>
	</div>

	<!-- Color by -->
	<div class="flex items-center gap-2">
		<span class="text-xs font-medium {isDark.value ? 'text-gray-400' : 'text-gray-500'}">Color by</span>
		<select
			class="rounded-md border px-2 py-1 text-xs focus:outline-none {isDark.value ? 'border-gray-600 bg-gray-700 text-gray-200 focus:border-blue-400' : 'border-gray-200 bg-white text-gray-700 focus:border-blue-500'}"
			value={colorByColId ?? ''}
			onchange={(e) => saveConfig({ color_by: (e.target as HTMLSelectElement).value || undefined })}
		>
			<option value="">— none —</option>
			{#each selectColumns as col (col.column_id)}
				<option value={col.column_id}>{col.name}</option>
			{/each}
		</select>
	</div>

	<!-- Group by -->
	<div class="flex items-center gap-2">
		<span class="text-xs font-medium {isDark.value ? 'text-gray-400' : 'text-gray-500'}">Group by</span>
		<select
			class="rounded-md border px-2 py-1 text-xs focus:outline-none {isDark.value ? 'border-gray-600 bg-gray-700 text-gray-200 focus:border-blue-400' : 'border-gray-200 bg-white text-gray-700 focus:border-blue-500'}"
			value={groupByColId ?? ''}
			onchange={(e) => saveConfig({ group_by: (e.target as HTMLSelectElement).value || undefined })}
		>
			<option value="">— none —</option>
			{#each columns as col (col.column_id)}
				<option value={col.column_id}>{col.name}</option>
			{/each}
		</select>
	</div>

	<!-- Granularity toggle -->
	<div class="ml-auto flex items-center gap-0.5 rounded-lg border p-0.5 {isDark.value ? 'border-gray-600 bg-gray-700' : 'border-gray-200 bg-gray-50'}">
		{#each GRANULARITIES as g (g)}
			<button
				class="rounded-md px-2.5 py-1 text-xs font-medium capitalize transition {granularity === g
					? (isDark.value ? 'bg-gray-600 text-blue-300 shadow-sm' : 'bg-white text-blue-600 shadow-sm')
					: (isDark.value ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-700')}"
				onclick={() => (granularity = g)}
			>
				{g}
			</button>
		{/each}
	</div>
</div>

{#if !startColId}
	<div class="flex h-64 items-center justify-center {isDark.value ? 'text-gray-500' : 'text-gray-400'}">
		<div class="text-center">
			<p class="text-sm">Select a "Start" date column above to activate the Timeline view.</p>
		</div>
	</div>
{:else}
	<!-- Timeline grid -->
	<div class="relative flex-1 overflow-auto">
		<div style="min-width: {SIDEBAR_WIDTH + totalGridWidth}px">
			<!-- Header row -->
			<div
				class="sticky top-0 z-20 flex border-b {isDark.value ? 'border-gray-700 bg-gray-800' : 'border-gray-200 bg-white'}"
				style="height: {HEADER_HEIGHT}px"
			>
				<!-- Sidebar corner -->
				<div
					class="sticky left-0 z-30 flex-shrink-0 border-r {isDark.value ? 'border-gray-700 bg-gray-800' : 'border-gray-200 bg-white'}"
					style="width: {SIDEBAR_WIDTH}px"
				></div>
				<!-- Time header cells -->
				{#each timeColumns as col, i (i)}
					<div
						class="flex-shrink-0 border-r px-1 text-center text-xs leading-none font-medium {isToday(col, granularity)
							? (isDark.value ? 'border-gray-700 bg-blue-900/40 text-blue-400' : 'border-gray-100 bg-blue-50 text-blue-600')
							: (isDark.value ? 'border-gray-700 text-gray-400' : 'border-gray-100 text-gray-500')}"
						style="width: {cellWidth}px; line-height: {HEADER_HEIGHT}px"
					>
						{formatColHeader(col, granularity)}
					</div>
				{/each}
			</div>

			<!-- Data rows -->
			{#each groupedRows as group (group.key)}
				<!-- Group header (only when grouped) -->
				{#if groupByColId && groupByCol}
					<div
						class="sticky left-0 z-10 flex items-center gap-2 border-b px-3 {isDark.value ? 'border-gray-700 bg-gray-800' : 'border-gray-200 bg-gray-50'}"
						style="height: {ROW_HEIGHT - 4}px; width: {SIDEBAR_WIDTH + totalGridWidth}px"
					>
						{#if groupByCol.type === 'select' && group.key}
							{@const choiceColor = getChoiceColor(groupByCol, group.key)}
							<span
								class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium {choiceColor.bg} {choiceColor.text} {choiceColor.border}"
							>
								{group.label}
							</span>
						{:else}
							<span class="text-xs font-semibold {isDark.value ? 'text-gray-300' : 'text-gray-600'}">{group.label}</span>
						{/if}
						<span class="text-xs text-gray-400">{group.rows.length}</span>
					</div>
				{/if}

				<!-- Rows -->
				{#each group.rows as { row, startDate: rawStart, endDate: rawEnd } (row.row_id)}
					{@const { startDate, endDate } = getEffectiveDates(row, rawStart, rawEnd)}
					<div
						class="flex border-b {isDark.value ? 'border-gray-700 hover:bg-gray-800/80' : 'border-gray-100 hover:bg-gray-50'}"
						style="height: {ROW_HEIGHT}px"
					>
						<!-- Sidebar label -->
						<div
							class="sticky left-0 z-10 flex flex-shrink-0 items-center border-r px-2 {isDark.value ? 'border-gray-700 bg-gray-900 hover:bg-gray-800' : 'border-gray-200 bg-white hover:bg-gray-50'}"
							style="width: {SIDEBAR_WIDTH}px"
						>
							<span class="truncate text-xs {isDark.value ? 'text-gray-300' : 'text-gray-700'}">
								{labelCol ? String(row.row_data[labelCol.column_id] ?? '') || '—' : '—'}
							</span>
						</div>

						<!-- Bar area -->
						<div
							class="relative flex-shrink-0"
							style="width: {totalGridWidth}px; height: {ROW_HEIGHT}px"
						>
							<!-- Column grid lines -->
							{#each timeColumns as col, i (i)}
								<div
									class="absolute top-0 bottom-0 border-r {isToday(col, granularity)
										? (isDark.value ? 'border-blue-700 bg-blue-900/20' : 'border-blue-200 bg-blue-50/40')
										: (isDark.value ? 'border-gray-700' : 'border-gray-100')}"
									style="left: {i * cellWidth}px; width: {cellWidth}px"
								></div>
							{/each}

							<!-- Bar -->
							<div
								class="absolute top-2 bottom-2 flex cursor-pointer items-center overflow-hidden rounded text-xs font-medium shadow-sm {getBarColorClasses(
									row
								)} {dragState?.rowId === row.row_id ? 'opacity-80' : ''}"
								style="left: {getBarLeft(startDate)}px; width: {getBarWidth(startDate, endDate)}px"
								title="{labelCol
									? String(row.row_data[labelCol.column_id] ?? '')
									: ''} ({formatDate(String(startDate.toISOString().slice(0, 10)))} → {formatDate(
									String(endDate.toISOString().slice(0, 10))
								)})"
								role="button"
								tabindex="0"
								onclick={() => onOpenExpand(row)}
								onkeydown={(e) => e.key === 'Enter' && onOpenExpand(row)}
							>
								<!-- Left resize handle -->
								{#if startColId}
									<button
										class="absolute top-0 bottom-0 left-0 w-2 cursor-col-resize hover:bg-black/10 focus:outline-none"
										onmousedown={(e) => onResizeMouseDown(e, row, 'start')}
										aria-label="Resize start date"
									></button>
								{/if}
								<span class="flex-1 truncate px-2">
									{labelCol ? String(row.row_data[labelCol.column_id] ?? '') || '—' : '—'}
								</span>
								<!-- Right resize handle -->
								{#if endColId}
									<button
										class="absolute top-0 right-0 bottom-0 w-2 cursor-col-resize hover:bg-black/10 focus:outline-none"
										onmousedown={(e) => onResizeMouseDown(e, row, 'end')}
										aria-label="Resize end date"
									></button>
								{/if}
							</div>
						</div>
					</div>
				{/each}
			{/each}

			<!-- Today indicator line (vertical) -->
			{#if todayX > 0 && todayX < totalGridWidth}
				<div
					class="pointer-events-none absolute top-0 bottom-0 z-10 w-0.5 bg-blue-500 opacity-60"
					style="left: {SIDEBAR_WIDTH + todayX}px"
				></div>
			{/if}
		</div>
	</div>
{/if}

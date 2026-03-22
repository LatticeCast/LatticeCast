<script lang="ts">
	import type { Column } from '$lib/types/table';
	import type { FilterCondition } from './table.utils';
	import { SvelteSet } from 'svelte/reactivity';

	let { columns, sortConfig, groupConfig, hiddenCols, filterConditions, showFilterPanel, searchQuery,
		onSortChange, onGroupChange, onToggleHideCol, onClearHiddenCols,
		onFilterConditionsChange, onShowFilterPanelChange, onSearchQueryChange,
		onExportTemplate, onShowImportTemplate, onExportCSV, onExportJSON, onImportFile,
		onAddFilterCondition, onRemoveFilterCondition, onClearAllFilters
	}: {
		columns: Column[];
		sortConfig: { colId: string; dir: 'asc' | 'desc' } | null;
		groupConfig: { colId: string; granularity?: 'month' | 'day' } | null;
		hiddenCols: SvelteSet<string>;
		filterConditions: FilterCondition[];
		showFilterPanel: boolean;
		searchQuery: string;
		onSortChange: (config: { colId: string; dir: 'asc' | 'desc' } | null) => void;
		onGroupChange: (config: { colId: string; granularity?: 'month' | 'day' } | null) => void;
		onToggleHideCol: (colId: string) => void;
		onClearHiddenCols: () => void;
		onFilterConditionsChange: (conditions: FilterCondition[]) => void;
		onShowFilterPanelChange: (show: boolean) => void;
		onSearchQueryChange: (query: string) => void;
		onExportTemplate: () => void;
		onShowImportTemplate: () => void;
		onExportCSV: () => void;
		onExportJSON: () => void;
		onImportFile: (e: Event) => void;
		onAddFilterCondition: () => void;
		onRemoveFilterCondition: (id: string) => void;
		onClearAllFilters: () => void;
	} = $props();

	let showSortMenu = $state(false);
	let showGroupMenu = $state(false);
	let showHideMenu = $state(false);
	let showExportMenu = $state(false);

	const sortedCols = $derived([...columns].sort((a, b) => a.position - b.position));

	const btnBase = 'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition';
	const btnActive = 'bg-blue-50 text-blue-600 font-medium';
	const btnInactive = 'text-gray-500 hover:bg-gray-100 hover:text-gray-700';
</script>

<!-- Toolbar -->
<div class="flex items-center gap-1 border-b border-gray-200 bg-white px-4 py-1.5">
	<!-- Sort -->
	<div class="relative">
		<button
			onclick={(e) => { e.stopPropagation(); showSortMenu = !showSortMenu; showGroupMenu = false; showHideMenu = false; }}
			class="{btnBase} {sortConfig ? btnActive : btnInactive}"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12" />
			</svg>
			Sort
			{#if sortConfig}
				<span class="flex h-4 w-4 items-center justify-center rounded-full bg-blue-500 text-xs font-bold text-white">1</span>
			{/if}
		</button>
		{#if showSortMenu}
			<div class="absolute top-full left-0 z-30 mt-1 min-w-[200px] rounded-xl border border-gray-200 bg-white py-1 shadow-xl" onclick={(e) => e.stopPropagation()} role="menu">
				<div class="px-3 py-1.5 text-xs font-semibold tracking-wide text-gray-400 uppercase">Sort by</div>
				{#each sortedCols as col (col.id)}
					<button
						class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50 {sortConfig?.colId === col.id ? 'font-semibold text-blue-600' : ''}"
						onclick={() => {
							if (sortConfig?.colId === col.id) {
								onSortChange({ colId: col.id, dir: sortConfig.dir === 'asc' ? 'desc' : 'asc' });
							} else {
								onSortChange({ colId: col.id, dir: 'asc' });
							}
							showSortMenu = false;
						}}
						role="menuitem"
					>
						{col.name}
						{#if sortConfig?.colId === col.id}
							<span class="ml-auto text-xs text-blue-500">{sortConfig.dir === 'asc' ? '↑ A→Z' : '↓ Z→A'}</span>
						{/if}
					</button>
				{/each}
				{#if sortConfig}
					<hr class="my-1 border-gray-100" />
					<button class="w-full px-3 py-1.5 text-left text-xs text-red-500 hover:bg-red-50" onclick={() => { onSortChange(null); showSortMenu = false; }} role="menuitem">Clear sort</button>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Group -->
	<div class="relative">
		<button
			onclick={(e) => { e.stopPropagation(); showGroupMenu = !showGroupMenu; showSortMenu = false; showHideMenu = false; }}
			class="{btnBase} {groupConfig ? btnActive : btnInactive}"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h8M4 18h8" />
			</svg>
			Group
			{#if groupConfig}
				<span class="flex h-4 w-4 items-center justify-center rounded-full bg-blue-500 text-xs font-bold text-white">1</span>
			{/if}
		</button>
		{#if showGroupMenu}
			<div class="absolute top-full left-0 z-30 mt-1 min-w-[200px] rounded-xl border border-gray-200 bg-white py-1 shadow-xl" onclick={(e) => e.stopPropagation()} role="menu">
				<div class="px-3 py-1.5 text-xs font-semibold tracking-wide text-gray-400 uppercase">Group by</div>
				{#each sortedCols.filter((c) => c.type === 'select' || c.type === 'date') as col (col.id)}
					{#if col.type === 'date'}
						<div class="px-3 py-1 text-xs font-medium text-gray-500">{col.name} <span class="text-gray-400">(date)</span></div>
						<button
							class="flex w-full items-center gap-2 px-5 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50 {groupConfig?.colId === col.id && groupConfig?.granularity === 'month' ? 'font-semibold text-blue-600' : ''}"
							onclick={() => { onGroupChange(groupConfig?.colId === col.id && groupConfig?.granularity === 'month' ? null : { colId: col.id, granularity: 'month' }); showGroupMenu = false; }}
							role="menuitem"
						>
							by month
							{#if groupConfig?.colId === col.id && groupConfig?.granularity === 'month'}
								<span class="ml-auto text-xs text-blue-500">✓</span>
							{/if}
						</button>
						<button
							class="flex w-full items-center gap-2 px-5 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50 {groupConfig?.colId === col.id && groupConfig?.granularity === 'day' ? 'font-semibold text-blue-600' : ''}"
							onclick={() => { onGroupChange(groupConfig?.colId === col.id && groupConfig?.granularity === 'day' ? null : { colId: col.id, granularity: 'day' }); showGroupMenu = false; }}
							role="menuitem"
						>
							by day
							{#if groupConfig?.colId === col.id && groupConfig?.granularity === 'day'}
								<span class="ml-auto text-xs text-blue-500">✓</span>
							{/if}
						</button>
					{:else}
						<button
							class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50 {groupConfig?.colId === col.id ? 'font-semibold text-blue-600' : ''}"
							onclick={() => { onGroupChange(groupConfig?.colId === col.id ? null : { colId: col.id }); showGroupMenu = false; }}
							role="menuitem"
						>
							{col.name}
							<span class="ml-1 text-xs text-gray-400">({col.type})</span>
							{#if groupConfig?.colId === col.id}
								<span class="ml-auto text-xs text-blue-500">✓</span>
							{/if}
						</button>
					{/if}
				{:else}
					<div class="px-3 py-2 text-xs text-gray-400">No select or date columns</div>
				{/each}
				{#if groupConfig}
					<hr class="my-1 border-gray-100" />
					<button class="w-full px-3 py-1.5 text-left text-xs text-red-500 hover:bg-red-50" onclick={() => { onGroupChange(null); showGroupMenu = false; }} role="menuitem">Clear group</button>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Hide Fields -->
	<div class="relative">
		<button
			onclick={(e) => { e.stopPropagation(); showHideMenu = !showHideMenu; showSortMenu = false; showGroupMenu = false; }}
			class="{btnBase} {hiddenCols.size > 0 ? btnActive : btnInactive}"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
			</svg>
			Hide Fields
			{#if hiddenCols.size > 0}
				<span class="flex h-4 w-4 items-center justify-center rounded-full bg-blue-500 text-xs font-bold text-white">{hiddenCols.size}</span>
			{/if}
		</button>
		{#if showHideMenu}
			<div class="absolute top-full left-0 z-30 mt-1 min-w-[200px] rounded-xl border border-gray-200 bg-white py-1 shadow-xl" onclick={(e) => e.stopPropagation()} role="menu">
				<div class="px-3 py-1.5 text-xs font-semibold tracking-wide text-gray-400 uppercase">Toggle columns</div>
				{#each sortedCols as col (col.id)}
					<label class="flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-gray-50">
						<input type="checkbox" checked={!hiddenCols.has(col.id)} onchange={() => onToggleHideCol(col.id)} class="accent-blue-500" />
						<span class="text-sm text-gray-700">{col.name}</span>
					</label>
				{/each}
				{#if hiddenCols.size > 0}
					<hr class="my-1 border-gray-100" />
					<button class="w-full px-3 py-1.5 text-left text-xs text-blue-500 hover:bg-blue-50" onclick={onClearHiddenCols} role="menuitem">Show all fields</button>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Filter -->
	<button
		onclick={() => onShowFilterPanelChange(!showFilterPanel)}
		class="{btnBase} {filterConditions.length > 0 ? btnActive : btnInactive}"
	>
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z" />
		</svg>
		Filter
		{#if filterConditions.length > 0}
			<span class="flex h-4 w-4 items-center justify-center rounded-full bg-blue-500 text-xs font-bold text-white">{filterConditions.length}</span>
		{/if}
	</button>

	<!-- Export Template -->
	<button onclick={onExportTemplate} class="{btnBase} {btnInactive}">
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
		</svg>
		Export Template
	</button>

	<!-- Import Template -->
	<button onclick={onShowImportTemplate} class="{btnBase} {btnInactive}">
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l4-4m0 0l4 4m-4-4v12" />
		</svg>
		Import Template
	</button>

	<!-- Export Data -->
	<div class="relative">
		<button
			onclick={(e) => { e.stopPropagation(); showExportMenu = !showExportMenu; showSortMenu = false; showGroupMenu = false; showHideMenu = false; }}
			class="{btnBase} {btnInactive}"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
			</svg>
			Export
		</button>
		{#if showExportMenu}
			<div class="absolute top-full left-0 z-30 mt-1 min-w-[150px] rounded-xl border border-gray-200 bg-white py-1 shadow-xl" onclick={(e) => e.stopPropagation()} role="menu">
				<button class="w-full px-3 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50" onclick={() => { onExportCSV(); showExportMenu = false; }} role="menuitem">Export CSV</button>
				<button class="w-full px-3 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50" onclick={() => { onExportJSON(); showExportMenu = false; }} role="menuitem">Export JSON</button>
			</div>
		{/if}
	</div>

	<!-- Import CSV -->
	<label class="{btnBase} {btnInactive} cursor-pointer">
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l4-4m0 0l4 4m-4-4v12" />
		</svg>
		Import CSV
		<input type="file" accept=".csv" class="hidden" onchange={onImportFile} />
	</label>

	<!-- Spacer -->
	<div class="flex-1"></div>

	<!-- Search -->
	<div class="relative flex items-center">
		<svg class="absolute left-2.5 h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0" />
		</svg>
		<input
			type="text"
			placeholder="Search..."
			value={searchQuery}
			oninput={(e) => onSearchQueryChange((e.currentTarget as HTMLInputElement).value)}
			class="rounded-lg border border-gray-200 bg-gray-50 py-1.5 pr-3 pl-8 text-sm text-gray-700 placeholder-gray-400 outline-none focus:border-blue-400 focus:bg-white {searchQuery ? 'w-48' : 'w-36'}"
		/>
		{#if searchQuery}
			<button onclick={() => onSearchQueryChange('')} class="absolute right-2 text-gray-400 hover:text-gray-600" aria-label="Clear search">×</button>
		{/if}
	</div>
</div>

<!-- Filter panel -->
{#if showFilterPanel}
	<div class="border-b border-gray-200 bg-gray-50 px-4 py-3">
		<div class="mb-2 flex items-center justify-between">
			<span class="text-xs font-semibold tracking-wide text-gray-500 uppercase">Filters (AND)</span>
			<div class="flex gap-3">
				{#if filterConditions.length > 0}
					<button onclick={onClearAllFilters} class="text-xs text-gray-400 hover:text-gray-600">Clear all</button>
				{/if}
				<button onclick={() => onShowFilterPanelChange(false)} class="text-xs text-gray-400 hover:text-gray-600" aria-label="Close filter panel">✕</button>
			</div>
		</div>
		{#each filterConditions as cond (cond.id)}
			<div class="mb-2 flex items-center gap-2">
				<select
					bind:value={cond.colId}
					class="rounded-lg border border-gray-200 bg-white px-2 py-1 text-sm text-gray-700 outline-none focus:border-blue-400"
				>
					{#each columns as col (col.id)}
						<option value={col.id}>{col.name}</option>
					{/each}
				</select>
				<select
					bind:value={cond.operator}
					class="rounded-lg border border-gray-200 bg-white px-2 py-1 text-sm text-gray-700 outline-none focus:border-blue-400"
				>
					<option value="contains">contains</option>
					<option value="equals">equals</option>
					<option value="is_empty">is empty</option>
					<option value="not_empty">is not empty</option>
				</select>
				{#if cond.operator !== 'is_empty' && cond.operator !== 'not_empty'}
					<input
						class="min-w-0 flex-1 rounded-lg border border-gray-200 bg-white px-2 py-1 text-sm text-gray-700 placeholder-gray-400 outline-none focus:border-blue-400"
						bind:value={cond.value}
						placeholder="Value…"
					/>
				{:else}
					<span class="flex-1"></span>
				{/if}
				<button onclick={() => onRemoveFilterCondition(cond.id)} class="shrink-0 rounded p-1 text-gray-400 hover:text-gray-600" aria-label="Remove condition">
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
		{/each}
		<button onclick={onAddFilterCondition} class="mt-1 text-sm text-gray-500 hover:text-gray-700">+ Add condition</button>
	</div>
{/if}

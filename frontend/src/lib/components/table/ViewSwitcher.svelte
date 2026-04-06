<script lang="ts">
	import type { ViewConfig } from '$lib/types/table';

	let {
		views,
		activeViewName,
		onViewChange,
		onAddView,
		onAddRow = () => {}
	}: {
		views: ViewConfig[];
		activeViewName: string;
		onViewChange: (view: ViewConfig) => void;
		onAddView: (type: string, name: string) => void;
		onAddRow?: () => void;
	} = $props();

	let showAddMenu = $state(false);

	const VIEW_TYPES = [
		{ type: 'table', label: 'Table' },
		{ type: 'kanban', label: 'Kanban' },
		{ type: 'timeline', label: 'Timeline' }
	];
</script>

<svelte:window
	onclick={() => {
		showAddMenu = false;
	}}
/>

<div class="flex items-center gap-0.5 overflow-x-auto border-b border-gray-200 bg-white px-4">
	{#each views as view (view.name)}
		<button
			onclick={() => onViewChange(view)}
			class="flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm transition {activeViewName ===
			view.name
				? 'border-blue-500 text-blue-600 font-medium'
				: 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}"
		>
			{#if view.type === 'table'}
				<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M3 10h18M3 14h18M10 3v18M14 3v18M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z"
					/>
				</svg>
			{:else if view.type === 'kanban'}
				<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2"
					/>
				</svg>
			{:else if view.type === 'timeline'}
				<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
					/>
				</svg>
			{/if}
			{view.name}
		</button>
	{/each}

	<!-- Spacer -->
	<div class="flex-1"></div>

	<!-- New Ticket button -->
	<button
		onclick={onAddRow}
		class="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-blue-700"
	>
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
		</svg>
		New Ticket
	</button>

	<!-- Add view button -->
	<div class="relative ml-1">
		<button
			onclick={(e) => {
				e.stopPropagation();
				showAddMenu = !showAddMenu;
			}}
			class="flex items-center gap-1 rounded-md px-2 py-1.5 text-sm text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
			aria-label="Add view"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
			</svg>
			<span class="text-xs">Add view</span>
		</button>
		{#if showAddMenu}
			<div
				class="absolute top-full left-0 z-30 mt-1 min-w-[160px] rounded-xl border border-gray-200 bg-white py-1 shadow-xl"
				onclick={(e) => e.stopPropagation()}
				role="menu"
			>
				<div class="px-3 py-1.5 text-xs font-semibold tracking-wide text-gray-400 uppercase">
					View type
				</div>
				{#each VIEW_TYPES as vt (vt.type)}
					<button
						class="w-full px-3 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50"
						onclick={() => {
							const existing = views.filter((v) => v.type === vt.type);
							const name =
								existing.length === 0 ? vt.label : `${vt.label} ${existing.length + 1}`;
							onAddView(vt.type, name);
							showAddMenu = false;
						}}
						role="menuitem"
					>
						{vt.label}
					</button>
				{/each}
			</div>
		{/if}
	</div>
</div>

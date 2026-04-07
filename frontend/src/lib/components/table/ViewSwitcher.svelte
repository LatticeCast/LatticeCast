<script lang="ts">
	import type { ViewConfig } from '$lib/types/table';

	let {
		views,
		activeViewName,
		onViewChange,
		onAddView
	}: {
		views: ViewConfig[];
		activeViewName: string;
		onViewChange: (view: ViewConfig) => void;
		onAddView: (type: string, name: string) => void;
	} = $props();

	let showAddPanel = $state(false);

	const VIEW_TYPES = [
		{
			type: 'table',
			label: 'Table',
			description: 'View and edit data in a spreadsheet grid'
		},
		{
			type: 'kanban',
			label: 'Kanban',
			description: 'Organize cards grouped by a select field'
		},
		{
			type: 'timeline',
			label: 'Timeline',
			description: 'Visualize data along a time axis'
		}
	];

	function addView(type: string, label: string) {
		const existing = views.filter((v) => v.type === type);
		const name = existing.length === 0 ? label : `${label} ${existing.length + 1}`;
		onAddView(type, name);
		showAddPanel = false;
	}
</script>

<svelte:window
	onkeydown={(e) => {
		if (e.key === 'Escape') showAddPanel = false;
	}}
	onclick={() => {
		showAddPanel = false;
	}}
/>

<!-- Outer wrapper: position:relative so the panel is clipped by it, not by overflow-x-auto -->
<div class="relative">
	<!-- Tab bar -->
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

		<!-- Add view button -->
		<button
			onclick={(e) => {
				e.stopPropagation();
				showAddPanel = !showAddPanel;
			}}
			class="flex items-center gap-1 rounded-md px-2 py-1.5 text-sm transition {showAddPanel
				? 'bg-blue-50 text-blue-600'
				: 'text-gray-400 hover:bg-gray-100 hover:text-gray-600'}"
			aria-label="Add view"
		>
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
			</svg>
			<span class="text-xs">Add view</span>
		</button>
	</div>

	<!-- Full-width panel overlay — sibling of tab bar so overflow-x-auto doesn't clip it -->
	{#if showAddPanel}
		<div
			class="absolute top-full left-0 right-0 z-40 border-b border-gray-200 bg-white shadow-lg"
			onclick={(e) => e.stopPropagation()}
			role="dialog"
			aria-label="Add a view"
		>
			<!-- Panel header -->
			<div class="flex items-center justify-between border-b border-gray-100 px-5 py-3">
				<span class="text-sm font-semibold text-gray-700">Add a view</span>
				<button
					onclick={() => (showAddPanel = false)}
					class="rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
					aria-label="Close"
				>
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M6 18L18 6M6 6l12 12"
						/>
					</svg>
				</button>
			</div>

			<!-- View type grid -->
			<div class="grid grid-cols-3 gap-3 p-4">
				{#each VIEW_TYPES as vt (vt.type)}
					<button
						onclick={() => addView(vt.type, vt.label)}
						class="flex flex-col items-start gap-2 rounded-lg border border-gray-200 bg-gray-50 p-4 text-left transition hover:border-blue-300 hover:bg-blue-50"
					>
						<!-- Icon -->
						<div class="rounded-md bg-white p-2 shadow-sm">
							{#if vt.type === 'table'}
								<svg
									class="h-5 w-5 text-blue-500"
									fill="none"
									stroke="currentColor"
									viewBox="0 0 24 24"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M3 10h18M3 14h18M10 3v18M14 3v18M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z"
									/>
								</svg>
							{:else if vt.type === 'kanban'}
								<svg
									class="h-5 w-5 text-purple-500"
									fill="none"
									stroke="currentColor"
									viewBox="0 0 24 24"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2"
									/>
								</svg>
							{:else if vt.type === 'timeline'}
								<svg
									class="h-5 w-5 text-green-500"
									fill="none"
									stroke="currentColor"
									viewBox="0 0 24 24"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
									/>
								</svg>
							{/if}
						</div>
						<div>
							<div class="text-sm font-medium text-gray-800">{vt.label}</div>
							<div class="mt-0.5 text-xs text-gray-500">{vt.description}</div>
						</div>
					</button>
				{/each}
			</div>
		</div>
	{/if}
</div>

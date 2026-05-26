<script lang="ts">
	import type { Column, Row } from '$lib/types/table';
	import { addSubgraph, renameSubgraph, removeSubgraph } from '$lib/stores/table_workflow.store';

	let {
		tableId,
		columns,
		rows,
		graphNames,
		activeGraph,
		onGraphChange
	}: {
		tableId: string;
		columns: Column[];
		rows: Row[];
		graphNames: string[];
		activeGraph: string;
		onGraphChange: (name: string) => void;
	} = $props();

	let menuOpen = $state(false);
	let menuRef: HTMLDivElement | undefined = $state();

	function close() {
		menuOpen = false;
	}

	async function handleAdd() {
		const name = prompt('Enter subgraph name:');
		if (!name) return;
		if (graphNames.includes(name)) {
			alert(`Subgraph "${name}" already exists.`);
			return;
		}
		close();
		await addSubgraph(tableId, columns, name);
		onGraphChange(name);
	}

	async function handleRename() {
		const newName = prompt(`Rename "${activeGraph}" to:`, activeGraph);
		if (!newName || newName === activeGraph) return;
		if (graphNames.includes(newName)) {
			alert(`Subgraph "${newName}" already exists.`);
			return;
		}
		close();
		await renameSubgraph(tableId, columns, rows, activeGraph, newName);
		onGraphChange(newName);
	}

	async function handleRemove() {
		if (!confirm(`Delete subgraph "${activeGraph}" and all its nodes?`)) return;
		close();
		await removeSubgraph(tableId, columns, rows, activeGraph);
		onGraphChange('root');
	}

	function handleClickOutside(e: MouseEvent) {
		if (menuRef && !menuRef.contains(e.target as Node)) close();
	}

	$effect(() => {
		if (menuOpen) {
			window.addEventListener('mousedown', handleClickOutside);
			return () => window.removeEventListener('mousedown', handleClickOutside);
		}
	});
</script>

<nav
	class="absolute top-2 left-2 z-10 flex items-center gap-1 rounded bg-white px-2 py-1 shadow"
	data-testid="workflow-graph-panel"
>
	<span class="text-xs font-medium text-gray-500">Graph:</span>
	<select
		class="rounded border border-gray-300 px-2 py-0.5 text-sm"
		data-testid="workflow-graph-selector"
		value={activeGraph}
		onchange={(e) => onGraphChange((e.target as HTMLSelectElement).value)}
	>
		{#each graphNames as name (name)}
			<option value={name}>{name}</option>
		{/each}
	</select>

	<div class="relative" bind:this={menuRef}>
		<button
			class="rounded border border-gray-300 px-2 py-0.5 text-sm hover:bg-gray-100"
			data-testid="workflow-subgraph-menu-btn"
			onclick={() => (menuOpen = !menuOpen)}
		>
			...
		</button>
		{#if menuOpen}
			<div
				class="absolute left-0 z-20 mt-1 min-w-[160px] rounded border border-gray-200 bg-white shadow-lg"
				data-testid="workflow-subgraph-menu"
			>
				<button
					class="block w-full px-3 py-1.5 text-left text-sm hover:bg-gray-100"
					onclick={handleAdd}
				>
					Add Subgraph
				</button>
				{#if activeGraph !== 'root'}
					<button
						class="block w-full px-3 py-1.5 text-left text-sm hover:bg-gray-100"
						onclick={handleRename}
					>
						Rename Subgraph
					</button>
					<button
						class="block w-full px-3 py-1.5 text-left text-sm text-red-600 hover:bg-red-50"
						onclick={handleRemove}
					>
						Remove Subgraph
					</button>
				{/if}
			</div>
		{/if}
	</div>
</nav>

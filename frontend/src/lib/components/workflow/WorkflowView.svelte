<script lang="ts">
	import { SvelteFlow, Controls, Background, MiniMap, type OnConnect } from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';
	import type { Node } from '@xyflow/svelte';
	import type { Row, Column, ViewConfig } from '$lib/types/table';
	import { updateRow } from '$lib/backend/tables';
	import WorkflowNode from './WorkflowNode.svelte';
	import {
		findColId,
		deriveGraphNames,
		filterGraphRows,
		deriveNodes,
		deriveEdges
	} from '$lib/stores/table_workflow.store';

	let {
		tableId,
		columns,
		rows,
		viewConfig,
		onOpenExpand
	}: {
		tableId: string;
		columns: Column[];
		rows: Row[];
		viewConfig: ViewConfig;
		onOpenExpand: (row: Row) => void;
	} = $props();

	const activeGraph = $state({ name: 'root' });

	const graphNames = $derived(deriveGraphNames(rows, columns));
	const graphRows = $derived(filterGraphRows(rows, columns, activeGraph.name));
	const nodes = $derived(deriveNodes(graphRows, columns));
	const edges = $derived(deriveEdges(graphRows, columns));

	const nodeTypes = { workflowNode: WorkflowNode };

	const handleConnect: OnConnect = (conn) => {
		if (!conn.source || !conn.target) return;
		const nextsColId = findColId(columns, 'nexts');
		const trueNextColId = findColId(columns, 'true_next');
		const falseNextColId = findColId(columns, 'false_next');
		const row = graphRows.find((r) => String(r.row_id) === conn.source);
		if (!row) return;

		const handle = conn.sourceHandle ?? 'next';
		const newData = { ...row.row_data };

		if (handle === 'true' && trueNextColId) {
			newData[trueNextColId] = conn.target;
		} else if (handle === 'false' && falseNextColId) {
			newData[falseNextColId] = conn.target;
		} else if (nextsColId) {
			let arr: string[] = [];
			try {
				arr = JSON.parse((newData[nextsColId] as string) || '[]');
			} catch {}
			if (!arr.includes(conn.target!)) arr.push(conn.target!);
			newData[nextsColId] = JSON.stringify(arr);
		}

		updateRow(tableId, row.row_id, { row_data: newData });
	};

	function handleNodeDragStop(node: Node) {
		const posXColId = findColId(columns, 'pos_x');
		const posYColId = findColId(columns, 'pos_y');
		const row = graphRows.find((r) => String(r.row_id) === node.id);
		if (!row || !posXColId || !posYColId) return;

		const newData = { ...row.row_data };
		newData[posXColId] = Math.round(node.position.x);
		newData[posYColId] = Math.round(node.position.y);
		updateRow(tableId, row.row_id, { row_data: newData });
	}
</script>

<div class="relative flex-1" data-testid="workflow-view">
	<div class="absolute top-2 left-2 z-10 flex items-center gap-2 rounded bg-white px-2 py-1 shadow">
		<span class="text-xs font-medium text-gray-500">Graph:</span>
		<select
			class="rounded border border-gray-300 px-2 py-0.5 text-sm"
			data-testid="workflow-graph-selector"
			bind:value={activeGraph.name}
		>
			{#each graphNames as name (name)}
				<option value={name}>{name}</option>
			{/each}
		</select>
	</div>

	<SvelteFlow
		{nodes}
		{edges}
		{nodeTypes}
		onconnect={handleConnect}
		onnodedragstop={(e) => {
			if (e.targetNode) handleNodeDragStop(e.targetNode);
		}}
		fitView
	>
		<Controls />
		<Background />
		<MiniMap />
	</SvelteFlow>
</div>

<style>
	div.relative {
		height: calc(100vh - 80px);
	}
</style>

<script lang="ts">
	import { get } from 'svelte/store';
	import { SvelteFlow, Controls, Background, MiniMap, type OnConnect } from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';
	import type { Row, Column, ViewConfig } from '$lib/types/table';
	import { updateRow } from '$lib/backend/tables';
	import WorkflowNode from './WorkflowNode.svelte';
	import WorkflowGraphPanel from './WorkflowGraphPanel.svelte';
	import WorkflowFlowCapture from './WorkflowFlowCapture.svelte';
	import {
		findColId,
		deriveGraphNames,
		filterGraphRows,
		deriveNodes,
		deriveEdges,
		addNode,
		deleteNode,
		removeEdgeByParts,
		parseEdgeId,
		screenToFlowStore
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

	// ── Edge connect ─────────────────────────────────────────────────────────
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

	// ── Node drag → persist position ─────────────────────────────────────────
	function handleNodeDragStop(e: {
		targetNode: { id: string; position: { x: number; y: number } } | null;
	}) {
		const node = e.targetNode;
		if (!node) return;
		const posXColId = findColId(columns, 'pos_x');
		const posYColId = findColId(columns, 'pos_y');
		const row = graphRows.find((r) => String(r.row_id) === node.id);
		if (!row || !posXColId || !posYColId) return;

		const newData = { ...row.row_data };
		newData[posXColId] = Math.round(node.position.x);
		newData[posYColId] = Math.round(node.position.y);
		updateRow(tableId, row.row_id, { row_data: newData });
	}

	// ── Context menu ─────────────────────────────────────────────────────────
	let ctxMenu = $state<{
		show: boolean;
		x: number;
		y: number;
		type: 'canvas' | 'node' | 'edge';
		elementId: string | null;
	}>({ show: false, x: 0, y: 0, type: 'canvas', elementId: null });

	function handleContextMenu(event: MouseEvent) {
		event.preventDefault();
		const el = (event.target as HTMLElement).closest('[data-id]');
		if (el) {
			const id = el.getAttribute('data-id');
			if (id) {
				const isEdge = id.startsWith('e-') || id.startsWith('xy-edge');
				ctxMenu = {
					show: true,
					x: event.clientX,
					y: event.clientY,
					type: isEdge ? 'edge' : 'node',
					elementId: id
				};
				return;
			}
		}
		ctxMenu = {
			show: true,
			x: event.clientX,
			y: event.clientY,
			type: 'canvas',
			elementId: null
		};
	}

	function closeMenu() {
		ctxMenu = { ...ctxMenu, show: false };
	}

	async function onAddNode() {
		const convert = get(screenToFlowStore);
		const pos = convert({ x: ctxMenu.x, y: ctxMenu.y });
		closeMenu();
		await addNode(tableId, columns, activeGraph.name, pos.x, pos.y);
	}

	function onExpandNode() {
		if (!ctxMenu.elementId) return;
		const row = graphRows.find((r) => String(r.row_id) === ctxMenu.elementId);
		closeMenu();
		if (row) onOpenExpand(row);
	}

	async function onDeleteNode() {
		if (!ctxMenu.elementId) return;
		const rowId = Number(ctxMenu.elementId);
		closeMenu();
		await deleteNode(tableId, rows, columns, rowId);
	}

	async function onDeleteEdge() {
		if (!ctxMenu.elementId) return;
		const parsed = parseEdgeId(ctxMenu.elementId, edges);
		closeMenu();
		if (parsed) {
			await removeEdgeByParts(tableId, rows, columns, parsed.source, parsed.handle, parsed.target);
		}
	}

	function handleWindowClick(e: MouseEvent) {
		if (ctxMenu.show) {
			const menuEl = document.querySelector('[data-testid="workflow-context-menu"]');
			if (menuEl && !menuEl.contains(e.target as Node)) closeMenu();
		}
	}

	$effect(() => {
		window.addEventListener('click', handleWindowClick);
		return () => window.removeEventListener('click', handleWindowClick);
	});
</script>

<div class="relative flex-1" data-testid="workflow-view">
	<WorkflowGraphPanel
		{tableId}
		{columns}
		{rows}
		{graphNames}
		activeGraph={activeGraph.name}
		onGraphChange={(name) => (activeGraph.name = name)}
	/>

	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="h-full w-full" oncontextmenu={handleContextMenu}>
		<SvelteFlow
			{nodes}
			{edges}
			{nodeTypes}
			onconnect={handleConnect}
			onnodedragstop={(e) => handleNodeDragStop(e)}
			fitView
		>
			<Controls />
			<Background />
			<MiniMap />
			<WorkflowFlowCapture />
		</SvelteFlow>

		{#if ctxMenu.show}
			<div
				class="fixed z-50 min-w-[140px] rounded border border-gray-200 bg-white py-1 shadow-lg"
				style="top: {ctxMenu.y}px; left: {ctxMenu.x}px;"
				data-testid="workflow-context-menu"
			>
				{#if ctxMenu.type === 'canvas'}
					<button
						class="block w-full px-3 py-1.5 text-left text-sm hover:bg-gray-100"
						data-testid="workflow-ctx-add-node"
						onclick={onAddNode}
					>
						Add Node
					</button>
				{:else if ctxMenu.type === 'node'}
					<button
						class="block w-full px-3 py-1.5 text-left text-sm hover:bg-gray-100"
						data-testid="workflow-ctx-expand"
						onclick={onExpandNode}
					>
						Expand Node
					</button>
					<button
						class="block w-full px-3 py-1.5 text-left text-sm text-red-600 hover:bg-red-50"
						data-testid="workflow-ctx-delete-node"
						onclick={onDeleteNode}
					>
						Delete Node
					</button>
				{:else if ctxMenu.type === 'edge'}
					<button
						class="block w-full px-3 py-1.5 text-left text-sm text-red-600 hover:bg-red-50"
						data-testid="workflow-ctx-delete-edge"
						onclick={onDeleteEdge}
					>
						Delete Edge
					</button>
				{/if}
			</div>
		{/if}
	</div>
</div>

<style>
	div.relative {
		height: calc(100vh - 80px);
	}
</style>

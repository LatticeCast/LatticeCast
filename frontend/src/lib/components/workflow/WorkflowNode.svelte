<script lang="ts">
	import { Handle, Position } from '@xyflow/svelte';
	import { NODE_COLORS } from '$lib/stores/table_workflow.store';

	let { data }: { id: string; data: { label: string; nodeType: string; description: string } } =
		$props();

	const color = $derived(NODE_COLORS[data.nodeType] ?? '#60a5fa');
	const isCondition = $derived(data.nodeType === 'CONDITION');
	const isStart = $derived(data.nodeType === 'START');
	const isTool = $derived(data.nodeType === 'TOOL');
</script>

<div class="workflow-node" data-testid="workflow-node-{data.label}" style="border-color: {color}; border-left: 4px solid {color};">
	<div class="node-header" style="background-color: {color}20;">
		<span class="node-type" style="color: {color};">{data.nodeType}</span>
		<span class="node-label">{data.label}</span>
	</div>
	{#if data.description}
		<div class="node-body">{data.description}</div>
	{/if}

	<!-- Target handle (left) — not on START or TOOL -->
	<Handle
		id="in"
		type="target"
		position={Position.Left}
		isConnectable={!isStart && !isTool}
		style="visibility: {!isStart && !isTool ? 'visible' : 'hidden'}; width: 10px; height: 10px; background: #6b7280;"
	/>

	<!-- Source handle (right) — not on CONDITION or TOOL -->
	{#if !isCondition && !isTool}
		<Handle
			id="next"
			type="source"
			position={Position.Right}
			style="width: 10px; height: 10px; background: #3b82f6;"
		/>
	{/if}

	<!-- Condition true/false handles -->
	{#if isCondition}
		<Handle
			id="true"
			type="source"
			position={Position.Right}
			style="top: 30%; width: 10px; height: 10px; background: #22c55e;"
		/>
		<Handle
			id="false"
			type="source"
			position={Position.Right}
			style="top: 70%; width: 10px; height: 10px; background: #ef4444;"
		/>
	{/if}
</div>

<style>
	.workflow-node {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 8px;
		min-width: 180px;
		max-width: 280px;
		font-family: inherit;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
	}
	.node-header {
		padding: 6px 10px;
		border-radius: 7px 7px 0 0;
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.node-type {
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.node-label {
		font-size: 13px;
		font-weight: 600;
		color: #1f2937;
	}
	.node-body {
		padding: 6px 10px;
		font-size: 11px;
		color: #6b7280;
		border-top: 1px solid #f3f4f6;
		white-space: pre-wrap;
		max-height: 80px;
		overflow-y: auto;
	}
</style>

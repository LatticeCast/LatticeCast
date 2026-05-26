<script lang="ts">
	import { useSvelteFlow } from '@xyflow/svelte';
	import { screenToFlowStore } from '$lib/stores/table_workflow.store';

	const { screenToFlowPosition } = useSvelteFlow();
	screenToFlowStore.set(screenToFlowPosition);
</script>

<script lang="ts">
	import * as echarts from 'echarts';
	import { onMount } from 'svelte';
	import { isDark } from '$lib/UI/theme.svelte';

	let { option }: { option: Record<string, unknown> } = $props();

	let container: HTMLDivElement;
	let chart: echarts.ECharts;

	onMount(() => {
		chart = echarts.init(container, isDark.value ? 'dark' : undefined);
		chart.setOption(option);
		const ro = new ResizeObserver(() => chart.resize());
		ro.observe(container);
		return () => {
			ro.disconnect();
			chart.dispose();
		};
	});

	$effect(() => {
		if (chart) chart.setOption(option, true);
	});
</script>

<div bind:this={container} class="h-full w-full"></div>

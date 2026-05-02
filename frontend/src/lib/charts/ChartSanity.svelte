<script lang="ts">
	import EChart from './EChart.svelte';

	const option = {
		dataset: [
			{
				source: [
					['Stage', 'Deals'],
					['Leads', 12],
					['Qualified', 7],
					['Won', 3]
				]
			}
		],
		xAxis: { type: 'category' },
		yAxis: { type: 'value' },
		series: [{ type: 'bar', encode: { x: 'Stage', y: 'Deals' } }]
	};
</script>

<div data-testid="chart-sanity" class="h-64 w-full max-w-sm">
	<EChart {option} />
</div>

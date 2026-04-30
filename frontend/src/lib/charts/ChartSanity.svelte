<script lang="ts">
	import {
		Chart,
		BarController,
		BarElement,
		CategoryScale,
		LinearScale,
		Tooltip,
		Legend
	} from 'chart.js';
	import { Bar } from 'svelte-chartjs';

	Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend);

	const data = {
		labels: ['Leads', 'Qualified', 'Won'],
		datasets: [
			{
				label: 'Deals',
				data: [12, 7, 3],
				backgroundColor: ['#6d28d9', '#7c3aed', '#8b5cf6']
			}
		]
	};

	const options = { responsive: true };
</script>

<div data-testid="chart-sanity" class="h-64 w-full max-w-sm">
	<Bar {data} {options} />
</div>

<!-- routes/[workspace_id]/+page.svelte — redirects to / -->

<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	onMount(() => {
		goto('/', { replaceState: true });
	});
</script>

<div class="min-h-screen bg-gray-50 flex items-center justify-center text-gray-400">
	Loading...
</div>

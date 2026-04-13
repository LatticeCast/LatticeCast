<!-- routes/[workspace_id]/+page.svelte — tables list filtered to this workspace -->

<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	onMount(() => {
		goto(`/?workspace=${$page.params.workspace_id}`, { replaceState: true });
	});
</script>

<div class="flex min-h-screen items-center justify-center bg-gray-50 text-gray-400">Loading...</div>

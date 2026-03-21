<!--routes/+page.svelte-->

<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { authStore } from '$lib/stores/auth.store';

	onMount(() => {
		if (!$authStore?.role) {
			goto('/login');
		} else {
			goto('/tables');
		}
	});
</script>

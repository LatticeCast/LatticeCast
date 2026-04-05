<!-- routes/tables/+page.svelte — redirects to /tables/[workspace_slug] -->

<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { authStore } from '$lib/stores/auth.store';
	import { fetchWorkspaces } from '$lib/backend/workspaces';

	function wsSlug(name: string): string {
		return name.toLowerCase().replace(/\s+/g, '-');
	}

	onMount(async () => {
		if (!$authStore?.role) {
			goto('/login');
			return;
		}
		try {
			const ws = await fetchWorkspaces();
			if (ws.length > 0) {
				goto(`/tables/${wsSlug(ws[0].workspace_name)}`, { replaceState: true });
			} else {
				// No workspaces — stay on this page, show empty state
			}
		} catch {
			// stay on page; error handled below
		}
	});
</script>

<div class="min-h-screen bg-gray-50 flex items-center justify-center text-gray-400">
	Loading workspaces...
</div>

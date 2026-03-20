<!-- lib/UI/Label.svelte -->

<script lang="ts">
	import type { Snippet } from 'svelte';

	export let text: string;
	export let children: Snippet;
</script>

<label class="flex flex-col gap-1 font-medium text-gray-800">
	{text}
	{@render children()}
</label>

<!-- Portal.svelte — teleports children to document.body to avoid stacking-context clipping -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();

	function teleport(node: HTMLElement) {
		document.body.appendChild(node);
		return {
			destroy() {
				node.remove();
			}
		};
	}
</script>

<div use:teleport style="display: contents">
	{@render children()}
</div>

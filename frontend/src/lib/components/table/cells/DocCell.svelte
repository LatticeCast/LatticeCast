<script lang="ts">
	let { onOpen }: { onOpen: () => void } = $props();
</script>

<button
	class="flex items-center gap-1.5 rounded px-2 py-1 text-xs transition hover:bg-blue-50 hover:text-blue-700"
	onclick={(e) => {
		e.stopPropagation();
		onOpen();
	}}
>
	<svg class="h-3.5 w-3.5 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
		<path
			fill-rule="evenodd"
			d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
			clip-rule="evenodd"
		/>
	</svg>
	<span class="text-blue-500">Open doc</span>
</button>

<script lang="ts">
	let { value, onToggle }: { value: unknown; onToggle: () => void } = $props();
</script>

<button
	class="relative inline-flex h-5 w-9 items-center rounded-full transition {value
		? 'bg-blue-500'
		: 'bg-gray-200'}"
	onclick={(e) => {
		e.stopPropagation();
		onToggle();
	}}
	aria-label="Toggle"
	role="switch"
	aria-checked={!!value}
>
	<span
		class="inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition {value
			? 'translate-x-4'
			: 'translate-x-1'}"
	></span>
</button>

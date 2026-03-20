<!-- lib/UI/Input.svelte -->
<script lang="ts">
	let {
		name = '',
		type = 'text',
		required = false,
		placeholder = '',
		value = $bindable(''),
		className = ''
	} = $props();
</script>

<input
	{name}
	{type}
	{required}
	{placeholder}
	bind:value
	class={`mt-1 w-[300px] rounded-md border border-gray-300 bg-white px-2 py-1 shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:outline-none ${className}`}
/>

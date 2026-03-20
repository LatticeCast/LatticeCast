<!-- src/lib/UI/Button.svelte -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	type ButtonProps = {
		variant?: 'primary' | 'secondary' | 'danger';
		type?: 'button' | 'submit' | 'reset';
		disabled?: boolean;
		className?: string;
		onclick?: (e: MouseEvent) => void;
		children: Snippet;
	};

	// Destructure all props
	let {
		variant = 'primary',
		type = 'button',
		disabled = false,
		className = '',
		onclick,
		children
	}: ButtonProps = $props();

	const base =
		'inline-flex items-center justify-center font-medium rounded-lg px-4 py-2 transition duration-150 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';

	const variants = {
		primary: 'bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500',
		secondary: 'bg-gray-100 text-gray-900 hover:bg-gray-200 focus:ring-gray-400',
		danger: 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500'
	};
</script>

<button {type} class={`${base} ${variants[variant]} ${className}`} {disabled} {onclick}>
	{@render children()}
</button>

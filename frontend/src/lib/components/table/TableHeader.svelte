<script lang="ts">
	let {
		tableName,
		loading,
		error,
		onBack,
		onAddColumn
	}: {
		tableName: string;
		loading: boolean;
		error: string | null;
		onBack: () => void;
		onAddColumn: () => void;
	} = $props();
</script>

<!-- Thin blue top bar -->
<div class="flex items-center gap-3 bg-blue-600 px-4 py-2.5">
	<button
		onclick={onBack}
		class="rounded-lg p-1.5 text-white/70 transition hover:bg-white/10 hover:text-white"
		aria-label="Back to tables"
	>
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
		</svg>
	</button>
	<h1 class="text-lg font-semibold text-white">
		{tableName}
	</h1>
	<div class="ml-auto">
		<button
			onclick={onAddColumn}
			disabled={loading}
			class="rounded-lg bg-white/15 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-white/25 disabled:opacity-50"
		>
			+ Column
		</button>
	</div>
</div>

{#if error}
	<div class="mx-4 mt-2 rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">{error}</div>
{/if}

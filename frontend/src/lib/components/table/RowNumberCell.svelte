<script lang="ts">
	import type { Row } from '$lib/types/table';
	import { isDark } from '$lib/UI/theme.svelte';

	let {
		row,
		hasDoc,
		onExpand
	}: {
		row: Row;
		hasDoc: boolean;
		onExpand: () => void;
	} = $props();
</script>

<td
	class="sticky left-0 z-20 border-r px-1 py-1 text-center {isDark.value
		? 'border-gray-700 bg-gray-800'
		: 'border-gray-100 bg-gray-50'}"
	style="width: 48px;"
>
	<button
		data-testid="grid-expand-row-{row.row_id}-btn"
		onclick={onExpand}
		class="group relative flex h-full w-full items-center justify-center rounded px-1 py-0.5 text-xs text-gray-400 hover:bg-gray-200 hover:text-gray-600"
		title="Expand row"
	>
		{row.row_id}
		{#if hasDoc}
			<svg
				class="absolute left-0.5 h-3 w-3 text-blue-400 group-hover:hidden"
				fill="currentColor"
				viewBox="0 0 20 20"
				aria-label="Has doc"
			>
				<path
					fill-rule="evenodd"
					d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"
					clip-rule="evenodd"
				/>
			</svg>
		{/if}
		<svg
			class="absolute right-0.5 hidden h-3 w-3 group-hover:block"
			fill="none"
			stroke="currentColor"
			viewBox="0 0 24 24"
			aria-hidden="true"
		>
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				stroke-width="2"
				d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
			/>
		</svg>
	</button>
</td>

<script lang="ts">
	let {
		rowId,
		isDeleting,
		onDelete
	}: {
		rowId: number;
		isDeleting: boolean;
		onDelete: () => void;
	} = $props();
</script>

<td class="px-1 py-1 text-center" style="width: 40px;">
	<button
		data-testid="grid-delete-row-{rowId}-btn"
		onclick={onDelete}
		disabled={isDeleting}
		class="rounded p-1 text-gray-300 transition hover:bg-red-50 hover:text-red-500 disabled:opacity-50"
		aria-label="Delete row"
		title="Delete row"
	>
		<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				stroke-width="2"
				d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
			/>
		</svg>
	</button>
</td>

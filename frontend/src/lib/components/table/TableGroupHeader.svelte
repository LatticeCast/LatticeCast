<script lang="ts">
	import type { Column } from '$lib/types/table';
	import { isDark } from '$lib/UI/theme.svelte';
	import { getChoiceColor } from './table.utils';

	let {
		groupKey,
		count,
		col,
		colspan,
		isCollapsed,
		onToggleCollapse
	}: {
		groupKey: string;
		count: number;
		col: Column;
		colspan: number;
		isCollapsed: boolean;
		onToggleCollapse: () => void;
	} = $props();
</script>

<tr class="border-b border-gray-200">
	<td {colspan} class="{isDark.value ? 'bg-gray-800' : 'bg-gray-50'} py-0.5">
		<div class="flex items-center gap-2 px-3 py-1">
			<button
				onclick={onToggleCollapse}
				class="rounded p-0.5 text-gray-400 hover:text-gray-600"
				aria-label={isCollapsed ? 'Expand group' : 'Collapse group'}
			>
				<svg
					class="h-4 w-4 transition {isCollapsed ? '-rotate-90' : ''}"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M19 9l-7 7-7-7"
					/>
				</svg>
			</button>
			{#if col.type === 'select' && groupKey !== '(empty)'}
				{@const color = getChoiceColor(col, groupKey)}
				<span
					class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium {color.bg} {color.text} {color.border}"
					>{groupKey}</span
				>
			{:else}
				<span class="text-sm font-medium {isDark.value ? 'text-gray-300' : 'text-gray-700'}"
					>{groupKey}</span
				>
			{/if}
			<span class="text-xs text-gray-400">{count} {count === 1 ? 'row' : 'rows'}</span>
		</div>
	</td>
</tr>

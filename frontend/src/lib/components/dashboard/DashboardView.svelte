<script lang="ts">
	import type { DashboardView as DashboardViewType } from '$lib/types/dashboard';
	import Block from './blocks/Block.svelte';
	import { T } from '$lib/UI/theme.svelte';
	import { updateView } from '$lib/backend/views';

	let { view, tableId }: { view: DashboardViewType & { view_id: number }; tableId: string } =
		$props();

	let layout = $derived(view.config?.layout ?? []);
	let blocks = $derived(view.config?.blocks ?? {});

	let editing = $state(false);
	let jsonText = $state('');
	let saveError = $state<string | null>(null);
	let saving = $state(false);

	function startEdit() {
		jsonText = JSON.stringify(view.config ?? { layout: [], blocks: {} }, null, 2);
		saveError = null;
		editing = true;
	}

	async function saveConfig() {
		saving = true;
		saveError = null;
		try {
			const parsed = JSON.parse(jsonText);
			await updateView(tableId, view.view_id, { config: parsed });
			editing = false;
		} catch (e) {
			saveError = e instanceof Error ? e.message : 'Invalid JSON';
		} finally {
			saving = false;
		}
	}
</script>

<div class="relative">
	<div class="absolute top-2 right-2 z-10 flex gap-2">
		{#if editing}
			<button
				onclick={saveConfig}
				disabled={saving}
				class="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
			>
				{saving ? 'Saving…' : 'Save'}
			</button>
			<button
				onclick={() => (editing = false)}
				class="rounded px-3 py-1 text-sm {T.inputBg} {T.body} {T.menuItemHover}"
			>
				Cancel
			</button>
		{:else}
			<button
				onclick={startEdit}
				class="rounded px-3 py-1 text-sm {T.inputBg} {T.body} {T.menuItemHover}"
			>
				Edit JSON
			</button>
		{/if}
	</div>

	{#if editing}
		<div class="p-4">
			{#if saveError}
				<div class="mb-2 rounded bg-red-100 px-3 py-2 text-sm text-red-700">{saveError}</div>
			{/if}
			<textarea
				bind:value={jsonText}
				class="h-[70vh] w-full rounded border font-mono text-sm {T.inputBorder} {T.editorBg} {T.heading}"
				spellcheck="false"
			></textarea>
		</div>
	{:else}
		<!--
		  V0.27.2: positions are honored via inline `grid-column` / `grid-row`.
		  Tailwind v4 purges dynamic class names like `col-span-{item.w}`, so we
		  cannot interpolate Tailwind classes from layout values at runtime.
		  Inline styles with explicit grid-column/grid-row lines are the fix.
		-->
		<div
			class="grid grid-cols-12 gap-4 p-4 {T.body}"
			style="grid-auto-rows: minmax(80px, auto);"
			data-testid="dashboard-grid"
		>
			{#each layout as item (item.id)}
				{@const block = blocks[item.id]}
				{#if block}
					<div
						class="{T.cardBg} flex flex-col overflow-hidden rounded-lg p-4 shadow-sm"
						style="grid-column: {item.x + 1} / span {item.w}; grid-row: {item.y +
							1} / span {item.h};"
						data-testid="dashboard-block-{item.id}"
					>
						<Block {block} {tableId} viewName={view.name} blockId={item.id} />
					</div>
				{/if}
			{/each}
		</div>
	{/if}
</div>

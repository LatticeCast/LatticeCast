<script lang="ts">
	let { show, headers, previewRows, newColumns, importing, error, onClose, onConfirm }: {
		show: boolean;
		headers: string[];
		previewRows: Record<string, string>[];
		newColumns: { name: string; type: string; values?: string[] }[];
		importing: boolean;
		error: string | null;
		onClose: () => void;
		onConfirm: () => void;
	} = $props();
</script>

{#if show}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
		onclick={onClose}
	>
		<div
			class="max-h-[80vh] w-full max-w-3xl overflow-auto rounded-2xl bg-white p-6 shadow-2xl"
			onclick={(e) => e.stopPropagation()}
			role="dialog"
			aria-modal="true"
			aria-label="Import CSV preview"
		>
			<h2 class="mb-4 text-lg font-bold text-gray-900">Import CSV Preview</h2>

			{#if newColumns.length > 0}
				<div class="mb-4 rounded-xl border border-blue-200 bg-blue-50 p-3">
					<p class="mb-1 text-sm font-semibold text-blue-700">New columns to create:</p>
					<ul class="space-y-0.5">
						{#each newColumns as nc (nc.name)}
							<li class="text-sm text-blue-600">
								<span class="font-medium">{nc.name}</span>
								<span class="text-blue-400"> ({nc.type})</span>
							</li>
						{/each}
					</ul>
				</div>
			{/if}

			<p class="mb-2 text-sm text-gray-500">
				{previewRows.length} row{previewRows.length === 1 ? '' : 's'} to import. Preview (first 5):
			</p>

			<div class="mb-4 overflow-x-auto rounded-xl border border-gray-200">
				<table class="w-full text-sm">
					<thead class="bg-gray-50">
						<tr>
							{#each headers as h (h)}
								<th class="border-b border-gray-200 px-3 py-2 text-left font-semibold text-gray-600">{h}</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each previewRows.slice(0, 5) as row, i (i)}
							<tr class={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
								{#each headers as h (h)}
									<td class="border-b border-gray-100 px-3 py-1.5 text-gray-700">{row[h] ?? ''}</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			{#if error}
				<div class="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>
			{/if}

			<div class="flex justify-end gap-3">
				<button
					onclick={onClose}
					class="rounded-xl border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
				>Cancel</button>
				<button
					onclick={onConfirm}
					disabled={importing}
					class="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
				>
					{importing ? 'Importing...' : `Import ${previewRows.length} rows`}
				</button>
			</div>
		</div>
	</div>
{/if}

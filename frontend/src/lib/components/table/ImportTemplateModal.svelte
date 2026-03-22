<script lang="ts">
	let {
		show,
		onClose,
		onImport
	}: {
		show: boolean;
		onClose: () => void;
		onImport: (file: File) => Promise<void>;
	} = $props();

	let importing = $state(false);
	let error = $state<string | null>(null);

	function handleClose() {
		error = null;
		onClose();
	}

	async function handleFile(e: Event) {
		const file = (e.currentTarget as HTMLInputElement).files?.[0];
		if (!file) return;
		importing = true;
		error = null;
		try {
			await onImport(file);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to import template';
		} finally {
			importing = false;
		}
	}
</script>

{#if show}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
		onclick={(e) => {
			if (e.target === e.currentTarget) handleClose();
		}}
		role="dialog"
		aria-modal="true"
		aria-label="Import template"
	>
		<div class="w-full max-w-sm rounded-3xl bg-white p-8 shadow-2xl">
			<h2 class="mb-2 text-xl font-bold text-gray-800">Import Template</h2>
			<p class="mb-6 text-sm text-gray-500">
				Select a <code class="rounded bg-gray-100 px-1 py-0.5 text-xs">template.json</code> file to restore
				column layout, types, and options. Existing rows will not be modified.
			</p>
			{#if error}
				<div class="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
			{/if}
			<div class="mb-6">
				<label class="mb-1 block text-sm font-medium text-gray-600" for="template-file"
					>Template JSON file</label
				>
				<input
					id="template-file"
					type="file"
					accept=".json,application/json"
					class="w-full rounded-xl border border-gray-200 px-4 py-2 text-sm text-gray-800 outline-none file:mr-3 file:rounded-lg file:border-0 file:bg-blue-50 file:px-3 file:py-1 file:text-sm file:font-medium file:text-blue-600 hover:file:bg-blue-100 focus:border-blue-500"
					onchange={handleFile}
					disabled={importing}
				/>
			</div>
			{#if importing}
				<p class="mb-4 text-center text-sm text-blue-500">Importing…</p>
			{/if}
			<button
				onclick={handleClose}
				disabled={importing}
				class="w-full rounded-2xl border border-gray-200 px-4 py-2 font-semibold text-gray-600 transition hover:bg-gray-50 disabled:opacity-50"
			>
				Cancel
			</button>
		</div>
	</div>
{/if}

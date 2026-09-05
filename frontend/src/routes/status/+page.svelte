<script lang="ts">
	const commit = import.meta.env.VITE_DEPLOY_COMMIT || 'unknown';
</script>

<svelte:head>
	<title>LatticeCast deployment status</title>
</svelte:head>

<main class="min-h-screen bg-gray-50 p-6 text-gray-900">
	<section class="mx-auto max-w-xl rounded-xl bg-white p-6 shadow-sm">
		<h1 class="text-xl font-semibold">LatticeCast frontend</h1>
		<p class="mt-3 text-sm text-gray-600">Deploy commit</p>
		<code class="mt-1 block break-all rounded bg-gray-100 px-3 py-2 text-sm">{commit}</code>
	</section>
</main>

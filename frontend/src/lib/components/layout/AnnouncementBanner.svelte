<!-- $lib/components/layout/AnnouncementBanner.svelte — read-only server announcement display -->
<script lang="ts">
	import { announcements } from '$lib/stores/announcement.store';

	const serverAnnouncement = $derived(
		$announcements.find(
			(announcement) => announcement.Type === 'server' || announcement.type === 'server'
		)
	);
	const title = $derived(readText(serverAnnouncement, 'Title', 'title'));
	const content = $derived(readText(serverAnnouncement, 'Description', 'description'));
	const visible = $derived(title !== null || content !== null);

	function readText(
		announcement: Record<string, unknown> | undefined,
		...keys: string[]
	): string | null {
		for (const key of keys) {
			const value = announcement?.[key];
			if (typeof value === 'string' && value.trim()) return value;
		}
		return null;
	}
</script>

{#if visible}
	<aside
		data-testid="announcement-banner"
		role="status"
		aria-live="polite"
		class="border-b border-blue-200 bg-blue-50 px-4 py-2 text-sm text-blue-950 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-100"
	>
		<div class="mx-auto flex max-w-7xl items-start gap-2">
			<svg
				class="mt-0.5 h-4 w-4 shrink-0 text-blue-600 dark:text-blue-300"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
				aria-hidden="true"
			>
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
			</svg>
			<div class="min-w-0">
				{#if title}
					<p class="font-medium">{title}</p>
				{/if}
				{#if content}
					<p class:mt-1={title !== null} class="whitespace-pre-wrap text-blue-800 dark:text-blue-200">
						{content}
					</p>
				{/if}
			</div>
		</div>
	</aside>
{/if}

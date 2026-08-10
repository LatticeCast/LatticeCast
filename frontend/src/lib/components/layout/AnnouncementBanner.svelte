<!-- $lib/components/layout/AnnouncementBanner.svelte — top-right announcement display -->
<script lang="ts">
	import { announcements } from '$lib/stores/announcement.store';

	let open = $state(false);

	const announcementItems = $derived.by(() =>
		$announcements
			.map((announcement, index) => ({
				id:
					readText(announcement, 'updated_at', 'created_at', 'updatedAt', 'createdAt') ??
					readText(announcement, 'title', 'Title') ??
					String(index),
				title: readText(announcement, 'Title', 'title'),
				content: readText(announcement, 'Description', 'description'),
				time: readText(announcement, 'updated_at', 'created_at', 'updatedAt', 'createdAt'),
				type: readText(announcement, 'Type', 'type')
			}))
			.filter((announcement) => announcement.title !== null || announcement.content !== null)
	);

	const hasAnnouncement = $derived(announcementItems.length > 0);

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

<div class="relative">
	<button
		data-testid="announcement-banner"
		type="button"
		aria-expanded={open}
		aria-label="公告"
		onclick={() => (open = !open)}
		class="flex max-w-[18rem] items-center gap-2 rounded-lg border border-white/20 bg-white/10 px-3 py-1.5 text-left text-xs text-white transition hover:bg-white/15"
	>
		<svg
			class="h-4 w-4 shrink-0 text-blue-100"
			fill="none"
			stroke="currentColor"
			viewBox="0 0 24 24"
			aria-hidden="true"
		>
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				stroke-width="2"
				d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
			/>
		</svg>
		<div class="min-w-0">
			<p class="truncate font-medium">公告</p>
		</div>
		{#if hasAnnouncement}
			<span class="shrink-0 rounded-full bg-amber-300 px-1.5 py-0.5 text-[10px] font-semibold text-slate-900">
				{announcementItems.length}
			</span>
		{/if}
	</button>

	{#if open}
		<div
			class="absolute top-full right-0 z-50 mt-2 w-96 max-w-[calc(100vw-1rem)] rounded-xl border border-blue-200 bg-white p-3 text-sm text-slate-900 shadow-xl"
		>
			{#if hasAnnouncement}
				<div class="max-h-96 space-y-3 overflow-y-auto pr-1">
					{#each announcementItems as announcement, index (announcement.id + ':' + index)}
						<div class={index > 0 ? 'border-t border-slate-200 pt-3' : ''}>
							<div class="mb-1 flex items-start gap-2">
								<svg
									class="mt-0.5 h-4 w-4 shrink-0 text-blue-600"
									fill="none"
									stroke="currentColor"
									viewBox="0 0 24 24"
									aria-hidden="true"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										stroke-width="2"
										d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
									/>
								</svg>
								<div class="min-w-0 flex-1">
									<div class="flex items-center gap-2">
										{#if announcement.title}
											<p class="font-semibold text-slate-950">{announcement.title}</p>
										{/if}
										{#if announcement.type}
											<span class="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium uppercase text-slate-600">
												{announcement.type}
											</span>
										{/if}
									</div>
									{#if announcement.time}
										<p class="mt-0.5 text-xs text-slate-500">{announcement.time}</p>
									{/if}
								</div>
							</div>
							{#if announcement.content}
								<p class="whitespace-pre-wrap text-slate-700">{announcement.content}</p>
							{/if}
						</div>
					{/each}
				</div>
			{:else}
				<p class="text-slate-500">目前沒有公告</p>
			{/if}
		</div>
	{/if}
</div>

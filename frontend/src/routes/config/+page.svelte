<!-- routes/config/+page.svelte -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { settingsStore, type SpeechLang } from '$lib/stores/settings.store';
	import { T } from '$lib/UI/theme.svelte';

	const languages: { value: SpeechLang; label: string; flag: string }[] = [
		{ value: 'zh-TW', label: '繁體中文', flag: '🇹🇼' },
		{ value: 'en-US', label: 'English', flag: '🇺🇸' },
		{ value: 'ja-JP', label: '日本語', flag: '🇯🇵' }
	];

	const intervalOptions = [1, 5, 15, 30, 60];

	function selectLang(lang: SpeechLang) {
		$settingsStore.speechLang = lang;
	}

	function goBack() {
		goto('/');
	}
</script>

<div class="{T.settingsHeroBg} min-h-screen p-4">
	<div class="mx-auto max-w-md">
		<div class="mb-6 flex items-center justify-between pt-8">
			<button
				onclick={goBack}
				class="flex items-center gap-2 rounded-xl bg-white/20 px-4 py-2 text-white backdrop-blur-sm transition-all hover:bg-white/30"
			>
				← Back
			</button>
			<h1 class="text-2xl font-bold text-white">Settings</h1>
			<div class="w-20"></div>
		</div>

		<!-- Speech Language -->
		<div class="mb-4 rounded-3xl {T.cardBg} p-6 shadow-2xl">
			<h2 class="mb-2 text-xl font-bold {T.heading}">Speech Language</h2>
			<p class="mb-4 text-sm {T.muted}">Select the language for voice input</p>

			<div class="space-y-2">
				{#each languages as lang (lang.value)}
					<button
						onclick={() => selectLang(lang.value)}
						class="flex w-full items-center justify-between rounded-2xl border-2 px-4 py-3 transition-all
							{$settingsStore.speechLang === lang.value
							? `${T.selectedBorder} ${T.selectedBg}`
							: `border-transparent ${T.inputBg} hover:border-blue-200`}"
					>
						<div class="flex items-center gap-3">
							<span class="text-2xl">{lang.flag}</span>
							<span class="font-medium {T.body}">{lang.label}</span>
						</div>
						{#if $settingsStore.speechLang === lang.value}
							<span class="text-xl text-blue-500">✓</span>
						{/if}
					</button>
				{/each}
			</div>
		</div>

		<!-- Dark Mode -->
		<div class="mb-4 rounded-3xl {T.cardBg} p-6 shadow-2xl">
			<h2 class="mb-2 text-xl font-bold {T.heading}">Appearance</h2>
			<p class="mb-4 text-sm {T.muted}">Customize the look of the app</p>

			<button
				onclick={() => ($settingsStore.darkMode = !$settingsStore.darkMode)}
				class="flex w-full items-center justify-between rounded-2xl {T.inputBg} px-4 py-3"
			>
				<span class="font-medium {T.body}">Dark Mode</span>
				<div
					class="relative h-7 w-12 rounded-full transition-colors {$settingsStore.darkMode
						? 'bg-blue-500'
						: T.toggleTrackBg}"
				>
					<div
						class="absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition-transform {$settingsStore.darkMode
							? 'translate-x-5'
							: 'translate-x-0.5'}"
					></div>
				</div>
			</button>
		</div>

		<!-- Notification Reminders -->
		<div class="mb-4 rounded-3xl {T.cardBg} p-6 shadow-2xl">
			<h2 class="mb-2 text-xl font-bold {T.heading}">Notification Reminders</h2>
			<p class="mb-4 text-sm {T.muted}">Get periodic reminders to check in</p>

			<!-- Toggle -->
			<button
				onclick={() => ($settingsStore.notificationEnabled = !$settingsStore.notificationEnabled)}
				class="mb-4 flex w-full items-center justify-between rounded-2xl {T.inputBg} px-4 py-3"
			>
				<span class="font-medium {T.body}">Enable notifications</span>
				<div
					class="relative h-7 w-12 rounded-full transition-colors {$settingsStore.notificationEnabled
						? 'bg-blue-500'
						: T.toggleTrackBg}"
				>
					<div
						class="absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition-transform {$settingsStore.notificationEnabled
							? 'translate-x-5'
							: 'translate-x-0.5'}"
					></div>
				</div>
			</button>

			<!-- Interval picker -->
			{#if $settingsStore.notificationEnabled}
				<p class="mb-2 text-sm font-medium {T.muted}">Remind every</p>
				<div class="flex flex-wrap gap-2">
					{#each intervalOptions as mins (mins)}
						<button
							onclick={() => ($settingsStore.notificationIntervalMinutes = mins)}
							class="rounded-xl px-4 py-2 text-sm font-medium transition-all
								{$settingsStore.notificationIntervalMinutes === mins
								? 'bg-blue-500 text-white'
								: `${T.inputBg} ${T.body} ${T.hoverBg}`}"
						>
							{mins < 60 ? `${mins} min` : `${mins / 60} hr`}
						</button>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</div>

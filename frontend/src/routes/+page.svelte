<!--routes/+page.svelte-->

<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { authStore } from '$lib/stores/auth.store';
	import { settingsStore } from '$lib/stores/settings.store';
	import { loadJson, saveJson } from '$lib/backend/storage';

	const ENTRIES_FILE = 'entries.json';

	onMount(async () => {
		if (!$authStore?.role) {
			goto('/login');
			return;
		}

		// Load entries from storage
		const storedEntries = await loadJson<Entry[]>(ENTRIES_FILE);
		if (storedEntries) {
			entries = storedEntries;
		}
	});

	interface Duration {
		label: string;
		value: number;
		icon: string;
	}
	interface Emotion {
		emoji: string;
		label: string;
	}
	interface Entry {
		activity: string;
		timestamp: string; // ISO string for JSON serialization
		duration?: Duration;
		emotion?: Emotion;
		energy: number;
	}

	let screen = $state<'main' | 'duration' | 'emotion' | 'energy'>('main');
	let currentTime = $state(new Date());
	let entries = $state<Entry[]>([]);
	let activity = $state('');
	let isRecording = $state(false);
	let energy = $state(3);
	let currentEntry = $state<Entry | null>(null);

	let webRecognition: any = null;
	let speechStatus = $state<string | null>(null);

	$effect(() => {
		const timer = setInterval(() => (currentTime = new Date()), 1000);
		return () => clearInterval(timer);
	});

	const time = $derived({
		hour: currentTime.getHours() % 12 || 12,
		minute: currentTime.getMinutes().toString().padStart(2, '0'),
		ampm: currentTime.getHours() >= 12 ? 'PM' : 'AM'
	});

	const date = $derived({
		weekday: currentTime.toLocaleDateString('en-US', { weekday: 'long' }),
		month: currentTime.toLocaleDateString('en-US', { month: 'long' }),
		day: currentTime.getDate()
	});

	const durations: Duration[] = [
		{ label: '15 min', value: 15, icon: '⚡' },
		{ label: '30 min', value: 30, icon: '🕐' },
		{ label: '1 hour', value: 60, icon: '⏰' },
		{ label: '1h 30m', value: 90, icon: '🕑' },
		{ label: '2 hours', value: 120, icon: '🕒' }
	];

	const emotions: Emotion[] = [
		{ emoji: '😢', label: 'Awful' },
		{ emoji: '😔', label: 'Bad' },
		{ emoji: '😐', label: 'Okay' },
		{ emoji: '😊', label: 'Good' },
		{ emoji: '😄', label: 'Great' }
	];

	const energyLabels = [
		'',
		'Running on empty 😴',
		'Pretty low 🥱',
		'Doing okay 👍',
		'Feeling good! 💪',
		'Fully charged! ⚡'
	];

	// Web speech recognition
	async function startWebRecording() {
		try {
			const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
			if (!SR) {
				alert('Speech recognition not supported. Use Chrome or Edge.');
				isRecording = false;
				return;
			}
			webRecognition = new SR();
			webRecognition.lang = $settingsStore.speechLang;
			webRecognition.continuous = false;
			webRecognition.interimResults = true;

			webRecognition.onstart = () => {
				speechStatus = `Started (${$settingsStore.speechLang})`;
			};
			webRecognition.onaudiostart = () => {
				speechStatus = 'Listening...';
			};
			webRecognition.onspeechstart = () => {
				speechStatus = 'Speech detected';
			};
			webRecognition.onresult = (e: any) => {
				speechStatus = null;
				activity = Array.from(e.results)
					.map((r: any) => r[0].transcript)
					.join('');
			};
			webRecognition.onnomatch = () => {
				speechStatus = 'No match';
			};
			webRecognition.onerror = (e: any) => {
				console.error('Speech error:', e.error);
				speechStatus = `Error: ${e.error}`;
				isRecording = false;
			};
			webRecognition.onend = () => (isRecording = false);
			webRecognition.start();
		} catch (err) {
			console.error('Mic error:', err);
			isRecording = false;
		}
	}

	async function toggleRecording() {
		if (isRecording) {
			webRecognition?.stop();
			isRecording = false;
			return;
		}

		activity = '';
		isRecording = true;
		await startWebRecording();
	}

	function submitActivity() {
		if (!activity.trim()) return;
		currentEntry = { activity: activity.trim(), timestamp: new Date().toISOString(), energy: 3 };
		activity = '';
		screen = 'duration';
	}

	function selectDuration(dur: Duration) {
		if (currentEntry) currentEntry.duration = dur;
		screen = 'emotion';
	}

	function selectEmotion(emo: Emotion) {
		if (currentEntry) currentEntry.emotion = emo;
		energy = 3;
		screen = 'energy';
	}

	async function save() {
		if (currentEntry) {
			entries = [{ ...currentEntry, energy }, ...entries];
			await saveJson(ENTRIES_FILE, entries);
		}
		currentEntry = null;
		screen = 'main';
	}

	function barColor(level: number, i: number) {
		if (i >= level) return 'bg-gray-200';
		return level <= 1
			? 'bg-red-500'
			: level <= 2
				? 'bg-orange-500'
				: level <= 3
					? 'bg-yellow-500'
					: 'bg-green-500';
	}
</script>

{#if screen === 'main'}
	<div class="min-h-screen bg-linear-to-br from-violet-500 via-purple-500 to-fuchsia-500 p-4">
		<div class="mx-auto max-w-md">
			<div class="pt-8 pb-6 text-center">
				<div class="flex items-baseline justify-center text-white">
					<span class="text-8xl font-thin tracking-tight">{time.hour}</span>
					<span class="animate-pulse text-8xl font-thin">:</span>
					<span class="text-8xl font-thin tracking-tight">{time.minute}</span>
					<span class="ml-2 text-2xl font-light opacity-80">{time.ampm}</span>
				</div>
				<p class="mt-2 text-lg text-white/80">{date.weekday}, {date.month} {date.day}</p>
			</div>

			<div class="mb-6 rounded-3xl bg-white p-6 shadow-2xl">
				<h2 class="mb-6 text-center text-2xl font-bold text-gray-800">What's happening? 🌟</h2>
				<textarea
					bind:value={activity}
					data-testid="activity-input"
					placeholder="Type or tap the mic to speak..."
					rows="3"
					class="mb-4 w-full resize-none rounded-2xl border-2 border-gray-100 bg-gray-50 p-4 text-gray-800 placeholder-gray-400 focus:border-purple-400 focus:outline-none"
				></textarea>

				{#if isRecording}
					<div class="mb-4 flex items-center justify-center gap-2 py-2">
						<div class="flex gap-1">
							<!-- eslint-disable-next-line @typescript-eslint/no-unused-vars -->
							{#each { length: 5 } as _unused, i (i)}<div
									class="w-1 animate-bounce rounded-full bg-red-500"
									style:height="{12 + i * 4}px"
									style:animation-delay="{i * 0.1}s"
								/>{/each}
						</div>
						<span class="ml-2 font-medium text-red-500">Recording...</span>
					</div>
				{/if}

				{#if speechStatus}
					<div class="mb-4 rounded-xl bg-amber-100 p-2 text-center text-sm text-amber-700">
						{speechStatus}
					</div>
				{/if}

				<div class="flex gap-3">
					<button
						onclick={toggleRecording}
						data-testid="btn-speak"
						class="flex flex-1 items-center justify-center gap-2 rounded-2xl py-4 font-semibold transition-all
              {isRecording
							? 'bg-red-500 text-white'
							: 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
					>
						{#if isRecording}<span class="h-4 w-4 rounded-sm bg-white"></span>Stop{:else}🎤 Speak{/if}
					</button>
					<button
						onclick={submitActivity}
						data-testid="btn-continue"
						disabled={!activity.trim()}
						class="flex-1 rounded-2xl bg-linear-to-r from-violet-500 to-fuchsia-500 py-4 font-semibold text-white transition-all hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-40"
					>
						Continue →
					</button>
				</div>
			</div>

			{#if entries.length}
				<div class="rounded-3xl bg-white/20 p-4 backdrop-blur-sm">
					<h3 class="mb-3 font-semibold text-white">Today's Log</h3>
					<div class="space-y-2">
						{#each entries.slice(0, 3) as entry (entry.timestamp)}
							<div class="flex items-center gap-3 rounded-xl bg-white/90 p-3">
								<span class="text-2xl">{entry.emotion?.emoji}</span>
								<div class="min-w-0 flex-1">
									<p class="truncate font-medium text-gray-800">{entry.activity}</p>
									<p class="text-sm text-gray-500">
										{new Date(entry.timestamp).toLocaleTimeString('en-US', {
											hour: 'numeric',
											minute: '2-digit'
										})} • {entry.duration?.label}
									</p>
								</div>
								<div class="text-sm text-gray-500">🔋{entry.energy}</div>
							</div>
						{/each}
					</div>
				</div>
			{:else}
				<p class="py-4 text-center text-white/60">Your activity log is empty. Start tracking!</p>
			{/if}
		</div>
	</div>
{:else if screen === 'duration'}
	<div
		class="flex min-h-screen items-center bg-linear-to-br from-violet-500 via-purple-500 to-fuchsia-500 p-4"
	>
		<div class="mx-auto w-full max-w-md">
			<div class="rounded-3xl bg-white p-8 shadow-2xl">
				<h2 class="mb-2 text-center text-2xl font-bold text-gray-800">How long? ⏱️</h2>
				<p class="mb-8 truncate px-4 text-center text-gray-500">"{currentEntry?.activity}"</p>
				<div class="space-y-3">
					{#each durations as dur (dur.value)}
						<button
							onclick={() => selectDuration(dur)}
							data-testid="duration-{dur.value}"
							class="group flex w-full items-center justify-between rounded-2xl border-2 border-transparent bg-linear-to-r from-gray-50 to-gray-100 px-6 py-4 transition-all hover:border-purple-200 hover:from-violet-50 hover:to-fuchsia-50"
						>
							<span class="text-2xl">{dur.icon}</span>
							<span class="text-lg font-semibold text-gray-800">{dur.label}</span>
							<span class="text-gray-400 transition-colors group-hover:text-purple-500">→</span>
						</button>
					{/each}
				</div>
			</div>
		</div>
	</div>
{:else if screen === 'emotion'}
	<div
		class="flex min-h-screen items-center bg-linear-to-br from-violet-500 via-purple-500 to-fuchsia-500 p-4"
	>
		<div class="mx-auto w-full max-w-md">
			<div class="rounded-3xl bg-white p-8 shadow-2xl">
				<h2 class="mb-2 text-center text-2xl font-bold text-gray-800">How do you feel? 💭</h2>
				<p class="mb-8 text-center text-gray-500">Tap your current mood</p>
				<div class="mb-4 flex justify-center gap-2">
					{#each emotions as emo (emo.label)}
						<button
							onclick={() => selectEmotion(emo)}
							data-testid="emotion-{emo.label.toLowerCase()}"
							class="flex flex-col items-center rounded-2xl p-3 transition-all hover:scale-110 hover:bg-gray-50 active:scale-95"
						>
							<span class="mb-2 text-5xl">{emo.emoji}</span>
							<span class="text-xs font-medium text-gray-500">{emo.label}</span>
						</button>
					{/each}
				</div>
			</div>
		</div>
	</div>
{:else if screen === 'energy'}
	<div
		class="flex min-h-screen items-center bg-linear-to-br from-violet-500 via-purple-500 to-fuchsia-500 p-4"
	>
		<div class="mx-auto w-full max-w-md">
			<div class="rounded-3xl bg-white p-8 shadow-2xl">
				<h2 class="mb-2 text-center text-2xl font-bold text-gray-800">Energy Level 🔋</h2>
				<p class="mb-8 text-center text-gray-500">How charged are you?</p>

				<div class="mb-8 flex justify-center">
					<div class="relative">
						<div
							class="flex h-56 w-32 flex-col-reverse gap-1 rounded-2xl border-4 border-gray-800 p-2"
						>
							{#each [1, 2, 3, 4, 5] as level (level)}
								<button
									onclick={() => (energy = level)}
									aria-label="Energy level {level}"
									class="flex-1 rounded-lg transition-all {barColor(
										energy,
										level - 1
									)} hover:opacity-80"
								/>
							{/each}
						</div>
						<div
							class="absolute -top-2 left-1/2 h-4 w-12 -translate-x-1/2 rounded-t-lg bg-gray-800"
						/>
					</div>
				</div>

				<div class="mb-8 px-4">
					<input
						type="range"
						min="1"
						max="5"
						bind:value={energy}
						class="h-2 w-full cursor-pointer appearance-none rounded-lg bg-gray-200 accent-purple-500"
					/>
					<div class="mt-2 flex justify-between text-sm text-gray-500">
						<span>Empty</span><span>Full</span>
					</div>
				</div>

				<div class="mb-6 text-center">
					<span class="text-4xl font-bold text-gray-800">{energy}</span><span class="text-gray-500"
						>/5</span
					>
					<p class="mt-1 text-gray-500">{energyLabels[energy]}</p>
				</div>

				<button
					onclick={save}
					data-testid="btn-save"
					class="w-full rounded-2xl bg-linear-to-r from-green-500 to-emerald-500 py-4 text-lg font-bold text-white transition-all hover:shadow-lg"
				>
					Save Entry ✓
				</button>
			</div>
		</div>
	</div>
{/if}

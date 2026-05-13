<script lang="ts">
	import { onMount } from 'svelte';
	import type { Column, ColumnChoice } from '$lib/types/table';
	import { getChoices, colorToStyle } from './table.utils';

	// vanilla-colorful registers a custom element via `customElements.define()`,
	// which only exists in the browser. Import client-side only.
	onMount(() => {
		import('vanilla-colorful/hex-color-picker.js');
	});

	const DEFAULT_HEX = '#5599e0'; // initial hex shown when opening picker on a legacy choice

	// Random hue, fixed saturation/lightness band → readable, vivid color.
	function randomChoiceColor(): string {
		const h = Math.floor(Math.random() * 360);
		const s = 60 + Math.random() * 15; // 60–75%
		const l = 55 + Math.random() * 10; // 55–65%
		return hslToHex(h, s, l);
	}

	function hslToHex(h: number, s: number, l: number): string {
		s /= 100;
		l /= 100;
		const c = (1 - Math.abs(2 * l - 1)) * s;
		const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
		const m = l - c / 2;
		let r = 0,
			g = 0,
			b = 0;
		if (h < 60) [r, g, b] = [c, x, 0];
		else if (h < 120) [r, g, b] = [x, c, 0];
		else if (h < 180) [r, g, b] = [0, c, x];
		else if (h < 240) [r, g, b] = [0, x, c];
		else if (h < 300) [r, g, b] = [x, 0, c];
		else [r, g, b] = [c, 0, x];
		const f = (n: number): string =>
			Math.round((n + m) * 255)
				.toString(16)
				.padStart(2, '0');
		return `#${f(r)}${f(g)}${f(b)}`;
	}

	let {
		col,
		onClose,
		onSave
	}: {
		col: Column;
		onClose: () => void;
		onSave: (colId: string, choices: ColumnChoice[]) => void;
	} = $props();

	let choices = $state<ColumnChoice[]>([...getChoices(col)]);
	let newValue = $state('');
	let draggedIdx = $state<number | null>(null);
	let pickerHex = $state<string | null>('#5599e0');

	let editingColorIdx = $state<number | null>(null);

	function openPicker(i: number) {
		const c = choices[i]?.color ?? '';
		// Hex passes straight through. hsl(...)/legacy classes default to the
		// first preset; user edits propagate via bind:hex.
		pickerHex = c && /^#[0-9a-f]{3,6}$/i.test(c) ? c : DEFAULT_HEX;
	}

	function closePicker() {
		if (editingColorIdx === null || !pickerHex) {
			editingColorIdx = null;
			return;
		}
		const idx = editingColorIdx;
		choices = choices.map((c, i) => (i === idx ? { ...c, color: pickerHex! } : c));
		editingColorIdx = null;
	}

	function onDragStart(i: number) {
		draggedIdx = i;
	}

	function onDragOver(e: DragEvent, i: number) {
		e.preventDefault();
		if (draggedIdx === null || draggedIdx === i) return;
		const updated = [...choices];
		const [item] = updated.splice(draggedIdx, 1);
		updated.splice(i, 0, item);
		choices = updated;
		draggedIdx = i;
	}

	function onDragEnd() {
		draggedIdx = null;
	}

	function addChoice() {
		const val = newValue.trim();
		if (!val || choices.some((c) => c.value === val)) return;
		choices = [...choices, { value: val, color: randomChoiceColor() }];
		newValue = '';
	}

	function togglePicker(i: number) {
		if (editingColorIdx === i) {
			closePicker();
		} else {
			openPicker(i);
			editingColorIdx = i;
		}
	}

	function removeChoice(value: string) {
		choices = choices.filter((c) => c.value !== value);
	}

	function handleSave() {
		onSave(col.column_id, choices);
		onClose();
	}
</script>

<div
	class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
	onclick={(e) => {
		if (e.target === e.currentTarget) onClose();
		closePicker();
	}}
	role="dialog"
	aria-modal="true"
	aria-label="Manage options"
>
	<div class="w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl">
		<h2 class="mb-1 text-lg font-bold text-gray-800">Manage Options</h2>
		<p class="mb-4 text-sm text-gray-500">
			{col.name} <span class="text-gray-400">({col.type})</span>
		</p>

		<!-- Existing choices -->
		<div class="mb-4 space-y-1.5">
			{#each choices as choice, i (choice.value)}
				{@const cs = colorToStyle(choice.color)}
				<div
					class="flex items-center gap-2 rounded transition-opacity {draggedIdx === i
						? 'opacity-40'
						: ''}"
					draggable="true"
					ondragstart={() => onDragStart(i)}
					ondragover={(e) => onDragOver(e, i)}
					ondragend={onDragEnd}
				>
					<!-- drag handle -->
					<svg
						class="h-3.5 w-3.5 shrink-0 cursor-grab text-gray-300 active:cursor-grabbing"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="M4 8h16M4 16h16"
						/>
					</svg>
					<!-- color swatch button -->
					<div class="relative shrink-0">
						<button
							data-testid="choice-color-btn-{i}"
							onclick={(e) => {
								e.stopPropagation();
								togglePicker(i);
							}}
							class="h-4 w-4 rounded-full border-2 {cs.cls} transition-transform hover:scale-110"
							style={cs.style}
							aria-label="Change color for {choice.value}"
						></button>
						{#if editingColorIdx === i}
							<div
								class="absolute top-6 left-0 z-20 rounded-xl border border-gray-200 bg-white p-3 shadow-xl"
								onclick={(e) => e.stopPropagation()}
								role="menu"
								aria-label="Pick a color"
								tabindex="-1"
							>
								<hex-color-picker
									color={pickerHex ?? '#5599e0'}
									oncolor-changed={(e: CustomEvent<{ value: string }>) =>
										(pickerHex = e.detail.value)}
									style="width: 200px; height: 200px;"
								></hex-color-picker>
								<div class="mt-2 flex items-center gap-2">
									<div
										class="h-5 w-5 shrink-0 rounded-full border border-gray-200"
										style="background-color: {pickerHex ?? '#5599e0'};"
									></div>
									<input
										data-testid="color-picker-hex"
										type="text"
										class="min-w-0 flex-1 rounded border border-gray-200 px-2 py-0.5 font-mono text-xs"
										value={pickerHex}
										onchange={(e) => {
											const v = (e.currentTarget as HTMLInputElement).value.trim();
											if (/^#[0-9a-f]{3,6}$/i.test(v)) pickerHex = v;
										}}
									/>
									<button
										data-testid="color-picker-apply"
										onclick={closePicker}
										class="rounded bg-blue-600 px-2 py-0.5 text-xs text-white hover:bg-blue-700"
										aria-label="Apply color">✓</button
									>
								</div>
							</div>
						{/if}
					</div>
					<span
						class="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium {cs.cls}"
						style={cs.style}
					>
						{choice.value}
					</span>
					<div class="flex-1"></div>
					<button
						onclick={() => removeChoice(choice.value)}
						class="rounded p-1 text-gray-300 hover:bg-red-50 hover:text-red-500"
						aria-label="Remove {choice.value}"
					>
						<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								stroke-width="2"
								d="M6 18L18 6M6 6l12 12"
							/>
						</svg>
					</button>
				</div>
			{:else}
				<p class="text-sm text-gray-400">No options yet.</p>
			{/each}
		</div>

		<!-- Add new choice -->
		<div class="mb-5 flex gap-2">
			<input
				class="min-w-0 flex-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-800 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
				bind:value={newValue}
				placeholder="New option..."
				onkeydown={(e) => {
					if (e.key === 'Enter') addChoice();
				}}
			/>
			<button
				onclick={addChoice}
				disabled={!newValue.trim()}
				class="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
			>
				Add
			</button>
		</div>

		<!-- Actions -->
		<div class="flex gap-3">
			<button
				onclick={onClose}
				class="flex-1 rounded-xl border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 transition hover:bg-gray-50"
			>
				Cancel
			</button>
			<button
				onclick={handleSave}
				class="flex-1 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700"
			>
				Save
			</button>
		</div>
	</div>
</div>

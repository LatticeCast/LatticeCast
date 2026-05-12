<script lang="ts">
	import type { Column, ColumnChoice } from '$lib/types/table';
	import { getChoices, colorToStyle } from './table.utils';

	const DEFAULT_COLORS = [
		'hsl(210 80% 60%)',
		'hsl(150 60% 55%)',
		'hsl(30 90% 60%)',
		'hsl(0 75% 60%)',
		'hsl(270 65% 65%)',
		'hsl(60 75% 55%)',
		'hsl(180 65% 55%)',
		'hsl(330 70% 65%)',
		'hsl(90 60% 55%)',
		'hsl(240 70% 65%)'
	];

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
	let colorPickerIdx = $state<number | null>(null);
	let pickerH = $state(210);
	let pickerS = $state(80);
	let pickerL = $state(60);
	const pickerHsl = $derived(`hsl(${pickerH} ${pickerS}% ${pickerL}%)`);
	const pickerHex = $derived(hslToHex(pickerH, pickerS, pickerL));

	function hslToHex(h: number, s: number, l: number): string {
		s /= 100;
		l /= 100;
		const a = s * Math.min(l, 1 - l);
		const f = (n: number): string => {
			const k = (n + h / 30) % 12;
			const c = l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
			return Math.round(255 * c)
				.toString(16)
				.padStart(2, '0');
		};
		return `#${f(0)}${f(8)}${f(4)}`;
	}

	function hexToHslValues(hex: string): { h: number; s: number; l: number } | null {
		const m = hex.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
		if (!m) return null;
		const hex6 =
			m[1].length === 3
				? m[1]
						.split('')
						.map((c) => c + c)
						.join('')
				: m[1];
		const r = parseInt(hex6.slice(0, 2), 16) / 255;
		const g = parseInt(hex6.slice(2, 4), 16) / 255;
		const b = parseInt(hex6.slice(4, 6), 16) / 255;
		const max = Math.max(r, g, b);
		const min = Math.min(r, g, b);
		const l = (max + min) / 2;
		if (max === min) return { h: 0, s: 0, l: Math.round(l * 100) };
		const d = max - min;
		const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
		let h = 0;
		if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
		else if (max === g) h = ((b - r) / d + 2) / 6;
		else h = ((r - g) / d + 4) / 6;
		return { h: Math.round(h * 360), s: Math.round(s * 100), l: Math.round(l * 100) };
	}

	function openPicker(i: number) {
		if (colorPickerIdx === i) {
			colorPickerIdx = null;
			return;
		}
		const c = choices[i]?.color ?? '';
		if (c && !c.startsWith('bg-')) {
			const hslMatch = c.match(/hsl\(\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*\)/i);
			if (hslMatch) {
				pickerH = Math.round(parseFloat(hslMatch[1]));
				pickerS = Math.round(parseFloat(hslMatch[2]));
				pickerL = Math.round(parseFloat(hslMatch[3]));
			} else {
				const parsed = hexToHslValues(c);
				if (parsed) {
					pickerH = parsed.h;
					pickerS = parsed.s;
					pickerL = Math.max(20, Math.min(80, parsed.l));
				}
			}
		}
		colorPickerIdx = i;
	}

	function onHexInput(e: Event) {
		const val = (e.currentTarget as HTMLInputElement).value.trim();
		const parsed = hexToHslValues(val);
		if (parsed) {
			pickerH = parsed.h;
			pickerS = parsed.s;
			pickerL = Math.max(20, Math.min(80, parsed.l));
		}
	}

	function setChoiceColor(i: number, color: string) {
		choices = choices.map((c, idx) => (idx === i ? { ...c, color } : c));
		colorPickerIdx = null;
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
		const colorIdx = choices.length % DEFAULT_COLORS.length;
		choices = [...choices, { value: val, color: DEFAULT_COLORS[colorIdx] }];
		newValue = '';
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
		colorPickerIdx = null;
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
								openPicker(i);
							}}
							class="h-4 w-4 rounded-full border-2 {cs.cls} transition-transform hover:scale-110"
							style={cs.style}
							aria-label="Change color for {choice.value}"
						></button>
						{#if colorPickerIdx === i}
							<div
								class="absolute top-6 left-0 z-10 w-52 rounded-xl border border-gray-200 bg-white p-3 shadow-xl"
								onclick={(e) => e.stopPropagation()}
								role="menu"
								aria-label="Pick a color"
							>
								<div class="mb-1 text-xs text-gray-400">Hue</div>
								<input
									data-testid="color-picker-hue"
									type="range"
									min="0"
									max="359"
									bind:value={pickerH}
									class="mb-2 w-full cursor-pointer"
									style="accent-color: {pickerHsl}"
								/>
								<div class="mb-1 text-xs text-gray-400">Saturation</div>
								<input
									data-testid="color-picker-sat"
									type="range"
									min="0"
									max="100"
									bind:value={pickerS}
									class="mb-2 w-full cursor-pointer"
									style="accent-color: {pickerHsl}"
								/>
								<div class="mb-1 text-xs text-gray-400">Lightness</div>
								<input
									data-testid="color-picker-light"
									type="range"
									min="20"
									max="80"
									bind:value={pickerL}
									class="mb-2 w-full cursor-pointer"
									style="accent-color: {pickerHsl}"
								/>
								<div class="flex items-center gap-2">
									<div
										class="h-6 w-6 shrink-0 rounded-full border border-gray-200"
										style="background-color: {pickerHsl}"
									></div>
									<input
										data-testid="color-picker-hex"
										type="text"
										class="min-w-0 flex-1 rounded border border-gray-200 px-2 py-0.5 font-mono text-xs"
										value={pickerHex}
										onchange={onHexInput}
									/>
									<button
										data-testid="color-picker-apply"
										onclick={() => setChoiceColor(i, pickerHsl)}
										class="rounded bg-blue-600 px-2 py-0.5 text-xs text-white hover:bg-blue-700"
										role="menuitem">✓</button
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

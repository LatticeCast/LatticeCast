<script lang="ts">
	let {
		value = 'hsl(210 80% 60%)',
		onApply,
		onCancel
	}: {
		value?: string;
		onApply?: (color: string) => void;
		onCancel?: () => void;
	} = $props();

	function hslToHsv(sl: number, ll: number): { sv: number; vv: number } {
		const s = sl / 100,
			l = ll / 100;
		const v = l + s * Math.min(l, 1 - l);
		return { sv: v === 0 ? 0 : 2 * (1 - l / v), vv: v };
	}

	function hsvToHsl(h: number, s: number, v: number): { h: number; s: number; l: number } {
		const l = v * (1 - s / 2);
		const sl = l === 0 || l === 1 ? 0 : (v - l) / Math.min(l, 1 - l);
		return { h, s: sl * 100, l: l * 100 };
	}

	function hslToHex(h: number, s: number, l: number): string {
		s /= 100;
		l /= 100;
		const a = s * Math.min(l, 1 - l);
		const f = (n: number) => {
			const k = (n + h / 30) % 12;
			const c = l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
			return Math.round(255 * c)
				.toString(16)
				.padStart(2, '0');
		};
		return `#${f(0)}${f(8)}${f(4)}`;
	}

	function parseColorToHsv(v: string): { hue: number; sv: number; vv: number } {
		const hslMatch = v.match(/hsl\(\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*\)/i);
		if (hslMatch) {
			const h = parseFloat(hslMatch[1]);
			return { hue: Math.round(h), ...hslToHsv(parseFloat(hslMatch[2]), parseFloat(hslMatch[3])) };
		}
		const hexMatch = v.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
		if (hexMatch) {
			const hex6 =
				hexMatch[1].length === 3
					? hexMatch[1]
							.split('')
							.map((c) => c + c)
							.join('')
					: hexMatch[1];
			const r = parseInt(hex6.slice(0, 2), 16) / 255;
			const g = parseInt(hex6.slice(2, 4), 16) / 255;
			const b = parseInt(hex6.slice(4, 6), 16) / 255;
			const max = Math.max(r, g, b),
				min = Math.min(r, g, b);
			const ll = (max + min) / 2;
			if (max === min) return { hue: 0, ...hslToHsv(0, ll * 100) };
			const d = max - min;
			const sl = ll > 0.5 ? d / (2 - max - min) : d / (max + min);
			let h = 0;
			if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
			else if (max === g) h = ((b - r) / d + 2) / 6;
			else h = ((r - g) / d + 4) / 6;
			return { hue: Math.round(h * 360), ...hslToHsv(sl * 100, ll * 100) };
		}
		return { hue: 210, sv: 0.696, vv: 0.92 };
	}

	const init = parseColorToHsv(value);
	let hue = $state(init.hue);
	let sv = $state(init.sv);
	let vv = $state(init.vv);
	let hueDragging = $state(false);
	let slDragging = $state(false);

	const hsl = $derived(hsvToHsl(hue, sv, vv));
	const hslString = $derived(
		`hsl(${Math.round(hsl.h)} ${Math.round(hsl.s)}% ${Math.round(hsl.l)}%)`
	);
	const hexString = $derived(hslToHex(hsl.h, hsl.s, hsl.l));

	function updateHue(e: PointerEvent) {
		const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
		hue = Math.round(Math.max(0, Math.min((e.clientX - rect.left) / rect.width, 1)) * 360);
	}

	function updateSL(e: PointerEvent) {
		const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
		sv = Math.max(0, Math.min((e.clientX - rect.left) / rect.width, 1));
		vv = 1 - Math.max(0, Math.min((e.clientY - rect.top) / rect.height, 1));
	}

	function onHexChange(e: Event) {
		const val = (e.currentTarget as HTMLInputElement).value.trim();
		const parsed = parseColorToHsv(val);
		hue = parsed.hue;
		sv = parsed.sv;
		vv = parsed.vv;
	}
</script>

<div
	class="w-52 rounded-xl border border-gray-200 bg-white p-3 shadow-xl"
	onclick={(e) => e.stopPropagation()}
	role="menu"
	aria-label="Pick a color"
>
	<!-- Hue bar -->
	<div
		data-testid="color-picker-hue-bar"
		class="relative mb-2 h-4 w-full cursor-crosshair rounded select-none"
		style="background: linear-gradient(to right, hsl(0,100%,50%), hsl(60,100%,50%), hsl(120,100%,50%), hsl(180,100%,50%), hsl(240,100%,50%), hsl(300,100%,50%), hsl(360,100%,50%))"
		onpointerdown={(e) => {
			hueDragging = true;
			(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
			updateHue(e);
		}}
		onpointermove={(e) => {
			if (hueDragging) updateHue(e);
		}}
		onpointerup={() => (hueDragging = false)}
	>
		<div
			class="pointer-events-none absolute top-0 h-full w-1.5 -translate-x-1/2 rounded border-2 border-white shadow"
			style="left: {(hue / 360) * 100}%"
		></div>
	</div>

	<!-- Saturation / Lightness square -->
	<div
		data-testid="color-picker-sl-square"
		class="relative mb-2 h-32 w-full cursor-crosshair rounded select-none"
		style="background: linear-gradient(to bottom, transparent, #000), linear-gradient(to right, #fff, hsl({hue},100%,50%))"
		onpointerdown={(e) => {
			slDragging = true;
			(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
			updateSL(e);
		}}
		onpointermove={(e) => {
			if (slDragging) updateSL(e);
		}}
		onpointerup={() => (slDragging = false)}
	>
		<div
			class="pointer-events-none absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow"
			style="left: {sv * 100}%; top: {(1 - vv) * 100}%; background-color: {hslString}"
		></div>
	</div>

	<!-- Preview + hex input + buttons -->
	<div class="flex items-center gap-1.5">
		<div
			class="h-5 w-5 shrink-0 rounded-full border border-gray-200"
			style="background-color: {hslString}"
		></div>
		<input
			data-testid="color-picker-hex"
			type="text"
			class="min-w-0 flex-1 rounded border border-gray-200 px-2 py-0.5 font-mono text-xs"
			value={hexString}
			onchange={onHexChange}
		/>
		<button
			data-testid="color-picker-cancel"
			onclick={onCancel}
			class="rounded border border-gray-200 px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-50"
			role="menuitem">✕</button
		>
		<button
			data-testid="color-picker-apply"
			onclick={() => onApply?.(hslString)}
			class="rounded bg-blue-600 px-2 py-0.5 text-xs text-white hover:bg-blue-700"
			role="menuitem">✓</button
		>
	</div>
</div>

<script lang="ts">
	import sticker from '$lib/assets/riley_sticker.png';

	function seededRandom(seed: number) {
		let s = seed;
		return () => {
			s = (s * 1664525 + 1013904223) & 0xffffffff;
			return (s >>> 0) / 0xffffffff;
		};
	}

	const rand = seededRandom(42);

	// Bell-curve-ish rotation: sum 3 uniforms (central limit theorem)
	// Gives most values near 0, rare at extremes, virtually none upside-down
	function bellRotation(): number {
		const sum = rand() + rand() + rand(); // range [0,3], mean 1.5
		return (sum - 1.5) * 30; // range [-45,45], most within ±20°
	}

	// Grid-based placement with jitter for even distribution
	const cols = 9;
	const rows = 7;
	const cellW = 100 / cols;
	const cellH = 100 / rows;

	const stickerSize = 120;

	interface StickerPlacement {
		left: number;
		top: number;
		rotate: number;
		z: number;
	}

	const stickers: StickerPlacement[] = [];
	for (let row = 0; row < rows; row++) {
		for (let col = 0; col < cols; col++) {
			stickers.push({
				left: col * cellW + rand() * cellW,
				top: row * cellH + rand() * cellH,
				rotate: bellRotation(),
				z: Math.floor(rand() * 10)
			});
		}
	}
</script>

<div class="absolute inset-0 overflow-hidden pointer-events-none">
	{#each stickers as s, i (i)}
		<img
			src={sticker}
			alt=""
			class="absolute"
			style="left:{s.left}%;top:{s.top}%;width:{stickerSize}px;transform:rotate({s.rotate}deg);z-index:{s.z}"
		/>
	{/each}
</div>

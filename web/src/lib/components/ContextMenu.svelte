<script lang="ts">
	import type { PlotMessage } from '$lib/types';

	interface Props {
		x: number;
		y: number;
		plot: PlotMessage;
		isInCompare: boolean;
		onrename: () => void;
		ontags: () => void;
		onnotes: () => void;
		oncopy: () => void;
		ondelete: () => void;
		ontogglecompare: () => void;
		onclose: () => void;
	}

	let { x, y, plot, isInCompare, onrename, ontags, onnotes, oncopy, ondelete, ontogglecompare, onclose }: Props = $props();

	function clampToViewport(node: HTMLElement) {
		const rect = node.getBoundingClientRect();
		const vw = window.innerWidth;
		const vh = window.innerHeight;

		let nx = x;
		let ny = y;

		if (x + rect.width > vw) {
			nx = vw - rect.width - 4;
		}
		if (y + rect.height > vh) {
			ny = vh - rect.height - 4;
		}
		if (nx < 0) nx = 4;
		if (ny < 0) ny = 4;

		node.style.left = `${nx}px`;
		node.style.top = `${ny}px`;
	}

	function handleWindowClick() {
		onclose();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			onclose();
		}
	}
</script>

<svelte:window onclick={handleWindowClick} onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div
	use:clampToViewport
	class="fixed z-50 border border-[var(--color-border)] bg-[var(--color-bg-raised)] py-1 min-w-[160px]"
	style="left: {x}px; top: {y}px;"
	onclick={(e) => e.stopPropagation()}
>
	<button
		class="w-full text-left text-xs px-3 py-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg)] transition-colors"
		onclick={onrename}
	>rename</button>
	<button
		class="w-full text-left text-xs px-3 py-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg)] transition-colors"
		onclick={ontags}
	>edit tags</button>
	<button
		class="w-full text-left text-xs px-3 py-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg)] transition-colors"
		onclick={onnotes}
	>edit notes</button>

	<div class="my-1 border-t border-[var(--color-border)]"></div>

	<button
		class="w-full text-left text-xs px-3 py-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg)] transition-colors"
		onclick={oncopy}
	>copy to clipboard</button>
	<button
		class="w-full text-left text-xs px-3 py-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-bg)] transition-colors"
		onclick={ontogglecompare}
	>{isInCompare ? 'remove from compare' : 'add to compare'}</button>

	<div class="my-1 border-t border-[var(--color-border)]"></div>

	<button
		class="w-full text-left text-xs px-3 py-1 text-[var(--color-text-muted)] hover:text-[var(--color-error)] hover:bg-[var(--color-bg)] transition-colors"
		onclick={ondelete}
	>delete</button>
</div>

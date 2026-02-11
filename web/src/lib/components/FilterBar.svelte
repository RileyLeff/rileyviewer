<script lang="ts">
	import type { PlotMessage } from '$lib/types';

	interface Props {
		plots: PlotMessage[];
		activeTag: string | null;
		searchQuery: string;
		ontagclick: (tag: string | null) => void;
		onsearch: (query: string) => void;
	}

	let { plots, activeTag, searchQuery, ontagclick, onsearch }: Props = $props();

	let tagCounts = $derived.by(() => {
		const counts = new Map<string, number>();
		for (const plot of plots) {
			if (plot.tags) {
				for (const tag of plot.tags) {
					counts.set(tag, (counts.get(tag) ?? 0) + 1);
				}
			}
		}
		return [...counts.entries()].sort((a, b) => b[1] - a[1]);
	});
</script>

<div class="flex items-center gap-2 border-b border-[var(--color-border)] px-3 py-1.5">
	<div class="flex items-center gap-1 flex-wrap min-w-0">
		<button
			class={`shrink-0 border px-2 py-0.5 text-xs transition-colors ${
				activeTag === null
					? 'border-[var(--color-accent)] text-[var(--color-accent)]'
					: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-text-faint)]'
			}`}
			onclick={() => ontagclick(null)}
		>[all ({plots.length})]</button>

		{#each tagCounts as [tag, count] (tag)}
			<button
				class={`shrink-0 border px-2 py-0.5 text-xs transition-colors ${
					activeTag === tag
						? 'border-[var(--color-accent)] text-[var(--color-accent)]'
						: 'border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-text-faint)]'
				}`}
				onclick={() => ontagclick(tag)}
			>[{tag} ({count})]</button>
		{/each}
	</div>

	<input
		type="text"
		placeholder="search..."
		value={searchQuery}
		oninput={(e) => onsearch(e.currentTarget.value)}
		class="ml-auto shrink-0 w-40 border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-faint)] text-xs px-2 py-0.5 focus:border-[var(--color-accent)] focus:outline-none transition-colors"
	/>
</div>

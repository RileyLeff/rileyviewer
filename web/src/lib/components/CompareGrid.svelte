<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import DataTable from '$lib/components/DataTable.svelte';

	type PlotContent =
		| { type: 'Png'; data: string }
		| { type: 'Svg'; data: string }
		| { type: 'Plotly'; data: string }
		| { type: 'Vega'; data: string }
		| { type: 'Html'; data: string }
		| { type: 'ArrowIpc'; data: string }
		| { type: 'Csv'; data: string };

	type PlotMessage = {
		id: string;
		timestamp: number;
		content: PlotContent;
	};

	interface Props {
		plots: PlotMessage[];
	}

	let { plots }: Props = $props();

	// Shared module caches -- plain let, NOT $state, to avoid infinite loops in $effect.
	// These are just library references and do not need reactivity.
	let plotlyModule: any = null;
	let vegaEmbed: any = null;

	// Per-cell DOM element refs, keyed by plot id.
	// Using $state so that $effect can track when bind:this assigns them.
	let plotlyEls: Record<string, HTMLDivElement | null> = $state({});
	let vegaEls: Record<string, HTMLDivElement | null> = $state({});

	// Per-cell cleanup functions -- plain let, NOT $state.
	// Written inside $effect callbacks that would also read them if reactive => infinite loop.
	let cleanups: Record<string, (() => void) | null> = {};

	// Per-cell render generation tokens -- plain let, NOT $state.
	// Prevents stale async renders from applying after a newer render has started.
	let cellGenerations: Record<string, number> = {};

	function humanTime(ts: number): string {
		return new Date(ts).toLocaleTimeString([], {
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		});
	}

	function renderSvgSrc(data: string): string | null {
		if (!browser) return null;
		const bytes = new TextEncoder().encode(data);
		let binary = '';
		const chunkSize = 8192;
		for (let i = 0; i < bytes.length; i += chunkSize) {
			binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
		}
		return `data:image/svg+xml;base64,${btoa(binary)}`;
	}

	function nextGen(plotId: string): number {
		const gen = (cellGenerations[plotId] ?? 0) + 1;
		cellGenerations[plotId] = gen;
		return gen;
	}

	function isStale(plotId: string, gen: number): boolean {
		return cellGenerations[plotId] !== gen;
	}

	async function renderPlotlyCell(
		el: HTMLDivElement,
		content: Extract<PlotContent, { type: 'Plotly' }>,
		plotId: string
	) {
		const gen = nextGen(plotId);
		try {
			cleanups[plotId]?.();
			cleanups[plotId] = null;

			const payload = JSON.parse(content.data);
			const Plotly = plotlyModule ?? (await import('plotly.js-dist-min')).default;
			plotlyModule = Plotly;

			if (isStale(plotId, gen) || !el) return;

			await Plotly.react(
				el,
				payload.data ?? payload,
				{ ...(payload.layout ?? {}), autosize: true },
				{ responsive: true }
			);

			const capturedEl = el;
			cleanups[plotId] = () => {
				try {
					Plotly.purge(capturedEl);
				} catch {}
			};
		} catch (e) {
			console.error('CompareGrid: Failed to render Plotly chart:', e);
		}
	}

	async function renderVegaCell(
		el: HTMLDivElement,
		content: Extract<PlotContent, { type: 'Vega' }>,
		plotId: string
	) {
		const gen = nextGen(plotId);
		try {
			cleanups[plotId]?.();
			cleanups[plotId] = null;

			const spec = JSON.parse(content.data);
			const embed = vegaEmbed ?? (await import('vega-embed')).default;
			vegaEmbed = embed;

			if (isStale(plotId, gen) || !el) return;

			const rect = el.getBoundingClientRect();
			const w = Math.floor(rect.width) - 16;
			const h = Math.floor(rect.height) - 16;
			if (w > 0 && h > 0) {
				spec.width = spec.width ?? w;
				spec.height = spec.height ?? h;
				spec.autosize = spec.autosize ?? { type: 'fit', contains: 'padding' };
			}

			const result = await embed(el, spec, { actions: false, renderer: 'canvas' });

			if (isStale(plotId, gen)) {
				result.view.finalize();
				return;
			}

			cleanups[plotId] = () => result.view.finalize();
		} catch (e) {
			console.error('CompareGrid: Failed to render Vega chart:', e);
		}
	}

	// $effect for Plotly renders. Tracks the plots array and per-cell element refs.
	// The {#key} block ensures DOM is destroyed/recreated when plot.id changes.
	// renderPlotlyCell only writes to plain let variables (cleanups, cellGenerations,
	// plotlyModule) -- NOT $state -- so this cannot cause infinite loops.
	$effect(() => {
		if (!browser) return;
		for (const plot of plots) {
			if (plot.content.type === 'Plotly') {
				const el = plotlyEls[plot.id];
				if (el) {
					// Read content.data synchronously to register as a dependency
					const _data = plot.content.data;
					renderPlotlyCell(el, plot.content, plot.id);
				}
			}
		}
	});

	// $effect for Vega renders, same pattern as Plotly.
	// renderVegaCell only writes to plain let variables -- NOT $state.
	$effect(() => {
		if (!browser) return;
		for (const plot of plots) {
			if (plot.content.type === 'Vega') {
				const el = vegaEls[plot.id];
				if (el) {
					const _data = plot.content.data;
					renderVegaCell(el, plot.content, plot.id);
				}
			}
		}
	});

	onMount(() => {
		return () => {
			// Clean up all Plotly/Vega cells on component unmount
			for (const id of Object.keys(cleanups)) {
				cleanups[id]?.();
			}
			cleanups = {};
			cellGenerations = {};
		};
	});
</script>

<div
	class="grid grid-cols-2 w-full h-full gap-2"
	style="grid-template-rows: repeat({plots.length <= 2 ? 1 : 2}, minmax(0, 1fr));"
>
	{#each plots as plot (plot.id)}
		{#key plot.id}
			<div class="flex flex-col border border-[var(--color-border)] bg-[var(--color-bg-canvas)] min-h-0 min-w-0 overflow-hidden">
				<!-- Per-cell label: plot type + timestamp -->
				<div class="flex-none flex items-center gap-2 px-2 py-1 border-b border-[var(--color-border)] bg-[var(--color-bg-raised)]">
					<span class="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
						{plot.content.type}
					</span>
					<span class="text-[11px] text-[var(--color-text-faint)]">
						{humanTime(plot.timestamp)}
					</span>
				</div>

				<!-- Per-cell content area -->
				<div class="flex-1 min-h-0 min-w-0 overflow-hidden">
					{#if plot.content.type === 'Png'}
						<div class="w-full h-full flex items-center justify-center p-1">
							<img
								src="data:image/png;base64,{plot.content.data}"
								alt="PNG plot"
								class="max-w-full max-h-full object-contain"
							/>
						</div>
					{:else if plot.content.type === 'Svg'}
						{@const svgSrc = renderSvgSrc(plot.content.data)}
						<div class="w-full h-full flex items-center justify-center p-1">
							{#if svgSrc}
								<img
									src={svgSrc}
									alt="SVG plot"
									class="max-w-full max-h-full object-contain"
								/>
							{/if}
						</div>
					{:else if plot.content.type === 'Plotly'}
						<div
							class="w-full h-full p-1"
							bind:this={plotlyEls[plot.id]}
						></div>
					{:else if plot.content.type === 'Vega'}
						<div
							class="w-full h-full p-1"
							bind:this={vegaEls[plot.id]}
						></div>
					{:else if plot.content.type === 'Html'}
						<div class="w-full h-full p-1">
							<iframe
								srcdoc={plot.content.data}
								class="w-full h-full border-0"
								sandbox="allow-scripts"
								title="HTML content"
							></iframe>
						</div>
					{:else if plot.content.type === 'ArrowIpc' || plot.content.type === 'Csv'}
						<div class="w-full h-full">
							<DataTable data={plot.content.data} format={plot.content.type} />
						</div>
					{:else}
						<div class="w-full h-full flex items-center justify-center p-2">
							<pre class="text-xs text-[var(--color-text-muted)] overflow-auto max-h-full">{JSON.stringify(plot.content, null, 2)}</pre>
						</div>
					{/if}
				</div>
			</div>
		{/key}
	{/each}
</div>

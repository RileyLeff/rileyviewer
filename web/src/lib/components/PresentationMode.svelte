<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import DataTable from '$lib/components/DataTable.svelte';
	import type { PlotMessage, PlotContent } from '$lib/types';

	interface Props {
		plots: PlotMessage[];
		initialId?: string | null;
		onclose: () => void;
	}

	let { plots, initialId = null, onclose }: Props = $props();

	function resolveInitialIndex(): number {
		if (!initialId) return 0;
		const idx = plots.findIndex((p) => p.id === initialId);
		return idx >= 0 ? idx : 0;
	}

	let currentIndex = $state(resolveInitialIndex());

	// Plain let variables — NOT $state — to avoid infinite loops in $effect.
	// These are internal caching/cleanup refs that must not trigger reactivity.
	let plotlyModule: any = null;
	let vegaEmbed: any = null;
	let plotlyCleanup: (() => void) | null = null;
	let vegaCleanup: (() => void) | null = null;
	let renderGeneration = 0;

	let plotlyEl: HTMLDivElement | null = $state(null);
	let vegaEl: HTMLDivElement | null = $state(null);

	let current = $derived(plots[currentIndex] ?? null);

	// Chrome auto-hide state
	let showChrome = $state(true);
	let chromeTimer: ReturnType<typeof setTimeout> | null = null;

	function resetChromeTimer() {
		showChrome = true;
		if (chromeTimer) clearTimeout(chromeTimer);
		chromeTimer = setTimeout(() => { showChrome = false; }, 3000);
	}

	function handleMouseMove() {
		resetChromeTimer();
	}

	// Auto-close if no plots
	$effect(() => {
		if (plots.length === 0) {
			close();
		}
	});

	// Clamp currentIndex if plots shrink
	$effect(() => {
		if (plots.length > 0 && currentIndex >= plots.length) {
			currentIndex = plots.length - 1;
		}
	});

	// Render Plotly when current plot is Plotly type
	$effect(() => {
		if (browser && current?.content.type === 'Plotly' && plotlyEl) {
			renderPlotly(current.content);
		}
	});

	// Render Vega when current plot is Vega type
	$effect(() => {
		if (browser && current?.content.type === 'Vega' && vegaEl) {
			renderVega(current.content);
		}
	});

	// Clean up renderers when switching away from those content types
	$effect(() => {
		const type = current?.content.type;
		if (type !== 'Plotly') {
			plotlyCleanup?.();
			plotlyCleanup = null;
		}
		if (type !== 'Vega') {
			vegaCleanup?.();
			vegaCleanup = null;
		}
	});

	onMount(() => {
		// Request fullscreen (returns a promise; catch rejection silently)
		document.documentElement.requestFullscreen?.()?.catch(() => {});

		// Show chrome briefly on mount, then auto-fade
		resetChromeTimer();

		// Listen for fullscreen exit via browser chrome (not our Escape handler)
		function onFullscreenChange() {
			if (!document.fullscreenElement) {
				onclose();
			}
		}
		document.addEventListener('fullscreenchange', onFullscreenChange);

		return () => {
			document.removeEventListener('fullscreenchange', onFullscreenChange);
			if (chromeTimer) clearTimeout(chromeTimer);
			vegaCleanup?.();
			plotlyCleanup?.();
		};
	});

	function close() {
		if (document.fullscreenElement) {
			document.exitFullscreen();
		} else {
			onclose();
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		switch (e.key) {
			case 'ArrowLeft': {
				e.stopPropagation();
				if (currentIndex > 0) currentIndex--;
				resetChromeTimer();
				break;
			}
			case 'ArrowRight': {
				e.stopPropagation();
				if (currentIndex < plots.length - 1) currentIndex++;
				resetChromeTimer();
				break;
			}
			case 'Home': {
				e.stopPropagation();
				currentIndex = 0;
				resetChromeTimer();
				break;
			}
			case 'End': {
				e.stopPropagation();
				if (plots.length > 0) currentIndex = plots.length - 1;
				resetChromeTimer();
				break;
			}
			case 'Escape': {
				e.stopPropagation();
				close();
				break;
			}
		}
	}

	function svgToBase64(svgData: string): string {
		const bytes = new TextEncoder().encode(svgData);
		let binary = '';
		const chunkSize = 8192;
		for (let i = 0; i < bytes.length; i += chunkSize) {
			binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
		}
		return btoa(binary);
	}

	async function renderPlotly(content: Extract<PlotContent, { type: 'Plotly' }>) {
		if (!plotlyEl) return;
		const gen = ++renderGeneration;
		try {
			plotlyCleanup?.();
			plotlyCleanup = null;
			const payload = JSON.parse(content.data);
			const Plotly = plotlyModule ?? (await import('plotly.js-dist-min')).default;
			plotlyModule = Plotly;
			if (gen !== renderGeneration || !plotlyEl) return;
			await Plotly.react(
				plotlyEl,
				payload.data ?? payload,
				{ ...(payload.layout ?? {}), autosize: true },
				{ responsive: true }
			);
			const el = plotlyEl;
			plotlyCleanup = () => {
				try {
					Plotly.purge(el);
				} catch {}
			};
		} catch (e) {
			console.error('Failed to render Plotly chart in presentation mode:', e);
		}
	}

	async function renderVega(content: Extract<PlotContent, { type: 'Vega' }>) {
		if (!vegaEl) return;
		const gen = ++renderGeneration;
		try {
			vegaCleanup?.();
			vegaCleanup = null;
			const spec = JSON.parse(content.data);
			const embed = vegaEmbed ?? (await import('vega-embed')).default;
			vegaEmbed = embed;
			if (gen !== renderGeneration || !vegaEl) return;

			const rect = vegaEl.getBoundingClientRect();
			const w = Math.floor(rect.width) - 16;
			const h = Math.floor(rect.height) - 16;
			if (w > 0 && h > 0) {
				spec.width = w;
				spec.height = h;
				spec.autosize = { type: 'fit', contains: 'padding' };
			}

			const result = await embed(vegaEl, spec, { actions: false, renderer: 'canvas' });
			if (gen !== renderGeneration) {
				result.view.finalize();
				return;
			}
			vegaCleanup = () => result.view.finalize();
		} catch (e) {
			console.error('Failed to render Vega chart in presentation mode:', e);
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="fixed inset-0 z-50 bg-black"
	onmousemove={handleMouseMove}
>
	<!-- Plot content fills entire viewport -->
	<div class="absolute inset-0 flex items-center justify-center">
		{#if current}
			{#if current.content.type === 'Png'}
				<img
					src="data:image/png;base64,{current.content.data}"
					class="max-w-full max-h-full object-contain"
					alt="plot"
				/>
			{:else if current.content.type === 'Svg'}
				<img
					src="data:image/svg+xml;base64,{svgToBase64(current.content.data)}"
					class="max-w-full max-h-full object-contain"
					alt="plot"
				/>
			{:else if current.content.type === 'Plotly'}
				<div bind:this={plotlyEl} class="w-full h-full"></div>
			{:else if current.content.type === 'Vega'}
				<div bind:this={vegaEl} class="w-full h-full"></div>
			{:else if current.content.type === 'Html'}
				<iframe
					srcdoc={current.content.data}
					class="w-full h-full border-0"
					sandbox="allow-scripts"
					title="HTML content"
				></iframe>
			{:else if current.content.type === 'ArrowIpc' || current.content.type === 'Csv'}
				<div class="w-full h-full">
					<DataTable data={current.content.data} format={current.content.type} />
				</div>
			{/if}
		{/if}
	</div>

	<!-- Close button (top-right, always accessible on hover) -->
	<div
		class="absolute top-0 right-0 z-10 p-4 transition-opacity duration-500 {showChrome ? 'opacity-100' : 'opacity-0 pointer-events-none'}"
	>
		<button class="text-white/60 hover:text-white text-xl leading-none" onclick={close}>
			&#x2715;
		</button>
	</div>

	<!-- Chrome overlay (bottom) -->
	<div
		class="absolute inset-x-0 bottom-0 z-10 transition-opacity duration-500 {showChrome ? 'opacity-100' : 'opacity-0 pointer-events-none'}"
	>
		<!-- Gradient backdrop -->
		<div class="absolute inset-0 bg-gradient-to-t from-black/70 to-transparent pointer-events-none"></div>

		<!-- Chrome content -->
		<div class="relative px-6 pb-4 pt-12">
			<!-- Info row -->
			<div class="flex items-center justify-between gap-4 mb-3">
				<div class="flex items-center gap-3 min-w-0">
					{#if current?.title}
						<span class="text-sm text-white/90 truncate">{current.title}</span>
					{/if}
					{#if current?.tags && current.tags.length > 0}
						<div class="flex items-center gap-1">
							{#each current.tags as tag (tag)}
								<span class="text-[10px] border border-white/30 text-white/60 px-1.5 py-0">{tag}</span>
							{/each}
						</div>
					{/if}
					{#if current?.notes}
						<span class="text-xs text-white/50 truncate max-w-[300px]">{current.notes}</span>
					{/if}
				</div>
				<span class="text-sm text-white/60 shrink-0">
					{currentIndex + 1} / {plots.length}
				</span>
			</div>

			<!-- Thumbnail strip -->
			{#if plots.length > 1}
				<div class="flex gap-2 overflow-x-auto pb-1" style="scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.3) transparent;">
					{#each plots as plot, i (plot.id)}
						<button
							class="shrink-0 w-16 h-10 border-2 transition-colors overflow-hidden bg-black/50 {i === currentIndex ? 'border-white/80' : 'border-white/20 hover:border-white/50'}"
							onclick={() => { currentIndex = i; resetChromeTimer(); }}
						>
							<span class="text-[9px] text-white/50 flex items-center justify-center h-full">
								{plot.title || i + 1}
							</span>
						</button>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</div>

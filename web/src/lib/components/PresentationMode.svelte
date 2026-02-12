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

		// Listen for fullscreen exit via browser chrome (not our Escape handler)
		function onFullscreenChange() {
			if (!document.fullscreenElement) {
				onclose();
			}
		}
		document.addEventListener('fullscreenchange', onFullscreenChange);

		return () => {
			document.removeEventListener('fullscreenchange', onFullscreenChange);
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
				break;
			}
			case 'ArrowRight': {
				e.stopPropagation();
				if (currentIndex < plots.length - 1) currentIndex++;
				break;
			}
			case 'Home': {
				e.stopPropagation();
				currentIndex = 0;
				break;
			}
			case 'End': {
				e.stopPropagation();
				if (plots.length > 0) currentIndex = plots.length - 1;
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
				spec.width = spec.width ?? w;
				spec.height = spec.height ?? h;
				spec.autosize = spec.autosize ?? { type: 'fit', contains: 'padding' };
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

<div class="fixed inset-0 z-50 bg-black flex flex-col">
	<!-- Top bar -->
	<div class="flex-none flex items-center justify-between px-4 py-2">
		<div class="text-sm text-white/70 truncate">
			{current?.title ?? ''}
		</div>
		<div class="flex items-center gap-3">
			<span class="text-sm text-white/70">
				{currentIndex + 1} / {plots.length}
			</span>
			<button class="text-white/50 hover:text-white text-lg leading-none" onclick={close}>
				&#x2715;
			</button>
		</div>
	</div>

	<!-- Main content -->
	<div class="flex-1 min-h-0 flex items-center justify-center p-4">
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
</div>

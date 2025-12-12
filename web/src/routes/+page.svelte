<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { page } from '$app/stores';
	import { browser } from '$app/environment';

	type PlotContent =
		| { type: 'Png'; data: string }
		| { type: 'Svg'; data: string }
		| { type: 'Plotly'; data: string }
		| { type: 'Vega'; data: string }
		| { type: 'Html'; data: string };

	type PlotMessage = {
		id: string;
		timestamp: number;
		content: PlotContent;
	};

	let socket: WebSocket | null = $state(null);
	let status: 'idle' | 'connecting' | 'open' | 'closed' | 'error' = $state('idle');
	let error: string | null = $state(null);
	let plots: PlotMessage[] = $state([]);
	let activeId: string | null = $state(null);
	let plotlyEl: HTMLDivElement | null = $state(null);
	let vegaEl: HTMLDivElement | null = $state(null);
	let vegaCleanup: (() => void) | null = $state(null);
	let plotlyModule: any = $state(null);
	let vegaEmbed: any = $state(null);
	let historyEl: HTMLDivElement | null = $state(null);
	let thumbnails: Record<string, string> = $state({});

	// Thumbnail generation queue to prevent UI freezing
	let thumbnailQueue: PlotMessage[] = $state([]);
	let isProcessingThumbnails = $state(false);

	let current = $derived(plots.find((p) => p.id === activeId) ?? plots.at(-1));
	let token = $derived($page.url.searchParams.get('token'));
	let wsUrl = $derived(getWsUrl($page.url, token));

	$effect(() => {
		if (browser && current?.content.type === 'Plotly' && plotlyEl) {
			renderPlotly(current.id, current.content);
		}
	});

	$effect(() => {
		if (browser && current?.content.type === 'Vega' && vegaEl) {
			renderVega(current.id, current.content);
		}
	});

	onMount(() => {
		connect();
		return () => socket?.close();
	});

	function getWsUrl(url: URL, authToken: string | null): string {
		const proto = url.protocol === 'https:' ? 'wss:' : 'ws:';
		const query = authToken ? `?token=${encodeURIComponent(authToken)}` : '';
		return `${proto}//${url.host}/ws${query}`;
	}

	function connect() {
		status = 'connecting';
		error = null;
		socket?.close();
		socket = new WebSocket(wsUrl);

		socket.addEventListener('open', () => {
			status = 'open';
		});

		socket.addEventListener('message', async (event) => {
			try {
				const parsed = JSON.parse(event.data) as PlotMessage;
				// Deduplicate by ID (server sends history on reconnect)
				if (plots.some((p) => p.id === parsed.id)) {
					return;
				}
				plots.push(parsed);
				activeId = parsed.id;
				await tick();
				if (historyEl) {
					historyEl.scrollLeft = historyEl.scrollWidth;
				}
				// Queue thumbnail generation for Plotly/Vega (processed one at a time)
				if (parsed.content.type === 'Plotly' || parsed.content.type === 'Vega') {
					queueThumbnail(parsed);
				}
			} catch (err) {
				console.error('failed to parse plot message', err);
			}
		});

		socket.addEventListener('close', () => {
			status = 'closed';
		});

		socket.addEventListener('error', (e) => {
			status = 'error';
			error = 'Unable to connect (check token?)';
			console.error('ws error', e);
		});
	}

	function humanTime(ts: number): string {
		const d = new Date(ts);
		return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
	}

	function renderSrc(content: PlotContent): string | null {
		if (content.type === 'Png') return `data:image/png;base64,${content.data}`;
		if (content.type === 'Svg') {
			if (!browser) return null;
			// Use TextEncoder to properly handle Unicode characters in SVG
			const bytes = new TextEncoder().encode(content.data);
			const base64 = btoa(String.fromCharCode(...bytes));
			return `data:image/svg+xml;base64,${base64}`;
		}
		return null;
	}

	function getThumbnailSrc(plot: PlotMessage): string | null {
		// Check for generated thumbnail first (Plotly/Vega)
		const generated = thumbnails[plot.id];
		if (generated) return generated;
		// Fall back to native image types
		return renderSrc(plot.content);
	}

	function queueThumbnail(plot: PlotMessage) {
		thumbnailQueue.push(plot);
		processThumbnailQueue();
	}

	async function processThumbnailQueue() {
		if (isProcessingThumbnails || thumbnailQueue.length === 0) return;
		isProcessingThumbnails = true;

		const plot = thumbnailQueue.shift();
		if (plot) {
			// Yield to main thread briefly to allow UI updates
			await new Promise((r) => setTimeout(r, 0));
			await generateThumbnail(plot);
		}

		isProcessingThumbnails = false;
		processThumbnailQueue();
	}

	async function generateThumbnail(plot: PlotMessage) {
		if (thumbnails[plot.id]) return; // Already have one

		if (plot.content.type === 'Plotly') {
			try {
				const Plotly = plotlyModule ?? (await import('plotly.js-dist-min')).default;
				plotlyModule = Plotly;
				const payload = JSON.parse(plot.content.data);

				// Create off-screen div for rendering at full size
				const offscreen = document.createElement('div');
				offscreen.style.position = 'absolute';
				offscreen.style.left = '-9999px';
				offscreen.style.width = '800px';
				offscreen.style.height = '560px';
				document.body.appendChild(offscreen);

				// Render at full size with explicit layout dimensions
				const layout = { ...(payload.layout ?? {}), width: 800, height: 560 };
				await Plotly.newPlot(offscreen, payload.data ?? payload, layout, { staticPlot: true });

				// Export full-size render, then scale down via canvas for proper proportions
				const fullDataUrl = await Plotly.toImage(offscreen, { format: 'png', width: 800, height: 560 });
				Plotly.purge(offscreen);
				document.body.removeChild(offscreen);

				// Scale down to thumbnail size using canvas
				const img = new Image();
				img.src = fullDataUrl;
				await new Promise((resolve) => (img.onload = resolve));

				const canvas = document.createElement('canvas');
				canvas.width = 160;
				canvas.height = 112;
				const ctx = canvas.getContext('2d');
				if (ctx) {
					ctx.drawImage(img, 0, 0, 160, 112);
					thumbnails[plot.id] = canvas.toDataURL('image/png');
				}
			} catch (e) {
				console.warn('Failed to generate Plotly thumbnail:', e);
			}
		} else if (plot.content.type === 'Vega') {
			try {
				const embed = vegaEmbed ?? (await import('vega-embed')).default;
				vegaEmbed = embed;
				const spec = JSON.parse(plot.content.data);

				// Create off-screen div with explicit size
				const offscreen = document.createElement('div');
				offscreen.style.position = 'absolute';
				offscreen.style.left = '-9999px';
				offscreen.style.width = '800px';
				offscreen.style.height = '560px';
				document.body.appendChild(offscreen);

				// Render with explicit dimensions for consistent proportions
				const specWithSize = {
					...spec,
					width: spec.width ?? 760,
					height: spec.height ?? 520
				};
				const result = await embed(offscreen, specWithSize, { actions: false, renderer: 'canvas' });
				const canvas = await result.view.toCanvas(1);
				result.view.finalize();
				document.body.removeChild(offscreen);

				// Scale down to thumbnail
				const thumbCanvas = document.createElement('canvas');
				thumbCanvas.width = 160;
				thumbCanvas.height = 112;
				const ctx = thumbCanvas.getContext('2d');
				if (ctx) {
					ctx.drawImage(canvas, 0, 0, 160, 112);
					thumbnails[plot.id] = thumbCanvas.toDataURL('image/png');
				}
			} catch (e) {
				console.warn('Failed to generate Vega thumbnail:', e);
			}
		}
	}

	async function renderPlotly(plotId: string, content: Extract<PlotContent, { type: 'Plotly' }>) {
		if (!plotlyEl) return;
		const payload = JSON.parse(content.data);
		const Plotly = plotlyModule ?? (await import('plotly.js-dist-min')).default;
		plotlyModule = Plotly;
		await Plotly.react(plotlyEl, payload.data ?? payload, payload.layout ?? {});
		// Thumbnail generation is handled by the queued generateThumbnail function
		// to avoid race conditions when plots arrive rapidly
	}

	async function renderVega(plotId: string, content: Extract<PlotContent, { type: 'Vega' }>) {
		if (!vegaEl) return;
		vegaCleanup?.();
		const spec = JSON.parse(content.data);
		const embed = vegaEmbed ?? (await import('vega-embed')).default;
		vegaEmbed = embed;
		const result = await embed(vegaEl, spec, { actions: false, renderer: 'canvas' });
		vegaCleanup = () => result.view.finalize();
		// Thumbnail generation is handled by the queued generateThumbnail function
		// to avoid race conditions when plots arrive rapidly
	}
</script>

<div class="h-screen flex flex-col bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 text-slate-50">
	<!-- Compact Header -->
	<header class="flex-none flex items-center justify-between gap-3 border-b border-slate-800/70 bg-slate-900/60 px-4 py-2 backdrop-blur">
		<div class="text-sm font-semibold uppercase tracking-[0.15em] text-slate-300">RileyViewer</div>
		<div class="flex items-center gap-2">
			<div class="flex items-center gap-1.5 rounded-full border border-slate-800 bg-slate-900 px-2.5 py-0.5 text-xs">
				<span class={`h-1.5 w-1.5 rounded-full ${
					status === 'open'
						? 'bg-emerald-400'
						: status === 'connecting'
							? 'bg-amber-400'
							: 'bg-slate-500'
				}`}></span>
				<span class="capitalize text-slate-300">{status}</span>
			</div>
			{#if token}
				<div class="rounded border border-emerald-400/40 bg-emerald-400/10 px-2 py-0.5 text-xs text-emerald-200">
					Token
				</div>
			{/if}
			<button class="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 text-xs font-medium text-slate-200 hover:border-slate-500 hover:bg-slate-700" onclick={connect}>
				Reconnect
			</button>
		</div>
	</header>

	{#if error}
		<div class="flex-none border-b border-red-500/50 bg-red-500/10 px-4 py-2 text-sm text-red-100">
			{error}
		</div>
	{/if}

	<!-- Main Canvas Area -->
	<main class="flex-1 min-h-0 p-4">
		{#if !current}
			<div class="h-full flex items-center justify-center">
				<div class="rounded-xl border border-dashed border-slate-700 px-8 py-12 text-center text-slate-400">
					<div class="text-lg mb-1">No plots yet</div>
					<div class="text-sm">Send from Python to see them here</div>
				</div>
			</div>
		{:else}
			<div class="h-full flex items-center justify-center">
				{#if current.content.type === 'Png' || current.content.type === 'Svg'}
					{#if renderSrc(current.content)}
						<img
							class="max-h-full max-w-full rounded-lg border border-slate-800 bg-slate-950/40 object-contain"
							src={renderSrc(current.content) ?? ''}
							alt="plot"
						/>
					{/if}
				{:else if current.content.type === 'Plotly'}
					<div class="w-full h-full rounded-lg border border-slate-800 bg-slate-950/40 p-2">
						<div bind:this={plotlyEl} class="w-full h-full"></div>
					</div>
				{:else if current.content.type === 'Vega'}
					<div class="w-full h-full rounded-lg border border-slate-800 bg-slate-950/40 p-2">
						<div bind:this={vegaEl} class="w-full h-full"></div>
					</div>
				{:else if current.content.type === 'Html'}
					<div class="prose prose-invert max-h-full overflow-auto rounded-lg border border-slate-800 bg-slate-950/40 p-4">
						{@html current.content.data}
					</div>
				{:else}
					<pre class="max-h-full overflow-auto rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-xs text-slate-200">
{JSON.stringify(current.content, null, 2)}
					</pre>
				{/if}
			</div>
		{/if}
	</main>

	<!-- Horizontal Thumbnail History Bar -->
	<footer class="flex-none border-t border-slate-800/70 bg-slate-900/60 backdrop-blur">
		<div
			bind:this={historyEl}
			class="flex gap-2 p-3 overflow-x-auto"
			style="scrollbar-width: thin; scrollbar-color: #334155 transparent;"
		>
			{#if plots.length === 0}
				<div class="flex-none text-sm text-slate-500 py-4 px-2">
					Waiting for plots...
				</div>
			{:else}
				{#each plots as plot}
					<button
						class={`flex-none flex flex-col items-center gap-1 rounded-lg border p-1.5 transition hover:border-slate-500 ${
							activeId === plot.id
								? 'border-emerald-400/60 bg-emerald-400/10'
								: 'border-slate-700 bg-slate-800/60'
						}`}
						onclick={() => (activeId = plot.id)}
					>
						<div class="w-20 h-14 rounded bg-slate-900 flex items-center justify-center overflow-hidden">
							{#if thumbnails[plot.id] || renderSrc(plot.content)}
								<img
									src={thumbnails[plot.id] ?? renderSrc(plot.content)}
									alt=""
									class="w-full h-full object-contain"
								/>
							{:else}
								<span class="text-xs text-slate-500 uppercase">{plot.content.type}</span>
							{/if}
						</div>
						<span class="text-[10px] text-slate-400">{humanTime(plot.timestamp)}</span>
					</button>
				{/each}
			{/if}
		</div>
	</footer>
</div>

<svelte:window onkeydown={(e) => {
	if (e.key === 'r' && e.metaKey) {
		e.preventDefault();
		connect();
	}
}} />

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
			renderPlotly(current.content);
		}
	});

	$effect(() => {
		if (browser && current?.content.type === 'Vega' && vegaEl) {
			renderVega(current.content);
		}
	});

	let reconnectTimer: ReturnType<typeof setTimeout> | null = $state(null);
	let reconnectAttempt = $state(0);

	onMount(() => {
		connect();
		return () => {
			vegaCleanup?.();
			if (reconnectTimer) clearTimeout(reconnectTimer);
			socket?.close();
		};
	});

	function getWsUrl(url: URL, authToken: string | null): string {
		const proto = url.protocol === 'https:' ? 'wss:' : 'ws:';
		const query = authToken ? `?token=${encodeURIComponent(authToken)}` : '';
		return `${proto}//${url.host}/ws${query}`;
	}

	function scheduleReconnect() {
		if (reconnectTimer) clearTimeout(reconnectTimer);
		const delay = Math.min(1000 * 2 ** reconnectAttempt, 10000);
		reconnectTimer = setTimeout(() => {
			reconnectAttempt++;
			connect();
		}, delay);
	}

	function connect() {
		status = 'connecting';
		error = null;
		if (reconnectTimer) {
			clearTimeout(reconnectTimer);
			reconnectTimer = null;
		}
		socket?.close();
		socket = new WebSocket(wsUrl);

		socket.addEventListener('open', () => {
			status = 'open';
			reconnectAttempt = 0;
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
			scheduleReconnect();
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
			// Use TextEncoder + chunked btoa to handle large SVGs safely
			// (spreading into String.fromCharCode crashes on SVGs > ~65KB)
			const bytes = new TextEncoder().encode(content.data);
			let binary = '';
			const chunkSize = 8192;
			for (let i = 0; i < bytes.length; i += chunkSize) {
				binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
			}
			return `data:image/svg+xml;base64,${btoa(binary)}`;
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

	function createOffscreenDiv(): HTMLDivElement {
		const div = document.createElement('div');
		div.style.position = 'absolute';
		div.style.left = '-9999px';
		div.style.width = '800px';
		div.style.height = '560px';
		document.body.appendChild(div);
		return div;
	}

	function removeOffscreenDiv(div: HTMLDivElement) {
		try { document.body.removeChild(div); } catch { /* already removed */ }
	}

	async function generateThumbnail(plot: PlotMessage) {
		if (thumbnails[plot.id]) return; // Already have one

		if (plot.content.type === 'Plotly') {
			const offscreen = createOffscreenDiv();
			try {
				const Plotly = plotlyModule ?? (await import('plotly.js-dist-min')).default;
				plotlyModule = Plotly;
				const payload = JSON.parse(plot.content.data);

				const layout = { ...(payload.layout ?? {}), width: 800, height: 560 };
				await Plotly.newPlot(offscreen, payload.data ?? payload, layout, { staticPlot: true });

				const fullDataUrl = await Plotly.toImage(offscreen, { format: 'png', width: 800, height: 560 });
				Plotly.purge(offscreen);

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
			} finally {
				removeOffscreenDiv(offscreen);
			}
		} else if (plot.content.type === 'Vega') {
			const offscreen = createOffscreenDiv();
			try {
				const embed = vegaEmbed ?? (await import('vega-embed')).default;
				vegaEmbed = embed;
				const spec = JSON.parse(plot.content.data);

				const specWithSize = {
					...spec,
					width: spec.width ?? 760,
					height: spec.height ?? 520
				};
				const result = await embed(offscreen, specWithSize, { actions: false, renderer: 'canvas' });
				const canvas = await result.view.toCanvas(1);
				result.view.finalize();

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
			} finally {
				removeOffscreenDiv(offscreen);
			}
		}
	}

	async function renderPlotly(content: Extract<PlotContent, { type: 'Plotly' }>) {
		if (!plotlyEl) return;
		const payload = JSON.parse(content.data);
		const Plotly = plotlyModule ?? (await import('plotly.js-dist-min')).default;
		plotlyModule = Plotly;
		await Plotly.react(plotlyEl, payload.data ?? payload, {
			...(payload.layout ?? {}),
			autosize: true,
		}, { responsive: true });
	}

	async function renderVega(content: Extract<PlotContent, { type: 'Vega' }>) {
		if (!vegaEl) return;
		vegaCleanup?.();
		const spec = JSON.parse(content.data);
		const embed = vegaEmbed ?? (await import('vega-embed')).default;
		vegaEmbed = embed;
		const result = await embed(vegaEl, spec, { actions: false, renderer: 'canvas' });
		vegaCleanup = () => result.view.finalize();
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
			{#if current.content.type === 'Png'}
				<div class="h-full flex items-center justify-center">
					{#if renderSrc(current.content)}
						<img
							class="h-full w-auto max-w-full rounded-lg border border-slate-800 bg-slate-950/40 object-contain"
							src={renderSrc(current.content) ?? ''}
							alt="plot"
						/>
					{/if}
				</div>
			{:else if current.content.type === 'Svg'}
				<div class="h-full flex items-center justify-center">
					{#if renderSrc(current.content)}
						<img
							class="h-full w-auto max-w-full rounded-lg border border-slate-800 bg-slate-950/40 object-contain"
							src={renderSrc(current.content) ?? ''}
							alt="plot"
						/>
					{/if}
				</div>
			{:else if current.content.type === 'Plotly'}
				<div class="w-full h-full rounded-lg border border-slate-800 bg-slate-950/40 p-2">
					<div bind:this={plotlyEl} class="w-full h-full"></div>
				</div>
			{:else if current.content.type === 'Vega'}
				<div class="w-full h-full rounded-lg border border-slate-800 bg-slate-950/40 p-2">
					<div bind:this={vegaEl} class="w-full h-full"></div>
				</div>
			{:else if current.content.type === 'Html'}
				<div class="h-full flex items-center justify-center">
					<iframe
						srcdoc={current.content.data}
						class="h-full w-auto max-w-full aspect-[10/7] rounded-lg border border-slate-800 bg-slate-950/40"
						sandbox="allow-scripts"
						title="HTML content"
					></iframe>
				</div>
			{:else}
				<div class="h-full flex items-center justify-center">
					<pre class="max-h-full overflow-auto rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-xs text-slate-200">
{JSON.stringify(current.content, null, 2)}
					</pre>
				</div>
			{/if}
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
							{#if getThumbnailSrc(plot)}
								<img
									src={getThumbnailSrc(plot)}
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


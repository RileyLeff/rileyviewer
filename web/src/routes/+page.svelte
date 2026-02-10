<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { page } from '$app/stores';
	import { browser } from '$app/environment';
	import SettingsMenu from '$lib/components/SettingsMenu.svelte';
	import RileyMania from '$lib/components/RileyMania.svelte';
	import rileySticker from '$lib/assets/riley_sticker.png';
	import { getBackground, getLinkLogo, getThumbPos } from '$lib/theme.svelte';

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
	let socketGeneration = 0; // tracks which socket is "current" to ignore stale close events
	let status: 'idle' | 'connecting' | 'open' | 'closed' | 'error' = $state('idle');
	let error: string | null = $state(null);
	let plots: PlotMessage[] = $state([]);
	let activeId: string | null = $state(null);
	let plotlyEl: HTMLDivElement | null = $state(null);
	let vegaEl: HTMLDivElement | null = $state(null);
	let vegaCleanup: (() => void) | null = null;
	let plotlyCleanup: (() => void) | null = null;
	let plotlyModule: any = null;
	let vegaEmbed: any = null;
	let renderGeneration = 0; // cancellation token for async renders
	let historyEl: HTMLDivElement | null = $state(null);
	let thumbnails: Record<string, string> = $state({});
	const MAX_CLIENT_PLOTS = 200;

	let thumbnailQueue: PlotMessage[] = $state([]);
	let isProcessingThumbnails = $state(false);

	let current = $derived(plots.find((p) => p.id === activeId) ?? plots.at(-1));
	let currentSrc = $derived(current ? renderSrc(current.content, current.id) : null);
	let token = $derived($page.url.searchParams.get('token'));
	let wsUrl = $derived(getWsUrl($page.url, token));
	let bg = $derived(getBackground());
	let linkLogo = $derived(getLinkLogo());
	let thumbPos = $derived(getThumbPos());
	let thumbIsVertical = $derived(thumbPos === 'left' || thumbPos === 'right');

	const STICKER_STORE = 'https://www.stickermule.com/rileyleff/item/19535644';

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
			++socketGeneration; // prevent stale close handler from scheduling reconnect
			vegaCleanup?.();
			plotlyCleanup?.();
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
		const gen = ++socketGeneration;
		socket = new WebSocket(wsUrl);

		socket.addEventListener('open', () => {
			if (gen !== socketGeneration) return;
			status = 'open';
			reconnectAttempt = 0;
		});

		socket.addEventListener('message', async (event) => {
			if (gen !== socketGeneration) return;
			try {
				const parsed = JSON.parse(event.data) as PlotMessage;
				if (plots.some((p) => p.id === parsed.id)) {
					return;
				}
				plots.push(parsed);
				while (plots.length > MAX_CLIENT_PLOTS) {
					const evicted = plots.shift();
					if (evicted) {
						delete thumbnails[evicted.id];
						srcCache.delete(evicted.id);
					}
				}
				activeId = parsed.id;
				await tick();
				if (historyEl) {
					if (thumbIsVertical) {
						historyEl.scrollTop = historyEl.scrollHeight;
					} else {
						historyEl.scrollLeft = historyEl.scrollWidth;
					}
				}
				if (parsed.content.type === 'Plotly' || parsed.content.type === 'Vega') {
					queueThumbnail(parsed);
				}
			} catch (err) {
				console.error('failed to parse plot message', err);
			}
		});

		socket.addEventListener('close', () => {
			if (gen !== socketGeneration) return; // stale socket, ignore
			status = 'closed';
			scheduleReconnect();
		});

		socket.addEventListener('error', (e) => {
			if (gen !== socketGeneration) return;
			status = 'error';
			error = 'Unable to connect (check token?)';
			console.error('ws error', e);
		});
	}

	function humanTime(ts: number): string {
		const d = new Date(ts);
		return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
	}

	const srcCache = new Map<string, string>();

	function renderSrc(content: PlotContent, id?: string): string | null {
		if (content.type === 'Png') return `data:image/png;base64,${content.data}`;
		if (content.type === 'Svg') {
			if (!browser) return null;
			if (id && srcCache.has(id)) return srcCache.get(id)!;
			const bytes = new TextEncoder().encode(content.data);
			let binary = '';
			const chunkSize = 8192;
			for (let i = 0; i < bytes.length; i += chunkSize) {
				binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
			}
			const src = `data:image/svg+xml;base64,${btoa(binary)}`;
			if (id) srcCache.set(id, src);
			return src;
		}
		return null;
	}

	function getThumbnailSrc(plot: PlotMessage): string | null {
		const generated = thumbnails[plot.id];
		if (generated) return generated;
		return renderSrc(plot.content, plot.id);
	}

	function queueThumbnail(plot: PlotMessage) {
		thumbnailQueue.push(plot);
		processThumbnailQueue();
	}

	async function processThumbnailQueue() {
		if (isProcessingThumbnails || thumbnailQueue.length === 0) return;
		isProcessingThumbnails = true;

		try {
			while (thumbnailQueue.length > 0) {
				const plot = thumbnailQueue.shift();
				if (plot) {
					// Wait for the main render to finish before generating thumbnails
					await new Promise((r) => setTimeout(r, 500));
					// Skip if this plot is currently displayed (avoid concurrent heavy renders)
					if (plot.id !== activeId) {
						await generateThumbnail(plot);
					}
					// If active, just drop it — the type label fallback is fine
				}
			}
		} finally {
			isProcessingThumbnails = false;
		}
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
		if (thumbnails[plot.id]) return;

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
				await new Promise((resolve, reject) => {
					img.onload = resolve;
					img.onerror = reject;
				});

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
		const gen = ++renderGeneration;
		try {
			plotlyCleanup?.();
			plotlyCleanup = null;
			const payload = JSON.parse(content.data);
			const Plotly = plotlyModule ?? (await import('plotly.js-dist-min')).default;
			plotlyModule = Plotly;
			if (gen !== renderGeneration || !plotlyEl) return; // stale or unmounted
			await Plotly.react(plotlyEl, payload.data ?? payload, {
				...(payload.layout ?? {}),
				autosize: true,
			}, { responsive: true });
			const el = plotlyEl; // capture for closure
			plotlyCleanup = () => { try { Plotly.purge(el); } catch {} };
		} catch (e) {
			console.error('Failed to render Plotly chart:', e);
		}
	}

	function scrollActiveIntoView() {
		tick().then(() => {
			const btn = historyEl?.querySelector('[data-active="true"]') as HTMLElement | null;
			btn?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
		});
	}

	function handleKeydown(e: KeyboardEvent) {
		const tag = (e.target as HTMLElement)?.tagName;
		if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target as HTMLElement)?.isContentEditable) return;

		switch (e.key) {
			case 'ArrowLeft':
			case 'ArrowUp': {
				e.preventDefault();
				const idx = plots.findIndex((p) => p.id === activeId);
				if (idx > 0) {
					activeId = plots[idx - 1].id;
					scrollActiveIntoView();
				}
				break;
			}
			case 'ArrowRight':
			case 'ArrowDown': {
				e.preventDefault();
				const idx = plots.findIndex((p) => p.id === activeId);
				if (idx >= 0 && idx < plots.length - 1) {
					activeId = plots[idx + 1].id;
					scrollActiveIntoView();
				}
				break;
			}
			case 'Home': {
				e.preventDefault();
				if (plots.length > 0) {
					activeId = plots[0].id;
					scrollActiveIntoView();
				}
				break;
			}
			case 'End': {
				e.preventDefault();
				if (plots.length > 0) {
					activeId = plots.at(-1)!.id;
					scrollActiveIntoView();
				}
				break;
			}
			case 'Escape':
				if (error) error = null;
				break;
			case 'r':
				if (!e.ctrlKey && !e.metaKey && !e.altKey) {
					connect();
				}
				break;
			case 'c':
				if (!e.ctrlKey && !e.metaKey && !e.altKey) {
					copyCurrentPlot();
				}
				break;
		}
	}

	async function copyCurrentPlot() {
		if (!current) return;
		try {
			if (current.content.type === 'Png') {
				const resp = await fetch(`data:image/png;base64,${current.content.data}`);
				const blob = await resp.blob();
				await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
			} else if (current.content.type === 'Svg') {
				await navigator.clipboard.writeText(current.content.data);
			} else if (current.content.type === 'Plotly' || current.content.type === 'Vega') {
				await navigator.clipboard.writeText(current.content.data);
			} else if (current.content.type === 'Html') {
				await navigator.clipboard.writeText(current.content.data);
			}
		} catch (e) {
			console.warn('Copy to clipboard failed:', e);
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
			if (gen !== renderGeneration || !vegaEl) return; // stale or unmounted

			// Size the chart to fit within its container (including axes/title/legend)
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
				result.view.finalize(); // cleanup orphaned render
				return;
			}
			vegaCleanup = () => result.view.finalize();
		} catch (e) {
			console.error('Failed to render Vega chart:', e);
		}
	}
</script>

{#snippet stickerImg()}
	<img
		src={rileySticker}
		alt="Riley"
		class="w-[360px] h-auto transition-transform duration-200 hover:-rotate-3 hover:scale-105"
	/>
{/snippet}

{#snippet thumbStrip()}
	{#if plots.length === 0}
		<div class={`flex-none text-xs text-[var(--color-text-faint)] py-4 px-2`}>
			waiting for plots...
		</div>
	{:else}
		{#each plots as plot (plot.id)}
			{@const thumbSrc = getThumbnailSrc(plot)}
			<button
				class={`flex-none flex flex-col items-center gap-1 border p-1.5 transition-colors ${
					activeId === plot.id
						? 'border-[var(--color-accent)] bg-[var(--color-accent-muted)]'
						: 'border-[var(--color-border)] hover:border-[var(--color-text-faint)]'
				}`}
				data-active={activeId === plot.id ? 'true' : undefined}
				onclick={() => (activeId = plot.id)}
			>
				<div class="w-20 h-14 bg-[var(--color-bg-canvas)] flex items-center justify-center overflow-hidden">
					{#if thumbSrc}
						<img
							src={thumbSrc}
							alt=""
							class="w-full h-full object-contain"
						/>
					{:else}
						<span class="text-[11px] text-[var(--color-text-faint)] uppercase">{plot.content.type}</span>
					{/if}
				</div>
				<span class="text-[11px] text-[var(--color-text-faint)]">{humanTime(plot.timestamp)}</span>
			</button>
		{/each}
	{/if}
{/snippet}

<svelte:window onkeydown={handleKeydown} />

<div class="h-screen flex flex-col bg-[var(--color-bg)] text-[var(--color-text)]">
	<header class="flex-none flex items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-bg-raised)] px-4 py-2">
		<span class="text-sm font-semibold uppercase tracking-[0.1em]">rileyviewer</span>
		<div class="flex items-center gap-3 text-xs text-[var(--color-text-muted)]">
			<span class="flex items-center gap-1.5">
				<span class={`inline-block h-1.5 w-1.5 rounded-full ${
					status === 'open'
						? 'bg-[var(--color-accent)]'
						: status === 'connecting'
							? 'bg-[var(--color-warning)]'
							: 'bg-[var(--color-text-faint)]'
				}`}></span>
				<span>{status}</span>
			</span>
			{#if token}
				<span class="text-[var(--color-accent)]">[token]</span>
			{/if}
			<SettingsMenu />
			<button
				class="border border-[var(--color-border)] px-2 py-0.5 text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-text)] transition-colors"
				onclick={connect}
			>[reconnect]</button>
		</div>
	</header>

	{#if error}
		<div class="flex-none border-b border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-2 text-sm text-[var(--color-error)]">
			error: {error}
		</div>
	{/if}

	<div class={`flex-1 min-h-0 flex ${thumbIsVertical ? 'flex-row' : 'flex-col'}`}>
		{#if thumbPos === 'top' || thumbPos === 'left'}
			<div
				bind:this={historyEl}
				class={`flex-none bg-[var(--color-bg-raised)] ${
					thumbIsVertical
						? 'flex flex-col gap-2 p-3 overflow-y-auto border-r border-[var(--color-border)]'
						: 'flex gap-2 p-3 overflow-x-auto border-b border-[var(--color-border)]'
				}`}
				style="scrollbar-width: thin; scrollbar-color: var(--color-border) transparent;"
			>
				{@render thumbStrip()}
			</div>
		{/if}

		<main class="flex-1 min-h-0 min-w-0 p-3">
			{#if !current}
				<div class="h-full relative flex flex-col items-center justify-center text-[var(--color-text-faint)] gap-4">
					{#if bg === 'mania'}
						<RileyMania />
					{:else if bg === 'sticker'}
						<div class="relative z-10">
							{#if linkLogo}
								<a href={STICKER_STORE} target="_blank" rel="noopener noreferrer">
									{@render stickerImg()}
								</a>
							{:else}
								{@render stickerImg()}
							{/if}
						</div>
					{/if}
					<div class="text-center relative z-10">
						<div class="text-sm">no plots yet</div>
						<div class="text-xs mt-1">send from python to see them here</div>
					</div>
				</div>
			{:else}
				{#if current.content.type === 'Png' || current.content.type === 'Svg'}
					<div class="h-full flex items-center justify-center">
						{#if currentSrc}
							<img
								class="h-full w-auto max-w-full border border-[var(--color-border)] bg-[var(--color-bg-canvas)] object-contain"
								src={currentSrc}
								alt="plot"
							/>
						{/if}
					</div>
				{:else if current.content.type === 'Plotly'}
					<div class="w-full h-full border border-[var(--color-border)] bg-[var(--color-bg-canvas)] p-2">
						<div bind:this={plotlyEl} class="w-full h-full"></div>
					</div>
				{:else if current.content.type === 'Vega'}
					<div class="w-full h-full border border-[var(--color-border)] bg-[var(--color-bg-canvas)] p-2">
						<div bind:this={vegaEl} class="w-full h-full"></div>
					</div>
				{:else if current.content.type === 'Html'}
					<div class="h-full flex items-center justify-center">
						<iframe
							srcdoc={current.content.data}
							class="h-full w-auto max-w-full aspect-[10/7] border border-[var(--color-border)] bg-[var(--color-bg-canvas)]"
							sandbox="allow-scripts"
							title="HTML content"
						></iframe>
					</div>
				{:else}
					<div class="h-full flex items-center justify-center">
						<pre class="max-h-full overflow-auto border border-[var(--color-border)] bg-[var(--color-bg-canvas)] p-4 text-xs">
{JSON.stringify(current.content, null, 2)}
						</pre>
					</div>
				{/if}
			{/if}
		</main>

		{#if thumbPos === 'bottom' || thumbPos === 'right'}
			<div
				bind:this={historyEl}
				class={`flex-none bg-[var(--color-bg-raised)] ${
					thumbIsVertical
						? 'flex flex-col gap-2 p-3 overflow-y-auto border-l border-[var(--color-border)]'
						: 'flex gap-2 p-3 overflow-x-auto border-t border-[var(--color-border)]'
				}`}
				style="scrollbar-width: thin; scrollbar-color: var(--color-border) transparent;"
			>
				{@render thumbStrip()}
			</div>
		{/if}
	</div>
</div>

<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { page } from '$app/stores';
	import { browser } from '$app/environment';
	import SettingsMenu from '$lib/components/SettingsMenu.svelte';
	import RileyMania from '$lib/components/RileyMania.svelte';
	import DataTable from '$lib/components/DataTable.svelte';
	import ExportMenu from '$lib/components/ExportMenu.svelte';
	import CompareGrid from '$lib/components/CompareGrid.svelte';
	import FilterBar from '$lib/components/FilterBar.svelte';
	import MetadataPanel from '$lib/components/MetadataPanel.svelte';
	import CollectionsMenu from '$lib/components/CollectionsMenu.svelte';
	import ContextMenu from '$lib/components/ContextMenu.svelte';
	import PresentationMode from '$lib/components/PresentationMode.svelte';
	import rileySticker from '$lib/assets/riley_sticker.png';
	import { getBackground, getLinkLogo, getThumbPos } from '$lib/theme.svelte';
	import type { PlotContent, PlotMessage, MetadataUpdate } from '$lib/types';

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

	// Toast notification state
	let toast: string | null = $state(null);
	let toastTimer: ReturnType<typeof setTimeout> | null = null;

	function showToast(msg: string, durationMs = 2000) {
		if (toastTimer) clearTimeout(toastTimer);
		toast = msg;
		toastTimer = setTimeout(() => { toast = null; }, durationMs);
	}

	let current = $derived(plots.find((p) => p.id === activeId) ?? plots.at(-1));
	let currentSrc = $derived(current ? renderSrc(current.content, current.id) : null);
	let token = $derived($page.url.searchParams.get('token'));
	let wsUrl = $derived(getWsUrl($page.url, token));
	let bg = $derived(getBackground());
	let linkLogo = $derived(getLinkLogo());
	let thumbPos = $derived(getThumbPos());
	let thumbIsVertical = $derived(thumbPos === 'left' || thumbPos === 'right');

	// Comparison grid state
	let compareIds: string[] = $state([]);
	let compareMode = $state(false);
	let comparePlots = $derived(
		compareIds.map((id) => plots.find((p) => p.id === id)).filter((p): p is PlotMessage => !!p)
	);

	// Context menu state
	let contextMenu: { x: number; y: number; plotId: string } | null = $state(null);
	let contextMenuPlot = $derived.by(() => {
		const cm = contextMenu;
		return cm ? plots.find((p) => p.id === cm.plotId) ?? null : null;
	});
	let requestEditField: 'title' | 'tags' | 'notes' | null = $state(null);

	// Presentation mode
	let presenting = $state(false);

	// Filter state
	let activeTag: string | null = $state(null);
	let searchQuery = $state('');

	let filteredPlots = $derived.by(() => {
		let result = plots;
		if (activeTag) {
			result = result.filter((p) => p.tags?.includes(activeTag!));
		}
		if (searchQuery.trim()) {
			const q = searchQuery.trim().toLowerCase();
			result = result.filter((p) => {
				if (p.title?.toLowerCase().includes(q)) return true;
				if (p.notes?.toLowerCase().includes(q)) return true;
				if (p.tags?.some((t) => t.toLowerCase().includes(q))) return true;
				return false;
			});
		}
		return result;
	});

	let hasAnyTags = $derived(plots.some((p) => p.tags && p.tags.length > 0));
	let showFilterBar = $derived(hasAnyTags || searchQuery.length > 0);

	function toggleCompare(id: string) {
		const idx = compareIds.indexOf(id);
		if (idx >= 0) {
			compareIds.splice(idx, 1);
		} else if (compareIds.length < 4) {
			compareIds.push(id);
		}
	}

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

	// Clean up Plotly/Vega when switching away from those content types.
	// Reads current?.content.type as dependency; fires cleanup for the
	// renderer that's no longer active. Writes only to plain let vars.
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

	let reconnectTimer: ReturnType<typeof setTimeout> | null = $state(null);
	let reconnectAttempt = $state(0);
	let authFailed = $state(false); // stop retrying after auth rejection

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
		if (authFailed) return; // don't retry auth failures
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
		authFailed = false;
		if (reconnectTimer) {
			clearTimeout(reconnectTimer);
			reconnectTimer = null;
		}
		socket?.close();
		const gen = ++socketGeneration;
		let didOpen = false;
		socket = new WebSocket(wsUrl);

		socket.addEventListener('open', () => {
			if (gen !== socketGeneration) return;
			didOpen = true;
			status = 'open';
			reconnectAttempt = 0;
		});

		socket.addEventListener('message', async (event) => {
			if (gen !== socketGeneration) return;
			try {
				const parsed = JSON.parse(event.data);

				// Handle metadata updates (PATCH broadcast)
				if (parsed.kind === 'metadata_update') {
					const update = parsed as MetadataUpdate;
					const plot = plots.find((p) => p.id === update.id);
					if (plot) {
						if ('title' in update) plot.title = update.title ?? undefined;
						if ('notes' in update) plot.notes = update.notes ?? undefined;
						if ('tags' in update) plot.tags = update.tags;
					}
					return;
				}

				// Handle clear broadcast
				if (parsed.kind === 'clear') {
					plots.length = 0;
					activeId = null;
					compareIds.length = 0;
					compareMode = false;
					presenting = false;
					activeTag = null;
					searchQuery = '';
					thumbnails = {};
					srcCache.clear();
					return;
				}

				// Handle delete broadcast
				if (parsed.kind === 'delete') {
					removePlotLocally(parsed.id);
					return;
				}

				// Regular plot message
				const plotMsg = parsed as PlotMessage;
				if (plots.some((p) => p.id === plotMsg.id)) {
					return;
				}
				plots.push(plotMsg);
				while (plots.length > MAX_CLIENT_PLOTS) {
					const evicted = plots.shift();
					if (evicted) {
						delete thumbnails[evicted.id];
						srcCache.delete(evicted.id);
						const cmpIdx = compareIds.indexOf(evicted.id);
						if (cmpIdx >= 0) compareIds.splice(cmpIdx, 1);
					}
				}
				activeId = plotMsg.id;
				await tick();
				if (historyEl) {
					// Only auto-scroll if user is already near the end
					if (thumbIsVertical) {
						const nearBottom = historyEl.scrollTop + historyEl.clientHeight >= historyEl.scrollHeight - 80;
						if (nearBottom) historyEl.scrollTop = historyEl.scrollHeight;
					} else {
						const nearEnd = historyEl.scrollLeft + historyEl.clientWidth >= historyEl.scrollWidth - 80;
						if (nearEnd) historyEl.scrollLeft = historyEl.scrollWidth;
					}
				}
				if (plotMsg.content.type === 'Plotly' || plotMsg.content.type === 'Vega') {
					queueThumbnail(plotMsg);
				}
			} catch (err) {
				console.error('failed to parse plot message', err);
			}
		});

		socket.addEventListener('close', async (e) => {
			if (gen !== socketGeneration) return; // stale socket, ignore
			// If socket never opened and closed with 1006, could be auth rejection
			// or a transient network failure. Probe /health to distinguish.
			if (!didOpen && e.code === 1006) {
				try {
					const healthUrl = `${$page.url.protocol}//${$page.url.host}/health`;
					const resp = await fetch(healthUrl, { signal: AbortSignal.timeout(2000) });
					if (resp.ok) {
						// Server is up but rejected our WS — auth failure
						authFailed = true;
						status = 'error';
						error = 'Connection rejected — check token';
						return;
					}
				} catch {
					// Server unreachable — transient failure, retry
				}
				status = 'closed';
				scheduleReconnect();
				return;
			}
			status = 'closed';
			scheduleReconnect();
		});

		socket.addEventListener('error', (e) => {
			if (gen !== socketGeneration) return;
			status = 'error';
			error = 'Unable to connect';
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

		// During presentation mode, only allow Escape (handled by PresentationMode itself)
		if (presenting) return;

		switch (e.key) {
			case 'ArrowLeft':
			case 'ArrowUp': {
				e.preventDefault();
				const idx = filteredPlots.findIndex((p) => p.id === activeId);
				if (idx > 0) {
					activeId = filteredPlots[idx - 1].id;
					scrollActiveIntoView();
				}
				break;
			}
			case 'ArrowRight':
			case 'ArrowDown': {
				e.preventDefault();
				const idx = filteredPlots.findIndex((p) => p.id === activeId);
				if (idx >= 0 && idx < filteredPlots.length - 1) {
					activeId = filteredPlots[idx + 1].id;
					scrollActiveIntoView();
				}
				break;
			}
			case 'Home': {
				e.preventDefault();
				if (filteredPlots.length > 0) {
					activeId = filteredPlots[0].id;
					scrollActiveIntoView();
				}
				break;
			}
			case 'End': {
				e.preventDefault();
				if (filteredPlots.length > 0) {
					activeId = filteredPlots.at(-1)!.id;
					scrollActiveIntoView();
				}
				break;
			}
			case 'Escape':
				if (presenting) {
					presenting = false;
				} else if (contextMenu) {
					contextMenu = null;
				} else if (compareMode) {
					compareMode = false;
				} else if (error) {
					error = null;
				}
				break;
			case 'p':
				if (!e.ctrlKey && !e.metaKey && !e.altKey && filteredPlots.length > 0 && !compareMode) {
					presenting = true;
				}
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
			case 'Delete':
			case 'Backspace':
				if (current) {
					e.preventDefault();
					deletePlot(current.id);
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
			} else if (current.content.type === 'ArrowIpc') {
				// Convert Arrow IPC to CSV text for clipboard
				const { tableFromIPC } = await import('apache-arrow');
				const binary = atob(current.content.data);
				const bytes = new Uint8Array(binary.length);
				for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
				const table = tableFromIPC(bytes);
				const cols = table.schema.fields.map((f) => f.name);
				const rows = [cols.join(',')];
				for (let i = 0; i < table.numRows; i++) {
					rows.push(cols.map((c) => {
						const v = table.getChild(c)?.get(i);
						if (v == null) return '';
						const s = String(v);
						return s.includes(',') || s.includes('"') || s.includes('\n')
							? `"${s.replace(/"/g, '""')}"` : s;
					}).join(','));
				}
				await navigator.clipboard.writeText(rows.join('\n'));
			} else if (current.content.type === 'Svg') {
				await navigator.clipboard.writeText(current.content.data);
			} else if (current.content.type === 'Plotly' || current.content.type === 'Vega') {
				await navigator.clipboard.writeText(current.content.data);
			} else if (current.content.type === 'Html') {
				await navigator.clipboard.writeText(current.content.data);
			} else if (current.content.type === 'Csv') {
				await navigator.clipboard.writeText(current.content.data);
			}
			showToast('copied to clipboard');
		} catch (e) {
			console.warn('Copy to clipboard failed:', e);
			showToast('copy failed');
		}
	}

	async function updatePlotMetadata(
		id: string,
		fields: { title?: string | null; notes?: string | null; tags?: string[] }
	) {
		// Optimistic local update
		const plot = plots.find((p) => p.id === id);
		if (plot) {
			if ('title' in fields) plot.title = fields.title ?? undefined;
			if ('notes' in fields) plot.notes = fields.notes ?? undefined;
			if ('tags' in fields) plot.tags = fields.tags;
		}

		// PATCH server
		const url = `${$page.url.protocol}//${$page.url.host}/api/plots/${id}/metadata`;
		const body: Record<string, any> = { ...fields };
		if (token) body.token = token;
		try {
			const resp = await fetch(url, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			if (!resp.ok) {
				console.error('Failed to update metadata:', resp.status);
				showToast('metadata update failed');
			}
		} catch (e) {
			console.error('Failed to update metadata:', e);
			showToast('metadata update failed');
		}
	}

	function removePlotLocally(id: string) {
		const idx = plots.findIndex((p) => p.id === id);
		if (idx < 0) return;

		// If deleting the active plot, select next or previous in filtered view
		if (activeId === id) {
			const filtered = filteredPlots;
			const fi = filtered.findIndex((p) => p.id === id);
			if (fi >= 0 && fi < filtered.length - 1) {
				activeId = filtered[fi + 1].id;
			} else if (fi > 0) {
				activeId = filtered[fi - 1].id;
			} else {
				activeId = null;
			}
		}

		plots.splice(idx, 1);
		delete thumbnails[id];
		srcCache.delete(id);
		const cmpIdx = compareIds.indexOf(id);
		if (cmpIdx >= 0) compareIds.splice(cmpIdx, 1);
	}

	async function deletePlot(id: string) {
		removePlotLocally(id);

		const url = `${$page.url.protocol}//${$page.url.host}/api/plots/${id}`;
		const body: Record<string, any> = {};
		if (token) body.token = token;
		try {
			const resp = await fetch(url, {
				method: 'DELETE',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			if (!resp.ok) {
				console.error('Failed to delete plot:', resp.status);
				showToast('delete failed');
			}
		} catch (e) {
			console.error('Failed to delete plot:', e);
			showToast('delete failed');
		}
	}

	async function clearAllPlots() {
		if (!confirm('Clear all plots? This cannot be undone.')) return;

		plots.length = 0;
		activeId = null;
		compareIds.length = 0;
		compareMode = false;
		presenting = false;
		activeTag = null;
		searchQuery = '';
		thumbnails = {};
		srcCache.clear();

		const url = `${$page.url.protocol}//${$page.url.host}/api/plots`;
		const body: Record<string, any> = {};
		if (token) body.token = token;
		try {
			const resp = await fetch(url, {
				method: 'DELETE',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			if (!resp.ok) {
				console.error('Failed to clear plots:', resp.status);
				showToast('clear failed');
			}
		} catch (e) {
			console.error('Failed to clear plots:', e);
			showToast('clear failed');
		}
	}

	async function snapshotSave() {
		const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';
		const url = `${$page.url.protocol}//${$page.url.host}/api/snapshot${tokenParam}`;
		try {
			const resp = await fetch(url);
			if (!resp.ok) {
				showToast(`snapshot save failed: HTTP ${resp.status}`);
				return;
			}
			const blob = await resp.blob();
			const ts = new Date();
			const tsStr = `${ts.getFullYear()}${String(ts.getMonth() + 1).padStart(2, '0')}${String(ts.getDate()).padStart(2, '0')}-${String(ts.getHours()).padStart(2, '0')}${String(ts.getMinutes()).padStart(2, '0')}${String(ts.getSeconds()).padStart(2, '0')}`;
			const a = document.createElement('a');
			a.href = URL.createObjectURL(blob);
			a.download = `session-${tsStr}.rvw`;
			a.click();
			setTimeout(() => URL.revokeObjectURL(a.href), 60000);
			showToast(`saved snapshot (${(blob.size / 1048576).toFixed(1)} MB)`);
		} catch (e) {
			console.error('Snapshot save failed:', e);
			showToast('snapshot save failed');
		}
	}

	async function snapshotLoad(file: File) {
		const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';
		const url = `${$page.url.protocol}//${$page.url.host}/api/snapshot${tokenParam}`;
		try {
			const data = await file.arrayBuffer();
			const resp = await fetch(url, {
				method: 'POST',
				headers: { 'Content-Type': 'application/x-rileyviewer-snapshot' },
				body: data,
			});
			if (!resp.ok) {
				showToast(`snapshot load failed: HTTP ${resp.status}`);
				return;
			}
			const result = await resp.json();
			showToast(`loaded ${result.loaded} plots from snapshot`);
		} catch (e) {
			console.error('Snapshot load failed:', e);
			showToast('snapshot load failed');
		}
	}

	function snapshotPickFile() {
		const input = document.createElement('input');
		input.type = 'file';
		input.accept = '.rvw';
		input.onchange = () => {
			const file = input.files?.[0];
			if (file) snapshotLoad(file);
		};
		input.click();
	}

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		const file = e.dataTransfer?.files[0];
		if (file?.name.endsWith('.rvw')) {
			snapshotLoad(file);
		}
	}

	function handleDragOver(e: DragEvent) {
		e.preventDefault();
		if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
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
				spec.width = w;
				spec.height = h;
				spec.autosize = { type: 'fit', contains: 'padding' };
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

	let batchExporting = $state(false);

	async function batchExport() {
		const selectedPlots = compareIds
			.map((id) => plots.find((p) => p.id === id))
			.filter((p): p is PlotMessage => !!p);
		if (selectedPlots.length === 0) return;

		batchExporting = true;
		try {
			const JSZip = (await import('jszip')).default;
			const zip = new JSZip();
			const ts = new Date();
			const tsStr = `${ts.getFullYear()}${String(ts.getMonth() + 1).padStart(2, '0')}${String(ts.getDate()).padStart(2, '0')}-${String(ts.getHours()).padStart(2, '0')}${String(ts.getMinutes()).padStart(2, '0')}${String(ts.getSeconds()).padStart(2, '0')}`;

			for (let i = 0; i < selectedPlots.length; i++) {
				const plot = selectedPlots[i];
				const idx = String(i + 1).padStart(2, '0');
				const c = plot.content;

				if (c.type === 'Png') {
					const binary = atob(c.data);
					const bytes = new Uint8Array(binary.length);
					for (let j = 0; j < binary.length; j++) bytes[j] = binary.charCodeAt(j);
					zip.file(`${idx}-plot.png`, bytes);
				} else if (c.type === 'Svg') {
					zip.file(`${idx}-plot.svg`, c.data);
				} else if (c.type === 'Plotly') {
					zip.file(`${idx}-plot.json`, c.data);
				} else if (c.type === 'Vega') {
					zip.file(`${idx}-plot.json`, c.data);
				} else if (c.type === 'Html') {
					zip.file(`${idx}-plot.html`, c.data);
				} else if (c.type === 'Csv') {
					zip.file(`${idx}-data.csv`, c.data);
				} else if (c.type === 'ArrowIpc') {
					// Convert Arrow to CSV for zip
					try {
						const { tableFromIPC } = await import('apache-arrow');
						const bin = atob(c.data);
						const bytes = new Uint8Array(bin.length);
						for (let j = 0; j < bin.length; j++) bytes[j] = bin.charCodeAt(j);
						const table = tableFromIPC(bytes);
						const cols = table.schema.fields.map((f) => f.name);
						const rows = [cols.join(',')];
						for (let r = 0; r < table.numRows; r++) {
							rows.push(cols.map((col) => {
								const v = table.getChild(col)?.get(r);
								if (v == null) return '';
								const s = String(v);
								return s.includes(',') || s.includes('"') || s.includes('\n')
									? `"${s.replace(/"/g, '""')}"` : s;
							}).join(','));
						}
						zip.file(`${idx}-data.csv`, rows.join('\n'));
					} catch {
						// Fallback: include raw base64
						zip.file(`${idx}-data.arrow.b64`, c.data);
					}
				}
			}

			const blob = await zip.generateAsync({ type: 'blob' });
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = `rileyviewer-${tsStr}.zip`;
			a.click();
			setTimeout(() => URL.revokeObjectURL(url), 60000);
			showToast(`exported ${selectedPlots.length} plots as zip`);
		} catch (e) {
			console.error('Batch export failed:', e);
			showToast('batch export failed');
		} finally {
			batchExporting = false;
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
	{#if filteredPlots.length === 0}
		<div class={`flex-none text-xs text-[var(--color-text-faint)] py-4 px-2`}>
			{plots.length === 0 ? 'waiting for plots...' : 'no matching plots'}
		</div>
	{:else}
		{#each filteredPlots as plot (plot.id)}
			{@const thumbSrc = getThumbnailSrc(plot)}
			{@const compareIdx = compareIds.indexOf(plot.id)}
			{@const tooltip = [plot.title, humanTime(plot.timestamp), plot.notes?.split('\n')[0]].filter(Boolean).join(' — ')}
			<button
				class={`group flex-none flex flex-col items-center gap-0.5 border p-1.5 transition-colors relative ${
					activeId === plot.id && !compareMode
						? 'border-[var(--color-accent)] bg-[var(--color-accent-muted)]'
						: compareIdx >= 0
							? 'border-[var(--color-accent)] ring-1 ring-[var(--color-accent)]'
							: 'border-[var(--color-border)] hover:border-[var(--color-text-faint)]'
				}`}
				data-active={activeId === plot.id ? 'true' : undefined}
				title={tooltip}
				onclick={(e) => {
					if (e.shiftKey) {
						toggleCompare(plot.id);
					} else {
						activeId = plot.id;
						if (compareMode) compareMode = false;
					}
				}}
				oncontextmenu={(e) => {
					e.preventDefault();
					contextMenu = { x: e.clientX, y: e.clientY, plotId: plot.id };
				}}
			>
				<!-- svelte-ignore a11y_click_events_have_key_events -->
				<span
					class="absolute top-0 right-0 w-4 h-4 flex items-center justify-center text-[10px] leading-none text-[var(--color-text-faint)] hover:text-[var(--color-error)] opacity-0 group-hover:opacity-100 transition-opacity z-10 cursor-pointer"
					role="button"
					tabindex="-1"
					onclick={(e) => { e.stopPropagation(); deletePlot(plot.id); }}
				>&times;</span>
				{#if compareIdx >= 0}
					<span class="absolute -top-1.5 -right-1.5 bg-[var(--color-accent)] text-[var(--color-bg)] text-[10px] font-bold w-4 h-4 rounded-full flex items-center justify-center z-10">
						{compareIdx + 1}
					</span>
				{/if}
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
				{#if plot.title}
					<span class="text-[10px] text-[var(--color-text-muted)] w-20 truncate text-center">{plot.title}</span>
				{/if}
				<span class="text-[11px] text-[var(--color-text-faint)]">{humanTime(plot.timestamp)}</span>
			</button>
		{/each}
	{/if}
{/snippet}

<svelte:window onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="h-screen flex flex-col bg-[var(--color-bg)] text-[var(--color-text)]"
	ondrop={handleDrop}
	ondragover={handleDragOver}
>
	<header class="flex-none flex items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-bg-raised)] px-4 py-2">
		<span class="text-sm font-semibold uppercase tracking-[0.1em]">rileyviewer</span>
		<div class="flex items-center gap-3 text-xs text-[var(--color-text-muted)]">
			<button
				class={`inline-block h-2.5 w-2.5 rounded-full transition-colors cursor-pointer ${
					status === 'open'
						? 'bg-[var(--color-accent)]'
						: status === 'connecting'
							? 'bg-[var(--color-warning)] animate-pulse'
							: 'bg-[var(--color-text-faint)]'
				}`}
				title={status === 'open'
					? (token ? 'Click to copy token' : 'Connected')
					: status === 'connecting'
						? 'Connecting...'
						: 'Disconnected — click to reconnect'}
				onclick={() => {
					if (status === 'open' && token) {
						navigator.clipboard.writeText(token).then(() => showToast('token copied'));
					} else if (status !== 'open' && status !== 'connecting') {
						connect();
					}
				}}
			></button>
			{#if compareMode}
				<button
					class="border border-[var(--color-accent)] bg-[var(--color-accent-muted)] px-2 py-0.5 text-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-[var(--color-bg)] transition-colors"
					onclick={() => { compareMode = false; }}
				>[exit compare]</button>
			{:else if compareIds.length >= 2}
				<button
					class="border border-[var(--color-accent)] px-2 py-0.5 text-[var(--color-accent)] hover:bg-[var(--color-accent-muted)] transition-colors"
					onclick={() => { compareMode = true; }}
				>[compare {compareIds.length}]</button>
			{/if}
			{#if compareIds.length > 0 && !compareMode}
				<button
					class="border border-[var(--color-border)] px-2 py-0.5 text-[var(--color-text-faint)] hover:border-[var(--color-text-faint)] transition-colors"
					onclick={() => { compareIds = []; }}
				>[clear]</button>
			{/if}
			{#if compareIds.length >= 2}
				<button
					class="border border-[var(--color-accent)] px-2 py-0.5 text-[var(--color-accent)] hover:bg-[var(--color-accent-muted)] transition-colors disabled:opacity-50"
					onclick={batchExport}
					disabled={batchExporting}
				>[{batchExporting ? 'zipping...' : `export ${compareIds.length} as zip`}]</button>
			{/if}
			{#if plots.length > 0 || current}
				<ExportMenu
					content={current && !compareMode ? current.content : null}
					onexport={showToast}
					plotCount={plots.length}
					onsave={snapshotSave}
					onopen={snapshotPickFile}
				/>
			{/if}
			<CollectionsMenu
				{activeTag}
				{searchQuery}
				onselectcollection={(c) => {
					activeTag = c.tag ?? null;
					searchQuery = c.search ?? '';
				}}
			/>
			<SettingsMenu />
			{#if filteredPlots.length > 0 && !compareMode}
				<button
					class="border border-[var(--color-border)] px-2 py-0.5 text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-text)] transition-colors"
					onclick={() => { presenting = true; }}
				>[present]</button>
			{/if}
			{#if plots.length > 0}
				<button
					class="border border-[var(--color-border)] px-2 py-0.5 text-[var(--color-text-muted)] hover:border-[var(--color-error)] hover:text-[var(--color-error)] transition-colors"
					onclick={clearAllPlots}
				>[clear all]</button>
			{/if}
			<div class="relative group">
				<button
					class="border border-[var(--color-border)] px-2 py-0.5 text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-text)] transition-colors"
				>[?]</button>
				<div class="hidden group-hover:block absolute right-0 top-full mt-1 z-50 border border-[var(--color-border)] bg-[var(--color-bg-raised)] p-3 min-w-[220px] text-[11px] text-[var(--color-text-muted)]">
					<div class="text-[11px] text-[var(--color-text-faint)] uppercase tracking-wider mb-2">keyboard shortcuts</div>
					<div class="flex flex-col gap-1">
						<div class="flex justify-between"><span>← ↑</span><span>previous plot</span></div>
						<div class="flex justify-between"><span>→ ↓</span><span>next plot</span></div>
						<div class="flex justify-between"><span>Home</span><span>first plot</span></div>
						<div class="flex justify-between"><span>End</span><span>last plot</span></div>
						<div class="flex justify-between"><span>p</span><span>present</span></div>
						<div class="flex justify-between"><span>r</span><span>reconnect</span></div>
						<div class="flex justify-between"><span>c</span><span>copy plot</span></div>
						<div class="flex justify-between"><span>Del</span><span>delete plot</span></div>
						<div class="flex justify-between"><span>Esc</span><span>dismiss</span></div>
					</div>
				</div>
			</div>
		</div>
	</header>

	{#if error}
		<div class="flex-none border-b border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-2 text-sm text-[var(--color-error)]">
			error: {error}
		</div>
	{/if}

	{#if showFilterBar}
		<FilterBar
			plots={plots}
			{activeTag}
			{searchQuery}
			ontagclick={(tag) => { activeTag = tag; }}
			onsearch={(q) => { searchQuery = q; }}
		/>
	{/if}

	{#if current && !compareMode}
		<MetadataPanel
			plot={current}
			onupdate={(id, fields) => updatePlotMetadata(id, fields)}
			requestEdit={requestEditField}
			oneditrequesthandled={() => { requestEditField = null; }}
		/>
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
				onscroll={() => { if (contextMenu) contextMenu = null; }}
			>
				{@render thumbStrip()}
			</div>
		{/if}

		<main class="flex-1 min-h-0 min-w-0 p-3">
			{#if compareMode && comparePlots.length >= 2}
				<CompareGrid plots={comparePlots} />
			{:else if !current}
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
				{:else if current.content.type === 'ArrowIpc' || current.content.type === 'Csv'}
					<div class="h-full w-full">
						<DataTable data={current.content.data} format={current.content.type} />
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
				onscroll={() => { if (contextMenu) contextMenu = null; }}
			>
				{@render thumbStrip()}
			</div>
		{/if}
	</div>

	{#if presenting}
		<PresentationMode
			plots={filteredPlots}
			initialId={activeId}
			onclose={() => { presenting = false; }}
		/>
	{/if}

	{#if contextMenu && contextMenuPlot}
		<ContextMenu
			x={contextMenu.x}
			y={contextMenu.y}
			plot={contextMenuPlot}
			isInCompare={compareIds.includes(contextMenuPlot.id)}
			onrename={() => { activeId = contextMenuPlot!.id; contextMenu = null; requestEditField = 'title'; }}
			ontags={() => { activeId = contextMenuPlot!.id; contextMenu = null; requestEditField = 'tags'; }}
			onnotes={() => { activeId = contextMenuPlot!.id; contextMenu = null; requestEditField = 'notes'; }}
			oncopy={() => { activeId = contextMenuPlot!.id; contextMenu = null; copyCurrentPlot(); }}
			ondelete={() => { const id = contextMenuPlot!.id; contextMenu = null; deletePlot(id); }}
			ontogglecompare={() => { toggleCompare(contextMenuPlot!.id); contextMenu = null; }}
			onclose={() => { contextMenu = null; }}
		/>
	{/if}

	{#if toast}
		<div class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 border border-[var(--color-border)] bg-[var(--color-bg-raised)] px-4 py-2 text-xs text-[var(--color-text-muted)] shadow-lg">
			{toast}
		</div>
	{/if}
</div>

<script lang="ts">
	import { tableFromIPC } from 'apache-arrow';
	import type { PlotContent } from '$lib/types';

	interface Props {
		content?: PlotContent | null;
		onexport?: (msg: string) => void;
		plotCount?: number;
		onsave?: () => void;
		onopen?: () => void;
	}

	let { content = null, onexport, plotCount = 0, onsave, onopen }: Props = $props();

	let open = $state(false);
	let exportError: string | null = $state(null);
	let showSizeOptions = $state(false);
	let exportWidth = $state(800);
	let exportHeight = $state(600);
	let exportDpi: number = $state(1);
	let exporting = $state(false);

	const DPI_OPTIONS = [
		{ label: '1x (screen)', value: 1 },
		{ label: '2x (retina)', value: 2 },
		{ label: '4x (300 dpi)', value: 4 },
		{ label: '8x (600 dpi)', value: 8 },
	];

	function handleClickOutside(e: MouseEvent) {
		const target = e.target as HTMLElement;
		if (!target.closest('.export-menu')) {
			close();
		}
	}

	function close() {
		open = false;
		showSizeOptions = false;
		exportError = null;
	}

	function timestamp(): string {
		const d = new Date();
		return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}-${String(d.getHours()).padStart(2, '0')}${String(d.getMinutes()).padStart(2, '0')}${String(d.getSeconds()).padStart(2, '0')}`;
	}

	function downloadBlob(blob: Blob, filename: string) {
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = filename;
		a.click();
		setTimeout(() => URL.revokeObjectURL(url), 60000);
		onexport?.(`exported ${filename}`);
	}

	function exportPng() {
		if (!content) return;
		const binary = atob(content.data);
		const bytes = new Uint8Array(binary.length);
		for (let i = 0; i < binary.length; i++) {
			bytes[i] = binary.charCodeAt(i);
		}
		downloadBlob(new Blob([bytes], { type: 'image/png' }), `plot-${timestamp()}.png`);
		close();
	}

	async function exportPngResized() {
		if (!content) return;
		exporting = true;
		exportError = null;
		try {
			const binary = atob(content.data);
			const bytes = new Uint8Array(binary.length);
			for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
			const blob = new Blob([bytes], { type: 'image/png' });
			const bmp = await createImageBitmap(blob);
			const w = exportWidth * exportDpi;
			const h = exportHeight * exportDpi;
			const canvas = new OffscreenCanvas(w, h);
			const ctx = canvas.getContext('2d')!;
			ctx.drawImage(bmp, 0, 0, w, h);
			const outBlob = await canvas.convertToBlob({ type: 'image/png' });
			downloadBlob(outBlob, `plot-${exportWidth}x${exportHeight}-${exportDpi}x-${timestamp()}.png`);
			close();
		} catch (e) {
			console.error('Failed to resize PNG:', e);
			exportError = 'resize failed';
		} finally {
			exporting = false;
		}
	}

	async function exportPlotlyPng() {
		if (!content) return;
		exporting = true;
		exportError = null;
		try {
			const payload = JSON.parse(content.data);
			const Plotly = (await import('plotly.js-dist-min')).default;
			const div = document.createElement('div');
			div.style.position = 'absolute';
			div.style.left = '-9999px';
			div.style.width = `${exportWidth}px`;
			div.style.height = `${exportHeight}px`;
			document.body.appendChild(div);
			try {
				await Plotly.newPlot(div, payload.data ?? payload, {
					...(payload.layout ?? {}),
					width: exportWidth,
					height: exportHeight,
				}, { staticPlot: true });
				const dataUrl = await Plotly.toImage(div, {
					format: 'png',
					width: exportWidth * exportDpi,
					height: exportHeight * exportDpi,
				});
				Plotly.purge(div);
				const resp = await fetch(dataUrl);
				const blob = await resp.blob();
				downloadBlob(blob, `plot-${exportWidth}x${exportHeight}-${exportDpi}x-${timestamp()}.png`);
				close();
			} finally {
				try { document.body.removeChild(div); } catch {}
			}
		} catch (e) {
			console.error('Failed to export Plotly as PNG:', e);
			exportError = 'export failed';
		} finally {
			exporting = false;
		}
	}

	async function exportVegaPng() {
		if (!content) return;
		exporting = true;
		exportError = null;
		try {
			const spec = JSON.parse(content.data);
			const embed = (await import('vega-embed')).default;
			const div = document.createElement('div');
			div.style.position = 'absolute';
			div.style.left = '-9999px';
			div.style.width = `${exportWidth}px`;
			div.style.height = `${exportHeight}px`;
			document.body.appendChild(div);
			try {
				const specSized = {
					...spec,
					width: exportWidth - 40,
					height: exportHeight - 40,
					autosize: { type: 'fit', contains: 'padding' },
				};
				const result = await embed(div, specSized, { actions: false, renderer: 'canvas' });
				const canvas = await result.view.toCanvas(exportDpi);
				result.view.finalize();
				canvas.toBlob((blob) => {
					if (blob) {
						downloadBlob(blob, `plot-${exportWidth}x${exportHeight}-${exportDpi}x-${timestamp()}.png`);
						close();
					} else {
						exportError = 'canvas export failed';
					}
				}, 'image/png');
			} finally {
				try { document.body.removeChild(div); } catch {}
			}
		} catch (e) {
			console.error('Failed to export Vega as PNG:', e);
			exportError = 'export failed';
		} finally {
			exporting = false;
		}
	}

	function exportSvg() {
		if (!content) return;
		downloadBlob(new Blob([content.data], { type: 'image/svg+xml' }), `plot-${timestamp()}.svg`);
		close();
	}

	function exportJson() {
		if (!content) return;
		downloadBlob(new Blob([content.data], { type: 'application/json' }), `plot-${timestamp()}.json`);
		close();
	}

	function exportHtml() {
		if (!content) return;
		downloadBlob(new Blob([content.data], { type: 'text/html' }), `plot-${timestamp()}.html`);
		close();
	}

	function exportCsv() {
		if (!content) return;
		downloadBlob(new Blob([content.data], { type: 'text/csv' }), `data-${timestamp()}.csv`);
		close();
	}

	function exportArrowAsCsv() {
		if (!content) return;
		exportError = null;
		try {
			const binary = atob(content.data);
			const bytes = new Uint8Array(binary.length);
			for (let i = 0; i < binary.length; i++) {
				bytes[i] = binary.charCodeAt(i);
			}
			const table = tableFromIPC(bytes);
			const columns = table.schema.fields.map((f) => f.name);
			const rows: string[] = [columns.join(',')];
			for (let i = 0; i < table.numRows; i++) {
				const row = columns.map((col) => {
					const val = table.getChild(col)?.get(i);
					if (val === null || val === undefined) return '';
					const str = String(val);
					if (str.includes(',') || str.includes('"') || str.includes('\n')) {
						return `"${str.replace(/"/g, '""')}"`;
					}
					return str;
				});
				rows.push(row.join(','));
			}
			downloadBlob(new Blob([rows.join('\n')], { type: 'text/csv' }), `data-${timestamp()}.csv`);
			close();
		} catch (e) {
			console.error('Failed to convert Arrow IPC to CSV:', e);
			exportError = 'conversion failed';
		}
	}

	function handleCustomExport() {
		if (!content) return;
		if (content.type === 'Png') exportPngResized();
		else if (content.type === 'Plotly') exportPlotlyPng();
		else if (content.type === 'Vega') exportVegaPng();
	}

	async function exportPdf() {
		if (!content) return;
		exporting = true;
		exportError = null;
		try {
			const { jsPDF } = await import('jspdf');
			const type = content.type;

			if (type === 'Png') {
				const imgData = `data:image/png;base64,${content.data}`;
				const img = new Image();
				img.src = imgData;
				await new Promise<void>((res, rej) => { img.onload = () => res(); img.onerror = rej; });
				const w = img.naturalWidth;
				const h = img.naturalHeight;
				const orientation = w > h ? 'landscape' : 'portrait';
				const doc = new jsPDF({ orientation, unit: 'px', format: [w, h] });
				doc.addImage(imgData, 'PNG', 0, 0, w, h);
				doc.save(`plot-${timestamp()}.pdf`);
				onexport?.(`exported plot-${timestamp()}.pdf`);
			} else if (type === 'Svg') {
				const blob = new Blob([content.data], { type: 'image/svg+xml' });
				const url = URL.createObjectURL(blob);
				const img = new Image();
				img.src = url;
				await new Promise<void>((res, rej) => { img.onload = () => res(); img.onerror = rej; });
				const w = img.naturalWidth || 800;
				const h = img.naturalHeight || 600;
				const canvas = document.createElement('canvas');
				canvas.width = w * 2;
				canvas.height = h * 2;
				const ctx = canvas.getContext('2d')!;
				ctx.scale(2, 2);
				ctx.drawImage(img, 0, 0, w, h);
				URL.revokeObjectURL(url);
				const dataUrl = canvas.toDataURL('image/png');
				const orientation = w > h ? 'landscape' : 'portrait';
				const doc = new jsPDF({ orientation, unit: 'px', format: [w, h] });
				doc.addImage(dataUrl, 'PNG', 0, 0, w, h);
				doc.save(`plot-${timestamp()}.pdf`);
				onexport?.(`exported plot-${timestamp()}.pdf`);
			} else if (type === 'Plotly') {
				const payload = JSON.parse(content.data);
				const Plotly = (await import('plotly.js-dist-min')).default;
				const div = document.createElement('div');
				div.style.position = 'absolute';
				div.style.left = '-9999px';
				div.style.width = '800px';
				div.style.height = '600px';
				document.body.appendChild(div);
				try {
					await Plotly.newPlot(div, payload.data ?? payload, {
						...(payload.layout ?? {}), width: 800, height: 600,
					}, { staticPlot: true });
					const dataUrl = await Plotly.toImage(div, { format: 'png', width: 1600, height: 1200 });
					Plotly.purge(div);
					const doc = new jsPDF({ orientation: 'landscape', unit: 'px', format: [800, 600] });
					doc.addImage(dataUrl, 'PNG', 0, 0, 800, 600);
					doc.save(`plot-${timestamp()}.pdf`);
					onexport?.(`exported plot-${timestamp()}.pdf`);
				} finally {
					try { document.body.removeChild(div); } catch {}
				}
			} else if (type === 'Vega') {
				const spec = JSON.parse(content.data);
				const embed = (await import('vega-embed')).default;
				const div = document.createElement('div');
				div.style.position = 'absolute';
				div.style.left = '-9999px';
				div.style.width = '800px';
				div.style.height = '600px';
				document.body.appendChild(div);
				try {
					const specSized = {
						...spec, width: 760, height: 560,
						autosize: { type: 'fit', contains: 'padding' },
					};
					const result = await embed(div, specSized, { actions: false, renderer: 'canvas' });
					const canvas = await result.view.toCanvas(2);
					result.view.finalize();
					const dataUrl = canvas.toDataURL('image/png');
					const doc = new jsPDF({ orientation: 'landscape', unit: 'px', format: [800, 600] });
					doc.addImage(dataUrl, 'PNG', 0, 0, 800, 600);
					doc.save(`plot-${timestamp()}.pdf`);
					onexport?.(`exported plot-${timestamp()}.pdf`);
				} finally {
					try { document.body.removeChild(div); } catch {}
				}
			}
			close();
		} catch (e) {
			console.error('Failed to export PDF:', e);
			exportError = 'PDF export failed';
		} finally {
			exporting = false;
		}
	}

	const btnClass = 'w-full text-left text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] py-1 transition-colors';
</script>

<svelte:window
	onclick={open ? handleClickOutside : undefined}
	onkeydown={open ? (e) => { if (e.key === 'Escape') close(); } : undefined}
/>

<div class="relative export-menu">
	<button
		class="border border-[var(--color-border)] px-2 py-0.5 text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-text)] transition-colors"
		onclick={(e) => { e.stopPropagation(); open = !open; exportError = null; showSizeOptions = false; }}
	>[export]</button>

	{#if open}
		<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
		<div
			class="absolute right-0 top-full mt-1 z-50 border border-[var(--color-border)] bg-[var(--color-bg-raised)] p-3 min-w-[200px]"
			onclick={(e) => e.stopPropagation()}
		>
			{#if !showSizeOptions}
				{#if content}
					{#if content.type === 'Png'}
						<button class={btnClass} onclick={exportPng}>[PNG (original)]</button>
						<button class={btnClass} onclick={() => { showSizeOptions = true; }}>[PNG (custom size)]</button>
						<button class={btnClass} onclick={exportPdf} disabled={exporting}>[{exporting ? 'exporting...' : 'PDF'}]</button>
					{:else if content.type === 'Svg'}
						<button class={btnClass} onclick={exportSvg}>[SVG (original)]</button>
						<button class={btnClass} onclick={exportPdf} disabled={exporting}>[{exporting ? 'exporting...' : 'PDF'}]</button>
					{:else if content.type === 'Plotly'}
						<button class={btnClass} onclick={exportJson}>[JSON (data)]</button>
						<button class={btnClass} onclick={() => { showSizeOptions = true; }}>[PNG (custom size)]</button>
						<button class={btnClass} onclick={exportPdf} disabled={exporting}>[{exporting ? 'exporting...' : 'PDF'}]</button>
					{:else if content.type === 'Vega'}
						<button class={btnClass} onclick={exportJson}>[JSON (data)]</button>
						<button class={btnClass} onclick={() => { showSizeOptions = true; }}>[PNG (custom size)]</button>
						<button class={btnClass} onclick={exportPdf} disabled={exporting}>[{exporting ? 'exporting...' : 'PDF'}]</button>
					{:else if content.type === 'Html'}
						<button class={btnClass} onclick={exportHtml}>[HTML (source)]</button>
					{:else if content.type === 'ArrowIpc'}
						<button class={btnClass} onclick={exportArrowAsCsv}>[CSV (converted)]</button>
					{:else if content.type === 'Csv'}
						<button class={btnClass} onclick={exportCsv}>[CSV (original)]</button>
					{/if}
				{/if}
				{#if onsave || onopen}
					{#if content}
						<div class="border-t border-[var(--color-border)] my-2"></div>
					{/if}
					<div class="text-[11px] text-[var(--color-text-faint)] uppercase tracking-wider mb-1">session</div>
					{#if onsave && plotCount > 0}
						<button class={btnClass} onclick={() => { onsave?.(); close(); }}>[save .rvw]</button>
					{/if}
					{#if onopen}
						<button class={btnClass} onclick={() => { onopen?.(); close(); }}>[open .rvw]</button>
					{/if}
				{/if}
			{:else}
				<div class="text-[11px] text-[var(--color-text-faint)] uppercase tracking-wider mb-2">export size</div>

				<div class="flex gap-2 mb-2">
					<label class="flex flex-col gap-0.5">
						<span class="text-[10px] text-[var(--color-text-faint)]">width</span>
						<input
							type="number"
							bind:value={exportWidth}
							min="100"
							max="8000"
							class="w-16 border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] text-xs px-1.5 py-0.5"
						/>
					</label>
					<label class="flex flex-col gap-0.5">
						<span class="text-[10px] text-[var(--color-text-faint)]">height</span>
						<input
							type="number"
							bind:value={exportHeight}
							min="100"
							max="8000"
							class="w-16 border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] text-xs px-1.5 py-0.5"
						/>
					</label>
				</div>

				<div class="mb-2">
					<span class="text-[10px] text-[var(--color-text-faint)]">scale</span>
					<div class="flex flex-wrap gap-1 mt-0.5">
						{#each DPI_OPTIONS as opt}
							<button
								class={`text-[10px] border px-1.5 py-0.5 transition-colors ${
									exportDpi === opt.value
										? 'border-[var(--color-accent)] text-[var(--color-accent)]'
										: 'border-[var(--color-border)] text-[var(--color-text-faint)] hover:text-[var(--color-text-muted)]'
								}`}
								onclick={() => { exportDpi = opt.value; }}
							>{opt.label}</button>
						{/each}
					</div>
				</div>

				<div class="text-[10px] text-[var(--color-text-faint)] mb-2">
					output: {exportWidth * exportDpi} x {exportHeight * exportDpi} px
				</div>

				<div class="flex gap-2">
					<button
						class="text-xs border border-[var(--color-accent)] text-[var(--color-accent)] px-2 py-0.5 hover:bg-[var(--color-accent-muted)] transition-colors disabled:opacity-50"
						onclick={handleCustomExport}
						disabled={exporting}
					>{exporting ? '[exporting...]' : '[export PNG]'}</button>
					<button
						class="text-xs border border-[var(--color-border)] text-[var(--color-text-faint)] px-2 py-0.5 hover:text-[var(--color-text-muted)] transition-colors"
						onclick={() => { showSizeOptions = false; }}
					>[back]</button>
				</div>
			{/if}

			{#if exportError}
				<div class="text-[10px] text-[var(--color-error)] mt-1">{exportError}</div>
			{/if}
		</div>
	{/if}
</div>

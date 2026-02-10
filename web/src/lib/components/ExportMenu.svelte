<script lang="ts">
	import { tableFromIPC } from 'apache-arrow';

	type PlotContent =
		| { type: 'Png'; data: string }
		| { type: 'Svg'; data: string }
		| { type: 'Plotly'; data: string }
		| { type: 'Vega'; data: string }
		| { type: 'Html'; data: string }
		| { type: 'ArrowIpc'; data: string }
		| { type: 'Csv'; data: string };

	interface Props {
		content: PlotContent;
	}

	let { content }: Props = $props();

	let open = $state(false);

	function handleClickOutside(e: MouseEvent) {
		const target = e.target as HTMLElement;
		if (!target.closest('.export-menu')) {
			open = false;
		}
	}

	function downloadBlob(blob: Blob, filename: string) {
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = filename;
		a.click();
		URL.revokeObjectURL(url);
	}

	function exportPng() {
		const binary = atob(content.data);
		const bytes = new Uint8Array(binary.length);
		for (let i = 0; i < binary.length; i++) {
			bytes[i] = binary.charCodeAt(i);
		}
		downloadBlob(new Blob([bytes], { type: 'image/png' }), 'plot.png');
		open = false;
	}

	function exportSvg() {
		downloadBlob(new Blob([content.data], { type: 'image/svg+xml' }), 'plot.svg');
		open = false;
	}

	function exportJson() {
		downloadBlob(new Blob([content.data], { type: 'application/json' }), 'plot.json');
		open = false;
	}

	function exportHtml() {
		downloadBlob(new Blob([content.data], { type: 'text/html' }), 'plot.html');
		open = false;
	}

	function exportCsv() {
		downloadBlob(new Blob([content.data], { type: 'text/csv' }), 'data.csv');
		open = false;
	}

	function exportArrowAsCsv() {
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
			downloadBlob(new Blob([rows.join('\n')], { type: 'text/csv' }), 'data.csv');
		} catch (e) {
			console.error('Failed to convert Arrow IPC to CSV:', e);
		}
		open = false;
	}
</script>

<svelte:window
	onclick={open ? handleClickOutside : undefined}
	onkeydown={open ? (e) => { if (e.key === 'Escape') open = false; } : undefined}
/>

<div class="relative export-menu">
	<button
		class="border border-[var(--color-border)] px-2 py-0.5 text-[var(--color-text-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-text)] transition-colors"
		onclick={(e) => { e.stopPropagation(); open = !open; }}
	>[export]</button>

	{#if open}
		<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
		<div
			class="absolute right-0 top-full mt-1 z-50 border border-[var(--color-border)] bg-[var(--color-bg-raised)] p-3 min-w-[160px]"
			onclick={(e) => e.stopPropagation()}
		>
			{#if content.type === 'Png'}
				<button
					class="w-full text-left text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] py-1 transition-colors"
					onclick={exportPng}
				>[PNG (original)]</button>
			{:else if content.type === 'Svg'}
				<button
					class="w-full text-left text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] py-1 transition-colors"
					onclick={exportSvg}
				>[SVG (original)]</button>
			{:else if content.type === 'Plotly'}
				<button
					class="w-full text-left text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] py-1 transition-colors"
					onclick={exportJson}
				>[JSON (data)]</button>
			{:else if content.type === 'Vega'}
				<button
					class="w-full text-left text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] py-1 transition-colors"
					onclick={exportJson}
				>[JSON (data)]</button>
			{:else if content.type === 'Html'}
				<button
					class="w-full text-left text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] py-1 transition-colors"
					onclick={exportHtml}
				>[HTML (source)]</button>
			{:else if content.type === 'ArrowIpc'}
				<button
					class="w-full text-left text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] py-1 transition-colors"
					onclick={exportArrowAsCsv}
				>[CSV (converted)]</button>
			{:else if content.type === 'Csv'}
				<button
					class="w-full text-left text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] py-1 transition-colors"
					onclick={exportCsv}
				>[CSV (original)]</button>
			{/if}
		</div>
	{/if}
</div>

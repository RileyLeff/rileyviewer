<script lang="ts">
	import { tableFromIPC } from 'apache-arrow';

	interface Props {
		data: string;
		format: 'ArrowIpc' | 'Csv';
	}

	let { data, format }: Props = $props();

	const ROW_HEIGHT = 28;
	const OVERSCAN = 10;

	type SortDir = 'asc' | 'desc' | 'none';

	let sortCol: number | null = $state(null);
	let sortDir: SortDir = $state('none');
	let scrollTop = $state(0);
	let containerHeight = $state(0);

	// Parse data into columns + rows
	let parsed = $derived.by(() => {
		if (format === 'ArrowIpc') {
			return parseArrow(data);
		}
		return parseCsv(data);
	});

	// Sorted index array — sort indices, not data
	let sortedIndices = $derived.by(() => {
		const rowCount = parsed.rows.length;
		const indices = Array.from({ length: rowCount }, (_, i) => i);

		if (sortCol === null || sortDir === 'none') {
			return indices;
		}

		const col = sortCol;
		const dir = sortDir;

		indices.sort((a, b) => {
			const va = parsed.rows[a][col];
			const vb = parsed.rows[b][col];

			// nulls always sort last
			const aNull = va == null || (typeof va === 'number' && isNaN(va));
			const bNull = vb == null || (typeof vb === 'number' && isNaN(vb));
			if (aNull && bNull) return 0;
			if (aNull) return 1;
			if (bNull) return -1;

			if (typeof va === 'number' && typeof vb === 'number') {
				return dir === 'asc' ? va - vb : vb - va;
			}

			const sa = String(va);
			const sb = String(vb);
			const cmp = sa.localeCompare(sb);
			return dir === 'asc' ? cmp : -cmp;
		});

		return indices;
	});

	// Virtual scroll calculations
	let totalHeight = $derived(sortedIndices.length * ROW_HEIGHT);

	let startIdx = $derived(
		Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN)
	);

	let endIdx = $derived(
		Math.min(
			sortedIndices.length,
			Math.floor(scrollTop / ROW_HEIGHT) + Math.ceil(containerHeight / ROW_HEIGHT) + OVERSCAN
		)
	);

	let offsetY = $derived(startIdx * ROW_HEIGHT);

	let visibleRows = $derived(
		sortedIndices.slice(startIdx, endIdx).map((idx) => ({
			idx,
			cells: parsed.rows[idx]
		}))
	);

	// Detect which columns are numeric
	let colIsNumeric = $derived.by(() => {
		return parsed.columns.map((_, ci) => {
			for (let ri = 0; ri < Math.min(parsed.rows.length, 100); ri++) {
				const v = parsed.rows[ri][ci];
				if (v != null && typeof v !== 'number') return false;
			}
			return true;
		});
	});

	function parseArrow(b64: string): { columns: string[]; rows: any[][] } {
		try {
			const binary = atob(b64);
			const bytes = new Uint8Array(binary.length);
			for (let i = 0; i < binary.length; i++) {
				bytes[i] = binary.charCodeAt(i);
			}
			const table = tableFromIPC(bytes);
			const columns = table.schema.fields.map((f) => f.name);
			const rows: any[][] = [];
			for (let r = 0; r < table.numRows; r++) {
				const row: any[] = [];
				for (let c = 0; c < table.numCols; c++) {
					const col = table.getChildAt(c);
					row.push(col ? col.get(r) : null);
				}
				rows.push(row);
			}
			return { columns, rows };
		} catch (e) {
			console.error('Failed to parse Arrow IPC:', e);
			return { columns: ['error'], rows: [[String(e)]] };
		}
	}

	function parseCsv(text: string): { columns: string[]; rows: any[][] } {
		const lines = text.split('\n').filter((l) => l.trim().length > 0);
		if (lines.length === 0) return { columns: [], rows: [] };
		const columns = lines[0].split(',').map((h) => h.trim());
		const rows: any[][] = [];
		for (let i = 1; i < lines.length; i++) {
			const cells = lines[i].split(',').map((c) => {
				const trimmed = c.trim();
				if (trimmed === '') return null;
				const num = Number(trimmed);
				if (!isNaN(num) && trimmed !== '') return num;
				return trimmed;
			});
			rows.push(cells);
		}
		return { columns, rows };
	}

	function handleSort(colIndex: number) {
		if (sortCol === colIndex) {
			if (sortDir === 'asc') sortDir = 'desc';
			else if (sortDir === 'desc') { sortDir = 'none'; sortCol = null; }
			else { sortDir = 'asc'; }
		} else {
			sortCol = colIndex;
			sortDir = 'asc';
		}
	}

	function formatCell(value: any): string {
		if (value == null) return 'null';
		if (typeof value === 'number' && isNaN(value)) return 'null';
		if (typeof value === 'number') {
			if (Number.isInteger(value)) return value.toLocaleString();
			return value.toLocaleString(undefined, { maximumFractionDigits: 6 });
		}
		const s = String(value);
		if (s.length > 100) return s.slice(0, 97) + '...';
		return s;
	}

	function isNullish(value: any): boolean {
		return value == null || (typeof value === 'number' && isNaN(value));
	}

	function handleScroll(e: Event) {
		const target = e.target as HTMLElement;
		scrollTop = target.scrollTop;
	}

	function sortIndicator(colIndex: number): string {
		if (sortCol !== colIndex || sortDir === 'none') return '';
		return sortDir === 'asc' ? ' \u25B2' : ' \u25BC';
	}
</script>

<div class="data-table-root">
	<div class="header-row">
		{#each parsed.columns as col, ci (ci)}
			<button
				class="header-cell"
				class:numeric={colIsNumeric[ci]}
				class:sorted={sortCol === ci && sortDir !== 'none'}
				onclick={() => handleSort(ci)}
			>
				{col}{sortIndicator(ci)}
			</button>
		{/each}
	</div>

	<div
		class="scroll-container"
		bind:clientHeight={containerHeight}
		onscroll={handleScroll}
	>
		<div class="scroll-spacer" style:height="{totalHeight}px">
			<div class="visible-rows" style:transform="translateY({offsetY}px)">
				{#each visibleRows as row (row.idx)}
					<div class="data-row">
						{#each row.cells as cell, ci (ci)}
							<div
								class="data-cell"
								class:numeric={colIsNumeric[ci]}
								class:null-value={isNullish(cell)}
							>
								{formatCell(cell)}
							</div>
						{/each}
					</div>
				{/each}
			</div>
		</div>
	</div>

	<div class="footer">
		{sortedIndices.length.toLocaleString()} rows x {parsed.columns.length} cols
	</div>
</div>

<style>
	.data-table-root {
		width: 100%;
		height: 100%;
		display: flex;
		flex-direction: column;
		background: var(--color-bg-canvas);
		border: 1px solid var(--color-border);
		overflow: hidden;
	}

	.header-row {
		display: flex;
		flex-shrink: 0;
		border-bottom: 1px solid var(--color-border);
		background: var(--color-bg-raised, var(--color-bg-canvas));
	}

	.header-cell {
		flex: 1 1 0;
		min-width: 80px;
		height: 28px;
		padding: 0 8px;
		display: flex;
		align-items: center;
		border: none;
		border-right: 1px solid var(--color-border);
		background: none;
		color: var(--color-text-muted);
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		cursor: pointer;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.header-cell:last-child {
		border-right: none;
	}

	.header-cell:hover {
		color: var(--color-text);
	}

	.header-cell.numeric {
		justify-content: flex-end;
	}

	.header-cell.sorted {
		color: var(--color-accent);
	}

	.scroll-container {
		flex: 1 1 0;
		overflow-y: auto;
		overflow-x: auto;
		scrollbar-width: thin;
		scrollbar-color: var(--color-border) transparent;
	}

	.scroll-spacer {
		position: relative;
		width: 100%;
	}

	.visible-rows {
		position: absolute;
		top: 0;
		left: 0;
		width: 100%;
	}

	.data-row {
		display: flex;
		height: 28px;
		border-bottom: 1px solid var(--color-border);
	}

	.data-row:hover {
		background: var(--color-accent-muted);
	}

	.data-cell {
		flex: 1 1 0;
		min-width: 80px;
		height: 28px;
		padding: 0 8px;
		display: flex;
		align-items: center;
		border-right: 1px solid var(--color-border);
		color: var(--color-text);
		font-size: 13px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.data-cell:last-child {
		border-right: none;
	}

	.data-cell.numeric {
		justify-content: flex-end;
		font-variant-numeric: tabular-nums;
	}

	.data-cell.null-value {
		color: var(--color-text-faint);
		font-style: italic;
	}

	.footer {
		flex-shrink: 0;
		height: 24px;
		padding: 0 8px;
		display: flex;
		align-items: center;
		border-top: 1px solid var(--color-border);
		background: var(--color-bg-raised, var(--color-bg-canvas));
		color: var(--color-text-faint);
		font-size: 11px;
	}
</style>

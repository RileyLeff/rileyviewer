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

	/** Unified parsed data interface: lazy (Arrow) or eager (CSV) */
	interface ParsedData {
		columns: string[];
		rowCount: number;
		getCell: (row: number, col: number) => any;
	}

	let sortCol: number | null = $state(null);
	let sortDir: SortDir = $state('none');
	let scrollTop = $state(0);
	let containerHeight = $state(0);

	// Parse data into columns + lazy cell accessor
	let parsed: ParsedData = $derived.by(() => {
		if (format === 'ArrowIpc') {
			return parseArrow(data);
		}
		return parseCsv(data);
	});

	// Sorted index array — sort indices, not data
	let sortedIndices = $derived.by(() => {
		const indices = Array.from({ length: parsed.rowCount }, (_, i) => i);

		if (sortCol === null || sortDir === 'none') {
			return indices;
		}

		const col = sortCol;
		const dir = sortDir;
		const { getCell } = parsed;

		indices.sort((a, b) => {
			const va = getCell(a, col);
			const vb = getCell(b, col);

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
		sortedIndices.slice(startIdx, endIdx).map((idx) => {
			const cells: any[] = [];
			for (let ci = 0; ci < parsed.columns.length; ci++) {
				cells.push(parsed.getCell(idx, ci));
			}
			return { idx, cells };
		})
	);

	// Detect which columns are numeric (sample first 100 rows)
	let colIsNumeric = $derived.by(() => {
		const sampleCount = Math.min(parsed.rowCount, 100);
		return parsed.columns.map((_, ci) => {
			for (let ri = 0; ri < sampleCount; ri++) {
				const v = parsed.getCell(ri, ci);
				if (v != null && typeof v !== 'number') return false;
			}
			return true;
		});
	});

	/**
	 * Parse Arrow IPC (base64-encoded) into a lazy accessor.
	 * Keeps the Arrow Table reference and reads cells on demand,
	 * avoiding materialization of all rows into JS arrays.
	 */
	function parseArrow(b64: string): ParsedData {
		try {
			const binary = atob(b64);
			const bytes = new Uint8Array(binary.length);
			for (let i = 0; i < binary.length; i++) {
				bytes[i] = binary.charCodeAt(i);
			}
			const table = tableFromIPC(bytes);
			const columns = table.schema.fields.map((f) => f.name);
			return {
				columns,
				rowCount: table.numRows,
				getCell(row: number, col: number): any {
					const child = table.getChildAt(col);
					return child ? child.get(row) : null;
				}
			};
		} catch (e) {
			console.error('Failed to parse Arrow IPC:', e);
			return {
				columns: ['error'],
				rowCount: 1,
				getCell(): any {
					return String(e);
				}
			};
		}
	}

	/**
	 * Parse CSV text with RFC 4180 basic quoting support.
	 * - Fields enclosed in double quotes can contain commas and newlines.
	 * - Double quotes inside quoted fields are escaped as "".
	 * Materializes rows eagerly (CSV data is already strings, no duplication concern).
	 */
	function parseCsv(text: string): ParsedData {
		const rows = parseCsvRows(text);
		if (rows.length === 0) {
			return { columns: [], rowCount: 0, getCell: () => null };
		}
		const columns = rows[0].map((h) => h.trim());
		const dataRows: any[][] = [];
		for (let i = 1; i < rows.length; i++) {
			const cells = rows[i].map((c) => {
				const trimmed = c.trim();
				if (trimmed === '') return null;
				const num = Number(trimmed);
				if (!isNaN(num) && trimmed !== '') return num;
				return trimmed;
			});
			dataRows.push(cells);
		}
		return {
			columns,
			rowCount: dataRows.length,
			getCell(row: number, col: number): any {
				const r = dataRows[row];
				return r ? r[col] ?? null : null;
			}
		};
	}

	/**
	 * Low-level CSV row parser handling RFC 4180 quoting.
	 * Returns an array of rows, each row an array of raw string fields.
	 */
	function parseCsvRows(text: string): string[][] {
		const rows: string[][] = [];
		let row: string[] = [];
		let field = '';
		let inQuotes = false;
		let i = 0;

		while (i < text.length) {
			const ch = text[i];

			if (inQuotes) {
				if (ch === '"') {
					// Look ahead: doubled quote is an escaped quote
					if (i + 1 < text.length && text[i + 1] === '"') {
						field += '"';
						i += 2;
					} else {
						// End of quoted field
						inQuotes = false;
						i++;
					}
				} else {
					field += ch;
					i++;
				}
			} else {
				if (ch === '"') {
					inQuotes = true;
					i++;
				} else if (ch === ',') {
					row.push(field);
					field = '';
					i++;
				} else if (ch === '\r') {
					// Handle \r\n or lone \r as row terminator
					row.push(field);
					field = '';
					if (row.some((f) => f.trim().length > 0)) {
						rows.push(row);
					}
					row = [];
					if (i + 1 < text.length && text[i + 1] === '\n') {
						i += 2;
					} else {
						i++;
					}
				} else if (ch === '\n') {
					row.push(field);
					field = '';
					if (row.some((f) => f.trim().length > 0)) {
						rows.push(row);
					}
					row = [];
					i++;
				} else {
					field += ch;
					i++;
				}
			}
		}

		// Handle last field/row if file doesn't end with newline
		if (field.length > 0 || row.length > 0) {
			row.push(field);
			if (row.some((f) => f.trim().length > 0)) {
				rows.push(row);
			}
		}

		return rows;
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

export type PlotContent =
	| { type: 'Png'; data: string }
	| { type: 'Svg'; data: string }
	| { type: 'Plotly'; data: string }
	| { type: 'Vega'; data: string }
	| { type: 'Html'; data: string }
	| { type: 'ArrowIpc'; data: string }
	| { type: 'Csv'; data: string };

export type PlotMessage = {
	id: string;
	timestamp: number;
	content: PlotContent;
	title?: string;
	notes?: string;
	tags?: string[];
};

export type MetadataUpdate = {
	kind: 'metadata_update';
	id: string;
	title?: string | null;
	notes?: string | null;
	tags?: string[];
};

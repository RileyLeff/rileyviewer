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
};

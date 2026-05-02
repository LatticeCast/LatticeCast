export type BlockKind = 'chart' | 'number' | 'list';

export interface LayoutEntry {
	id: string;
	x: number;
	y: number;
	w: number;
	h: number;
}

export interface ChartBlock {
	kind: 'chart';
	title: string;
	lql: string;
	echarts: Record<string, unknown>;
}

export interface NumberBlock {
	kind: 'number';
	title: string;
	lql: string;
	field: string;
	format?: string;
}

export interface ListColumn {
	key: string;
	label: string;
}

export interface ListBlock {
	kind: 'list';
	title: string;
	lql: string;
	columns: ListColumn[];
}

export type Block = ChartBlock | NumberBlock | ListBlock;

export interface DashboardConfig {
	layout: LayoutEntry[];
	blocks: Record<string, Block>;
}

export interface DashboardView {
	name: string;
	type: 'dashboard';
	config: DashboardConfig;
}

export type BlockRow = Record<string, unknown>;

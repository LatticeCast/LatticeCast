export type ChartKind = 'number' | 'bar' | 'pie' | 'line' | 'list';

export interface WidgetBinding {
	x?: string;
	y?: string;
	label?: string;
	value?: string;
}

export interface Widget {
	title: string;
	chart: ChartKind;
	lql: string;
	binding: WidgetBinding;
}

export interface DashboardLayoutItem {
	widget_id: string;
	x: number;
	y: number;
	w: number;
	h: number;
}

export interface DashboardConfig {
	layout: DashboardLayoutItem[];
	widgets: Record<string, Widget>;
}

export interface DashboardView {
	name: string;
	type: 'dashboard';
	config: DashboardConfig;
}

export type WidgetRow = Record<string, unknown>;

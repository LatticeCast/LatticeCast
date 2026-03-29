// src/lib/types/table.ts

export type ColumnType =
	| 'text'
	| 'string'
	| 'number'
	| 'date'
	| 'select'
	| 'tags'
	| 'checkbox'
	| 'url';

export interface ColumnChoice {
	value: string;
	color: string;
}

export interface ColumnOptions {
	choices?: ColumnChoice[];
	width?: number;
}

export interface Workspace {
	workspace_id: string;
	name: string;
	created_at: string;
	updated_at: string;
}

export interface WorkspaceMember {
	workspace_id: string;
	user_id: string;
	role: string;
}

export interface Table {
	table_id: string;
	workspace_id: string;
	name: string;
	columns: Column[];
	views: ViewConfig[];
	created_at: string;
	updated_at: string;
}

export interface Column {
	column_id: string;
	name: string;
	type: ColumnType;
	options: ColumnOptions;
	position: number;
	created_at: string;
}

export interface Row {
	row_id: string;
	table_id: string;
	row_data: Record<string, unknown>;
	created_by: string;
	updated_by: string;
	created_at: string;
	updated_at: string;
}

export interface CreateTable {
	name: string;
	workspace_id: string;
}

export interface CreateColumn {
	name: string;
	type: ColumnType;
	options?: ColumnOptions;
	position?: number;
}

export interface CreateRow {
	row_data: Record<string, unknown>;
}

export interface UpdateTable {
	name?: string;
}

export interface UpdateColumn {
	name?: string;
	type?: ColumnType;
	options?: ColumnOptions;
	position?: number;
}

export interface UpdateRow {
	row_data: Record<string, unknown>;
}

export interface ViewConfig {
	name: string;
	type: 'table' | 'kanban' | 'timeline';
	config: Record<string, unknown>;
}

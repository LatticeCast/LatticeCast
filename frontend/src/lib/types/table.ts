// src/lib/types/table.ts

export type ColumnType = 'text' | 'string' | 'number' | 'date' | 'select' | 'tags' | 'checkbox' | 'url';

export interface ColumnChoice {
	value: string;
	color: string;
}

export interface ColumnOptions {
	choices?: ColumnChoice[];
	width?: number;
}

export interface Table {
	id: string;
	user_id: string;
	name: string;
	created_at: string;
	updated_at: string;
}

export interface Column {
	id: string;
	table_id: string;
	name: string;
	type: ColumnType;
	options: ColumnOptions;
	position: number;
	created_at: string;
}

export interface Row {
	id: string;
	table_id: string;
	data: Record<string, unknown>;
	created_at: string;
	updated_at: string;
}

export interface CreateTable {
	name: string;
}

export interface CreateColumn {
	name: string;
	type: ColumnType;
	options?: ColumnOptions;
	position?: number;
}

export interface CreateRow {
	data: Record<string, unknown>;
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
	data: Record<string, unknown>;
}

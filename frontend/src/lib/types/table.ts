// src/lib/types/table.ts

/** UUID string — always a 36-char hyphenated UUID, never a user_name or row_number */
export type UUID = string;

export type ColumnType =
	| 'text'
	| 'string'
	| 'number'
	| 'date'
	| 'select'
	| 'tags'
	| 'checkbox'
	| 'url'
	| 'doc';

export interface ColumnChoice {
	value: string;
	color: string;
}

export interface ColumnOptions {
	choices?: ColumnChoice[];
	width?: number;
}

export interface Workspace {
	workspace_id: UUID;
	workspace_name: string;
	created_at: string;
	updated_at: string;
}

export interface WorkspaceMember {
	workspace_id: UUID;
	user_id: UUID;
	role: string;
}

export interface Table {
	table_id: UUID;
	workspace_id: UUID;
	table_name: string;
	columns: Column[];
	views: ViewConfig[];
	created_at: string;
	updated_at: string;
}

export interface Column {
	column_id: UUID;
	name: string;
	type: ColumnType;
	options: ColumnOptions;
	position: number;
	created_at: string;
}

export interface Row {
	table_id: UUID;
	row_number: number;
	row_data: Record<UUID, unknown>;
	created_by: UUID | null;
	updated_by: UUID | null;
	created_at: string;
	updated_at: string;
}

export interface CreateTable {
	table_name: string;
	workspace_id: UUID;
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
	table_name?: string;
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

// src/lib/types/table.ts

/** UUID string — always a 36-char hyphenated UUID, never a user_name or row_id */
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

export interface WorkspaceMemberFull {
	workspace_id: UUID;
	user_id: UUID;
	user_name: string | null;
	email: string | null;
	role: string;
}

export interface Table {
	table_id: string;
	workspace_id: UUID;
	columns: Column[];
	view_order: string[];
	default_view?: string | null;
	views?: ViewConfig[];
	created_at: string;
	updated_at: string;
}

export interface Column {
	column_id: UUID;
	name: string;
	type: ColumnType;
	options: ColumnOptions;
	created_at: string;
}

/** Server-authoritative schema snapshot. Every mutation endpoint on
 * views / columns / orders / default-view returns this shape, so the FE
 * replaces its local store from the response and never derives schema
 * state locally. */
export interface TableSchema {
	columns: Column[];
	view_order: string[];
	default_view: string | null;
}

export interface Row {
	table_id: string;
	row_id: number;
	row_data: Record<UUID, unknown>;
	created_by: UUID | null;
	updated_by: UUID | null;
	created_at: string;
	updated_at: string;
}

export interface CreateTable {
	table_id: string;
	workspace_id: UUID;
}

export interface CreateColumn {
	name: string;
	type: ColumnType;
	options?: ColumnOptions;
}

export interface CreateRow {
	row_data: Record<string, unknown>;
}

export interface UpdateTable {
	table_id?: string;
}

export interface UpdateColumn {
	name?: string;
	type?: ColumnType;
	options?: ColumnOptions;
}

export interface UpdateRow {
	row_data: Record<string, unknown>;
}

export type ViewType = 'table' | 'kanban' | 'timeline' | 'dashboard';

export interface ViewConfig {
	name: string;
	type: ViewType;
	config: Record<string, unknown>;
}

export interface UpdateView {
	name?: string;
	type?: ViewType;
	config?: Record<string, unknown>;
}

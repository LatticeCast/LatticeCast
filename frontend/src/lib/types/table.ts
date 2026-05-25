// src/lib/types/table.ts
//
// Shared contract: PG → BE (passthrough) → FE.
// These types mirror the exact JSON shape returned by PG functions.
// BE does NOT transform the data — it passes PG output directly.
// FE stores these shapes as-is in SSOT stores.

/** UUID string — always a 36-char hyphenated UUID */
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

// ─── PG output shapes (BE passthrough) ────────────────────────────────────────

/** Single column definition — from PG table_schemas.config.columns[] */
export interface Column {
	column_id: UUID;
	name: string;
	type: ColumnType;
	options: ColumnOptions;
	created_at: string;
}

/** View config — from PG table_views rows assembled by get_table_schema() */
export interface ViewConfig {
	view_id: number;
	name: string;
	type: ViewType;
	config: Record<string, unknown>;
}

/** Full table schema — returned by ALL schema-mutating PG functions.
 * This is THE shared contract: PG returns it, BE passes through, FE stores as-is. */
export interface TableSchema {
	columns: Column[];
	view_order: number[];
	default_view: number | null;
	views: ViewConfig[];
}

/** Single row — from PG rows table via get_rows() */
export interface Row {
	table_id: string;
	row_id: number;
	row_data: Record<UUID, unknown>;
	created_by: UUID | null;
	updated_by: UUID | null;
	created_at: string;
	updated_at: string;
}

/** Full table response — from PG get_table() / BE GET /tables/{tid} */
export interface Table {
	table_id: string;
	workspace_id: UUID;
	columns: Column[];
	view_order: number[];
	default_view?: number | null;
	views?: ViewConfig[];
	created_at: string;
	updated_at: string;
}

/** Workspace — from PG workspaces table */
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

// ─── Request types (FE → BE → PG) ────────────────────────────────────────────

export type ViewType = 'table' | 'kanban' | 'timeline' | 'dashboard' | 'workflow';

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

export interface UpdateView {
	name?: string;
	type?: ViewType;
	config?: Record<string, unknown>;
}

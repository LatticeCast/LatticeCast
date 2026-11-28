import type {
	BlobCellMetadata,
	BlobKind,
	Column,
	ColumnChoice,
	ColumnReading,
	ColumnType,
	Row
} from '$lib/types/table';
import {
	formatTemporal,
	fromInput,
	temporalGroupKey,
	toEpochMs,
	type TemporalType
} from '$lib/utils/temporal';
import { currentZone } from '$lib/stores/settings.store';

/** The readings whose cells hold an epoch-millisecond instant. */
export function isTemporalType(reading: ColumnReading): reading is TemporalType {
	return reading === 'date' || reading === 'datetime';
}

/**
 * How this client reads a column. The database knows only the storage type;
 * `options.display` says which reading of it the user chose.
 */
export function readAs(column: Pick<Column, 'type' | 'options'>): ColumnReading {
	const display = column.options?.display;
	switch (column.type) {
		case 'text':
			return display === 'url' || display === 'select' ? display : 'text';
		case 'int':
			return display === 'date' || display === 'datetime' ? display : 'number';
		case 'double':
			return 'number';
		case 'strings':
			// An array of strings: tags unless the column says it is a checkbox (T, F).
			return display === 'checkbox' ? 'checkbox' : 'tags';
		default:
			return column.type;
	}
}

/** What the add-column dialog offers: a reading, and the storage type + display that make it. */
export const COLUMN_CHOICES: ReadonlyArray<{
	key: string;
	label: string;
	type: ColumnType;
	display?: string;
}> = [
	{ key: 'text', label: 'text', type: 'text' },
	{ key: 'url', label: 'url', type: 'text', display: 'url' },
	{ key: 'select', label: 'select', type: 'text', display: 'select' },
	{ key: 'checkbox', label: 'checkbox', type: 'strings', display: 'checkbox' },
	{ key: 'int', label: 'integer', type: 'int' },
	{ key: 'double', label: 'decimal', type: 'double' },
	{ key: 'date', label: 'date', type: 'int', display: 'date' },
	{ key: 'datetime', label: 'datetime', type: 'int', display: 'datetime' },
	{ key: 'tags', label: 'tags', type: 'strings' },
	{ key: 'blob', label: 'file', type: 'blob' }
];

/** The date or datetime reading of a column, or null when it is read as something else. */
export function temporalReading(column: Pick<Column, 'type' | 'options'>): TemporalType | null {
	const reading = readAs(column);
	return isTemporalType(reading) ? reading : null;
}

/** The choice a keyword names, as in a CSV header `Name{{keyword}}`. `number` is a decimal; an unknown keyword is text. */
export function columnChoice(key: string): (typeof COLUMN_CHOICES)[number] {
	const wanted = key === 'number' ? 'double' : key;
	return COLUMN_CHOICES.find((choice) => choice.key === wanted) ?? COLUMN_CHOICES[0];
}

/** A checkbox is a strings cell: ['T'] when checked, ['F'] when not. */
export const CHECKED = 'T';
export const UNCHECKED = 'F';

export function isChecked(value: unknown): boolean {
	return Array.isArray(value) && value.includes(CHECKED);
}

/** The cell to store for a checkbox state. */
export function checkboxCell(checked: boolean): string[] {
	return [checked ? CHECKED : UNCHECKED];
}

/** Fixed single-file blob categories. The UI selects a category, never a free-form accept string. */
export const BLOB_KIND_OPTIONS: ReadonlyArray<{
	value: BlobKind;
	label: string;
	description: string;
	accept?: string;
}> = [
	{
		value: 'text',
		label: 'Text',
		description: 'Plain text, Markdown, or CSV',
		accept: '.md,.txt,.csv,text/markdown,text/plain,text/csv'
	},
	{
		value: 'table',
		label: 'Table data',
		description: 'CSV, Excel, JSON Lines',
		accept:
			'.csv,.xlsx,.jsonl,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/x-ndjson,application/jsonl'
	},
	{ value: 'image', label: 'Image', description: 'Any image file', accept: 'image/*' },
	{
		value: 'file',
		label: 'File / Binary',
		description: 'Any single file, including ZIP and other binary data'
	}
];

/** Display the concrete content type for blob columns instead of the storage implementation. */
export function getColumnTypeLabel(column: Pick<Column, 'type' | 'options'>): string {
	if (column.type === 'blob') return column.options?.kind ?? 'file';
	const reading = readAs(column);
	return reading === 'number' ? column.type : reading;
}

export interface FilterCondition {
	id: string;
	colId: string;
	operator: 'contains' | 'equals' | 'is_empty' | 'not_empty';
	value: string;
}

export interface ContextMenuState {
	type: 'row' | 'col';
	id: string;
	x: number;
	y: number;
}

export interface GroupHeaderItem {
	type: 'group-header';
	key: string;
	count: number;
	col: Column;
}

export interface DataRowItem {
	type: 'row';
	row: Row;
	rowIdx: number;
}

export interface GroupAddItem {
	type: 'group-add';
	key: string;
	col: Column;
}

export type RenderItem = GroupHeaderItem | DataRowItem | GroupAddItem;

export function getItemKey(item: RenderItem): string {
	if (item.type === 'row') return 'row-' + item.row.row_id;
	return item.type + '-' + item.key;
}

export function getCellValue(
	row: { row_data: Record<string, unknown> },
	colId: string,
	colType?: ColumnReading
): string {
	const val = row.row_data[colId];
	if (val === null || val === undefined) return '';
	if (colType === 'checkbox') return isChecked(val) ? '✓' : '';
	if (isBlobCellMetadata(val)) return val.filename;
	if (colType && isTemporalType(colType)) return formatCellDate(val, colType);
	return String(val);
}

/** Return true only for the storage descriptor written to blob cells. */
export function isBlobCellMetadata(value: unknown): value is BlobCellMetadata {
	if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
	const metadata = value as Record<string, unknown>;
	return (
		typeof metadata.key === 'string' &&
		typeof metadata.filename === 'string' &&
		typeof metadata.content_type === 'string' &&
		typeof metadata.size === 'number'
	);
}

/** Read a blob cell without duplicating metadata in component-local state. */
export function getBlobCellMetadata(
	row: { row_data: Record<string, unknown> },
	colId: string
): BlobCellMetadata | null {
	const value = row.row_data[colId];
	return isBlobCellMetadata(value) ? value : null;
}

/** Compact, human-readable size for a blob metadata label. */
export function formatBlobSize(size: number): string {
	if (!Number.isFinite(size) || size < 0) return '';
	if (size < 1024) return `${size} B`;
	if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
	return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function getChoices(col: Column): ColumnChoice[] {
	const choices = col.options?.choices;
	if (!Array.isArray(choices)) return [];
	return choices as ColumnChoice[];
}

export interface ChoiceStyle {
	cls: string;
	style: string;
}

export function colorToStyle(color: string): ChoiceStyle {
	if (!color)
		return {
			cls: '',
			style: 'background-color: #9ca3af20; color: #9ca3af; border-color: #9ca3af;'
		};
	const hex = color.startsWith('#') ? color : '#9ca3af';
	return {
		cls: '',
		style: `background-color: ${hex}20; color: ${hex}; border-color: ${hex};`
	};
}

export function getChoiceColor(col: Column, value: string): ChoiceStyle {
	const choices = getChoices(col);
	const choice = choices.find((c) => c.value === value);
	return colorToStyle(choice?.color ?? '');
}

export function getTagValues(row: { row_data: Record<string, unknown> }, colId: string): string[] {
	const val = row.row_data[colId];
	return Array.isArray(val) ? (val as string[]) : [];
}

export function sortLabels(type: ColumnReading): { asc: string; desc: string } {
	switch (type) {
		case 'number':
			return { asc: 'Ascending (1 → 9)', desc: 'Descending (9 → 1)' };
		case 'date':
		case 'datetime':
			return { asc: 'Oldest first', desc: 'Newest first' };
		case 'select':
		case 'tags':
			return { asc: 'Defined order', desc: 'Reverse defined order' };
		case 'checkbox':
			return { asc: 'Unchecked first', desc: 'Checked first' };
		default:
			return { asc: 'A → Z', desc: 'Z → A' };
	}
}

/**
 * Never alters what was typed: a fraction in an int column goes to the server,
 * which refuses it. Only values JavaScript cannot carry are rejected here.
 */
function parseNumber(text: string, type: ColumnType): number | null {
	if (text.trim() === '') return null;
	const n = Number(text);
	if (!Number.isFinite(n)) throw new Error(`"${text}" is not a number`);
	if (type === 'int' && Number.isInteger(n) && !Number.isSafeInteger(n))
		throw new Error(`"${text}" is too large to edit without losing digits`);
	return n;
}

/** Parse a string edit value into what the column stores, by how the column is read. */
export function parseEditValue(editVal: string, column: Pick<Column, 'type' | 'options'>): unknown {
	const colType = readAs(column);
	if (colType === 'number') return parseNumber(editVal, column.type);
	if (colType === 'checkbox') return checkboxCell(editVal === 'true');
	if (isTemporalType(colType)) return fromInput(editVal, colType, currentZone());
	if (editVal === '') return null;
	return editVal;
}

/** Return new row_data with the edit applied (parsed by column type). */
export function applyEditToRowData(
	rowData: Record<string, unknown>,
	colId: string,
	editVal: string,
	column: Pick<Column, 'type' | 'options'>
): Record<string, unknown> {
	return { ...rowData, [colId]: parseEditValue(editVal, column) };
}

/** Return new row_data with the checkbox toggled. */
export function toggleCheckboxInRowData(
	rowData: Record<string, unknown>,
	colId: string
): Record<string, unknown> {
	return { ...rowData, [colId]: checkboxCell(!isChecked(rowData[colId])) };
}

/** Return new row_data with the tag removed (no-op if not present). */
export function removeTagFromRowData(
	rowData: Record<string, unknown>,
	colId: string,
	tag: string
): Record<string, unknown> {
	const current = Array.isArray(rowData[colId]) ? (rowData[colId] as string[]) : [];
	return { ...rowData, [colId]: current.filter((t) => t !== tag) };
}

/** Return new row_data with the tag added (no-op if already present). */
export function addTagToRowData(
	rowData: Record<string, unknown>,
	colId: string,
	tag: string
): Record<string, unknown> {
	const current = Array.isArray(rowData[colId]) ? (rowData[colId] as string[]) : [];
	if (current.includes(tag)) return rowData;
	return { ...rowData, [colId]: [...current, tag] };
}

/**
 * Display text for a temporal cell, read in the user's configured zone.
 *
 * Replaces the old tolerant parser. That one accepted five shapes and passed
 * anything else through unchanged, which is why an epoch-millisecond value
 * rendered as the raw number 1798675200000 — thirteen digits matched none of
 * its patterns and fell to `return raw`.
 */
/** Format an epoch-ms cell. A reading that is not a datetime is shown as a date. */
export function formatCellDate(value: unknown, reading: ColumnReading = 'date'): string {
	const type: TemporalType = reading === 'datetime' ? 'datetime' : 'date';
	return formatTemporal(value, type, currentZone());
}

// ─── Filter / Sort / Group / Render ──────────────────────────────────────────

export function applyFilters(
	rowList: Row[],
	filterConditions: FilterCondition[],
	searchQuery: string
): Row[] {
	let result = rowList;
	if (searchQuery.trim()) {
		const q = searchQuery.trim().toLowerCase();
		result = result.filter((r) =>
			Object.values(r.row_data).some((v) => {
				if (v === null || v === undefined) return false;
				if (Array.isArray(v)) return v.some((item) => String(item).toLowerCase().includes(q));
				return String(v).toLowerCase().includes(q);
			})
		);
	}
	for (const cond of filterConditions) {
		if (!cond.colId) continue;
		if (cond.operator !== 'is_empty' && cond.operator !== 'not_empty' && !cond.value.trim())
			continue;
		const lv = cond.value.toLowerCase();
		result = result.filter((r) => {
			const cell = r.row_data[cond.colId];
			const isEmpty =
				cell === null ||
				cell === undefined ||
				(typeof cell === 'string' && cell === '') ||
				(Array.isArray(cell) && cell.length === 0);
			if (cond.operator === 'is_empty') return isEmpty;
			if (cond.operator === 'not_empty') return !isEmpty;
			if (isEmpty) return false;
			if (cond.operator === 'equals') {
				if (Array.isArray(cell)) return cell.some((v) => String(v).toLowerCase() === lv);
				return String(cell).toLowerCase() === lv;
			}
			if (Array.isArray(cell)) return cell.some((v) => String(v).toLowerCase().includes(lv));
			return String(cell).toLowerCase().includes(lv);
		});
	}
	return result;
}

/** Sentinel colId for sorting by the row's own `#` (row_id) instead of a data column. */
export const ROW_ID_SORT_COL = '__row_id__';

/** Reads the view's persisted sort out of its config — the single source of
 * truth (no local mirror): BE response -> store -> this parse -> render. */
export function parseSortConfig(
	config: Record<string, unknown> | undefined
): { colId: string; dir: 'asc' | 'desc' } | null {
	const s = config?.sort as { colId: string; dir: 'asc' | 'desc' } | undefined;
	return s && s.colId && s.dir ? s : null;
}

/** Reads the view's persisted column widths out of its config. */
export function parseWidths(config: Record<string, unknown> | undefined): Record<string, number> {
	const w = config?.widths;
	return w && typeof w === 'object' && !Array.isArray(w)
		? { ...(w as Record<string, number>) }
		: {};
}

export function sortRows(
	rowList: Row[],
	sortConfig: { colId: string; dir: 'asc' | 'desc' } | null,
	colList: Column[]
): Row[] {
	if (!sortConfig) return rowList;
	const { colId, dir } = sortConfig;
	if (colId === ROW_ID_SORT_COL) {
		return [...rowList].sort((a, b) => (dir === 'asc' ? a.row_id - b.row_id : b.row_id - a.row_id));
	}
	const sortCol = colList.find((c) => c.column_id === colId);
	const choiceOrder =
		sortCol && readAs(sortCol) === 'select' ? getChoices(sortCol).map((c) => c.value) : null;
	return [...rowList].sort((a, b) => {
		const av = a.row_data[colId];
		const bv = b.row_data[colId];
		if (choiceOrder) {
			const getIdx = (v: unknown) => {
				if (v == null) return choiceOrder!.length;
				const i = choiceOrder!.indexOf(String(v));
				return i === -1 ? choiceOrder!.length : i;
			};
			const cmp = getIdx(av) - getIdx(bv);
			return dir === 'asc' ? cmp : -cmp;
		}
		if (sortCol && (isTemporalType(readAs(sortCol)) || readAs(sortCol) === 'number')) {
			// Compare the instants. localeCompare with numeric:true happens to
			// order equal-width epochs correctly, but not a negative one
			// (pre-1970) against a positive, and not a 12-digit against a 13.
			const an = readAs(sortCol) === 'number' ? Number(av) : toEpochMs(av);
			const bn = readAs(sortCol) === 'number' ? Number(bv) : toEpochMs(bv);
			const aMissing = an === null || an === undefined || Number.isNaN(an);
			const bMissing = bn === null || bn === undefined || Number.isNaN(bn);
			if (aMissing || bMissing) {
				// Empty sorts last in both directions, so toggling never hides it.
				const cmp = aMissing && bMissing ? 0 : aMissing ? 1 : -1;
				return cmp;
			}
			const cmp = (an as number) - (bn as number);
			return dir === 'asc' ? cmp : -cmp;
		}
		const as = av === null || av === undefined ? '' : String(av);
		const bs = bv === null || bv === undefined ? '' : String(bv);
		const cmp = as.localeCompare(bs, undefined, { numeric: true, sensitivity: 'base' });
		return dir === 'asc' ? cmp : -cmp;
	});
}

export function getGroupKey(row: Row, col: Column, granularity: 'month' | 'day' = 'month'): string {
	const val = row.row_data[col.column_id];
	if (val === null || val === undefined || val === '') return '(empty)';
	if (temporalReading(col)) {
		// Bucket on the instant, in the reader's zone. The old code sliced the
		// display string, which on an epoch number yielded '1798675200' as a
		// "month".
		return temporalGroupKey(val, granularity, currentZone()) || '(empty)';
	}
	return String(val);
}

export function buildGroupedRows(
	rowList: Row[],
	groupConfig: { colId: string; granularity?: 'month' | 'day' } | null,
	colList: Column[],
	sortConfig?: { colId: string; dir: 'asc' | 'desc' } | null
): { groups: { key: string; rows: Row[] }[]; col: Column } | null {
	if (!groupConfig) return null;
	const col = colList.find((c) => c.column_id === groupConfig.colId);
	if (!col) return null;
	const granularity = groupConfig.granularity ?? 'month';
	const keyOrder: string[] = [];
	const keyMap: Record<string, Row[]> = {};
	for (const row of rowList) {
		const key = getGroupKey(row, col, granularity);
		if (!keyMap[key]) {
			keyMap[key] = [];
			keyOrder.push(key);
		}
		keyMap[key].push(row);
	}
	const groups = keyOrder.map((key) => ({
		key,
		rows: sortConfig ? sortRows(keyMap[key], sortConfig, colList) : keyMap[key]
	}));
	return { groups, col };
}

export function buildRenderItems(
	sortedRowList: Row[],
	groupedRows: { groups: { key: string; rows: Row[] }[]; col: Column } | null,
	collapsedGroups: Set<string>
): RenderItem[] {
	if (!groupedRows) {
		return sortedRowList.map((row, rowIdx): RenderItem => ({ type: 'row', row, rowIdx }));
	}
	const items: RenderItem[] = [];
	for (const group of groupedRows.groups) {
		items.push({
			type: 'group-header',
			key: group.key,
			count: group.rows.length,
			col: groupedRows.col
		});
		if (!collapsedGroups.has(group.key)) {
			group.rows.forEach((row, rowIdx) => {
				items.push({ type: 'row', row, rowIdx });
			});
			items.push({ type: 'group-add', key: group.key, col: groupedRows.col });
		}
	}
	return items;
}

export function buildSortedColumns(colList: Column[], viewColOrder: string[] | null): Column[] {
	return viewColOrder && viewColOrder.length > 0
		? [...colList].sort((a, b) => {
				const ai = viewColOrder.indexOf(a.column_id);
				const bi = viewColOrder.indexOf(b.column_id);
				return (ai === -1 ? 9999 : ai) - (bi === -1 ? 9999 : bi);
			})
		: colList;
}

// ─── Export helpers ───────────────────────────────────────────────────────────

export function buildTemplateJSON(colList: Column[]): string {
	const template = colList.map((col) => ({
		name: col.name,
		type: col.type,
		options: col.options
	}));
	return JSON.stringify(template, null, 2);
}

export function buildCSV(colList: Column[], rowList: Row[]): string {
	const cols = colList;
	const escapeCSV = (v: string) => `"${v.replace(/"/g, '""')}"`;
	const csvRows = [
		cols.map((c) => escapeCSV(c.name)).join(','),
		...rowList.map((row) =>
			cols
				.map((col) => {
					const val = row.row_data[col.column_id];
					if (val === null || val === undefined) return '';
					if (Array.isArray(val)) return escapeCSV(val.join(','));
					// Export the readable instant, not the epoch integer — a CSV
					// full of 1798675200000 is not something a person can use.
					const temporal = temporalReading(col);
					if (temporal) return escapeCSV(formatCellDate(val, temporal));
					return escapeCSV(String(val));
				})
				.join(',')
		)
	];
	return csvRows.join('\n');
}

export function buildExportJSON(colList: Column[], rowList: Row[]): string {
	const cols = colList;
	const data = rowList.map((row) => {
		const obj: Record<string, unknown> = {};
		for (const col of cols) {
			const val = row.row_data[col.column_id] ?? null;
			const temporal = temporalReading(col);
			obj[col.name] = val !== null && temporal ? formatCellDate(val, temporal) : val;
		}
		return obj;
	});
	return JSON.stringify(data, null, 2);
}

export function triggerDownload(content: string, filename: string, mimeType: string): void {
	const blob = new Blob([content], { type: mimeType });
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	a.download = filename;
	a.click();
	URL.revokeObjectURL(url);
}

export function parseCSV(text: string): string[][] {
	const lines = text.split(/\r?\n/).filter((l) => l.trim());
	return lines.map((line) => {
		const fields: string[] = [];
		let i = 0;
		while (i < line.length) {
			if (line[i] === '"') {
				let j = i + 1;
				let field = '';
				while (j < line.length) {
					if (line[j] === '"' && line[j + 1] === '"') {
						field += '"';
						j += 2;
					} else if (line[j] === '"') {
						j++;
						break;
					} else {
						field += line[j++];
					}
				}
				fields.push(field);
				i = j;
				if (line[i] === ',') i++;
			} else {
				const end = line.indexOf(',', i);
				if (end === -1) {
					fields.push(line.slice(i));
					break;
				} else {
					fields.push(line.slice(i, end));
					i = end + 1;
				}
			}
		}
		return fields;
	});
}

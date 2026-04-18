import type { Column, ColumnChoice, ColumnType, Row } from '$lib/types/table';
import { TAG_COLORS } from '$lib/UI/theme.svelte';

export const COLUMN_TYPES = [
	'text',
	'string',
	'number',
	'date',
	'select',
	'tags',
	'checkbox',
	'url',
	'doc'
] as const;

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
	if (item.type === 'row') return 'row-' + item.row.row_number;
	return item.type + '-' + item.key;
}

export function getCellValue(row: { row_data: Record<string, unknown> }, colId: string): string {
	const val = row.row_data[colId];
	if (val === null || val === undefined) return '';
	if (typeof val === 'boolean') return val ? '✓' : '';
	return String(val);
}

export function getChoices(col: Column): ColumnChoice[] {
	const choices = col.options?.choices;
	if (!Array.isArray(choices)) return [];
	return choices as ColumnChoice[];
}

export function getChoiceColor(col: Column, value: string): (typeof TAG_COLORS)[number] {
	const choices = getChoices(col);
	const idx = choices.findIndex((c) => c.value === value);
	return TAG_COLORS[idx >= 0 ? idx % TAG_COLORS.length : 0];
}

export function getTagValues(row: { row_data: Record<string, unknown> }, colId: string): string[] {
	const val = row.row_data[colId];
	return Array.isArray(val) ? (val as string[]) : [];
}

/** Parse a string edit value to the correct runtime type for the given column type. */
export function parseEditValue(editVal: string, colType: ColumnType): unknown {
	if (colType === 'number') return editVal === '' ? null : Number(editVal);
	if (colType === 'checkbox') return editVal === 'true';
	if (editVal === '') return null;
	return editVal;
}

/** Return new row_data with the edit applied (parsed by column type). */
export function applyEditToRowData(
	rowData: Record<string, unknown>,
	colId: string,
	editVal: string,
	colType: ColumnType
): Record<string, unknown> {
	return { ...rowData, [colId]: parseEditValue(editVal, colType) };
}

/** Return new row_data with the checkbox toggled. */
export function toggleCheckboxInRowData(
	rowData: Record<string, unknown>,
	colId: string
): Record<string, unknown> {
	return { ...rowData, [colId]: !rowData[colId] };
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

export function formatDate(raw: string): string {
	if (!raw) return '';
	if (/^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?/.test(raw)) {
		const normalized = raw.replace('T', ' ').replace(/(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$/, '');
		return normalized.length > 10 ? normalized.slice(0, 19) : normalized.slice(0, 10);
	}
	if (/^\d{14}$/.test(raw)) {
		return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)} ${raw.slice(8, 10)}:${raw.slice(10, 12)}:${raw.slice(12, 14)}`;
	}
	if (/^\d{6}$/.test(raw)) {
		return `20${raw.slice(0, 2)}-${raw.slice(2, 4)}-${raw.slice(4, 6)}`;
	}
	if (/^\d{8}$/.test(raw)) {
		return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
	}
	return raw;
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

export function sortRows(
	rowList: Row[],
	sortConfig: { colId: string; dir: 'asc' | 'desc' } | null,
	colList: Column[]
): Row[] {
	if (!sortConfig) return rowList;
	const { colId, dir } = sortConfig;
	const sortCol = colList.find((c) => c.column_id === colId);
	const choiceOrder =
		sortCol?.type === 'select' ? getChoices(sortCol).map((c) => c.value) : null;
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
		const as = av === null || av === undefined ? '' : String(av);
		const bs = bv === null || bv === undefined ? '' : String(bv);
		const cmp = as.localeCompare(bs, undefined, { numeric: true, sensitivity: 'base' });
		return dir === 'asc' ? cmp : -cmp;
	});
}

export function getGroupKey(
	row: Row,
	col: Column,
	granularity: 'month' | 'day' = 'month'
): string {
	const val = row.row_data[col.column_id];
	if (val === null || val === undefined || val === '') return '(empty)';
	if (col.type === 'date') {
		const normalized = formatDate(String(val));
		return granularity === 'month' ? normalized.slice(0, 7) : normalized.slice(0, 10);
	}
	return String(val);
}

export function buildGroupedRows(
	sortedRowList: Row[],
	groupConfig: { colId: string; granularity?: 'month' | 'day' } | null,
	colList: Column[]
): { groups: { key: string; rows: Row[] }[]; col: Column } | null {
	if (!groupConfig) return null;
	const col = colList.find((c) => c.column_id === groupConfig.colId);
	if (!col) return null;
	const granularity = groupConfig.granularity ?? 'month';
	const keyOrder: string[] = [];
	const keyMap: Record<string, Row[]> = {};
	for (const row of sortedRowList) {
		const key = getGroupKey(row, col, granularity);
		if (!keyMap[key]) {
			keyMap[key] = [];
			keyOrder.push(key);
		}
		keyMap[key].push(row);
	}
	return { groups: keyOrder.map((key) => ({ key, rows: keyMap[key] })), col };
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

export function buildSortedColumns(
	colList: Column[],
	viewColOrder: string[] | null,
	hiddenCols: Set<string>
): Column[] {
	return [...colList]
		.sort((a, b) => {
			if (viewColOrder && viewColOrder.length > 0) {
				const ai = viewColOrder.indexOf(a.column_id);
				const bi = viewColOrder.indexOf(b.column_id);
				return (ai === -1 ? 9999 : ai) - (bi === -1 ? 9999 : bi);
			}
			return a.position - b.position;
		})
		.filter((c) => !hiddenCols.has(c.column_id));
}

// ─── Export helpers ───────────────────────────────────────────────────────────

export function buildTemplateJSON(colList: Column[]): string {
	const template = [...colList]
		.sort((a, b) => a.position - b.position)
		.map((col) => ({ name: col.name, type: col.type, options: col.options, position: col.position }));
	return JSON.stringify(template, null, 2);
}

export function buildCSV(colList: Column[], rowList: Row[]): string {
	const cols = [...colList].sort((a, b) => a.position - b.position);
	const escapeCSV = (v: string) => `"${v.replace(/"/g, '""')}"`;
	const csvRows = [
		cols.map((c) => escapeCSV(c.name)).join(','),
		...rowList.map((row) =>
			cols
				.map((col) => {
					const val = row.row_data[col.column_id];
					if (val === null || val === undefined) return '';
					if (Array.isArray(val)) return escapeCSV(val.join(','));
					return escapeCSV(String(val));
				})
				.join(',')
		)
	];
	return csvRows.join('\n');
}

export function buildExportJSON(colList: Column[], rowList: Row[]): string {
	const cols = [...colList].sort((a, b) => a.position - b.position);
	const data = rowList.map((row) => {
		const obj: Record<string, unknown> = {};
		for (const col of cols) obj[col.name] = row.row_data[col.column_id] ?? null;
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

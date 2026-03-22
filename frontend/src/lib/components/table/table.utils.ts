import type { Column, ColumnChoice, Row } from '$lib/types/table';
import { TAG_COLORS } from '$lib/UI/theme.svelte';

export const COLUMN_TYPES = [
	'text',
	'string',
	'number',
	'date',
	'select',
	'tags',
	'checkbox',
	'url'
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
	if (item.type === 'row') return 'row-' + item.row.id;
	return item.type + '-' + item.key;
}

export function getCellValue(row: { data: Record<string, unknown> }, colId: string): string {
	const val = row.data[colId];
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

export function getTagValues(row: { data: Record<string, unknown> }, colId: string): string[] {
	const val = row.data[colId];
	return Array.isArray(val) ? (val as string[]) : [];
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

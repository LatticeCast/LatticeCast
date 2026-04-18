import type { Column, Row } from '$lib/types/table';
import { getChoices, formatDate } from './table.utils';

export type Granularity = 'day' | 'week' | 'month';

export const GRANULARITIES: Granularity[] = ['day', 'week', 'month'];

export function parseTimelineDate(raw: unknown): Date | null {
	if (!raw) return null;
	const normalized = formatDate(String(raw));
	const d = new Date(normalized.slice(0, 10));
	return isNaN(d.getTime()) ? null : d;
}

export function generateTimeColumns(start: Date, end: Date, gran: Granularity): Date[] {
	const cols: Date[] = [];
	let cur = start;
	while (cur <= end) {
		cols.push(cur);
		if (gran === 'day') {
			cur = new Date(cur.getFullYear(), cur.getMonth(), cur.getDate() + 1);
		} else if (gran === 'week') {
			cur = new Date(cur.getFullYear(), cur.getMonth(), cur.getDate() + 7);
		} else {
			cur = new Date(cur.getFullYear(), cur.getMonth() + 1, 1);
		}
	}
	return cols;
}

export function getWeekNumber(d: Date): number {
	const dayOfWeek =
		new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())).getUTCDay() || 7;
	const thursday = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate() + 4 - dayOfWeek));
	const yearStart = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 1));
	return Math.ceil(((thursday.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}

export function formatColHeader(date: Date, gran: Granularity): string {
	if (gran === 'day') {
		return `${date.getMonth() + 1}/${date.getDate()}`;
	} else if (gran === 'week') {
		return `W${getWeekNumber(date)} ${date.getFullYear()}`;
	} else {
		return date.toLocaleString('default', { month: 'short', year: 'numeric' });
	}
}

export function isToday(date: Date, gran: Granularity, today: Date): boolean {
	if (gran === 'day') {
		return (
			date.getFullYear() === today.getFullYear() &&
			date.getMonth() === today.getMonth() &&
			date.getDate() === today.getDate()
		);
	} else if (gran === 'week') {
		const weekEnd = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 6);
		return today >= date && today <= weekEnd;
	} else {
		return date.getFullYear() === today.getFullYear() && date.getMonth() === today.getMonth();
	}
}

export function dateToX(
	date: Date,
	viewportStart: Date,
	viewportEnd: Date,
	totalGridWidth: number
): number {
	const totalMs = viewportEnd.getTime() - viewportStart.getTime();
	if (totalMs === 0) return 0;
	const offsetMs = date.getTime() - viewportStart.getTime();
	return Math.max(0, Math.min(totalGridWidth, (offsetMs / totalMs) * totalGridWidth));
}

export function getBarLeft(
	startDate: Date,
	viewportStart: Date,
	viewportEnd: Date,
	totalGridWidth: number
): number {
	return dateToX(startDate, viewportStart, viewportEnd, totalGridWidth);
}

export function getBarWidth(
	startDate: Date,
	endDate: Date,
	viewportStart: Date,
	viewportEnd: Date,
	totalGridWidth: number,
	cellWidth: number
): number {
	const endInclusive = new Date(endDate.getTime() + 86400000);
	return Math.max(
		cellWidth / 2,
		dateToX(endInclusive, viewportStart, viewportEnd, totalGridWidth) -
			dateToX(startDate, viewportStart, viewportEnd, totalGridWidth)
	);
}

const BAR_COLORS = [
	'bg-blue-400 text-white',
	'bg-green-400 text-white',
	'bg-yellow-400 text-gray-800',
	'bg-red-400 text-white',
	'bg-purple-400 text-white',
	'bg-pink-400 text-white',
	'bg-orange-400 text-white',
	'bg-teal-400 text-white',
	'bg-cyan-400 text-gray-800',
	'bg-indigo-400 text-white',
	'bg-lime-400 text-gray-800',
	'bg-rose-400 text-white'
];

export function getBarColorClasses(
	row: Row,
	colorByCol: Column | undefined,
	colorByColId: string | undefined
): string {
	if (!colorByCol || !colorByColId) return 'bg-blue-400 text-white';
	const val = row.row_data[colorByColId];
	if (!val) return 'bg-blue-400 text-white';
	const choices = getChoices(colorByCol);
	const idx = choices.findIndex((c) => c.value === String(val));
	return BAR_COLORS[idx >= 0 ? idx % BAR_COLORS.length : 0];
}

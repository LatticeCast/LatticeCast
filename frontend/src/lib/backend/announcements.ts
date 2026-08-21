// lib/backend/announcements.ts
//
// Controller: load server-wide announcements and replace the shared cache.

import { BACKEND_URL } from './config';
import { setAnnouncements, type Announcement } from '$lib/stores/announcement.store';

const ANNOUNCEMENTS_LQL =
	'table("announcement") | filter((r)->{r.type in @["app","server"]}) | sort_desc("updated_at") | limit(20)';

export async function fetchAnnouncements(): Promise<Announcement[]> {
	const response = await fetch(`${BACKEND_URL}/api/v1/announcements/query`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ lql: ANNOUNCEMENTS_LQL })
	});
	if (!response.ok) {
		const body = await response.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to fetch announcements: ${response.statusText}`);
	}

	const payload: unknown = await response.json();
	if (!isAnnouncementResponse(payload)) throw new Error('Invalid announcement response');

	const normalized = normalizeAnnouncements(payload.rows, payload.columns);
	setAnnouncements(normalized);
	return normalized;
}

function isAnnouncementResponse(
	value: unknown
): value is { rows: Announcement[]; columns: { name: string; column_id: string }[] } {
	return (
		typeof value === 'object' &&
		value !== null &&
		'rows' in value &&
		Array.isArray(value.rows) &&
		'columns' in value &&
		Array.isArray(value.columns) &&
		value.rows.every((row) => typeof row === 'object' && row !== null && !Array.isArray(row)) &&
		value.columns.every(
			(column) =>
				typeof column === 'object' &&
				column !== null &&
				'name' in column &&
				typeof column.name === 'string' &&
				'column_id' in column &&
				typeof column.column_id === 'string'
		)
	);
}

function normalizeAnnouncements(
	rows: Announcement[],
	columns: { name: string; column_id: string }[]
): Announcement[] {
	const idByName = Object.fromEntries(columns.map((column) => [column.name, column.column_id]));

	return rows
		.map((row) => {
			const rowData =
				'row_data' in row && typeof row.row_data === 'object' && row.row_data !== null
					? row.row_data
					: {};
			const title = readCell(rowData, idByName.Title);
			const description = readCell(rowData, idByName.Description);
			const type = readCell(rowData, idByName.Type);
			const updated_at = readCell(rowData, idByName.updated_at) ?? readText(row, 'updated_at');
			const created_at = readCell(rowData, idByName.created_at) ?? readText(row, 'created_at');
			return { title, description, type, updated_at, created_at };
		})
		.filter((row) => row.type === 'app' || row.type === 'server');
}

function readCell(rowData: object, columnId: string | undefined): string | null {
	if (!columnId) return null;
	const value = rowData[columnId as keyof typeof rowData];
	return typeof value === 'string' && value.trim() ? value : null;
}

function readText(row: Announcement, key: string): string | null {
	const value = row[key];
	return typeof value === 'string' && value.trim() ? value : null;
}

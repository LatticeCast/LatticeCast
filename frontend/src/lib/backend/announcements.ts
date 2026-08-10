// lib/backend/announcements.ts
//
// Controller: load server-wide announcements and replace the shared cache.

import { BACKEND_URL } from './config';
import { setAnnouncements, type Announcement } from '$lib/stores/announcements.store';

export const SERVER_ANNOUNCEMENTS_LQL = 'table("announcement") | filter(Type = "server")';

export async function fetchAnnouncements(): Promise<Announcement[]> {
	const response = await fetch(`${BACKEND_URL}/api/v1/announcements/query`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ lql: SERVER_ANNOUNCEMENTS_LQL })
	});
	if (!response.ok) {
		const body = await response.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to fetch announcements: ${response.statusText}`);
	}

	const payload: unknown = await response.json();
	if (!isAnnouncementResponse(payload)) throw new Error('Invalid announcement response');

	setAnnouncements(payload.rows);
	return payload.rows;
}

function isAnnouncementResponse(value: unknown): value is { rows: Announcement[] } {
	return (
		typeof value === 'object' &&
		value !== null &&
		'rows' in value &&
		Array.isArray(value.rows) &&
		value.rows.every((row) => typeof row === 'object' && row !== null && !Array.isArray(row))
	);
}

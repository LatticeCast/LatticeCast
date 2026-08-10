// src/lib/stores/announcement.store.ts
//
// Public announcement feed cache. The announcement endpoint runs its query
// using a dedicated read-only identity, so consumers do not need app auth.

import { writable } from 'svelte/store';
import { BACKEND_URL } from '$lib/backend/config';

export type Announcement = Record<string, unknown>;

export const ANNOUNCEMENTS_LQL = 'table("announcement")';

export const announcements = writable<Announcement[]>([]);
export const announcementsLoading = writable(false);
export const announcementsError = writable<string | null>(null);

export async function fetchAnnouncements(lql = ANNOUNCEMENTS_LQL): Promise<Announcement[]> {
	announcementsLoading.set(true);
	announcementsError.set(null);

	try {
		const response = await fetch(`${BACKEND_URL}/api/v1/announcements/query`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ lql })
		});
		if (!response.ok) {
			const body = await response.json().catch(() => ({}));
			throw new Error(body.detail || `Failed to fetch announcements: ${response.statusText}`);
		}

		const payload: unknown = await response.json();
		if (!isAnnouncementResponse(payload)) {
			throw new Error('Invalid announcement response');
		}

		announcements.set(payload.rows);
		return payload.rows;
	} catch (error) {
		const message = error instanceof Error ? error.message : 'Failed to fetch announcements';
		announcementsError.set(message);
		throw error;
	} finally {
		announcementsLoading.set(false);
	}
}

export function resetAnnouncements(): void {
	announcements.set([]);
	announcementsLoading.set(false);
	announcementsError.set(null);
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

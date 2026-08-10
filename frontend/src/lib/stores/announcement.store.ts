// src/lib/stores/announcement.store.ts
//
// Shared announcement-query cache. Controllers replace these rows with the
// backend response; presentation derives the announcement it wants to show.

import { writable } from 'svelte/store';

/** A row returned by the announcement LatticeQL query. */
export type Announcement = Record<string, unknown>;

export const announcements = writable<Announcement[]>([]);

export function setAnnouncements(rows: Announcement[]): void {
	announcements.set(rows);
}

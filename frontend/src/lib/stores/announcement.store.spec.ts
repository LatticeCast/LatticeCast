import { get } from 'svelte/store';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BACKEND_URL } from '$lib/backend/config';
import {
	ANNOUNCEMENTS_LQL,
	announcements,
	announcementsError,
	announcementsLoading,
	fetchAnnouncements,
	resetAnnouncements
} from './announcement.store';

describe('announcement store', () => {
	afterEach(() => {
		vi.unstubAllGlobals();
		resetAnnouncements();
	});

	it('loads public announcement rows through the query endpoint', async () => {
		const rows = [{ title: 'Maintenance window', type: 'server' }];
		const fetchMock = vi.fn().mockResolvedValue(
			new Response(JSON.stringify({ rows }), { status: 200, headers: { 'Content-Type': 'application/json' } })
		);
		vi.stubGlobal('fetch', fetchMock);

		await expect(fetchAnnouncements()).resolves.toEqual(rows);
		expect(fetchMock).toHaveBeenCalledWith(
			`${BACKEND_URL}/api/v1/announcements/query`,
			expect.objectContaining({
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ lql: ANNOUNCEMENTS_LQL })
			})
		);
		expect(get(announcements)).toEqual(rows);
		expect(get(announcementsLoading)).toBe(false);
		expect(get(announcementsError)).toBeNull();
	});

	it('keeps cached rows and exposes a useful error when the query fails', async () => {
		announcements.set([{ title: 'Existing announcement' }]);
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Bad query' }), { status: 400 }))
		);

		await expect(fetchAnnouncements('invalid')).rejects.toThrow('Bad query');
		expect(get(announcements)).toEqual([{ title: 'Existing announcement' }]);
		expect(get(announcementsError)).toBe('Bad query');
		expect(get(announcementsLoading)).toBe(false);
	});
});

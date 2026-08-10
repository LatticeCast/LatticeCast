import { get } from 'svelte/store';
import { afterEach, describe, expect, it } from 'vitest';
import { announcements, setAnnouncements } from './announcement.store';

describe('announcement store', () => {
	afterEach(() => {
		setAnnouncements([]);
	});

	it('replaces cached rows', () => {
		setAnnouncements([{ title: 'Maintenance window', type: 'server' }]);
		setAnnouncements([{ title: 'Updated announcement', type: 'server' }]);

		expect(get(announcements)).toEqual([{ title: 'Updated announcement', type: 'server' }]);
	});
});

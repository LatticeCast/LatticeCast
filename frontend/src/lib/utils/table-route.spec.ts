import { describe, expect, it, vi } from 'vitest';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));

import { findTableForPath } from './table-route';

const firstWorkspace = '11111111-1111-4111-8111-111111111111';
const secondWorkspace = '22222222-2222-4222-8222-222222222222';
const workspaces = [
	{ workspace_id: firstWorkspace, workspace_name: 'homun', created_at: '2026-01-01' },
	{ workspace_id: secondWorkspace, workspace_name: 'homun', created_at: '2026-01-02' }
];
const tables = [
	{ workspace_id: secondWorkspace, table_id: 61, table_name: 'data-reports' },
	{ workspace_id: firstWorkspace, table_id: 60, table_name: 'data-reports' },
	{ workspace_id: firstWorkspace, table_id: 62, table_name: '60' }
];

describe('table URL resolution', () => {
	it('gives the plain name to the first-created workspace', () => {
		expect(findTableForPath('homun', 'data-reports', workspaces, tables)?.table_id).toBe(60);
	});

	it('addresses the second workspace of that name as name-1', () => {
		expect(findTableForPath('homun-1', 'data-reports', workspaces, tables)?.table_id).toBe(61);
	});

	it('uses an explicit workspace identity to disambiguate matching names', () => {
		expect(findTableForPath(secondWorkspace, 'data-reports', workspaces, tables)?.table_id).toBe(
			61
		);
	});

	it('prefers a numeric table name over a legacy numeric identity', () => {
		expect(findTableForPath('homun', '60', workspaces, tables)?.table_id).toBe(62);
	});

	it('finds a workspace whose name looks like a UUID', () => {
		const uuidName = '33333333-3333-4333-8333-333333333333';
		const named = [{ workspace_id: firstWorkspace, workspace_name: uuidName, created_at: 'a' }];
		expect(findTableForPath(uuidName, 'data-reports', named, tables)?.table_id).toBe(60);
	});
});

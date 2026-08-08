// src/lib/stores/workspace_members.store.ts
//
// Workspace-member cache keyed by workspace UUID. Backend responses are the
// only source used to populate or mutate this store.

import { writable } from 'svelte/store';
import type { WorkspaceMemberFull } from '$lib/types/table';

export const workspaceMembers = writable<Record<string, WorkspaceMemberFull[]>>({});

export function setWorkspaceMembers(workspaceId: string, members: WorkspaceMemberFull[]): void {
	workspaceMembers.update((cache) => ({ ...cache, [workspaceId]: members }));
}

export function upsertWorkspaceMember(workspaceId: string, member: WorkspaceMemberFull): void {
	workspaceMembers.update((cache) => {
		const current = cache[workspaceId] ?? [];
		const exists = current.some((item) => item.user_id === member.user_id);
		return {
			...cache,
			[workspaceId]: exists
				? current.map((item) => (item.user_id === member.user_id ? member : item))
				: [...current, member]
		};
	});
}

export function deleteWorkspaceMember(workspaceId: string, userId: string): void {
	workspaceMembers.update((cache) => ({
		...cache,
		[workspaceId]: (cache[workspaceId] ?? []).filter((member) => member.user_id !== userId)
	}));
}

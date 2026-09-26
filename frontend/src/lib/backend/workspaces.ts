// lib/backend/workspaces.ts
//
// Controller: workspace + members CRUD → API call + menu store update.

import { get } from 'svelte/store';
import { authenticatedLatticeCast } from './client';
import { workspaces, currentWorkspaceId, tables } from '$lib/stores/table_schemas.store';
import {
	deleteWorkspaceMember,
	setWorkspaceMembers,
	upsertWorkspaceMember
} from '$lib/stores/workspace_members.store';
import type { Workspace, WorkspaceAccessLevel, WorkspaceMemberFull } from '$lib/types/table';

export interface CreateWorkspace {
	workspace_name: string;
}

export interface UpdateWorkspace {
	workspace_name: string;
}

export interface AddMember {
	user_id?: string;
	user_name?: string;
	user_email?: string;
	level: WorkspaceAccessLevel;
}

// ─── Workspaces ───────────────────────────────────────────────────────────────

export async function fetchWorkspaces(): Promise<Workspace[]> {
	const result = await authenticatedLatticeCast.requestJson<Workspace[]>('/workspaces');
	workspaces.set(result);
	return result;
}

export async function createWorkspace(data: CreateWorkspace): Promise<Workspace> {
	const ws = await authenticatedLatticeCast.requestJson<Workspace>('/workspaces', {
		method: 'POST',
		body: data
	});
	workspaces.update((list) => [
		...list.filter((item) => item.workspace_id !== ws.workspace_id),
		ws
	]);
	return ws;
}

export async function updateWorkspace(
	workspaceId: string,
	data: UpdateWorkspace
): Promise<Workspace> {
	const ws = await authenticatedLatticeCast.requestJson<Workspace>(`/workspaces/${workspaceId}`, {
		method: 'PUT',
		body: data
	});
	workspaces.update((list) => list.map((w) => (w.workspace_id === workspaceId ? ws : w)));
	return ws;
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
	await authenticatedLatticeCast.requestJson<void>(`/workspaces/${workspaceId}`, {
		method: 'DELETE'
	});
	workspaces.update((list) => list.filter((w) => w.workspace_id !== workspaceId));
	if (get(currentWorkspaceId) === workspaceId) {
		currentWorkspaceId.set(null);
		tables.set([]);
	}
}

// ─── Members ──────────────────────────────────────────────────────────────────

export async function fetchMembers(workspaceId: string): Promise<WorkspaceMemberFull[]> {
	const result = await authenticatedLatticeCast.requestJson<WorkspaceMemberFull[]>(
		`/workspaces/${workspaceId}/members`
	);
	setWorkspaceMembers(workspaceId, result);
	return result;
}

export async function addMember(
	workspaceId: string,
	data: AddMember
): Promise<WorkspaceMemberFull> {
	const member = await authenticatedLatticeCast.requestJson<WorkspaceMemberFull>(
		`/workspaces/${workspaceId}/members`,
		{ method: 'POST', body: data }
	);
	upsertWorkspaceMember(workspaceId, member);
	return member;
}

export async function updateMemberLevel(
	workspaceId: string,
	userId: string,
	level: WorkspaceAccessLevel
): Promise<WorkspaceMemberFull> {
	const member = await authenticatedLatticeCast.requestJson<WorkspaceMemberFull>(
		`/workspaces/${workspaceId}/members/${userId}`,
		{ method: 'PUT', body: { level } }
	);
	upsertWorkspaceMember(workspaceId, member);
	return member;
}

export async function removeMember(workspaceId: string, userId: string): Promise<void> {
	await authenticatedLatticeCast.requestJson<void>(`/workspaces/${workspaceId}/members/${userId}`, {
		method: 'DELETE'
	});
	deleteWorkspaceMember(workspaceId, userId);
}

// lib/backend/workspaces.ts
//
// Controller: workspace + members CRUD → API call + menu store update.

import { get } from 'svelte/store';
import { BACKEND_URL } from './config';
import { getAuthHeaders } from './http';
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
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/workspaces`, { headers });
	if (!response.ok) throw new Error(`Failed to fetch workspaces: ${response.statusText}`);
	const result: Workspace[] = await response.json();
	workspaces.set(result);
	return result;
}

export async function createWorkspace(data: CreateWorkspace): Promise<Workspace> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/workspaces`, {
		method: 'POST',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to create workspace: ${response.statusText}`);
	const ws: Workspace = await response.json();
	workspaces.update((list) => [...list, ws]);
	return ws;
}

export async function updateWorkspace(
	workspaceId: string,
	data: UpdateWorkspace
): Promise<Workspace> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/workspaces/${workspaceId}`, {
		method: 'PUT',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) {
		const body = await response.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to update workspace: ${response.statusText}`);
	}
	const ws: Workspace = await response.json();
	workspaces.update((list) => list.map((w) => (w.workspace_id === workspaceId ? ws : w)));
	return ws;
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/workspaces/${workspaceId}`, {
		method: 'DELETE',
		headers
	});
	if (!response.ok) throw new Error(`Failed to delete workspace: ${response.statusText}`);
	workspaces.update((list) => list.filter((w) => w.workspace_id !== workspaceId));
	if (get(currentWorkspaceId) === workspaceId) {
		currentWorkspaceId.set(null);
		tables.set([]);
	}
}

// ─── Members ──────────────────────────────────────────────────────────────────

export async function fetchMembers(workspaceId: string): Promise<WorkspaceMemberFull[]> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/workspaces/${workspaceId}/members`, {
		headers
	});
	if (!response.ok) throw new Error(`Failed to fetch members: ${response.statusText}`);
	const result: WorkspaceMemberFull[] = await response.json();
	setWorkspaceMembers(workspaceId, result);
	return result;
}

export async function addMember(
	workspaceId: string,
	data: AddMember
): Promise<WorkspaceMemberFull> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/workspaces/${workspaceId}/members`, {
		method: 'POST',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) {
		const body = await response.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to add member: ${response.statusText}`);
	}
	const member: WorkspaceMemberFull = await response.json();
	upsertWorkspaceMember(workspaceId, member);
	return member;
}

export async function updateMemberLevel(
	workspaceId: string,
	userId: string,
	level: WorkspaceAccessLevel
): Promise<WorkspaceMemberFull> {
	const headers = await getAuthHeaders();
	const response = await fetch(
		`${BACKEND_URL}/api/v1/workspaces/${workspaceId}/members/${userId}`,
		{
			method: 'PUT',
			headers,
			body: JSON.stringify({ level })
		}
	);
	if (!response.ok) {
		const body = await response.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to update access level: ${response.statusText}`);
	}
	const member: WorkspaceMemberFull = await response.json();
	upsertWorkspaceMember(workspaceId, member);
	return member;
}

export async function removeMember(workspaceId: string, userId: string): Promise<void> {
	const headers = await getAuthHeaders();
	const response = await fetch(
		`${BACKEND_URL}/api/v1/workspaces/${workspaceId}/members/${userId}`,
		{
			method: 'DELETE',
			headers
		}
	);
	if (!response.ok) {
		const body = await response.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to remove member: ${response.statusText}`);
	}
	deleteWorkspaceMember(workspaceId, userId);
}

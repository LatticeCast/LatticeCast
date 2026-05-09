// lib/backend/workspaces.ts
// API client for workspaces + members CRUD

import { BACKEND_URL } from './config';
import { getAuthHeaders } from './http';
import type { Workspace, WorkspaceMember, WorkspaceMemberFull } from '$lib/types/table';

export interface CreateWorkspace {
	workspace_name: string;
}

export interface UpdateWorkspace {
	workspace_name: string;
}

export interface AddMember {
	user_id?: string;
	user_email?: string;
	role?: string;
}

// Workspaces

export async function fetchWorkspaces(): Promise<Workspace[]> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/workspaces`, { headers });
	if (!response.ok) throw new Error(`Failed to fetch workspaces: ${response.statusText}`);
	return response.json();
}

export async function createWorkspace(data: CreateWorkspace): Promise<Workspace> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/workspaces`, {
		method: 'POST',
		headers,
		body: JSON.stringify(data)
	});
	if (!response.ok) throw new Error(`Failed to create workspace: ${response.statusText}`);
	return response.json();
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
	return response.json();
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/workspaces/${workspaceId}`, {
		method: 'DELETE',
		headers
	});
	if (!response.ok) throw new Error(`Failed to delete workspace: ${response.statusText}`);
}

// Members

export async function fetchMembers(workspaceId: string): Promise<WorkspaceMemberFull[]> {
	const headers = await getAuthHeaders();
	const response = await fetch(`${BACKEND_URL}/api/v1/workspaces/${workspaceId}/members`, {
		headers
	});
	if (!response.ok) throw new Error(`Failed to fetch members: ${response.statusText}`);
	return response.json();
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
	return response.json();
}

export async function updateMemberRole(
	workspaceId: string,
	userId: string,
	role: string
): Promise<WorkspaceMemberFull> {
	const headers = await getAuthHeaders();
	const response = await fetch(
		`${BACKEND_URL}/api/v1/workspaces/${workspaceId}/members/${userId}`,
		{
			method: 'PUT',
			headers,
			body: JSON.stringify({ role })
		}
	);
	if (!response.ok) {
		const body = await response.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to update role: ${response.statusText}`);
	}
	return response.json();
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
}

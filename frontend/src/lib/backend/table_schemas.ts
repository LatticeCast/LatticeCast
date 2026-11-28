// lib/backend/table_schemas.ts — fetch the workspaces and tables preload payload.

import { authenticatedRequestJson } from './client';
import {
	applyWorkspacesTables,
	type WorkspacesTablesPayload
} from '$lib/stores/table_schemas.store';

export async function fetchWorkspacesTables(): Promise<WorkspacesTablesPayload> {
	const payload = await authenticatedRequestJson<WorkspacesTablesPayload>('/workspaces_tables');
	applyWorkspacesTables(payload);
	return payload;
}

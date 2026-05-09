// src/lib/utils/url.ts

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(s: string): boolean {
	return UUID_RE.test(s);
}

export function prettifyWorkspacePathname(
	pathname: string,
	workspaceId: string,
	workspaceName: string
): string {
	const encoded = encodeURIComponent(workspaceName);
	if (pathname.startsWith(`/${workspaceId}`)) {
		return `/${encoded}${pathname.slice(workspaceId.length + 1)}`;
	}
	return pathname;
}

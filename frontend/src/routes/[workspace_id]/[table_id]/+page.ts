import type { PageLoad } from './$types';

// Auth + ssr are handled once in the root +layout.ts. This load only passes
// the route params through; the component fetches table + rows so navigation
// lands on the URL immediately and shows a loading state while data arrives.
export const load: PageLoad = ({ params, url }) => {
	const urlViewRaw = url.searchParams.get('view');
	return {
		workspaceParam: params.workspace_id,
		tableParam: params.table_id,
		urlViewId: urlViewRaw !== null ? Number(urlViewRaw) : NaN
	};
};

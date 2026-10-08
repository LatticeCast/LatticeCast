import { json } from '@sveltejs/kit';

// Emit deployment metadata for static hosting as well as the dev server.
export const prerender = true;

export function GET() {
	return json({
		status: 'ok',
		version: import.meta.env.VITE_APP_VERSION,
		commit: import.meta.env.VITE_DEPLOY_COMMIT || 'unknown'
	});
}

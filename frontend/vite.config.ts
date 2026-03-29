// vite.config.ts
/// <reference types="vitest" />

import { projectBaseWithSlash } from './myconfig.js';

import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';
import { sveltekit } from '@sveltejs/kit/vite';

const backendPort = process.env.BACKEND_PORT ?? '13491';
const frontendPort = process.env.FRONTEND_PORT ?? '13492';

// Same origin via nginx — use relative /api/ in dev, full URL in prod
const backendUrls = {
	development: `http://localhost:${backendPort}`,
	production: 'https://lattice-cast.posetmage.com'
} as const;

const frontendUrls = {
	development: `http://localhost:${backendPort}`,
	production: 'https://lattice-cast.posetmage.com'
} as const;

type BackendUrlMode = keyof typeof backendUrls;

export default defineConfig(({ mode }) => {
	const safeMode = mode as BackendUrlMode;
	const backendUrl = backendUrls[safeMode] || backendUrls.production;
	const frontendUrl = frontendUrls[safeMode] || frontendUrls.production;

	const isProduction = mode === 'production';

	const allowedHosts: string[] | true =
		safeMode === 'development' ? true : ['lattice-cast.posetmage.com'];

	return {
		base: isProduction ? projectBaseWithSlash : '/',

		plugins: [tailwindcss(), sveltekit()],
		optimizeDeps: {
			exclude: ['clsx', '@xyflow/system', 'classcat']
		},
		server: {
			host: '0.0.0.0',
			port: parseInt(frontendPort),
			allowedHosts
		},
		define: {
			'import.meta.env.VITE_BACKEND_URL': JSON.stringify(backendUrl),
			'import.meta.env.VITE_AUTH_REQUIRED': JSON.stringify(process.env.AUTH_REQUIRED ?? 'true'),

			// Authentik OAuth
			'import.meta.env.VITE_AUTHENTIK_URL': JSON.stringify(process.env.AUTHENTIK_URL),
			'import.meta.env.VITE_AUTHENTIK_CLIENT_ID': JSON.stringify(process.env.AUTHENTIK_CLIENT_ID),
			'import.meta.env.VITE_AUTHENTIK_REDIRECT_URI': JSON.stringify(
				`${frontendUrl}/callback/authentik`
			),

			// Google OAuth
			'import.meta.env.VITE_GOOGLE_CLIENT_ID': JSON.stringify(process.env.GOOGLE_CLIENT_ID),
			'import.meta.env.VITE_GOOGLE_REDIRECT_URI': JSON.stringify(`${frontendUrl}/callback/google`)
		},
		test: {
			workspace: [
				{
					extends: './vite.config.ts',
					test: {
						name: 'client',
						environment: 'jsdom',
						clearMocks: true,
						include: ['src/**/*.svelte.{test,spec}.{js,ts}'],
						exclude: ['src/lib/server/**'],
						setupFiles: ['./vitest-setup-client.ts']
					}
				},
				{
					extends: './vite.config.ts',
					test: {
						name: 'server',
						environment: 'node',
						include: ['src/**/*.{test,spec}.{js,ts}'],
						exclude: ['src/**/*.svelte.{test,spec}.{js,ts}']
					}
				}
			]
		}
	};
});

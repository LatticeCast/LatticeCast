// svelte.config.js
import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import { projectBase } from './myconfig.js';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),

	kit: {
		adapter: adapter({
			// default options are shown. On some platforms
			// these options are set automatically — see below
			pages: 'build',
			assets: 'build',
			fallback: 'index.html',
			precompress: false,
			strict: true
		}),

		paths: {
			base: process.env.NODE_ENV === 'production' ? projectBase : ''
		},

		// optional, but ensures SvelteKit app files stay in a predictable dir
		appDir: '_app'
	}
};

export default config;

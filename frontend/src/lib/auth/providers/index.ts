// lib/auth/providers/index.ts

import { authentikProvider } from './authentik';
import { googleProvider } from './google';

export const providers = {
	authentik: authentikProvider,
	google: googleProvider
};

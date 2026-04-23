// lib/auth/validation.ts
// Pure validation helpers for login form. Keep UI-free.

export const USER_NAME_RE = /^[a-z0-9][a-z0-9_.\\-]*$/;

export function validateUserName(id: string): string {
	const trimmed = id.trim();
	if (!trimmed) return '';
	if (!USER_NAME_RE.test(trimmed)) {
		return 'Invalid format — use lowercase letters, numbers, and _ - . only (e.g. homun-lang-002)';
	}
	return '';
}

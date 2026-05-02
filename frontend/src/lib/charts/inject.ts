export function applyInjects(
	option: Record<string, unknown>,
	ctx: { rows: unknown[] }
): Record<string, unknown> {
	return JSON.parse(JSON.stringify(option), (_key: string, value: unknown) => {
		if (
			value !== null &&
			typeof value === 'object' &&
			!Array.isArray(value) &&
			(value as Record<string, unknown>)['$inject'] === 'rows'
		) {
			return { source: ctx.rows };
		}
		return value;
	}) as Record<string, unknown>;
}

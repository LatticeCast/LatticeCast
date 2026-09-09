// src/lib/utils/temporal.ts
//
// Server times are epoch milliseconds in UTC and carry no zone (V48-V54).
// The frontend is the only place a timezone exists, and the zone it uses is
// the one in the user's config — not the browser's, so the same board reads
// the same way on a laptop and a phone in another country.
//
// `date` and `datetime` are one storage shape: an integer instant with no
// alignment rule (V54 removed the UTC-midnight flooring, which made the
// round trip lossy — a viewer at UTC-5 who picked 2026-12-31 got 2026-12-30
// back). The column type picks the input widget and the display precision;
// it is not a claim about the value.
//
// These are pure functions: the zone comes in as an argument so nothing here
// depends on a store, and the callers read it from settingsStore.

import { DateTime } from 'luxon';

export const MS_PER_DAY = 86_400_000;

/** An epoch-millisecond cell value, or null for an empty cell. */
export type EpochMs = number | null;

/** The two column types that hold an instant. */
export type TemporalType = 'date' | 'datetime';

/** Fall back to the browser's zone when the user has not chosen one. */
export function browserZone(): string {
	try {
		return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
	} catch {
		return 'UTC';
	}
}

/**
 * Read a cell as epoch milliseconds.
 *
 * Empty is null, never 0 — zero is a real instant (1970-01-01T00:00:00Z).
 * Legacy ISO strings are still parsed so a grid rendered against un-migrated
 * data shows a date rather than raw text; nothing writes them any more.
 */
export function toEpochMs(value: unknown): EpochMs {
	if (value === null || value === undefined || value === '') return null;
	if (typeof value === 'number') return Number.isFinite(value) ? value : null;
	if (typeof value === 'string') {
		if (/^-?\d+$/.test(value)) return Number(value);
		// A zone-less calendar string is read as UTC, matching what the
		// database does with the same input.
		const iso = DateTime.fromISO(value, { zone: 'utc' });
		return iso.isValid ? iso.toMillis() : null;
	}
	return null;
}

function inZone(ms: number, zone: string): DateTime {
	return DateTime.fromMillis(ms, { zone: zone || 'UTC' });
}

/** `YYYY-MM-DD` in the user's zone — the value `<input type="date">` wants. */
export function toDateInput(value: unknown, zone: string): string {
	const ms = toEpochMs(value);
	return ms === null ? '' : inZone(ms, zone).toFormat('yyyy-MM-dd');
}

/** `YYYY-MM-DDTHH:mm` in the user's zone, for `<input type="datetime-local">`. */
export function toDateTimeInput(value: unknown, zone: string): string {
	const ms = toEpochMs(value);
	return ms === null ? '' : inZone(ms, zone).toFormat("yyyy-MM-dd'T'HH:mm");
}

/** `YYYY-MM-DD` picked in the user's zone → the instant that day starts there. */
export function fromDateInput(text: string, zone: string): EpochMs {
	if (!text) return null;
	const dt = DateTime.fromFormat(text, 'yyyy-MM-dd', { zone: zone || 'UTC' });
	return dt.isValid ? dt.toMillis() : null;
}

/** `YYYY-MM-DDTHH:mm` picked in the user's zone → that instant. */
export function fromDateTimeInput(text: string, zone: string): EpochMs {
	if (!text) return null;
	const dt = DateTime.fromISO(text, { zone: zone || 'UTC' });
	return dt.isValid ? dt.toMillis() : null;
}

/** The value to send for an edited cell, by column type. */
export function fromInput(text: string, type: TemporalType, zone: string): EpochMs {
	return type === 'date' ? fromDateInput(text, zone) : fromDateTimeInput(text, zone);
}

/** The value to put in an input element for a cell, by column type. */
export function toInput(value: unknown, type: TemporalType, zone: string): string {
	return type === 'date' ? toDateInput(value, zone) : toDateTimeInput(value, zone);
}

/** Display text: a day for `date`, a day and time for `datetime`. */
export function formatTemporal(value: unknown, type: TemporalType, zone: string): string {
	const ms = toEpochMs(value);
	if (ms === null) return '';
	const dt = inZone(ms, zone);
	return type === 'date' ? dt.toFormat('yyyy-MM-dd') : dt.toFormat('yyyy-MM-dd HH:mm');
}

/**
 * Group key for a temporal cell, in the user's zone.
 *
 * The zone belongs in the key: a row's bucket is a statement about the day it
 * falls on for this reader, and reading it in UTC would put an evening entry
 * in the wrong day for most of the world.
 */
export function temporalGroupKey(
	value: unknown,
	granularity: 'month' | 'day',
	zone: string
): string {
	const ms = toEpochMs(value);
	if (ms === null) return '';
	const dt = inZone(ms, zone);
	return dt.toFormat(granularity === 'month' ? 'yyyy-MM' : 'yyyy-MM-dd');
}

/** Start of the day an instant falls on, in the user's zone. */
export function startOfDay(ms: number, zone: string): number {
	return inZone(ms, zone).startOf('day').toMillis();
}

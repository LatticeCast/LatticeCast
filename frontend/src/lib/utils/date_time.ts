// utils/date_time.ts
import { DateTime } from 'luxon';

export function getWeekdayAndTime(
	year: number,
	month: number,
	day: number,
	hour: number,
	minute: number,
	second: number,
	timezone: string
) {
	const dtUtc = DateTime.utc(year, month, day, hour, minute, second);
	const dtTz = dtUtc.setZone(timezone);

	return {
		weekday: dtTz.toFormat('cccc'), // e.g., "Sunday"
		time: dtTz.toFormat('HH:mm:ss') // e.g., "22:30:00"
	};
}

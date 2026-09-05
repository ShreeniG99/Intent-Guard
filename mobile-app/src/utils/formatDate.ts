/** SQLite's datetime('now') returns UTC with a space separator and no
 * timezone marker (e.g. "2026-09-05 08:29:05") -- JS's Date constructor
 * parses that as LOCAL time, not UTC, silently showing timestamps off by
 * the viewer's UTC offset. Converting to proper ISO-8601 UTC first fixes it. */
export function parseSqliteUtc(sqliteDatetime: string): Date {
  return new Date(sqliteDatetime.replace(' ', 'T') + 'Z');
}

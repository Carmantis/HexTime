/**
 * Money on its way into and out of the UI.
 *
 * Amounts are integer cents everywhere. Parsing works on the digits as text
 * and never goes through a float, so "0,1" + "0,2" style rounding errors
 * cannot creep into a stored rate.
 */

export type ParsedCents =
  | { kind: 'empty' }
  | { kind: 'invalid' }
  | { kind: 'ok'; cents: number };

/**
 * Read a user-typed amount such as "85", "85,5" or "1 250,00".
 *
 * Both a comma and a point are accepted as the decimal separator, so a Finnish
 * and an English user can type the way they are used to. Spaces (including the
 * no-break space Finnish formatting uses for thousands) are ignored.
 */
export function parseCents(input: string): ParsedCents {
  const cleaned = input.replace(/\s/g, '').replace(',', '.');
  if (cleaned === '') return { kind: 'empty' };

  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(cleaned);
  if (!match) return { kind: 'invalid' };

  const [, whole, fraction = ''] = match;
  return { kind: 'ok', cents: Number(whole) * 100 + Number(fraction.padEnd(2, '0')) };
}

/** Cents back into the text a user would type, e.g. 8550 → "85,50" in Finnish. */
export function centsToInput(cents: number, locale: string): string {
  const separator = locale === 'fi' ? ',' : '.';
  const whole = Math.trunc(cents / 100);
  const fraction = String(cents % 100).padStart(2, '0');
  return `${whole}${separator}${fraction}`;
}

/**
 * Cents as a formatted amount, e.g. "85,00 €".
 *
 * Display only. The division runs on an exact integer and its result is never
 * stored or added to anything — totals always come from the backend.
 */
export function formatCents(cents: number, locale: string, currency = 'EUR'): string {
  return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(cents / 100);
}

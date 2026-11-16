/**
 * Reading a pasted list of people for the administrator's "add people".
 *
 * People paste from wherever the staff list lives, so each line may be:
 *
 *   anna@example.org
 *   Anna Admin <anna@example.org>        (an email client's address list)
 *   Anna Admin, anna@example.org         (CSV, comma or semicolon)
 *   anna@example.org;Anna Admin
 *   Anna Admin<TAB>anna@example.org      (copied from Excel)
 *
 * The address is whatever looks like one; the rest of the line is the name.
 * Several addresses separated by commas on one line count as several people.
 * Lines without an address (a header row, a blank line) are reported back.
 */

export interface PastedPerson {
  email: string;
  display_name: string;
}

export interface PastedList {
  people: PastedPerson[];
  /** Non-empty lines with no address in them, to show the administrator. */
  skipped: string[];
}

const EMAIL = /[^\s<>,;"']+@[^\s<>,;"']+\.[^\s<>,;"']+/g;

/** What is left of a line once the address is out: the name, tidied. */
function nameFrom(rest: string): string {
  return rest
    .replace(/[<>"']/g, ' ')
    .replace(/[\t,;]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function parsePeople(text: string): PastedList {
  const people: PastedPerson[] = [];
  const skipped: string[] = [];

  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;

    const emails = line.match(EMAIL) ?? [];
    if (emails.length === 0) {
      skipped.push(line);
    } else if (emails.length === 1) {
      people.push({
        email: emails[0].toLowerCase(),
        display_name: nameFrom(line.replace(emails[0], '')),
      });
    } else {
      // "Anna <anna@x>, Ville <ville@x>": split on the separators between them.
      for (const part of line.split(/[,;]/)) {
        const found = part.match(EMAIL);
        if (found) {
          people.push({
            email: found[0].toLowerCase(),
            display_name: nameFrom(part.replace(found[0], '')),
          });
        }
      }
    }
  }
  return { people, skipped };
}

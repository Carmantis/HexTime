import { describe, expect, it } from 'vitest';

import { parsePeople } from './people';

describe('parsePeople', () => {
  it('takes a bare address', () => {
    expect(parsePeople('anna@example.org').people).toEqual([
      { email: 'anna@example.org', display_name: '' },
    ]);
  });

  it.each([
    ['Anna Admin <Anna@Example.ORG>'],
    ['Anna Admin, anna@example.org'],
    ['anna@example.org;Anna Admin'],
    ['Anna Admin\tanna@example.org'],
    ['"Anna Admin" <anna@example.org>'],
  ])('reads the name and address from %j', (line) => {
    expect(parsePeople(line).people).toEqual([
      { email: 'anna@example.org', display_name: 'Anna Admin' },
    ]);
  });

  it('reads one person per line, as pasted from Excel', () => {
    const { people } = parsePeople('Anna\tanna@example.org\nVille\tville@example.org\n');
    expect(people.map((p) => p.email)).toEqual(['anna@example.org', 'ville@example.org']);
  });

  it('splits an address list on one line', () => {
    const { people } = parsePeople('Anna <anna@example.org>, Ville <ville@example.org>');
    expect(people).toEqual([
      { email: 'anna@example.org', display_name: 'Anna' },
      { email: 'ville@example.org', display_name: 'Ville' },
    ]);
  });

  it('reports lines without an address instead of dropping them silently', () => {
    const { people, skipped } = parsePeople('Nimi\tSähköposti\n\nAnna\tanna@example.org');
    expect(people).toHaveLength(1);
    expect(skipped).toEqual(['Nimi\tSähköposti']);
  });
});

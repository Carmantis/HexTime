import { describe, expect, it } from 'vitest';

import en from './en.json';
import fi from './fi.json';

/** Every leaf key, flattened to its dotted path. */
function keysOf(bundle: unknown, prefix = ''): string[] {
  if (typeof bundle !== 'object' || bundle === null) return [prefix];

  return Object.entries(bundle as Record<string, unknown>)
    .flatMap(([key, value]) => keysOf(value, prefix ? `${prefix}.${key}` : key))
    .sort();
}

describe('translations', () => {
  it('have exactly the same keys in both languages', () => {
    // A key added to one file and forgotten in the other would otherwise show
    // up as a raw key in the UI, and only in the language nobody tested.
    expect(keysOf(en)).toEqual(keysOf(fi));
  });

  it('have no empty strings', () => {
    const empties = Object.entries({ fi, en }).flatMap(([language, bundle]) =>
      keysOf(bundle)
        .filter((key) => {
          const value = key
            .split('.')
            .reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], bundle);
          return typeof value === 'string' && value.trim() === '';
        })
        .map((key) => `${language}:${key}`),
    );

    expect(empties).toEqual([]);
  });
});

import { describe, expect, it } from 'vitest';

import { filenameFrom } from './client';

describe('filenameFrom', () => {
  it('reads the name the backend suggested', () => {
    expect(
      filenameFrom('attachment; filename="hextime-2026-10-01-2026-10-31.pdf"', 'x.pdf'),
    ).toBe('hextime-2026-10-01-2026-10-31.pdf');
  });

  it('falls back when there is no header', () => {
    expect(filenameFrom(null, 'hextime.pdf')).toBe('hextime.pdf');
  });

  it('falls back when the header has no file name', () => {
    expect(filenameFrom('inline', 'hextime.pdf')).toBe('hextime.pdf');
  });
});

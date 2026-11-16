import { describe, expect, it } from 'vitest';

import { centsToInput, parseCents } from './money';

describe('parseCents', () => {
  it.each([
    ['85', 8500],
    ['85,5', 8550],
    ['85,50', 8550],
    ['85.50', 8550],
    ['0,01', 1],
    ['1 250,00', 125000],
    ['1 250,00', 125000],
    [' 42 ', 4200],
  ])('reads %j as %i cents', (input, cents) => {
    expect(parseCents(input)).toEqual({ kind: 'ok', cents });
  });

  it('treats blank input as no rate at all', () => {
    expect(parseCents('')).toEqual({ kind: 'empty' });
    expect(parseCents('   ')).toEqual({ kind: 'empty' });
  });

  it.each(['abc', '-5', '85,555', '1,2,3', '€85', '85e2'])('rejects %j', (input) => {
    expect(parseCents(input)).toEqual({ kind: 'invalid' });
  });

  it('never goes through a float', () => {
    // 0.1 + 0.2 !== 0.3 in floating point; text parsing sidesteps that.
    const ten = parseCents('0,10');
    const twenty = parseCents('0,20');
    expect(ten.kind === 'ok' && twenty.kind === 'ok' && ten.cents + twenty.cents).toBe(30);
  });
});

describe('centsToInput', () => {
  it('uses the separator of the language', () => {
    expect(centsToInput(8550, 'fi')).toBe('85,50');
    expect(centsToInput(8550, 'en')).toBe('85.50');
  });

  it('pads single-digit cents', () => {
    expect(centsToInput(8505, 'fi')).toBe('85,05');
  });

  it('round-trips through parseCents', () => {
    for (const cents of [0, 1, 99, 100, 8550, 125000]) {
      expect(parseCents(centsToInput(cents, 'fi'))).toEqual({ kind: 'ok', cents });
    }
  });
});

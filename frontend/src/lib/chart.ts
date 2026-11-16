/**
 * Chart theming and labels.
 *
 * This module deliberately imports nothing from ECharts. Chart.svelte loads
 * the library dynamically so it only reaches a browser that actually draws a
 * chart, and a static import here would drag all of it back into the main
 * bundle for every view.
 *
 * Charts read the same CSS tokens as the rest of the UI, so a theme switch
 * changes them too. The values have to come from the computed style because
 * ECharts paints onto a canvas and cannot use CSS.
 */

export interface ChartTokens {
  text: string;
  muted: string;
  border: string;
  accent: string;
  surface: string;
}

/** The current theme's colours, read from tokens.css. */
export function chartTokens(): ChartTokens {
  const style = getComputedStyle(document.documentElement);
  const read = (name: string) => style.getPropertyValue(name).trim();

  return {
    text: read('--color-text'),
    muted: read('--color-text-muted'),
    border: read('--color-border'),
    accent: read('--color-accent'),
    surface: read('--color-surface-elevated'),
  };
}

/** Seconds as the "1 h 30 min" label used in axes, tooltips and bar labels. */
export function hoursLabel(seconds: number, locale: string): string {
  const minutes = Math.round(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  const unit = locale === 'fi' ? 't' : 'h';

  if (hours === 0) return `${rest} min`;
  if (rest === 0) return `${hours} ${unit}`;
  return `${hours} ${unit} ${rest} min`;
}

const MINUTE = 60;
const HOUR = 3600;

/**
 * Axis steps a person reads easily: quarter and half hours for short
 * periods, then whole hours in 1-2-5 style steps for longer ones.
 */
const HOUR_STEPS = [
  15 * MINUTE,
  30 * MINUTE,
  HOUR,
  2 * HOUR,
  4 * HOUR,
  5 * HOUR,
  10 * HOUR,
  20 * HOUR,
  25 * HOUR,
  50 * HOUR,
  100 * HOUR,
  200 * HOUR,
  250 * HOUR,
  500 * HOUR,
];

/**
 * The tick interval and axis end for a value axis measured in seconds.
 *
 * Left to itself ECharts picks round numbers *of seconds*, so 10 000 s became
 * a "2 h 47 min" tick. Fixing both the interval and the max makes every tick
 * a whole step, and the axis ends on a tick rather than at the tallest bar.
 */
export function hourAxis(maxSeconds: number, maxTicks: number): { interval: number; max: number } {
  const top = Math.max(maxSeconds, 1);
  const interval =
    HOUR_STEPS.find((step) => Math.ceil(top / step) <= maxTicks) ??
    // Beyond the table: whole multiples of the largest step.
    Math.ceil(top / maxTicks / HOUR_STEPS.at(-1)!) * HOUR_STEPS.at(-1)!;
  return { interval, max: Math.ceil(top / interval) * interval };
}

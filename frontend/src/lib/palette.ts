/**
 * The colours a user can give a project or a tag.
 *
 * These are the same eight swatches HexCalendar offers for events. They are
 * data rather than theme: each is stored with its row and only ever shown as a
 * dot, a thin border or a light tint, never as a large filled area. The first
 * one is HexCalendar's accent and the backend's default.
 */
export const SWATCHES = [
  '#4A90D9',
  '#E74C3C',
  '#2ECC71',
  '#F39C12',
  '#9B59B6',
  '#1ABC9C',
  '#E67E22',
  '#34495E',
] as const;

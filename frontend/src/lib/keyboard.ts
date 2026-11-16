/**
 * Keyboard shortcuts: S start/stop, N new entry, T today, ← → previous/next.
 *
 * One rule for all of them, kept here so no view has to remember it: a
 * shortcut never fires while the user is typing, while a modifier key is held
 * (Ctrl+S must stay the browser's), or while a dialog is open on top.
 */

function isTyping(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null;
  return Boolean(target?.closest('input, textarea, select, [contenteditable]'));
}

function dialogOpen(): boolean {
  return document.querySelector('[aria-modal="true"]') !== null;
}

/** True when `event` is the bare key `key` (case-insensitive) and may act. */
export function isPlainKey(event: KeyboardEvent, key: string): boolean {
  if (event.key.toLowerCase() !== key.toLowerCase()) return false;
  if (event.ctrlKey || event.metaKey || event.altKey) return false;
  return !isTyping(event) && !dialogOpen();
}

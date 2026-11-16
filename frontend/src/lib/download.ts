/**
 * Hand a file to the user.
 *
 * The file was fetched first (rather than linking to the URL) so that a
 * failure shows up as a translated error in the view instead of a page of
 * JSON. What happens next depends on where the page runs:
 *
 * - In a browser, a temporary object URL lets it download the file itself.
 * - In the desktop window there is no download manager, so the file goes to
 *   the window (app/desktop.py), which shows the system's "Save as" dialog.
 */
import type { DownloadedFile } from './api/client';

/** What app/desktop.py exposes to the page through pywebview. */
interface DesktopBridge {
  save_file(filename: string, dataBase64: string): Promise<boolean>;
}

declare global {
  interface Window {
    pywebview?: { api?: Partial<DesktopBridge> };
  }
}

function desktopBridge(): DesktopBridge | null {
  const api = window.pywebview?.api;
  return api?.save_file ? (api as DesktopBridge) : null;
}

/** A Blob as base64, the form the pywebview bridge can carry. */
async function toBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = '';
  // In chunks: spreading a large array into one call can overflow the stack.
  for (let index = 0; index < bytes.length; index += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  }
  return btoa(binary);
}

function browserDownload(file: DownloadedFile): void {
  const url = URL.createObjectURL(file.blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = file.filename;
  document.body.append(link);
  link.click();
  link.remove();
  // Revoked on the next tick: the click has started the download by then.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** Save the file. Resolves to false if the user cancelled the dialog. */
export async function saveFile(file: DownloadedFile): Promise<boolean> {
  const bridge = desktopBridge();
  if (bridge) {
    return bridge.save_file(file.filename, await toBase64(file.blob));
  }
  browserDownload(file);
  return true;
}

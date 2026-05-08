/**
 * Parses the standardised RESULT_JSON marker block emitted by Python scripts
 * (see emit_result() in src/scripts/_text_utils.py).
 *
 * The marker pattern is:
 *
 *     ### RESULT_JSON ###
 *     {...json...}
 *     ### END_RESULT_JSON ###
 *
 * The parser is permissive about surrounding debug output (every script
 * emits DEBUG/print lines around the markers) and tolerates trailing
 * whitespace.
 *
 * Usage:
 *   const r = parseResultJson<{value: string}>(result.output);
 *   if (r.ok) { ... r.data.value ... } else { ... r.error ... }
 */

export type ParseResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string };

const START = '### RESULT_JSON ###';
const END = '### END_RESULT_JSON ###';

export function parseResultJson<T = unknown>(output: string): ParseResult<T> {
  // Scan from the END of output: the real emit is always the last block,
  // so a stray copy of the marker text inside an earlier debug line (e.g.
  // a string variable that happens to contain `### RESULT_JSON ###`) won't
  // confuse the parser. Find the last START, then the first END after it.
  const startIdx = output.lastIndexOf(START);
  if (startIdx === -1) {
    return { ok: false, error: 'No RESULT_JSON block found in script output.' };
  }
  const afterStart = startIdx + START.length;
  const endIdx = output.indexOf(END, afterStart);
  if (endIdx === -1) {
    return { ok: false, error: 'RESULT_JSON block was opened but never closed.' };
  }
  const jsonText = output.slice(afterStart, endIdx).trim();
  if (jsonText.length === 0) {
    return { ok: false, error: 'RESULT_JSON block was empty.' };
  }
  try {
    return { ok: true, data: JSON.parse(jsonText) as T };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { ok: false, error: `RESULT_JSON parse failed: ${msg}` };
  }
}

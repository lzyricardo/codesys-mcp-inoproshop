/**
 * Python script template loading and interpolation.
 * Loads .py templates from src/scripts/ and performs {PARAM} replacement.
 */

import * as fs from 'fs';
import * as path from 'path';
import { ScriptParams } from './types';

/**
 * Escape a string for safe embedding inside an IronPython 2.7 double-quoted
 * string literal. Handles backslash, double-quote, single-quote, and the
 * standard line/whitespace escapes.
 */
function pyEscape(s: string): string {
  return s
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/'/g, "\\'")
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r')
    .replace(/\t/g, '\\t');
}

export class ScriptManager {
  private scriptsDir: string;

  constructor(scriptsDir?: string) {
    this.scriptsDir = scriptsDir ?? path.join(__dirname, 'scripts');
  }

  /** Load a template file from disk. */
  loadTemplate(name: string): string {
    const fileName = name.endsWith('.py') ? name : `${name}.py`;
    const filePath = path.join(this.scriptsDir, fileName);
    if (!fs.existsSync(filePath)) {
      throw new Error(`Script template not found: ${filePath}`);
    }
    return fs.readFileSync(filePath, 'utf-8');
  }

  /**
   * Replace {KEY} placeholders with Python-string-escaped values.
   *
   * Every value is escaped for safe embedding inside a Python double-quoted
   * string literal: backslashes, double/single quotes, and newline chars are
   * escaped. This eliminates injection bugs where a user-controlled identifier
   * (POU name, variable path, password) could contain a `"` that broke out
   * of the string literal in the generated IronPython source.
   *
   * For values that must be embedded outside a string (raw code blocks like
   * `set_pou_code` declaration/implementation), use `{KEY:raw}` in the template
   * - those placeholders skip escaping. set_pou_code.py applies its own
   * targeted escape for its triple-quoted blocks.
   *
   * The replace callback form is used so a `$` in the value isn't interpreted
   * as a regex backreference token.
   */
  interpolate(template: string, params: ScriptParams): string {
    let result = template;
    for (const [key, value] of Object.entries(params)) {
      const escaped = pyEscape(String(value));
      const escapedPattern = new RegExp(`\\{${key}\\}`, 'g');
      const rawPattern = new RegExp(`\\{${key}:raw\\}`, 'g');
      result = result.replace(rawPattern, () => String(value));
      result = result.replace(escapedPattern, () => escaped);
    }
    return result;
  }

  /** Concatenate multiple script fragments with double newlines */
  combineScripts(...scripts: string[]): string {
    return scripts.join('\n\n');
  }

  /** Load a template and interpolate parameters */
  prepareScript(name: string, params: ScriptParams): string {
    const template = this.loadTemplate(name);
    return this.interpolate(template, params);
  }

  /** Prepend helper scripts before the main script, then interpolate all */
  prepareScriptWithHelpers(
    name: string,
    params: ScriptParams,
    helpers: string[]
  ): string {
    const helperContents = helpers.map((h) => this.loadTemplate(h));
    const mainTemplate = this.loadTemplate(name);
    const combined = this.combineScripts(...helperContents, mainTemplate);
    return this.interpolate(combined, params);
  }
}

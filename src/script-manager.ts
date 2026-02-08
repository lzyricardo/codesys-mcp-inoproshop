/**
 * Python script template loading and interpolation.
 * Loads .py templates from src/scripts/, caches them, and performs {PARAM} replacement.
 */

import * as fs from 'fs';
import * as path from 'path';
import { ScriptParams } from './types';

export class ScriptManager {
  private scriptsDir: string;
  private cache: Map<string, string> = new Map();

  constructor(scriptsDir?: string) {
    this.scriptsDir = scriptsDir ?? path.join(__dirname, 'scripts');
  }

  /** Synchronously load a template file and cache it */
  loadTemplate(name: string): string {
    const fileName = name.endsWith('.py') ? name : `${name}.py`;
    const cached = this.cache.get(fileName);
    if (cached !== undefined) {
      return cached;
    }

    const filePath = path.join(this.scriptsDir, fileName);
    if (!fs.existsSync(filePath)) {
      throw new Error(`Script template not found: ${filePath}`);
    }

    const content = fs.readFileSync(filePath, 'utf-8');
    this.cache.set(fileName, content);
    return content;
  }

  /**
   * Replace {KEY} placeholders with values.
   * No automatic escaping — callers are responsible for escaping values
   * appropriate to their Python context (raw strings, triple-quoted strings, etc.).
   */
  interpolate(template: string, params: ScriptParams): string {
    let result = template;
    for (const [key, value] of Object.entries(params)) {
      const pattern = new RegExp(`\\{${key}\\}`, 'g');
      result = result.replace(pattern, String(value));
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

import { describe, it, expect } from 'vitest';
import * as path from 'path';
import { ScriptManager } from '../../src/script-manager';

const SCRIPTS_DIR = path.join(__dirname, '..', '..', 'src', 'scripts');

describe('ScriptManager', () => {
  const mgr = new ScriptManager(SCRIPTS_DIR);

  it('loads an existing template', () => {
    const content = mgr.loadTemplate('check_status');
    expect(content).toContain('scriptengine');
    expect(content).toContain('SCRIPT_SUCCESS');
  });

  it('throws for non-existent template', () => {
    expect(() => mgr.loadTemplate('nonexistent_script')).toThrow(/not found/);
  });

  it('interpolates a single param', () => {
    const result = mgr.interpolate('hello {FOO}', { FOO: 'bar' });
    expect(result).toBe('hello bar');
  });

  it('Python-escapes backslashes for regular string templates', () => {
    const result = mgr.interpolate('path = "{PATH}"', {
      PATH: 'C:\\Users\\Test',
    });
    // Each \ becomes \\ in source so Python decodes it back to a single \.
    expect(result).toBe('path = "C:\\\\Users\\\\Test"');
  });

  it('Python-escapes triple quotes (single " each, safe in triple-quoted)', () => {
    const result = mgr.interpolate('code = """{CODE}"""', {
      CODE: 'a """ b',
    });
    // Each " is escaped to \" - safe in both regular and triple-quoted strings.
    expect(result).toBe('code = """a \\"\\"\\" b"""');
  });

  it('escapes single quotes', () => {
    const result = mgr.interpolate('s = "{S}"', { S: "it's" });
    expect(result).toBe('s = "it\\\'s"');
  });

  it('escapes newlines so source stays single-line per template line', () => {
    const result = mgr.interpolate('s = "{S}"', { S: 'line1\nline2' });
    expect(result).toBe('s = "line1\\nline2"');
  });

  it('{KEY:raw} bypasses escaping for code-block embedding', () => {
    const result = mgr.interpolate('code = {C:raw}', { C: 'print("hi")' });
    expect(result).toBe('code = print("hi")');
  });

  it('does not interpret $ in value as a regex backref', () => {
    const result = mgr.interpolate('s = "{S}"', { S: '$&' });
    expect(result).toBe('s = "$&"');
  });

  it('interpolates multiple params', () => {
    const result = mgr.interpolate('{A} and {B}', { A: 'x', B: 'y' });
    expect(result).toBe('x and y');
  });

  it('two reads of the same template return identical content', () => {
    // The cache was removed in 0.6.1; loadTemplate now reads from disk every
    // call. This test asserts content stability, not reference equality.
    const first = mgr.loadTemplate('check_status');
    const second = mgr.loadTemplate('check_status');
    expect(first).toEqual(second);
  });

  it('combineScripts concatenates with double newlines', () => {
    const result = mgr.combineScripts('script1', 'script2', 'script3');
    expect(result).toBe('script1\n\nscript2\n\nscript3');
  });

  it('prepareScript loads and interpolates with Python escape', () => {
    const result = mgr.prepareScript('create_project', {
      PROJECT_FILE_PATH: 'C:\\Projects\\test.project',
      TEMPLATE_PROJECT_PATH: 'C:\\Templates\\Standard.project',
    });
    // Backslashes are escaped for embedding in regular Python string literals.
    expect(result).toContain('C:\\\\Projects\\\\test.project');
    expect(result).toContain('C:\\\\Templates\\\\Standard.project');
  });

  it('prepareScriptWithHelpers prepends helpers', () => {
    const result = mgr.prepareScriptWithHelpers(
      'open_project',
      { PROJECT_FILE_PATH: 'C:\\test.project' },
      ['ensure_project_open']
    );
    // ensure_project_open content should appear before open_project content
    const ensureIdx = result.indexOf('def ensure_project_open');
    const openIdx = result.indexOf('Project Opened');
    expect(ensureIdx).toBeGreaterThan(-1);
    expect(openIdx).toBeGreaterThan(-1);
    expect(ensureIdx).toBeLessThan(openIdx);
  });

  it('Windows path with spaces passes through correctly', () => {
    const result = mgr.interpolate('path = "{PATH}"', {
      PATH: 'C:\\Program Files\\CODESYS',
    });
    // Backslashes escaped, spaces unchanged.
    expect(result).toBe('path = "C:\\\\Program Files\\\\CODESYS"');
  });
});

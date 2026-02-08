import { describe, it, expect } from 'vitest';
import * as path from 'path';
import { ScriptManager } from '../../src/script-manager';

/**
 * Integration tests that verify the full script preparation pipeline.
 * These don't require CODESYS but verify the template system works end-to-end.
 */
describe('E2E Script Preparation', () => {
  const scriptsDir = path.join(__dirname, '..', '..', 'src', 'scripts');
  const mgr = new ScriptManager(scriptsDir);

  it('open_project script prepares correctly with helpers', () => {
    const script = mgr.prepareScriptWithHelpers(
      'open_project',
      { PROJECT_FILE_PATH: 'C:\\Projects\\Test.project' },
      ['ensure_project_open']
    );
    // Should contain ensure_project_open function
    expect(script).toContain('def ensure_project_open');
    // Should contain the actual open logic
    expect(script).toContain('Project Opened');
    // Path should appear as-is (no escaping) since templates use r"..." raw strings
    expect(script).toContain('C:\\Projects\\Test.project');
    // Should contain success marker
    expect(script).toContain('SCRIPT_SUCCESS');
  });

  it('create_pou script prepares with both helpers', () => {
    const script = mgr.prepareScriptWithHelpers(
      'create_pou',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        POU_NAME: 'MyProgram',
        POU_TYPE_STR: 'Program',
        IMPL_LANGUAGE_STR: 'ST',
        PARENT_PATH: 'Application',
      },
      ['ensure_project_open', 'find_object_by_path']
    );
    expect(script).toContain('def ensure_project_open');
    expect(script).toContain('def find_object_by_path_robust');
    expect(script).toContain('MyProgram');
    expect(script).toContain('POU_TYPE_STR = "Program"');
  });

  it('set_pou_code script handles pre-escaped code content', () => {
    // Simulate what server.ts does: manually escape code for triple-quoted strings
    const declCode = 'VAR\\n  x : INT;\\nEND_VAR';
    const implCode = 'x := 42;';
    const sanDecl = declCode.replace(/\\/g, '\\\\').replace(/"""/g, '\\"\\"\\"');
    const sanImpl = implCode.replace(/\\/g, '\\\\').replace(/"""/g, '\\"\\"\\"');

    const script = mgr.prepareScriptWithHelpers(
      'set_pou_code',
      {
        PROJECT_FILE_PATH: 'C:\\test.project',
        POU_FULL_PATH: 'Application/MyPOU',
        DECLARATION_CONTENT: sanDecl,
        IMPLEMENTATION_CONTENT: sanImpl,
      },
      ['ensure_project_open', 'find_object_by_path']
    );
    expect(script).toContain('Application/MyPOU');
    expect(script).toContain('x := 42;');
  });

  it('check_status script has no placeholders after load', () => {
    const script = mgr.loadTemplate('check_status');
    // check_status has no {PLACEHOLDER} params
    expect(script).not.toMatch(/\{[A-Z_]+\}/);
    expect(script).toContain('SCRIPT_SUCCESS');
  });

  it('compile_project script prepares with ensure_project_open', () => {
    const script = mgr.prepareScriptWithHelpers(
      'compile_project',
      { PROJECT_FILE_PATH: 'C:\\test.project' },
      ['ensure_project_open']
    );
    expect(script).toContain('def ensure_project_open');
    expect(script).toContain('build()');
  });

  it('all scripts are loadable', () => {
    const scriptNames = [
      'check_status', 'compile_project', 'create_method', 'create_pou',
      'create_project', 'create_property', 'ensure_project_open',
      'find_object_by_path', 'get_pou_code', 'get_project_structure',
      'open_project', 'save_project', 'set_pou_code', 'watcher',
    ];
    for (const name of scriptNames) {
      expect(() => mgr.loadTemplate(name)).not.toThrow();
      const content = mgr.loadTemplate(name);
      expect(content.length).toBeGreaterThan(0);
    }
  });
});

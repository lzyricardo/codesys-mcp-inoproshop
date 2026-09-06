#!/usr/bin/env node
/**
 * CLI entry point for codesys-mcp-inoproshop.
 *
 * Improved for InoProShop (V1.9.1.6 / V1.10.0.3). Persistent-UI core
 * retained from upstream codesys-mcp-persistent (luke-harriman).
 */

import { program } from 'commander';
import { startMcpServer } from './server';
import { ServerConfig, ExecutionMode } from './types';

let version = '1.0.0';
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const pkg = require('../package.json');
  version = pkg.version;
} catch {
  // ignore
}

// InoProShop default installation (V1.9.1.6 and V1.10.0.3 share the same path)
// Default = the path the user's original (broken) MCP used and that is
// actually installed on this machine. Both the legacy `CODESYS\Common` and the
// newer `InoProShop\CODESYS\Common` layouts exist as V1.9.1.6; we default to
// the legacy one because that is what the original config validated against.
const DEFAULT_INOPROSHOP_PATH = 'D:\\Inovance Control\\CODESYS\\Common\\InoProShop.exe';
const DEFAULT_PROFILE_V1916 = 'InoProShop(V1.9.1.6)';
const DEFAULT_PROFILE_V11003 = 'InoProShop(V1.10.0.3)';

program
  .name('codesys-mcp-inoproshop')
  .description('MCP server for InoProShop with persistent UI instance (single-window). Improved from codesys-mcp-persistent to fix repeated window pop-ups.')
  .version(version)
  .option(
    '-p, --codesys-path <path>',
    'Path to InoProShop executable',
    process.env.CODESYS_PATH || DEFAULT_INOPROSHOP_PATH
  )
  .option(
    '-f, --codesys-profile <profile>',
    'InoProShop profile name (e.g. "InoProShop(V1.9.1.6)" or "InoProShop(V1.10.0.3)")',
    process.env.CODESYS_PROFILE || DEFAULT_PROFILE_V1916
  )
  .option(
    '-w, --workspace <dir>',
    'Workspace directory for relative project paths',
    process.env.CODESYS_WORKSPACE || process.cwd()
  )
  .option(
    '-m, --mode <mode>',
    'Execution mode: persistent (UI) or headless (--noUI)',
    'persistent'
  )
  .option('--no-auto-launch', 'Do not auto-launch InoProShop on startup')
  .option('--fallback-headless', 'Fall back to headless if persistent fails', true)
  .option('--keep-alive', 'Keep InoProShop running after server stops', false)
  .option('--kill-existing-inoproshop', 'Kill any running InoProShop.exe before launching (dev convenience; off by default)', false)
  .option('--timeout <ms>', 'Default per-command IPC timeout in ms (bumped from upstream 60000 to 900000 for InoProShop stability)', '900000')
  .option('--ready-timeout <ms>', 'InoProShop startup ready-signal timeout in ms', '180000')
  .option('--verbose', 'Enable verbose logging')
  .option('--debug', 'Enable debug logging (more verbose)')
  .option('--detect', 'Detect installed InoProShop versions and exit')
  .parse(process.argv);

const opts = program.opts();

// Handle --detect flag: scan common InoProShop install paths
if (opts.detect) {
  import('fs').then((fs) => {
    import('path').then((pathMod) => {
      const candidates = [
        'D:\\Inovance Control\\CODESYS\\Common\\InoProShop.exe',
        'D:\\Inovance Control\\InoProShop\\CODESYS\\Common\\InoProShop.exe',
        'D:\\Inovance Control\\InoProShop\\CODESYS\\Common\\x64\\Common64\\InoProShop.exe',
        'C:\\Program Files\\InoProShop\\CODESYS\\Common\\InoProShop.exe',
      ];
      process.stderr.write('Scanning for InoProShop installations...\n\n');
      let found = 0;
      for (const exe of candidates) {
        const exists = fs.existsSync(exe);
        process.stderr.write(`  ${exists ? '[OK]' : '[--]'} ${exe}\n`);
        if (exists) {
          try {
            const { execSync } = require('child_process');
            const out = execSync(
              `powershell -NoProfile -Command "(Get-Item '${exe}').VersionInfo.FileVersion"`,
              { timeout: 5000 }
            ).toString().trim();
            process.stderr.write(`        Version: ${out}\n`);
            found++;
          } catch {
            process.stderr.write(`        Version: <unable to read>\n`);
            found++;
          }
        }
      }
      process.stderr.write(`\nFound ${found} InoProShop installation(s).\n`);
      process.stderr.write(`\nDefault profile candidates:\n  - ${DEFAULT_PROFILE_V1916}\n  - ${DEFAULT_PROFILE_V11003}\n`);
      process.stderr.write(`(Check actual installed profile name under:\n  D:\\Inovance Control\\InoProShop\\CODESYS\\<version>\\)\n`);
      process.exit(0);
    });
  });
} else {
  // Build server config
  const config: ServerConfig = {
    codesysPath: opts.codesysPath.trim(),
    profileName: opts.codesysProfile.trim(),
    workspaceDir: opts.workspace.trim(),
    autoLaunch: opts.autoLaunch !== false,
    keepAlive: opts.keepAlive || false,
    killExistingCodesys: opts.killExistingInoproshop || false,
    timeoutMs: parseInt(opts.timeout, 10) || 900000,
    fallbackHeadless: opts.fallbackHeadless !== false,
    verbose: opts.verbose || false,
    debug: opts.debug || false,
    mode: (opts.mode === 'headless' ? 'headless' : 'persistent') as ExecutionMode,
  };

  process.stderr.write(`Starting InoProShop MCP Server v${version}\n`);
  process.stderr.write(`  InoProShop Path: ${config.codesysPath}\n`);
  process.stderr.write(`  Profile: ${config.profileName}\n`);
  process.stderr.write(`  Workspace: ${config.workspaceDir}\n`);
  process.stderr.write(`  Mode: ${config.mode}\n`);
  process.stderr.write(`  Command timeout: ${config.timeoutMs}ms\n`);
  process.stderr.write(`  Ready timeout: ${opts.readyTimeout}ms\n`);
  process.stderr.write(`  Auto-launch: ${config.autoLaunch}\n`);

  startMcpServer(config).catch((err) => {
    process.stderr.write(`FATAL: ${err.message}\n`);
    process.exit(1);
  });
}

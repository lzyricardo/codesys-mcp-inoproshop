/**
 * Integration smoke test for the InoProShop persistent MCP launcher.
 *
 * Validates the two core fixes on a real InoProShop V1.9.1.6 install:
 *   1. Multiple tool calls reuse ONE InoProShop window (no per-call pop-up).
 *   2. An MCP-server "reconnect" (a fresh launcher with the same config)
 *      adopts the existing session instead of spawning a second window.
 *
 * Run:  npx tsx test/integration-launch.ts
 */

import { CodesysLauncher } from '../src/launcher';
import { LauncherConfig } from '../src/types';
import { execSync } from 'child_process';

function countInoProShop(): number {
  try {
    const out = execSync(
      'tasklist /NH /FI "IMAGENAME eq InoProShop.exe"',
      { stdio: ['ignore', 'pipe', 'ignore'] }
    ).toString();
    return out.split('\n').filter((l) => l.includes('InoProShop.exe')).length;
  } catch {
    return 0;
  }
}

const config: LauncherConfig = {
  codesysPath: 'D:\\Inovance Control\\CODESYS\\Common\\InoProShop.exe',
  profileName: 'InoProShop(V1.9.1.6)',
  workspaceDir: 'D:\\_mcp_restore\\codesys-mcp-improved\\test-workspace',
  killExistingCodesys: false,
};

const SIMPLE = `
import sys
print("PY " + sys.version.split()[0])
print("FRAME " + str(sys.platform))
print("SCRIPT_SUCCESS")
sys.exit(0)
`;

const ENGINE_PROBE = `
import scriptengine as se
try:
    print("engine-module=scriptengine")
    print("has-app=" + str(hasattr(se, "app")))
    print("has-system=" + str(hasattr(se, "system")))
except Exception as e:
    print("engine-probe-err=" + str(e))
print("SCRIPT_SUCCESS")
sys.exit(0)
`;

async function main() {
  const baseline = countInoProShop();
  console.log(`[baseline] InoProShop.exe processes = ${baseline}`);

  // --- Launcher #1: first launch (cold start) ---
  const l1 = new CodesysLauncher(config);
  console.log('\n[1] Launching first InoProShop session (cold start, may take ~120s)...');
  const t0 = Date.now();
  await l1.launch();
  console.log(`    ready in ${(Date.now() - t0) / 1000}s, pid=${l1.getStatus().pid}, state=${l1.getStatus().state}`);

  const afterLaunch = countInoProShop();
  if (afterLaunch !== baseline + 1) {
    throw new Error(`Expected exactly 1 new InoProShop process (got ${afterLaunch - baseline}).`);
  }
  console.log(`[1] processes now = ${afterLaunch}  (expected ${baseline + 1})  OK`);

  // --- Send 3 distinct scripts (simulating 3 separate tool calls) ---
  for (let i = 1; i <= 3; i++) {
    const r = await l1.executeScript(i === 2 ? ENGINE_PROBE : SIMPLE, 60_000);
    const stillOne = countInoProShop();
    const samePid = l1.getStatus().pid;
    console.log(`[call ${i}] success=${r.success} pid=${samePid} processes=${stillOne}`);
    if (stillOne !== baseline + 1) {
      throw new Error(`Window count changed during call ${i} (processes=${stillOne}). Single-instance guarantee violated!`);
    }
    if (!r.success) {
      console.log('    output:', r.output);
      console.log('    error :', r.error);
    }
  }
  console.log('[calls] 3 tool calls reused the SAME window — no pop-ups. OK');

  // --- Launcher #2: simulate an MCP-server restart / reconnect ---
  const l2 = new CodesysLauncher(config);
  console.log('\n[2] Simulating MCP reconnect with a fresh launcher (should ADOPT, not spawn)...');
  const t1 = Date.now();
  await l2.launch();
  console.log(`    adopted in ${(Date.now() - t1) / 1000}s, pid=${l2.getStatus().pid}, state=${l2.getStatus().state}`);
  const afterAdopt = countInoProShop();
  if (afterAdopt !== baseline + 1) {
    throw new Error(`Reconnect spawned a NEW window (processes=${afterAdopt}, expected ${baseline + 1}). Fix failed!`);
  }
  console.log(`[2] processes still = ${afterAdopt}  (no second window)  OK`);

  // --- Shut down the adopted session cleanly ---
  console.log('\n[3] Shutting down the persistent session...');
  await l2.shutdown();
  // Give the process a moment to exit.
  await new Promise((r) => setTimeout(r, 4_000));
  const afterShutdown = countInoProShop();
  console.log(`[3] processes after shutdown = ${afterShutdown}  (expected ${baseline})`);

  console.log('\n========== TEST PASSED ==========');
  console.log('Single persistent InoProShop instance maintained across multiple');
  console.log('tool calls AND an MCP reconnect. No repeated window pop-ups.');
  process.exit(0);
}

main().catch((e) => {
  console.error('\n========== TEST FAILED ==========');
  console.error(e);
  process.exit(1);
});

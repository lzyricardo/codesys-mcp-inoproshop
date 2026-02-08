/**
 * MCP Server — registers tools and resources for CODESYS automation.
 * Supports persistent (watcher-based) and headless (spawn-per-command) modes.
 */

import * as path from 'path';
import * as fs from 'fs';
import { McpServer, ResourceTemplate } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { ServerConfig, IpcResult, ScriptExecutor, ExecutionMode } from './types';
import { CodesysLauncher } from './launcher';
import { HeadlessExecutor } from './headless';
import { ScriptManager } from './script-manager';
import { serverLog, setLogLevel } from './logger';

// Zod enums for POU tools
const PouTypeEnum = z.enum(['Program', 'FunctionBlock', 'Function']);
const ImplementationLanguageEnum = z.enum([
  'ST', 'LD', 'FBD', 'SFC', 'IL', 'CFC',
  'StructuredText', 'LadderDiagram', 'FunctionBlockDiagram',
  'SequentialFunctionChart', 'InstructionList', 'ContinuousFunctionChart',
]);

/** Resolve a file path to an absolute normalized path */
function resolvePath(filePath: string, workspaceDir: string): string {
  return path.normalize(
    path.isAbsolute(filePath) ? filePath : path.join(workspaceDir, filePath)
  );
}

/** Sanitize a POU path (forward slashes, no leading/trailing slashes) */
function sanitizePouPath(pouPath: string): string {
  return pouPath.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
}

/** Format an IpcResult into an MCP tool response */
function formatToolResponse(
  result: IpcResult,
  successMessage: string
): { content: Array<{ type: 'text'; text: string }>; isError: boolean } {
  const success = result.success && result.output.includes('SCRIPT_SUCCESS');
  return {
    content: [
      {
        type: 'text' as const,
        text: success
          ? successMessage
          : `Operation failed. Output:\n${result.output}${result.error ? '\nError: ' + result.error : ''}`,
      },
    ],
    isError: !success,
  };
}

/** Check if a file exists (async) */
async function fileExists(filePath: string): Promise<boolean> {
  try {
    fs.statSync(filePath);
    return true;
  } catch {
    return false;
  }
}

export async function startMcpServer(config: ServerConfig): Promise<void> {
  // Set log level
  if (config.debug) setLogLevel('debug');
  else if (config.verbose) setLogLevel('info');

  serverLog.info(`Starting CODESYS Persistent MCP Server v0.1.0`);
  serverLog.info(`Mode: ${config.mode}`);
  serverLog.info(`CODESYS Path: ${config.codesysPath}`);
  serverLog.info(`Profile: ${config.profileName}`);
  serverLog.info(`Workspace: ${config.workspaceDir}`);

  // Validate CODESYS path
  if (!fs.existsSync(config.codesysPath)) {
    throw new Error(`CODESYS executable not found: ${config.codesysPath}`);
  }

  // Initialize executor based on mode
  let executor: ScriptExecutor;
  let launcher: CodesysLauncher | null = null;
  let executionMode: ExecutionMode = config.mode;

  if (config.mode === 'persistent') {
    launcher = new CodesysLauncher(config);

    if (config.autoLaunch) {
      try {
        await launcher.launch();
        executor = launcher;
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : String(err);
        serverLog.error(`Persistent launch failed: ${errMsg}`);
        if (config.fallbackHeadless) {
          serverLog.warn('Falling back to headless mode');
          executor = new HeadlessExecutor(config);
          executionMode = 'headless';
        } else {
          throw err;
        }
      }
    } else {
      // Launcher exists but not yet launched — will use headless until manually launched
      executor = new HeadlessExecutor(config);
      executionMode = 'headless';
    }
  } else {
    executor = new HeadlessExecutor(config);
  }

  const scriptManager = new ScriptManager();
  const workspaceDir = config.workspaceDir;

  // Create MCP server
  const server = new McpServer(
    {
      name: 'CODESYS Persistent MCP Server',
      version: '0.1.0',
    },
    {
      capabilities: {
        resources: { listChanged: true },
        tools: { listChanged: true },
      },
    }
  );

  // Note: using 'as any' cast on server for tool() calls to work around
  // TS2589 deep type instantiation with MCP SDK generics + Zod.
  const s = server as any;

  // ─── Management Tools ────────────────────────────────────────────────

  s.tool(
    'launch_codesys',
    'Manually launch CODESYS with UI. Use when --no-auto-launch was set.',
    async () => {
      if (!launcher) {
        return {
          content: [{ type: 'text' as const, text: 'Persistent mode not configured. Use --mode persistent.' }],
          isError: true,
        };
      }
      try {
        await launcher.launch();
        executor = launcher;
        executionMode = 'persistent';
        return {
          content: [{ type: 'text' as const, text: 'CODESYS launched successfully in persistent mode.' }],
          isError: false,
        };
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          content: [{ type: 'text' as const, text: `Launch failed: ${msg}` }],
          isError: true,
        };
      }
    }
  );

  s.tool(
    'shutdown_codesys',
    'Shut down the persistent CODESYS instance.',
    async () => {
      if (!launcher) {
        return {
          content: [{ type: 'text' as const, text: 'No persistent CODESYS instance to shut down.' }],
          isError: true,
        };
      }
      try {
        await launcher.shutdown();
        executor = new HeadlessExecutor(config);
        executionMode = 'headless';
        return {
          content: [{ type: 'text' as const, text: 'CODESYS shut down successfully.' }],
          isError: false,
        };
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          content: [{ type: 'text' as const, text: `Shutdown failed: ${msg}` }],
          isError: true,
        };
      }
    }
  );

  s.tool(
    'get_codesys_status',
    'Get the current status of the CODESYS instance (state, PID, mode).',
    async () => {
      const status = launcher ? launcher.getStatus() : {
        state: 'stopped',
        pid: null,
        sessionId: null,
        ipcDir: null,
        startedAt: null,
        lastError: null,
      };
      const text = [
        `State: ${status.state}`,
        `Mode: ${executionMode}`,
        `PID: ${status.pid ?? 'N/A'}`,
        `Session: ${status.sessionId ?? 'N/A'}`,
        `Started: ${status.startedAt ? new Date(status.startedAt).toISOString() : 'N/A'}`,
        status.lastError ? `Last Error: ${status.lastError}` : null,
      ].filter(Boolean).join('\n');
      return {
        content: [{ type: 'text' as const, text }],
        isError: false,
      };
    }
  );

  // ─── Project Tools ───────────────────────────────────────────────────

  s.tool(
    'open_project',
    'Opens an existing CODESYS project file.',
    {
      filePath: z.string().describe("Path to the project file (e.g., 'C:/Projects/MyPLC.project')."),
    },
    async (args: { filePath: string }) => {
      const escaped = resolvePath(args.filePath, workspaceDir);
      const script = scriptManager.prepareScriptWithHelpers(
        'open_project', { PROJECT_FILE_PATH: escaped }, ['ensure_project_open']
      );
      const result = await executor.executeScript(script);
      return formatToolResponse(result, `Project opened: ${args.filePath}`);
    }
  );

  s.tool(
    'create_project',
    'Creates a new CODESYS project from the standard template.',
    {
      filePath: z.string().describe("Path where the new project file should be created."),
    },
    async (args: { filePath: string }) => {
      const absPath = path.normalize(
        path.isAbsolute(args.filePath) ? args.filePath : path.join(workspaceDir, args.filePath)
      );

      // Find template project
      let templatePath = '';
      try {
        const baseDir = path.dirname(path.dirname(config.codesysPath));
        templatePath = path.normalize(path.join(baseDir, 'Templates', 'Standard.project'));
        if (!(await fileExists(templatePath))) {
          const programData = process.env.ALLUSERSPROFILE || process.env.ProgramData || 'C:\\ProgramData';
          const pd1 = path.normalize(path.join(programData, 'CODESYS', 'CODESYS', config.profileName, 'Templates', 'Standard.project'));
          if (await fileExists(pd1)) {
            templatePath = pd1;
          } else {
            const pd2 = path.normalize(path.join(programData, 'CODESYS', 'Templates', 'Standard.project'));
            if (await fileExists(pd2)) {
              templatePath = pd2;
            } else {
              throw new Error('Standard template project file not found.');
            }
          }
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        return {
          content: [{ type: 'text' as const, text: `Template Error: ${msg}` }],
          isError: true,
        };
      }

      const script = scriptManager.prepareScript('create_project', {
        PROJECT_FILE_PATH: absPath,
        TEMPLATE_PROJECT_PATH: templatePath,
      });
      const result = await executor.executeScript(script);
      return formatToolResponse(result, `Project created from template: ${absPath}`);
    }
  );

  s.tool(
    'save_project',
    'Saves the currently open CODESYS project.',
    {
      projectFilePath: z.string().describe("Path to the project file to ensure is open before saving."),
    },
    async (args: { projectFilePath: string }) => {
      const escaped = resolvePath(args.projectFilePath, workspaceDir);
      const script = scriptManager.prepareScriptWithHelpers(
        'save_project', { PROJECT_FILE_PATH: escaped }, ['ensure_project_open']
      );
      const result = await executor.executeScript(script);
      return formatToolResponse(result, `Project saved: ${args.projectFilePath}`);
    }
  );

  // ─── POU Tools ───────────────────────────────────────────────────────

  s.tool(
    'create_pou',
    'Creates a new Program, Function Block, or Function POU within the specified CODESYS project.',
    {
      projectFilePath: z.string().describe("Path to the project file."),
      name: z.string().describe("Name for the new POU (must be a valid IEC identifier)."),
      type: z.string().describe("Type of POU: Program, FunctionBlock, or Function."),
      language: z.string().describe("Implementation language: ST, LD, FBD, SFC, IL, or CFC."),
      parentPath: z.string().describe("Relative path under project root or application (e.g., 'Application')."),
    },
    async (args: { projectFilePath: string; name: string; type: string; language: string; parentPath: string }) => {
      const escProjPath = resolvePath(args.projectFilePath, workspaceDir);
      const sanParentPath = sanitizePouPath(args.parentPath);
      const script = scriptManager.prepareScriptWithHelpers(
        'create_pou',
        {
          PROJECT_FILE_PATH: escProjPath,
          POU_NAME: args.name.trim(),
          POU_TYPE_STR: args.type,
          IMPL_LANGUAGE_STR: args.language,
          PARENT_PATH: sanParentPath,
        },
        ['ensure_project_open', 'find_object_by_path']
      );
      const result = await executor.executeScript(script);
      return formatToolResponse(
        result,
        `POU '${args.name}' created in '${sanParentPath}' of ${args.projectFilePath}. Project saved.`
      );
    }
  );

  s.tool(
    'set_pou_code',
    'Sets the declaration and/or implementation code for a specific POU, Method, or Property.',
    {
      projectFilePath: z.string().describe("Path to the project file."),
      pouPath: z.string().describe("Full relative path to the target object (e.g., 'Application/MyPOU')."),
      declarationCode: z.string().optional().describe("Code for the declaration part (VAR...END_VAR). If omitted, not changed."),
      implementationCode: z.string().optional().describe("Code for the implementation logic. If omitted, not changed."),
    },
    async (args: { projectFilePath: string; pouPath: string; declarationCode?: string; implementationCode?: string }) => {
      if (args.declarationCode === undefined && args.implementationCode === undefined) {
        return {
          content: [{ type: 'text' as const, text: 'Error: At least one of declarationCode or implementationCode must be provided.' }],
          isError: true,
        };
      }
      const escProjPath = resolvePath(args.projectFilePath, workspaceDir);
      const sanPouPath = sanitizePouPath(args.pouPath);
      // Escape for triple-quoted Python strings
      const sanDecl = (args.declarationCode ?? '').replace(/\\/g, '\\\\').replace(/"""/g, '\\"\\"\\"');
      const sanImpl = (args.implementationCode ?? '').replace(/\\/g, '\\\\').replace(/"""/g, '\\"\\"\\"');
      const script = scriptManager.prepareScriptWithHelpers(
        'set_pou_code',
        {
          PROJECT_FILE_PATH: escProjPath,
          POU_FULL_PATH: sanPouPath,
          DECLARATION_CONTENT: sanDecl,
          IMPLEMENTATION_CONTENT: sanImpl,
        },
        ['ensure_project_open', 'find_object_by_path']
      );
      const result = await executor.executeScript(script);
      return formatToolResponse(
        result,
        `Code set for '${sanPouPath}' in ${args.projectFilePath}. Project saved.`
      );
    }
  );

  s.tool(
    'create_property',
    'Creates a new Property within a specific Function Block POU.',
    {
      projectFilePath: z.string().describe("Path to the project file."),
      parentPouPath: z.string().describe("Relative path to the parent Function Block POU (e.g., 'Application/MyFB')."),
      propertyName: z.string().describe("Name for the new property (must be a valid IEC identifier)."),
      propertyType: z.string().describe("Data type of the property (e.g., 'BOOL', 'INT', 'MyDUT')."),
    },
    async (args: { projectFilePath: string; parentPouPath: string; propertyName: string; propertyType: string }) => {
      const escProjPath = resolvePath(args.projectFilePath, workspaceDir);
      const sanParentPath = sanitizePouPath(args.parentPouPath);
      const script = scriptManager.prepareScriptWithHelpers(
        'create_property',
        {
          PROJECT_FILE_PATH: escProjPath,
          PARENT_POU_FULL_PATH: sanParentPath,
          PROPERTY_NAME: args.propertyName.trim(),
          PROPERTY_TYPE: args.propertyType.trim(),
        },
        ['ensure_project_open', 'find_object_by_path']
      );
      const result = await executor.executeScript(script);
      return formatToolResponse(
        result,
        `Property '${args.propertyName}' created under '${sanParentPath}' in ${args.projectFilePath}. Project saved.`
      );
    }
  );

  s.tool(
    'create_method',
    'Creates a new Method within a specific Function Block POU.',
    {
      projectFilePath: z.string().describe("Path to the project file."),
      parentPouPath: z.string().describe("Relative path to the parent Function Block POU (e.g., 'Application/MyFB')."),
      methodName: z.string().describe("Name of the new method (must be a valid IEC identifier)."),
      returnType: z.string().optional().describe("Return type (e.g., 'BOOL', 'INT'). Leave empty or omit for no return value."),
    },
    async (args: { projectFilePath: string; parentPouPath: string; methodName: string; returnType?: string }) => {
      const escProjPath = resolvePath(args.projectFilePath, workspaceDir);
      const sanParentPath = sanitizePouPath(args.parentPouPath);
      const script = scriptManager.prepareScriptWithHelpers(
        'create_method',
        {
          PROJECT_FILE_PATH: escProjPath,
          PARENT_POU_FULL_PATH: sanParentPath,
          METHOD_NAME: args.methodName.trim(),
          RETURN_TYPE: (args.returnType ?? '').trim(),
        },
        ['ensure_project_open', 'find_object_by_path']
      );
      const result = await executor.executeScript(script);
      return formatToolResponse(
        result,
        `Method '${args.methodName}' created under '${sanParentPath}' in ${args.projectFilePath}. Project saved.`
      );
    }
  );

  s.tool(
    'compile_project',
    'Compiles (Builds) the primary application within a CODESYS project.',
    {
      projectFilePath: z.string().describe("Path to the project file containing the application to compile."),
    },
    async (args: { projectFilePath: string }) => {
      const escaped = resolvePath(args.projectFilePath, workspaceDir);
      const script = scriptManager.prepareScriptWithHelpers(
        'compile_project', { PROJECT_FILE_PATH: escaped }, ['ensure_project_open']
      );
      const result = await executor.executeScript(script, 120_000); // 120s timeout for compile

      const success = result.success && result.output.includes('SCRIPT_SUCCESS');
      const hasCompileErrors =
        result.output.includes('Compile complete --') &&
        !/ 0 error\(s\),/.test(result.output);

      let message = success
        ? `Compilation initiated for ${args.projectFilePath}. Check CODESYS messages for results.`
        : `Failed initiating compilation for ${args.projectFilePath}. Output:\n${result.output}`;
      let isError = !success;

      if (success && hasCompileErrors) {
        message += ' WARNING: Build command reported errors.';
        isError = true;
      }

      return { content: [{ type: 'text' as const, text: message }], isError };
    }
  );

  // ─── Resources ───────────────────────────────────────────────────────

  server.resource(
    'project-status',
    'codesys://project/status',
    async (uri) => {
      try {
        const script = scriptManager.loadTemplate('check_status');
        const result = await executor.executeScript(script);

        const outputLines = result.output.split(/[\r\n]+/).filter((l) => l.trim());
        const statusData: Record<string, string> = {};
        outputLines.forEach((line) => {
          const match = line.match(/^([^:]+):\s*(.*)$/);
          if (match) statusData[match[1].trim()] = match[2].trim();
        });

        const statusText = [
          'CODESYS Status:',
          ` - Scripting OK: ${statusData['Scripting OK'] ?? 'Unknown'}`,
          ` - Project Open: ${statusData['Project Open'] ?? 'Unknown'}`,
          ` - Project Name: ${statusData['Project Name'] ?? 'Unknown'}`,
          ` - Project Path: ${statusData['Project Path'] ?? 'N/A'}`,
        ].join('\n');

        const isError =
          !result.success ||
          statusData['Scripting OK']?.toLowerCase() !== 'true';

        return {
          contents: [{ uri: uri.href, text: statusText, contentType: 'text/plain' }],
          isError,
        };
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        return {
          contents: [{ uri: uri.href, text: `Failed status check: ${msg}`, contentType: 'text/plain' }],
          isError: true,
        };
      }
    }
  );

  const projectStructureTemplate = new ResourceTemplate(
    'codesys://project/{+project_path}/structure',
    { list: undefined }
  );

  server.resource(
    'project-structure',
    projectStructureTemplate,
    async (uri, params) => {
      const projectPath = params.project_path as string;
      if (!projectPath) {
        return {
          contents: [{ uri: uri.href, text: 'Error: Project path missing.', contentType: 'text/plain' }],
          isError: true,
        };
      }
      try {
        const escaped = resolvePath(projectPath, workspaceDir);
        const script = scriptManager.prepareScriptWithHelpers(
          'get_project_structure', { PROJECT_FILE_PATH: escaped }, ['ensure_project_open']
        );
        const result = await executor.executeScript(script);

        let structureText = `Error retrieving structure.\n\n${result.output}`;
        let isError = !result.success;

        if (result.success && result.output.includes('SCRIPT_SUCCESS')) {
          const startMarker = '--- PROJECT STRUCTURE START ---';
          const endMarker = '--- PROJECT STRUCTURE END ---';
          const startIdx = result.output.indexOf(startMarker);
          const endIdx = result.output.indexOf(endMarker);
          if (startIdx !== -1 && endIdx !== -1 && startIdx < endIdx) {
            structureText = result.output
              .substring(startIdx + startMarker.length, endIdx)
              .replace(/\\n/g, '\n')
              .trim();
          } else {
            structureText = `Could not parse structure markers.\n\nOutput:\n${result.output}`;
            isError = true;
          }
        }

        return {
          contents: [{ uri: uri.href, text: structureText, contentType: 'text/plain' }],
          isError,
        };
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        return {
          contents: [{ uri: uri.href, text: `Failed: ${msg}`, contentType: 'text/plain' }],
          isError: true,
        };
      }
    }
  );

  const pouCodeTemplate = new ResourceTemplate(
    'codesys://project/{+project_path}/pou/{+pou_path}/code',
    { list: undefined }
  );

  server.resource(
    'pou-code',
    pouCodeTemplate,
    async (uri, params) => {
      const projectPath = params.project_path as string;
      const pouPath = params.pou_path as string;
      if (!projectPath || !pouPath) {
        return {
          contents: [{ uri: uri.href, text: 'Error: Project or POU path missing.', contentType: 'text/plain' }],
          isError: true,
        };
      }
      try {
        const escProjPath = resolvePath(projectPath, workspaceDir);
        const sanPouPath = sanitizePouPath(pouPath);
        const script = scriptManager.prepareScriptWithHelpers(
          'get_pou_code',
          { PROJECT_FILE_PATH: escProjPath, POU_FULL_PATH: sanPouPath },
          ['ensure_project_open', 'find_object_by_path']
        );
        const result = await executor.executeScript(script);

        let codeText = `Error retrieving code.\n\n${result.output}`;
        let isError = !result.success;

        if (result.success && result.output.includes('SCRIPT_SUCCESS')) {
          const declStart = '### POU DECLARATION START ###';
          const declEnd = '### POU DECLARATION END ###';
          const implStart = '### POU IMPLEMENTATION START ###';
          const implEnd = '### POU IMPLEMENTATION END ###';

          let declaration = '/* Declaration not found */';
          let implementation = '/* Implementation not found */';

          const ds = result.output.indexOf(declStart);
          const de = result.output.indexOf(declEnd);
          if (ds !== -1 && de !== -1 && ds < de) {
            declaration = result.output.substring(ds + declStart.length, de).replace(/\\n/g, '\n').trim();
          }

          const is_ = result.output.indexOf(implStart);
          const ie = result.output.indexOf(implEnd);
          if (is_ !== -1 && ie !== -1 && is_ < ie) {
            implementation = result.output.substring(is_ + implStart.length, ie).replace(/\\n/g, '\n').trim();
          }

          codeText = `// ----- Declaration -----\n${declaration}\n\n// ----- Implementation -----\n${implementation}`;
        }

        return {
          contents: [{ uri: uri.href, text: codeText, contentType: 'text/plain' }],
          isError,
        };
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        return {
          contents: [{ uri: uri.href, text: `Failed: ${msg}`, contentType: 'text/plain' }],
          isError: true,
        };
      }
    }
  );

  // ─── Connect ─────────────────────────────────────────────────────────

  const transport = new StdioServerTransport();
  serverLog.info('Connecting MCP server via stdio...');
  server.connect(transport);
  serverLog.info('MCP Server connected and listening.');

  // ─── Graceful Shutdown ───────────────────────────────────────────────

  const shutdown = async () => {
    serverLog.info('Shutdown signal received');
    if (launcher) {
      try {
        await launcher.shutdown();
      } catch {
        serverLog.warn('Launcher shutdown failed during signal handler');
      }
    }
    process.exit(0);
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
  process.on('unhandledRejection', (reason) => {
    serverLog.error(`Unhandled rejection: ${reason}`);
  });
}

import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Type, type TSchema } from "typebox";
import type {
  AgentToolResult,
  ExtensionAPI,
  ExtensionContext,
  ToolResultEvent,
} from "@earendil-works/pi-coding-agent";

type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

type SchemaType = "string" | "integer" | "number" | "boolean" | "Selector" | "point";

type ToolSpec = {
  name: string;
  label?: string;
  description?: string;
  command: string[];
  inputSchema: Record<string, `${SchemaType}${"?" | ""}`>;
  optionFlags?: Record<string, string>;
  positionals?: string[];
  mutates?: boolean;
  confirm?: boolean;
  confirmWhen?: string[];
};

type SharedTools = {
  tools: ToolSpec[];
};

type ProjectSettings = {
  u2cli?: {
    requireAgentRole?: boolean;
  };
  androidCli?: {
    requireAgentRole?: boolean;
  };
};

type Selector = {
  text?: string;
  textContains?: string;
  resourceId?: string;
  description?: string;
  descriptionContains?: string;
  className?: string;
  xpath?: string;
  index?: number;
};

type ToolInput = Record<string, unknown> & {
  serial?: string;
  timeoutMs?: number;
  selector?: Selector;
  confirmed?: boolean;
};

type CommandResult = {
  success?: boolean;
  error?: {
    code?: string;
    message?: string;
  };
  [key: string]: JsonValue | undefined;
};

type ExecutionDetails = {
  command: string[];
  exitCode: number | null;
  signal: NodeJS.Signals | null;
  stderr: string;
  stdout?: string;
  payload?: CommandResult;
  error?: string;
};

type AndroidCliToolResult = AgentToolResult<ExecutionDetails>;

const TOOL_PREFIXES = ["android_cli_", "u2cli_"] as const;
const FALLBACK_SOURCE = "git+https://github.com/Funerr/u2cli.git";
const EXEC_HINT =
  "Set ANDROID_CLI_BIN=/path/to/android-cli or U2CLI_BIN=/path/to/u2cli, install with `uv tool install git+https://github.com/Funerr/u2cli`, or make `uvx` available for the git fallback.";
const READONLY_AGENT_ROLES = new Set(["planner", "healer"]);

const selectorSchema = Type.Object(
  {
    text: Type.Optional(Type.String()),
    textContains: Type.Optional(Type.String()),
    resourceId: Type.Optional(Type.String()),
    description: Type.Optional(Type.String()),
    descriptionContains: Type.Optional(Type.String()),
    className: Type.Optional(Type.String()),
    xpath: Type.Optional(Type.String()),
    index: Type.Optional(Type.Integer()),
  },
  { additionalProperties: false },
);

const selectorFlags: Record<keyof Selector, string> = {
  text: "--text",
  textContains: "--text-contains",
  resourceId: "--resource-id",
  description: "--description",
  descriptionContains: "--description-contains",
  className: "--class-name",
  xpath: "--xpath",
  index: "--index",
};

const primitiveSchemas: Record<SchemaType, () => TSchema> = {
  string: () => Type.String(),
  integer: () => Type.Integer(),
  number: () => Type.Number(),
  boolean: () => Type.Boolean(),
  Selector: () => selectorSchema,
  point: () => Type.Tuple([Type.Integer(), Type.Integer()]),
};

const sharedToolsPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../src/u2cli/pi/tools.json",
);
const sharedTools = JSON.parse(await readFile(sharedToolsPath, "utf8")) as SharedTools;
const projectSettings = await readProjectSettings();

async function readProjectSettings(): Promise<ProjectSettings> {
  try {
    const raw = await readFile(resolve(process.cwd(), ".pi/settings.json"), "utf8");
    const settings = JSON.parse(raw) as unknown;
    return settings && typeof settings === "object" && !Array.isArray(settings)
      ? (settings as ProjectSettings)
      : {};
  } catch {
    return {};
  }
}

function schemaFromSpec(spec: ToolSpec): TSchema {
  const properties: Record<string, TSchema> = {};
  const required: string[] = [];

  for (const [name, encodedType] of Object.entries(spec.inputSchema)) {
    const optional = encodedType.endsWith("?");
    const baseType = (optional ? encodedType.slice(0, -1) : encodedType) as SchemaType;
    const schemaFactory = primitiveSchemas[baseType];
    if (!schemaFactory) {
      throw new Error(`Unsupported Android CLI Pi schema type ${encodedType} for ${spec.name}.${name}`);
    }
    properties[name] = optional ? Type.Optional(schemaFactory()) : schemaFactory();
    if (!optional) {
      required.push(name);
    }
  }

  return Type.Object(properties, { additionalProperties: false, required });
}

function flagName(field: string, spec: ToolSpec): string {
  return spec.optionFlags?.[field] ?? `--${field.replace(/[A-Z]/g, "-$&").toLowerCase()}`;
}

function pointValue(field: string, value: unknown): string {
  if (
    Array.isArray(value) &&
    value.length === 2 &&
    Number.isInteger(value[0]) &&
    Number.isInteger(value[1])
  ) {
    return `${value[0]},${value[1]}`;
  }
  throw new Error(`${field} must be a two-integer point like [x, y]`);
}

function buildArgs(spec: ToolSpec, input: ToolInput): string[] {
  const args = ["--json"];

  if (input.serial) {
    args.push("--serial", input.serial);
  }
  if (input.timeoutMs !== undefined) {
    args.push("--timeout-ms", String(input.timeoutMs));
  }

  args.push(...spec.command);

  const positionalFields = new Set(spec.positionals ?? []);
  for (const field of spec.positionals ?? []) {
    const encodedType = spec.inputSchema[field];
    const optional = encodedType?.endsWith("?") ?? false;
    const value = input[field];
    if (value === undefined) {
      if (!optional) {
        throw new Error(`Missing required Android CLI positional argument: ${field}`);
      }
      continue;
    }
    if (encodedType?.replace("?", "") === "point") {
      args.push(pointValue(field, value));
    } else {
      args.push(String(value));
    }
  }

  for (const [field, value] of Object.entries(input.selector ?? {}) as [keyof Selector, string | number][]) {
    if (value !== undefined) {
      args.push(selectorFlags[field], String(value));
    }
  }

  for (const [field, encodedType] of Object.entries(spec.inputSchema)) {
    if (
      field === "serial" ||
      field === "timeoutMs" ||
      field === "selector" ||
      field === "confirmed" ||
      positionalFields.has(field)
    ) {
      continue;
    }

    const optional = encodedType.endsWith("?");
    const baseType = optional ? encodedType.slice(0, -1) : encodedType;
    const value = input[field];

    if (value === undefined) {
      if (!optional) {
        throw new Error(`Missing required Android CLI argument: ${field}`);
      }
      continue;
    }

    const flag = flagName(field, spec);
    if (baseType === "boolean") {
      if (value === true) {
        args.push(flag);
      }
      continue;
    }
    if (baseType === "point") {
      args.push(flag, pointValue(field, value));
      continue;
    }

    args.push(flag, String(value));
  }

  return args;
}

function parseStdout(stdout: string): CommandResult {
  const trimmed = stdout.trim();
  if (!trimmed) {
    throw new Error("Android CLI did not write a JSON object to stdout");
  }

  const payload = JSON.parse(trimmed) as unknown;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Android CLI stdout was not a single JSON object");
  }
  return payload as CommandResult;
}

type CommandCandidate = {
  file: string;
  argsPrefix: string[];
  fallbackOnMissing: boolean;
};

function commandCandidates(): CommandCandidate[] {
  if (process.env.ANDROID_CLI_BIN) {
    return [{ file: process.env.ANDROID_CLI_BIN, argsPrefix: [], fallbackOnMissing: false }];
  }
  if (process.env.U2CLI_BIN) {
    return [{ file: process.env.U2CLI_BIN, argsPrefix: [], fallbackOnMissing: false }];
  }
  return [
    { file: "android-cli", argsPrefix: [], fallbackOnMissing: true },
    { file: "u2cli", argsPrefix: [], fallbackOnMissing: true },
    { file: "uvx", argsPrefix: ["--from", FALLBACK_SOURCE, "android-cli"], fallbackOnMissing: true },
    { file: "uvx", argsPrefix: ["--from", FALLBACK_SOURCE, "u2cli"], fallbackOnMissing: false },
  ];
}

function errorPayload(code: string, message: string): CommandResult {
  return {
    success: false,
    error: { code, message },
  };
}

function formatResult(payload: CommandResult): string {
  return JSON.stringify(payload, null, 2);
}

function runCandidate(candidate: CommandCandidate, args: string[]): Promise<{
  missing: boolean;
  text: string;
  details: ExecutionDetails;
  isError: boolean;
}> {
  const commandArgs = [...candidate.argsPrefix, ...args];

  return new Promise((resolvePromise) => {
    execFile(
      candidate.file,
      commandArgs,
      { encoding: "utf8", maxBuffer: 20 * 1024 * 1024 },
      (error, stdout, stderr) => {
        if ((error as NodeJS.ErrnoException | null)?.code === "ENOENT") {
          resolvePromise({
            missing: true,
            text: "",
            details: {
              command: [candidate.file, ...commandArgs],
              exitCode: null,
              signal: null,
              stderr,
              error: `${candidate.file} was not found`,
            },
            isError: true,
          });
          return;
        }

        const exitCode =
          error && typeof (error as { code?: unknown }).code === "number"
            ? (error as { code: number }).code
            : 0;
        const signal = ((error as { signal?: NodeJS.Signals | null } | null)?.signal ??
          null) as NodeJS.Signals | null;
        const command = [candidate.file, ...commandArgs];

        try {
          const payload = parseStdout(stdout);
          const isError = exitCode !== 0 || payload.success === false;
          resolvePromise({
            missing: false,
            text: formatResult(payload),
            details: { command, exitCode, signal, stderr, payload },
            isError,
          });
        } catch (parseError) {
          const message = parseError instanceof Error ? parseError.message : String(parseError);
          const payload = errorPayload("ANDROID_CLI_NON_JSON_OUTPUT", message);
          resolvePromise({
            missing: false,
            text: formatResult(payload),
            details: {
              command,
              exitCode,
              signal,
              stderr,
              stdout,
              payload,
              error: message,
            },
            isError: true,
          });
        }
      },
    );
  });
}

async function runAndroidCli(args: string[]): Promise<{
  text: string;
  details: ExecutionDetails;
  isError: boolean;
}> {
  let lastMissing: ExecutionDetails | undefined;

  for (const candidate of commandCandidates()) {
    const result = await runCandidate(candidate, args);
    if (result.missing && candidate.fallbackOnMissing) {
      lastMissing = result.details;
      continue;
    }
    if (result.missing) {
      const payload = errorPayload("ANDROID_CLI_NOT_FOUND", `${candidate.file} was not found. ${EXEC_HINT}`);
      return {
        text: formatResult(payload),
        details: { ...result.details, payload },
        isError: true,
      };
    }
    return result;
  }

  const payload = errorPayload("ANDROID_CLI_NOT_FOUND", `Android CLI was not found. ${EXEC_HINT}`);
  return {
    text: formatResult(payload),
    details: lastMissing
      ? { ...lastMissing, payload }
      : { command: ["android-cli", ...args], exitCode: null, signal: null, stderr: "", payload },
    isError: true,
  };
}

async function maybeConfirm(
  spec: ToolSpec,
  input: ToolInput,
  ctx: ExtensionContext,
  toolName: string,
): Promise<void> {
  const needsConfirmation =
    spec.confirm === true ||
    spec.confirmWhen?.some((field) => input[field] !== undefined && input[field] !== null);

  if (!needsConfirmation) {
    return;
  }

  if (input.confirmed === true) {
    return;
  }

  if (!ctx.hasUI) {
    throw new Error(
      `${toolName} changes Android device state. Pass confirmed: true in headless mode.`,
    );
  }

  const accepted = await ctx.ui.confirm(
    toolName,
    `This tool will change Android device state.\n\n${JSON.stringify(input, null, 2)}`,
  );
  if (!accepted) {
    throw new Error(`${toolName} cancelled by user`);
  }
}

function registerTool(pi: ExtensionAPI, failedToolCalls: Set<string>, spec: ToolSpec, prefix: string): void {
  const toolName = `${prefix}${spec.name}`;

  pi.registerTool({
    name: toolName,
    label: spec.label ?? toolName,
    description: spec.description ?? spec.label ?? spec.name,
    parameters: schemaFromSpec(spec),
    async execute(
      toolCallId: string,
      input: ToolInput,
      _signal: AbortSignal | undefined,
      _onUpdate: unknown,
      ctx: ExtensionContext,
    ): Promise<AndroidCliToolResult> {
      await maybeConfirm(spec, input, ctx, toolName);

      const args = buildArgs(spec, input);
      const result = await runAndroidCli(args);
      const toolResult: AndroidCliToolResult = {
        content: [{ type: "text", text: result.text }],
        details: result.details,
      };

      if (result.isError) {
        failedToolCalls.add(toolCallId);
      }

      return toolResult;
    },
  });
}

function currentAgentRole(): string | undefined {
  const role = process.env.PI_AGENT_ROLE?.trim().toLowerCase();
  return role || undefined;
}

function envFlag(name: string): boolean {
  const value = process.env[name]?.trim().toLowerCase();
  return value === "1" || value === "true" || value === "yes";
}

function requireAgentRole(): boolean {
  return (
    envFlag("ANDROID_CLI_PI_REQUIRE_AGENT_ROLE") ||
    envFlag("U2CLI_PI_REQUIRE_AGENT_ROLE") ||
    projectSettings.androidCli?.requireAgentRole === true ||
    projectSettings.u2cli?.requireAgentRole === true
  );
}

function isMutatingTool(spec: ToolSpec): boolean {
  return spec.mutates === true || spec.confirm === true || Boolean(spec.confirmWhen?.length);
}

function canRegisterForRole(spec: ToolSpec, role: string | undefined): boolean {
  if (!role) return !requireAgentRole();
  if (role === "executor") return true;
  if (READONLY_AGENT_ROLES.has(role)) return !isMutatingTool(spec);
  return false;
}

export default function u2cliExtension(pi: ExtensionAPI): void {
  const failedToolCalls = new Set<string>();
  const role = currentAgentRole();

  pi.on("tool_result", (event: ToolResultEvent) => {
    if (failedToolCalls.delete(event.toolCallId)) {
      return { isError: true };
    }
  });

  for (const spec of sharedTools.tools) {
    if (!canRegisterForRole(spec, role)) continue;
    for (const prefix of TOOL_PREFIXES) {
      registerTool(pi, failedToolCalls, spec, prefix);
    }
  }
}

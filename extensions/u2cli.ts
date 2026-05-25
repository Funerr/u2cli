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

type ToolSpec = {
  name: string;
  label?: string;
  description?: string;
  command: string[];
  inputSchema: Record<string, string>;
  optionFlags?: Record<string, string>;
  confirm?: boolean;
};

type SharedTools = {
  tools: ToolSpec[];
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

type ToolArgs = {
  serial?: string;
  timeoutMs?: number;
  selector?: Selector;
  text?: string;
  out?: string;
  x?: number;
  y?: number;
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
  payload?: CommandResult;
  u2cliFailed: boolean;
};

type U2CliToolResult = AgentToolResult<ExecutionDetails>;

const TOOL_PREFIX = "u2cli_";
const INSTALL_HINT =
  "u2cli binary not found. Install it with `uv tool install git+https://github.com/Funerr/u2cli` or set `U2CLI_BIN=/path/to/u2cli`.";

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

const primitiveSchemas = {
  string: () => Type.String(),
  integer: () => Type.Integer(),
  Selector: () => selectorSchema,
} as const;

const sharedToolsPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../src/u2cli/pi/tools.json",
);
const sharedTools = JSON.parse(await readFile(sharedToolsPath, "utf8")) as SharedTools;

function schemaFromSpec(spec: ToolSpec) {
  const properties: Record<string, TSchema> = {};
  const required: string[] = [];

  for (const [name, encodedType] of Object.entries(spec.inputSchema)) {
    const optional = encodedType.endsWith("?");
    const baseType = optional ? encodedType.slice(0, -1) : encodedType;
    const schemaFactory = primitiveSchemas[baseType as keyof typeof primitiveSchemas];
    if (!schemaFactory) {
      throw new Error(`Unsupported u2cli Pi schema type ${encodedType} for ${spec.name}.${name}`);
    }
    properties[name] = optional ? Type.Optional(schemaFactory()) : schemaFactory();
    if (!optional) {
      required.push(name);
    }
  }

  return Type.Object(properties, { additionalProperties: false, required });
}

function buildArgs(spec: ToolSpec, input: ToolArgs): string[] {
  const args = [...spec.command];
  if (args[0] === "u2cli") {
    args.shift();
  }

  if (input.serial) {
    args.push("--serial", input.serial);
  }
  if (input.timeoutMs !== undefined) {
    args.push("--timeout-ms", String(input.timeoutMs));
  }

  for (const [field, value] of Object.entries(input.selector ?? {}) as [keyof Selector, string | number][]) {
    if (value !== undefined) {
      args.push(selectorFlags[field], String(value));
    }
  }

  for (const [field, encodedType] of Object.entries(spec.inputSchema)) {
    if (field === "serial" || field === "timeoutMs" || field === "selector") {
      continue;
    }
    const value = input[field as keyof ToolArgs];
    if (value !== undefined) {
      const flag = spec.optionFlags?.[field] ?? `--${field.replace(/[A-Z]/g, "-$&").toLowerCase()}`;
      args.push(flag, String(value));
    } else if (!encodedType.endsWith("?")) {
      throw new Error(`Missing required u2cli argument: ${field}`);
    }
  }

  return args;
}

function parseStdout(stdout: string): CommandResult {
  const trimmed = stdout.trim();
  if (!trimmed) {
    throw new Error("u2cli did not write a JSON object to stdout");
  }

  const payload = JSON.parse(trimmed) as unknown;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("u2cli stdout was not a single JSON object");
  }
  return payload as CommandResult;
}

async function runU2Cli(args: string[]): Promise<{ text: string; details: ExecutionDetails }> {
  const bin = process.env.U2CLI_BIN || "u2cli";

  return await new Promise((resolvePromise, rejectPromise) => {
    execFile(
      bin,
      args,
      { encoding: "utf8", maxBuffer: 20 * 1024 * 1024 },
      (error, stdout, stderr) => {
        let exitCode: number | null = 0;
        let signal: NodeJS.Signals | null = null;

        if (error) {
          if ((error as NodeJS.ErrnoException).code === "ENOENT") {
            rejectPromise(new Error(INSTALL_HINT));
            return;
          }

          exitCode =
            typeof (error as { code?: unknown }).code === "number"
              ? ((error as { code: number }).code)
              : null;
          signal = ((error as { signal?: NodeJS.Signals | null }).signal ?? null) as NodeJS.Signals | null;
        }

        let payload: CommandResult;
        try {
          payload = parseStdout(stdout);
        } catch (parseError) {
          const details: ExecutionDetails = {
            command: [bin, ...args],
            exitCode,
            signal,
            stderr,
            u2cliFailed: true,
          };
          rejectPromise(
            Object.assign(parseError instanceof Error ? parseError : new Error(String(parseError)), {
              details,
            }),
          );
          return;
        }

        const text = JSON.stringify(payload, null, 2);
        const details: ExecutionDetails = {
          command: [bin, ...args],
          exitCode,
          signal,
          stderr,
          payload,
          u2cliFailed: payload.success === false,
        };

        resolvePromise({ text, details });
      },
    );
  });
}

async function maybeConfirm(spec: ToolSpec, input: ToolArgs, ctx: ExtensionContext): Promise<void> {
  if (!spec.confirm) {
    return;
  }

  if (!ctx.hasUI) {
    return;
  }

  const accepted = await ctx.ui.confirm(
    `${TOOL_PREFIX}${spec.name}`,
    `This tool will change Android device state.\n\n${JSON.stringify(input, null, 2)}`,
  );
  if (!accepted) {
    throw new Error(`${TOOL_PREFIX}${spec.name} cancelled by user`);
  }
}

export default function u2cliExtension(pi: ExtensionAPI): void {
  const failedToolCalls = new Set<string>();

  pi.on("tool_result", (event: ToolResultEvent) => {
    if (failedToolCalls.delete(event.toolCallId)) {
      return { isError: true };
    }
  });

  for (const spec of sharedTools.tools) {
    pi.registerTool({
      name: `${TOOL_PREFIX}${spec.name}`,
      label: spec.label ?? `${TOOL_PREFIX}${spec.name}`,
      description: spec.description ?? spec.label ?? spec.name,
      parameters: schemaFromSpec(spec),
      async execute(
        toolCallId: string,
        input: ToolArgs,
        _signal: AbortSignal | undefined,
        _onUpdate: unknown,
        ctx: ExtensionContext,
      ): Promise<U2CliToolResult> {
        await maybeConfirm(spec, input, ctx);

        const args = buildArgs(spec, input);
        const result = await runU2Cli(args);
        const toolResult: U2CliToolResult = {
          content: [{ type: "text", text: result.text }],
          details: result.details,
        };

        if (result.details.payload?.success === false) {
          failedToolCalls.add(toolCallId);
        }

        return toolResult;
      },
    });
  }
}

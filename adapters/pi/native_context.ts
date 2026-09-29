/** Pi 0.87.1 process-local context probe and new-session bridge. No model call. */
import { link, lstat, open, unlink } from "node:fs/promises";
import { join } from "node:path";

type Context = {
  cwd: string;
  model: { provider: string; id: string } | null;
  thinking: string;
  trusted: boolean;
  tools: string[] | null;
  session_id: string;
  session_file: string | null;
};

const noncePattern = /^[a-f0-9]{32}$/;

export default function (pi: any) {
  function capture(ctx: any, includeTools = true): Context {
    return {
      cwd: ctx.cwd,
      model: ctx.model ? { provider: ctx.model.provider, id: ctx.model.id } : null,
      thinking: includeTools ? pi.getThinkingLevel() : (ctx.thinkingLevel ?? "unknown"),
      trusted: ctx.isProjectTrusted(),
      tools: includeTools ? [...pi.getActiveTools()].sort() : null,
      session_id: ctx.sessionManager.getSessionId(),
      session_file: ctx.sessionManager.getSessionFile() ?? null,
    };
  }

  async function writeProof(nonce: string, proof: object): Promise<void> {
    const root = process.env.HERDR_ORCH_BRIDGE_DIR;
    if (!root || !root.startsWith("/") || !noncePattern.test(nonce)) {
      throw new Error("bridge directory or nonce unavailable");
    }
    const info = await lstat(root);
    if (!info.isDirectory() || info.uid !== process.getuid?.() || (info.mode & 0o077) !== 0) {
      throw new Error("bridge directory must be owner-only");
    }
    const target = join(root, `${nonce}.json`);
    const temp = join(root, `.${nonce}.${process.pid}.tmp`);
    const handle = await open(temp, "wx", 0o600);
    try {
      await handle.writeFile(JSON.stringify({ nonce, ...proof }) + "\n", "utf8");
      await handle.sync();
    } finally {
      await handle.close();
    }
    try {
      await link(temp, target);
    } finally {
      await unlink(temp);
    }
  }

  pi.registerCommand("herdrinspect", {
    description: "Record native Pi context for a scoped Herdr run",
    handler: async (args: string, ctx: any) => {
      const nonce = args.trim();
      if (process.env.HERDR_ENV !== "1" || !noncePattern.test(nonce)) return;
      try {
        await writeProof(nonce, { operation: "inspect", current: capture(ctx) });
      } catch (error) {
        ctx.ui.notify(`Herdr context inspection failed: ${String(error)}`, "error");
      }
    },
  });

  pi.registerCommand("herdrnew", {
    description: "Start a fresh native Pi session in this same pane",
    handler: async (args: string, ctx: any) => {
      const nonce = args.trim();
      if (process.env.HERDR_ENV !== "1" || !noncePattern.test(nonce) || !ctx.isIdle()) return;
      const before = capture(ctx);
      try {
        const result = await ctx.newSession({ withSession: async (freshCtx: any) => {
          await writeProof(nonce, { operation: "new", before,
                                    after: capture(freshCtx, false), cancelled: false, error: null });
        }});
        if (result.cancelled) {
          await writeProof(nonce, { operation: "new", before, after: before,
                                    cancelled: true, error: null });
        }
      } catch (cause) {
        try {
          await writeProof(nonce, { operation: "new", before, after: null,
                                    cancelled: true, error: String(cause).slice(0, 200) });
        } catch { /* A missing proof is an explicit timeout to the caller. */ }
      }
    },
  });
}

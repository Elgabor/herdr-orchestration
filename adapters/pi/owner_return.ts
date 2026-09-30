/** Process-local Pi owner bridge. A deterministic child waits; Pi stays interactive. */
import { randomBytes } from "node:crypto";
import { spawn } from "node:child_process";
import { link, lstat, open, unlink } from "node:fs/promises";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const helper = resolve(dirname(fileURLToPath(import.meta.url)), "../../scripts/herdr_orchestrate.py");
const idPattern = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$/;
const shellQuote = (value: string) => `'${value.replaceAll("'", "'\\''")}'`;

async function writeArm(root: string, nonce: string, body: object): Promise<void> {
  const info = await lstat(root);
  if (!info.isDirectory() || info.uid !== process.getuid?.() || (info.mode & 0o077) !== 0) {
    throw new Error("owner bridge directory must be owner-only");
  }
  const temp = join(root, `.${nonce}.${process.pid}.tmp`);
  const target = join(root, `${nonce}.json`);
  const handle = await open(temp, "wx", 0o600);
  try {
    await handle.writeFile(JSON.stringify({ nonce, operation: "owner_arm", ...body }) + "\n", "utf8");
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

export default function (pi: any) {
  let activeSessionFile: string | null = null;
  const inFlight = new Set<string>();
  pi.on("session_start", (_event: any, ctx: any) => {
    activeSessionFile = ctx.sessionManager.getSessionFile() ?? null;
  });
  pi.on("session_before_switch", () => { activeSessionFile = null; });

  pi.registerCommand("herdrdispatch", {
    description: "Dispatch one scoped Herdr assignment and return to this Pi session",
    handler: async (args: string, ctx: any) => {
      if (process.env.HERDR_ENV !== "1" || !ctx.isIdle()) {
        ctx.ui.notify("Herdr owner is not idle in a Herdr pane", "error");
        return;
      }
      const parts = args.trim().split(/\s+/);
      if (parts.length !== 6) {
        ctx.ui.notify("Expected run_id assignment_id config_path state_dir generation epoch", "error");
        return;
      }
      const [runId, assignmentId, encodedConfig, encodedState, generation, epoch] = parts;
      let configPath: string;
      let stateDir: string;
      try {
        configPath = decodeURIComponent(encodedConfig);
        stateDir = decodeURIComponent(encodedState);
      } catch {
        ctx.ui.notify("Invalid encoded path", "error");
        return;
      }
      const bridgeDir = process.env.HERDR_ORCH_BRIDGE_DIR;
      const ownerSessionFile = ctx.sessionManager.getSessionFile();
      if (!idPattern.test(runId) || !idPattern.test(assignmentId) ||
          !isAbsolute(configPath) || !isAbsolute(stateDir) || !bridgeDir ||
          !ownerSessionFile || !/^\d+$/.test(generation) || !/^\d+$/.test(epoch)) {
        ctx.ui.notify("Herdr dispatch binding incomplete", "error");
        return;
      }
      const identity = `${runId}/${assignmentId}`;
      if (inFlight.has(identity)) {
        ctx.ui.notify("Assignment already has a local listener", "error");
        return;
      }
      const nonce = randomBytes(16).toString("hex");
      try {
        await writeArm(bridgeDir, nonce, {
          run_id: runId, assignment_id: assignmentId,
          owner_session_file: ownerSessionFile,
          owner_pane_id: process.env.HERDR_PANE_ID ?? null,
          owner_process_pid: process.pid,
          owner_epoch: Number(epoch), generation: Number(generation),
        });
      } catch (error) {
        ctx.ui.notify(`Herdr owner arm failed: ${String(error)}`, "error");
        return;
      }
      inFlight.add(identity);
      activeSessionFile = ownerSessionFile;
      const child = spawn("python3", [helper, "assignment", "dispatch",
        "--config", configPath, "--expected-generation", generation,
        "--owner-epoch", epoch, "--state-dir", stateDir,
        "--bridge-dir", bridgeDir, "--bridge-nonce", nonce],
      { stdio: ["ignore", "pipe", "pipe"] });
      let stdout = "";
      let closed = false;
      child.stdout.on("data", (chunk: Buffer) => { stdout = (stdout + chunk.toString()).slice(-4096); });
      child.stderr.on("data", () => { /* No raw stderr is forwarded into the owner model. */ });
      const deliver = (outcome: string, eventId: string | null) => {
        if (closed) return;
        closed = true;
        inFlight.delete(identity);
        if (activeSessionFile !== ownerSessionFile) return;
        const event = eventId ?? "none";
        const command = eventId
          ? `python3 ${shellQuote(helper)} assignment collect --run-id ${runId} --assignment-id ${assignmentId} ` +
            `--event-id ${eventId} --owner-epoch ${epoch} --state-dir ${shellQuote(stateDir)}`
          : `python3 ${shellQuote(helper)} assignment pending --run-id ${runId} ` +
            `--owner-epoch ${epoch} --state-dir ${shellQuote(stateDir)}`;
        pi.sendUserMessage(`Herdr assignment ${assignmentId} in run ${runId} returned ${outcome}; event ${event}. ` +
          `To collect the recorded event, run exactly: ${command}. ` +
          "Inspect its outcome before deciding next work. Do not redispatch this assignment.",
          { deliverAs: "followUp" });
      };
      child.on("error", () => deliver("listener_error", null));
      child.on("close", (code: number) => {
        let outcome = code === 0 ? "returned" : "listener_error";
        let eventId: string | null = null;
        try {
          const envelope = JSON.parse(stdout.trim());
          if (envelope.run_id === runId && envelope.assignment_id === assignmentId) {
            outcome = envelope.outcome;
            eventId = typeof envelope.event_id === "string" ? envelope.event_id : null;
          }
        } catch { /* A malformed CLI envelope is an error, never success. */ }
        deliver(outcome, eventId);
      });
      ctx.ui.notify(`Assignment ${assignmentId} dispatched; owner input remains available`, "info");
    },
  });
}

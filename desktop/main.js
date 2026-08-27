const { app, BrowserWindow } = require("electron");
const { spawn, exec } = require("child_process");
const path = require("path");

const BACKEND_DIR = path.join(__dirname, "..", "backend");
const FRONTEND_DIR = path.join(__dirname, "..", "frontend");
const BACKEND_PYTHON = path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe");
const BACKEND_HEALTH_URL = "http://localhost:8000/health";
const FRONTEND_URL = "http://localhost:3000";
const READY_TIMEOUT_MS = 30000;
const POLL_INTERVAL_MS = 500;
const MAX_LOG_LINES = 50;

let backendProcess = null;
let frontendProcess = null;
let mainWindow = null;
const recentBackendOutput = [];
const recentFrontendOutput = [];

function dataUrl(bodyHtml) {
  return `data:text/html,${encodeURIComponent(bodyHtml)}`;
}

const STARTING_PAGE = dataUrl(`
  <html><body style="font-family: system-ui, sans-serif; display: flex; align-items: center;
    justify-content: center; height: 100vh; margin: 0; background: #0a0a0a; color: #fafafa;">
    <p>Starting Agent Ops Dashboard...</p>
  </body></html>
`);

function trackOutput(buffer, data) {
  buffer.push(data.toString());
  if (buffer.length > MAX_LOG_LINES) buffer.shift();
}

function spawnBackend() {
  // A direct path to the venv's python.exe -- no shell needed, and no PATH/.cmd-shim resolution
  // concerns the way a bare "python" or "npm" would have (the exact PATHEXT gotcha already found
  // and fixed elsewhere in this series). No --reload: this session found its Windows process
  // handling to be unreliable (a stuck worker left the backend serving stale code after an edit).
  backendProcess = spawn(
    BACKEND_PYTHON,
    ["-m", "uvicorn", "app.main:app", "--port", "8000"],
    { cwd: BACKEND_DIR, env: process.env },
  );
  backendProcess.stdout.on("data", (d) => {
    console.log(`[backend] ${d}`);
    trackOutput(recentBackendOutput, d);
  });
  backendProcess.stderr.on("data", (d) => {
    console.error(`[backend] ${d}`);
    trackOutput(recentBackendOutput, d);
  });
}

function spawnFrontend() {
  // Spawn Next's CLI script directly through Electron's own bundled Node (process.execPath),
  // with ELECTRON_RUN_AS_NODE forcing that one child invocation to behave as plain node -- NOT
  // "npm run dev" with shell: true, which was tried first and found to orphan the real frontend
  // process tree on shutdown: shell: true wraps the command in a cmd.exe that hands off to
  // npm.cmd and exits early once "next dev" is actually running, so by the time shutdown() calls
  // `taskkill /T` on the recorded pid, that pid (the cmd.exe wrapper) is already gone and the
  // tree-walk has nothing left to find -- confirmed live: after a graceful Electron quit, four
  // node.exe processes (npm's wrapper, next's CLI, its start-server, a turbopack worker) were
  // still running. Spawning next's script directly makes frontendProcess.pid the actual
  // long-lived process, so its own descendants (start-server, turbopack workers) nest correctly
  // underneath it and /T can walk down to all of them.
  const nextBin = path.join(FRONTEND_DIR, "node_modules", "next", "dist", "bin", "next");
  frontendProcess = spawn(process.execPath, [nextBin, "dev"], {
    cwd: FRONTEND_DIR,
    env: { ...process.env, ELECTRON_RUN_AS_NODE: "1" },
  });
  frontendProcess.stdout.on("data", (d) => {
    console.log(`[frontend] ${d}`);
    trackOutput(recentFrontendOutput, d);
  });
  frontendProcess.stderr.on("data", (d) => {
    console.error(`[frontend] ${d}`);
    trackOutput(recentFrontendOutput, d);
  });
}

async function waitForUrl(url, timeoutMs) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return true;
    } catch {
      // Not up yet -- keep polling until the timeout.
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
  return false;
}

function killProcessTree(proc) {
  if (!proc || proc.exitCode !== null) return;
  if (process.platform === "win32") {
    // proc.kill() alone only signals the immediate process -- uvicorn/npm/next can themselves
    // spawn further children that would otherwise survive as orphans (the exact class of problem
    // already hit once this session with a stuck --reload worker). /T kills the whole tree.
    exec(`taskkill /pid ${proc.pid} /T /F`);
  } else {
    proc.kill("SIGTERM");
  }
}

function showStartupError(backendReady, frontendReady) {
  const page = dataUrl(`
    <html><body style="font-family: ui-monospace, monospace; padding: 24px; background: #0a0a0a;
      color: #fafafa; white-space: pre-wrap;">
      <h2>Agent Ops Dashboard failed to start</h2>
      <p>Backend ready: ${backendReady} &nbsp; Frontend ready: ${frontendReady}</p>
      <h3>Recent backend output</h3>
      <pre>${recentBackendOutput.join("").slice(-3000)}</pre>
      <h3>Recent frontend output</h3>
      <pre>${recentFrontendOutput.join("").slice(-3000)}</pre>
    </body></html>
  `);
  mainWindow.loadURL(page);
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
    },
  });
  mainWindow.loadURL(STARTING_PAGE);

  spawnBackend();
  spawnFrontend();

  const [backendReady, frontendReady] = await Promise.all([
    waitForUrl(BACKEND_HEALTH_URL, READY_TIMEOUT_MS),
    waitForUrl(FRONTEND_URL, READY_TIMEOUT_MS),
  ]);

  if (!backendReady || !frontendReady) {
    showStartupError(backendReady, frontendReady);
    return;
  }

  mainWindow.loadURL(FRONTEND_URL);
}

function shutdown() {
  killProcessTree(backendProcess);
  killProcessTree(frontendProcess);
}

app.whenReady().then(createWindow);
app.on("before-quit", shutdown);
app.on("window-all-closed", () => {
  shutdown();
  if (process.platform !== "darwin") app.quit();
});

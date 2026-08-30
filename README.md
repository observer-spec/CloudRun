# CloudRun

A deliberately small, temporary cloud workspace for an AI coding agent.

A manually dispatched GitHub Actions job:

1. clones a selected public repository into an Ubuntu runner;
2. starts an authenticated MCP HTTP server;
3. exposes it through a temporary Cloudflare Tunnel; and
4. expires automatically after the requested number of minutes.

## Setup

Create an Actions repository secret named `MCP_TOKEN` with a long random value. Never put this token in workflow inputs or source files.

Run **Actions → One-shot Cloud MCP runner → Run workflow**. Choose the repository/ref and lifetime. The workflow automatically updates [`CURRENT_ENDPOINT.md`](CURRENT_ENDPOINT.md) with the latest temporary `/mcp` URL. The Bearer token remains only in the `MCP_TOKEN` secret.

Tools are intentionally limited to:

- `exec`: argv-only commands, no shell, workspace-contained cwd
- `read_file`: workspace-contained file reads
- `write_file`: workspace-contained file writes

The runner is not a general production shell. It is for short-lived coding sessions. Cancel the workflow when finished. Cloudflare quick-tunnel URLs are public, so use a strong token and do not commit the URL or token.

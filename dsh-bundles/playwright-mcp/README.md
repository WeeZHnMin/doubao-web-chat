# Playwright MCP

Configuration-only DSH bundle that connects the [Playwright MCP](https://github.com/microsoft/playwright-mcp) server through `@deepseek-ai/dsh-mcp-client`.

## What it does

Starts `npx -y @playwright/mcp@latest` over stdio and registers its browser tools as `mcp__playwright__*` (for example `mcp__playwright__browser_navigate`).

## Configuration

| Field | Value |
|---|---|
| `serverName` | `playwright` |
| `transport` | `stdio` |
| `command` | `npx` |
| `args` | `-y @playwright/mcp@latest` |

The server runs with default Playwright MCP settings (headless, isolated browser context). Edit `cordis.patch.yml` to change the browser, add `--headless`, or pass extra arguments.

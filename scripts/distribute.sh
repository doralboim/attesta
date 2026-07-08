#!/usr/bin/env bash
# Attesta distribution — run after production deploy is live.
set -euo pipefail

BASE_URL="${ATTESTA_BASE_URL:-https://api.attesta.dev}"
MCP_URL="${BASE_URL}/mcp"
SERVER_NAME="${ATTESTA_SERVER_NAME:-@doralboim/attesta}"
GITHUB_USER="${GITHUB_USER:-doralboim}"

echo "=== Attesta Distribution ==="
echo "Base URL: ${BASE_URL}"
echo "MCP URL:  ${MCP_URL}"
echo

echo "1. Health check"
curl -sf "${BASE_URL}/healthz" | python3 -m json.tool
echo

echo "2. MCP server card"
curl -sf "${BASE_URL}/.well-known/mcp/server-card.json" | python3 -m json.tool | head -20
echo

echo "3. llms.txt"
curl -sf "${BASE_URL}/llms.txt" | head -15
echo

cat <<EOF

=== Manual publish steps ===

A) MCP Official Registry (Anthropic ecosystem)
   1. Install: go install github.com/modelcontextprotocol/registry/cmd/mcp-publisher@latest
   2. Edit distribution/server.json — set remotes[0].url to ${MCP_URL}
   3. cd distribution && mcp-publisher login github
   4. mcp-publisher publish

B) Smithery (https://smithery.ai/new)
   URL: ${MCP_URL}
   Config schema: distribution/smithery-config.json
   CLI: npx @smithery/cli mcp publish "${MCP_URL}" -n ${SERVER_NAME}

C) Claude Desktop / Cursor
   Copy distribution/claude-desktop.json or distribution/cursor-mcp.json
   Replace YOUR_ATTESTA_API_KEY with your demo key.

D) Composio (partner outreach — no public custom-MCP listing yet)
   Email: partners@composio.dev
   Pitch: Attesta MCP at ${MCP_URL} — Portugal property data + JWS verification
   Template: distribution/composio-outreach.md

E) Demo for prospects
   python scripts/demo.py --base-url ${BASE_URL} --api-key YOUR_DEMO_KEY

EOF

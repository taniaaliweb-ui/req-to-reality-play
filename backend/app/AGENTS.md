## Backend app rules (MCP, research acceptance)
- The MCP server (`app/mcp_server.py`, stdio, no dependencies) exposes only service-backed tools; no snapshot-edit, self-verify or SQL tool.
- Research acceptance goes through `services/research_acceptance.py` (reviewer-chosen FACT/ESTIMATE/CONTEXT/ASSUMPTION/REJECT with validated scope); it never touches finalized snapshots and only raises replacement notices — new evidence reaches simulations only via a new snapshot version + rerun.
- MCP tools carry a risk class and group (`mcp_server.TOOL_META`); PROHIBITED tools are never executable, CONSEQUENTIAL_WRITE calls go through user approval by default (`mcp_approvals`) — agents get the minimum tool set.

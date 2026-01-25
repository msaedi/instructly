# scripts/setup-mcp.sh
#!/bin/bash
cd mcp-server
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
echo "MCP server ready. Run: cd mcp-server && source venv/bin/activate"

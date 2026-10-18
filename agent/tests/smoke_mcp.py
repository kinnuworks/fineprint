"""Start the stdio MCP server, list its tools and call check_model once.

    python tests/smoke_mcp.py [MODEL_ID]
"""
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def attr(obj, snake, camel):
    """mcp 2.x uses snake_case attributes, 1.x camelCase."""
    return getattr(obj, snake, None) if hasattr(obj, snake) else getattr(obj, camel)


async def main(model_id: str) -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "fineprint.mcp_server"])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            print(f"server: {attr(init, "server_info", "serverInfo").name}")
            for t in (await s.list_tools()).tools:
                print(f"- {t.name}({', '.join(attr(t, 'input_schema', 'inputSchema').get('properties', {}))}): {t.description.splitlines()[0]}")
            res = await s.call_tool("check_model", {"model_id": model_id})
            print()
            print(("ERROR: " if attr(res, "is_error", "isError") else "") + res.content[0].text)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "QCRI/Fanar-2-27B-Instruct"))

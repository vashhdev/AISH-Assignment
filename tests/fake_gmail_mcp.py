"""Stand-in Gmail MCP server for tests: same send_email shape as the real server, no network.

Replies like the real server (GongRzhe 1.1.11): success text "Email sent successfully with ID: ...",
errors as plain "Error: ..." text without the MCP isError flag.

Env vars (set by the test through StdioServerParameters.env):
  FAKE_GMAIL_CALLS    file to append one JSON line per send_email call
  FAKE_GMAIL_FAIL_ON  subject substring that makes the call fail
"""
import json
import os

from mcp.server.mcpserver import MCPServer

server = MCPServer("fake-gmail")


@server.tool()
def send_email(to: list[str], subject: str, body: str, inReplyTo: str | None = None) -> str:
    calls = os.environ.get("FAKE_GMAIL_CALLS")
    if calls:
        with open(calls, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"to": to, "subject": subject, "body": body, "inReplyTo": inReplyTo}) + "\n")
    fail_on = os.environ.get("FAKE_GMAIL_FAIL_ON")
    if fail_on and fail_on in subject:
        return "Error: simulated Gmail failure"
    return "Email sent successfully with ID: fake-0001"


if __name__ == "__main__":
    server.run("stdio")

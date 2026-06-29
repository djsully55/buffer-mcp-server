#!/usr/bin/env python3
"""Buffer MCP Server v3 — low-level MCP SDK, Starlette SSE, no host validation"""
import asyncio
import json
import os
import requests
import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route, Mount

server = Server("Buffer")
GQL_URL = "https://api.buffer.com/graphql"

def _headers():
    return {"Authorization": f"Bearer {os.environ['BUFFER_ACCESS_TOKEN']}", "Content-Type": "application/json"}

def _gql(query: str, variables: dict = None) -> dict:
    resp = requests.post(GQL_URL, headers=_headers(), json={"query": query, "variables": variables or {}}, timeout=30)
    resp.raise_for_status()
    return resp.json()

@server.list_tools()
async def list_tools():
    return [
        Tool(name="get_channels", description="Get all connected Buffer channels. Always call this first to get channel_id values.", inputSchema={"type": "object", "properties": {}}),
        Tool(name="create_post", description="Create and publish a post to a Buffer channel.", inputSchema={"type": "object", "properties": {"channel_id": {"type": "string"}, "text": {"type": "string"}, "image_urls": {"type": "array", "items": {"type": "string"}}, "platform": {"type": "string", "default": "instagram"}, "mode": {"type": "string", "default": "shareNow"}}, "required": ["channel_id", "text"]}),
        Tool(name="get_post_status", description="Get the current status of a Buffer post.", inputSchema={"type": "object", "properties": {"post_id": {"type": "string"}}, "required": ["post_id"]}),
        Tool(name="delete_post", description="Delete a post from the Buffer queue.", inputSchema={"type": "object", "properties": {"post_id": {"type": "string"}}, "required": ["post_id"]}),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "get_channels":
        data = _gql("{ account { channels { id name service serviceId } } }")
        return [TextContent(type="text", text=json.dumps(data.get("data", {}).get("account", {}).get("channels", [])))]
    elif name == "create_post":
        assets = [{"image": {"url": u}} for u in arguments.get("image_urls", [])]
        inp = {"channelId": arguments["channel_id"], "text": arguments["text"], "schedulingType": "automatic", "mode": arguments.get("mode", "shareNow"), "assets": assets}
        if arguments.get("platform", "instagram") == "instagram":
            inp["metadata"] = {"instagram": {"type": "post", "shouldShareToFeed": True}}
        mutation = "mutation CreatePost($input: CreatePostInput!) { createPost(input: $input) { __typename ... on PostActionSuccess { post { id status dueAt } } ... on UnexpectedError { message } ... on InvalidInputError { message } } }"
        data = _gql(mutation, {"input": inp})
        return [TextContent(type="text", text=json.dumps(data.get("data", {}).get("createPost", {})))]
    elif name == "get_post_status":
        post_id = arguments["post_id"]
        q = f'{{ post(input: {{ id: "{post_id}" }}) {{ id status sentAt dueAt error {{ message rawError }} }} }}'
        data = _gql(q)
        return [TextContent(type="text", text=json.dumps(data.get("data", {}).get("post", {})))]
    elif name == "delete_post":
        data = _gql("mutation D($id: PostId!) { deletePost(input: { id: $id }) { __typename } }", {"id": arguments["post_id"]})
        return [TextContent(type="text", text=json.dumps(data.get("data", {}).get("deletePost", {})))]
    return [TextContent(type="text", text="Unknown tool")]

sse_transport = SseServerTransport("/messages/")

async def handle_sse(request: Request):
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())

app = Starlette(routes=[
    Route("/sse", endpoint=handle_sse),
    Mount("/messages/", app=sse_transport.handle_post_message),
])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

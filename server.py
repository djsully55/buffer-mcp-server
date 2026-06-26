#!/usr/bin/env python3
"""
Buffer MCP Server v2 — uses official MCP SDK
"""
from mcp.server.fastmcp import FastMCP
import os
import requests

mcp = FastMCP("Buffer")

GQL_URL = "https://api.buffer.com/graphql"

def _headers():
    return {
        "Authorization": f"Bearer {os.environ['BUFFER_ACCESS_TOKEN']}",
        "Content-Type": "application/json"
    }

def _gql(query: str, variables: dict = None) -> dict:
    resp = requests.post(GQL_URL, headers=_headers(),
                         json={"query": query, "variables": variables or {}},
                         timeout=30)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def get_channels() -> list:
    """Get all connected Buffer channels with their IDs and platform names.
    Always call this first to get channel_id values for create_post."""
    data = _gql("{ account { channels { id name service serviceId } } }")
    return data.get("data", {}).get("account", {}).get("channels", [])


@mcp.tool()
def create_post(channel_id: str, text: str, image_urls: list = [],
                platform: str = "instagram", mode: str = "shareNow") -> dict:
    """Create and publish a post to a Buffer channel.

    Args:
        channel_id: Buffer channel ID from get_channels
        text: Caption or thread text
        image_urls: List of image URLs (empty list for text-only posts)
        platform: instagram or x
        mode: shareNow or addToQueue
    """
    assets = [{"image": {"url": u}} for u in image_urls]
    inp = {"channelId": channel_id, "text": text,
           "schedulingType": "automatic", "mode": mode, "assets": assets}
    if platform == "instagram":
        inp["metadata"] = {"instagram": {"type": "post", "shouldShareToFeed": True}}
    mutation = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        __typename
        ... on PostActionSuccess { post { id status dueAt } }
        ... on UnexpectedError   { message }
        ... on InvalidInputError { message }
      }
    }"""
    data = _gql(mutation, {"input": inp})
    return data.get("data", {}).get("createPost", {})


@mcp.tool()
def get_post_status(post_id: str) -> dict:
    """Get the current status of a Buffer post (sent, error, sending, scheduled).

    Args:
        post_id: Buffer post ID returned by create_post
    """
    q = f'{{ post(input: {{ id: "{post_id}" }}) {{ id status sentAt dueAt error {{ message rawError }} }} }}'
    data = _gql(q)
    return data.get("data", {}).get("post", {})


@mcp.tool()
def delete_post(post_id: str) -> dict:
    """Delete a post from the Buffer queue.

    Args:
        post_id: Buffer post ID to remove
    """
    mutation = "mutation D($id: PostId!) { deletePost(input: { id: $id }) { __typename } }"
    data = _gql(mutation, {"id": post_id})
    return data.get("data", {}).get("deletePost", {})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.settings.port = port
    mcp.settings.host = "0.0.0.0"
    mcp.run(transport="sse")

#!/usr/bin/env python3
"""
Buffer MCP Server
Exposes Buffer posting tools to Gumloop Workflows via the MCP protocol.
Deploy to Railway, Render, or any Python host. Proxy through Gumloop Proxied MCPs.
"""

from fastmcp import FastMCP
import os
import requests

mcp = FastMCP(
    name="Buffer",
    instructions=(
        "Tools for creating, managing, and checking posts in Buffer. "
        "Use create_post to publish to Instagram or X. "
        "Use get_channels to retrieve channel IDs before posting."
    )
)

GQL_URL = "https://api.buffer.com/graphql"

def _headers():
    token = os.environ.get("BUFFER_ACCESS_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def _gql(query: str, variables: dict = None) -> dict:
    resp = requests.post(
        GQL_URL,
        headers=_headers(),
        json={"query": query, "variables": variables or {}},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def get_channels() -> list:
    """Get all connected Buffer channels with their IDs and platform names.
    Call this first to get channel_id values for create_post.

    Returns:
        List of channels — each has id, name, service (instagram / twitter / etc.)
    """
    query = """
    {
      account {
        channels { id name service serviceId avatar }
      }
    }"""
    data = _gql(query)
    return data.get("data", {}).get("account", {}).get("channels", [])


@mcp.tool()
def create_post(
    channel_id: str,
    text: str,
    image_urls: list = [],
    platform: str = "instagram",
    mode: str = "shareNow"
) -> dict:
    """Create and publish a post to a Buffer channel.

    Args:
        channel_id: Buffer channel ID (get from get_channels)
        text: Caption or thread text
        image_urls: List of image URLs for carousel / image posts (pass [] for text-only)
        platform: 'instagram' or 'x'
        mode: 'shareNow' (post immediately) or 'addToQueue'

    Returns:
        Buffer post ID and status, or error message
    """
    assets = [{"image": {"url": u}} for u in image_urls]
    inp = {
        "channelId": channel_id,
        "text": text,
        "schedulingType": "automatic",
        "mode": mode,
        "assets": assets,
    }
    if platform == "instagram":
        inp["metadata"] = {
            "instagram": {"type": "post", "shouldShareToFeed": True}
        }

    mutation = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        __typename
        ... on PostActionSuccess { post { id status dueAt sentAt } }
        ... on UnexpectedError   { message }
        ... on InvalidInputError { message }
        ... on LimitReachedError { message }
        ... on RestProxyError    { message code }
      }
    }"""

    data = _gql(mutation, {"input": inp})
    return data.get("data", {}).get("createPost", {})


@mcp.tool()
def get_post_status(post_id: str) -> dict:
    """Get the current status of a Buffer post.

    Args:
        post_id: Buffer post ID (returned by create_post)

    Returns:
        status (sent / error / sending / scheduled), sentAt, dueAt, and any error details
    """
    query = f"""
    {{
      post(input: {{ id: "{post_id}" }}) {{
        id
        status
        sentAt
        dueAt
        channelService
        error {{ message rawError }}
      }}
    }}"""
    data = _gql(query)
    return data.get("data", {}).get("post", {})


@mcp.tool()
def delete_post(post_id: str) -> dict:
    """Delete a post from the Buffer queue (e.g. to remove errored posts).

    Args:
        post_id: Buffer post ID to delete

    Returns:
        Deletion result typename (DeletePostSuccess or error)
    """
    mutation = """
    mutation DeletePost($id: PostId!) {
      deletePost(input: { id: $id }) { __typename }
    }"""
    data = _gql(mutation, {"id": post_id})
    return data.get("data", {}).get("deletePost", {})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="sse", host="0.0.0.0", port=port)

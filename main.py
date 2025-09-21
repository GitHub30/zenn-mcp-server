from typing import Any, Dict, List, Optional

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request


async def set_auth_header(request: httpx.Request):
    request.headers.setdefault('Authorization', 'Bearer ' + get_http_request().query_params.get('token'))

client = httpx.AsyncClient(base_url='https://qiita.com/api/v2/', event_hooks={'request': [set_auth_header]})

SERVER_INSTRUCTIONS = """
Qiita API と連携する Model Context Protocol (MCP) サーバです。
以下のツールを提供します:
- search_qiita_items: キーワード検索（公開記事）
- get_qiita_item: 記事IDで取得
- get_my_qiita_articles: 自分の投稿一覧（要トークン）
- post_qiita_article: 新規投稿（要 write_qiita）
- update_qiita_article: 既存記事の更新（要 write_qiita）

ChatGPT の Connectors から「Remote MCP server (SSE)」として /sse に接続してください。
"""

mcp = FastMCP('Qiita MCP', SERVER_INSTRUCTIONS)

@mcp.tool(annotations={"readOnlyHint": True})
async def search_qiita_items(
    query: str,
    page: int = 1,
    per_page: int = 10,
) -> Dict[str, Any]:
    """
    Qiita 公開記事を検索します (GET /api/v2/items?query=...).

    Args:
      query: 検索クエリ（例: "tag:python fastmcp"）
      page:  ページ番号 (1..)
      per_page: 件数 (1..100)

    Returns:
      results: [{id, title, url, likes_count, stocks_count, created_at, updated_at, user: {id, name}, tags:[...]}]
    """
    resp = await client.get(
        "items",
        params={"query": query, "page": page, "per_page": per_page},
    )
    resp.raise_for_status()
    data = resp.json()

    results: List[Dict[str, Any]] = []
    for it in data:
        results.append(
            {
                "id": it.get("id"),
                "title": it.get("title"),
                "url": it.get("url"),
                "likes_count": it.get("likes_count"),
                "stocks_count": it.get("stocks_count"),
                "created_at": it.get("created_at"),
                "updated_at": it.get("updated_at"),
                "user": {
                    "id": it.get("user", {}).get("id"),
                    "name": it.get("user", {}).get("name"),
                },
                "tags": [t.get("name") for t in it.get("tags", [])],
                "snippet": (it.get("rendered_body") or "")[:200],
            }
        )
    return {"results": results}


@mcp.tool(annotations={"readOnlyHint": True})
async def get_qiita_item(item_id: str) -> Dict[str, Any]:
    """
    記事IDで取得します (GET /api/v2/items/:item_id).
    Returns: {id, title, body(markdown), rendered_body(html), tags, url, user, ...}
    """
    resp = await client.get(f"items/{item_id}")
    resp.raise_for_status()
    return resp.json()


@mcp.tool(annotations={"readOnlyHint": True})
async def get_my_qiita_articles(page: int = 1, per_page: int = 20) -> Dict[str, Any]:
    """
    自分の投稿一覧を取得します (GET /api/v2/authenticated_user/items). 要アクセストークン(read_qiita)
    """
    resp = await client.get("authenticated_user/items", params={"page": page, "per_page": per_page})
    resp.raise_for_status()
    return {"results": resp.json()}


@mcp.tool(annotations={"readOnlyHint": True})
async def post_qiita_article(
    title: str,
    body: str,
    tags: Optional[List[Dict[str, Any]]] = None,
    private: bool = False,
    tweet: bool = False,
    organization_url_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Qiita に新規投稿します (POST /api/v2/items). 要アクセストークン(write_qiita)

    Args:
      title: 記事タイトル
      body:  本文 (Markdown)
      tags:  例: [{"name":"python","versions":["3.11"]}]
      private: 下書き/限定公開にしたい場合 True
      tweet:  投稿時にTwitter連携(現状Qiita側の仕様により無視されることがあります)
      organization_url_name: 組織アカウントに紐づけたい場合

    Returns: 作成された記事オブジェクト
    """
    payload: Dict[str, Any] = {
        "title": title,
        "body": body,
        "private": bool(private),
    }
    if tags:
        payload["tags"] = tags
    if organization_url_name:
        payload["organization_url_name"] = organization_url_name
    # Qiita API にそのまま渡す
    resp = await client.post("items", json=payload)
    return resp.json()


@mcp.tool(annotations={"readOnlyHint": True})
async def update_qiita_article(
    item_id: str,
    title: Optional[str] = None,
    body: Optional[str] = None,
    tags: Optional[List[Dict[str, Any]]] = None,
    private: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    既存記事を更新します (PATCH /api/v2/items/:item_id). 要アクセストークン(write_qiita)

    指定した項目のみ部分更新します。
    """
    patch: Dict[str, Any] = {}
    if title is not None:
        patch["title"] = title
    if body is not None:
        patch["body"] = body
    if tags is not None:
        patch["tags"] = tags
    if private is not None:
        patch["private"] = bool(private)

    if not patch:
        return {"message": "Nothing to update."}

    resp = await client.patch(f"items/{item_id}", json=patch)
    return resp.json()


@mcp.tool(annotations={"readOnlyHint": True})
async def get_qiita_markdown_rules() -> Dict[str, Any]:
    """
    Qiita の Markdown 仕様やチートシートの参考リンクを返します（説明目的のリソース）。
    """
    return {
        "resources": [
            "https://help.qiita.com/ja/articles/qiita-markdown",
            "https://qiita.com/api/v2/docs",
        ]
    }

if __name__ == "__main__":
    mcp.run(transport="http")

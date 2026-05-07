#!/usr/bin/env python3
"""Fetch GitHub weekly trending repositories and push a digest notification."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from typing import Any

TRENDING_URL = "https://github.com/trending"


def _request_text(url: str, method: str = "GET", headers: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> str:
    data = None
    req_headers = headers or {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, method=method, headers=req_headers, data=data)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def fetch_weekly_trending(language: str | None, top: int) -> list[dict[str, str]]:
    params = {"since": "weekly"}
    if language:
        params["l"] = language
    url = f"{TRENDING_URL}?{urllib.parse.urlencode(params)}"

    html = _request_text(
        url,
        headers={
            "User-Agent": "weekly-github-trending-script",
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    # Each repository card is inside an <article class="Box-row"> ... </article>
    cards = re.findall(r"<article class=\"Box-row\"(.*?)</article>", html, flags=re.S)
    repos = []

    for card in cards[:top]:
        name_match = re.search(r"href=\"/([^\"]+/[^\"]+)\"", card)
        if not name_match:
            continue
        full_name = name_match.group(1).strip()

        desc_match = re.search(r"<p[^>]*>(.*?)</p>", card, flags=re.S)
        description = ""
        if desc_match:
            description = re.sub(r"<.*?>", "", desc_match.group(1))
            description = " ".join(unescape(description).split())

        lang_match = re.search(r"itemprop=\"programmingLanguage\">\s*(.*?)\s*</span>", card, flags=re.S)
        language = unescape(lang_match.group(1).strip()) if lang_match else "Unknown"

        stars_week_match = re.search(r"([0-9,]+)\s+stars?\s+this\s+week", card, flags=re.I)
        stars_week = stars_week_match.group(1) if stars_week_match else "0"

        stars_total_match = re.search(r"href=\"/[^\"]+/stargazers\"[^>]*>\s*([0-9,]+)\s*</a>", card, flags=re.S)
        stars_total = stars_total_match.group(1) if stars_total_match else "0"

        repos.append(
            {
                "full_name": full_name,
                "description": description,
                "language": language,
                "stars_week": stars_week,
                "stars_total": stars_total,
                "url": f"https://github.com/{full_name}",
            }
        )

    return repos


def format_digest(repos: list[dict[str, str]]) -> str:
    if not repos:
        return "本周未检索到符合条件的 Trending 项目。"

    lines = []
    for i, repo in enumerate(repos, start=1):
        lines.append(
            f"{i}. {repo['full_name']} | 本周 +⭐ {repo['stars_week']} | 总⭐ {repo['stars_total']} | {repo['language']}\n"
            f"   {repo['description']}\n"
            f"   {repo['url']}"
        )
    return "\n\n".join(lines)


def push_digest(webhook_url: str, title: str, content: str) -> None:
    _request_text(webhook_url, method="POST", body={"title": title, "content": content})


def main() -> int:
    parser = argparse.ArgumentParser(description="每周 GitHub Trending 项目抓取 + 推送")
    parser.add_argument("--language", default=None, help="可选语言，如 python")
    parser.add_argument("--top", type=int, default=10, help="返回项目数量")
    parser.add_argument("--dry-run", action="store_true", help="仅打印，不推送")
    args = parser.parse_args()

    try:
        repos = fetch_weekly_trending(args.language, args.top)
    except urllib.error.HTTPError as exc:
        print(f"获取 GitHub Trending 失败: HTTP {exc.code}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"获取 GitHub Trending 失败: {exc}", file=sys.stderr)
        return 1

    today = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    title = f"GitHub 周热榜（{today}）"
    content = format_digest(repos)

    print(title)
    print("=" * len(title))
    print(content)

    if args.dry_run:
        return 0

    webhook_url = os.getenv("PUSH_WEBHOOK_URL")
    if not webhook_url:
        print("未设置 PUSH_WEBHOOK_URL，无法推送。", file=sys.stderr)
        return 2

    try:
        push_digest(webhook_url, title, content)
    except urllib.error.HTTPError as exc:
        print(f"推送失败: HTTP {exc.code}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"推送失败: {exc}", file=sys.stderr)
        return 3

    print("\n推送成功。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

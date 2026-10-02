#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 references/topics.json 配置定向抓取 arXiv 最新论文，输出 JSON 原始数据供生成日报。

用法：
    python references/fetch_arxiv.py                      # 使用 topics.json 默认配置
    python references/fetch_arxiv.py --days 5             # 覆盖时间窗口（天）
    python references/fetch_arxiv.py --no-dedup           # 不去重（默认会排除此前日报已覆盖的论文）
    python references/fetch_arxiv.py --output out.json    # 指定输出路径
"""

import argparse
import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ARXIV_API = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"

SKILL_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = SKILL_DIR / "reports"
SEEN_FILE = REPORTS_DIR / ".seen_ids.json"
DEFAULT_TOPICS = SKILL_DIR / "references" / "topics.json"


def build_search_query(topic):
    parts = []
    cats = topic.get("categories") or []
    if cats:
        parts.append("(" + " OR ".join(f"cat:{c}" for c in cats) + ")")
    kws = topic.get("keywords") or []
    if kws:
        terms = [f'all:"{k}"' if " " in k else f"all:{k}" for k in kws]
        parts.append("(" + " OR ".join(terms) + ")")
    return " AND ".join(parts) if parts else "cat:cs.CV"


def fetch_topic(topic, days, max_results):
    params = {
        "search_query": build_search_query(topic),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "start": 0,
        "max_results": max_results,
    }
    url = ARXIV_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "arxiv-daily-report/1.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.URLError as e:
        # 部分 Windows Python 环境缺少根证书，回退到不校验证书
        if "CERTIFICATE_VERIFY_FAILED" not in str(e):
            raise
        print("[提示] 本机 Python 缺少根证书，已跳过 SSL 证书校验", file=sys.stderr)
        resp = urllib.request.urlopen(req, timeout=60,
                                      context=ssl._create_unverified_context())
    with resp:
        root = ET.fromstring(resp.read())

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    papers = []
    for entry in root.findall(f"{ATOM}entry"):
        published = entry.findtext(f"{ATOM}published", "")
        try:
            pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except ValueError:
            continue
        if pub_dt < cutoff:
            continue
        arxiv_id = entry.findtext(f"{ATOM}id", "").rsplit("/abs/", 1)[-1]
        authors = [a.findtext(f"{ATOM}name", "") for a in entry.findall(f"{ATOM}author")]
        cats = [c.get("term", "") for c in entry.findall(f"{ATOM}category")]
        papers.append({
            "arxiv_id": arxiv_id,
            "title": " ".join(entry.findtext(f"{ATOM}title", "").split()),
            "authors": authors,
            "published": published[:10],
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "categories": cats,
            "abstract": " ".join(entry.findtext(f"{ATOM}summary", "").split()),
        })
    return papers


def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def save_seen(seen):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=0),
                         encoding="utf-8")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description="arXiv 定向抓取")
    ap.add_argument("--topics", default=str(DEFAULT_TOPICS), help="方向配置 JSON 路径")
    ap.add_argument("--days", type=int, default=None, help="时间窗口（天），默认取配置")
    ap.add_argument("--max-results", type=int, default=None, help="每个方向最大抓取数")
    ap.add_argument("--output", default=None, help="输出 JSON 路径，默认 reports/raw-YYYYMMDD.json")
    ap.add_argument("--no-dedup", action="store_true", help="不排除此前日报已覆盖的论文")
    args = ap.parse_args()

    config = json.loads(Path(args.topics).read_text(encoding="utf-8"))
    days = args.days or config.get("days", 3)
    max_results = args.max_results or config.get("max_results_per_topic", 40)
    topics = config.get("topics", [])

    seen = load_seen()
    result_topics = []
    new_ids = set()
    total_dup = 0

    for i, topic in enumerate(topics):
        if i > 0:
            time.sleep(5)  # arXiv API 要求请求间隔 >= 3 秒，留余量
        papers = None
        last_err = None
        for attempt in range(4):
            try:
                papers = fetch_topic(topic, days, max_results)
                break
            except Exception as e:
                last_err = e
                if attempt < 3:
                    wait = 15 * (attempt + 1)
                    print(f"[提示] 方向「{topic.get('name')}」第 {attempt + 1} 次抓取失败"
                          f"（{e}），{wait} 秒后重试", file=sys.stderr)
                    time.sleep(wait)
        if papers is None:
            print(f"[警告] 方向「{topic.get('name')}」抓取失败：{last_err}", file=sys.stderr)
            result_topics.append({"name": topic.get("name"), "error": str(last_err), "papers": []})
            continue

        if args.no_dedup:
            kept = papers
        else:
            kept = [p for p in papers if p["arxiv_id"] not in seen]
            total_dup += len(papers) - len(kept)
        new_ids.update(p["arxiv_id"] for p in kept)
        result_topics.append({"name": topic.get("name"), "papers": kept})

    if not args.no_dedup:
        save_seen(seen | new_ids)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output = args.output or str(REPORTS_DIR / f"raw-{datetime.now():%Y%m%d}.json")
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window_days": days,
        "deduped_count": total_dup,
        "topics": result_topics,
    }
    Path(output).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    counts = ", ".join(f"{t['name']}: {len(t['papers'])} 篇" for t in result_topics)
    print(f"抓取完成（{counts}；去重过滤 {total_dup} 篇）-> {output}")


if __name__ == "__main__":
    main()

"""
Live RSS Feed Ingest Verification & Smoke Test Tool
Audits, probes, and benchmarks active RSS/Atom endpoints across all 16 languages.
Generates latency, status code, XML parse validity, and item count metrics.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Dict, List
import feedparser
import httpx
import yaml


def probe_feed(
    url: str,
    timeout: float = 6.0,
    user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 (compatible; PosiPulseBot/1.0; +https://posipulse.in/bot)"
) -> Dict[str, Any]:
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
    }
    start = time.time()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            duration = round(time.time() - start, 3)
            status_code = resp.status_code
            if status_code == 200:
                parsed = feedparser.parse(resp.text)
                entries_count = len(parsed.entries)
                bozo = getattr(parsed, "bozo", 0)
                title = parsed.feed.get("title", "Untitled Feed") if hasattr(parsed, "feed") else "Unknown"
                return {
                    "status": "HEALTHY" if entries_count > 0 else "EMPTY",
                    "http_code": 200,
                    "duration_sec": duration,
                    "items_count": entries_count,
                    "bozo": int(bozo),
                    "feed_title": title,
                    "error": None
                }
            else:
                return {
                    "status": "HTTP_ERROR",
                    "http_code": status_code,
                    "duration_sec": duration,
                    "items_count": 0,
                    "bozo": 1,
                    "feed_title": None,
                    "error": f"HTTP {status_code}"
                }
    except Exception as e:
        duration = round(time.time() - start, 3)
        return {
            "status": "NETWORK_ERROR",
            "http_code": None,
            "duration_sec": duration,
            "items_count": 0,
            "bozo": 1,
            "feed_title": None,
            "error": f"{type(e).__name__}: {str(e)[:80]}"
        }


def run_audit(config_dir: Path) -> List[Dict[str, Any]]:
    results = []
    yaml_files = sorted(config_dir.glob("*.yaml"))
    
    for yf in yaml_files:
        with open(yf, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        lang = data.get("language_code", yf.stem)
        lang_name = data.get("language_name_english", lang)
        tier = data.get("tier", "tier_unknown")
        
        for src in data.get("sources", []):
            sid = src.get("id")
            sname = src.get("name")
            feed_url = src.get("feed_url")
            is_active = src.get("is_active", True)
            
            probe_res = probe_feed(feed_url)
            results.append({
                "language_code": lang,
                "language_name": lang_name,
                "tier": tier,
                "source_id": sid,
                "source_name": sname,
                "feed_url": feed_url,
                "is_active": is_active,
                **probe_res
            })
            
    return results


def print_markdown_report(results: List[Dict[str, Any]]) -> str:
    healthy_count = sum(1 for r in results if r["status"] == "HEALTHY")
    total_count = len(results)
    
    lines = [
        "# PosiPulse Live RSS Ingest Verification Audit",
        f"**Timestamp:** {datetime.now(timezone.utc).isoformat()}  ",
        f"**Healthy Yielding Feeds:** {healthy_count} / {total_count} ({round(healthy_count / total_count * 100, 1) if total_count else 0}%)\n",
        "| Tier | Lang | Source ID | Name | HTTP | Items | Latency | Status |",
        "|---|---|---|---|---|---|---|---|"
    ]
    
    for r in results:
        status_icon = "✅" if r["status"] == "HEALTHY" else ("⚠️" if r["status"] == "EMPTY" else "❌")
        lines.append(
            f"| {r['tier']} | {r['language_code']} | `{r['source_id']}` | {r['source_name']} | {r['http_code'] or 'ERR'} | {r['items_count']} | {r['duration_sec']}s | {status_icon} {r['status']} |"
        )
        
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live RSS Feed Smoke Tester")
    parser.add_argument("--config-dir", default="config/languages", help="Path to language YAML configurations")
    parser.add_argument("--json", action="store_true", help="Output raw JSON format")
    args = parser.parse_args()
    
    res = run_audit(Path(args.config_dir))
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(print_markdown_report(res))

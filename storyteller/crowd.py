"""Crowd mood from YouTube comments.

Pipeline per game:
1. YouTube Data API v3 (key in YOUTUBE_API_KEY): search.list for recap videos
   published within `search_window_days` of the round start, videos.list for
   titles/stats, commentThreads.list for top-level comments (no author data kept).
2. Claude (Haiku by default) labels each comment: who the commenter favours,
   tone toward each player, how the game felt, and opinions on specific moves.
   Move mentions are validated against the game's actual moves.
3. Aggregates only are published: shares, counts, moves discussed, and an
   "engine vs crowd" comparison. Raw comments stay in the local cache.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import requests

from .cache import Cache

log = logging.getLogger(__name__)
API = "https://www.googleapis.com/youtube/v3"
PROMPT_VERSION = "crowd-v1"


# ---------------------------------------------------------------- YouTube

def _get(path: str, params: dict) -> dict:
    r = requests.get(f"{API}/{path}", params={**params, "key": os.environ["YOUTUBE_API_KEY"]}, timeout=30)
    if r.status_code == 403 and "commentsDisabled" in r.text:
        return {"items": [], "comments_disabled": True}
    r.raise_for_status()
    return r.json()


def find_videos(query: str, after: datetime, before: datetime, n: int) -> list[dict]:
    data = _get("search", {
        "part": "snippet", "q": query, "type": "video", "order": "relevance", "maxResults": n,
        "publishedAfter": after.strftime("%Y-%m-%dT%H:%M:%SZ"), "publishedBefore": before.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    ids = [it["id"]["videoId"] for it in data.get("items", []) if it.get("id", {}).get("videoId")]
    if not ids:
        return []
    stats = _get("videos", {"part": "snippet,statistics", "id": ",".join(ids)})
    out = []
    for it in stats.get("items", []):
        sn, st = it["snippet"], it.get("statistics", {})
        out.append({
            "id": it["id"], "title": sn["title"], "channel": sn["channelTitle"], "published": sn["publishedAt"],
            "views": int(st.get("viewCount", 0)), "comment_count": int(st.get("commentCount", 0)),
            "url": f"https://www.youtube.com/watch?v={it['id']}",
        })
    return out


def fetch_comments(video_id: str, limit: int) -> list[dict]:
    comments, token = [], None
    while len(comments) < limit:
        params = {"part": "snippet", "videoId": video_id, "maxResults": min(100, limit - len(comments)), "order": "relevance", "textFormat": "plainText"}
        if token:
            params["pageToken"] = token
        data = _get("commentThreads", params)
        for it in data.get("items", []):
            c = it["snippet"]["topLevelComment"]["snippet"]
            # deliberately no author name / channel: only text, likes and time
            comments.append({"id": it["id"], "text": c["textDisplay"][:600], "likes": int(c.get("likeCount", 0)), "published": c["publishedAt"]})
        token = data.get("nextPageToken")
        if not token:
            break
    return comments


def collect(cfg: dict, cache: Cache, game_id: str, round_no: int, starts_at_ms: int, players: list[str], refresh: bool = False) -> dict | None:
    """Videos + comments for one game, cached so YouTube quota is spent once."""
    key = f"{game_id}|{cfg['videos_per_game']}|{cfg['comments_per_video']}|{cfg['search_window_days']}"
    if not refresh and (hit := cache.get("youtube", key)):
        return hit
    start = datetime.fromtimestamp(starts_at_ms / 1000, tz=timezone.utc)
    query = cfg.get("query", "{p1} {p2} game {round}").format(p1=players[0], p2=players[1], round=round_no)
    videos = find_videos(query, start, start + timedelta(days=float(cfg["search_window_days"])), int(cfg["videos_per_game"]))
    seen, comments = set(), []
    for v in videos:
        cs = fetch_comments(v["id"], int(cfg["comments_per_video"]))
        v["comments_read"] = len(cs)
        for c in cs:
            norm = re.sub(r"\s+", " ", c["text"].strip().lower())
            if len(norm.split()) < 3 or norm in seen:
                continue
            seen.add(norm)
            comments.append({**c, "video": v["id"]})
    data = {"query": query, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "videos": videos, "comments": comments}
    cache.put("youtube", key, data)
    return data


# ---------------------------------------------------------------- labelling

SYSTEM = """You label YouTube comments about one game of the World Chess Championship match between {a} and {b}.

For every comment return:
- favours: which player the commenter wants or expects to win the MATCH: "{ka}", "{kb}" or "none" (none if unclear).
- tone_{ka} / tone_{kb}: the comment's attitude toward that player: -1 negative, 0 neutral or not mentioned, 1 positive.
- game_feel: how the commenter found this game: "exciting", "boring" or "none".
- moves: moves of THIS game the comment gives an opinion on, written in SAN exactly as in the list of game moves,
  with opinion "praise", "criticism" or "neutral". Only include moves that appear in the list. Empty if none.
Judge only what the comment says; do not judge the chess yourself. Sarcasm counts as the meaning intended."""

SCHEMA_TEMPLATE = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "favours": {"type": "string", "enum": []},
                    "tone_a": {"type": "integer", "enum": [-1, 0, 1]},
                    "tone_b": {"type": "integer", "enum": [-1, 0, 1]},
                    "game_feel": {"type": "string", "enum": ["exciting", "boring", "none"]},
                    "moves": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"san": {"type": "string"}, "opinion": {"type": "string", "enum": ["praise", "criticism", "neutral"]}},
                            "required": ["san", "opinion"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["id", "favours", "tone_a", "tone_b", "game_feel", "moves"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["labels"],
    "additionalProperties": False,
}


def _keys(players: list[str], display: dict) -> tuple[str, str]:
    return tuple(display.get(p, {}).get("short", p).lower() for p in players)  # type: ignore[return-value]


def label_comments(comments: list[dict], doc: dict, players: list[str], display: dict, cfg: dict, cache: Cache) -> list[dict]:
    import anthropic

    ka, kb = _keys(players, display)
    schema = json.loads(json.dumps(SCHEMA_TEMPLATE))
    item = schema["properties"]["labels"]["items"]["properties"]
    item["favours"]["enum"] = [ka, kb, "none"]
    item[f"tone_{ka}"] = item.pop("tone_a")
    item[f"tone_{kb}"] = item.pop("tone_b")
    req = schema["properties"]["labels"]["items"]["required"]
    req[req.index("tone_a")], req[req.index("tone_b")] = f"tone_{ka}", f"tone_{kb}"
    system = SYSTEM.format(a=players[0], b=players[1], ka=ka, kb=kb)
    game_moves = " ".join(m["label"] for m in doc["moves"])
    client = anthropic.Anthropic()
    out: list[dict] = []
    size = int(cfg["batch_size"])
    for i in range(0, len(comments), size):
        batch = comments[i : i + size]
        payload = {"game": doc["id"], "game_moves": game_moves, "comments": [{"id": c["id"], "text": c["text"]} for c in batch]}
        key = hashlib.sha256(json.dumps([PROMPT_VERSION, cfg["model"], system, payload], sort_keys=True).encode()).hexdigest()
        if (hit := cache.get("crowd_labels", key)) is not None:
            out += hit
            continue
        resp = client.messages.create(
            model=cfg["model"],
            max_tokens=16000,
            system=system,
            output_config={"effort": cfg.get("effort", "low"), "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        if resp.stop_reason in ("refusal", "max_tokens"):
            log.warning("crowd labelling stopped (%s) for a batch of %d; skipping it", resp.stop_reason, len(batch))
            continue
        labels = json.loads(next(b.text for b in resp.content if b.type == "text"))["labels"]
        ids = {c["id"] for c in batch}
        labels = [{**l, "tone": {ka: l.pop(f"tone_{ka}"), kb: l.pop(f"tone_{kb}")}} for l in labels if l["id"] in ids]
        cache.put("crowd_labels", key, labels)
        out += labels
    return out


# ---------------------------------------------------------------- aggregation

def _norm(san: str) -> str:
    return san.rstrip("+#!?")


def aggregate(doc: dict, data: dict, labels: list[dict], players: list[str], display: dict, min_mentions: int = 3) -> dict:
    ka, kb = _keys(players, display)
    by_id = {c["id"]: c for c in data["comments"]}
    labels = [l for l in labels if l["id"] in by_id]
    n = len(labels)
    fav = {k: sum(1 for l in labels if l["favours"] == k) for k in (ka, kb, "none")}
    tone = {k: {"positive": sum(1 for l in labels if l["tone"][k] > 0), "negative": sum(1 for l in labels if l["tone"][k] < 0)} for k in (ka, kb)}
    feel = {k: sum(1 for l in labels if l["game_feel"] == k) for k in ("exciting", "boring", "none")}

    # move opinions, validated against the game's own moves
    san_to_plies: dict[str, list[int]] = {}
    for m in doc["moves"]:
        san_to_plies.setdefault(_norm(m["san"]), []).append(m["ply"])
    ops: dict[str, dict] = {}
    dropped = 0
    for l in labels:
        for mv in {(_norm(x["san"]), x["opinion"]) for x in l["moves"]}:
            san, opinion = mv
            if san not in san_to_plies:
                dropped += 1
                continue
            o = ops.setdefault(san, {"praise": 0, "criticism": 0, "neutral": 0})
            o[opinion] += 1

    moves = []
    for san, o in ops.items():
        total = sum(o.values())
        if total < min_mentions:
            continue
        plies = san_to_plies[san]
        m = doc["moves"][plies[0]]
        if m["played_rank"] == 1:
            engine = "top choice"
        elif m["classification"]:
            engine = m["classification"]
        elif m["wp_loss"] >= 2:
            engine = f"slightly worse (−{m['wp_loss']:.1f})"
        else:
            engine = "fine"
        crowd = "praised" if o["praise"] >= 0.6 * total else "criticised" if o["criticism"] >= 0.6 * total else "mixed"
        disagree = (crowd == "praised" and m["classification"] in ("mistake", "blunder")) or (crowd == "criticised" and m["wp_loss"] < 2)
        moves.append({
            "san": san, "label": m["label"], "ply": m["ply"], "ambiguous": len(plies) > 1,
            "mentions": total, **o, "crowd": crowd, "engine": engine, "wp_loss": m["wp_loss"],
            "agrees": None if crowd == "mixed" else not disagree,
        })
    moves.sort(key=lambda x: -x["mentions"])
    return {
        "source": "youtube",
        "query": data["query"],
        "fetched_at": data["fetched_at"],
        "videos": [{k: v[k] for k in ("title", "channel", "url", "views", "comments_read")} for v in data["videos"]],
        "comments_labelled": n,
        "favours": {"keys": {ka: players[0], kb: players[1]}, "counts": fav},
        "tone": tone,
        "game_feel": feel,
        "moves": moves,
        "dropped_unknown_moves": dropped,
        "min_mentions": min_mentions,
    }


def crowd_for_game(cfg_crowd: dict, cache: Cache, doc: dict, round_no: int, starts_at_ms: int | None, players: list[str], display: dict, refresh: bool = False) -> dict | None:
    if not cfg_crowd.get("enabled") or not os.environ.get("YOUTUBE_API_KEY") or starts_at_ms is None:
        return None
    try:
        short = [display.get(p, {}).get("short", p) for p in players]
        data = collect(cfg_crowd, cache, doc["id"], round_no, starts_at_ms, short, refresh)
        if not data or not data["comments"]:
            return {"source": "youtube", "comments_labelled": 0, "videos": data["videos"] if data else [], "query": data["query"] if data else None}
        labels = label_comments(data["comments"], doc, players, display, cfg_crowd, cache)
        return {**aggregate(doc, data, labels, players, display, int(cfg_crowd["min_mentions"])), "model": cfg_crowd["model"]}
    except Exception as e:  # never break the pipeline over crowd data
        log.warning("crowd mood failed for %s: %s", doc["id"], e)
        return None

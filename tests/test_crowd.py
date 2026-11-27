from storyteller import crowd
from storyteller.cache import Cache
from storyteller.crowd import aggregate

PLAYERS = ["Gukesh D", "Sindarov, Javokhir"]
DISPLAY = {"Gukesh D": {"short": "Gukesh"}, "Sindarov, Javokhir": {"short": "Sindarov"}}


def doc():
    sans = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Bxc6", "dxc6"]
    moves = []
    for ply, san in enumerate(sans):
        moves.append({"ply": ply, "san": san, "label": f"{ply // 2 + 1}{'.' if ply % 2 == 0 else '...'}{san}",
                      "classification": "blunder" if san == "Bxc6" else None,
                      "played_rank": 1 if san != "Bxc6" else 4, "wp_loss": 20.0 if san == "Bxc6" else 0.0})
    return {"id": "game-01", "moves": moves}


def label(i, favours="none", g=0, s=0, feel="none", moves=()):
    return {"id": f"c{i}", "favours": favours, "tone": {"gukesh": g, "sindarov": s}, "game_feel": feel,
            "moves": [{"san": m, "opinion": o} for m, o in moves]}


def data(n):
    return {"query": "q", "fetched_at": "t", "videos": [{"title": "v", "channel": "c", "url": "u", "views": 1, "comments_read": n}],
            "comments": [{"id": f"c{i}", "text": "x y z", "likes": 0, "video": "v"} for i in range(n)]}


def test_shares_tone_and_feel():
    labels = [label(0, "gukesh", g=1, feel="exciting"), label(1, "sindarov", s=-1, feel="boring"),
              label(2, "sindarov", feel="boring"), label(3)]
    a = aggregate(doc(), data(4), labels, PLAYERS, DISPLAY)
    assert a["comments_labelled"] == 4
    assert a["favours"]["counts"] == {"gukesh": 1, "sindarov": 2, "none": 1}
    assert a["favours"]["keys"]["gukesh"] == "Gukesh D"
    assert a["tone"]["gukesh"] == {"positive": 1, "negative": 0} and a["tone"]["sindarov"]["negative"] == 1
    assert a["game_feel"] == {"exciting": 1, "boring": 2, "none": 1}


def test_engine_vs_crowd_and_validation():
    labels = [label(i, moves=[("Bxc6", "praise")]) for i in range(4)]            # crowd loves the engine's blunder
    labels += [label(10 + i, moves=[("Nf3+", "criticism")]) for i in range(3)]   # crowd hates a top move (check suffix normalised)
    labels += [label(20, moves=[("Qh5", "praise")]), label(21, moves=[("Bb5", "praise")])]   # Qh5 not in game; Bb5 below min
    labels.append(label(22, moves=[("Bxc6", "praise"), ("Bxc6", "praise")]))     # duplicate inside one comment counts once
    d = data(30)
    a = aggregate(doc(), d, labels, PLAYERS, DISPLAY, min_mentions=3)
    by = {m["san"]: m for m in a["moves"]}
    assert set(by) == {"Bxc6", "Nf3"}
    assert by["Bxc6"]["mentions"] == 5 and by["Bxc6"]["crowd"] == "praised" and by["Bxc6"]["agrees"] is False
    assert by["Nf3"]["crowd"] == "criticised" and by["Nf3"]["agrees"] is False and by["Nf3"]["engine"] == "top choice"
    assert a["dropped_unknown_moves"] == 1
    assert a["moves"][0]["san"] == "Bxc6"   # sorted by mentions


def test_labels_for_unknown_comments_are_ignored():
    a = aggregate(doc(), data(1), [label(0, "gukesh"), label(99, "sindarov")], PLAYERS, DISPLAY)
    assert a["comments_labelled"] == 1 and a["favours"]["counts"]["sindarov"] == 0


def test_collect_dedupes_drops_short_and_never_keeps_authors(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test")
    calls = []

    def fake_get(path, params):
        calls.append(path)
        if path == "search":
            return {"items": [{"id": {"videoId": "v1"}}]}
        if path == "videos":
            return {"items": [{"id": "v1", "snippet": {"title": "T", "channelTitle": "C", "publishedAt": "p"}, "statistics": {"viewCount": "10", "commentCount": "3"}}]}
        return {"items": [
            {"id": "a", "snippet": {"topLevelComment": {"snippet": {"textDisplay": "Great game by Gukesh today", "likeCount": 5, "publishedAt": "p", "authorDisplayName": "SomeUser"}}}},
            {"id": "b", "snippet": {"topLevelComment": {"snippet": {"textDisplay": "great  game by gukesh today", "likeCount": 1, "publishedAt": "p", "authorDisplayName": "Other"}}}},
            {"id": "c", "snippet": {"topLevelComment": {"snippet": {"textDisplay": "lol", "likeCount": 0, "publishedAt": "p"}}}},
        ]}

    monkeypatch.setattr(crowd, "_get", fake_get)
    cfg = {"videos_per_game": 5, "comments_per_video": 100, "search_window_days": 3, "query": "{p1} {p2} game {round}"}
    cache = Cache(tmp_path / "c.sqlite")
    out = crowd.collect(cfg, cache, "game-01", 1, 1795528800000, ["Gukesh", "Sindarov"])
    assert out["query"] == "Gukesh Sindarov game 1"
    assert [c["id"] for c in out["comments"]] == ["a"]
    assert all("author" not in k.lower() for c in out["comments"] for k in c)
    n = len(calls)
    crowd.collect(cfg, cache, "game-01", 1, 1795528800000, ["Gukesh", "Sindarov"])   # second call: cached, no API
    assert len(calls) == n


def test_disabled_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert crowd.crowd_for_game({"enabled": True}, Cache(tmp_path / "c.sqlite"), doc(), 1, 1, PLAYERS, DISPLAY) is None


# ---------------------------------------------------------------- Bluesky

from datetime import datetime, timedelta, timezone

T0 = datetime(2026, 11, 24, 14, tzinfo=timezone.utc)


def fake_bsky(posts_by_minute):
    """posts_by_minute: {minute offset from T0: text}. Mimics the 100-per-request cap."""
    calls = []

    def search(term, since, until):
        calls.append((term, since, until))
        hits = [(m, t) for m, t in posts_by_minute.items() if term in t and since <= T0 + timedelta(minutes=m) < until]
        hits.sort(key=lambda x: -x[0])
        return [{"id": f"bs-{m}", "text": t, "likes": 0, "reposts": 0, "published": (T0 + timedelta(minutes=m)).isoformat(), "langs": []}
                for m, t in hits[:100]]
    return search, calls


def test_bluesky_window_stops_at_next_round_and_now():
    start, nxt = int(T0.timestamp() * 1000), int((T0 + timedelta(hours=24)).timestamp() * 1000)
    since, until, closed = crowd.bluesky_window(start, nxt, 48, now=T0 + timedelta(days=3))
    assert (since, until, closed) == (T0, T0 + timedelta(hours=24), True)
    since, until, closed = crowd.bluesky_window(start, None, 48, now=T0 + timedelta(hours=5))
    assert until == T0 + timedelta(hours=5) and not closed


def test_bluesky_splits_full_slices_and_merges_terms(tmp_path):
    posts = {m: f"gukesh plays move number {m}" for m in range(0, 1440, 4)}     # 360 posts in 24h: needs splitting
    posts.update({m: f"sindarov holds the draw {m}" for m in range(1, 1440, 30)})
    posts[3] = "gukesh and sindarov shake hands"                                # matches both terms: kept once
    search, calls = fake_bsky(posts)
    start, nxt = int(T0.timestamp() * 1000), int((T0 + timedelta(hours=24)).timestamp() * 1000)
    cfg = {"max_window_hours": 48, "min_slice_minutes": 20}
    cache = Cache(tmp_path / "c.sqlite")
    data = crowd.collect_bluesky(cfg, cache, "game-01", start, nxt, ["gukesh", "sindarov"], search=search, now=T0 + timedelta(days=2))
    assert data["posts_found"] == len(posts) and not data["truncated"]
    assert len({c["id"] for c in data["comments"]}) == len(data["comments"]) == len(posts)
    assert all("author" not in k and "uri" not in k for c in data["comments"] for k in c)
    n = len(calls)
    crowd.collect_bluesky(cfg, cache, "game-01", start, nxt, ["gukesh", "sindarov"], search=search, now=T0 + timedelta(days=2))
    assert len(calls) == n                                                      # closed window: served from cache


def test_bluesky_open_window_is_not_cached(tmp_path):
    posts = {m: f"gukesh blitz post {m} " for m in range(0, 30)} | {m + 0.5: f"gukesh blitz again {m}" for m in range(0, 30)}
    posts.update({m + 0.25: f"gukesh third wave {m}" for m in range(0, 30)} | {m + 0.75: f"gukesh fourth wave {m}" for m in range(0, 30)})
    search, calls = fake_bsky(posts)                                            # 120 posts inside 30 minutes
    start = int(T0.timestamp() * 1000)
    cfg = {"max_window_hours": 48, "min_slice_minutes": 20}
    cache = Cache(tmp_path / "c.sqlite")
    data = crowd.collect_bluesky(cfg, cache, "game-04", start, None, ["gukesh"], search=search, now=T0 + timedelta(minutes=30))
    assert not data["window_closed"]
    n = len(calls)
    crowd.collect_bluesky(cfg, cache, "game-04", start, None, ["gukesh"], search=search, now=T0 + timedelta(minutes=30))
    assert len(calls) > n                                                       # still open: fetched again


def test_normalise_wraps_old_single_source_files():
    old = {"source": "youtube", "comments_labelled": 3}
    assert crowd.normalise(old) == {"youtube": old}
    assert crowd.normalise({"youtube": old}) == {"youtube": old}
    assert crowd.normalise(None) == {}

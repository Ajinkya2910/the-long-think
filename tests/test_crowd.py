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

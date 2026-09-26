"""RSS adapter (stdlib only). Stores headlines/links/short excerpts and tags player mentions."""
import email.utils, html, json, re
import xml.etree.ElementTree as ET
import requests
from . import db

FEEDS = [
    ("https://dobberhockey.com/feed/", "dobberhockey", "Dobber: all"),
    ("https://dobberhockey.com/category/hockey-home/feed/", "dobberhockey", "Dobber: hockey home"),
    ("https://dobberhockey.com/category/hockey-rambling/feed/", "dobberhockey", "Dobber: ramblings"),
    ("https://dobberhockey.com/tag/fantasy-hockey/feed/", "dobberhockey", "Dobber: fantasy-hockey tag"),
    ("https://dobberhockey.com/tag/fantasy-hockey-tips/feed/", "dobberhockey", "Dobber: fantasy-hockey-tips tag"),
]
NS = {"dc": "http://purl.org/dc/elements/1.1/", "content": "http://purl.org/rss/1.0/modules/content/"}
UA = {"User-Agent": "fantasy-hockey-research/0.1 (personal, read-only)"}
EXCERPT = 300


def _text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _iso(rfc):
    try:
        return email.utils.parsedate_to_datetime(rfc).astimezone(__import__("datetime").timezone.utc).isoformat()
    except Exception:
        return None


def _name_index(con):
    idx = {}
    for r in con.execute("SELECT espn_id, full_name FROM players WHERE active=1"):
        idx.setdefault(r["full_name"], []).append(r["espn_id"])
    # one regex per name is slow; bucket by last word instead
    by_last = {}
    for name, ids in idx.items():
        by_last.setdefault(name.split()[-1].lower(), []).append((name, ids))
    return by_last


def _mentions(text, by_last):
    low = text.lower()
    found = {}
    for word in set(re.findall(r"[a-zà-ÿ'\-]+", low)):
        for name, ids in by_last.get(word, []):
            if re.search(r"(?<![\w])" + re.escape(name.lower()) + r"(?![\w])", low):
                for i in ids:
                    found[i] = "full_name_unique" if len(ids) == 1 else "full_name_ambiguous"
    return found


def refresh(con, feeds=FEEDS):
    by_last = _name_index(con)
    ts = db.now_utc()
    summary = []
    for url, source, label in feeds:
        con.execute("INSERT OR IGNORE INTO feeds (feed_url, source_id, label) VALUES (?,?,?)", (url, source, label))
        run = db.start_run(con, source, "rss:" + url, None)
        try:
            r = requests.get(url, headers=UA, timeout=30)
            r.raise_for_status()
            ch = ET.fromstring(r.content).find("channel")
        except Exception as e:
            con.execute("UPDATE feeds SET last_fetched_at=?, last_http_status=? WHERE feed_url=?",
                        (ts, getattr(getattr(e, "response", None), "status_code", None), url))
            db.finish_run(con, run, False, None, 0, type(e).__name__)
            summary.append((label, "FAILED"))
            continue
        new = 0
        for it in ch.findall("item"):
            guid = (it.findtext("guid") or it.findtext("link")).strip()
            title = _text(it.findtext("title"))
            desc = _text(it.findtext("description"))
            body = _text(it.findtext("content:encoded", namespaces=NS))  # used for matching only, never stored
            cats = [c.text for c in it.findall("category") if c.text]
            existed = con.execute("SELECT feeds_seen_in FROM news_items WHERE guid=?", (guid,)).fetchone()
            if existed:
                seen = set(json.loads(existed[0] or "[]")) | {label}
                con.execute("UPDATE news_items SET feeds_seen_in=? WHERE guid=?", (json.dumps(sorted(seen)), guid))
            else:
                new += 1
                con.execute("INSERT INTO news_items VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (guid, source, title, it.findtext("link"), _text(it.findtext("dc:creator", namespaces=NS)),
                             _iso(it.findtext("pubDate")), json.dumps(cats),
                             desc[:EXCERPT] + ("..." if len(desc) > EXCERPT else ""), ts, json.dumps([label])))
            for pid, how in _mentions(" ".join([title, desc, body, " ".join(cats)]), by_last).items():
                con.execute("INSERT OR IGNORE INTO news_player_mentions VALUES (?,?,?,?)",
                            (guid, pid, 1 if pid in _mentions(title, by_last) else 0, how))
        con.execute("UPDATE feeds SET last_fetched_at=?, last_http_status=200, last_build_date=? WHERE feed_url=?",
                    (ts, _iso(ch.findtext("lastBuildDate")), url))
        db.finish_run(con, run, True, 200, new)
        summary.append((label, new))
    con.commit()
    return summary

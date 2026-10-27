"""
見どころなう レバンガ北海道版 収集・判定プログラム（v0.6：判定ルール v1.2、好プレー・熱さの推移の記録）

やること（止めるまで動き続ける）
  1) 6時間ごと：B.LEAGUE公式の日程ページ（クラブ：レバンガ北海道）から、前後の試合を取る
  2) 試合の時間帯（開始10分前〜開始3時間後）：公式サイトが使う試合データを20秒ごとに取り、
     見どころ度を判定する。更新ごとに実際の時刻つきで保存する（学習用）
  3) 見どころ度が「高」になった瞬間：Webプッシュ（毎回）、LINE（1試合1回）で通知する
  4) data/state.json を書き、Webページ（public/index.html）を作り直す
  ※ スコアそのものはどこにも表示・配信しない

使い方
    python midokoro_daemon.py               # 常時（サーバー向け）
    python midokoro_daemon.py --until-idle  # 試合中と直前だけ動き、なければ終了（PCのタスクスケジューラ向け）
"""

import argparse
import gzip
import os
import subprocess
import html as htmllib
import json
import re
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

import midokoro_score

JST = timezone(timedelta(hours=9))
BASE = "https://www.bleague.jp"
SCHEDULE_URL = f"{BASE}/schedule/"
GAME_PAGE = f"{BASE}/game_detail/?ScheduleKey={{key}}&tab=1"
CONTEXT_URL = "http://b-league.s3.amazonaws.com/web_json/v2_genius_contexts/{key}/{name}"
HEADERS = {"User-Agent": "Mozilla/5.0 (midokoro-now personal project)"}

TEAM_ID = 702                 # レバンガ北海道
TEAM_SHORT = "北海道"          # 日程ページでの表記
LEAGUE_TAB = 1                # B.PREMIER

GAME_POLL_SECONDS = 20
IDLE_POLL_SECONDS = 60
SCHEDULE_REFRESH = timedelta(hours=6)
WINDOW_BEFORE = timedelta(minutes=10)
WINDOW_AFTER = timedelta(hours=3)
IDLE_LOOKAHEAD = timedelta(minutes=int(os.environ.get("MIDOKORO_LOOKAHEAD_MIN", "35")))
NOTIFY_COOLDOWN = timedelta(minutes=3)
DAY_SWITCH_HOUR = 5           # 5時までは前日の試合を「今日」として扱う
NEXT_COUNT = 5
REQUEST_WAIT = 1.5

PUSH_ENABLED = os.environ.get("MIDOKORO_PUSH", "1") != "0"     # GitHub版は 0（受付サーバーがない）
LIVE_API = bool(os.environ.get("MIDOKORO_API"))                  # GitHub版：「いまの熱さ」を受付窓口に置く
LIVE_HEARTBEAT = timedelta(seconds=60)                           # 変化がなくても、この間隔で置き直す（更新中だとわかるように）
PUBLISH_CMD = os.environ.get("MIDOKORO_PUBLISH_CMD", "")         # GitHub版：ページを公開するコマンド
PUBLISH_LIVE = timedelta(minutes=6)       # 試合中の公開間隔（GitHub Pagesの更新は1時間に10回まで）
PUBLISH_IDLE = timedelta(minutes=60)      # 試合がないときの公開間隔

DATA = Path("data")
STATE_FILE = DATA / "state.json"
ALERTS_FILE = DATA / "alerts.json"
WEEKDAYS = "月火水木金土日"


def now() -> datetime:
    return datetime.now(JST)


def game_day(t: datetime) -> date:
    return (t - timedelta(hours=DAY_SWITCH_HOUR)).date()


def log(msg: str) -> None:
    line = f"[{now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    DATA.mkdir(exist_ok=True)
    with (DATA / "daemon.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------- 日程（レバンガの試合だけ） ----------

def season_year(d: date) -> int:
    """日程ページの year はシーズン開始年（2026-27シーズンなら全月2026）"""
    return d.year if d.month >= 8 else d.year - 1


def schedule_html(y: int, m: int, day: int | None = None) -> str:
    params = dict(tab=LEAGUE_TAB, year=season_year(date(y, m, 1)), mon=f"{m:02d}",
                  event="", club=TEAM_ID, ha="", fb="")
    if day:
        params["day"] = f"{day:02d}"
    time.sleep(REQUEST_WAIT)
    res = requests.get(SCHEDULE_URL, headers=HEADERS, timeout=20, params=params)
    res.raise_for_status()
    return res.text


BLOCK = re.compile(r'<li class="list-item" id="(\d+)">(.*?)</li>', re.S)


def parse_games(page: str, d: date) -> list[dict]:
    out = []
    for m in BLOCK.finditer(page):
        key, b = m.group(1), m.group(2)
        names = [n.strip() for n in re.findall(r'class="team-name">([^<]+)<', b)]
        if len(names) < 2 or TEAM_SHORT not in names[:2]:
            continue
        home, away = names[0], names[1]
        info = re.search(r'class="info-arena">(.*?)</div>', b, re.S)
        spans = [s.strip() for s in re.findall(r"<span[^>]*>([^<]*)</span>", info.group(1)) if s.strip()] if info else []
        arena = next((s for s in spans if "|" in s), "")
        tm = next((s for s in spans if re.fullmatch(r"\d{1,2}:\d{2}", s)), None)
        state = re.search(r'class="info-scorestate">(.*?)</div>', b, re.S)
        final = bool(state and "FINAL" in state.group(1))
        hl = re.search(r'href="([^"]+)"[^>]*>ハイライト<', b)
        hh, mm = map(int, tm.split(":")) if tm else (0, 0)
        out.append({
            "key": key, "date": d.isoformat(),
            "start": datetime(d.year, d.month, d.day, hh, mm, tzinfo=JST),
            "time_known": bool(tm), "home": home, "away": away,
            "is_home": home == TEAM_SHORT, "opponent": away if home == TEAM_SHORT else home,
            "pref": arena.split("|")[0].strip() if arena else "",
            "final": final, "highlight": htmllib.unescape(hl.group(1)) if hl else None,
        })
    return out


_day_cache: dict[str, list[dict]] = {}   # 終わった日は取り直さない


def _month_days(y: int, m: int) -> list[int]:
    page = schedule_html(y, m)
    return sorted({int(x) for x in re.findall(r'class="js_click_data" data-day="(\d+)"', page)})


def _games_on(d: date, today: date) -> list[dict]:
    k = d.isoformat()
    if k in _day_cache and d < today:
        return _day_cache[k]
    games = parse_games(schedule_html(d.year, d.month, d.day), d)
    _day_cache[k] = games
    return games


def fetch_team_schedule(today: date) -> dict[str, dict]:
    """前回の試合・今日の試合・この先の試合（最大5試合）を集める"""
    games: dict[str, dict] = {}
    cur = today.replace(day=1)
    days = _month_days(cur.year, cur.month)
    past = [d for d in days if d < today.day]
    if past:
        last_day = date(cur.year, cur.month, past[-1])
    else:                                            # 月初は前の月の最後の試合
        prev = cur - timedelta(days=1)
        pdays = _month_days(prev.year, prev.month)
        last_day = date(prev.year, prev.month, pdays[-1]) if pdays else None
    if last_day:
        for g in _games_on(last_day, today):
            games[g["key"]] = g
    upcoming = [date(cur.year, cur.month, d) for d in days if d >= today.day]
    if len(upcoming) < NEXT_COUNT + 1:
        nxt = (cur + timedelta(days=32)).replace(day=1)
        upcoming += [date(nxt.year, nxt.month, d) for d in _month_days(nxt.year, nxt.month)]
    for d in upcoming[:NEXT_COUNT + 1]:
        for g in _games_on(d, today):
            games[g["key"]] = g
    return games


SCHEDULE_CACHE = DATA / "schedule.json"


def load_schedule_cache(t: datetime) -> dict[str, dict] | None:
    """前回の実行で取った日程（6時間以内・同じ日）を使う。GitHub版は数分おきに起動し直すため"""
    try:
        c = json.loads(SCHEDULE_CACHE.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(c["fetched"])
        if t - fetched >= SCHEDULE_REFRESH or game_day(fetched) != game_day(t):
            return None
        games = c["games"]
        for g in games.values():
            g["start"] = datetime.fromisoformat(g["start"])
        return games
    except Exception:
        return None


def save_schedule_cache(games: dict[str, dict], t: datetime) -> None:
    DATA.mkdir(exist_ok=True)
    out = {k: {**g, "start": g["start"].isoformat()} for k, g in games.items()}
    SCHEDULE_CACHE.write_text(json.dumps({"fetched": t.isoformat(), "games": out}, ensure_ascii=False), encoding="utf-8")


def in_window(g: dict, t: datetime) -> bool:
    return g["time_known"] and g["start"] - WINDOW_BEFORE <= t <= g["start"] + WINDOW_AFTER


# ---------- 試合データ（公式サイトが使うもの） ----------

_latest: dict[str, str] = {}
_changed_at: dict[str, datetime] = {}     # 公式の試合データが最後に更新された時刻（止まったことに気づくため）
_ctx_cache: dict[str, dict] = {}


def fetch_context(key: str) -> dict | None:
    """更新があったときだけ取り直す。試合前は公開されていない（403）ので None"""
    latest = requests.get(CONTEXT_URL.format(key=key, name="latestid"), headers={**HEADERS, "Cache-Control": "no-cache"},
                          params={"_": int(time.time())}, timeout=15)
    if latest.status_code != 200:
        return None
    lid = latest.text.strip()
    if _latest.get(key) == lid and key in _ctx_cache:
        return _ctx_cache[key]
    raw = requests.get(CONTEXT_URL.format(key=key, name=f"{lid}.json"), headers=HEADERS, timeout=20).content
    data = json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    _latest[key], _ctx_cache[key] = lid, data
    _changed_at[key] = now()
    d = DATA / "games" / key                # 学習用に、更新ごとの実時刻つきで保存
    d.mkdir(parents=True, exist_ok=True)
    with gzip.open(d / f"{now():%Y%m%d_%H%M%S}_{lid}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


# ---------- 見どころの記録（再起動しても残す） ----------

def load_alerts() -> dict:
    if ALERTS_FILE.exists():
        return json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
    return {}


def save_alerts(alerts: dict) -> None:
    DATA.mkdir(exist_ok=True)
    tmp = ALERTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(alerts, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ALERTS_FILE)


# ---------- 通知 ----------

def notify_web(title: str, body: str, url: str, image: str | None = None, game: dict | None = None) -> None:
    if not PUSH_ENABLED:
        return
    try:
        if os.environ.get("MIDOKORO_API"):       # GitHub版：Cloudflareの受付窓口から送る
            import push_api as webpush
        else:
            import webpush
        n = webpush.send_all(title, body, url, image, game)
        log(f"Webプッシュ送信 {n}件")
    except Exception as e:
        log(f"Webプッシュ失敗: {e}")


def notify_line(text: str) -> None:
    try:
        import line_bot
        line_bot.broadcast(text)
        log("LINE通知を送信")
    except Exception as e:
        log(f"LINE通知失敗: {e}")


_last_publish: datetime | None = None


def publish(t: datetime, live: bool, force: bool = False) -> None:
    """GitHub版：作り直したページを公開する（間隔をあけて、通知した瞬間はすぐ）"""
    global _last_publish
    if not PUBLISH_CMD:
        return
    if _last_publish is None:
        try:
            _last_publish = datetime.fromisoformat((DATA / "last_publish.txt").read_text().strip())
        except Exception:
            _last_publish = datetime.min.replace(tzinfo=JST)
    gap = PUBLISH_LIVE if live else PUBLISH_IDLE
    if not force and t - _last_publish < gap:
        return
    r = subprocess.run(PUBLISH_CMD, shell=True, capture_output=True, text=True)
    _last_publish = t
    (DATA / "last_publish.txt").write_text(t.isoformat())
    log("ページ公開" + ("" if r.returncode == 0 else f"失敗: {r.stderr.strip()[-300:]}"))


# ---------- 状態づくり ----------

def place_label(g: dict) -> str:
    return "ホーム" if g["is_home"] else (f"アウェイ（{g['pref']}）" if g["pref"] else "アウェイ")


def view(g: dict, alerts: dict, ev: dict | None, status: str) -> dict:
    d = date.fromisoformat(g["date"])
    return {
        "key": g["key"], "date": g["date"], "md": f"{d.month}/{d.day}", "wd": WEEKDAYS[d.weekday()],
        "start": f"{g['start']:%H:%M}" if g["time_known"] else "時間未定",
        "opponent": g["opponent"], "is_home": g["is_home"], "place": place_label(g),
        "url": GAME_PAGE.format(key=g["key"]), "highlight": g.get("highlight"),
        "status": status,
        "level": ev["level"] if ev else None, "meter": ev["score"] if ev else None,
        "text": ev["text"] if ev else None, "clock": ev["clock"] if ev else None,
        "alerts": alerts.get(g["key"], {}).get("items", []),
        "plays": alerts.get(g["key"], {}).get("plays", []),
        "heat": alerts.get(g["key"], {}).get("heat", []),      # 熱さの推移 [[経過秒, 見どころ度], ...]
        "tracked": bool(alerts.get(g["key"], {}).get("tracked")),
    }


def gauge_text(pct: int) -> str:
    """通知用の記号のゲージ：満タンは ▰×10、100%を超えたら炎を足す"""
    lit = min(10, max(0, pct // 10))
    return "▰" * lit + "▱" * (10 - lit) + ("🔥" if pct > 100 else "") + f" {pct}%"


class Tracker:
    def __init__(self):
        self.alerts = load_alerts()
        self.last_notify: dict[str, datetime] = {}
        self.ended: set[str] = set()
        self.notified = False
        self._heat_tried: set[str] = set()
        self._live_sent: tuple | None = None
        self._live_at: datetime | None = None
        self._stale_logged: set[str] = set()

    def status_of(self, g: dict, t: datetime, ev: dict | None) -> str:
        if g["final"] or g["key"] in self.ended:
            return "終了"
        if not g["time_known"] or t < g["start"]:
            return "予定"
        if t > g["start"] + WINDOW_AFTER:
            return "終了"
        if ev is None:
            return "まもなく" if t < g["start"] + timedelta(minutes=40) else "試合中"
        return "試合中"

    def judge(self, g: dict, t: datetime, ev: dict) -> None:
        """通知するかを midokoro_score.notify_reasons() で決めて送る
           ・満タン（「いま見て！」）：最初に満タン、残り3分・延長の各回に入って満タン、最後の1分の逆転・同点・勝ち越し
           ・激アツ（「激アツ！」）：熱さが100%を超えたとき。残り3分・延長の各回で1回まで。
             同じ試合で3分あけるきまりより優先する（満タンの直後でも送る）"""
        from site_build import SITE_URL, heat_pct
        key = g["key"]
        rec = self.alerts.setdefault(key, {"items": [], "line": False, "flags": []})
        flags = set(rec.setdefault("flags", []))
        reasons = midokoro_score.notify_reasons(flags, ev)
        rec["flags"] = sorted(flags)
        if not reasons:
            return
        self.notified = True
        geki = midokoro_score.GEKI in reasons
        pct = heat_pct(ev["score"])
        item = {"time": f"{t:%H:%M}", "clock": ev["clock"], "text": ev["headline"], "detail": ev["text"]}
        # 通知はゲージが主役：1行目に記号のゲージと熱さ、2行目に一言。Android・パソコンには同じゲージの画像も付ける
        body = f"{gauge_text(pct)}\n{ev['headline']}"
        if geki:
            item.update(kind="激アツ", pct=pct)
            title = f"激アツ！ {g['opponent']}戦"
            image = f"{SITE_URL}push-burst-{min(8, max(1, -(-(pct - 100) // 10)))}.png"
        else:
            title = f"いま見て！ {g['opponent']}戦"
            image = f"{SITE_URL}push-full.png"
        rec["items"].append(item)
        log(f"見どころ（{'・'.join(reasons)}） {g['opponent']}戦: {ev['text']}（{ev['score']}）")
        url = GAME_PAGE.format(key=key)
        if geki or key not in self.last_notify or t - self.last_notify[key] >= NOTIFY_COOLDOWN:
            self.last_notify[key] = t
            api = os.environ.get("MIDOKORO_API", "").rstrip("/")
            kind = "geki" if geki else "full"
            tap = f"{api}/api/go?g={key}&k={kind}" if api else url      # タップを数えてから公式の試合ページへ
            notify_web(title, body, tap, image, {"key": key, "date": g.get("date", ""), "opponent": g["opponent"], "kind": kind, "pct": pct})
        if not rec["line"]:
            rec["line"] = True                     # 無料枠節約のため1試合1回まで
            notify_line(f"【見どころなう】{title}\n{body}\n{url}")
        save_alerts(self.alerts)

    def post_live(self, v: dict, t: datetime) -> None:
        """今日の試合の「いまの熱さ」を受付窓口に置く（ページが20秒ごとに読む）。変化したときと、1分おきに"""
        if not LIVE_API or v["status"] not in ("試合中", "終了"):
            return
        if v["status"] == "試合中" and v["meter"] is None:
            return
        sig = (v["key"], v["status"], v["level"], v["meter"], v["clock"], v["text"])
        if sig == self._live_sent and self._live_at and t - self._live_at < LIVE_HEARTBEAT:
            return
        if v["status"] == "終了" and self._live_sent and self._live_sent[1] == "終了" and self._live_sent[0] == v["key"]:
            return                                 # 終了は1回だけ
        try:
            import push_api
            from site_build import heat_pct
            from site_build import peak_pct
            push_api.post_live({"key": v["key"], "status": v["status"], "level": v["level"] or "", "meter": v["meter"],
                                "pct": heat_pct(v["meter"]), "peak": peak_pct(v.get("heat") or [], v["meter"]),
                                "clock": v["clock"] or "", "text": v["text"] or "",
                                "opponent": v["opponent"], "url": v["url"], "at": int(t.timestamp())})
            self._live_sent, self._live_at = sig, t
        except Exception as e:
            log(f"いまの熱さを置けませんでした: {e}")

    def mark_stale(self, g: dict, t: datetime, ev: dict, pbp: list) -> dict:
        """公式の試合データが6分以上更新されていなければ、説明文でそう伝える（ハーフタイムなどピリオドの合間は除く）"""
        since = _changed_at.get(g["key"])
        last = (pbp[-1].get("PlayText") or "") if pbp else ""
        if not since or t - since < timedelta(minutes=6) or "ピリオドエンド" in last or "タイムストップ" in last and "ピリオド" in last:
            return ev
        if g["key"] not in self._stale_logged:
            self._stale_logged.add(g["key"])
            log(f"公式の試合データが {since:%H:%M} から更新されていません {g['opponent']}戦")
        return {**ev, "text": f"公式の試合データが{since:%H:%M}から更新されていません。再開すると、ゲージも動きだします。"}

    def ensure_heat(self, g: dict) -> None:
        """終わった試合の熱さの推移がまだなければ、試合データから計算して残す（見どころなうが動いていなかった試合も）"""
        key = g["key"]
        rec = self.alerts.get(key) or {}
        # 試合終了まで入った推移があれば済み。途中で公式の試合データが止まった試合は、あとから全部そろうので1時間ごとに取り直す（3日まで）
        if rec.get("complete") or rec.get("heat_none") or rec.get("heat_tries", 0) >= 3 or key in self._heat_tried:
            return
        if date.fromisoformat(g["date"]) < game_day(now()) - timedelta(days=3):
            return
        self._heat_tried.add(key)
        try:
            ctx = fetch_context(key)
        except Exception as e:
            log(f"熱さの推移：試合データ取得失敗 {key}: {e}")
            ctx = None
        rec = self.alerts.setdefault(key, {"items": [], "line": False, "flags": []})
        pbp = (ctx or {}).get("PlayByPlays") or []
        try:
            heat = midokoro_score.heat_curve(pbp, g["is_home"]) if pbp else []
        except Exception as e:
            log(f"熱さの推移の計算失敗 {key}: {e}")
            heat = []
        if heat:
            rec["heat"] = heat
            rec["plays"] = midokoro_score.good_plays(pbp, g["is_home"])
            rec["complete"] = any(p.get("GameEndRowFlg") or "試合終了" in (p.get("PlayText") or "") for p in pbp)
            log(f"熱さの推移を計算 {g['opponent']}戦（{len(heat)}点）")
        elif ctx is not None:
            rec["heat_none"] = True               # データはあるがプレー記録がない
        else:
            rec["heat_tries"] = rec.get("heat_tries", 0) + 1
        save_alerts(self.alerts)

    def update(self, games: dict[str, dict], t: datetime) -> list[str]:
        today = game_day(t)
        live = [g for g in games.values() if in_window(g, t) and g["key"] not in self.ended and not g["final"]]
        evs: dict[str, dict | None] = {}
        for g in live:
            try:
                ctx = fetch_context(g["key"])
                pbp = (ctx or {}).get("PlayByPlays") or []
                ev = midokoro_score.evaluate(pbp, g["is_home"])
                if pbp:
                    plays = midokoro_score.good_plays(pbp, g["is_home"])
                    rec = self.alerts.setdefault(g["key"], {"items": [], "line": False, "flags": []})
                    changed = False
                    if plays != rec.get("plays"):
                        rec["plays"] = plays            # 好プレー（通知はしない。ページとLINE返信に並べる）
                        changed = True
                    try:
                        heat = midokoro_score.heat_curve(pbp, g["is_home"])   # 熱さの推移（ページのグラフ用）
                        if heat != rec.get("heat"):
                            rec["heat"], changed = heat, True
                    except Exception as e:
                        log(f"熱さの推移の計算失敗 {g['key']}: {e}")
                    if changed:
                        save_alerts(self.alerts)
            except Exception as e:
                log(f"試合データ取得失敗 {g['key']}: {e}")
                ev = None
            if ev and ev["level"] == "終了":
                self.ended.add(g["key"])
                log(f"試合終了 {g['opponent']}戦")
                ev = None
            elif ev:
                ev = self.mark_stale(g, t, ev, pbp)
                rec = self.alerts.setdefault(g["key"], {"items": [], "line": False, "flags": []})
                if not rec.get("tracked"):
                    rec["tracked"] = True          # この試合を見ていた印（「見どころなし」と言ってよいか）
                    save_alerts(self.alerts)
                self.judge(g, t, ev)
            evs[g["key"]] = ev

        ordered = sorted(games.values(), key=lambda g: g["start"])
        todays = [g for g in ordered if date.fromisoformat(g["date"]) == today]
        future = [g for g in ordered if date.fromisoformat(g["date"]) > today]
        past = [g for g in ordered if date.fromisoformat(g["date"]) < today]
        cur = todays[0] if todays else None
        done = ([past[-1]] if past else []) + ([cur] if cur and self.status_of(cur, t, evs.get(cur["key"])) == "終了" else [])
        for g in done:
            self.ensure_heat(g)
        state = {
            "updated": f"{t:%Y-%m-%d %H:%M}",
            "today": view(cur, self.alerts, evs.get(cur["key"]), self.status_of(cur, t, evs.get(cur["key"]))) if cur else None,
            "next": [view(g, self.alerts, None, "予定") for g in future[:NEXT_COUNT]],
            "last": view(past[-1], self.alerts, None, "終了") if past else None,
        }
        if state["today"]:
            self.post_live(state["today"], t)
        DATA.mkdir(exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(STATE_FILE)
        try:
            import site_build
            site_build.build()
        except Exception as e:
            log(f"サイト更新失敗: {e}")
        still = [g["key"] for g in live if g["key"] not in self.ended]
        publish(t, bool(still), force=self.notified or (bool(live) and not still))
        self.notified = False
        return still


# ---------- メインループ ----------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--until-idle", action="store_true",
                    help="試合中と直前だけ動き、試合がなくなったら終了する（タスクスケジューラ用）")
    ap.add_argument("--max-minutes", type=int, default=0, help="この分数で終了する（GitHub Actionsの時間制限用）")
    args = ap.parse_args()
    until_idle = args.until_idle
    started = now()
    log("レバンガ北海道版を開始" + ("（試合がなくなったら終了）" if until_idle else "（常時）"))
    tracker = Tracker()
    games: dict[str, dict] = {}
    last_schedule = None
    was_live = False
    first_load = True                       # 起動直後だけ、前回の日程の控えを使ってよい

    while True:
        t = now()
        live: list[str] = []
        try:
            stale = last_schedule is None or t - last_schedule >= SCHEDULE_REFRESH \
                or game_day(last_schedule) != game_day(t)
            if stale and not was_live:
                cached = load_schedule_cache(t) if first_load else None
                first_load = False
                if cached is not None:
                    games = cached
                else:
                    games = fetch_team_schedule(game_day(t))
                    save_schedule_cache(games, t)
                last_schedule = t
                log("日程更新: " + ", ".join(f"{g['date'][5:]} {g['start']:%H:%M} {g['opponent']}"
                                            for g in sorted(games.values(), key=lambda g: g["start"])))
            live = tracker.update(games, t)
            if was_live and not live:
                last_schedule = None               # 試合が終わったら日程を取り直す（ハイライト動画のリンク用）
            was_live = bool(live)
        except Exception:
            log("予期しないエラー\n" + traceback.format_exc())

        if until_idle and not live:
            soon = [g for g in games.values()
                    if g["time_known"] and t < g["start"] - WINDOW_BEFORE <= t + IDLE_LOOKAHEAD]
            if not soon:
                log("試合中・直前の試合がないため終了")
                return
        if args.max_minutes and now() - started >= timedelta(minutes=args.max_minutes):
            log("実行時間の上限のため終了")
            publish(now(), False, force=True)
            return
        time.sleep(GAME_POLL_SECONDS if live else IDLE_POLL_SECONDS)


if __name__ == "__main__":
    main()

"""
見どころなう レバンガ北海道版 Webページ生成
data/state.json を読んで public/index.html を作る（収集プログラムが毎回呼ぶ）。

デザイン
  トップは「今、見るべき？」への答えを大きく出す（いま見て！／そろそろ／まだ大丈夫／次の試合の日付）。
  見どころ度が「高」になったときだけ、トップ全体がレバンガの黄緑（#8FC31F）に変わる。
  書体は見出しに Dela Gothic One、本文に BIZ UDPゴシック。
  公式ロゴ・マスコット・写真は使わない。スコアは載せない。非公式であることを明記する。
"""

import html
import json
import os
import shutil
from pathlib import Path

STATE_FILE = Path("data/state.json")
OUT_DIR = Path("public")
STATIC_DIR = Path("static")
TEAM = "レバンガ北海道"

CSS = """
:root{
  --lime:#8FC31F; --pine:#14290F; --snow:#F6F8F1; --frost:#DDE6D0; --moss:#56664F;
  --bg:var(--snow); --ink:var(--pine); --sub:var(--moss); --line:var(--frost);
  --btn-bg:var(--pine); --btn-ink:var(--snow); --empty:#CFDAC0;
  --display:"Dela Gothic One","Hiragino Sans","Noto Sans JP",sans-serif;
  --body:"BIZ UDPGothic","Hiragino Sans","Noto Sans JP",sans-serif;
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#0D1A0B; --ink:#E8F0DD; --sub:#9AAA90; --line:#24361F;
         --btn-bg:#8FC31F; --btn-ink:#14290F; --empty:#2C4226; }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body);
     font-size:16px;line-height:1.75}
a{color:inherit}
.wrap{max-width:560px;margin:0 auto;padding:0 20px}
:focus-visible{outline:3px solid var(--lime);outline-offset:3px;border-radius:4px}

header.site{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;padding-top:20px;padding-bottom:4px}
.mark{font-family:var(--display);font-size:22px;letter-spacing:.02em;margin:0;font-weight:400}
.edition{font-size:13px;color:var(--sub)}

.hero{margin-top:14px;padding:28px 0 32px;border-top:6px solid var(--lime)}
.hero .ctx{margin:0;font-size:14px;color:var(--sub)}
.hero .word{margin:6px 0 4px;font-family:var(--display);font-weight:400;
            font-size:clamp(46px,15vw,84px);line-height:1.08;letter-spacing:0}
.hero .say{margin:0;font-size:17px;max-width:32em}
.hero .word .wd{font-family:var(--body);font-weight:700;font-size:.34em;margin-left:.35em;white-space:nowrap}
.hero.hot{background:var(--lime);color:var(--pine);border-top-color:var(--lime)}
.hero.hot .ctx{color:var(--pine)}
.hero.hot:not(.still){animation:flood .7s cubic-bezier(.2,.7,.2,1) both}
@keyframes flood{from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0 0 0)}}
@media (prefers-reduced-motion:reduce){.hero.hot{animation:none}}

.btn{display:inline-flex;align-items:center;justify-content:center;min-height:48px;padding:0 20px;
     border-radius:6px;border:0;background:var(--btn-bg);color:var(--btn-ink);font:inherit;
     font-weight:700;text-decoration:none;cursor:pointer}
.btn.quiet{background:transparent;color:var(--ink);box-shadow:inset 0 0 0 2px var(--sub)}
.hero .btn{margin-top:20px}
.hero.hot .btn{background:var(--pine);color:var(--lime)}

.meter{display:flex;align-items:center;gap:12px;margin-top:22px;font-size:13px;color:var(--sub)}
.hero.hot .meter{color:var(--pine)}
.bars{display:grid;grid-template-columns:repeat(10,1fr);gap:4px;flex:1;max-width:260px}
.bars i{height:12px;border-radius:2px;background:var(--empty)}
.bars i.on{background:var(--lime)}
.hero.hot .bars i{background:rgba(20,41,15,.18)}
.hero.hot .bars i.on{background:var(--pine)}

section{padding:28px 0 4px}
section h2{margin:0 0 10px;font-family:var(--display);font-weight:400;font-size:19px}
.note{margin:0;color:var(--sub);font-size:14px}
ol.moments,ul.games{list-style:none;margin:0;padding:0}
h3.sub{font-size:14px;margin:22px 0 4px;color:var(--sub);font-weight:700}
ol.moments li{display:grid;grid-template-columns:92px 1fr auto;gap:12px;align-items:baseline;
              padding:12px 0;border-top:1px solid var(--line)}
.clock{font-family:var(--display);font-size:15px;white-space:nowrap}
.when{font-size:13px;color:var(--sub)}
ul.games li{display:grid;grid-template-columns:76px 1fr auto;gap:12px;align-items:baseline;
            padding:12px 0;border-top:1px solid var(--line)}
.day{font-family:var(--display);font-size:17px;line-height:1.3}
.day small{display:block;font-family:var(--body);font-size:12px;color:var(--sub)}
.opp{font-weight:700}
.opp small{display:block;font-weight:400;font-size:13px;color:var(--sub)}
.start{font-family:var(--display);font-size:16px}
.links{margin-top:14px;display:flex;gap:10px;flex-wrap:wrap}
.notify .row{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
.notify .btn[hidden]{display:none}
footer{padding:40px 0 48px;font-size:12px;color:var(--sub)}
footer p{margin:0 0 6px}
"""

SCRIPT = r"""
(() => {
  // 30秒ごとに試合の部分だけ新しくする（ページ全体は読み直さない）
  async function refresh() {
    if (document.hidden) return;
    try {
      const r = await fetch(location.pathname, { cache: "no-store" });
      const doc = new DOMParser().parseFromString(await r.text(), "text/html");
      const fresh = doc.getElementById("live"), cur = document.getElementById("live");
      if (!fresh || !cur || fresh.innerHTML === cur.innerHTML) return;
      const wasHot = !!cur.querySelector(".hero.hot");
      cur.replaceWith(fresh);
      const hot = fresh.querySelector(".hero.hot");
      if (hot && wasHot) hot.classList.add("still");
      document.title = doc.title;
    } catch (e) {}
  }
  setInterval(refresh, 30000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
})();

(async () => {
  const msg = document.getElementById("np"), btn = document.getElementById("nb");
  if (!msg || !btn) return;
  const API = "";
  const viaLine = msg.dataset.line === "1" ? "LINEで受け取れます。" : "";
  const ios = /iPhone|iPad|iPod/.test(navigator.userAgent);
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    msg.textContent = ios && !standalone
      ? "iPhoneは、共有ボタンから「ホーム画面に追加」して開くと通知を受け取れます。"
      : "このブラウザは通知に対応していません。" + viaLine;
    return;
  }
  let reg;
  try { reg = await navigator.serviceWorker.register("sw.js"); }
  catch (e) { msg.textContent = "このページでは通知を設定できません。" + viaLine; return; }
  const b64 = (s) => {
    const raw = atob((s + "=".repeat((4 - s.length % 4) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, (c) => c.charCodeAt(0));
  };
  const post = (path, sub) => fetch(path, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(sub) });
  const show = (on) => {
    btn.hidden = false;
    btn.textContent = on ? "この端末の通知を止める" : "この端末に通知する";
    btn.classList.toggle("quiet", on);
    msg.textContent = on ? "通知はオンです。見どころが来た瞬間にお知らせします。"
                         : "見どころが来た瞬間に、この端末へお知らせします。";
  };
  let sub = await reg.pushManager.getSubscription();
  show(!!sub);
  btn.onclick = async () => {
    btn.disabled = true;
    try {
      if (sub) {
        await post(API + "/api/unsubscribe", sub); await sub.unsubscribe(); sub = null;
      } else {
        if (await Notification.requestPermission() !== "granted") {
          msg.textContent = "通知が許可されていません。ブラウザの設定で、このサイトの通知を許可してください。";
          return;
        }
        const { key } = await (await fetch(API + "/api/vapid")).json();
        sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(key) });
        if (!(await post(API + "/api/subscribe", sub)).ok) throw new Error("subscribe");
      }
      show(!!sub);
    } catch (e) {
      msg.textContent = "通知を設定できませんでした。時間をおいて、もう一度押してください。";
    } finally { btn.disabled = false; }
  };
})();
"""

e = html.escape


def _meter(score: int | None) -> str:
    if score is None:
        return ""
    on = max(0, min(10, round(score / 10)))
    bars = "".join(f'<i class="on"></i>' if i < on else "<i></i>" for i in range(10))
    return (f'<div class="meter"><span>見どころ度</span>'
            f'<div class="bars" role="img" aria-label="見どころ度 10段階中{on}">{bars}</div></div>')


def _btn(label: str, url: str | None, quiet: bool = False) -> str:
    if not url:
        return ""
    cls = "btn quiet" if quiet else "btn"
    return f'<a class="{cls}" href="{e(url)}" target="_blank" rel="noopener">{e(label)}</a>'


def _until(updated: str | None, g: dict) -> str:
    """「3時間5分」のような開始までの残り時間"""
    from datetime import datetime
    try:
        now_ = datetime.strptime(updated, "%Y-%m-%d %H:%M")
        start = datetime.strptime(f'{g["date"]} {g["start"]}', "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return ""
    mins = int((start - now_).total_seconds() // 60)
    if mins <= 0:
        return ""
    h, m = divmod(mins, 60)
    return f"{h}時間{m}分" if h else f"{m}分"


def hero(state: dict) -> tuple[str, str]:
    """（HTML, ページタイトル）"""
    g = state.get("today")
    title = "見どころなう｜レバンガ北海道版"
    vs = lambda x: f"vs {x['opponent']}　{x['place']}"
    if g and g["status"] == "試合中":
        lv, clock = g.get("level"), g.get("clock")
        ctx = f"試合中　{clock}　vs {g['opponent']}" if clock else f"試合中　vs {g['opponent']}"
        if lv == "高":
            return (f'<div class="hero hot"><div class="wrap"><p class="ctx">{e(ctx)}</p>'
                    f'<h2 class="word">いま見て！</h2><p class="say">{e(g["text"] or "")}</p>'
                    f'{_meter(g["meter"])}{_btn("試合を見る（B.LEAGUE公式）", g["url"])}</div></div>',
                    "いま見て！｜見どころなう")
        if lv == "中":
            word, say = "そろそろ", g["text"] or "盛り上がってきました。"
        else:
            word, say = "まだ大丈夫", "見どころが来たら、すぐにお知らせします。"
        return (f'<div class="hero"><div class="wrap"><p class="ctx">{e(ctx)}</p>'
                f'<h2 class="word">{word}</h2><p class="say">{e(say)}</p>'
                f'{_meter(g["meter"])}{_btn("試合を見る（B.LEAGUE公式）", g["url"], quiet=True)}</div></div>', title)
    if g and g["status"] == "まもなく":
        return (f'<div class="hero"><div class="wrap"><p class="ctx">今日　{e(vs(g))}</p>'
                f'<h2 class="word">まもなく</h2><p class="say">{e(g["start"])}に試合開始です。見どころが来たらお知らせします。</p>'
                f'</div></div>', title)
    if g and g["status"] == "予定":
        left = _until(state.get("updated"), g)
        say = f"試合開始まで、あと{left}。始まったら、見どころをお知らせします。" if left else "始まったら、見どころをお知らせします。"
        return (f'<div class="hero"><div class="wrap"><p class="ctx">今日　{e(vs(g))}</p>'
                f'<h2 class="word">{e(g["start"])}</h2><p class="say">{e(say)}</p>'
                f'</div></div>', title)
    if g and g["status"] == "終了":
        n = len(g["alerts"])
        say = f"見どころは{n}回ありました。" if n else "通知するほどの場面はありませんでした。"
        link = _btn("ハイライト動画を見る", g.get("highlight")) or _btn("試合の記録を見る（B.LEAGUE公式）", g["url"], quiet=True)
        return (f'<div class="hero"><div class="wrap"><p class="ctx">今日　{e(vs(g))}</p>'
                f'<h2 class="word">試合終了</h2><p class="say">{e(say)}</p>{link}</div></div>', title)
    nxt = (state.get("next") or [None])[0]
    if nxt:
        return (f'<div class="hero"><div class="wrap"><p class="ctx">次の試合　{e(vs(nxt))}</p>'
                f'<h2 class="word">{e(nxt["md"])}<span class="wd">{e(nxt["wd"])}曜日</span></h2>'
                f'<p class="say">{e(nxt["start"])}開始。始まったら、見どころをお知らせします。</p></div></div>', title)
    return ('<div class="hero"><div class="wrap"><p class="ctx">次の試合</p>'
            '<h2 class="word">日程待ち</h2><p class="say">次の試合が決まったら、ここに表示します。</p></div></div>', title)


def moments(state: dict) -> str:
    g = state.get("today")
    if g and g["status"] in ("試合中", "終了", "まもなく"):
        head, items, empty = "今日の見どころ", g["alerts"], "見どころが来たら、ここに残ります。"
        extra = ""
    elif state.get("last"):
        g = state["last"]
        extra = _btn("ハイライト動画を見る", g.get("highlight"), quiet=True)
        extra = f'<div class="links">{extra}</div>' if extra else ""
        if not g.get("tracked"):            # 見どころなうが動いていなかった試合
            if not extra:
                return ""
            return f'<section><div class="wrap"><h2>前回の試合　{e(g["md"])} {e(g["opponent"])}戦</h2>{extra}</div></section>'
        head = f"前回の見どころ　{g['md']} {g['opponent']}戦"
        items, empty = g["alerts"], "前回の試合は、通知するほどの場面はありませんでした。"
    else:
        return ""
    if items:
        rows = "".join(f'<li><span class="clock">{e(a.get("clock", ""))}</span>'
                       f'<span>{e(a["text"])}</span><span class="when">{e(a["time"])}</span></li>' for a in items)
        body = f'<ol class="moments">{rows}</ol>'
    else:
        body = f'<p class="note">{e(empty)}</p>'
    plays = g.get("plays") or []
    if plays:                                # レバンガの好プレー（通知はしない記録）。新しい順に最大12件
        rows = "".join(f'<li><span class="clock">{e(p["clock"])}</span><span>{e(p["text"])}</span><span></span></li>'
                       for p in plays[::-1][:12])
        more = f'<p class="note">ほか{len(plays) - 12}件。ハイライト動画でまとめて見られます。</p>' if len(plays) > 12 else ""
        body += f'<h3 class="sub">レバンガの好プレー</h3><ol class="moments">{rows}</ol>{more}'
    return f'<section><div class="wrap"><h2>{e(head)}</h2>{body}{extra}</div></section>'


def upcoming(state: dict) -> str:
    games = state.get("next") or []
    if not state.get("today") and games:   # 次の試合はトップに大きく出しているので、一覧は2試合目から
        games = games[1:]
    if not games:
        return ""
    rows = "".join(
        f'<li><span class="day">{e(g["md"])}<small>{e(g["wd"])}曜日</small></span>'
        f'<span class="opp">vs {e(g["opponent"])}<small>{e(g["place"])}</small></span>'
        f'<span class="start">{e(g["start"])}</span></li>' for g in games)
    return f'<section><div class="wrap"><h2>この先の試合</h2><ul class="games">{rows}</ul></div></section>'


PUSH_ENABLED = os.environ.get("MIDOKORO_PUSH", "1") != "0"   # GitHub版（受付サーバーなし）は 0


def notify_block() -> str:
    line_url = os.environ.get("LINE_ADD_URL", "").strip()
    if not PUSH_ENABLED:                       # Webプッシュなし：LINEだけで受け取る
        line = _btn("LINEで受け取る", line_url) if line_url else ""
        say = ("試合が盛り上がったら、LINEでお知らせします（1試合1回）。このページは数分おきに更新されます。"
               if line_url else "このページは数分おきに更新されます。")
        return ('<section class="notify"><div class="wrap"><h2>通知を受け取る</h2>'
                f'<p class="note">{e(say)}</p><div class="row">{line}</div></div></section>')
    line = _btn("LINEで受け取る", line_url, quiet=True) if line_url else ""
    return ('<section class="notify"><div class="wrap"><h2>通知を受け取る</h2>'
            f'<p class="note" id="np" data-line="{1 if line_url else 0}">見どころが来た瞬間に、この端末へお知らせします。</p>'
            f'<div class="row"><button class="btn" id="nb" hidden>この端末に通知する</button>{line}</div>'
            '</div></section>')


PAGE = """<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="レバンガ北海道の試合が盛り上がった瞬間をお知らせする、非公式のファンサービスです。">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icon-180.png">
<meta name="theme-color" content="#8FC31F">
<meta name="apple-mobile-web-app-capable" content="yes">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=BIZ+UDPGothic:wght@400;700&family=Dela+Gothic+One&display=swap">
<style>{css}</style>
</head>
<body>
<header class="site wrap"><h1 class="mark">見どころなう</h1><span class="edition">レバンガ北海道版（非公式）</span></header>
<main>
<div id="live">{hero}{moments}</div>
{notify}
{upcoming}
</main>
<footer class="wrap">
<p>レバンガ北海道を応援する個人の非公式サービスです。B.LEAGUE・レバンガ北海道とは関係ありません。</p>
<p>試合の映像と記録はB.LEAGUE公式でご覧ください。見どころの判定は試験運用中です。</p>
<p>最終更新 {updated}</p>
</footer>
<script>{script}</script>
</body></html>
"""


def render(state: dict) -> str:
    hero_html, title = hero(state)
    return PAGE.format(title=e(title), css=CSS, hero=hero_html, moments=moments(state),
                       notify=notify_block(), upcoming=upcoming(state),
                       updated=e(state.get("updated", "-")), script=SCRIPT)


def build() -> Path:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    OUT_DIR.mkdir(exist_ok=True)
    for f in STATIC_DIR.glob("*"):                 # 通知用の部品とアイコンをコピー
        dst = OUT_DIR / f.name
        if f.is_file() and (not dst.exists() or dst.stat().st_mtime < f.stat().st_mtime):
            shutil.copy2(f, dst)
    out = OUT_DIR / "index.html"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(render(state), encoding="utf-8")
    tmp.replace(out)
    return out


if __name__ == "__main__":
    print(build())

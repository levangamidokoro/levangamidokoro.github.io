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
  --btn-bg:var(--pine); --btn-ink:var(--snow); --empty:#CFDAC0; --card:#FFFFFF; --panel:#FFFFFF;
  --display:"Dela Gothic One","Hiragino Sans","Noto Sans JP",sans-serif;
  --body:"BIZ UDPGothic","Hiragino Sans","Noto Sans JP",sans-serif;
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#0D1A0B; --ink:#E8F0DD; --sub:#9AAA90; --line:#24361F;
         --btn-bg:#8FC31F; --btn-ink:#14290F; --empty:#2C4226; --card:#122310; --panel:#122310; }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body);
     font-size:16px;line-height:1.75;overflow-x:hidden}
a{color:inherit}
.wrap{max-width:560px;margin:0 auto;padding:0 16px}
:focus-visible{outline:3px solid var(--lime);outline-offset:3px;border-radius:4px}

/* ヘッダー */
header.site{display:flex;align-items:center;gap:10px;padding-top:14px;padding-bottom:14px}
.brand{display:flex;flex-direction:column;line-height:1.25}
.mark{font-family:var(--display);font-size:21px;letter-spacing:.02em;margin:0;font-weight:400;white-space:nowrap}
.edition{font-size:11px;font-weight:700;color:var(--sub);white-space:nowrap}
header.site .go{margin-left:auto;font-size:13px;font-weight:700;text-decoration:none;padding:6px 12px;
                border-radius:999px;background:var(--lime);color:var(--pine);white-space:nowrap}

/* トップ（試合の状態）：ポスターのように暗い地に黄緑の大文字 */
.hero{position:relative;overflow:hidden;background:var(--pine);color:var(--snow);padding:30px 0 34px}
.hero .court{position:absolute;right:-90px;top:-40px;width:360px;height:360px;opacity:.13;pointer-events:none}
.hero .wrap{position:relative}
.chip{display:inline-block;font-size:13px;font-weight:700;padding:3px 10px;border-radius:999px;
      background:var(--lime);color:var(--pine);margin-right:8px}
.chip.live::before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;background:#E03C31;margin-right:6px;vertical-align:1px;animation:blink 1.2s steps(2) infinite}
@keyframes blink{50%{opacity:0}}
.hero .ctx{margin:0;font-size:14px;color:#C9D6BC}
.hero .word{margin:12px 0 6px;font-family:var(--display);font-weight:400;color:var(--lime);
            font-size:clamp(52px,17vw,96px);line-height:1.02;letter-spacing:0}
.hero .say{margin:0;font-size:17px;max-width:32em}
.hero .word .wd{font-family:var(--body);font-weight:700;font-size:.3em;margin-left:.35em;white-space:nowrap;color:var(--snow)}
.hero.hot{background:var(--lime);color:var(--pine)}
.hero.hot .word{color:var(--pine)}
.hero.hot .ctx{color:var(--pine)}
.hero.hot .chip{background:var(--pine);color:var(--lime)}
.hero.hot .court{opacity:.18}
.hero.hot:not(.still){animation:flood .7s cubic-bezier(.2,.7,.2,1) both}
@keyframes flood{from{clip-path:inset(0 100% 0 0)}to{clip-path:inset(0 0 0 0)}}

.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:52px;padding:0 22px;
     border-radius:999px;border:0;background:var(--btn-bg);color:var(--btn-ink);font:inherit;
     font-weight:700;text-decoration:none;cursor:pointer}
.btn.quiet{background:transparent;color:var(--ink);box-shadow:inset 0 0 0 2px var(--sub)}
.btn.big{width:100%;min-height:60px;font-size:18px;background:var(--lime);color:var(--pine);
         box-shadow:0 6px 0 #5E8410;transition:transform .08s,box-shadow .08s}
.btn.big:active{transform:translateY(4px);box-shadow:0 2px 0 #5E8410}
.btn.big.quiet{background:transparent;color:var(--ink);box-shadow:inset 0 0 0 2px var(--sub)}
.btn:disabled{opacity:.6}
.hero .btn{margin-top:20px;background:var(--lime);color:var(--pine)}
.hero .btn.quiet{background:transparent;color:var(--snow);box-shadow:inset 0 0 0 2px #C9D6BC}
.hero.hot .btn{background:var(--pine);color:var(--lime)}

.meter{display:flex;align-items:center;gap:12px;margin-top:22px;font-size:13px;color:#C9D6BC}
.hero.hot .meter{color:var(--pine)}
.bars{display:grid;grid-template-columns:repeat(10,1fr);gap:4px;flex:1;max-width:260px}
.bars i{height:12px;border-radius:2px;background:rgba(246,248,241,.16)}
.bars i.on{background:var(--lime)}
.hero.hot .bars i{background:rgba(20,41,15,.18)}
.hero.hot .bars i.on{background:var(--pine)}

/* 広告ブロック：キャッチ→スマホの実物イメージ→ボタン */
.pitch{padding:36px 0 8px}
.kicker{margin:0 0 6px;font-size:13px;font-weight:700;color:var(--sub);letter-spacing:.04em}
.hook{margin:0;font-family:var(--display);font-weight:400;font-size:clamp(30px,8.4vw,44px);line-height:1.3}
.hook mark{background:linear-gradient(transparent 58%,var(--lime) 58%);color:inherit;padding:0 .05em}
.hook-sub{margin:12px 0 0;font-size:16px;color:var(--sub)}
.phone{position:relative;width:250px;height:300px;margin:26px auto 0;border-radius:36px 36px 0 0;
       background:#0B160A;padding:14px 12px 0;box-shadow:0 0 0 7px #24361F,0 18px 40px rgba(20,41,15,.28);
       overflow:hidden;transform:rotate(-3deg)}
.phone .tm{margin:14px 0 0;text-align:center;font-family:var(--display);font-size:46px;color:#E8F0DD;line-height:1}
.phone .dt{margin:4px 0 18px;text-align:center;font-size:12px;color:#9AAA90}
.toast{display:grid;grid-template-columns:34px 1fr;gap:2px 10px;padding:11px 12px;border-radius:16px;
       background:rgba(246,248,241,.94);color:var(--pine);font-size:13px;line-height:1.5;
       animation:drop 3.2s cubic-bezier(.2,.8,.2,1) infinite}
.toast .ic{grid-row:span 3;width:34px;height:34px;border-radius:9px;background:var(--lime);
           display:grid;place-items:center;font-family:var(--display);font-size:13px;color:var(--pine)}
.toast .ap{font-size:11px;color:var(--moss)}
.toast b{font-size:14px}
.toast.two{margin-top:8px;opacity:.55;animation:none}
@keyframes drop{0%{transform:translateY(-130%);opacity:0}12%,88%{transform:none;opacity:1}100%{transform:none;opacity:1}}
@media (prefers-reduced-motion:reduce){.toast,.chip.live::before,.hero.hot{animation:none!important}}
.cta{position:relative;margin-top:-6px;padding:22px 18px 18px;border-radius:20px;background:var(--panel);
     box-shadow:0 0 0 1px var(--line),0 10px 30px rgba(20,41,15,.10)}
.badges{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 14px;padding:0;list-style:none}
.badges li{font-size:13px;font-weight:700;padding:4px 10px;border-radius:999px;background:var(--bg);box-shadow:inset 0 0 0 1px var(--line)}
.badges li::before{content:"✓ ";color:#3F7A1A}
@media (prefers-color-scheme: dark){.badges li::before{color:var(--lime)}}
.cta .note{margin-top:10px;text-align:center}
.cta .row{display:grid;gap:10px}
.notify .btn[hidden]{display:none}

/* 数字の裏付け */
.proof{padding:34px 0 4px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0 6px}
.stat{padding:14px 8px 12px;border-radius:14px;background:var(--pine);color:var(--snow);text-align:center}
.stat b{display:block;font-family:var(--display);font-weight:400;font-size:clamp(24px,7.4vw,34px);line-height:1.1;color:var(--lime)}
.stat b small{font-family:var(--body);font-weight:700;font-size:.5em;color:var(--snow);margin-left:2px}
.stat span{display:block;margin-top:6px;font-size:12px;line-height:1.45}
.fine{margin:4px 0 0;font-size:12px;color:var(--sub)}

/* 3ステップ */
ol.steps{list-style:none;margin:12px 0 0;padding:0;display:grid;gap:10px;counter-reset:s}
ol.steps li{counter-increment:s;display:grid;grid-template-columns:44px 1fr;gap:12px;align-items:center;
            padding:12px 14px;border-radius:14px;background:var(--panel);box-shadow:0 0 0 1px var(--line)}
ol.steps li::before{content:counter(s);display:grid;place-items:center;width:44px;height:44px;border-radius:50%;
            background:var(--lime);color:var(--pine);font-family:var(--display);font-size:20px}
ol.steps b{display:block}
ol.steps span{font-size:14px;color:var(--sub)}

section{padding:30px 0 4px}
section h2{margin:0 0 10px;font-family:var(--display);font-weight:400;font-size:22px;line-height:1.4}
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

/* 画面下に追従するボタン */
.sticky{position:fixed;left:12px;right:12px;bottom:12px;z-index:10;max-width:536px;margin:0 auto;
        display:flex;align-items:center;justify-content:center;min-height:56px;border-radius:999px;
        background:var(--lime);color:var(--pine);font-weight:700;font-size:17px;text-decoration:none;
        box-shadow:0 8px 24px rgba(20,41,15,.35);transform:translateY(140%);visibility:hidden;transition:transform .25s,visibility 0s .25s}
.sticky.show{transform:none;visibility:visible;transition:transform .25s}
.sticky small{font-weight:400;font-size:12px;margin-left:8px}
footer{padding:40px 0 96px;font-size:12px;color:var(--sub)}
footer p{margin:0 0 6px}
"""

SCRIPT = r"""
(() => {
  // 30秒ごとに試合の部分（data-live）だけ新しくする（ページ全体は読み直さない）
  async function refresh() {
    if (document.hidden) return;
    try {
      const r = await fetch(location.pathname, { cache: "no-store" });
      const doc = new DOMParser().parseFromString(await r.text(), "text/html");
      for (const fresh of doc.querySelectorAll("[data-live]")) {
        const cur = document.getElementById(fresh.id);
        if (!cur || fresh.innerHTML === cur.innerHTML) continue;
        const wasHot = !!cur.querySelector(".hero.hot");
        cur.replaceWith(fresh);
        const hot = fresh.querySelector(".hero.hot");
        if (hot && wasHot) hot.classList.add("still");
      }
      document.title = doc.title;
    } catch (e) {}
  }
  setInterval(refresh, 30000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
})();

(async () => {
  const msg = document.getElementById("np"), btn = document.getElementById("nb");
  if (!msg || !btn) return;
  window.__midokoroPush = true;
  const API = document.body.dataset.api || "";
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
    btn.textContent = on ? "この端末の通知を止める" : "無料で通知を受け取る";
    btn.classList.toggle("quiet", on);
    msg.textContent = on ? "通知はオンです。見どころが来た瞬間にお知らせします。"
                         : "押すと通知の許可を聞かれます。「許可」を選べば完了です。";
    window.__midokoroOn = on; window.dispatchEvent(new Event("midokoro"));
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

(() => {
  // 画面下の追従ボタン：通知がまだオフで、申し込み欄が見えていないときだけ出す
  const bar = document.getElementById("sticky"), box = document.getElementById("notify");
  if (!bar || !box) return;
  let inView = true;
  const update = () => {
    const want = bar.dataset.mode === "line" || (window.__midokoroPush && window.__midokoroOn === false);
    bar.classList.toggle("show", !!want && !inView && scrollY > 120);
    bar.tabIndex = bar.classList.contains("show") ? 0 : -1;
  };
  if ("IntersectionObserver" in window)
    new IntersectionObserver((es) => { inView = es[0].isIntersecting; update(); }).observe(box);
  addEventListener("scroll", update, { passive: true });
  addEventListener("midokoro", update);
  update();
})();
"""

# アクセス数を1回数える（Cookieなし。数えるのは表示回数と、日ごとのおおよその訪問者数だけ）
BEACON = """<script>try{navigator.sendBeacon(document.body.dataset.api+"/api/hit",new Blob(["{}"],{type:"text/plain"}))}catch(e){}</script>"""

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


# 背景のコート線（一般的な図形。公式の意匠は使わない）
COURT = ('<svg class="court" viewBox="0 0 200 200" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="3">'
         '<circle cx="100" cy="100" r="96"/><circle cx="100" cy="100" r="30"/>'
         '<path d="M4 100H196"/><path d="M40 4v40a60 60 0 0 0 120 0V4"/></svg>')


def _days(updated: str | None, g: dict) -> str:
    """次の試合までの「あと3日」「明日」"""
    from datetime import datetime
    try:
        d = (datetime.strptime(g["date"], "%Y-%m-%d").date()
             - datetime.strptime(updated, "%Y-%m-%d %H:%M").date()).days
    except (KeyError, TypeError, ValueError):
        return ""
    return {0: "今日", 1: "明日"}.get(d, f"あと{d}日" if d > 1 else "")


def _hero(inner: str, hot: bool = False) -> str:
    return f'<div class="hero{" hot" if hot else ""}">{COURT}<div class="wrap">{inner}</div></div>'


def hero(state: dict) -> tuple[str, str]:
    """（HTML, ページタイトル）"""
    g = state.get("today")
    title = "見どころなう｜レバンガ北海道版"
    vs = lambda x: f"vs {x['opponent']}　{x['place']}"
    if g and g["status"] == "試合中":
        lv, clock = g.get("level"), g.get("clock")
        ctx = f"{clock}　vs {g['opponent']}" if clock else f"vs {g['opponent']}"
        chip = '<span class="chip live">試合中</span>'
        if lv == "高":
            return (_hero(f'<p class="ctx">{chip}{e(ctx)}</p>'
                          f'<h2 class="word">いま見て！</h2><p class="say">{e(g["text"] or "")}</p>'
                          f'{_meter(g["meter"])}{_btn("試合を見る（B.LEAGUE公式）", g["url"])}', hot=True),
                    "いま見て！｜見どころなう")
        if lv == "中":
            word, say = "そろそろ", g["text"] or "盛り上がってきました。"
        else:
            word, say = "まだ大丈夫", "見どころが来たら、すぐにお知らせします。"
        return (_hero(f'<p class="ctx">{chip}{e(ctx)}</p>'
                      f'<h2 class="word">{word}</h2><p class="say">{e(say)}</p>'
                      f'{_meter(g["meter"])}{_btn("試合を見る（B.LEAGUE公式）", g["url"], quiet=True)}'), title)
    if g and g["status"] == "まもなく":
        return (_hero(f'<p class="ctx"><span class="chip">今日</span>{e(vs(g))}</p>'
                      f'<h2 class="word">まもなく</h2><p class="say">{e(g["start"])}に試合開始。見どころが来たらお知らせします。</p>'), title)
    if g and g["status"] == "予定":
        left = _until(state.get("updated"), g)
        chip = f'<span class="chip">開始まであと{e(left)}</span>' if left else '<span class="chip">今日</span>'
        return (_hero(f'<p class="ctx">{chip}{e(vs(g))}</p>'
                      f'<h2 class="word">{e(g["start"])}</h2><p class="say">今日の試合開始。始まったら、見どころをお知らせします。</p>'), title)
    if g and g["status"] == "終了":
        n = len(g["alerts"])
        say = f"見どころは{n}回ありました。" if n else "通知するほどの場面はありませんでした。"
        link = _btn("ハイライト動画を見る", g.get("highlight")) or _btn("試合の記録を見る（B.LEAGUE公式）", g["url"], quiet=True)
        return (_hero(f'<p class="ctx"><span class="chip">今日</span>{e(vs(g))}</p>'
                      f'<h2 class="word">試合終了</h2><p class="say">{e(say)}</p>{link}'), title)
    nxt = (state.get("next") or [None])[0]
    if nxt:
        left = _days(state.get("updated"), nxt)
        chip = f'<span class="chip">次の試合まで{e(left)}</span>' if left.startswith("あと") else (
            f'<span class="chip">{e(left)}</span>' if left else '<span class="chip">次の試合</span>')
        return (_hero(f'<p class="ctx">{chip}{e(vs(nxt))}</p>'
                      f'<h2 class="word">{e(nxt["md"])}<span class="wd">{e(nxt["wd"])}曜日 {e(nxt["start"])}</span></h2>'
                      f'<p class="say">始まったら、見どころをお知らせします。</p>'), title)
    return (_hero('<p class="ctx"><span class="chip">次の試合</span></p>'
                  '<h2 class="word">日程待ち</h2><p class="say">次の試合が決まったら、ここに表示します。</p>'), title)


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


PUSH_ENABLED = os.environ.get("MIDOKORO_PUSH", "1") != "0"   # 受付窓口がないときは 0
API_BASE = os.environ.get("MIDOKORO_API", "").rstrip("/")   # GitHub版：Cloudflareの受付窓口


PHONE = ('<div class="phone" aria-hidden="true"><p class="tm">20:48</p><p class="dt">金曜日</p>'
         '<div class="toast"><span class="ic">見</span><span class="ap">見どころなう・いま</span>'
         '<b>いま見て！ 佐賀戦</b><span>第4Q残り2分、1ポゼッション差。レバンガが逆転！</span></div>'
         '<div class="toast two"><span class="ic">見</span><span class="ap">見どころなう・12分前</span>'
         '<b>そろそろ 佐賀戦</b><span>第4Q、差が縮まってきました。</span></div></div>')

PITCH = ('<p class="kicker">レバンガ北海道ファンのための通知サービス（非公式）</p>'
         '<h2 class="hook">試合は、<mark>山場だけ</mark>見ればいい。</h2>'
         '<p class="hook-sub">接戦・逆転・終盤の勝負どころを自動で判定。'
         '見逃したくない瞬間だけ、スマホに「いま見て！」が届きます。</p>' + PHONE)

PROOF = ('<section class="proof"><div class="wrap"><h2>通知は、本当に見たい試合だけ。</h2>'
         '<div class="stats">'
         '<div class="stat"><b>1.2<small>回</small></b><span>1試合あたりの<br>通知（平均）</span></div>'
         '<div class="stat"><b>23<small>/23</small></b><span>5点差以内の<br>接戦で通知</span></div>'
         '<div class="stat"><b>0<small>回</small></b><span>20点差以上の<br>大差の試合</span></div>'
         '</div><p class="fine">過去シーズンのレバンガの60試合に、いまの判定ルールを当てはめた試算です。実際の回数は試合によって変わります。</p>'
         '</div></section>')

STEPS = ('<section><div class="wrap"><h2>はじめ方は3つだけ</h2><ol class="steps">'
         '<li><div><b>ボタンを押す</b><span>アプリのインストールも会員登録もいりません</span></div></li>'
         '<li><div><b>通知を「許可」する</b><span>iPhoneはホーム画面に追加してから開きます</span></div></li>'
         '<li><div><b>あとは待つだけ</b><span>山場が来たら「いま見て！」が届きます</span></div></li>'
         '</ol></div></section>')


def notify_block() -> str:
    line_url = os.environ.get("LINE_ADD_URL", "").strip()
    badges = '<ul class="badges"><li>無料</li><li>登録・アプリ不要</li><li>試合のない日は届かない</li></ul>'
    if not PUSH_ENABLED:                       # Webプッシュなし：LINEだけで受け取る
        line = _btn("LINEで受け取る", line_url).replace('class="btn"', 'class="btn big"') if line_url else ""
        say = ("試合が盛り上がったら、LINEでお知らせします（1試合1回）。" if line_url
               else "このページは数分おきに更新されます。")
        return ('<section class="notify pitch" id="notify"><div class="wrap">' + PITCH +
                f'<div class="cta">{badges}<div class="row">{line}</div><p class="note">{e(say)}</p></div></div></section>')
    line = _btn("LINEで受け取る", line_url, quiet=True).replace('class="btn quiet"', 'class="btn big quiet"') if line_url else ""
    count = "1試合おおむね1〜3回" + ("（LINEは1回まで）" if line_url else "")
    return ('<section class="notify pitch" id="notify"><div class="wrap">' + PITCH +
            f'<div class="cta">{badges}<div class="row"><button class="btn big" id="nb" hidden>無料で通知を受け取る</button>{line}</div>'
            f'<p class="note" id="np" data-line="{1 if line_url else 0}">押すと通知の許可を聞かれます。「許可」を選べば完了です。</p>'
            f'<p class="note">届くのは{e(count)}。</p></div>'
            '</div></section>')


def sticky() -> str:
    line_url = os.environ.get("LINE_ADD_URL", "").strip()
    if PUSH_ENABLED:
        return '<a class="sticky" id="sticky" href="#notify" tabindex="-1">「いま見て！」を受け取る<small>無料</small></a>'
    if line_url:
        return '<a class="sticky" id="sticky" data-mode="line" href="#notify" tabindex="-1">LINEで「いま見て！」を受け取る</a>'
    return ""


PAGE = """<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="レバンガ北海道の試合が盛り上がった瞬間をお知らせする、非公式のファンサービスです。">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icon-180.png">
<meta name="theme-color" content="#14290F">
<meta name="apple-mobile-web-app-capable" content="yes">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=BIZ+UDPGothic:wght@400;700&family=Dela+Gothic+One&display=swap">
<style>{css}</style>
</head>
<body data-api="{api}">
<header class="site wrap"><div class="brand"><h1 class="mark">見どころなう</h1><span class="edition">レバンガ北海道版（非公式）</span></div><a class="go" href="#notify">通知を受け取る</a></header>
<main>
<div id="live-top" data-live>{top}</div>
{notify}
{proof}
<div id="live-low" data-live>{low}</div>
{steps}
{upcoming}
</main>
<footer class="wrap">
<p>レバンガ北海道を応援する個人の非公式サービスです。B.LEAGUE・レバンガ北海道とは関係ありません。</p>
<p>試合の映像と記録はB.LEAGUE公式でご覧ください。見どころの判定は試験運用中です。</p>
<p>最終更新 {updated}</p>
</footer>
{sticky}
<script>{script}</script>{beacon}
</body></html>
"""


def render(state: dict) -> str:
    hero_html, title = hero(state)
    m = moments(state)
    today = state.get("today")
    game_day = bool(today and today["status"] in ("試合中", "終了", "まもなく"))
    return PAGE.format(title=e(title), css=CSS, top=hero_html + (m if game_day else ""),
                       low="" if game_day else m, notify=notify_block(), proof=PROOF, steps=STEPS,
                       upcoming=upcoming(state), sticky=sticky(),
                       updated=e(state.get("updated", "-")), script=SCRIPT, api=e(API_BASE),
                       beacon=BEACON if API_BASE else "")


def build() -> Path:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    OUT_DIR.mkdir(exist_ok=True)
    for f in STATIC_DIR.glob("*"):                 # 通知用の部品・アイコン・利用状況ページをコピー
        dst = OUT_DIR / f.name
        if f.name == "stats.html":                 # 受付窓口のURLを埋め込む
            text = f.read_text(encoding="utf-8").replace("__API__", html.escape(API_BASE))
            if not dst.exists() or dst.read_text(encoding="utf-8") != text:
                dst.write_text(text, encoding="utf-8")
        elif f.is_file() and (not dst.exists() or dst.stat().st_mtime < f.stat().st_mtime):
            shutil.copy2(f, dst)
    out = OUT_DIR / "index.html"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(render(state), encoding="utf-8")
    tmp.replace(out)
    return out


if __name__ == "__main__":
    print(build())

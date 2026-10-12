"""
見どころなう レバンガ北海道版 Webページ生成
data/state.json を読んで public/ に index.html・sitemap.xml・robots.txt を作る（収集プログラムが毎回呼ぶ）。

デザイン：「試合の熱さゲージ」が主役のページ
  ファーストビュー：暗い緑の地に「レバンガ北海道の試合、いまどれくらい熱い？」と、スコアボード風の熱さゲージ。
  試合がない日は次の試合とカウントダウン、試合中はいまの熱さ、試合後はその試合の最高の熱さを出す。
  熱さ（%）＝ 見どころ度 ÷ 通知ライン（midokoro_score.HIGH）。ゲージが満タン（100%）＝「いま見て！」の通知。
  満タンのときは、ファーストビュー全体がレバンガの黄緑（#8FC31F）に変わる。
  熱さの推移（試合時間ごとの折れ線）を、今日の試合・前回の試合について出す。
  書体は見出し・本文・ゲージの数字に M PLUS 1、日付と時刻に Anton。
  公式ロゴ・マスコット・写真は使わない。スコアは載せない。非公式であることを明記する。
  ページの説明（第1〜3Qは満タンにならない、など）は判定ルール v1.2 に合わせている。
  ルールを変えたら FLOW・FAQ・PROOF の文も見直すこと。

検索対策
  タイトル・説明文・正規URL・OGP・構造化データ（WebSite）を入れ、sitemap.xml と robots.txt を出す。
  Search Console などの所有確認は、環境変数 GOOGLE_SITE_VERIFICATION / BING_SITE_VERIFICATION で入れる。
"""

import html
import json
import math
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from midokoro_score import HIGH

STATE_FILE = Path("data/state.json")
OUT_DIR = Path("public")
STATIC_DIR = Path("static")
TEAM = "レバンガ北海道"
SEGMENTS = 20

SITE_URL = (os.environ.get("SITE_URL") or "https://levangamidokoro.github.io/").rstrip("/") + "/"
PUSH_ENABLED = os.environ.get("MIDOKORO_PUSH", "1") != "0"   # 受付窓口がないときは 0
API_BASE = os.environ.get("MIDOKORO_API", "").rstrip("/")   # GitHub版：Cloudflareの受付窓口
LINE_URL = os.environ.get("LINE_ADD_URL", "").strip()

TITLE = "レバンガ北海道の試合、熱くなったら通知｜見どころなう（非公式）"
DESC = ("レバンガ北海道（B.LEAGUE）の試合の熱さをゲージで表示。接戦・逆転・終盤の山場でゲージが満タンになったら、"
        "スマホに「いま見て！」と通知する無料の非公式ファンサービスです。")
OG_DESC = "試合の熱さをゲージで表示。満タンになったら、スマホに「いま見て！」が届く。レバンガ北海道ファンのための無料の非公式サービスです。"
SHARE_TEXT = "レバンガの試合の熱さをゲージで表示して、満タンになったら「いま見て！」と通知してくれる非公式サービス #レバンガ北海道"

FONTS = "https://fonts.googleapis.com/css2?family=Anton&family=M+PLUS+1:wght@400;700;900&display=swap"

CSS = """
:root{
  --lime:#8FC31F; --pine:#14290F; --snow:#F6F8F1; --frost:#DDE6D0; --moss:#56664F; --mist:#C9D6BC; --board:#0B1909;
  --bg:var(--snow); --ink:var(--pine); --sub:var(--moss); --line:var(--frost); --card:#FFFFFF; --tile:var(--pine);
  --series:#3F7A1A;
  --display:"M PLUS 1","Hiragino Sans","Noto Sans JP",sans-serif;
  --num:"Anton","M PLUS 1",sans-serif;
  --body:"M PLUS 1","Hiragino Sans","Noto Sans JP",sans-serif;
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#0D1A0B; --ink:#E8F0DD; --sub:#9AAA90; --line:#24361F; --card:#122310; --tile:#1A3415; --series:#73A318; }
}
*{box-sizing:border-box}
[hidden]{display:none!important}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body);font-size:16px;line-height:1.75;overflow-x:hidden}
a{color:inherit}
button{font:inherit}
.wrap{max-width:640px;margin:0 auto;padding:0 16px}
.wrap.wide{max-width:1040px}
:focus-visible{outline:3px solid var(--lime);outline-offset:3px;border-radius:6px}
h1,h2,h3{font-feature-settings:"palt"}

/* ファーストビュー（満タンのときは全体が黄緑に変わる） */
.poster{--p-ink:var(--snow);--p-sub:var(--mist);--p-mark:var(--lime);--p-btn:var(--lime);--p-btn-ink:var(--pine);--p-btn-sh:#5E8410;
        position:relative;overflow:hidden;color:var(--p-ink);background-color:var(--pine);
        background-image:radial-gradient(560px 340px at 88% 4%,rgba(143,195,31,.20),transparent 70%);transition:background-color .6s}
.poster:has(.panel.hot){--p-ink:var(--pine);--p-sub:#2B4520;--p-mark:var(--pine);--p-btn:var(--pine);--p-btn-ink:var(--lime);--p-btn-sh:#050D04;
        background-color:var(--lime);background-image:none}
.poster .court{position:absolute;right:-120px;top:70px;width:440px;height:440px;color:var(--p-mark);opacity:.10;pointer-events:none}
header.site{position:relative;display:flex;align-items:center;gap:10px;padding-top:14px;padding-bottom:10px}
.brand{display:flex;flex-direction:column;line-height:1.2;text-decoration:none}
.mark{font-family:var(--display);font-weight:900;font-size:21px;letter-spacing:.02em;white-space:nowrap}
.edition{font-size:11px;font-weight:700;color:var(--p-sub);white-space:nowrap}
.on-badge{margin-left:auto;display:none;font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px;background:var(--p-btn);color:var(--p-btn-ink)}
body[data-pstate=on] .on-badge{display:inline-block}
.first{position:relative;display:grid;grid-template-areas:"copy" "now" "text" "cta";gap:18px;padding-top:14px;padding-bottom:40px}
.first .copy{grid-area:copy}.first .now{grid-area:now}.first .text{grid-area:text}.first .cta-area{grid-area:cta}
.hook{margin:0;font-family:var(--display);font-weight:900;font-size:clamp(28px,7.9vw,46px);line-height:1.3;letter-spacing:.01em}
.hook span,.final h2 span{display:block;width:fit-content;transform:skewX(-6deg);transform-origin:left bottom}
.hook-sub{margin:0;font-size:16px;color:var(--p-sub);max-width:30em}
@media (min-width:860px){
  .first{grid-template-columns:1fr 440px;grid-template-areas:"copy now" "text now" "cta now";column-gap:56px;row-gap:22px;
         padding-top:36px;padding-bottom:64px;align-items:start}
  .first .now{grid-row:1 / span 3}
}

.chip{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:700;line-height:1.6;padding:2px 10px;
      border-radius:999px;background:var(--lime);color:var(--pine);white-space:nowrap}
.chip.live::before{content:"";width:8px;height:8px;border-radius:50%;background:#E03C31;animation:blink 1.2s steps(2) infinite}
@keyframes blink{50%{opacity:0}}

/* 熱さゲージ（スコアボード風） */
.panel{position:relative;padding:16px 16px 18px;border-radius:22px;background:var(--board);color:var(--snow);
       box-shadow:0 0 0 1px rgba(201,214,188,.14),0 18px 40px rgba(0,0,0,.30)}
.panel .ctx{margin:0;display:flex;align-items:center;flex-wrap:wrap;gap:4px 10px;font-size:14px;color:var(--mist)}
.panel .word{margin:10px 0 0;font-family:var(--display);font-weight:900;font-size:clamp(44px,13.5vw,76px);line-height:1.05;
             transform:skewX(-6deg);transform-origin:left bottom;font-feature-settings:"palt"}
.panel.hot .word{color:var(--lime)}
.readout{margin:14px 0 8px;display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 10px}
.readout .lbl{font-size:14px;font-weight:700;color:var(--mist)}
.readout .fig{font-family:var(--display);font-weight:900;font-size:clamp(40px,12vw,58px);line-height:1}
.readout .fig small{font-size:.42em;margin-left:2px}
.readout .goal{margin-left:auto;font-size:12px;font-weight:700;color:var(--mist);text-align:right}
.panel.hot .readout .goal{color:var(--lime)}
.gauge{display:grid;grid-template-columns:repeat(20,1fr);gap:3px;height:48px;padding:5px;border-radius:12px;
       background:#050D04;box-shadow:inset 0 0 0 1px rgba(143,195,31,.18)}
.gauge i{border-radius:3px;background:rgba(143,195,31,.13)}
.gauge i.on{background:var(--lime);box-shadow:0 0 10px rgba(143,195,31,.45)}
.gauge i.lead{background:#D4EE85}
.panel:not(.still) .gauge i.on{animation:charge .3s ease-out both;animation-delay:calc(var(--i) * 35ms)}
@keyframes charge{from{background:rgba(143,195,31,.13);box-shadow:none}}
.panel.hot .gauge i.on{animation:glow 1.4s ease-in-out infinite}
@keyframes glow{50%{background:#E4F7A8;box-shadow:0 0 16px rgba(228,247,168,.85)}}
.panel .say{margin:12px 0 0;font-size:16px;font-weight:700}
.panel .quiet-note{margin:10px 0 0;font-size:14px;color:var(--mist)}
.panel .btn{margin-top:14px}
.nextgame{display:grid;grid-template-columns:1fr auto;align-items:center;gap:2px 10px}
.nextgame .chip{justify-self:start}
.nextgame .slot,.nextgame .vs{grid-column:1 / -1;margin:0}
.nextgame .slot{display:flex;align-items:baseline;flex-wrap:wrap;gap:0 8px;margin-top:8px}
.nextgame .date{font-family:var(--num);font-size:40px;line-height:1.05}
.nextgame .wd{font-weight:700;font-size:14px}
.nextgame .time{font-family:var(--num);font-size:28px;line-height:1.05}
.nextgame .vs{font-weight:700}
.nextgame .vs small{font-weight:400;font-size:13px;color:var(--mist);margin-left:8px}
.count{margin:0;justify-self:end;font-size:12px;font-weight:700;color:var(--mist);white-space:nowrap}
.count b{font-family:var(--num);font-weight:400;font-size:20px;color:var(--snow);margin:0 2px;letter-spacing:.03em}

/* ボタン */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:50px;padding:0 22px;border-radius:999px;
     border:0;background:var(--pine);color:var(--snow);font-weight:700;text-decoration:none;cursor:pointer;text-align:center;line-height:1.4}
@media (prefers-color-scheme: dark){.btn{background:var(--lime);color:var(--pine)}}
.btn.quiet{background:transparent;color:inherit;box-shadow:inset 0 0 0 2px currentColor}
.panel .btn{background:var(--lime);color:var(--pine)}
.panel .btn.quiet,.final .btn.quiet,.poster .cta-area .btn.quiet{background:transparent;color:inherit;box-shadow:inset 0 0 0 2px var(--mist)}
.btn.big{position:relative;overflow:hidden;width:100%;min-height:62px;font-size:19px;font-weight:900;
         background:var(--lime);color:var(--pine);box-shadow:0 6px 0 #5E8410;transition:transform .08s,box-shadow .08s}
.poster .btn.big{background:var(--p-btn);color:var(--p-btn-ink);box-shadow:0 6px 0 var(--p-btn-sh)}
.btn.big:active{transform:translateY(4px);box-shadow:0 2px 0 #5E8410}
.btn.big::after{content:"";position:absolute;inset:0;pointer-events:none;
                background:linear-gradient(105deg,transparent 35%,rgba(255,255,255,.5) 50%,transparent 65%);
                transform:translateX(-120%);animation:shine 4.5s ease-in-out 1.6s infinite}
@keyframes shine{0%,70%{transform:translateX(-120%)}100%{transform:translateX(120%)}}
.btn[aria-busy=true]{opacity:.7;pointer-events:none}
.link{background:none;border:0;padding:4px;color:inherit;text-decoration:underline;cursor:pointer;font-size:13px;font-weight:400}

/* 登録ボタンまわり */
.cta-area{display:grid;gap:12px;width:100%;max-width:520px}
.micro{margin:0;font-size:13px;color:var(--p-sub,var(--mist));text-align:center}
.badges{display:flex;flex-wrap:wrap;justify-content:center;gap:6px;margin:0;padding:0;list-style:none}
.badges li{font-size:12.5px;font-weight:700;padding:3px 11px;border-radius:999px;background:rgba(246,248,241,.08);box-shadow:inset 0 0 0 1px rgba(201,214,188,.24)}
.badges li::before{content:"✓ ";color:var(--p-mark,var(--lime))}
.poster:has(.panel.hot) .badges li{background:rgba(20,41,15,.08);box-shadow:inset 0 0 0 1px rgba(20,41,15,.3)}
.pushmsg{margin:0;font-size:14px;text-align:center}
.pushmsg:empty{display:none}
.on-only{display:none}
body[data-pstate=on] .on-only{display:flex}
body[data-pstate=on] .off-only{display:none}
body[data-pstate=none] .pushbtn{display:none}
.on-box{align-items:center;justify-content:center;flex-wrap:wrap;gap:4px 12px;padding:14px;border-radius:16px;font-weight:700;text-align:center;
        background:rgba(143,195,31,.16);box-shadow:inset 0 0 0 1px rgba(143,195,31,.5);animation:pop .5s cubic-bezier(.2,.9,.3,1.4)}
.on-box::before{content:"✓";display:grid;place-items:center;width:24px;height:24px;border-radius:50%;background:var(--lime);color:var(--pine);font-weight:900;font-size:14px}
@keyframes pop{from{transform:scale(.92);opacity:0}to{transform:none;opacity:1}}

/* 下の各セクション */
section{padding:44px 0 4px}
section h2{margin:0 0 16px;font-family:var(--display);font-weight:900;font-size:clamp(22px,6.2vw,30px);line-height:1.35}
h3.sub{font-size:14px;margin:24px 0 4px;color:var(--sub);font-weight:700}
.note{margin:0;color:var(--sub);font-size:14px}
.fine{margin:8px 0 0;font-size:12px;color:var(--sub)}

/* 実演：満タンになると、こう届く */
.demo{display:grid;gap:14px;justify-items:center}
.demo .panel{width:100%;max-width:470px}
.demo .readout{margin-top:0}
.demo.ready:not(.play) .gauge i{background:rgba(143,195,31,.13);box-shadow:none}
.demo.ready:not(.play) .toast{opacity:0}
.demo.play .gauge i{animation:charge .25s ease-out both;animation-delay:calc(var(--i) * 70ms)}
.demo.play .panel{animation:fullring .9s ease-out 1.45s both}
@keyframes fullring{from{box-shadow:0 0 0 0 rgba(143,195,31,.7),0 18px 40px rgba(0,0,0,.3)}to{box-shadow:0 0 0 14px rgba(143,195,31,0),0 18px 40px rgba(0,0,0,.3)}}
.demo.play .toast{animation:drop .6s cubic-bezier(.2,.8,.2,1) 1.55s both}
.phone{margin:0;width:100%;max-width:470px;display:grid;justify-items:center}
.phone figcaption{margin-top:8px;font-size:11px;letter-spacing:.06em;color:var(--sub)}
.toast{display:grid;grid-template-columns:40px 1fr;gap:1px 10px;width:100%;padding:12px 14px;border-radius:18px;
       background:var(--card);color:var(--ink);font-size:13.5px;line-height:1.5;text-align:left;
       box-shadow:0 0 0 1px var(--line),0 14px 30px rgba(20,41,15,.16)}
.toast .ic{grid-row:span 3;width:40px;height:40px;border-radius:11px;background:var(--lime);display:grid;place-items:center;
           font-family:var(--display);font-weight:900;font-size:16px;color:var(--pine)}
.toast .ap{display:flex;justify-content:space-between;font-size:11px;color:var(--sub)}
.toast b{font-size:15px;font-weight:900}
@keyframes drop{from{transform:translateY(-30px) scale(.96);opacity:0}to{transform:none;opacity:1}}
.replay{justify-self:center}

/* 熱さの推移（折れ線） */
.curve{margin:0;padding:14px 14px 12px;border-radius:16px;background:var(--card);box-shadow:0 0 0 1px var(--line)}
.curve figcaption{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:2px 12px;margin-bottom:10px}
.curve figcaption b{font-size:15px}
.key{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--sub)}
.key i{width:10px;height:10px;border-radius:50%;background:var(--series);box-shadow:0 0 0 2px var(--card)}
.plot{position:relative;display:grid;grid-template-columns:34px 1fr;grid-template-rows:auto 20px;margin-top:22px}
.ylab{position:relative}
.ylab span{position:absolute;right:6px;transform:translateY(-50%);font-size:11px;color:var(--sub);line-height:1}
.area{position:relative;height:150px;touch-action:pan-y;outline-offset:6px}
@media (min-width:600px){.area{height:180px}}
.area svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.area .gl{stroke:var(--line);stroke-width:1;vector-effect:non-scaling-stroke}
.area .full{stroke:var(--sub);stroke-width:1;vector-effect:non-scaling-stroke}
.area .ln{fill:none;stroke:var(--series);stroke-width:2;stroke-linejoin:round;stroke-linecap:round;vector-effect:non-scaling-stroke}
.area .ar{fill:var(--series);opacity:.1}
.flabel{position:absolute;left:0;top:-18px;font-size:11px;color:var(--sub);white-space:nowrap}
.mk,.fd{position:absolute;width:10px;height:10px;margin:-5px 0 0 -5px;border-radius:50%;background:var(--series);box-shadow:0 0 0 2px var(--card)}
.fd{width:12px;height:12px;margin:-6px 0 0 -6px}
.xh{position:absolute;top:0;bottom:0;width:1px;background:var(--sub)}
.tip{position:absolute;top:-6px;transform:translate(-50%,-100%);pointer-events:none;padding:6px 10px;border-radius:10px;
     background:var(--ink);color:var(--bg);font-size:12px;line-height:1.35;white-space:nowrap;box-shadow:0 6px 16px rgba(0,0,0,.2);z-index:2}
.tip b{display:block;font-size:16px}
.xlab{position:relative;grid-column:2}
.xlab span{position:absolute;top:4px;transform:translateX(-50%);font-size:11px;color:var(--sub);line-height:1}
.tbl summary{cursor:pointer;font-size:13px;color:var(--sub);margin-top:10px}
.tbl table{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
.tbl th,.tbl td{text-align:left;padding:4px 6px;border-top:1px solid var(--line);font-variant-numeric:tabular-nums}
.tbl th{font-weight:700;color:var(--sub)}
.peak{margin:0 0 14px;font-family:var(--display);font-weight:900;font-size:clamp(20px,5.6vw,26px);line-height:1.45}

ul.fit{list-style:none;margin:0;padding:0;display:grid;gap:10px}
ul.fit li{display:grid;grid-template-columns:28px 1fr;gap:12px;align-items:start;padding:14px 16px;border-radius:14px;
          background:var(--card);box-shadow:0 0 0 1px var(--line);font-weight:700;line-height:1.6}
ul.fit li::before{content:"✓";display:grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--lime);color:var(--pine);font-weight:900;font-size:15px}

.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.stat{padding:16px 6px 14px;border-radius:16px;background:var(--tile);color:var(--snow);text-align:center}
.stat b{display:block;font-family:var(--display);font-weight:900;font-size:clamp(30px,9vw,44px);line-height:1}
.stat b small{font-size:.4em;margin-left:2px}
.stat span{display:block;margin-top:8px;font-size:12px;line-height:1.45;color:var(--mist)}

ol.flow{list-style:none;margin:0;padding:0;position:relative}
ol.flow::before{content:"";position:absolute;left:18px;top:14px;bottom:14px;width:3px;border-radius:2px;background:var(--line)}
ol.flow li{position:relative;display:grid;grid-template-columns:40px 1fr;gap:14px;padding:9px 0}
ol.flow .dot{position:relative;z-index:1;width:40px;height:40px;border-radius:50%;display:grid;place-items:center;
             background:var(--bg);box-shadow:inset 0 0 0 3px var(--line);font-weight:900;font-size:17px;color:var(--sub)}
ol.flow li.hot .dot{background:var(--lime);box-shadow:none;color:var(--pine)}
ol.flow .when{display:block;font-size:12px;font-weight:700;color:var(--sub)}
ol.flow b{display:block;font-size:16px;line-height:1.5}
ol.flow p{margin:2px 0 0;font-size:14px;color:var(--sub)}

ol.steps{list-style:none;margin:0;padding:0;display:grid;gap:10px;counter-reset:s}
ol.steps li{counter-increment:s;display:grid;grid-template-columns:46px 1fr;gap:12px;align-items:center;
            padding:12px 14px;border-radius:14px;background:var(--card);box-shadow:0 0 0 1px var(--line)}
ol.steps li::before{content:counter(s);display:grid;place-items:center;width:46px;height:46px;border-radius:50%;
            background:var(--lime);color:var(--pine);font-family:var(--num);font-size:24px}
ol.steps b{display:block}
ol.steps span{font-size:14px;color:var(--sub)}

ol.moments,ul.games{list-style:none;margin:0;padding:0}
ol.moments li{display:grid;grid-template-columns:96px 1fr auto;gap:12px;align-items:baseline;padding:12px 0;border-top:1px solid var(--line)}
.clock{font-weight:900;font-size:15px;white-space:nowrap}
.when{font-size:13px;color:var(--sub)}
ul.games li{display:grid;grid-template-columns:72px 1fr auto;gap:12px;align-items:center;padding:12px 0;border-top:1px solid var(--line)}
.day{line-height:1.2}
.day .num{display:block;font-family:var(--num);font-size:24px}
.day small{display:block;font-size:12px;color:var(--sub)}
.opp{font-weight:700}
.opp small{display:block;font-weight:400;font-size:13px;color:var(--sub)}
.start{font-family:var(--num);font-size:22px}
.links{margin-top:14px;display:flex;gap:10px;flex-wrap:wrap}

.share-row{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:14px}
.share-row [data-share]{grid-column:1 / -1}
.btn.sh{min-height:50px;padding:0 6px;font-size:14px;background:var(--card);color:var(--ink);box-shadow:0 0 0 1px var(--line)}
.btn.sh i{flex:none;width:10px;height:10px;border-radius:50%;background:var(--lime)}
.btn.sh i.d-line{background:#06C755}.btn.sh i.d-x{background:currentColor}

.faq details{border-top:1px solid var(--line)}
.faq details:last-of-type{border-bottom:1px solid var(--line)}
.faq summary{list-style:none;cursor:pointer;display:grid;grid-template-columns:1fr 24px;gap:10px;align-items:center;padding:15px 0;font-weight:700}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";font-family:var(--num);font-size:24px;line-height:1;text-align:center;color:var(--sub);transition:transform .2s}
.faq details[open] summary::after{transform:rotate(45deg)}
.faq details p{margin:0 0 16px;font-size:14px;color:var(--sub)}

.final{position:relative;overflow:hidden;margin-top:56px;padding:48px 0 52px;background:var(--pine);color:var(--snow)}
.final .court{position:absolute;left:-140px;bottom:-160px;width:420px;height:420px;color:var(--lime);opacity:.08;pointer-events:none}
.final .wrap{position:relative}
.final h2{font-size:clamp(24px,6.6vw,40px)}
.final .hook-sub{margin:0 0 20px;color:var(--mist)}
.final .micro{color:var(--mist)}
footer{padding:28px 0 112px;font-size:12px;color:var(--sub)}
footer p{margin:0 0 6px}

/* 画面下に追従するボタン */
.sticky{position:fixed;left:12px;right:12px;bottom:calc(12px + env(safe-area-inset-bottom));z-index:10;max-width:520px;margin:0 auto;
        display:flex;align-items:center;justify-content:center;min-height:56px;border:0;border-radius:999px;
        background:var(--lime);color:var(--pine);font-weight:900;font-size:16px;text-decoration:none;cursor:pointer;
        box-shadow:0 8px 24px rgba(20,41,15,.4);transform:translateY(160%);visibility:hidden;transition:transform .25s,visibility 0s .25s}
.sticky.show{transform:none;visibility:visible;transition:transform .25s}

/* 受け取り方の案内（iPhone・アプリ内ブラウザなど） */
dialog.guide{width:min(520px,calc(100% - 24px));max-height:calc(100% - 24px);margin:auto auto 12px;border:0;border-radius:22px;
             padding:22px 20px 16px;background:var(--card);color:var(--ink);box-shadow:0 20px 50px rgba(0,0,0,.35)}
@media (min-width:600px){dialog.guide{margin:auto}}
dialog.guide::backdrop{background:rgba(8,18,7,.6)}
dialog.guide h2{margin:0 0 12px;font-family:var(--display);font-weight:900;font-size:20px;line-height:1.4}
dialog.guide p{margin:0 0 10px}
dialog.guide ol{margin:0 0 12px;padding:0;list-style:none;display:grid;gap:12px;counter-reset:g}
dialog.guide ol li{counter-increment:g;display:grid;grid-template-columns:30px 1fr;gap:10px;align-items:start}
dialog.guide ol li::before{content:counter(g);display:grid;place-items:center;width:30px;height:30px;border-radius:50%;
                           background:var(--lime);color:var(--pine);font-family:var(--num);font-size:17px}
dialog.guide .g{display:none}
dialog.guide[data-mode=ios] .g-ios,dialog.guide[data-mode=inapp] .g-inapp,
dialog.guide[data-mode=denied] .g-denied,dialog.guide[data-mode=none] .g-none{display:block}
dialog.guide .row{display:grid;gap:8px;margin-top:12px}
.shareico{display:inline-block;width:20px;height:20px;vertical-align:-4px;margin:0 3px}

@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  *,*::before,*::after{animation:none!important;transition:none!important}
}
"""

SCRIPT = r"""
// 1) 試合の部分（data-live）だけ30秒ごとに新しくする（ページ全体は読み直さない）
(() => {
  const last = new Map();
  for (const el of document.querySelectorAll("[data-live]")) last.set(el.id, el.innerHTML);
  async function refresh() {
    if (document.hidden) return;
    try {
      const r = await fetch(location.pathname, { cache: "no-store" });
      if (!r.ok) return;
      const doc = new DOMParser().parseFromString(await r.text(), "text/html");
      let changed = false;
      for (const fresh of doc.querySelectorAll("[data-live]")) {
        const cur = document.getElementById(fresh.id);
        if (!cur || last.get(fresh.id) === fresh.innerHTML) continue;
        last.set(fresh.id, fresh.innerHTML);
        cur.replaceWith(fresh);
        fresh.querySelectorAll(".panel").forEach((p) => p.classList.add("still"));
        changed = true;
      }
      if (changed) { document.title = doc.title; dispatchEvent(new Event("midokoro:live")); }
    } catch (e) {}
  }
  setInterval(refresh, 30000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
})();

// 2) 試合開始までのカウントダウン
(() => {
  const pad = (n) => String(n).padStart(2, "0");
  const tick = () => {
    for (const el of document.querySelectorAll("[data-count]")) {
      const ms = Date.parse(el.dataset.count) - Date.now();
      if (Number.isNaN(ms)) continue;
      let h = "まもなく開始";
      if (ms > 0) {
        const s = Math.floor(ms / 1000), d = Math.floor(s / 86400);
        const hh = Math.floor((s % 86400) / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
        h = d ? `開始まで <b>${d}</b>日<b>${hh}</b>時間<b>${pad(mm)}</b>分`
              : `開始まで <b>${pad(hh)}:${pad(mm)}:${pad(ss)}</b>`;
      }
      if (el.innerHTML !== h) el.innerHTML = h;
    }
  };
  tick();
  setInterval(tick, 1000);
})();

// 3) 通知の登録（ボタンはページ内に何個あってもよい）
(() => {
  const body = document.body, API = body.dataset.api || "";
  const ua = navigator.userAgent;
  const ios = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  const line = /\bLine\//.test(ua);
  const inApp = line || /FBAN|FBAV|Instagram/.test(ua);
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const can = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  const LABEL = { off: "無料で通知を受け取る", ios: "iPhoneで通知を受け取る", inapp: "ブラウザで開いて受け取る", denied: "通知を許可する方法を見る" };
  const SHORT = { off: "満タンで「いま見て！」を受け取る", ios: "iPhoneで「いま見て！」を受け取る", inapp: "ブラウザで開いて受け取る", denied: "通知を許可する方法を見る" };
  let reg = null, sub = null, key = null, busy = false;
  const say = (t) => document.querySelectorAll("[data-push-msg]").forEach((m) => { m.textContent = t; });
  const set = (mode) => {
    body.dataset.pstate = mode;
    document.querySelectorAll("[data-push]").forEach((b) => {
      const l = ("short" in b.dataset ? SHORT : LABEL)[mode];
      if (l) b.textContent = l;
    });
    dispatchEvent(new Event("midokoro"));
  };
  const b64 = (s) => {
    const raw = atob((s + "=".repeat((4 - s.length % 4) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, (c) => c.charCodeAt(0));
  };
  const post = (path, s) => fetch(path, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(s) });
  const getKey = async () => (await (await fetch(API + "/api/vapid")).json()).key;

  const ready = (async () => {
    if (inApp) return set("inapp");
    if (!can) {
      if (ios && !standalone) return set("ios");
      set("none");
      say("このブラウザは通知に対応していません。iPhoneはSafari、AndroidやパソコンはChromeなどで開いてください。");
      return;
    }
    try { reg = await navigator.serviceWorker.register("sw.js"); }
    catch (e) { set("none"); say("このページでは通知を設定できません。"); return; }
    sub = await reg.pushManager.getSubscription();
    if (sub) return set("on");
    set(Notification.permission === "denied" ? "denied" : "off");
    try { key = await getKey(); } catch (e) {}
  })();

  async function subscribe(btn) {
    if (busy) return;
    busy = true; btn.setAttribute("aria-busy", "true"); say("");
    try {
      let p;
      if (reg && key) {
        // Safariは「押した直後」でないと許可を聞けないので、ほかの処理を待たずにすぐ呼ぶ
        p = reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(key) });
      } else {
        const perm = Notification.requestPermission();
        await ready;
        if ((await perm) !== "granted") throw Object.assign(new Error("denied"), { name: "NotAllowedError" });
        if (!key) key = await getKey();
        p = reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(key) });
      }
      sub = await p;
      const r = await post(API + "/api/subscribe", sub);
      if (!r.ok) { try { await sub.unsubscribe(); } catch (e) {} sub = null; throw new Error("subscribe"); }
      set("on");
      try {
        reg.showNotification("通知をオンにしました", { body: "レバンガの試合の熱さゲージが満タンになったら、こんなふうに「いま見て！」をお知らせします。",
          icon: "icon-192.png", badge: "icon-192.png", tag: "welcome", data: { url: "./" } });
      } catch (e) {}
    } catch (e) {
      if (window.Notification && Notification.permission === "denied") {
        set("denied"); say("通知がブロックされました。ブラウザの設定で許可すると受け取れます。");
      } else if (e && e.name === "NotAllowedError") {
        say("通知が許可されませんでした。もう一度押すと設定できます。");
      } else {
        say("通知を設定できませんでした。時間をおいて、もう一度押してください。");
      }
    } finally { busy = false; btn.removeAttribute("aria-busy"); }
  }

  async function unsubscribe() {
    if (busy || !sub) return;
    busy = true;
    try {
      await post(API + "/api/unsubscribe", sub); await sub.unsubscribe(); sub = null;
      set(Notification.permission === "denied" ? "denied" : "off"); say("通知を止めました。");
    } catch (e) { say("止められませんでした。時間をおいて、もう一度押してください。"); }
    finally { busy = false; }
  }

  const guide = document.getElementById("guide");
  function openGuide(mode) {
    if (!guide) return;
    guide.dataset.mode = mode;
    const ext = guide.querySelector("[data-open-external]");
    if (ext) { ext.hidden = !line; ext.href = location.origin + location.pathname + "?openExternalBrowser=1"; }
    if (guide.showModal) guide.showModal(); else guide.setAttribute("open", "");
  }

  document.addEventListener("click", (ev) => {
    if (ev.target.closest("[data-push-off]")) { unsubscribe(); return; }
    const btn = ev.target.closest("[data-push]");
    if (!btn) return;
    const mode = body.dataset.pstate || "off";
    if (mode === "on") return;
    if (mode !== "off") { openGuide(mode); return; }
    subscribe(btn);
  });
})();

// 4) 共有・リンクのコピー
(() => {
  const canon = document.querySelector("link[rel=canonical]");
  const url = canon ? canon.href : location.href, text = document.body.dataset.sharetext || "";
  if (navigator.share) document.querySelectorAll("[data-share] span").forEach((s) => { s.textContent = "ほかのアプリで共有"; });
  const copy = async () => {
    try { await navigator.clipboard.writeText(url); return true; } catch (e) {}
    const t = document.createElement("textarea");
    t.value = url; t.setAttribute("readonly", ""); t.style.position = "fixed"; t.style.opacity = "0";
    document.body.appendChild(t); t.select();
    let ok = false; try { ok = document.execCommand("copy"); } catch (e) {}
    t.remove(); return ok;
  };
  document.addEventListener("click", async (ev) => {
    const b = ev.target.closest("[data-share],[data-copy]");
    if (!b) return;
    if ("share" in b.dataset && navigator.share) { try { await navigator.share({ title: document.title, text, url }); } catch (e) {} return; }
    const label = b.querySelector("span") || b;
    label.textContent = (await copy()) ? "コピーしました" : "コピーできませんでした";
  });
})();

// 5) 画面下の追従ボタン：通知がオフで、登録ボタンが画面に見えていないときだけ出す
(() => {
  const bar = document.getElementById("sticky");
  if (!bar) return;
  const seen = new Set();
  const update = () => {
    const mode = document.body.dataset.pstate;
    const want = bar.dataset.mode === "line" || ["off", "ios", "inapp", "denied"].includes(mode);
    const show = want && seen.size === 0 && scrollY > 240;
    bar.classList.toggle("show", show);
    bar.tabIndex = show ? 0 : -1;
    bar.setAttribute("aria-hidden", show ? "false" : "true");
  };
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((es) => {
      for (const x of es) x.isIntersecting ? seen.add(x.target) : seen.delete(x.target);
      update();
    });
    document.querySelectorAll("[data-cta-zone]").forEach((z) => io.observe(z));
  }
  addEventListener("scroll", update, { passive: true });
  addEventListener("midokoro", update);
  update();
})();

// 6) 熱さの推移：指やマウスを置いた時間の熱さを出す（←→キーでも動かせる）
(() => {
  const f = (r) => `${Math.floor(r / 60)}:${String(Math.floor(r % 60)).padStart(2, "0")}`;
  const label = (t) => {
    if (t <= 2400) { const q = Math.max(1, Math.ceil(t / 600)); return `${q}Q 残り${f(q * 600 - t)}`; }
    const k = Math.ceil((t - 2400) / 300);
    return `${k === 1 ? "OT" : "OT" + k} 残り${f(2400 + 300 * k - t)}`;
  };
  const init = (plot) => {
    if (plot.dataset.ready) return;
    plot.dataset.ready = "1";
    const d = JSON.parse(plot.dataset.curve), pts = d.pts, xmax = d.xmax;
    const area = plot.querySelector(".area"), xh = area.querySelector(".xh"), fd = area.querySelector(".fd"), tip = area.querySelector(".tip");
    if (!pts.length) return;
    let idx = pts.length - 1;
    const show = (i) => {
      idx = Math.max(0, Math.min(pts.length - 1, i));
      const [t, v] = pts[idx], x = (t / xmax) * 100;
      xh.style.left = fd.style.left = x + "%";
      fd.style.top = (100 - v) + "%";
      tip.querySelector("b").textContent = `熱さ ${v}%`;
      tip.querySelector("span").textContent = label(t);
      tip.style.left = Math.min(86, Math.max(14, x)) + "%";
      xh.hidden = fd.hidden = tip.hidden = false;
    };
    const hide = () => { xh.hidden = fd.hidden = tip.hidden = true; };
    const near = (ev) => {
      const r = area.getBoundingClientRect(), t = ((ev.clientX - r.left) / r.width) * xmax;
      let best = 0;
      for (let i = 1; i < pts.length; i++) if (Math.abs(pts[i][0] - t) < Math.abs(pts[best][0] - t)) best = i;
      show(best);
    };
    area.addEventListener("pointermove", near);
    area.addEventListener("pointerdown", near);
    area.addEventListener("pointerleave", hide);
    area.addEventListener("focus", () => show(idx));
    area.addEventListener("blur", hide);
    area.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowLeft") { show(idx - 1); ev.preventDefault(); }
      if (ev.key === "ArrowRight") { show(idx + 1); ev.preventDefault(); }
    });
  };
  const all = () => document.querySelectorAll(".plot[data-curve]").forEach(init);
  all();
  addEventListener("midokoro:live", all);
})();

// 7) 実演「満タンになると、こう届く」：画面に入ったら1回だけ動かす（もう一度見るボタンあり）
(() => {
  const demo = document.querySelector("[data-demo]");
  if (!demo || matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) return;
  const fig = demo.querySelector("[data-demo-fig]");
  demo.classList.add("ready");
  fig.firstChild.nodeValue = "0";
  const run = () => {
    demo.classList.remove("play"); void demo.offsetWidth; demo.classList.add("play");
    const t0 = performance.now(), dur = 1400;
    const step = (now) => {
      const p = Math.min(1, (now - t0) / dur);
      fig.firstChild.nodeValue = String(Math.round(p * 100));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  const io = new IntersectionObserver((es) => {
    if (es.some((x) => x.isIntersecting)) { io.disconnect(); run(); }
  }, { threshold: 0.6 });
  io.observe(demo);
  const again = document.querySelector("[data-demo-replay]");
  if (again) { again.hidden = false; again.addEventListener("click", run); }
})();
"""

# アクセス数を1回数える（Cookieなし。数えるのは表示回数と、日ごとのおおよその訪問者数だけ）
BEACON = """<script>try{navigator.sendBeacon(document.body.dataset.api+"/api/hit",new Blob(["{}"],{type:"text/plain"}))}catch(e){}</script>"""

e = html.escape

# 背景のコート線（一般的な図形。公式の意匠は使わない）
COURT = ('<svg class="court" viewBox="0 0 200 200" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="3">'
         '<circle cx="100" cy="100" r="96"/><circle cx="100" cy="100" r="30"/>'
         '<path d="M4 100H196"/><path d="M40 4v40a60 60 0 0 0 120 0V4"/></svg>')

SHARE_ICON = ('<svg class="shareico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
              'stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="共有ボタン">'
              '<path d="M12 3v12"/><path d="M8 7l4-4 4 4"/>'
              '<path d="M7 10H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2h-1"/></svg>')


# ---------- 熱さ ----------

def heat_pct(score: int | float | None) -> int:
    """見どころ度 → 熱さ（%）。通知ライン（HIGH）で満タンの100%"""
    if score is None:
        return 0
    return max(0, min(100, math.floor(score * 100 / HIGH)))


def clock_label(t: float) -> str:
    """経過秒 → 「4Q 残り2:00」"""
    f = lambda r: f"{int(r // 60)}:{int(r % 60):02d}"
    if t <= 2400:
        q = max(1, math.ceil(t / 600))
        return f"{q}Q 残り{f(q * 600 - t)}"
    k = math.ceil((t - 2400) / 300)
    return f"{'OT' if k == 1 else f'OT{k}'} 残り{f(2400 + 300 * k - t)}"


def clock_seconds(c: str) -> int | None:
    """判定の時計表記「4Q 2:58」「OT 1:05」「OT2 0:30」→ 経過秒"""
    m = re.fullmatch(r"(\d)Q (\d+):(\d{2})", c or "")
    if m:
        q, rest = int(m.group(1)), int(m.group(2)) * 60 + int(m.group(3))
        return (q - 1) * 600 + 600 - rest
    m = re.fullmatch(r"OT(\d*) (\d+):(\d{2})", c or "")
    if m:
        k, rest = int(m.group(1) or 1), int(m.group(2)) * 60 + int(m.group(3))
        return 2400 + (k - 1) * 300 + 300 - rest
    return None


def nice_clock(c: str | None) -> str:
    """判定の時計表記を、ページの表記（4Q 残り2:58）にそろえる"""
    t = clock_seconds(c or "")
    return clock_label(t) if t is not None else (c or "")


def bin_heat(heat: list, step: int = 60) -> list[list[int]]:
    """グラフ用に、step 秒ごとの最大値にまとめる（細かいギザギザを減らし、山はそのまま残す）"""
    out: dict[int, int] = {}
    for t, s in heat:
        k = int(math.ceil(t / step) * step)
        out[k] = max(out.get(k, 0), int(s))
    return [[k, v] for k, v in sorted(out.items())]


def full_moments(heat: list) -> list[int]:
    """満タンになった瞬間（満タンが続く区間の最初）"""
    out, prev = [], False
    for t, s in heat:
        full = heat_pct(s) >= 100
        if full and not prev:
            out.append(int(t))
        prev = full
    return out


def gauge(pct: int, extra: str = "") -> str:
    lit = pct * SEGMENTS // 100
    segs = "".join(
        (f'<i class="on{" lead" if i == lit - 1 and lit < SEGMENTS else ""}" style="--i:{i}"></i>' if i < lit
         else f'<i style="--i:{i}"></i>') for i in range(SEGMENTS))
    return (f'<div class="gauge{extra}" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{pct}" '
            f'aria-label="熱さ {pct}%（100%で通知）">{segs}</div>')


def readout(pct: int, label: str = "熱さ", goal: str = "満タンで通知", attr: str = "") -> str:
    return (f'<p class="readout"><span class="lbl">{e(label)}</span><span class="fig"{attr}>{pct}<small>%</small></span>'
            f'<span class="goal">{e(goal)}</span></p>')


# ---------- 部品 ----------

def _btn(label: str, url: str | None, quiet: bool = False, cls: str = "") -> str:
    if not url:
        return ""
    cls = cls or ("btn quiet" if quiet else "btn")
    return f'<a class="{cls}" href="{e(url)}" target="_blank" rel="noopener">{e(label)}</a>'


def _start(g: dict) -> datetime | None:
    d, s = g.get("date") or "", g.get("start") or ""
    if not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and re.fullmatch(r"\d{1,2}:\d{2}", s)):
        return None
    return datetime.strptime(f"{d} {s}", "%Y-%m-%d %H:%M")


def _count(updated: str | None, g: dict) -> str:
    """試合開始までのカウントダウン（最初の表示はページを作った時刻で計算し、あとはブラウザで1秒ごとに進める）"""
    st = _start(g)
    if not st:
        return ""
    text = "開始まで"
    try:
        mins = int((st - datetime.strptime(updated or "", "%Y-%m-%d %H:%M")).total_seconds() // 60)
        if mins <= 0:
            text = "まもなく開始"
        else:
            d, rest = divmod(mins, 1440)
            h, m = divmod(rest, 60)
            text = (f"開始まで <b>{d}</b>日<b>{h}</b>時間<b>{m:02d}</b>分" if d
                    else f"開始まで <b>{h:02d}:{m:02d}:00</b>")
    except ValueError:
        pass
    return f'<p class="count" data-count="{st:%Y-%m-%dT%H:%M}:00+09:00">{text}</p>'


def _nextgame(g: dict, chip: str, updated: str | None) -> str:
    return (f'<div class="nextgame"><span class="chip">{e(chip)}</span>{_count(updated, g)}'
            f'<p class="slot"><span class="date">{e(g["md"])}</span><span class="wd">{e(g["wd"])}曜日</span>'
            f'<span class="time">{e(g["start"])}</span></p>'
            f'<p class="vs">vs {e(g["opponent"])}<small>{e(g["place"])}</small></p></div>')


def _panel(inner: str, hot: bool = False) -> str:
    return f'<div class="panel{" hot" if hot else ""}">{inner}</div>'


def panel(state: dict) -> tuple[str, str]:
    """ファーストビューの熱さゲージ（HTML, ページタイトル）"""
    g, up = state.get("today"), state.get("updated")
    if g and g["status"] == "試合中":
        lv, clock, pct = g.get("level"), g.get("clock"), heat_pct(g.get("meter"))
        hot = lv == "高"
        ctx = (f'<p class="ctx"><span class="chip live">試合中</span>'
               f'{f"<span>{e(nice_clock(clock))}</span>" if clock else ""}<span>vs {e(g["opponent"])}</span></p>')
        word = "いま見て！" if hot else ("そろそろ" if lv == "中" else "まだ大丈夫")
        goal = "満タン！" if hot else f"満タンまで あと{100 - pct}%"
        say = g.get("text") or ("" if hot else "ゲージが満タンになったら、すぐにお知らせします。")
        inner = (f'{ctx}<p class="word">{word}</p>{readout(pct, goal=goal)}{gauge(pct)}'
                 f'{f"<p class=say>{e(say)}</p>" if say else ""}'
                 f'{_btn("試合を見る（B.LEAGUE公式）", g["url"], quiet=not hot)}')
        title = (f'いま見て！ レバンガ vs {g["opponent"]}（熱さ100%）｜見どころなう（非公式）' if hot
                 else f'熱さ{pct}% レバンガ vs {g["opponent"]}｜見どころなう（非公式）')
        return _panel(inner, hot), title
    if g and g["status"] in ("予定", "まもなく"):
        chip = "まもなく試合開始" if g["status"] == "まもなく" else "今日の試合"
        inner = (f'{_nextgame(g, chip, up)}{readout(0, goal="満タンで通知")}{gauge(0)}'
                 '<p class="quiet-note">試合が始まると、ゲージが動きだします。</p>')
        return _panel(inner), TITLE
    if g and g["status"] == "終了":
        heat = g.get("heat") or []
        peak = heat_pct(max((s for _, s in heat), default=0))
        n = len(g["alerts"])
        if n:
            say = f"ゲージが満タンになり、「いま見て！」を{n}回お知らせしました。"
        elif g.get("tracked"):
            say = "この試合は、ゲージが満タンになる場面はありませんでした。"
        else:
            say = ""
        link = (_btn("ハイライト動画を見る", g.get("highlight"))
                or _btn("試合の記録を見る（B.LEAGUE公式）", g["url"], quiet=True))
        inner = (f'<p class="ctx"><span class="chip">試合終了</span><span>vs {e(g["opponent"])}</span></p>'
                 f'<p class="word">試合終了</p>'
                 f'{readout(peak, label="この試合の最高", goal="満タン＝通知") if heat else ""}{gauge(peak) if heat else ""}'
                 f'{f"<p class=say>{e(say)}</p>" if say else ""}{link}')
        return _panel(inner), TITLE
    nxt = (state.get("next") or [None])[0]
    if nxt:
        inner = (f'{_nextgame(nxt, "次の試合", up)}{readout(0, goal="満タンで通知")}{gauge(0)}'
                 '<p class="quiet-note">試合が始まると、ゲージが動きだします。</p>')
        return _panel(inner), TITLE
    return _panel('<div class="nextgame"><span class="chip">次の試合</span>'
                  '<p class="vs">日程が決まりしだい表示します</p></div>'
                  f'{readout(0, goal="満タンで通知")}{gauge(0)}'), TITLE


def heat_chart(heat: list, marks: list[int], title: str, key: str) -> str:
    """熱さの推移の折れ線（1系列）。marks は●を付ける経過秒"""
    if not heat:
        return ""
    end = max(t for t, _ in heat)
    xmax = 2400 if end <= 2400 else 2400 + 300 * math.ceil((end - 2400) / 300)
    pts = [[min(int(t), xmax), heat_pct(s)] for t, s in bin_heat(heat)]
    X = lambda t: 1000 * t / xmax
    line = "M0,100 " + " ".join(f"L{X(t):.1f},{100 - v}" for t, v in pts)
    area = f"{line} L{X(pts[-1][0]):.1f},100 Z"
    quarters = [600, 1200, 1800] + list(range(2400, xmax, 300))   # クォーターの区切り（延長は5分ごと）
    vlines = "".join(f'<line class="gl" x1="{X(t):.1f}" x2="{X(t):.1f}" y1="0" y2="100"/>' for t in quarters)
    names = ["1Q", "2Q", "3Q", "4Q"] + [("OT" if k == 1 else f"OT{k}") for k in range(1, (xmax - 2400) // 300 + 1)]
    bounds = [0, 600, 1200, 1800, 2400] + list(range(2700, xmax + 1, 300))
    xlab = "".join(f'<span style="left:{100 * (a + b) / 2 / xmax:.2f}%">{n}</span>'
                   for n, a, b in zip(names, bounds, bounds[1:]))
    dots = "".join(f'<span class="mk" style="left:{100 * t / xmax:.2f}%;top:0%" title="{e(clock_label(t))} 満タン"></span>'
                   for t in marks if 0 <= t <= xmax)
    peak_v = max(v for _, v in pts)
    first_full = marks[0] if marks else None
    aria = (f"熱さの推移。{clock_label(first_full)}にゲージが満タン。" if first_full is not None
            else f"熱さの推移。最高{peak_v}%。")
    rows = "".join(f"<tr><td>{e(clock_label(t))}</td><td>{v}%</td></tr>" for t, v in pts)
    data = e(json.dumps({"pts": pts, "xmax": xmax}, separators=(",", ":")))
    return (f'<figure class="curve"><figcaption><b>{e(title)}</b>'
            f'{f"<span class=key><i></i>{e(key)}</span>" if marks else ""}</figcaption>'
            f'<div class="plot" data-curve="{data}">'
            '<div class="ylab"><span style="top:0%">100%</span><span style="top:50%">50%</span><span style="top:100%">0%</span></div>'
            f'<div class="area" tabindex="0" role="img" aria-label="{e(aria)}">'
            '<svg viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true">'
            '<line class="gl" x1="0" x2="1000" y1="50" y2="50"/><line class="gl" x1="0" x2="1000" y1="100" y2="100"/>'
            f'{vlines}<line class="full" x1="0" x2="1000" y1="0" y2="0"/>'
            f'<path class="ar" d="{area}"/><path class="ln" d="{line}"/></svg>'
            '<span class="flabel">満タン（通知）</span>'
            f'{dots}<span class="xh" hidden></span><span class="fd" hidden></span>'
            '<div class="tip" hidden><b></b><span></span></div></div>'
            f'<div class="xlab">{xlab}</div></div>'
            f'<details class="tbl"><summary>表で見る</summary><table><thead><tr><th>試合時間</th><th>熱さ</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></details></figure>')


def _alert_marks(g: dict) -> list[int]:
    ts = [clock_seconds(a.get("clock", "")) for a in g.get("alerts") or []]
    return [t for t in ts if t is not None]


def _list(items: list[dict], plays: list[dict], empty: str, limit: int = 8) -> str:
    if items:
        rows = "".join(f'<li><span class="clock">{e(nice_clock(a.get("clock")))}</span>'
                       f'<span>{e(a["text"])}</span><span class="when">{e(a["time"])}</span></li>' for a in items)
        body = f'<h3 class="sub">「いま見て！」の場面</h3><ol class="moments">{rows}</ol>'
    else:
        body = f'<p class="note">{e(empty)}</p>' if empty else ""
    if plays:                                # レバンガの好プレー（通知はしない記録）。新しい順に limit 件まで
        rows = "".join(f'<li><span class="clock">{e(nice_clock(p["clock"]))}</span><span>{e(p["text"])}</span><span></span></li>'
                       for p in plays[::-1][:limit])
        more = f'<p class="note">ほか{len(plays) - limit}件。ハイライト動画でまとめて見られます。</p>' if len(plays) > limit else ""
        body += f'<h3 class="sub">レバンガの好プレー</h3><ol class="moments">{rows}</ol>{more}'
    return body


def today_section(state: dict) -> str:
    """試合の日：今日の熱さの推移と見どころ（ファーストビューのすぐ下）"""
    g = state["today"]
    heat = g.get("heat") or []
    chart = heat_chart(heat, _alert_marks(g), f'今日の熱さの推移　vs {g["opponent"]}',
                       "「いま見て！」をお知らせした場面")
    body = _list(g["alerts"], g.get("plays") or [], "" if heat else "ゲージが満タンになったら、ここに残ります。")
    return f'<section><div class="wrap"><h2>今日の試合の熱さ</h2>{chart}{body}</div></section>'


def last_section(state: dict) -> str:
    """試合のない日：前回の試合で、ゲージがどう動いたか"""
    g = state.get("last")
    if not g:
        return ""
    heat = g.get("heat") or []
    hl = _btn("ハイライト動画を見る", g.get("highlight"), quiet=True)
    links = f'<div class="links">{hl}</div>' if hl else ""
    meta = f'{g["md"]}（{g["wd"]}） vs {g["opponent"]}・{g["place"]}'
    if not heat:
        if not links:
            return ""
        return f'<section><div class="wrap"><h2>前回の試合</h2><p class="note">{e(meta)}</p>{links}</div></section>'
    tracked = bool(g.get("tracked"))
    marks = _alert_marks(g) if tracked else full_moments(heat)
    peak = max(heat_pct(s) for _, s in heat)
    if marks:
        head = f'前回の{g["opponent"]}戦は、{clock_label(marks[0])}にゲージが満タン'
    else:
        head = f'前回の{g["opponent"]}戦は、最高{peak}%でした'
    chart = heat_chart(heat, marks, meta, "「いま見て！」をお知らせした場面" if tracked else "ゲージが満タンになった場面")
    note = ("" if tracked else
            '<p class="fine">見どころなうの公開前の試合のため、通知は送っていません。いまの判定ルールで、試合の記録から計算した推移です。</p>')
    body = _list(g["alerts"] if tracked else [], g.get("plays") or [], "", limit=5)
    return (f'<section><div class="wrap"><h2>{e(head)}</h2>{chart}{note}{links}{body}</div></section>')


BADGES = '<ul class="badges"><li>無料</li><li>会員登録・アプリ不要</li><li>試合のない日は届かない</li></ul>'


def cta() -> str:
    """登録ボタン一式（ファーストビューと最後の2か所に置く）"""
    if PUSH_ENABLED:
        line = _btn("LINEで受け取る", LINE_URL, quiet=True) if LINE_URL else ""
        return ('<div class="cta-area" data-cta-zone>'
                '<button class="btn big pushbtn off-only" type="button" data-push>無料で通知を受け取る</button>'
                '<div class="on-box on-only" role="status">この端末は通知オンです。満タンになったらお知らせします。'
                '<button class="link" type="button" data-push-off>止める</button></div>'
                '<p class="pushmsg" data-push-msg role="status" aria-live="polite"></p>'
                '<p class="micro off-only">「許可」を選ぶだけ。会員登録もアプリもいりません。</p>'
                f'{BADGES}{line}</div>')
    if LINE_URL:                               # Webプッシュなし：LINEだけで受け取る
        return ('<div class="cta-area" data-cta-zone>'
                + _btn("LINEで受け取る（無料）", LINE_URL, cls="btn big") +
                '<p class="micro">ゲージが満タンになったら、LINEでお知らせします（1試合1回）。</p>'
                f'{BADGES}</div>')
    return '<div class="cta-area"><p class="micro">このページは数分おきに更新されます。</p></div>'


def first_view(state: dict) -> tuple[str, str]:
    top, title = panel(state)
    return (f'<div class="first wrap wide"><div class="copy">'
            '<h1 class="hook"><span>レバンガ北海道の試合、</span><span>いまどれくらい熱い？</span></h1></div>'
            f'<div class="now" id="live-top" data-live>{top}</div>'
            '<div class="text"><p class="hook-sub">接戦・逆転・終盤の山場ほど、ゲージがたまります。'
            '満タンになったら、スマホに「いま見て！」が届きます。</p></div>'
            f'{cta()}</div>'), title


def demo() -> str:
    return ('<section><div class="wrap"><h2>満タンになると、こう届く</h2><div class="demo" data-demo>'
            f'<div class="panel">{readout(100, goal="満タンで通知", attr=" data-demo-fig")}{gauge(100)}</div>'
            '<figure class="phone"><div class="toast"><span class="ic" aria-hidden="true">見</span>'
            '<span class="ap"><span>見どころなう</span><span>いま</span></span>'
            '<b>いま見て！ 佐賀戦</b><span>第4Q残り38秒、1ポゼッション差。レバンガが勝ち越し！</span></div>'
            '<figcaption>通知のイメージ</figcaption></figure>'
            '<button class="link replay" type="button" data-demo-replay hidden>もう一度見る</button></div></div></section>')


FIT = ('<section><div class="wrap"><h2>こんなレバンガファンに</h2><ul class="fit">'
       '<li>平日夜の試合は、仕事や家事で最初から見られない</li>'
       '<li>試合の流れを、ずっと追いかけている時間はない</li>'
       '<li>それでも、接戦の終盤と逆転の瞬間だけは見逃したくない</li>'
       '</ul></div></section>')

# 判定ルール v1.2 の過去60試合での試算（1試合平均1.23回、5点差以内で決着した23試合はすべて通知、20点差以上の13試合は0件）
PROOF = ('<section><div class="wrap"><h2>満タンになるのは、本当に熱い試合だけ</h2><div class="stats">'
         '<div class="stat"><b>1.2<small>回</small></b><span>1試合あたりの<br>通知（平均）</span></div>'
         '<div class="stat"><b>23<small>/23</small></b><span>5点差以内で決着<br>した試合で満タン</span></div>'
         '<div class="stat"><b>0<small>回</small></b><span>20点差以上の<br>大差の試合</span></div>'
         '</div><p class="fine">過去シーズンのレバンガの60試合に、いまの判定ルールを当てはめた試算です。'
         '実際の回数は試合によって変わります。</p></div></section>')

# 判定ルール v1.2 では、満タン（見どころ度70以上）になるのは第4Q・延長だけ（第3Qまでは最大でも45）
FLOW = ('<section><div class="wrap"><h2>試合の日、ゲージはこう動く</h2><ol class="flow">'
        '<li><span class="dot" aria-hidden="true">…</span><div><span class="when">第1Q〜第3Q</span>'
        '<b>満タンにはなりません</b><p>点差が動いてもゲージは控えめ。通知は届かないので、いつも通りに過ごしてください。</p></div></li>'
        '<li class="hot"><span class="dot" aria-hidden="true">!</span><div><span class="when">第4Q・延長</span>'
        '<b>接戦なら一気にたまる</b><p>逆転・同点や、競ったまま残り3分に入ると満タンに。「いま見て！」が届きます。</p></div></li>'
        '<li class="hot"><span class="dot" aria-hidden="true">!</span><div><span class="when">最後の1分</span>'
        '<b>土壇場も、もう一度</b><p>満タンのまま終了間際に逆転・同点・勝ち越しがあれば、改めてお知らせします。</p></div></li>'
        '<li><span class="dot" aria-hidden="true">✓</span><div><span class="when">試合のあと</span>'
        '<b>熱さの推移が残ります</b><p>このページで、試合のどこが熱かったかを振り返れます。</p></div></li>'
        '</ol><p class="fine">通知をタップすると、B.LEAGUE公式の試合ページが開きます。</p></div></section>')

STEPS = ('<section><div class="wrap"><h2>はじめ方は3ステップ</h2><ol class="steps">'
         '<li><div><b>ボタンを押す</b><span>会員登録もアプリのインストールもいりません</span></div></li>'
         '<li><div><b>通知を「許可」する</b><span>iPhoneはホーム画面に追加してから。やり方はボタンを押すと出ます</span></div></li>'
         '<li><div><b>あとは待つだけ</b><span>ゲージが満タンになったら「いま見て！」が届きます</span></div></li>'
         '</ol></div></section>')


def schedule(state: dict) -> str:
    rows = "".join(
        f'<li><span class="day"><span class="num">{e(g["md"])}</span><small>{e(g["wd"])}曜日</small></span>'
        f'<span class="opp">vs {e(g["opponent"])}<small>{e(g["place"])}</small></span>'
        f'<span class="start">{e(g["start"])}</span></li>' for g in state.get("next") or [])
    lst = (f'<ul class="games">{rows}</ul>' if rows
           else '<p class="note">この先の試合は、日程が決まりしだい表示します。</p>')
    return f'<section><div class="wrap"><h2>レバンガ北海道の試合日程</h2>{lst}</div></section>'


def share() -> str:
    u, t = quote(SITE_URL, safe=""), quote(SHARE_TEXT, safe="")
    return ('<section><div class="wrap"><h2>レバンガ仲間に教える</h2>'
            '<p class="note">一緒に応援している人に、教えてあげてください。</p><div class="share-row">'
            f'<a class="btn sh" href="https://social-plugins.line.me/lineit/share?url={u}" target="_blank" rel="noopener">'
            '<i class="d-line"></i>LINEで送る</a>'
            f'<a class="btn sh" href="https://twitter.com/intent/tweet?text={t}&amp;url={u}" target="_blank" rel="noopener">'
            '<i class="d-x"></i>Xでポスト</a>'
            '<button class="btn sh" type="button" data-share><i></i><span>リンクをコピー</span></button>'
            '</div></div></section>')


FAQ_ITEMS = [
    ("熱さゲージとは何ですか？",
     "点差・残り時間・逆転や同点などの試合の流れから、いまどれくらい盛り上がっているかを0〜100%で表したものです。"
     "100%（満タン）になると「いま見て！」をお知らせします。"),
    ("無料ですか？", "はい、無料です。会員登録やアプリのインストールもいりません。"),
    ("どんなときに通知が届きますか？",
     "熱さゲージが満タンになったときです。満タンになるのは第4Qと延長戦の接戦で、逆転・同点になったときや、"
     "競ったまま残り3分に入ったときなどです。1試合おおむね1〜3回で、大差の試合や試合のない日は届きません。"),
    ("ゲージはどれくらいの間隔で動きますか？",
     "試合中、このページのゲージは数分おきに新しくなります。通知は、満タンになった直後に届きます。"),
    ("iPhoneでも使えますか？",
     "使えます（iOS 16.4以降）。Safariでこのページを開き、共有ボタンから「ホーム画面に追加」を選んだあと、"
     "ホーム画面のアイコンから開いて「無料で通知を受け取る」を押してください。"),
    ("通知をタップするとどうなりますか？", "B.LEAGUE公式の試合ページが開きます。映像や記録は公式でご覧ください。"),
    ("通知を止めるには？", "このページの「止める」を押すか、ブラウザの設定でこのサイトの通知をオフにしてください。"),
    ("公式のサービスですか？", "いいえ。レバンガ北海道を応援する個人の非公式サービスで、B.LEAGUE・レバンガ北海道とは関係ありません。"),
    ("登録した情報は何に使いますか？",
     "保存するのは、ブラウザが発行する通知の宛先と、端末の大まかな種類（iPhone・Android・パソコン）だけで、通知を送るためにだけ使います。"
     "名前やメールアドレスは受け取りません。アクセス数はCookieを使わずに数え、IPアドレスそのものも保存しません。"),
]


def faq() -> str:
    items = "".join(f'<details><summary>{e(q)}</summary><p>{e(a)}</p></details>' for q, a in FAQ_ITEMS)
    return f'<section class="faq"><div class="wrap"><h2>よくある質問</h2>{items}</div></section>'


def final() -> str:
    return (f'<section class="final">{COURT}<div class="wrap">'
            '<h2><span>次の試合から、</span><span>満タンの瞬間を見逃さない。</span></h2>'
            '<p class="hook-sub">試合のない日は届きません。いつでも止められます。</p>'
            f'{cta()}</div></section>')


def sticky() -> str:
    if PUSH_ENABLED:
        return ('<button class="sticky pushbtn off-only" id="sticky" type="button" data-push data-short '
                'aria-hidden="true" tabindex="-1">満タンで「いま見て！」を受け取る</button>')
    if LINE_URL:
        return (f'<a class="sticky" id="sticky" data-mode="line" href="{e(LINE_URL)}" target="_blank" rel="noopener" '
                'aria-hidden="true" tabindex="-1">LINEで「いま見て！」を受け取る</a>')
    return ""


def guide() -> str:
    line = f'<div class="row">{_btn("LINEで受け取る", LINE_URL, cls="btn big")}</div>' if LINE_URL else ""
    return ('<dialog class="guide" id="guide" aria-label="通知の受け取り方">'
            '<div class="g g-ios"><h2>iPhoneで通知を受け取るには</h2><ol>'
            f'<li><span>Safariの<b>共有ボタン</b>{SHARE_ICON}をタップ</span></li>'
            '<li><span><b>「ホーム画面に追加」</b>を選んで追加</span></li>'
            '<li><span>ホーム画面の<b>「見どころなう」</b>から開いて、<b>「無料で通知を受け取る」</b>を押す</span></li>'
            '</ol><p class="note">iOS 16.4以降で使えます。</p></div>'
            '<div class="g g-inapp"><h2>アプリの中のブラウザでは受け取れません</h2>'
            '<p>LINEなどのアプリの中で開いたページでは、通知を受け取れません。SafariやChromeで開き直してから、もう一度押してください。</p>'
            '<div class="row"><a class="btn big" data-open-external href="./?openExternalBrowser=1" target="_blank" rel="noopener">ブラウザで開く</a>'
            '<button class="btn quiet" type="button" data-copy><span>リンクをコピー</span></button></div>'
            '<p class="note">開けないときは、画面の「…」メニューから「ブラウザで開く」を選んでください。</p></div>'
            '<div class="g g-denied"><h2>通知がブロックされています</h2>'
            '<p>ブラウザの設定で、このサイト（levangamidokoro.github.io）の通知を「許可」に変えてから、もう一度押してください。</p>'
            '<p class="note">アドレスバーの鍵や設定のアイコンから変えられます。</p></div>'
            '<div class="g g-none"><h2>このブラウザは通知に対応していません</h2>'
            f'<p>iPhoneはSafari（iOS 16.4以降）、AndroidやパソコンはChromeなどで開くと受け取れます。</p>{line}</div>'
            '<form method="dialog" class="row"><button class="btn quiet" type="submit">閉じる</button></form></dialog>')


def head_meta() -> str:
    out = [f'<link rel="canonical" href="{e(SITE_URL)}">',
           '<meta property="og:type" content="website">',
           '<meta property="og:site_name" content="見どころなう">',
           f'<meta property="og:title" content="{e(TITLE)}">',
           f'<meta property="og:description" content="{e(OG_DESC)}">',
           f'<meta property="og:url" content="{e(SITE_URL)}">',
           f'<meta property="og:image" content="{e(SITE_URL)}og.png">',
           '<meta property="og:image:width" content="1200">',
           '<meta property="og:image:height" content="630">',
           '<meta property="og:image:alt" content="レバンガ北海道の試合、いまどれくらい熱い？ 熱さゲージが満タンで「いま見て！」">',
           '<meta property="og:locale" content="ja_JP">',
           '<meta name="twitter:card" content="summary_large_image">']
    g = os.environ.get("GOOGLE_SITE_VERIFICATION", "").strip()
    b = os.environ.get("BING_SITE_VERIFICATION", "").strip()
    if g:
        out.append(f'<meta name="google-site-verification" content="{e(g)}">')
    if b:
        out.append(f'<meta name="msvalidate.01" content="{e(b)}">')
    ld = {"@context": "https://schema.org", "@type": "WebSite", "name": "見どころなう",
          "alternateName": ["見どころなう レバンガ北海道版", "見どころなう（非公式）"],
          "url": SITE_URL, "inLanguage": "ja", "description": DESC}
    out.append('<script type="application/ld+json">'
               + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>")
    return "\n".join(out)


PAGE = """<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<meta name="description" content="{desc}">
{meta}
<link rel="icon" type="image/png" sizes="192x192" href="icon-192.png">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icon-180.png">
<meta name="theme-color" content="#14290F">
<meta name="apple-mobile-web-app-capable" content="yes">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{fonts}">
<style>{css}</style>
</head>
<body data-api="{api}" data-sharetext="{share_text}">
<div class="poster">{court}
<header class="site wrap wide"><a class="brand" href="./"><span class="mark">見どころなう</span><span class="edition">レバンガ北海道版（非公式）</span></a><span class="on-badge">通知オン</span></header>
{first}
</div>
<main>
<div id="live-mid" data-live>{mid}</div>
{demo}
<div id="live-low" data-live>{low}</div>
{fit}
{proof}
{flow}
{steps}
{schedule}
{share}
{faq}
{final}
</main>
<footer class="wrap">
<p>レバンガ北海道を応援する個人の非公式サービスです。B.LEAGUE・レバンガ北海道とは関係ありません。</p>
<p>試合の映像と記録はB.LEAGUE公式でご覧ください。熱さの判定は試験運用中です。</p>
<p>最終更新 {updated}</p>
</footer>
{sticky}
{guide}
<script>{script}</script>{beacon}
</body></html>
"""


def render(state: dict) -> str:
    first, title = first_view(state)
    today = state.get("today")
    game_day = bool(today and today["status"] in ("試合中", "終了", "まもなく"))
    return PAGE.format(title=e(title), desc=e(DESC), meta=head_meta(), fonts=FONTS, css=CSS,
                       api=e(API_BASE), share_text=e(SHARE_TEXT), court=COURT, first=first,
                       mid=today_section(state) if game_day else "", demo=demo(),
                       low="" if game_day else last_section(state), fit=FIT, proof=PROOF, flow=FLOW,
                       steps=STEPS, schedule=schedule(state), share=share(), faq=faq(), final=final(),
                       updated=e(state.get("updated", "-")), sticky=sticky(), guide=guide(),
                       script=SCRIPT, beacon=BEACON if API_BASE else "")


def sitemap(state: dict) -> str:
    day = (state.get("updated") or "")[:10]
    lastmod = f"<lastmod>{day}</lastmod>" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) else ""
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"  <url><loc>{e(SITE_URL)}</loc>{lastmod}</url>\n</urlset>\n")


def robots() -> str:
    return f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n"


def _write_if_changed(path: Path, text: str) -> None:
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)


def build() -> Path:
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    OUT_DIR.mkdir(exist_ok=True)
    for f in STATIC_DIR.glob("*"):                 # 通知用の部品・アイコン・OGP画像・利用状況ページをコピー
        if not f.is_file():
            continue
        dst = OUT_DIR / f.name
        if f.name == "stats.html":                 # 受付窓口のURLを埋め込む
            _write_if_changed(dst, f.read_text(encoding="utf-8").replace("__API__", html.escape(API_BASE)))
        elif not dst.exists() or dst.read_bytes() != f.read_bytes():   # 中身で比べる（時刻はあてにならない）
            shutil.copyfile(f, dst)
    _write_if_changed(OUT_DIR / "sitemap.xml", sitemap(state))
    _write_if_changed(OUT_DIR / "robots.txt", robots())
    out = OUT_DIR / "index.html"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(render(state), encoding="utf-8")
    tmp.replace(out)
    return out


if __name__ == "__main__":
    print(build())

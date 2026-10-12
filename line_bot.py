"""
見どころなう 受付サーバー（LINE公式アカウント ＋ Webプッシュの登録受付）

- /callback        LINEからのメッセージ
- /api/vapid       Webプッシュの公開鍵
- /api/subscribe   Webプッシュの登録・/api/unsubscribe 解除

- 返信（無料・通数に数えない）：「見どころ」「今日」を含むメッセージに、今日の試合と見どころを返す
- 友だち追加時：あいさつを返す
- プッシュ（通数に数える）：broadcast() を収集プログラムが呼ぶ。対象チームの試合で1試合1回まで

起動（サーバー上で）
    環境変数 LINE_CHANNEL_SECRET と LINE_CHANNEL_ACCESS_TOKEN を設定
    python line_bot.py      → 127.0.0.1:8080 で待ち受け（外からはCaddy経由で /callback に届く）
"""

import base64
import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests

STATE_FILE = Path("data/state.json")
SITE_URL = os.environ.get("SITE_URL", "")
API = "https://api.line.me/v2/bot/message"


def _token() -> str:
    t = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not t:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN が未設定")
    return t


def _post(path: str, body: dict) -> None:
    res = requests.post(f"{API}/{path}", timeout=15, json=body,
                        headers={"Authorization": f"Bearer {_token()}"})
    res.raise_for_status()


def broadcast(text: str) -> None:
    """友だち全員に送る（無料枠は月200通。人数分カウントされる）"""
    _post("broadcast", {"messages": [{"type": "text", "text": text[:4900]}]})


def reply(reply_token: str, text: str) -> None:
    _post("reply", {"replyToken": reply_token, "messages": [{"type": "text", "text": text[:4900]}]})


def today_summary() -> str:
    """「今日の見どころ」への返信（レバンガ北海道の試合だけ）"""
    if not STATE_FILE.exists():
        return "試合の情報をまだ取得できていません。しばらくしてから、もう一度送ってください。"
    st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    g, lines = st.get("today"), []
    if g:
        lines.append(f'今日 {g["start"]} vs {g["opponent"]}　{g["place"]}')
        if g["status"] == "試合中":
            word = {"高": "いま見て！", "中": "そろそろ"}.get(g.get("level"), "まだ大丈夫")
            lines.append(f'{word}　{g.get("clock") or "試合中"}')
            if g.get("level") in ("高", "中") and g.get("text"):
                lines.append(g["text"])
            lines.append(g["url"])
        elif g["status"] == "終了":
            lines.append("試合終了")
        elif g["status"] == "まもなく":
            lines.append("まもなく試合開始")
        items = g.get("alerts") or []
        if items:
            lines.append("")
            lines.append("今日の見どころ")
            lines += [f'{a.get("clock", "")}　{a["text"]}（{a["time"]}）' for a in items]
        plays = g.get("plays") or []
        if plays:
            lines.append("")
            lines.append("レバンガの好プレー（新しい順）")
            lines += [f'{p["clock"]}　{p["text"]}' for p in plays[::-1][:5]]
            if len(plays) > 5:
                lines.append(f"ほか{len(plays) - 5}件")
    else:
        lines.append("今日は試合がありません。")
    nxt = st.get("next") or []
    if nxt:
        n = nxt[0]
        lines.append("")
        lines.append(f'次の試合 {n["md"]}（{n["wd"]}）{n["start"]} vs {n["opponent"]}　{n["place"]}')
    if SITE_URL:
        lines.append("")
        lines.append(f"くわしく：{SITE_URL}")
    return "\n".join(lines)


GREETING = ("友だち追加ありがとうございます。見どころなう レバンガ北海道版です（非公式）。\n"
            "レバンガの試合が盛り上がった瞬間に、1試合1回お知らせします（試験運用中）。\n"
            "「今日の見どころ」と送ると、今日の試合の様子をお返しします。")


def valid_signature(body: bytes, signature: str) -> bool:
    secret = os.environ.get("LINE_CHANNEL_SECRET", "").encode()
    digest = hmac.new(secret, body, hashlib.sha256).digest()
    return bool(secret) and hmac.compare_digest(base64.b64encode(digest).decode(), signature or "")


def handle_events(events: list[dict]) -> None:
    for ev in events:
        token = ev.get("replyToken")
        if not token:
            continue
        if ev.get("type") == "follow":
            reply(token, GREETING)
        elif ev.get("type") == "message" and ev.get("message", {}).get("type") == "text":
            text = ev["message"]["text"]
            if "見どころ" in text or "今日" in text:
                reply(token, today_summary())
            else:
                reply(token, "「今日の見どころ」と送ると、今日の試合をお返しします。")


MAX_BODY = 64 * 1024


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, obj) -> None:
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/vapid":
            import webpush
            return self._json(200, {"key": webpush.public_key()})
        self.send_response(404); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY:
            self.send_response(413); self.end_headers(); return
        body = self.rfile.read(length)

        if self.path in ("/api/subscribe", "/api/unsubscribe"):
            import webpush
            try:
                sub = json.loads(body)
            except ValueError:
                return self._json(400, {"ok": False})
            try:
                if self.path == "/api/subscribe":
                    ok = isinstance(sub, dict) and webpush.add(sub)
                    return self._json(200 if ok else 400, {"ok": ok})
                webpush.remove(str(sub.get("endpoint", "")) if isinstance(sub, dict) else "")
                return self._json(200, {"ok": True})
            except Exception as e:
                print("登録処理の失敗:", e, flush=True)
                return self._json(500, {"ok": False})

        if self.path != "/callback":
            self.send_response(404); self.end_headers(); return
        if not valid_signature(body, self.headers.get("X-Line-Signature")):
            self.send_response(403); self.end_headers(); return
        self.send_response(200); self.end_headers()
        try:
            handle_events(json.loads(body).get("events", []))
        except Exception as e:
            print("処理失敗:", e, flush=True)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("LINE bot 待ち受け開始 127.0.0.1:8080", flush=True)
    HTTPServer(("127.0.0.1", 8080), Handler).serve_forever()

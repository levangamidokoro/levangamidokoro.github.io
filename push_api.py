"""
見どころなう Webプッシュ送信（GitHub版）
Cloudflareの受付窓口（MIDOKORO_API）に「全員へ送って」と頼む。
本人確認は、GitHub Actions が発行するOIDCトークンで行う（合言葉や鍵をGitHubに置かない）。
"""

import base64
import json
import os
import time

import requests

API = os.environ.get("MIDOKORO_API", "").rstrip("/")
AUDIENCE = "midokoro-api"


def _github_token() -> str:
    url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    tok = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not tok:
        dev = os.environ.get("MIDOKORO_DEV_NOTIFY_TOKEN", "")   # ローカル試験用
        if dev:
            return dev
        raise RuntimeError("GitHub ActionsのOIDCトークンが使えません（workflowに id-token: write が必要）")
    r = requests.get(url, params={"audience": AUDIENCE}, headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    r.raise_for_status()
    return r.json()["value"]


_tok = {"value": "", "exp": 0.0}


def _cached_token() -> str:
    """OIDCトークンを、期限の1分前まで使い回す（20秒ごとに取り直さない）"""
    if _tok["value"] and _tok["exp"] - time.time() > 60:
        return _tok["value"]
    value = _github_token()
    try:
        part = value.split(".")[1]
        exp = float(json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))["exp"])
    except Exception:
        exp = time.time() + 240                       # 開発用の合言葉など、期限が読めないとき
    _tok.update(value=value, exp=exp)
    return value


def post_live(state: dict) -> None:
    """試合中の「いまの熱さ」を受付窓口に置く。ページは20秒ごとにこれを読む"""
    r = requests.post(f"{API}/api/live", headers={"Authorization": f"Bearer {_cached_token()}"}, json=state, timeout=10)
    r.raise_for_status()


def send_all(title: str, body: str, url: str, image: str | None = None, game: dict | None = None) -> int:
    """登録者全員に送る（窓口が40件ずつ送り、続きの位置を返す）。送れた件数を返す"""
    hdr = {"Authorization": f"Bearer {_github_token()}"}
    cursor, total = 0, 0
    for _ in range(2000):
        r = requests.post(f"{API}/api/notify", params={"cursor": cursor}, headers=hdr,
                          json={"title": title, "body": body, "url": url, "image": image or "", "game": game}, timeout=60)
        r.raise_for_status()
        d = r.json()
        total += d.get("sent", 0)
        if not d.get("cursor"):
            break
        cursor = d["cursor"]
    return total

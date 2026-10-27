"""
見どころなう Webプッシュ通知（無料・送信数の上限なし）

- 初回に通知用の鍵（VAPID鍵）を data/ に作る
- 登録情報は data/subscriptions.json に保存（ブラウザごとに1件）
- send_all() を収集プログラムが呼ぶ。期限切れの登録は自動で消す
"""

import base64
import json
import os
import threading
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01
from pywebpush import WebPushException, webpush

DATA = Path("data")
KEY_FILE = DATA / "vapid_private.pem"
SUBS_FILE = DATA / "subscriptions.json"
CONTACT = os.environ.get("VAPID_CONTACT", "").strip()
if CONTACT in ("", "mailto:"):
    CONTACT = "mailto:midokoro-now@example.com"   # 連絡先メールを設定すると、通知サービス側の問い合わせ先になる
_lock = threading.Lock()


def _vapid() -> Vapid01:
    DATA.mkdir(exist_ok=True)
    if not KEY_FILE.exists():
        v = Vapid01()
        v.generate_keys()
        v.save_key(str(KEY_FILE))
        os.chmod(KEY_FILE, 0o600)
    return Vapid01.from_file(str(KEY_FILE))


def public_key() -> str:
    """ブラウザに渡す公開鍵（base64url）"""
    raw = _vapid().public_key.public_bytes(serialization.Encoding.X962,
                                           serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _load() -> list[dict]:
    if not SUBS_FILE.exists():
        return []
    return json.loads(SUBS_FILE.read_text(encoding="utf-8"))


def _save(subs: list[dict]) -> None:
    DATA.mkdir(exist_ok=True)
    tmp = SUBS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(subs, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SUBS_FILE)


def _valid(sub: dict) -> bool:
    return (isinstance(sub, dict) and str(sub.get("endpoint", "")).startswith("https://")
            and isinstance(sub.get("keys"), dict)
            and {"p256dh", "auth"} <= set(sub["keys"]))


def add(sub: dict) -> bool:
    if not _valid(sub):
        return False
    with _lock:
        subs = [s for s in _load() if s["endpoint"] != sub["endpoint"]]
        subs.append({"endpoint": sub["endpoint"], "keys": sub["keys"]})
        _save(subs)
    return True


def remove(endpoint: str) -> None:
    with _lock:
        _save([s for s in _load() if s["endpoint"] != endpoint])


def send_all(title: str, body: str, url: str, image: str | None = None, game: dict | None = None) -> int:
    """全員に送る。送れた件数を返す"""
    payload = json.dumps({"title": title, "body": body, "url": url, "image": image or ""}, ensure_ascii=False)
    key = str(KEY_FILE) if KEY_FILE.exists() else (_vapid() and str(KEY_FILE))
    ok, dead = 0, []
    for s in _load():
        try:
            webpush(subscription_info=s, data=payload, vapid_private_key=key,
                    vapid_claims={"sub": CONTACT}, ttl=600)
            ok += 1
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):
                dead.append(s["endpoint"])   # 解除済み・期限切れ
    for ep in dead:
        remove(ep)
    return ok

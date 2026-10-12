-- 見どころなう 受付窓口のデータベース（Cloudflare D1）
-- 個人を特定する情報は保存しない：IPアドレスそのものは残さず、日ごとの合言葉で混ぜたハッシュだけを40日間持つ
CREATE TABLE IF NOT EXISTS subs (
  endpoint TEXT PRIMARY KEY,        -- 通知の宛先（ブラウザが発行するURL）
  p256dh   TEXT NOT NULL,
  auth     TEXT NOT NULL,
  device   TEXT NOT NULL DEFAULT '', -- iPhone / Android / PC（集計用の大まかな区分）
  created  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (  -- 日ごとの回数（view, sub, unsub, gone, push_sent, push_fail）
  day  TEXT NOT NULL,
  kind TEXT NOT NULL,
  n    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, kind)
);
CREATE TABLE IF NOT EXISTS visitors ( -- 日ごとのおおよその訪問者数を数えるためのハッシュ
  day TEXT NOT NULL,
  h   TEXT NOT NULL,
  PRIMARY KEY (day, h)
);
CREATE TABLE IF NOT EXISTS live (    -- 試合中の「いまの熱さ」（1行だけ。収集プログラムが20秒ごとに上書きする）
  id   INTEGER PRIMARY KEY,
  body TEXT NOT NULL,
  at   INTEGER NOT NULL
);

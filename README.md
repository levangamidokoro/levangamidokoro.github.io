# 見どころなう レバンガ北海道版（非公式）

レバンガ北海道の試合で盛り上がった瞬間を判定して、「いま見て！」と知らせる個人の非公式サービスです。
B.LEAGUE・レバンガ北海道とは関係ありません。スコアそのものは表示・配信せず、B.LEAGUE公式の試合ページへのリンクだけを出します。

## 仕組み（GitHub版）

- GitHub Actions が10分おきに起動し、試合の前後だけ20秒ごとに公式の試合データを見て判定します（`midokoro_daemon.py`、判定ルールは `midokoro_score.py`）。
- ページは `gh-pages` ブランチに置き、GitHub Pages で公開します（試合中は数分おきに更新）。
- 盛り上がったら LINE 公式アカウントから一斉通知します（1試合1回）。

## 設定

- Settings → Pages：Source を「Deploy from a branch」、ブランチを `gh-pages` / `(root)` にする
- Settings → Secrets and variables → Actions
  - Secrets：`LINE_CHANNEL_ACCESS_TOKEN`
  - Variables：`LINE_ADD_URL`（友だち追加リンク）、`SITE_URL`（このページのURL）

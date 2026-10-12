# 見どころなう レバンガ北海道版（非公式）

**公開ページ：https://levangamidokoro.github.io/**

レバンガ北海道の試合の熱さをゲージで表示し、ゲージが満タンになったら「いま見て！」と通知します。

レバンガ北海道の試合で盛り上がった瞬間を判定して、「いま見て！」と知らせる個人の非公式サービスです。
B.LEAGUE・レバンガ北海道とは関係ありません。スコアそのものは表示・配信せず、B.LEAGUE公式の試合ページへのリンクだけを出します。

## 仕組み（GitHub版）

- GitHub Actions が10分おきに起動し、試合の前後だけ20秒ごとに公式の試合データを見て判定します（`midokoro_daemon.py`、判定ルールは `midokoro_score.py`）。
- ページは `gh-pages` ブランチに置き、GitHub Pages で公開します（試合中は数分おきに更新）。
- 盛り上がったら LINE 公式アカウントから一斉通知します（1試合1回）。
- Webプッシュは Cloudflare Workers の受付窓口（`worker/`）が登録を受け付けて送ります。GitHub Actions からの依頼は、GitHubのOIDCトークンで本人確認します。
- 利用状況（アクセス数・通知登録数）は `stats.html` で見られます（合言葉が必要）。Cookieは使わず、IPアドレスそのものは保存しません。

## 設定

- Settings → Pages：Source を「Deploy from a branch」、ブランチを `gh-pages` / `(root)` にする
- Settings → Secrets and variables → Actions
  - Secrets：`LINE_CHANNEL_ACCESS_TOKEN`
  - Secrets：`CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`、`STATS_TOKEN`（利用状況ページの合言葉）
  - Variables：`LINE_ADD_URL`（友だち追加リンク）、`SITE_URL`（このページのURL）、`MIDOKORO_API`（受付窓口のURL。deploy-api の実行結果に表示される）
  - Variables（任意）：`GOOGLE_SITE_VERIFICATION`（Google Search Console の「HTMLタグ」で表示される content の値）、`BING_SITE_VERIFICATION`

## 熱さゲージ

- 熱さ（%）＝ 見どころ度 ÷ 通知ライン（`midokoro_score.HIGH`＝70）。100%（満タン）が「いま見て！」の通知。
- 熱さの推移は `midokoro_score.heat_curve()` で、試合時間30秒ごとに、その時点までのプレーだけで判定し直して作る。
- 終わった試合（見どころなうが動いていなかった試合も）は、試合データから一度だけ計算して `data/alerts.json` に残す。

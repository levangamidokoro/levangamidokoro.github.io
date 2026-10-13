# 実行の依頼

`request.json` の `id` を新しい値に変えて main に push すると、受付窓口（Cloudflare Worker）が10分以内に、
`run` に書いたワークフローを GitHub App（midokoro-starter）の名前で起動します。
Actions の実行者に個人のアカウント名を出さないための仕組みです。起動できるのは決まったワークフローだけです。

例：ページを公開し直す、受付窓口を更新する

```json
{"id": "2026-10-13-1", "run": [{"workflow": "deploy-api.yml"}, {"workflow": "midokoro.yml", "inputs": {"force_publish": "true"}}]}
```

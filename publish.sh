#!/usr/bin/env bash
# 作り直したページ（site/）を gh-pages ブランチに公開する。変化がなければ何もしない
set -e
cd site
git add -A
git diff --cached --quiet && exit 0
git commit -q -m "ページ更新 $(TZ=Asia/Tokyo date '+%m/%d %H:%M')"
git push -q origin HEAD:gh-pages

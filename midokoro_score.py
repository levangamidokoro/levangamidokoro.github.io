"""
見どころなう 見どころ判定（暫定ルール v1.2）

v1.2の変更（公式YouTubeハイライト20試合・1,821得点プレーの照合から）
  - フリースローによる逆転・同点・勝ち越しは加点しない（最後の1分は例外）。FTはハイライト率0.2倍
  - 相手の3P・ダンクは+5（レバンガは+10のまま）
  - レバンガの8点以上の連続得点（直近1分以内に続いている）で+5
  - 好プレー（レバンガの3P・ダンク・逆転、4Q以降の同点・勝ち越し）を good_plays() で一覧にする。通知ではなく記録用

根拠：レバンガ北海道 2025-26 の7試合・ハイライト101場面の分析
  ハイライトに選ばれやすい：4Q残り3分以内（約3.3倍）、逆転・先制（約1.9倍）、ダンク（約5.6倍）、3P（約1.5倍）
  ほぼ選ばれない：フリースロー
過去60試合の再生テスト（v1.2、2026-10-11）：通知は1試合平均1.23回、最終5点差以内の23試合すべてで通知、20点差以上の13試合は0件
激アツの通知を加えた再生テスト（2026-10-12、同じ60試合）：1試合平均1.38回、激アツの通知は18試合で19回（うち7回は満タンなどの通知と同時なので1回にまとめる）

入力：公式サイトが使うプレー記録（PlayByPlays）と、レバンガがホームかどうか
出力：見どころ度（0〜。70以上で満タン＝「いま見て！」の通知、100以上で激アツ＝「激アツ！」の通知）、レベル（高・中・低）、試合時間、説明文
※ 説明文に得点そのものは入れない（スコアは表示しない方針）
通知するかどうかは notify_reasons() で決める（収集プログラムと再生テストで同じものを使う）
"""

SKIP = {84, 85, 86, 87}          # タイマー・選手交代
HIGH, MID = 70, 45
BREAK = 100                      # 激アツ：見どころ度がここまで上がると、熱さが100%を超えてゲージを突き破る（約143%）
RECENT = 60                      # 直近とみなす試合時間（秒）
TEAM_LABEL = "レバンガ"


def _sec(t) -> float:
    m, s = str(t).split(":")
    return int(m) * 60 + float(s)


def _elapsed(p) -> float:
    q = p["Period"]
    if q <= 4:
        return (q - 1) * 600 + 600 - _sec(p["RestTime"])
    return 2400 + (q - 5) * 300 + 300 - _sec(p["RestTime"])


def _clock(q: int, rest: float) -> str:
    label = f"{q}Q" if q <= 4 else ("OT" if q == 5 else f"OT{q - 4}")
    return f"{label} {int(rest // 60)}:{int(rest % 60):02d}"


def _time_phrase(q: int, rest: float, late: bool, ot: bool) -> str:
    if ot:
        return "延長戦"
    m, s = int(rest // 60), int(rest % 60)
    if late:
        return f"第4Q残り{m}分{s:02d}秒" if m else f"第4Q残り{s}秒"
    return f"第{q}Q"


def _event_phrase(kind: str, ours: bool) -> str:
    return {
        ("逆転", True): f"{TEAM_LABEL}が逆転！",
        ("逆転", False): "逆転された…",
        ("同点", True): f"{TEAM_LABEL}が同点に追いついた！",
        ("同点", False): "同点に追いつかれた",
        ("勝ち越し", True): f"{TEAM_LABEL}が勝ち越し！",
        ("勝ち越し", False): "勝ち越された",
        ("ダンク", True): f"{TEAM_LABEL}のダンク！",
        ("ダンク", False): "相手のダンク",
        ("3P", True): f"{TEAM_LABEL}の3P！",
        ("3P", False): "相手の3P",
    }[(kind, ours)]


def evaluate(pbp: list[dict], team_is_home: bool = True) -> dict | None:
    """試合中のプレー記録から現在の見どころ度を出す。試合前・データなしは None"""
    plays = [p for p in pbp if p.get("ActionCD1") not in SKIP and p.get("RestTime")]
    plays.sort(key=lambda p: (_elapsed(p), p.get("No") or 0))   # 記録順の入れ替わりに備えて試合時間順に
    if not plays:
        return None
    if any(p.get("GameEndRowFlg") for p in plays) or any("試合終了" in (p.get("PlayText") or "") for p in plays):
        return {"score": 0, "level": "終了", "text": "試合終了", "clock": "", "headline": "試合終了"}

    # 得点の推移
    scoring, last = [], (0, 0)
    for p in plays:
        if p.get("Score"):
            h, a = map(int, p["Score"].split("-"))
            if (h, a) != last:
                scoring.append((p, last, (h, a)))
                last = (h, a)
    now = plays[-1]
    q, rest = now["Period"], _sec(now["RestTime"])
    margin = abs(last[0] - last[1])
    t_now = _elapsed(now)

    score = 0
    ot = q >= 5
    late = ot or (q == 4 and rest <= 180)
    if ot:
        score += 50
    elif late:
        score += 40
    elif q == 4 and margin <= 8:
        score += 15

    situation = None
    w = 1.0 if q >= 4 else 0.5 if q == 3 else 0.25   # 序盤の接戦は重みを下げる
    if margin <= 3:
        score += 40 * w; situation = "1ポゼッション差"
    elif margin <= 5:
        score += 30 * w; situation = "接戦"
    elif margin <= 8 and q >= 3:
        score += 10 * w

    # 直近のプレー
    event = None
    for p, (ph, pa), (h, a) in reversed(scoring):
        if t_now - _elapsed(p) > RECENT:
            break
        text = p.get("PlayText") or ""
        before, after = ph - pa, h - a
        ours = (h > ph) == team_is_home          # 得点したのがレバンガか
        ft_only = "フリースロー" in text and not (q >= 4 and rest <= 60)
        if ft_only and (before * after < 0 or (before != 0 and after == 0) or (before == 0 and after != 0)):
            continue                              # FTでの逆転・同点・勝ち越しは数えない（最後の1分は除く）
        if before * after < 0:
            score += 20 * max(w, 0.5); event = event if event and event[0] in ("逆転", "同点") else ("逆転", ours); break
        if before != 0 and after == 0:
            score += 15 * max(w, 0.5); event = event if event and event[0] in ("逆転", "同点") else ("同点", ours); break
        if before == 0 and after != 0 and q >= 4:      # 同点からの勝ち越し（4Q以降）
            score += 15; event = event if event and event[0] in ("逆転", "同点") else ("勝ち越し", ours); break
        if "ダンク" in text:
            score += 10 if ours else 5; event = event or ("ダンク", ours)
        elif "3Pシュート○" in text:
            score += 10 if ours else 5; event = event or ("3P", ours)
    # レバンガの連続得点（相手が止められていない8点以上）
    run = 0
    for p, (ph, pa), (h, a) in reversed(scoring):
        if ((h > ph) == team_is_home):
            run += (h - ph) + (a - pa)
        else:
            break
    if run >= 8 and scoring and t_now - _elapsed(scoring[-1][0]) <= RECENT:
        score += 5
    score = int(score)                     # 上限なし。HIGH（70）で満タン、BREAK（100）で激アツ
    level = "高" if score >= HIGH else "中" if score >= MID else "低"

    time_phrase = _time_phrase(q, rest, late, ot)
    first = time_phrase + ("、" + situation if situation else "")
    event_text = _event_phrase(*event) if event else ""
    text = first + "。" + event_text if event_text else first + "。"
    headline = event_text or situation or time_phrase
    return {"score": score, "level": level, "text": text, "headline": headline,
            "clock": _clock(q, rest), "period": q, "rest": rest,
            "event": event[0] if event else None, "phase": phase(q, rest)}


def good_plays(pbp: list[dict], team_is_home: bool = True) -> list[dict]:
    """レバンガの好プレー（3P・ダンク・逆転、4Q以降の同点・勝ち越し）。試合時間の順。得点そのものは含めない
       フリースローによる逆転・同点・勝ち越しは、最後の1分だけ入れる"""
    plays = [p for p in pbp if p.get("ActionCD1") not in SKIP and p.get("RestTime")]
    plays.sort(key=lambda p: (_elapsed(p), p.get("No") or 0))
    out, last = [], (0, 0)
    for p in plays:
        if not p.get("Score"):
            continue
        h, a = map(int, p["Score"].split("-"))
        if (h, a) == last:
            continue
        ph, pa = last
        last = (h, a)
        if (h > ph) != team_is_home:
            continue
        text = p.get("PlayText") or ""
        name = (p.get("PlayerNameJ1") or "").strip()
        q, rest = p["Period"], _sec(p["RestTime"])
        ft_ok = "フリースロー" not in text or (q >= 4 and rest <= 60)
        kinds = []
        if ft_ok and (ph - pa) * (h - a) < 0:
            kinds.append("逆転")
        elif ft_ok and q >= 4 and ph != pa and h == a:
            kinds.append("同点")
        elif ft_ok and q >= 4 and ph == pa and h != a:
            kinds.append("勝ち越し")
        if "ダンク" in text:
            kinds.append("ダンク")
        elif "3Pシュート○" in text:
            kinds.append("3P")
        if kinds:
            out.append({"clock": _clock(q, rest), "text": "・".join(kinds) + (f"　{name}" if name else "")})
    return out


def heat_curve(pbp: list[dict], team_is_home: bool = True, step: int = 30) -> list[list[int]]:
    """熱さの推移：試合時間 step 秒ごとの見どころ度 [[経過秒, 見どころ度], ...]。
       その時点までのプレーだけで evaluate() し直すので、試合中のゲージの動きをそのまま再現する"""
    plays = [p for p in pbp if p.get("ActionCD1") not in SKIP and p.get("RestTime")]
    if not plays:
        return []
    plays.sort(key=lambda p: (_elapsed(p), p.get("No") or 0))
    times = [_elapsed(p) for p in plays]
    out, i, t = [], 0, step
    end = times[-1]
    while t < end + step:
        while i < len(plays) and times[i] <= t:
            i += 1
        ev = evaluate(plays[:i], team_is_home) if i else None
        if ev and ev["level"] != "終了":
            out.append([int(min(t, end)), int(ev["score"])])
        t += step
    return out


GEKI = "激アツ"


def notify_reasons(flags: set, ev: dict) -> list[str]:
    """この瞬間に通知するか。flags（その試合で通知済みの印）を更新し、理由の一覧を返す（空なら通知しない）
       ・満タン：その試合で最初に「高」になったとき（落ち着いて「低」に戻ったあとは、もう一度）
       ・満タン：残り3分（延長は各回）に入って「高」のとき
       ・最後の1分：満タンのまま逆転・同点・勝ち越し
       ・激アツ：見どころ度が BREAK に届き、熱さが100%を超えたとき。区切り（通常／残り3分／延長の各回）ごとに1回まで
       同じ瞬間に重なった理由は、まとめて1回の通知にする（送る側で、激アツがあれば激アツの文面にする）"""
    if ev["level"] == "低":
        flags.discard("通常")
    reasons = []
    if ev["level"] == "高":
        if ev["phase"] not in flags:
            reasons.append(ev["phase"])
        elif ev["period"] >= 4 and ev["rest"] <= 60 and ev["event"] in ("逆転", "同点", "勝ち越し") and "最後の1分" not in flags:
            reasons.append("最後の1分")
    if ev["score"] >= BREAK and f"{GEKI}:{ev['phase']}" not in flags:
        reasons.append(GEKI)
    for r in reasons:
        flags.add(f"{GEKI}:{ev['phase']}" if r == GEKI else r)
    return reasons


def phase(q: int, rest: float) -> str:
    """通知の区切り：通常／残り3分／延長（延長は回ごと）"""
    if q >= 5:
        return f"延長{q - 4}"
    if q == 4 and rest <= 180:
        return "残り3分"
    return "通常"

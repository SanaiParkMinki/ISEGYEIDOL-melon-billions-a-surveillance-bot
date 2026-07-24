#!/usr/bin/env python3
"""
이세계아이돌 멜론 누적 스트리밍 스냅샷 수집기.

하루 한 번 실행해서 data/history.json 에 { date, total_streams } 한 줄을 덧붙입니다.
같은 날짜가 이미 있으면 덮어씁니다(중복 실행 안전).

사용법
  python3 scripts/collect.py                    # 멜론에서 자동 수집
  python3 scripts/collect.py --value 856820708  # 눈으로 확인한 값 직접 입력
  python3 scripts/collect.py --dry-run          # 파일에 쓰지 않고 결과만 출력
"""

import argparse
import datetime
import json
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "history.json"
KST = datetime.timezone(datetime.timedelta(hours=9))

ARTIST_ID = "3059851"  # 멜론 이세계아이돌
ARTIST_URL = f"https://www.melon.com/artist/detail.htm?artistId={ARTIST_ID}"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# 누적 스트리밍 수치를 감싸는 마크업 후보들.
# 멜론이 페이지 구조를 바꾸면 여기만 고치면 됩니다.
PATTERNS = [
    r"누적\s*스트리밍[^0-9]{0,80}?([\d,]{7,})",
    r"data-total-stream[^0-9]*([\d,]{7,})",
    r'"totalStreamCnt"\s*:\s*"?([\d,]{7,})"?',
]


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.melon.com/"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def scrape_total() -> int:
    html = fetch_html(ARTIST_URL)
    for pat in PATTERNS:
        m = re.search(pat, html, re.S)
        if m:
            n = int(m.group(1).replace(",", ""))
            if n > 1_000_000:  # 말도 안 되게 작은 값은 오탐
                return n
    raise LookupError(
        "누적 스트리밍 값을 찾지 못했습니다.\n"
        f"  1) 브라우저로 {ARTIST_URL} 를 열어 실제 수치가 어느 태그에 있는지 확인하고\n"
        "  2) scripts/collect.py 의 PATTERNS 에 정규식을 추가하세요.\n"
        "  급하면 --value 로 직접 넣어도 됩니다."
    )


def clean_number(raw: str) -> int:
    """사람이 복사해 넣는 온갖 모양을 숫자로 바꿉니다.

    '856,820,708' / '856 820 708' / '856820708회' / '８５６' 전부 받습니다.
    """
    if raw is None:
        raise ValueError("값이 비어 있습니다.")
    s = raw.strip()
    s = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))  # 전각 숫자
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        raise ValueError(f"숫자를 못 찾았습니다: {raw!r}")
    n = int(digits)
    if n < 1_000_000:
        raise ValueError(
            f"{n:,} 은 너무 작습니다. 누적 스트리밍은 억 단위입니다. "
            "'1.2억' 같은 축약형 말고 전체 숫자를 넣어주세요."
        )
    return n


def load() -> dict:
    if not DATA.exists():
        return {
            "artist": {"name": "이세계아이돌", "melon_artist_id": ARTIST_ID, "debut": "2021-12-17"},
            "tiers": [
                {"name": "브론즈", "threshold": 1_000_000_000},
                {"name": "실버", "threshold": 2_000_000_000},
                {"name": "골드", "threshold": 5_000_000_000},
                {"name": "다이아", "threshold": 10_000_000_000},
            ],
            "history": [],
            "songs": [],
        }
    return json.loads(DATA.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--value", help="누적 스트리밍 수 (쉼표·공백·'회' 붙어 있어도 됩니다)")
    ap.add_argument("--date", help="스냅샷 날짜 (기본: 오늘, KST)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    day = args.date or datetime.datetime.now(KST).date().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        print(f"날짜 형식이 잘못됐습니다: {day!r} — 2026-07-24 처럼 넣어주세요.", file=sys.stderr)
        return 1

    if args.value is not None:
        try:
            total, source = clean_number(args.value), "manual"
        except ValueError as e:
            print(f"입력한 값을 못 읽었습니다: {e}", file=sys.stderr)
            return 1
    else:
        try:
            total, source = scrape_total(), "melon.com/artist/detail"
        except Exception as e:
            print(f"수집 실패: {e}", file=sys.stderr)
            return 1

    doc = load()
    hist = [h for h in doc["history"] if h["date"] != day]
    hist.append({"date": day, "total_streams": total})
    hist.sort(key=lambda h: h["date"])

    prev = hist[-2]["total_streams"] if len(hist) > 1 else None
    if prev is not None and total < prev:
        print(f"경고: 누적치가 줄었습니다 ({prev:,} → {total:,}). 파싱 오류일 가능성이 큽니다.", file=sys.stderr)
        return 1

    doc["history"] = hist
    doc["source"] = source
    doc["updated_at"] = datetime.datetime.now(KST).isoformat(timespec="seconds")
    doc.pop("sample", None)

    delta = f"+{total - prev:,}" if prev is not None else "첫 스냅샷"
    print(f"{day}  {total:,}회  ({delta})")

    if args.dry_run:
        print("(dry-run: 저장 안 함)")
        return 0

    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

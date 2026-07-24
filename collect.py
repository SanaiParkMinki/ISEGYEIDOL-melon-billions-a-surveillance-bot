name: 스냅샷 수집

on:
  # 손으로 숫자 넣기 — 이게 기본 방식입니다.
  workflow_dispatch:
    inputs:
      value:
        description: "멜론에서 본 누적 스트리밍 수 (쉼표 빼고 숫자만)"
        required: false
        type: string
      date:
        description: "날짜 (비워두면 오늘). 예: 2026-07-20"
        required: false
        type: string

  # 자동 수집은 되면 좋고 안 되면 마는 보너스입니다. 막혀도 빨간 X를 띄우지 않습니다.
  schedule:
    - cron: "0 19 * * *"   # 매일 04:00 KST

permissions:
  contents: write

concurrency:
  group: collect
  cancel-in-progress: false

jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: 파일 확인
        run: |
          missing=0
          for f in scripts/collect.py data/history.json; do
            if [ ! -f "$f" ]; then echo "::error::$f 가 저장소에 없습니다. 업로드가 빠졌는지 확인하세요."; missing=1; fi
          done
          [ "$missing" = "0" ]

      - name: 숫자 기록
        env:
          IN_VALUE: ${{ inputs.value }}
          IN_DATE: ${{ inputs.date }}
        run: |
          if [ -n "$IN_VALUE" ]; then
            # 손으로 넣은 값. 쉼표나 '회'가 붙어 있어도 스크립트가 알아서 걸러냅니다.
            if [ -n "$IN_DATE" ]; then
              python3 scripts/collect.py --value "$IN_VALUE" --date "$IN_DATE"
            else
              python3 scripts/collect.py --value "$IN_VALUE"
            fi
          else
            # 자동 시도. 멜론에 막히면 조용히 넘어갑니다.
            python3 scripts/collect.py || echo "::notice::자동 수집 실패(멜론 차단으로 보임). Run workflow 로 숫자를 직접 넣으세요."
          fi

      - name: 변경분 커밋
        run: |
          if git diff --quiet -- data/history.json; then
            echo "새로 적을 게 없어 건너뜁니다."
            exit 0
          fi
          git config user.name  "billions-bot"
          git config user.email "billions-bot@users.noreply.github.com"
          git add data/history.json
          git commit -m "스냅샷 $(TZ=Asia/Seoul date +%Y-%m-%d)"
          git push

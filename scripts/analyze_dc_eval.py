"""어린이집 평가결과서(개편 후, src/data/dc_eval.json) → Claude Haiku로 4칸 정리 → src/data/dc_eval_ai.json

학부모 질문 4개에 대해, 원문에 적힌 사실만 정해진 값으로 고르게 한다(칸·값이 늘어나지 않게).
  ① 바깥에 자주 나가나요?    freq(매주/매월/정기적/있음/없음) + kinds(숲·산책·텃밭·공원·하천·생태·현장체험)
  ② 밥은 잘 나오나요?        meal(저염 인증·우수급식소·전담 영양사·부모 급식 모니터링·이유식 직접 조리)
  ③ 부모가 들여다볼 수 있나요? parent(참여수업·아빠 참여·급식 모니터링·쿠킹클래스·가족 프로그램·부모교육·현장학습 도우미)
  ④ 발달 지원이 있나요?      dev(발달 검사·전문기관 연계)
각 칸에 근거 문장(ev)을 같이 저장해 검증할 수 있게 한다. 정해진 값 밖의 답은 버린다.
- 결과: {stcode: {"ym": 평가연월, "o": {"freq", "kinds", "meal", "parent", "dev", "ev": {칸: 근거}}, "m": 모델, "t": 날}}
- 이미 같은 평가연월로 정리한 곳은 건너뜀. 4곳 동시. --limit N, --minutes N, --ids a,b(시험용). env ANTHROPIC_API_KEY(없으면 아무것도 안 하고 끝).
- 비용(2026-11): Haiku 5.5 입력 100만 토큰당 0.10달러·출력 0.50달러 → 전체 2,157곳 약 1달러, 이후 매달 새로 평가받은 곳만.
"""
import datetime, json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SRC = os.path.join(ROOT, 'src', 'data', 'dc_eval.json')
OUT = os.path.join(ROOT, 'src', 'data', 'dc_eval_ai.json')
MODEL = 'claude-haiku-5-5'
FREQ = ['매주', '매월', '정기적', '있음', '없음']
KINDS = ['숲', '산책', '텃밭', '공원', '하천·생태', '현장체험']
MEAL = ['저염 인증', '우수급식소', '전담 영양사', '부모 급식 모니터링', '이유식 직접 조리']
PARENT = ['참여수업', '아빠 참여', '급식 모니터링', '쿠킹클래스', '가족 프로그램', '부모교육', '현장학습 도우미']
DEV = ['발달 검사', '전문기관 연계']

PROMPT = f"""다음은 한 어린이집의 정부 평가결과서(6개 영역 종합의견)입니다. 학부모를 위해 아래 4가지를 원문에 '명시된 사실'로만 정리하세요.
추측·일반론 금지. 모든 어린이집에 나오는 형식적 문장(예: "가정과 원활히 소통합니다", "부모 면담에 활용합니다", "바깥놀이 시간을 조정")은 근거가 아닙니다.

1. freq — 바깥·자연 활동(숲·산책·텃밭·공원·하천 생태·현장체험)을 얼마나 자주 하는지. 다음 중 하나:
   "매주"(매주·주 1회 이상이 명시), "매월"(매월·월 1~3회가 명시), "정기적"(주기적·정기적·분기별 등 횟수 불명확), "있음"(활동은 구체적으로 나오나 빈도 언급 없음), "없음"
   kinds — 해당 활동 종류, 다음에서만 고름: {KINDS}
2. meal — 급식 관련, 다음에서만 고름: {MEAL}
   "저염 인증"은 저염급식소·저염 실천 급식소 등 외부 인증/선정이 명시된 경우만(단순 "저염식 제공"은 제외). "우수급식소"는 우수(어린이)급식소·빛나는 급식소 등 선정·수상이 명시된 경우만("서울 든든급식"은 식자재 공급 사업이라 제외).
3. parent — 부모가 실제로 어린이집에 와서 참여하는 프로그램, 다음에서만 고름: {PARENT}
   "부모 의견을 반영해 ○○ 운영"처럼 부모가 직접 참여하지 않는 것은 제외.
4. dev — 아이 발달 지원, 다음에서만 고름: {DEV} ("발달 검사"는 발달 진단·검사 도구로 평가한 경우, "전문기관 연계"는 필요시 전문기관에 연결하는 경우)

각 항목의 근거가 된 원문 구절을 ev에 30자 이내로 그대로 옮기세요(없으면 빈 문자열).
반드시 아래 JSON 한 개만 출력하세요(설명 금지):
{{"freq":"...","kinds":[],"meal":[],"parent":[],"dev":[],"ev":{{"outdoor":"","meal":"","parent":"","dev":""}}}}

평가결과서:
"""


def call(text, key):
    body = json.dumps({'model': MODEL, 'max_tokens': 500, 'temperature': 0,
                       'messages': [{'role': 'user', 'content': PROMPT + text}]}).encode()
    for i in range(4):
        try:
            req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=body, headers={
                'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.load(r)
            return ''.join(c.get('text', '') for c in d.get('content', [])), d.get('usage', {})
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529) and i < 3:
                time.sleep(5 * (i + 1))
                continue
            raise RuntimeError(f'HTTP {e.code}: {e.read()[:300]!r}')
        except Exception:
            if i == 3:
                raise
            time.sleep(5 * (i + 1))


def clean(raw):
    m = re.search(r'\{.*\}', raw, re.S)
    j = json.loads(m.group(0))
    pick = lambda xs, allow: [x for x in dict.fromkeys(xs or []) if x in allow]
    o = {'freq': j.get('freq') if j.get('freq') in FREQ else '없음',
         'kinds': pick(j.get('kinds'), KINDS), 'meal': pick(j.get('meal'), MEAL),
         'parent': pick(j.get('parent'), PARENT), 'dev': pick(j.get('dev'), DEV),
         'ev': {k: str(v)[:60] for k, v in (j.get('ev') or {}).items() if k in ('outdoor', 'meal', 'parent', 'dev') and v}}
    if o['freq'] == '없음':
        o['kinds'] = []
    return o


def main():
    args = sys.argv[1:]
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        print('평가 AI 정리: ANTHROPIC_API_KEY가 없어 건너뜀')
        return
    limit = int(args[args.index('--limit') + 1]) if '--limit' in args else 0
    minutes = float(args[args.index('--minutes') + 1]) if '--minutes' in args else 0
    deadline = time.time() + minutes * 60 if minutes else None
    src = {k: v for k, v in json.load(open(SRC, encoding='utf-8')).items() if v.get('a')}
    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    data = {k: v for k, v in old.items() if k in src}
    todo = [k for k in sorted(src) if data.get(k, {}).get('ym') != src[k]['ym']]
    if '--ids' in args:  # 시험용: 특정 곳만
        want = args[args.index('--ids') + 1].split(',')
        todo = [k for k in want if k in src]
    if limit:
        todo = todo[:limit]
    print(f'평가 AI 정리: 대상 {len(src)}곳, 할 곳 {len(todo)}곳(이미 {len(data)}곳)')
    today = datetime.date.today().isoformat()
    ok = fail = 0
    tok_in = tok_out = 0

    def one(k):
        text = '\n'.join(f'[{a}] {t}' for a, t in src[k]['a'])
        raw, use = call(text, key)
        return clean(raw), use

    def save():
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(dict(sorted(data.items())), f, ensure_ascii=False, separators=(',', ':'))

    left = 0
    with ThreadPoolExecutor(4) as ex:
        it, futs = iter(todo), {}

        def submit():
            nonlocal left
            for k in it:
                if deadline and time.time() > deadline:
                    left += 1
                    continue
                futs[ex.submit(one, k)] = k
                return
        for _ in range(4):
            submit()
        while futs:
            f = next(as_completed(futs))
            k = futs.pop(f)
            try:
                o, use = f.result()
                data[k] = {'ym': src[k]['ym'], 'o': o, 'm': MODEL, 't': today}
                tok_in += use.get('input_tokens', 0); tok_out += use.get('output_tokens', 0)
                ok += 1
            except Exception as e:
                fail += 1
                if fail <= 5:
                    print(f'  실패 {k}: {e}', file=sys.stderr)
                if fail >= 10 and ok == 0:
                    save()
                    sys.exit('평가 AI 정리: 처음부터 계속 실패(키·크레딧 확인)')
            if (ok + fail) % 100 == 0:
                print(f'  {ok + fail}/{len(todo)}')
                save()
            submit()
    save()
    cost = tok_in / 1e6 * 0.10 + tok_out / 1e6 * 0.50
    print(f'평가 AI 정리: 성공 {ok}, 실패 {fail}, 시간 넘어 다음으로 {left} · 토큰 입력 {tok_in:,} 출력 {tok_out:,} (약 ${cost:.3f})')
    if fail > max(5, (ok + fail) * 0.1):
        sys.exit(f'평가 AI 정리: 실패 {fail}곳')


if __name__ == '__main__':
    main()

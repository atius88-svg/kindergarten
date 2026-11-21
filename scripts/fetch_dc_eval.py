"""어린이집정보공개포털 평가결과서(2024-07 개편 후 평가) → src/data/dc_eval.json  (python3 scripts/fetch_dc_eval.py)

개편된 평가제는 A~D 등급 없이 6개 영역별 '종합의견'(서술)만 나온다. 그 글을 받아 상세 화면에 보여 준다.
  평가 화면  /info_html5/pnis/search/preview/AppraisaAuthenticationGradeSlPu.jsp?flag=PI&STCODE_POP={stcode}
             → goTotalComment(v, s, c, e): v = 결과서 id, e = '01'이면 개편 후(2주기) 평가
  결과서     /info_html5/cera/search/totalGradeCommentEvl2nd.jsp?flag=commnetGrade&childHouseId={v}&evlIdxTy=01
             → <tr id="evlResult_N"><th>영역</th><td>종합의견</td></tr> × 6  (evlIdxTy가 없으면 빈 표)
- 대상: dc_portal.json에서 평가완료이고 총평 등급이 없으며 평가연월 2024-07 이후인 곳. 이미 같은 평가연월로 받은 곳은 건너뜀.
- 결과: {stcode: {"ym": "2025-11", "a": [[영역, 종합의견], …] 또는 null(결과서 없음), "t": 받은 날}}
- 보완 권고: 종합의견 안의 '다만, …' 문장(scripts/build.py가 개수를 dc.json에 넣음).
- 4곳 동시, 100곳마다 저장, --minutes N(넘으면 저장하고 멈춤, 다음 실행이 이어 받음), --limit N, --parse 결과서.html
키 불필요, GitHub(해외)에서 접속됨.
"""
import datetime, html, json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PORTAL = os.path.join(ROOT, 'src', 'data', 'dc_portal.json')
OUT = os.path.join(ROOT, 'src', 'data', 'dc_eval.json')
HOST = 'https://info.childcare.go.kr'
PRE = HOST + '/info_html5/pnis/search/preview/'


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (kindergarten-map-updater)'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def text(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()


def parse_doc(page):
    rows = re.findall(r'<tr id="evlResult_\d+">\s*<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>', page, re.S)
    out = []
    for a, t in rows:
        a = re.sub(r'^\d+\.\s*', '', text(a))
        out.append([a, text(t)])
    return out


def one(stcode):
    p = get(PRE + f'AppraisaAuthenticationGradeSlPu.jsp?flag=PI&STCODE_POP={stcode}')
    m = re.search(r"goTotalComment\('([^']*)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'\)", p)
    if not m or m.group(4) != '01':
        return None  # 개편 후 결과서가 없음
    a = parse_doc(get(f'{HOST}/info_html5/cera/search/totalGradeCommentEvl2nd.jsp?flag=commnetGrade&childHouseId={m.group(1)}&evlIdxTy=01'))
    time.sleep(0.3)
    return a or None


def main():
    args = sys.argv[1:]
    if args[:1] == ['--parse']:
        print(json.dumps(parse_doc(open(args[1], encoding='utf-8').read()), ensure_ascii=False, indent=1))
        return
    minutes = float(args[args.index('--minutes') + 1]) if '--minutes' in args else 0
    limit = int(args[args.index('--limit') + 1]) if '--limit' in args else 0
    deadline = time.time() + minutes * 60 if minutes else None
    portal = json.load(open(PORTAL, encoding='utf-8'))
    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    want = {k: v['평가연월'] for k, v in portal.items()
            if v.get('평가완료') and not v.get('평가') and (v.get('평가연월') or '') >= '2024-07'}
    data = {k: v for k, v in old.items() if k in want}  # 개편 전 평가로 바뀌거나 사라진 곳은 지움
    todo = sorted((k for k, ym in want.items() if data.get(k, {}).get('ym') != ym), key=lambda k: (k in data, k))
    if limit:
        todo = todo[:limit]
    print(f'평가결과서: 대상 {len(want)}곳, 받을 곳 {len(todo)}곳(이미 받음 {len(data)})')
    today = datetime.date.today().isoformat()
    ok = fail = none = 0

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
                a = f.result()
                data[k] = {'ym': want[k], 'a': a, 't': today}  # 결과서가 없어도 기록(a=None) → 같은 평가연월이면 다시 안 받음
                if a:
                    ok += 1
                else:
                    none += 1
            except Exception as e:
                fail += 1
                if fail <= 10:
                    print(f'  실패 {k}: {e}', file=sys.stderr)
            if (ok + none + fail) % 100 == 0:
                print(f'  {ok + none + fail}/{len(todo)}')
                save()
            submit()
    save()
    print(f'평가결과서: 받음 {ok}, 결과서 없음 {none}, 실패 {fail}, 시간 넘어 다음으로 {left} → 저장 {len(data)}곳')
    if fail > max(5, (ok + none + fail) * 0.1):
        sys.exit(f'평가결과서: 실패 {fail}곳')


if __name__ == '__main__':
    main()

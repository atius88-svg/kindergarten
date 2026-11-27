"""유치원알리미 유치원별 요약·안전 화면 → src/data/kg_detail.json (주소·전화·홈페이지·통학차량 대수·CCTV 수).

SEO 기관별 페이지(scripts/build_pages.py)에 쓰는 값. OPEN API에는 대수·설치수가 없어서
유치원알리미 상세 화면 두 탭을 유치원마다 받는다. 로그인·인증키 불필요.
- 요약 탭 POST /kinderMt/kinderSummary.do  ittId=유치원코드 → 지도 스크립트 변수(전화·주소·홈페이지)
- 안전 탭 POST /kinderMt/kinderSafetyManagement.do → 표 '통학차량 현황', 'CCTV 설치 현황'의 마지막 행
유치원코드는 src/data/kg_ids.json(유치원코드 → id).

사용법 (저장소 루트에서):
    python3 scripts/fetch_detail.py                       # 받은 지 25일 넘은 곳(또는 없는 곳)만
    python3 scripts/fetch_detail.py --days 0 --minutes 40 # 전부 다시, 40분 넘으면 저장 후 멈춤(다음 실행이 이어 받음)
    python3 scripts/fetch_detail.py --limit 20            # 20곳만(시험)
    python3 scripts/fetch_detail.py --parse 요약.html 안전.html   # 파서 시험

결과: {id: {"addr": "성북구 …", "tel": "02-…", "web": "http…"|null, "bus": 운행 차량 수(0=미운영), "cctv": 총 설치수, "t": 받은 날}}
- 3곳씩 동시에 받고 100곳마다 저장한다. 오래된 곳부터 받는다. 실패한 곳은 예전 값을 그대로 둔다.
- GitHub(해외)에서 한 곳(요청 2번)에 몇 초씩 걸려 711곳 전체는 30분을 넘는다(2026-11-21 시험) → --minutes로 나눠 받음.
"""
import json, os, re, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_cost import Tables, active_ids  # caption별 표 파서·운영 중 목록 재사용

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
OUT = os.path.join(ROOT, 'src', 'data', 'kg_detail.json')
IDS = os.path.join(ROOT, 'src', 'data', 'kg_ids.json')
BASE = 'https://e-childschoolinfo.moe.go.kr/kinderMt/'


def num(s):
    m = re.search(r'\d+', s or '')
    return int(m.group()) if m else None


def parse_summary(text):
    g = lambda pat: (re.search(pat, text) or [None, None])[1]
    tel = g(r"kinderTel\s*=\s*'전화번호 : '\s*\+\s*'([^']*)'")
    addr = g(r"kinderAddr\s*=\s*'주소 : '\s*\+\s*'([^']*)'")
    web = g(r"homepage\s*=\s*'홈페이지 : '\s*\+\s*'([^']*)'")
    web = web.strip() if web else ''
    return {'addr': addr.replace('서울특별시', '', 1).strip() if addr else None,  # 경기는 '경기도 …' 그대로(build_pages가 앞에 '서울'을 붙이지 않음)
            'tel': tel.strip() if tel else None,
            'web': web if web.startswith(('http://', 'https://')) else None}


def parse_safety(text):
    p = Tables()
    p.feed(text)
    out = {}
    # 사이트 HTML이 CCTV 표 첫 칸의 </td>를 빼먹어 '설치' 칸이 사라질 수 있음(2026-11-21) → 칸 위치 대신
    # '미운영/미설치' 글자와 첫 숫자로 판단한다. 첫 숫자 = 운행 차량수 / 총 설치수.
    for t in p.tables:
        last = t['rows'][-1] if t['rows'] else []
        nums = [n for n in map(num, last) if n is not None]
        val = 0 if any(x.startswith('미') for x in last) or not nums else nums[0]
        if t['caption'].startswith('통학차량 현황') and last:
            out['bus'] = val
        elif t['caption'].startswith('CCTV 설치 현황') and last:
            out['cctv'] = val
    return out


def fetch(tab, code):
    data = urllib.parse.urlencode({'ittId': code}).encode()
    for i in range(3):
        try:
            req = urllib.request.Request(BASE + tab + '.do', data=data, headers={'User-Agent': 'kindergarten-map-updater'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception:
            if i == 2:
                raise
            time.sleep(3 * (i + 1))


def one(code):
    d = parse_summary(fetch('kinderSummary', code))
    time.sleep(0.3)
    d.update(parse_safety(fetch('kinderSafetyManagement', code)))
    if not d.get('addr') and not d.get('tel'):
        raise ValueError('요약 화면에서 주소·전화를 못 찾음')
    return d


def save(d):
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(dict(sorted(d.items(), key=lambda x: int(x[0]))), f, ensure_ascii=False, separators=(',', ':'))


def main():
    import datetime
    from concurrent.futures import ThreadPoolExecutor, as_completed
    args = sys.argv[1:]
    if args[:1] == ['--parse']:
        d = parse_summary(open(args[1], encoding='utf-8').read())
        d.update(parse_safety(open(args[2], encoding='utf-8').read()))
        print(d)
        return
    opt = lambda k, v: type(v)(args[args.index(k) + 1]) if k in args else v
    days, minutes, limit = opt('--days', 25), opt('--minutes', 0.0), opt('--limit', 0)
    today = datetime.date.today()
    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    age = lambda kid: (today - datetime.date.fromisoformat(old[kid]['t'])).days if old.get(kid, {}).get('t') else 10 ** 6
    act = active_ids()
    if act:
        old = {k: v for k, v in old.items() if k in act}  # 휴원·폐원한 곳 값은 지움(지도·페이지에 안 쓰임)
    todo = [(c, str(k)) for c, k in json.load(open(IDS, encoding='utf-8')).items() if age(str(k)) >= days and (not act or str(k) in act)]
    todo.sort(key=lambda x: -age(x[1]))
    if limit:
        todo = todo[:limit]
    print(f'상세정보: {len(todo)}곳 받을 차례(받은 지 {days}일 이상)')
    deadline = time.time() + minutes * 60 if minutes else None
    new, ok, fail, skipped = dict(old), 0, 0, 0
    with ThreadPoolExecutor(3) as ex:
        it = iter(todo)
        run = {}
        def submit():
            nonlocal skipped
            for c, k in it:
                if deadline and time.time() > deadline:
                    skipped += 1
                    continue
                run[ex.submit(one, c)] = (c, k)
                return
        for _ in range(3):
            submit()
        while run:
            f = next(as_completed(run))
            c, k = run.pop(f)
            try:
                new[k] = dict(f.result(), t=today.isoformat())
                ok += 1
            except Exception as e:
                fail += 1
                print(f'  실패 {k} {c}: {e}', file=sys.stderr)
            if (ok + fail) % 100 == 0:
                save(new)
                print(f'  {ok + fail}/{len(todo)}')
            if fail > 30 and fail > (ok + fail) * 0.5:
                save(new)
                sys.exit('실패가 너무 많아 멈춥니다.')
            time.sleep(0.2)
            submit()
    save(new)
    print(f'상세정보 완료: 성공 {ok}, 실패 {fail}(예전 값 유지), 시간 넘어 다음으로 미룸 {skipped}, 파일에 {len(new)}곳')


if __name__ == '__main__':
    main()

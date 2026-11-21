"""유치원알리미 유치원별 요약·안전 화면 → src/data/kg_detail.json (주소·전화·홈페이지·통학차량 대수·CCTV 수).

SEO 기관별 페이지(scripts/build_pages.py)에 쓰는 값. OPEN API에는 대수·설치수가 없어서
유치원알리미 상세 화면 두 탭을 유치원마다 받는다. 로그인·인증키 불필요.
- 요약 탭 POST /kinderMt/kinderSummary.do  ittId=유치원코드 → 지도 스크립트 변수(전화·주소·홈페이지)
- 안전 탭 POST /kinderMt/kinderSafetyManagement.do → 표 '통학차량 현황', 'CCTV 설치 현황'의 마지막 행
유치원코드는 src/data/kg_ids.json(유치원코드 → id).

사용법 (저장소 루트에서):
    python3 scripts/fetch_detail.py                 # 서울 전체(약 15분)
    python3 scripts/fetch_detail.py --limit 20      # 앞 20곳만(시험)
    python3 scripts/fetch_detail.py --parse 요약.html 안전.html   # 파서 시험

결과: {id: {"addr": "성북구 …", "tel": "02-…", "web": "http…"|null, "bus": 운행 차량 수(0=미운영), "cctv": 총 설치수}}
- 한 곳이 실패하면 그곳은 예전 값을 그대로 둔다. 80% 넘게 받아야 저장.
"""
import json, os, re, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_cost import Tables  # caption별 표 파서 재사용

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
OUT = os.path.join(ROOT, 'src', 'data', 'kg_detail.json')
IDS = os.path.join(ROOT, 'src', 'data', 'kg_ids.json')
BASE = 'https://e-childschoolinfo.moe.go.kr/kinderMt/'
MIN_OK = 0.8


def num(s):
    m = re.search(r'\d+', s or '')
    return int(m.group()) if m else None


def parse_summary(text):
    g = lambda pat: (re.search(pat, text) or [None, None])[1]
    tel = g(r"kinderTel\s*=\s*'전화번호 : '\s*\+\s*'([^']*)'")
    addr = g(r"kinderAddr\s*=\s*'주소 : '\s*\+\s*'([^']*)'")
    web = g(r"homepage\s*=\s*'홈페이지 : '\s*\+\s*'([^']*)'")
    web = web.strip() if web else ''
    return {'addr': addr.replace('서울특별시', '', 1).strip() if addr else None,
            'tel': tel.strip() if tel else None,
            'web': web if web.startswith(('http://', 'https://')) else None}


def parse_safety(text):
    p = Tables()
    p.feed(text)
    out = {}
    for t in p.tables:
        last = t['rows'][-1] if t['rows'] else []
        if t['caption'].startswith('통학차량 현황') and last:
            out['bus'] = num(last[1]) if last[0] == '운영' and len(last) > 1 else 0
        elif t['caption'].startswith('CCTV 설치 현황') and last:
            out['cctv'] = num(last[1]) if last[0] == '설치' and len(last) > 1 else 0
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


def main():
    args = sys.argv[1:]
    if args[:1] == ['--parse']:
        d = parse_summary(open(args[1], encoding='utf-8').read())
        d.update(parse_safety(open(args[2], encoding='utf-8').read()))
        print(d)
        return
    limit = int(args[args.index('--limit') + 1]) if '--limit' in args else None
    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    codes = list(json.load(open(IDS, encoding='utf-8')).items())[:limit]
    new, fail = dict(old), 0
    for n, (code, kid) in enumerate(codes, 1):
        try:
            new[str(kid)] = one(code)
        except Exception as e:
            fail += 1
            print(f'  실패 {kid} {code}: {e}', file=sys.stderr)
            if fail > 30 and fail > n * 0.5:
                sys.exit('실패가 너무 많아 멈춥니다.')
        if n % 100 == 0:
            print(f'  {n}/{len(codes)}')
        time.sleep(0.3)
    ok = len(codes) - fail
    if ok < len(codes) * MIN_OK:
        sys.exit(f'상세정보를 {ok}/{len(codes)}곳만 받아 저장하지 않습니다.')
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(dict(sorted(new.items(), key=lambda x: int(x[0]))), f, ensure_ascii=False, separators=(',', ':'))
    print(f'상세정보 완료: {ok}/{len(codes)}곳 (실패 {fail}곳은 예전 값 유지), 파일에 {len(new)}곳')


if __name__ == '__main__':
    main()

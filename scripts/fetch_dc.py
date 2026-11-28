"""어린이집정보공개포털 「어린이집별 기본정보 조회」(cpmsapi030) → src/data/dc_seoul.json 갱신(서울 25개 구).

사용법 (저장소 루트에서):
    CHILDCARE_API_KEY=운영키 python3 scripts/fetch_dc.py
    python3 scripts/fetch_dc.py --fixtures 폴더   # {시군구코드}.json(응답 item 목록)으로 오프라인 테스트, 파일은 안 씀
    python3 scripts/fetch_dc.py --merge           # API는 안 부르고, dc_portal.json 값만 dc_seoul.json에 다시 합침
                                                  # (워크플로: API → 포털 수집 → 합치기 순서라 새로 생긴 곳도 같은 달에 채워짐)

- 운영계정 키 필요(개발키는 01, 02… 자리표시 값만 돌려줌). 운영계정 만료 2027-11-09 → 12개월마다 갱신.
- API에 없는 운영시간·평가·연장보육은 src/data/dc_portal.json(scripts/fetch_dc_portal.py, 포털 화면 수집)에서,
  없으면 기존 값을 이어 쓴다(새 어린이집은 비움).
- 교사 수 = 보육교사(A2) + 특수교사(A3), 가정어린이집은 원장(A1)도 포함(원장이 보육 겸임).
  기존 포털 스크랩 값과 대부분 같고 날짜 차이로 ±1 정도 다름.
- 휴지(휴원) 상태는 뺀다. 받은 수가 기존의 80% 미만이면 파일을 쓰지 않고 실패로 끝낸다.
"""
import json, os, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DATA = os.path.join(ROOT, 'src', 'data', 'dc_seoul.json')
PORTAL = os.path.join(ROOT, 'src', 'data', 'dc_portal.json')
URL = 'http://api.childcare.go.kr/mediate/rest/cpmsapi030/cpmsapi030/request'
DISTRICTS = {
    '11110': '종로구', '11140': '중구', '11170': '용산구', '11200': '성동구', '11215': '광진구', '11230': '동대문구',
    '11260': '중랑구', '11290': '성북구', '11305': '강북구', '11320': '도봉구', '11350': '노원구', '11380': '은평구',
    '11410': '서대문구', '11440': '마포구', '11470': '양천구', '11500': '강서구', '11530': '구로구', '11545': '금천구',
    '11560': '영등포구', '11590': '동작구', '11620': '관악구', '11650': '서초구', '11680': '강남구', '11710': '송파구',
    '11740': '강동구',
    # 경기도 1차 시험(2026-11-27): 성남(구 3곳)·광명(구 없음). 시군구 코드는 행정표준코드 기준, 첫 실행에서 확인
    '41131': '성남 수정구', '41133': '성남 중원구', '41135': '성남 분당구', '41210': '광명시',
    # 2차(2026-11-27): 하남·안양(구 2곳)·과천·부천(2024년 구 다시 설치, 3곳)
    '41450': '하남시', '41171': '안양 만안구', '41173': '안양 동안구', '41290': '과천시',
    '41192': '부천 원미구', '41194': '부천 소사구', '41196': '부천 오정구',
    # 3차(2026-11-27): 고양(구 3곳)·구리·남양주·의정부·김포·의왕·군포·시흥
    '41281': '고양 덕양구', '41285': '고양 일산동구', '41287': '고양 일산서구', '41310': '구리시',
    '41360': '남양주시', '41150': '의정부시', '41570': '김포시', '41430': '의왕시', '41410': '군포시', '41390': '시흥시',
    '41111': '수원 장안구', '41113': '수원 권선구', '41115': '수원 팔달구', '41117': '수원 영통구',
    '41460': '용인시',
    '41271': '안산 상록구', '41273': '안산 단원구', '41220': '평택시', '41480': '파주시',
    '41610': '광주시', '41370': '오산시', '41500': '이천시', '41630': '양주시', '41550': '안성시',
    '41650': '포천시', '41670': '여주시', '41250': '동두천시',
    '41830': '양평군', '41820': '가평군', '41800': '연천군'}
# 시 코드로 한 번 받아 주소의 구 이름으로 나누는 곳. 용인은 구 코드가 어긋남(2026-11: 41463이 수지구 주소를, 41465는 결과 없음)
# 결과가 없으면 옛 코드로 다시 받는 곳(여주는 2013년 시 승격 전 여주군 41730)
ALT_CODES = {'41670': ['41730']}
CITY_SPLIT = {'41460': ['용인 처인구', '용인 기흥구', '용인 수지구']}
KEEP = ['운영시간', '평가완료', '평가연월', '평가', '연장반', '연장아동']  # API에 없는 항목
# 나이별 반(cpmsapi030 명세서 v1.7): class_cnt_*/child_cnt_* — 만0~5세, 영아혼합(0~2), 영유아혼합(2~3), 유아혼합(3~5), 특수
AGES = ['00', '01', '02', '03', '04', '05', 'M2', 'M3', 'M5', 'SP']
WAIT = ['00', '01', '02', '03', '04', '05', 'M6', 'TOT']  # ew_cnt_* 입소대기아동수(명세서엔 있음, 실제 값이 오는지 확인용으로 저장)
NEW_COLS = ['연령별', '대기']
TYPE = {'국공립': '국공립', '민간': '민간', '가정': '가정'}  # 나머지(직장·법인단체·사회복지법인·협동)는 '직장·법인'


def fetch(arcode, key):
    q = urllib.parse.urlencode({'key': key, 'arcode': arcode})
    for i in range(4):
        try:
            req = urllib.request.Request(f'{URL}?{q}', headers={'User-Agent': 'kindergarten-map-updater'})
            with urllib.request.urlopen(req, timeout=90) as r:
                root = ET.fromstring(r.read())
            err = root.findtext('errmsg')
            if err:
                raise RuntimeError(f'{arcode}: {root.findtext("errcode")} {err}')
            items = [{c.tag: (c.text or '').strip() for c in it} for it in root.iter('item')]
            if items and items[0].get('crname') == '04':
                raise RuntimeError('개발키입니다. 운영계정 키가 필요합니다.')
            return items
        except Exception as e:
            if i == 3 or '키' in str(e):
                raise
            print(f'  재시도 {arcode}: {e}', file=sys.stderr)
            time.sleep(5 * (i + 1))


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def get(a, k):  # 응답 태그 대소문자가 섞여 있어(crcapat, EM_CNT_0Y) 둘 다 본다
    v = a.get(k)
    if v in (None, ''):
        v = a.get(k.upper()) if a.get(k.upper()) not in (None, '') else a.get(k.lower())
    return v


def convert(a, gu):
    em = lambda k: int(num(get(a, 'EM_CNT_' + k)))
    by_age = [[int(num(get(a, 'CLASS_CNT_' + x))), int(num(get(a, 'CHILD_CNT_' + x)))] for x in AGES]
    wait = [get(a, 'EW_CNT_' + x) for x in WAIT]
    ty = TYPE.get(a.get('crtypename'), '직장·법인')
    teachers = em('A2') + em('A3') + (em('A1') if ty == '가정' else 0)
    kids, cap = int(num(a.get('crchcnt'))), int(num(a.get('crcapat')))
    spec = [s for s in (a.get('crspec') or '').split(',') if s and s != '일반']
    return {
        'id': 'c' + a['stcode'],
        '유치원명': a['crname'].strip(),
        '설립유형': a.get('crtypename', ''),
        '유형': ty,
        '구': gu,
        '위도': round(num(a.get('la')), 6),
        '경도': round(num(a.get('lo')), 6),
        '원아수': kids,
        '정원': cap,
        '충원율': round(kids / cap * 100) if cap else None,
        '교사수': teachers or None,
        '교사1인당원아': round(kids / teachers, 1) if teachers else None,
        '1년미만비율': round(num(a.get('EM_CNT_0Y')), 1) if teachers else None,
        '4년이상비율': round(num(a.get('EM_CNT_4Y')) + num(a.get('EM_CNT_6Y')), 1) if teachers else None,
        '차량운영여부': a.get('crcargbname') or '미운영',
        'CCTV': int(num(a.get('cctvinstlcnt'))),
        '보육실': int(num(a.get('nrtrroomcnt'))),
        '놀이터': int(num(a.get('plgrdco'))),
        '특성': '|'.join(spec),
        '주소': a.get('craddr', ''),
        '전화': a.get('crtelno', ''),
        '연령별': by_age if any(c or k for c, k in by_age) else None,  # [[반 수, 아동 수] × AGES]
        '대기': [int(num(x)) for x in wait] if any(x not in (None, '') for x in wait) else None,
    }


def merge_portal():
    d = json.load(open(DATA, encoding='utf-8'))
    portal = json.load(open(PORTAL, encoding='utf-8')) if os.path.exists(PORTAL) else {}
    idx = {c: i for i, c in enumerate(d['cols'])}
    n = 0
    for row in d['rows']:
        pt = portal.get(row[idx['id']][1:])
        if not pt:
            continue  # 포털 값이 없으면 지금 값 유지(fetch_dc 본 실행과 같은 규칙)
        for k in KEEP:
            v = pt.get(k) if k != '운영시간' else (pt.get(k) or None)
            if row[idx[k]] != v:
                row[idx[k]] = v; n += 1
    with open(DATA, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, separators=(',', ':'))
    print(f'포털 값 합치기: {len(d["rows"])}곳 중 바뀐 칸 {n}개')


def main():
    args = sys.argv[1:]
    if args[:1] == ['--merge']:
        return merge_portal()
    test = args[:1] == ['--fixtures']
    raw = []
    for code, gu in DISTRICTS.items():
        if test:
            items = json.load(open(os.path.join(args[1], code + '.json'), encoding='utf-8'))
        else:
            key = os.environ.get('CHILDCARE_API_KEY')
            if not key:
                sys.exit('CHILDCARE_API_KEY 환경변수가 없습니다.')
            try:
                items = fetch(code, key)
            except RuntimeError as e:
                if 'INFO-200' not in str(e) or code not in ALT_CODES:
                    raise
                for alt in ALT_CODES[code]:
                    try:
                        items = fetch(alt, key)
                        print(f'  {gu}: {code} 결과 없음 → 옛 코드 {alt}로 받음', file=sys.stderr)
                        break
                    except RuntimeError as e2:
                        if 'INFO-200' not in str(e2) or alt == ALT_CODES[code][-1]:
                            raise
            time.sleep(1)
        if code in CITY_SPLIT:
            for lab in CITY_SPLIT[code]:
                g = lab.split()[1]
                part = [a for a in items if f' {g} ' in f" {a.get('craddr', '')} "]
                print(f'{lab}: {len(part)}곳')
                raw += [(a, lab) for a in part]
            left = len(items) - sum(1 for a in items if any(f" {l.split()[1]} " in f" {a.get('craddr', '')} " for l in CITY_SPLIT[code]))
            if left:
                print(f'  {gu}: 주소에 구 이름이 없어 뺀 곳 {left}곳', file=sys.stderr)
            continue
        print(f'{gu}: {len(items)}곳')
        raw += [(a, gu) for a in items]

    new = [convert(a, gu) for a, gu in raw
           if a.get('crstatusname') not in ('휴지', '폐지') and not a.get('crabldt') and num(a.get('la'))]

    old = json.load(open(DATA, encoding='utf-8'))
    cols = old['cols'] + [c for c in NEW_COLS if c not in old['cols']]
    old_rows = [dict(zip(cols, r)) for r in old['rows']]
    by_id = {r['id']: r for r in old_rows}
    by_name = {(r['구'], r['유치원명']): r for r in old_rows}
    portal = json.load(open(PORTAL, encoding='utf-8')) if os.path.exists(PORTAL) else {}
    if len(new) < len(old_rows) * 0.8:
        sys.exit(f'받은 어린이집이 {len(new)}곳뿐이라 갱신하지 않습니다(기존 {len(old_rows)}곳).')

    rows = []
    new_ids = {n['id'] for n in new}
    for n in new:
        prev = by_id.get(n['id'])
        if not prev:  # id가 바뀐 곳만 이름으로 찾되, 지금 다른 곳이 쓰는 id는 물려받지 않음(같은 이름이 옆 구에 있을 때)
            prev = by_name.get((n['구'], n['유치원명']))
            if prev and prev['id'] in new_ids:
                prev = None
        if prev:
            n['id'] = prev['id']  # 공유된 상세 주소(#kc…) 유지
        pt = portal.get(n['id'][1:])
        for k in KEEP:
            n[k] = pt.get(k) if pt else (prev or {}).get(k)
        if not n.get('운영시간'):
            n['운영시간'] = None
        rows.append(n)
    rows.sort(key=lambda r: r['id'])

    if test:
        diff = {}
        for n in rows:
            o = by_id.get(n['id'])
            if not o:
                print('새 어린이집', n['유치원명']); continue
            for c in cols:
                if o.get(c) != n.get(c):
                    diff.setdefault(c, []).append((n['유치원명'], o.get(c), n.get(c)))
        for c, v in diff.items():
            print(c, len(v), v[:3])
        print('빠진 곳', [r['유치원명'] for r in old_rows if r['id'] not in {n['id'] for n in rows}])
        print('총', len(rows))
        return

    with open(DATA, 'w', encoding='utf-8') as f:
        # t = 받은 날 → 화면 상세 '자료 기준'
        json.dump({'cols': cols, 'rows': [[r.get(c) for c in cols] for r in rows], 't': time.strftime('%Y-%m-%d')},
                  f, ensure_ascii=False, separators=(',', ':'))
    print(f'완료: {len(rows)}곳 (기존 {len(old_rows)}곳)')


if __name__ == '__main__':
    main()

"""유치원알리미 OPEN API → src/data/kg_seoul.json.txt 갱신.

사용법 (저장소 루트에서):
    KINDER_API_KEY=발급키 python3 scripts/fetch_kg.py
    python3 scripts/fetch_kg.py --fixtures 폴더   # 저장해 둔 API 응답으로 테스트 (네트워크 없이)

- 서울 25개 구 × 5개 API(일반현황·교원·근속·수업일수·통학차량)를 받아 기존과 같은 cols/rows 형식으로 만든다.
- 기존 id는 유치원코드(kindercode) → id 대응표(src/data/kg_ids.json)로 유지한다. 처음엔 (구, 이름)으로 맞춘다.
  상세 화면 주소(#k{id})가 바뀌지 않게 하기 위함.
- 방과후참여율은 API에 없어 「공시자료 다운로드」의 '방과후 과정 편성ㆍ운영' CSV(1차 공시에만 있음, 키 불필요)에서
  가장 최근 1차 공시를 받아 참여원아 계 / 원아수로 계산한다. (구, 유치원명)으로 맞추고, 못 받거나 없는 곳은 기존 값을 이어 쓴다.
- 받은 유치원 수가 너무 적으면(일부 구 실패 등) 파일을 쓰지 않고 실패로 끝낸다 → 깨진 데이터가 배포되지 않음.
"""
import csv, datetime, io, json, os, sys, time, urllib.parse, urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DATA = os.path.join(ROOT, 'src', 'data', 'kg_seoul.json.txt')
IDS = os.path.join(ROOT, 'src', 'data', 'kg_ids.json')
BASE = 'https://e-childschoolinfo.moe.go.kr/api/notice/'
APIS = ['basicInfo2', 'teachersInfo', 'yearOfWork', 'lessonDay', 'schoolBus']
SEOUL = {
    11110: '종로구', 11140: '중구', 11170: '용산구', 11200: '성동구', 11215: '광진구', 11230: '동대문구',
    11260: '중랑구', 11290: '성북구', 11305: '강북구', 11320: '도봉구', 11350: '노원구', 11380: '은평구',
    11410: '서대문구', 11440: '마포구', 11470: '양천구', 11500: '강서구', 11530: '구로구', 11545: '금천구',
    11560: '영등포구', 11590: '동작구', 11620: '관악구', 11650: '서초구', 11680: '강남구', 11710: '송파구',
    11740: '강동구',
}
MIN_ROWS = 600  # 지금 705곳. 이보다 크게 줄면 무언가 잘못된 것
SITE = 'https://e-childschoolinfo.moe.go.kr'
AFTERSCHOOL_CODE = '111'  # 공시항목 '방과후 과정 편성ㆍ운영에 관한 사항'


def http(url, data=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers={'User-Agent': 'kindergarten-map-updater'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8-sig')


def fetch_afterschool():
    """가장 최근 1차 공시의 서울 방과후 CSV → ({(구, 이름): 참여원아 계}, 차수). 실패하면 ({}, None)."""
    try:
        for y in range(datetime.date.today().year, datetime.date.today().year - 3, -1):
            timing = f'{y}1'
            items = json.loads(http(f'{SITE}/gongsi/{timing}/findGongsiList.do'))
            if AFTERSCHOOL_CODE not in items.values():
                continue
            form = urllib.parse.urlencode({'combineSidoName': '서울특별시', 'combineSidoCode': '11', 'timingListCode': timing,
                                           'gongsiListCode': AFTERSCHOOL_CODE, 'safetyListCode': '', 'ExcelCsv': '2'}).encode()
            return parse_afterschool(http(f'{SITE}/download/getOpenData.do', form, timeout=120)), timing
    except Exception as e:
        print(f'방과후 CSV를 받지 못해 기존 값을 씁니다: {e}', file=sys.stderr)
    return {}, None


def parse_afterschool(text):
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        addr = (r.get('주소') or '').split()
        if len(addr) > 1 and r.get('유치원명'):
            out[(addr[1], r['유치원명'].strip())] = num(r.get('참여원아 계'))
    return out


def fetch(api, sgg, key):
    q = urllib.parse.urlencode({'key': key, 'sidoCode': 11, 'sggCode': sgg})
    for i in range(4):
        try:
            req = urllib.request.Request(f'{BASE}{api}.do?{q}', headers={'User-Agent': 'kindergarten-map-updater'})
            with urllib.request.urlopen(req, timeout=30) as r:
                j = json.loads(r.read().decode('utf-8'))
            if j.get('status') != 'SUCCESS':
                raise RuntimeError(f"{api} {sgg}: {j.get('status')} {j.get('message')}")
            return next(v for v in j.values() if isinstance(v, list))
        except Exception as e:
            if i == 3:
                raise
            print(f'  재시도 {api} {sgg}: {e}', file=sys.stderr)
            time.sleep(3 * (i + 1))


def num(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


AGES = [('clcnt3', 'ag3fpcnt', 'ppcnt3'), ('clcnt4', 'ag4fpcnt', 'ppcnt4'), ('clcnt5', 'ag5fpcnt', 'ppcnt5'),
        ('mixclcnt', 'mixfpcnt', 'mixppcnt'), ('shclcnt', 'spcnfpcnt', 'shppcnt')]


def age_breakdown(b):
    """[[반 수, 정원, 원아] × (만3, 만4, 만5, 혼합, 특수)]"""
    return [[num(b.get(c)), num(b.get(f)), num(b.get(p))] for c, f, p in AGES]


def pct(a, b):
    return round(a / b * 100) if b else None


def build(raw):
    """raw: {api: [rows...]} (서울 전체) → rows 목록 (kindercode, 구, 이름 포함)"""
    by = {a: {x['kindercode']: x for x in raw[a]} for a in APIS[1:]}
    basics = raw['basicInfo2']
    # 폐원·공시 중단 등으로 예전 공시만 남은 곳 제외: 가장 최근 공시 연도만 사용
    year = max(str(x.get('pbnttmng') or '')[:4] for x in basics)
    out = []
    for b in basics:
        if str(b.get('pbnttmng') or '')[:4] != year:
            continue
        k = b['kindercode']
        t, y, l, s = (by[a].get(k, {}) for a in APIS[1:])
        try:
            lat, lng = round(float(b['lttdcdnt']), 5), round(float(b['lngtcdnt']), 5)
        except (KeyError, TypeError, ValueError):
            continue
        if not lat or not lng:
            continue
        kids = sum(num(b.get(f)) for f in ('ppcnt3', 'ppcnt4', 'ppcnt5', 'mixppcnt', 'shppcnt'))
        classes = sum(num(b.get(f)) for f in ('clcnt3', 'clcnt4', 'clcnt5', 'mixclcnt', 'shclcnt'))
        by_age = age_breakdown(b)
        cap = sum(x[1] for x in by_age)  # 올해 만든 반들의 정원 합
        years = [num(y.get(f)) for f in ('yy1_undr_thcnt', 'yy1_abv_yy2_undr_thcnt', 'yy2_abv_yy4_undr_thcnt',
                                          'yy4_abv_yy6_undr_thcnt', 'yy6_abv_thcnt')]
        teachers = sum(years)
        days = max([num(l.get(f)) for f in ('ag3_lsn_dcnt', 'ag4_lsn_dcnt', 'ag5_lsn_dcnt', 'mix_age_lsn_dcnt')] or [0])
        est = b.get('establish') or ''
        ot = (b.get('opertime') or '').replace('시', ':').replace('분', '').replace(' ', '')
        bus = s.get('vhcl_oprn_yn')
        addr = (b.get('addr') or '').split()
        out.append({
            'kindercode': k,
            '유치원명': b['kindername'].strip(),
            '설립유형': est,
            '유형': '사립' if est.startswith('사립') else '국공립',
            '구': addr[1] if len(addr) > 1 and addr[1].endswith('구') else b.get('_gu', ''),
            '위도': lat, '경도': lng,
            '원아수': kids,
            '충원율': float(round(kids / cap * 100)) if cap else None,  # 반 정원 기준 (2026-11-10부터)
            '정원': cap or None,
            '인가정원': num(b.get('prmstfcnt')) or None,
            '연령별': by_age,
            '학급당원아': round(kids / classes, 1) if classes else None,
            '교사1인당원아': round(kids / teachers, 1) if teachers else None,
            '4년이상비율': float(pct(years[3] + years[4], teachers)) if teachers else None,
            '1년미만비율': float(pct(years[0], teachers)) if teachers else None,
            '운영시간': ot or None,
            '수업일수': days or None,
            '차량운영여부': {'Y': '운영', 'N': '미운영'}.get(bus),
            '데이터주의': 1 if teachers and classes and teachers < classes else 0,
        })
    return out


def main():
    args = sys.argv[1:]
    raw = {a: [] for a in APIS}
    if args[:1] == ['--fixtures']:
        d = args[1]
        for a in APIS:
            rows = next(v for v in json.load(open(os.path.join(d, a + '.json'), encoding='utf-8')).values() if isinstance(v, list))
            raw[a] += rows
        min_rows = 1
        f = [x for x in os.listdir(d) if x.startswith('afterschool') and x.endswith('.csv')]
        aft, timing = (parse_afterschool(open(os.path.join(d, f[0]), encoding='utf-8-sig').read()), f[0]) if f else ({}, None)
    else:
        key = os.environ.get('KINDER_API_KEY')
        if not key:
            sys.exit('KINDER_API_KEY 환경변수가 없습니다.')
        for sgg, gu in SEOUL.items():
            for a in APIS:
                rows = fetch(a, sgg, key)
                if a == 'basicInfo2':
                    for x in rows:
                        x['_gu'] = gu
                raw[a] += rows
                time.sleep(0.3)
            print(f'{gu}: {len([x for x in raw["basicInfo2"] if x.get("_gu") == gu])}곳')
        min_rows = MIN_ROWS
        aft, timing = fetch_afterschool()
    if aft:
        print(f'방과후 공시 {timing}: {len(aft)}곳')

    new = build(raw)
    if len(new) < min_rows:
        sys.exit(f'받은 유치원이 {len(new)}곳뿐이라 갱신하지 않습니다(최소 {min_rows}).')

    old = json.load(open(DATA, encoding='utf-8'))
    cols = old['cols'] + [c for c in ('정원', '인가정원', '연령별') if c not in old['cols']]
    old_rows = [dict(zip(cols, r)) for r in old['rows']]
    by_name = {}
    for r in old_rows:
        by_name.setdefault((r['구'], r['유치원명']), []).append(r)
    ids = json.load(open(IDS, encoding='utf-8')) if os.path.exists(IDS) else {}
    by_id = {r['id']: r for r in old_rows}
    next_id = max([r['id'] for r in old_rows] + list(ids.values()) + [-1]) + 1
    used = set()

    rows = []
    for n in new:
        prev = None
        if n['kindercode'] in ids:
            prev = by_id.get(ids[n['kindercode']]) or {'id': ids[n['kindercode']]}
        else:
            cands = [r for r in by_name.get((n['구'], n['유치원명']), []) if r['id'] not in used]
            if cands:  # 같은 구 같은 이름이 여럿이면 가장 가까운 곳
                prev = min(cands, key=lambda r: (r['위도'] - n['위도']) ** 2 + (r['경도'] - n['경도']) ** 2)
        if prev and prev['id'] not in used:
            n['id'] = prev['id']
        else:
            n['id'] = next_id
            next_id += 1
        used.add(n['id'])
        ids[n['kindercode']] = n['id']
        p = aft.get((n['구'], n['유치원명']))
        n['방과후참여율'] = float(round(p / n['원아수'] * 100)) if p is not None and n['원아수'] else (prev or {}).get('방과후참여율')
        rows.append(n)

    rows.sort(key=lambda r: r['id'])
    if args[:1] == ['--fixtures']:
        # 테스트: 기존 값과 다른 칸 개수만 보여 주고 파일은 쓰지 않음
        diff = {}
        for n in rows:
            o = by_id.get(n['id'])
            if not o:
                print('새 유치원', n['유치원명']); continue
            for c in cols:
                if o.get(c) != n.get(c):
                    diff.setdefault(c, []).append((n['유치원명'], o.get(c), n.get(c)))
        for c, v in diff.items():
            print(c, len(v), v[:3])
        print('총', len(rows))
        return

    with open(DATA, 'w', encoding='utf-8') as f:
        json.dump({'cols': cols, 'rows': [[r.get(c) for c in cols] for r in rows]}, f, ensure_ascii=False, separators=(',', ':'))
    with open(IDS, 'w', encoding='utf-8') as f:
        json.dump(ids, f, ensure_ascii=False, indent=0, sort_keys=True)
    print(f'완료: {len(rows)}곳 (기존 {len(old_rows)}곳)')


if __name__ == '__main__':
    main()

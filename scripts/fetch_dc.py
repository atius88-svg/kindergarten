"""어린이집정보공개포털 「어린이집별 기본정보 조회」(cpmsapi030) → src/data/dc_seongbuk.json 갱신.

사용법 (저장소 루트에서):
    CHILDCARE_API_KEY=운영키 python3 scripts/fetch_dc.py
    python3 scripts/fetch_dc.py --fixtures 폴더   # {시군구코드}.json(응답 item 목록)으로 오프라인 테스트, 파일은 안 씀

- 운영계정 키 필요(개발키는 01, 02… 자리표시 값만 돌려줌). 운영계정 만료 2027-11-09 → 12개월마다 갱신.
- API에 없는 운영시간·평가·연장보육은 기존 값을 그대로 이어 쓴다(새 어린이집은 비움).
- 교사 수 = 보육교사(A2) + 특수교사(A3), 가정어린이집은 원장(A1)도 포함(원장이 보육 겸임).
  기존 포털 스크랩 값과 대부분 같고 날짜 차이로 ±1 정도 다름.
- 휴지(휴원) 상태는 뺀다. 받은 수가 기존의 80% 미만이면 파일을 쓰지 않고 실패로 끝낸다.
"""
import json, os, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DATA = os.path.join(ROOT, 'src', 'data', 'dc_seongbuk.json')
URL = 'http://api.childcare.go.kr/mediate/rest/cpmsapi030/cpmsapi030/request'
DISTRICTS = {'11290': '성북구'}  # 서울 25개 구로 넓힐 때 여기에 추가
KEEP = ['운영시간', '평가완료', '평가연월', '평가', '연장반', '연장아동']  # API에 없는 항목
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


def convert(a, gu):
    em = lambda k: int(num(a.get('EM_CNT_' + k)))
    ty = TYPE.get(a.get('crtypename'), '직장·법인')
    teachers = em('A2') + em('A3') + (em('A1') if ty == '가정' else 0)
    kids, cap = int(num(a.get('crchcnt'))), int(num(a.get('crcapat')))
    spec = [s for s in (a.get('crspec') or '').split(',') if s and s != '일반']
    return {
        'id': 'c' + a['stcode'],
        '유치원명': a['crname'].strip(),
        '설립유형': a.get('crtypename', ''),
        '유형': ty,
        '구': a.get('sigunname') or gu,
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
    }


def main():
    args = sys.argv[1:]
    test = args[:1] == ['--fixtures']
    raw = []
    for code, gu in DISTRICTS.items():
        if test:
            items = json.load(open(os.path.join(args[1], code + '.json'), encoding='utf-8'))
        else:
            key = os.environ.get('CHILDCARE_API_KEY')
            if not key:
                sys.exit('CHILDCARE_API_KEY 환경변수가 없습니다.')
            items = fetch(code, key)
            time.sleep(1)
        print(f'{gu}: {len(items)}곳')
        raw += [(a, gu) for a in items]

    new = [convert(a, gu) for a, gu in raw
           if a.get('crstatusname') not in ('휴지', '폐지') and not a.get('crabldt') and num(a.get('la'))]

    old = json.load(open(DATA, encoding='utf-8'))
    cols = old['cols']
    old_rows = [dict(zip(cols, r)) for r in old['rows']]
    by_id = {r['id']: r for r in old_rows}
    by_name = {(r['구'], r['유치원명']): r for r in old_rows}
    if len(new) < len(old_rows) * 0.8:
        sys.exit(f'받은 어린이집이 {len(new)}곳뿐이라 갱신하지 않습니다(기존 {len(old_rows)}곳).')

    rows = []
    for n in new:
        prev = by_id.get(n['id']) or by_name.get((n['구'], n['유치원명']))
        if prev:
            n['id'] = prev['id']  # 공유된 상세 주소(#kc…) 유지
        for k in KEEP:
            n[k] = (prev or {}).get(k)
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
        json.dump({'cols': cols, 'rows': [[r.get(c) for c in cols] for r in rows]}, f, ensure_ascii=False, separators=(',', ':'))
    print(f'완료: {len(rows)}곳 (기존 {len(old_rows)}곳)')


if __name__ == '__main__':
    main()

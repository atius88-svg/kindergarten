"""유치원알리미 유치원별 「교육·보육 비용」 화면 → src/data/kg_cost_seoul.json (서울 전체 원비).

원비는 OPEN API·공시자료 다운로드 어디에도 없어서, 유치원알리미 상세 화면 중 비용 탭
(POST /kinderMt/kinderEducateAndCost.do, ittId=유치원코드)을 유치원마다 한 번씩 받아 표에서 숫자를 뽑는다.
로그인·인증키 불필요. 유치원코드는 src/data/kg_ids.json(유치원코드 → id)에서 가져온다.

사용법 (저장소 루트에서):
    python3 scripts/fetch_cost.py            # 공시 차수가 바뀌었을 때만 서울 전체를 다시 받음
    python3 scripts/fetch_cost.py --force    # 무조건 다시 받음
    python3 scripts/fetch_cost.py --parse 파일.html   # 파서 시험

결과: {"timing": "20262", "basis": "2026년 2학기 (2026. 10. 1.)", "cost": {id: [교육과정 만3,4,5세, 방과후 만3,4,5세]}}
- 값은 '기본경비 소계(월)' = 수업료·간식비·급식비·교재비 (학부모 부담 고지액, 지원금 제외, 월).
  차량비·현장학습비 같은 선택경비와 특성화 활동비는 뺀다(기존 성북구 데이터와 같은 기준).
- 숫자가 없는 칸('-' 등)은 null = 해당 연령반 없음.
"""
import html, json, os, re, sys, time, urllib.parse, urllib.request
from html.parser import HTMLParser

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
OUT = os.path.join(ROOT, 'src', 'data', 'kg_cost_seoul.json')
IDS = os.path.join(ROOT, 'src', 'data', 'kg_ids.json')
URL = 'https://e-childschoolinfo.moe.go.kr/kinderMt/kinderEducateAndCost.do'
MIN_OK = 0.8  # 80% 넘게 받아야 저장


class Tables(HTMLParser):
    """caption이 있는 표마다 [행[칸 텍스트]]를 모은다."""
    def __init__(self):
        super().__init__()
        self.tables, self.cur, self.row, self.cell, self.cap = [], None, None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.cur = {'caption': '', 'rows': []}
        elif self.cur is not None:
            if tag == 'caption':
                self.cap = []
            elif tag == 'tr':
                self.row = []
            elif tag in ('td', 'th') and self.row is not None:
                self.cell = []

    def handle_endtag(self, tag):
        if self.cur is None:
            return
        if tag == 'caption' and self.cap is not None:
            self.cur['caption'] = ' '.join(''.join(self.cap).split())
            self.cap = None
        elif tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.cur['rows'].append(self.row)
            self.row = None
        elif tag == 'table':
            self.tables.append(self.cur)
            self.cur = None

    def handle_data(self, data):
        if self.cap is not None:
            self.cap.append(data)
        elif self.cell is not None:
            self.cell.append(data)


def money(s):
    s = (s or '').replace(',', '').replace('원', '').strip()
    return int(s) if re.fullmatch(r'\d+', s) else None


def base_subtotal(table):
    """'기본경비' 묶음의 첫 '소계(월)' 행 → [만3, 만4, 만5].
    수업료 칸이 '-'인 연령은 반이 없는 것이라 소계가 0으로 찍혀도 null로 둔다."""
    fee = sub = None
    for row in table['rows']:
        if fee is None and '수업료' in row:
            fee = row[row.index('수업료') + 1:][:3]
        if sub is None and row and row[0] == '소계(월)':
            sub = [money(x) for x in row[1:4]]
    if sub is None:
        return None
    return [None if fee and money(f) is None else v for f, v in zip(fee or [None] * 3, sub)]


def parse(text):
    p = Tables()
    p.feed(text)
    edu = aft = None
    for t in p.tables:
        if t['caption'].startswith('교육과정 교육비용'):
            edu = base_subtotal(t)
        elif t['caption'].startswith('방과후 과정 교육비용'):
            aft = base_subtotal(t)
    if edu is None and aft is None:
        return None, None
    m = re.search(r'<option value="(\d{5})"\s+selected', text)
    b = re.search(r'자료기준일\s*:\s*([^<]+)', text)
    timing = m.group(1) if m else None
    basis = ' '.join(html.unescape(b.group(1)).split()) if b else None
    return (edu or [None] * 3) + (aft or [None] * 3), (timing, basis)


def fetch(code):
    data = urllib.parse.urlencode({'ittId': code}).encode()
    for i in range(3):
        try:
            req = urllib.request.Request(URL, data=data, headers={'User-Agent': 'kindergarten-map-updater'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:
            if i == 2:
                raise
            time.sleep(3 * (i + 1))


def main():
    args = sys.argv[1:]
    if args[:1] == ['--parse']:
        print(parse(open(args[1], encoding='utf-8').read()))
        return
    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    ids = json.load(open(IDS, encoding='utf-8'))
    codes = list(ids.items())

    # 한 곳만 먼저 받아 공시 차수 확인 → 바뀌지 않았으면 끝
    _, (timing, basis) = parse(fetch(codes[0][0]))
    if '--force' not in args and timing and timing == old.get('timing'):
        print(f'원비: 공시 {timing} 그대로라 건너뜀')
        return

    cost, fail = {}, 0
    for n, (code, kid) in enumerate(codes, 1):
        try:
            v, _ = parse(fetch(code))
            if v is not None:
                cost[str(kid)] = v
        except Exception as e:
            fail += 1
            print(f'  실패 {code}: {e}', file=sys.stderr)
            if fail > 30 and fail > n * 0.5:
                sys.exit('실패가 너무 많아 멈춥니다.')
        if n % 100 == 0:
            print(f'  {n}/{len(codes)}')
        time.sleep(0.4)

    if len(cost) < len(codes) * MIN_OK:
        sys.exit(f'원비를 {len(cost)}/{len(codes)}곳만 받아 저장하지 않습니다.')
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'timing': timing, 'basis': basis, 'cost': dict(sorted(cost.items(), key=lambda x: int(x[0])))},
                  f, ensure_ascii=False, separators=(',', ':'))
    print(f'원비 완료: {len(cost)}/{len(codes)}곳, 공시 {timing} ({basis})')


if __name__ == '__main__':
    main()

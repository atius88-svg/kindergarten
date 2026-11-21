"""유치원알리미 유치원별 「교육·보육 비용」 화면 → src/data/kg_cost_seoul.json (서울 전체 원비).

원비는 OPEN API·공시자료 다운로드 어디에도 없어서, 유치원알리미 상세 화면 중 비용 탭
(POST /kinderMt/kinderEducateAndCost.do, ittId=유치원코드)을 유치원마다 한 번씩 받아 표에서 숫자를 뽑는다.
로그인·인증키 불필요. 유치원코드는 src/data/kg_ids.json(유치원코드 → id)에서 가져온다.

사용법 (저장소 루트에서):
    python3 scripts/fetch_cost.py                 # 공시 차수가 바뀌었을 때만 서울 전체를 다시 받음(+ 예전에 실패한 곳 다시 받기)
    python3 scripts/fetch_cost.py --minutes 30    # 30분 넘으면 저장하고 멈춤 → 다음 실행이 이어 받음
    python3 scripts/fetch_cost.py --force         # 차수가 같아도 서울 전체를 처음부터 다시 받음
    python3 scripts/fetch_cost.py --parse 파일.html   # 파서 시험

결과: {"timing": "20262", "basis": "2026년 2학기 (2026. 10. 1.)", "cost": {id: [교육과정 만3,4,5세, 방과후 만3,4,5세]},
       "retry": [id, …]}   ← retry는 이번 차수 값을 못 받아 예전 값을 이어 쓰는 곳(없으면 키 없음). 다음 실행 때 다시 받는다.
- 값은 '기본경비 소계(월)' = 수업료·간식비·급식비·교재비 (학부모 부담 고지액, 지원금 제외, 월).
  차량비·현장학습비 같은 선택경비와 특성화 활동비는 뺀다(기존 성북구 데이터와 같은 기준).
- 숫자가 없는 칸('-' 등)은 null = 해당 연령반 없음.
- 공시 차수 확인: 앞에서부터 최대 5곳을 차례로 열어 차수가 보이는 첫 화면을 쓴다(한 곳이 폐원·오류 화면이어도 멈추지 않게).
- 새 차수 수집은 3곳씩 동시에 받고, 진행 중인 값은 src/data/kg_cost_next.json에 모은다(100곳마다 저장).
  사이트는 그동안 예전 차수 값을 그대로 보여 준다. 다 받거나, 시간 안에 다 시도했고 못 받은 곳이 20% 이하면
  kg_cost_seoul.json으로 옮긴다(못 받은 곳은 예전 값 + retry). 시간이 모자라면 다음 실행이 kg_cost_next.json에서 이어 받는다.
- 실패가 많으면(5% 넘고 3곳 넘음, 또는 못 옮김) 오류로 끝나 워크플로 실패 알림이 간다. 파일은 그때까지 받은 만큼 저장된다.
"""
import html, json, os, re, sys, time, urllib.parse, urllib.request
from html.parser import HTMLParser

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
OUT = os.path.join(ROOT, 'src', 'data', 'kg_cost_seoul.json')
NEXT = os.path.join(ROOT, 'src', 'data', 'kg_cost_next.json')  # 새 차수 수집 중일 때만 있음
IDS = os.path.join(ROOT, 'src', 'data', 'kg_ids.json')
URL = 'https://e-childschoolinfo.moe.go.kr/kinderMt/kinderEducateAndCost.do'
MIN_OK = 0.8  # 새 차수 값을 80% 넘게 받아야 사이트용 파일로 옮김
WORKERS = 3


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


def active_ids():
    """kg_seoul.json.txt에서 운영 중(상태 없음)인 유치원 id. kg_ids.json은 휴원·폐원한 곳도 남겨 두므로(다시 열면 같은 id) 수집 대상은 이걸로 거른다."""
    try:
        k = json.loads(open(os.path.join(ROOT, 'src', 'data', 'kg_seoul.json.txt'), encoding='utf-8').read())
        i, st = k['cols'].index('id'), k['cols'].index('상태') if '상태' in k['cols'] else None
        return {str(r[i]) for r in k['rows'] if st is None or not r[st]}
    except Exception as e:
        print(f'  운영 중 목록을 못 읽어 kg_ids.json 전체를 씀: {e}', file=sys.stderr)
        return None


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
        except Exception:
            if i == 2:
                raise
            time.sleep(3 * (i + 1))


def probe(codes, n=5):
    """앞에서부터 최대 n곳을 열어 공시 차수·기준일을 찾는다. 못 찾으면 (None, None)."""
    for code, kid in codes[:n]:
        try:
            v, meta = parse(fetch(code))
        except Exception as e:
            print(f'  차수 확인 실패 {kid}: {e}', file=sys.stderr)
            continue
        if meta and meta[0]:
            return meta
        print(f'  차수 확인: {kid} 화면에 비용 표·차수가 없음, 다음 곳으로', file=sys.stderr)
    return None, None


def collect(todo, code_of, deadline, on_progress=None):
    """todo(id 목록)를 WORKERS곳씩 동시에 받는다 → (ok {id: 값}, none {표 없는 id}, fail {id}, left {시간 넘어 못 한 id}).
    실패한 곳은 끝에 한 번 더 시도한다."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    ok, none, fail, left = {}, set(), set(), []

    def one(kid):
        v, _ = parse(fetch(code_of[kid]))
        time.sleep(0.2)
        return v

    def run(ids):
        bad = []
        with ThreadPoolExecutor(WORKERS) as ex:
            it, futs = iter(ids), {}

            def submit():
                for kid in it:
                    if deadline and time.time() > deadline:
                        left.append(kid)
                        continue
                    futs[ex.submit(one, kid)] = kid
                    return
            for _ in range(WORKERS):
                submit()
            while futs:
                f = next(as_completed(futs))
                kid = futs.pop(f)
                try:
                    v = f.result()
                    (none.add(kid) if v is None else ok.__setitem__(kid, v))
                except Exception as e:
                    bad.append(kid)
                    if len(bad) <= 10:
                        print(f'  실패 {kid} {code_of[kid]}: {e}', file=sys.stderr)
                n = len(ok) + len(none) + len(bad)
                if n % 100 == 0:
                    print(f'  {n}/{len(ids)}')
                    if on_progress:
                        on_progress(ok, none)
                submit()
        return bad

    bad = run(todo)
    if bad and not left:
        print(f'  실패한 {len(bad)}곳 다시 시도')
        bad = run(bad)
    fail.update(bad)
    return ok, none, fail, left


def write(path, d):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, separators=(',', ':'))


def bykey(cost):
    return dict(sorted(cost.items(), key=lambda x: int(x[0])))


def main():
    args = sys.argv[1:]
    if args[:1] == ['--parse']:
        print(parse(open(args[1], encoding='utf-8').read()))
        return
    minutes = float(args[args.index('--minutes') + 1]) if '--minutes' in args else 0
    deadline = time.time() + minutes * 60 if minutes else None
    force = '--force' in args
    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    old.setdefault('cost', {})
    codes = [(code, str(kid)) for code, kid in json.load(open(IDS, encoding='utf-8')).items()]
    act = active_ids()
    if act:
        codes = [(c, k) for c, k in codes if k in act]  # 휴원·폐원한 곳은 받지 않음
    code_of = {kid: code for code, kid in codes}
    every = sorted(code_of, key=int)

    timing, basis = probe(codes)
    if not timing:
        sys.exit('원비: 앞 5곳 화면에서 공시 차수를 찾지 못했습니다(사이트 변경·접속 차단?). 예전 값을 그대로 둡니다.')

    nxt = json.load(open(NEXT, encoding='utf-8')) if os.path.exists(NEXT) else None
    if nxt and nxt.get('timing') != timing:
        print(f'원비: 수집 중이던 차수 {nxt.get("timing")}가 아니라 {timing}가 최신이라 새로 시작')
        nxt = None
    if force or (timing != old.get('timing') and not nxt):
        nxt = {'timing': timing, 'basis': basis, 'cost': {}, 'todo': every}

    if nxt:  # 새 차수 수집(또는 이어 받기)
        todo = [k for k in nxt['todo'] if k in code_of]
        print(f'원비: 공시 {timing} ({basis}) — {len(todo)}곳 받을 차례(전체 {len(every)}곳, 기존 차수 {old.get("timing")})')

        def save_next(ok, none):
            done = set(ok) | none
            write(NEXT, {**nxt, 'cost': bykey({**nxt['cost'], **ok}), 'todo': [k for k in todo if k not in done]})
        ok, none, fail, left = collect(todo, code_of, deadline, save_next)
        nxt['cost'] = bykey({**nxt['cost'], **ok})
        for k in none:
            nxt['cost'].pop(k, None)
        nxt['todo'] = sorted(fail | set(left), key=int)
        rest = nxt['todo']
        if not rest or (not left and len(rest) <= len(every) * (1 - MIN_OK)):
            carry = {k: old['cost'][k] for k in rest if k in old['cost']}
            live = {'timing': timing, 'basis': basis, 'cost': bykey({**nxt['cost'], **carry})}
            if rest:
                live['retry'] = rest
            write(OUT, live)
            if os.path.exists(NEXT):
                os.remove(NEXT)
            print(f'원비 완료: 공시 {timing}, {len(live["cost"])}곳' + (f' (못 받은 {len(rest)}곳은 예전 값, 다음 실행 때 다시 받음)' if rest else ''))
        else:
            write(NEXT, nxt)
            why = f'시간이 모자라 {len(left)}곳은 다음 실행에서 이어 받음' if left else f'못 받은 곳이 {len(rest)}곳(20% 넘음)'
            print(f'원비: {len(every) - len(rest)}/{len(every)}곳 받음. {why}. 사이트 값은 예전 차수 그대로(진행분은 kg_cost_next.json).')
            if not left:
                sys.exit('원비: 실패가 너무 많아 새 차수로 바꾸지 않았습니다(접속 차단?).')
    else:  # 차수 그대로: 예전에 못 받은 곳·원비가 없는 곳만 다시
        todo = sorted(set(old.get('retry', [])) | {k for k in every if k not in old['cost']}, key=int)
        todo = [k for k in todo if k in code_of]
        if not todo:
            print(f'원비: 공시 {timing} 그대로라 건너뜀')
            return
        print(f'원비: 공시 {timing} 그대로, 예전에 못 받은 곳·원비 없는 곳 {len(todo)}곳 다시 받기')
        ok, none, fail, left = collect(todo, code_of, deadline)
        old['cost'].update(ok)
        for k in none:
            old['cost'].pop(k, None)
        rest = sorted((set(old.get('retry', [])) - set(ok) - none) & set(code_of), key=int)
        live = {'timing': old['timing'], 'basis': old.get('basis'), 'cost': bykey(old['cost'])}
        if rest:
            live['retry'] = rest
        write(OUT, live)
        print(f'원비: 다시 받기 성공 {len(ok)}, 표 없음 {len(none)}, 실패 {len(fail)}, 시간 넘음 {len(left)}')
    if len(fail) > max(3, (len(ok) + len(none) + len(fail)) * 0.05):
        sys.exit(f'원비: {len(fail)}곳 실패(5% 넘음).')


if __name__ == '__main__':
    main()

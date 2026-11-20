"""어린이집정보공개포털 어린이집별 화면 → src/data/dc_portal.json (API에 없는 운영시간·평가·연장보육).

어린이집마다 화면 3~4개(키 불필요):
  요약   /info_html5/pnis/search/preview/SummaryInfoSlPu.jsp?flag=YJ&STCODE_POP={stcode}   → 운영시간(평일기준시간)
  평가   .../AppraisaAuthenticationGradeSlPu.jsp?flag=PI&STCODE_POP={stcode}             → 평가 상태·평가년월, 결과서 id
  총평   /info_html5/cera/search/totalGradeComment.jsp?flag=commnetGrade&childHouseId={id} → '모든 영역 충족'=A, '대부분'=B
         (goTotalComment 넷째 인자가 '01'이면 totalGradeCommentEvl2nd.jsp ... &evlIdxTy=01)
  연장   .../EtntctClassAdditionSlPu.jsp?flag=EN&STCODE_POP={stcode}                     → 연장보육반 수·이용 아동 합

사용법 (저장소 루트에서):
    python3 scripts/fetch_dc_portal.py                 # dc_seoul.json의 어린이집 중 받은 지 90일 넘은 곳·없는 곳
    python3 scripts/fetch_dc_portal.py --days 0        # 전부 다시
    python3 scripts/fetch_dc_portal.py --limit 20      # 앞에서 20곳만(시험)
    python3 scripts/fetch_dc_portal.py --minutes 50    # 이 시간이 지나면 저장하고 멈춤(다음 실행이 이어서 받음)
    python3 scripts/fetch_dc_portal.py --parse 요약.html 평가.html 총평.html 연장.html   # 파서 시험
"""
import concurrent.futures as cf, datetime, html, json, os, re, sys, time, urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DC = os.path.join(ROOT, 'src', 'data', 'dc_seoul.json')
OUT = os.path.join(ROOT, 'src', 'data', 'dc_portal.json')
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


def cell(page, label):  # <th>label</th> <td>값</td>
    m = re.search(r'<th[^>]*>\s*' + re.escape(label) + r'\s*</th>\s*<td[^>]*>(.*?)</td>', page, re.S)
    return text(m.group(1)) if m else None


def parse_summary(page):
    m = re.search(r'평일기준시간\s*:\s*(\d{1,2}:\d{2})\s*~\s*(\d{1,2}:\d{2})', page)
    return {'운영시간': f'{m.group(1).zfill(5)}~{m.group(2).zfill(5)}'} if m else {'운영시간': None}


def parse_eval(page):
    st = cell(page, '평가 상태') or ''
    ym = (cell(page, '평가년월') or '').replace('.', '-')
    m = re.search(r"goTotalComment\('([^']*)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'\)", page)
    link = None
    if m:
        v, s, c, e = m.groups()
        if not (s in ('3', '4', '5', '9') or c == 'Y'):
            link = (f'{HOST}/info_html5/cera/search/totalGradeCommentEvl2nd.jsp?flag=commnetGrade&childHouseId={v}&evlIdxTy={e}'
                    if e == '01' else f'{HOST}/info_html5/cera/search/totalGradeComment.jsp?flag=commnetGrade&childHouseId={v}')
    done = 1 if '평가완료' in st else 0
    return {'평가완료': done, '평가연월': ym if re.match(r'\d{4}-\d{2}$', ym) else None, '_상태': st or None}, link


def parse_comment(page):
    t = text(page)
    i = t.rfind('총평')
    t = t[i:] if i >= 0 else t
    if '모든 영역' in t and '충족' in t:
        return 'A'
    if '대부분' in t or '일부' in t or '보완' in t:
        return 'B'
    return None


def parse_ext(page):
    m = re.search(r'이용아동수.*?<tbody>(.*?)</tbody>', page, re.S)
    if not m:
        return {'연장반': 0, '연장아동': 0}
    n = kids = 0
    for row in re.findall(r'<tr>(.*?)</tr>', m.group(1), re.S):
        tds = [text(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
        if len(tds) >= 4 and tds[3].isdigit():
            n += 1
            kids += int(tds[3])
    return {'연장반': n, '연장아동': kids}


def one(stcode):
    q = f'&STCODE_POP={stcode}'
    r = parse_summary(get(PRE + 'SummaryInfoSlPu.jsp?flag=YJ' + q))
    ev, link = parse_eval(get(PRE + 'AppraisaAuthenticationGradeSlPu.jsp?flag=PI' + q))
    r.update(ev)
    r['평가'] = parse_comment(get(link)) if link and ev['평가완료'] else None
    r.update(parse_ext(get(PRE + 'EtntctClassAdditionSlPu.jsp?flag=EN' + q)))
    r['t'] = datetime.date.today().isoformat()
    return r


def main():
    a = sys.argv[1:]
    if a[:1] == ['--parse']:
        s, e, c, x = (open(p, encoding='utf-8').read() for p in a[1:5])
        r = parse_summary(s)
        ev, link = parse_eval(e)
        r.update(ev, 평가=parse_comment(c), 결과서=link)
        r.update(parse_ext(x))
        print(json.dumps(r, ensure_ascii=False))
        return
    opt = lambda k, d: int(a[a.index(k) + 1]) if k in a else d
    days, limit, minutes, workers = opt('--days', 90), opt('--limit', 0), opt('--minutes', 0), opt('--workers', 4)
    dc = json.load(open(DC, encoding='utf-8'))
    ids = [r[0][1:] for r in dc['rows'] if str(r[0]).startswith('c') and r[0][1:].isdigit()]
    old = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    cut = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    todo = [s for s in ids if s not in old or old[s].get('t', '') <= cut or days == 0]
    todo.sort(key=lambda s: old.get(s, {}).get('t', ''))  # 오래된 것부터
    if limit:
        todo = todo[:limit]
    print(f'포털 수집: {len(todo)}곳 (전체 {len(ids)}곳, 기존 {len(old)}곳)')
    t0, ok, fail = time.time(), 0, 0

    def save():
        keep = {k: v for k, v in old.items() if k in set(ids)}
        json.dump(keep, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, sort_keys=True, separators=(',', ':'))

    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {}
        it = iter(todo)
        stop = False
        def submit():
            s = next(it, None)
            if s:
                futs[ex.submit(one, s)] = s
        for _ in range(workers * 2):
            submit()
        while futs:
            done, _ = cf.wait(futs, return_when=cf.FIRST_COMPLETED)
            for f in done:
                s = futs.pop(f)
                try:
                    old[s] = f.result(); ok += 1
                except Exception as e:
                    fail += 1
                    if fail <= 5:
                        print('  실패', s, e, file=sys.stderr)
                if minutes and time.time() - t0 > minutes * 60:
                    stop = True
                if not stop:
                    submit()
            if (ok + fail) % 200 == 0:
                print(f'  {ok + fail}곳 ({time.time() - t0:.0f}초)')
                save()
    save()
    print(f'완료 {ok}곳, 실패 {fail}곳, {time.time() - t0:.0f}초')
    if ok == 0 and todo:
        sys.exit('하나도 못 받았습니다(접속 차단?)')


if __name__ == '__main__':
    main()

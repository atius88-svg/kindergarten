# 어린이집 기관별 정적 페이지(검색엔진용): python3 scripts/build_dc_pages.py  (저장소 루트, src/build.py 다음에 실행)
# dc.json(화면과 같은 데이터: 평가보완·특색·평가4 포함)·dc_tips.json(보완 권고 문장)으로 d/{id}.html 을 만들고,
# build_pages.py가 쓴 sitemap.xml 에 d/ 주소를 덧붙인다(유치원 k/ 주소는 그대로 둠).
# 명단에서 빠진 곳의 옛 d/{id}.html은 지운다. 한 번에 많이 지워야 하면(데이터 이상일 수 있음) 지우지 않고 알리며,
# 일부러 줄인 거면 --prune 을 붙여 실행한다.
import collections, datetime, hashlib, html, json, math, os, re, statistics, sys, traceback, urllib.parse

NOINDEX = False
SITE = 'https://kindermap.kr/'
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DIR = os.path.join(root, 'd')
KAKAO_KEY = '0688a80cbe72ae0757d555b93dc48ab9'  # 사이트 지도와 같은 JS 키(등록 도메인에서만 동작)
OG_V = hashlib.md5(open(os.path.join(root, 'og-dc.png'), 'rb').read()).hexdigest()[:8]

D = json.load(open(os.path.join(root, 'dc.json'), encoding='utf-8'))
ROWS = [dict(zip(D['cols'], r)) for r in D['rows']]
FIX = {i for i, _ in D.get('fix', [])}  # 좌표가 틀려 화면에서 주소로 다시 찾는 곳 → 정적 지도는 안 그림
TIPS = json.load(open(os.path.join(root, 'dc_tips.json'), encoding='utf-8'))
e = html.escape

AGE = ['만 0세', '만 1세', '만 2세', '만 3세', '만 4세', '만 5세', '영아 혼합(0~2세)', '영유아 혼합(2~3세)', '유아 혼합(3~5세)', '장애아반']
AGE_MAX = [3, 5, 7, 15, 20, 20, None, None, None, 3]  # 영유아보육법 시행규칙 별표2 보육교사 1인당 아동 수
WAIT_LAB = ['만 0세', '만 1세', '만 2세', '만 3세', '만 4세', '만 5세', '6세 이상']
SPEC = {'야간연장형': '밤늦게까지 맡아주는 야간연장형', '24시간': '24시간 보육', '시간제보육': '시간제 보육', '장애아통합': '장애아 통합 보육', '영아전담': '영아 전담'}


def seoul(r):  # 화면 문구가 '서울 평균'이라 서울만(경기 id는 c41…·북부 c40…)
    return r['id'].startswith(('c11', 'cx'))


def gg(r):
    return (r.get('주소') or '').startswith('경기')


SEO = [r for r in ROWS if seoul(r)]
TCH_AVG = {t: statistics.mean(v) for t in {r['유형'] for r in SEO}
           if (v := [r['교사1인당원아'] for r in SEO if r['유형'] == t and r['교사1인당원아'] is not None])}
_w = sorted(r['대기'][7] for r in SEO if r['대기'])
WAIT_MED = _w[len(_w) // 2] if _w else None

# 가까운 어린이집: 0.01도(약 1km) 칸으로 나눠 이웃 칸만 본다
GRID = collections.defaultdict(list)
for o in ROWS:
    if o['위도'] and o['경도'] and o['id'] not in FIX:
        GRID[(int(o['위도'] * 100), int(o['경도'] * 100))].append(o)


def dist_m(a, b):
    p = math.pi / 180
    h = math.sin((b['위도'] - a['위도']) * p / 2) ** 2 + math.cos(a['위도'] * p) * math.cos(b['위도'] * p) * math.sin((b['경도'] - a['경도']) * p / 2) ** 2
    return 12742000 * math.asin(math.sqrt(h))


def nearby(r, km=1.0, n=5):
    if not (r['위도'] and r['경도']) or r['id'] in FIX:
        return []
    y, x = int(r['위도'] * 100), int(r['경도'] * 100)
    v = [(dist_m(r, o), o) for dy in (-1, 0, 1) for dx in (-1, 0, 1) for o in GRID[(y + dy, x + dx)] if o['id'] != r['id']]
    return sorted(((d, o) for d, o in v if d <= km * 1000), key=lambda t: (t[0], t[1]['id']))[:n]


def kind(r):
    return {'국공립': '국공립', '민간': '민간', '가정': '가정'}.get(r['유형'], r['설립유형'] or '직장·법인')


def eval_txt(r):
    """(한 줄 요약, 표 행들) — 화면 dcEval과 같은 기준"""
    if r['평가완료'] is None:
        return None, []
    if not r['평가완료']:
        return '아직 평가를 받지 않았어요.', [('평가', '아직 받지 않음 (새로 문을 연 곳일 수 있어요)')]
    ym = r['평가연월'] or ''
    old = r['평가'] in ('A', 'B') or (ym or '9999') < '2024-07'
    if r['평가'] == 'A':
        return f'{ym} 평가에서 모든 영역을 충족했어요(개편 전 평가).', [('평가', f'{ym} 완료 · 총평 “모든 영역 충족” (2024년 7월 개편 전 평가)')]
    if r['평가'] == 'B':
        return f'{ym} 평가에서 대부분 영역을 충족했어요(개편 전 평가).', [('평가', f'{ym} 완료 · 총평 “대부분 충족”, 일부 보완할 점 (2024년 7월 개편 전 평가)')]
    if old:
        return f'{ym}에 평가를 받았어요(개편 전 평가).', [('평가', f'{ym} 완료 (2024년 7월 개편 전 평가)')]
    n = r.get('평가보완')
    if n == 0:
        return f'{ym} 평가에서 보완 권고가 없었어요.', [('평가', f'{ym} 완료 · 보완 권고 없음')]
    if n:
        return f'{ym} 평가에서 보완 권고가 {n}건 있었어요.', [('평가', f'{ym} 완료 · 보완 권고 {n}건')]
    return f'{ym}에 평가를 받았어요.', [('평가', f'{ym} 완료')]


def page(r):
    name, gu, k = r['유치원명'], r['구'], kind(r)
    lead = [f'{gu}에 있는 {k} 어린이집이에요.']
    if r['정원']:
        lead.append(f'정원 {r["정원"]}명 중 {r["원아수"]}명이 다녀요.')
    if r['대기']:
        lead.append(f'입소를 기다리는 아이가 {r["대기"][7]}명이에요.' if r['대기'][7] else '지금 입소를 기다리는 아이가 없어요.')
    ev1, evrows = eval_txt(r)
    if ev1:
        lead.append(ev1)
    if r['연장반']:
        lead.append(f'저녁 7시 반 이후 연장보육반 {r["연장반"]}개를 운영해요.')

    # 나이별 반·대기
    ages = []
    if r['연령별']:
        for i, (n, kids) in enumerate(r['연령별']):
            if not (n or kids):
                continue
            per = kids / n if n else None
            mx = AGE_MAX[i]
            w = f'{r["대기"][i]}명' if r['대기'] and i < 6 else '-'
            ages.append(f'<tr><th>{AGE[i]}</th><td>{n}개</td><td>{kids}명</td><td>{"-" if per is None else f"{round(per, 1):g}명"}</td><td>{f"{mx}명" if mx else "-"}</td><td>{w}</td></tr>')
    wait_by = ''
    if r['대기'] and r['대기'][7]:
        b = [f'{WAIT_LAB[i]} {v}명' for i, v in enumerate(r['대기'][:7]) if v]
        wait_by = ' · '.join(b)

    # 평가
    evs = [f'<tr><th>{a}</th><td>{e(b)}</td></tr>' for a, b in evrows]
    tips = TIPS.get(r['id']) or []
    tip_html = ''.join(f'<li><b>{e(a)}</b> — {e(b)}</li>' for a, b in tips)
    qa = []
    if r.get('평가4'):
        freq, kinds, meal, parent, dev = r['평가4']
        none = '결과서에 언급 없음'
        out = none if freq == '없음' else ' · '.join(([freq] if freq in ('매주', '매월', '정기적') else []) + list(kinds)) or '있음'
        for q, a in (('바깥 활동', out), ('급식', ' · '.join(meal) or none), ('부모 참여', ' · '.join(parent) or none), ('발달 전문기관 지원', ' · '.join(dev) or none)):
            qa.append(f'<tr><th>{q}</th><td>{e(a)}</td></tr>')
    elif r.get('특색'):
        qa.append(f'<tr><th>특색 활동</th><td>{e(" · ".join(r["특색"]))}</td></tr>')

    # 선생님·운영
    info = []
    if r['운영시간']:
        info.append(f'<tr><th>운영 시간</th><td>{e(r["운영시간"])}</td></tr>')
    if r['연장반'] is not None:
        ext = f'{r["연장반"]}개 반 · {r["연장아동"]}명 이용' if r['연장반'] else '운영 안 함'
        info.append(f'<tr><th>연장보육(19:30 이후)</th><td>{ext}</td></tr>')
    sp = [SPEC[s] for s in (r['특성'] or '').split('|') if s in SPEC]
    if sp:
        info.append(f'<tr><th>특성</th><td>{e(" · ".join(sp))}</td></tr>')
    if r['교사1인당원아'] is not None:
        a = TCH_AVG.get(r['유형'])
        info.append(f'<tr><th>선생님 한 명당 아이</th><td>{r["교사1인당원아"]:g}명' + (f' (서울 {r["유형"]} 평균 {a:.1f}명)' if a else '') + '</td></tr>')
    if r['4년이상비율'] is not None:
        info.append(f'<tr><th>4년 넘게 근무한 선생님</th><td>{round(r["4년이상비율"])}%</td></tr>')
    if r['차량운영여부'] in ('운영', '미운영'):
        info.append(f'<tr><th>통학 차량</th><td>{"운영" if r["차량운영여부"] == "운영" else "운영 안 함"}</td></tr>')
    if r['CCTV'] is not None:
        info.append(f'<tr><th>CCTV</th><td>{r["CCTV"]}대</td></tr>')
    if r['보육실']:
        info.append(f'<tr><th>보육실</th><td>{r["보육실"]}개' + (f' · 놀이터 {r["놀이터"]}개' if r['놀이터'] else '') + '</td></tr>')

    # 가까운 어린이집
    near = nearby(r)
    nrows = []
    if near:
        wv = lambda o: '-' if not o['대기'] else f'{o["대기"][7]}명'
        nrows.append(f'<tr><th>{e(name)} (이 어린이집)</th><td>-</td><td>{e(kind(r))}</td><td>{r["원아수"]}/{r["정원"]}명</td><td><b>{wv(r)}</b></td></tr>')
        for d, o in near:
            nrows.append(f'<tr><th><a href="{o["id"]}.html">{e(o["유치원명"])}</a></th><td>{round(d / 10) * 10}m</td><td>{e(kind(o))}</td><td>{o["원아수"]}/{o["정원"]}명</td><td>{wv(o)}</td></tr>')

    # 위치·연락처
    addr, tel = r['주소'] or '', r['전화'] or ''
    place = ''
    if addr or tel:
        q = urllib.parse.quote(f'{name},{r["위도"]},{r["경도"]}') if r['id'] not in FIX else urllib.parse.quote(addr)
        link = (f'<a href="https://map.kakao.com/link/map/{q}">카카오맵에서 보기</a> · <a href="https://map.kakao.com/link/to/{q}">길찾기</a>'
                if r['id'] not in FIX else f'<a href="https://map.kakao.com/?q={q}">카카오맵에서 주소 찾기</a>')
        contact = ([f'<tr><th>주소</th><td>{e(addr)}</td></tr>'] if addr else []) + ([f'<tr><th>전화</th><td><a href="tel:{e(tel)}">{e(tel)}</a></td></tr>'] if tel else [])
        smap = ('' if r['id'] in FIX or not r['위도'] else
                f'<div id="map" style="height:200px;border-radius:12px;background:#e6ece8"></div>\n'
                f'<script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_KEY}&autoload=false"></script>\n'
                f'<script>kakao.maps.load(function(){{var p=new kakao.maps.LatLng({r["위도"]},{r["경도"]});new kakao.maps.StaticMap(document.getElementById("map"),{{center:p,level:3,marker:{{position:p}}}})}})</script>\n')
        place = f'{smap}<p>{link}</p>\n<table>{"".join(contact)}</table>'

    title = f'{name} 입소 대기·평가·정원 | {gu} 어린이집 | 킨더맵'
    desc = ' '.join(lead)[:150]
    ld = {'@context': 'https://schema.org', '@type': 'ChildCare', 'name': name,
          'address': {'@type': 'PostalAddress', 'addressRegion': '경기도' if gg(r) else '서울특별시', 'addressLocality': gu, 'addressCountry': 'KR'}}
    if r['위도'] and r['id'] not in FIX:
        ld['geo'] = {'@type': 'GeoCoordinates', 'latitude': r['위도'], 'longitude': r['경도']}
    if addr:
        ld['address']['streetAddress'] = addr
    if tel:
        ld['telephone'] = tel
    robots = '<meta name="robots" content="noindex,nofollow">\n' if NOINDEX else ''
    sec = lambda h, body: f'<h2>{h}</h2>\n{body}\n' if body else ''
    tbl = lambda head, rows: f'<table class="h"><tr>{"".join(f"<th>{x}</th>" for x in head)}</tr>{"".join(rows)}</table>' if rows else ''
    evsec = ''
    if evs or qa or tip_html:
        evsec = (f'<table>{"".join(evs)}</table>' +
                 (f'<p><small>평가결과서의 보완 권고</small></p><ul>{tip_html}</ul>' if tip_html else '') +
                 (f'<h3>평가로 본 생활</h3><table>{"".join(qa)}</table><small>어린이집 평가결과서를 AI(Claude)로 정리했어요. 결과서에 적힌 것만 담았어요.</small>' if qa else ''))
    wait_note = ''
    if r['대기']:
        wait_note = (f'<p>입소 대기 <b>{r["대기"][7]}명</b>' + (f' ({e(wait_by)})' if wait_by else '') + '</p>' if r['대기'][7] else '<p>지금 입소 대기 <b>없음</b></p>')
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{robots}<link rel="canonical" href="{SITE}d/{r["id"]}.html">
<meta property="og:type" content="website">
<meta property="og:site_name" content="킨더맵">
<meta property="og:title" content="{e(name)} · {e(gu)} 어린이집 입소 대기·평가">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{SITE}d/{r["id"]}.html">
<meta property="og:image" content="{SITE}og-dc.png?v={OG_V}">
<link rel="icon" href="../favicon.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="../apple-touch-icon.png">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<!-- 방문 통계: Google 애널리틱스 4 (킨더맵 웹 스트림) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-Q93M007YBJ"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag('js',new Date());gtag('config','G-Q93M007YBJ');</script>
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
<style>
body{{margin:0;font:16px/1.6 system-ui,-apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;color:#1b2a25;background:#f6f8f6}}
main{{max-width:640px;margin:0 auto;padding:16px}}
h1{{font-size:22px;margin:8px 0}}h2{{font-size:17px;margin:24px 0 8px}}h3{{font-size:15px;margin:16px 0 6px}}
.lead{{background:#fff;border-radius:12px;padding:14px 16px}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;font-size:14px}}
th,td{{padding:8px 10px;border-bottom:1px solid #e6ece8;text-align:left}}
td{{white-space:nowrap}}td:last-child{{white-space:normal}}table.h tr:first-child th{{white-space:nowrap;font-size:13px;color:#5b6b64}}th,td{{padding:8px 6px}}
ul{{background:#fff;border-radius:12px;padding:10px 16px 10px 32px;font-size:14px;margin:0}}li{{margin:4px 0}}
.cta{{display:block;text-align:center;margin:20px 0;padding:14px;border-radius:12px;background:#1f3a32;color:#ffc94a;font-weight:700;text-decoration:none}}
small{{color:#5b6b64}}a{{color:#1f6f54}}
</style></head><body><main>
<small><a href="../dc/">킨더맵</a> › {e(gu)} › 어린이집</small>
<h1>{e(name)}</h1>
{f'<small>{e(addr)}</small>' if addr else ''}
<p class="lead">{e(" ".join(lead))}</p>
<a class="cta" href="../#k{r["id"]}">지도에서 주변 어린이집과 비교하기</a>
{sec("나이별 반·입소 대기", wait_note + tbl(["", "반", "아이", "한 반", "법정 최대", "대기"], ages) + "<small>반 수와 지금 다니는 아이 수예요(나이별 정원은 공개되지 않아요). 법정 최대는 보육교사 1명이 맡을 수 있는 아이 수로, 한 반이 이에 가까우면 그 나이 자리는 거의 찼다는 뜻이에요. 입소 대기는 신청 아동 수로 여러 곳에 중복 신청한 아이가 포함돼요. 내 순번은 아이사랑(childcare.go.kr)에서 확인하세요.</small>" if ages or wait_note else "")}
{sec("평가", evsec)}
{sec("선생님·운영", f'<table>{"".join(info)}</table>' if info else '')}
{sec("가까운 어린이집과 비교 (반경 1km)", tbl(["", "거리", "유형", "현원/정원", "입소 대기"], nrows) + "<small>이 어린이집에서 가까운 순이에요.</small>" if nrows else "")}
{sec("위치·연락처", place)}
<p><small>출처: 어린이집정보공개포털(보육통합정보시스템) OPEN API·기관별 공개 화면·평가결과서. 정확한 내용은 어린이집에 직접 확인하세요.</small></p>
<p><small>정보가 다르거나 바뀐 게 있으면 <a href="mailto:kindermap2026@gmail.com?subject={urllib.parse.quote("[정정 요청] " + name)}">kindermap2026@gmail.com</a>으로 알려 주세요. 어린이집 관계자의 정정 요청도 받아요.</small></p>
</main></body></html>
'''


def main():
    sel = [r for r in ROWS if r['id']]
    os.makedirs(DIR, exist_ok=True)
    fail = []
    for r in sel:
        try:
            out = page(r)
        except Exception:
            fail.append(r['id'])
            print(f'  페이지 오류 {r["id"]} {r["유치원명"]} (예전 파일 유지):', file=sys.stderr)
            traceback.print_exc(limit=2)
            continue
        open(os.path.join(DIR, f'{r["id"]}.html'), 'w', encoding='utf-8').write(out)
    print(len(sel) - len(fail), 'pages -> d/', f'(오류 {len(fail)}곳: {fail[:10]})' if fail else '')
    keep = {f'{r["id"]}.html' for r in sel}
    stale = sorted(f for f in os.listdir(DIR) if f.endswith('.html') and f not in keep)
    if stale and (len(stale) <= max(10, len(sel) * 0.2) or '--prune' in sys.argv) and sel:
        for f in stale:
            os.remove(os.path.join(DIR, f))
        print(f'명단에서 빠진 옛 페이지 {len(stale)}개 지움: {stale[:10]}')
    elif stale:
        print(f'명단에서 빠진 옛 페이지가 {len(stale)}개라 지우지 않음(데이터 이상일 수 있음). 일부러 줄였으면 --prune', file=sys.stderr)
        fail.append('stale')
    # sitemap.xml: build_pages.py가 쓴 것(첫 화면·k/)에서 d/ 줄만 바꿔 넣음. 5만 주소 한도 안(지금 약 1만 4천)
    sm = os.path.join(root, 'sitemap.xml')
    if not NOINDEX and os.path.exists(sm):
        today = datetime.date.today().isoformat()
        lines = [l for l in open(sm, encoding='utf-8').read().splitlines() if '<url>' in l and f'{SITE}d/' not in l]
        have = set(os.listdir(DIR))
        lines += [f'<url><loc>{SITE}d/{r["id"]}.html</loc><lastmod>{today}</lastmod></url>' for r in sel if f'{r["id"]}.html' in have]
        with open(sm, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + '\n'.join(lines) + '\n</urlset>\n')
        print('sitemap.xml', len(lines), '주소')
    if fail:
        sys.exit(1)


main()

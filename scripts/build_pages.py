# 기관별 정적 상세 페이지(SEO 시험): python3 scripts/build_pages.py  (저장소 루트에서 실행)
# 서울 운영 중 유치원 전부 k/{id}.html 로 만들고 검색을 허용한다 + 저장소 루트에 sitemap.xml.
# 다시 시험 단계로 돌리려면 NOINDEX=True(이때 sitemap.xml은 지움), GU='성북구', LIMIT=30.
# 대상에서 빠진 곳(폐원·휴원 등)의 옛 k/{id}.html은 지운다. 한 번에 많이 지워야 하면(데이터 이상일 수 있음) 지우지 않고 알리며,
# 일부러 줄인 거면 --prune 을 붙여 실행한다.
import datetime, html, json, math, os, re, statistics, sys, traceback, urllib.parse

NOINDEX, GU, LIMIT = False, None, None  # 2026-11-25 서울 운영 중 유치원 전부 공개(검색 허용)
SITE = 'https://kindermap.kr/'
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
L = lambda p: json.load(open(os.path.join(root, 'src/data', p), encoding='utf-8'))

kg = L('kg_seoul.json.txt')
ROWS = [dict(zip(kg['cols'], r)) for r in kg['rows']]
COSTD = L('kg_cost_seoul.json'); COST = COSTD['cost']
RC = L('kg_rcrt.json'); RCR = RC['r']
BASIS = COSTD['basis'].split('(')[0].strip()
DET = L('kg_detail.json')  # 주소·전화·홈페이지·통학차량 대수·CCTV 수 (scripts/fetch_detail.py가 매달 수집). 값이 빠질 수 있어 .get으로 읽는다
KAKAO_KEY = '0688a80cbe72ae0757d555b93dc48ab9'  # 사이트 지도와 같은 JS 키(등록 도메인에서만 동작)
GEN = set()  # 이번에 만드는 페이지 id
import hashlib
OG_V = hashlib.md5(open(os.path.join(root, 'og.png'), 'rb').read()).hexdigest()[:8]  # 카톡이 이미지를 주소로 캐시 → og.png가 바뀌면 주소도 바뀌게


def dist_m(a, b):
    p = math.pi / 180
    h = math.sin((b['위도'] - a['위도']) * p / 2) ** 2 + math.cos(a['위도'] * p) * math.cos(b['위도'] * p) * math.sin((b['경도'] - a['경도']) * p / 2) ** 2
    return 12742000 * math.asin(math.sqrt(h))


def cost5(i):
    c = COST.get(str(i))
    return None if not c or c[2] is None else c[2] + (c[5] or 0)


def nearby(r, km=1.0, n=5):
    v = [(dist_m(r, o), o) for o in ROWS if o['id'] != r['id'] and o['상태'] is None and o['위도'] and o['경도']]
    return sorted(((d, o) for d, o in v if d <= km * 1000), key=lambda x: (x[0], x[1]['id']))[:n]  # 같은 좌표(같은 건물)면 id순
AGE = ['만 3세', '만 4세', '만 5세', '혼합반', '특수반']
e = html.escape


def won(n):
    return f'{round(n / 1000) / 10:g}만원' if n >= 10000 else f'{n:,}원'


def gg(r):  # 경기 유치원(fetch_kg.py '시도' 41)
    return r.get('시도') == 41


def full_addr(addr):  # kg_detail 주소: 서울은 '서울특별시'를 뗀 '성북구 …', 경기는 '경기도 …'
    return addr if addr.startswith('경기') else f'서울 {addr}'


def cost_avg(typ, gu, a):
    v = [COST[str(r['id'])][a] + (COST[str(r['id'])][a + 3] or 0) for r in ROWS
         if r['구'] == gu and r['유형'] == typ and r['상태'] is None and COST.get(str(r['id'])) and COST[str(r['id'])][a] is not None]
    return statistics.mean(v) if v else None


def avg(typ, k):
    v = [r[k] for r in ROWS if r['유형'] == typ and r[k] is not None and r['상태'] is None and not gg(r) and not (k == '교사1인당원아' and r['데이터주의'])]  # 문구가 '서울 평균'이라 서울만
    return statistics.mean(v) if v else None


def next_rows(r):
    q = RCR.get(str(r['id']))
    if not q or q[3][1]:
        return []
    out = []
    for a in range(3):
        n, cap = q[a]
        if not cap:
            continue
        up = 0 if a == 0 else (r['연령별'][a - 1][2] if r['연령별'] else None)
        out.append((AGE[a], n, cap, None if up is None or a == 0 else up, None if up is None else max(0, cap - up)))
    return out


def page(r):
    c = COST.get(str(r['id']))
    typ, gu, name = r['유형'], r['구'], r['유치원명']
    kind = '국공립' if typ == '국공립' else '사립'
    lead = [f'{gu}에 있는 {kind} 유치원이에요.']
    if r['원아수'] is not None:
        lead.append(f'올해 {r["원아수"]}명이 다니고 한 반 평균은 {round(r["학급당원아"])}명이에요.' if r['학급당원아'] is not None else f'올해 {r["원아수"]}명이 다녀요.')
    cost_lines = []
    if c:
        for a in range(3):
            if c[a] is None:
                continue
            tot = c[a] + (c[a + 3] or 0)
            av = cost_avg(typ, gu, a)
            cmp = '' if av is None or tot == 0 else f' ({gu} {kind} 평균 월 {won(round(av))})'
            cost_lines.append(f'<tr><th>{AGE[a]}</th><td>{won(c[a])}</td><td>{won(c[a + 3] or 0)}</td><td><b>{"0원" if tot == 0 else won(tot)}</b>{cmp}</td></tr>')
        if c[2] is not None:
            tot = c[2] + (c[5] or 0)
            lead.append('만 5세 기준 월 비용은 0원이에요.' if tot == 0 else f'만 5세 기준 월 비용은 {won(tot)}이에요.')
    fx = []
    if r['연령별']:
        for i, (n, cap, kids) in enumerate(r['연령별']):
            if n > 0:
                p = f'{round(kids / cap * 100)}%' if cap else '-'
                fx.append(f'<tr><th>{AGE[i]}</th><td>{n}개</td><td>{cap}명</td><td>{kids}명</td><td>{p}</td></tr>')
    nx = next_rows(r)
    mixed = bool(r['연령별'] and r['연령별'][3][2])
    if nx and not mixed:
        first = [x for x in nx if x[4] is not None and x[0] != '만 3세']
        if first:
            best = max(first, key=lambda x: x[4])
            if best[4] > 0:
                lead.append(f'내년({RC["aid"]}학년도)엔 {best[0]} 반에 약 {best[4]}명 자리가 날 것으로 보여요.')
    info = []
    if r['교사1인당원아'] is not None and not r['데이터주의']:
        ta = avg(typ, '교사1인당원아')
        info.append(f'<tr><th>선생님 한 명당 아이</th><td>{round(r["교사1인당원아"])}명' + (f' (서울 {kind} 평균 {round(ta)}명)' if ta is not None else '') + '</td></tr>')
    if r['4년이상비율'] is not None:
        info.append(f'<tr><th>4년 넘게 근무한 선생님</th><td>{round(r["4년이상비율"])}%</td></tr>')
    if r['운영시간']:
        info.append(f'<tr><th>운영 시간</th><td>{e(r["운영시간"])} (방과후 포함)</td></tr>')
    if r['방과후참여율'] is not None and r['방과후참여율'] <= 100:
        info.append(f'<tr><th>방과후 참여</th><td>{round(r["방과후참여율"])}%</td></tr>')
    det = DET.get(str(r['id'])) or {}
    bus, cctv = det.get('bus'), det.get('cctv')
    if bus is not None:
        info.append(f'<tr><th>통학 차량</th><td>{f"운영 ({bus}대)" if bus else "운영 안 함"}</td></tr>')
    else:
        info.append(f'<tr><th>통학 차량</th><td>{"운영" if r["차량운영여부"] == "운영" else "운영 안 함"}</td></tr>')
    if cctv is not None:
        info.append(f'<tr><th>CCTV</th><td>{cctv}대 설치</td></tr>')
    near = nearby(r)
    nrows = []
    if near:
        me = cost5(r['id'])
        nrows.append(f'<tr><th>{e(name)} (이 유치원)</th><td>-</td><td><b>{"-" if me is None else ("0원" if me == 0 else won(me))}</b></td></tr>')
        for d, o in near:
            cc = cost5(o['id'])
            href = f'{o["id"]}.html' if o['id'] in GEN else f'../#k{o["id"]}'
            nrows.append(f'<tr><th><a href="{href}">{e(o["유치원명"])}</a></th><td>{round(d / 10) * 10}m</td><td>{"-" if cc is None else ("0원" if cc == 0 else won(cc))}</td></tr>')
    place = ''
    addr, tel, web = det.get('addr'), det.get('tel'), det.get('web')
    if addr or tel:
        q = urllib.parse.quote(f'{name},{r["위도"]},{r["경도"]}')
        contact = ([f'<tr><th>주소</th><td>{e(full_addr(addr))}</td></tr>'] if addr else []) + \
                  ([f'<tr><th>전화</th><td><a href="tel:{e(tel)}">{e(tel)}</a></td></tr>'] if tel else [])
        if web and web.startswith(('http://', 'https://')):
            contact.append(f'<tr><th>홈페이지</th><td><a href="{e(web)}" rel="nofollow noopener" target="_blank">{e(web.split("//")[1].rstrip("/"))}</a></td></tr>')
        place = (f'<div id="map" style="height:200px;border-radius:12px;background:#e6ece8"></div>\n'
                 f'<p><a href="https://map.kakao.com/link/map/{q}">카카오맵에서 보기</a> · <a href="https://map.kakao.com/link/to/{q}">길찾기</a></p>\n'
                 f'<table>{"".join(contact)}</table>\n'
                 f'<script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_KEY}&autoload=false"></script>\n'
                 f'<script>kakao.maps.load(function(){{var p=new kakao.maps.LatLng({r["위도"]},{r["경도"]});new kakao.maps.StaticMap(document.getElementById("map"),{{center:p,level:3,marker:{{position:p}}}})}})</script>')
    title = f'{name} 원비·정원·내년 빈자리 | {gu} 유치원 | 킨더맵'
    desc = ' '.join(lead)[:150]
    ld = {'@context': 'https://schema.org', '@type': 'Preschool', 'name': name,
          'address': {'@type': 'PostalAddress', 'addressRegion': '경기도' if gg(r) else '서울특별시', 'addressLocality': gu, 'addressCountry': 'KR'},
          'geo': {'@type': 'GeoCoordinates', 'latitude': r['위도'], 'longitude': r['경도']}}
    if addr:
        ld['address']['streetAddress'] = addr
    if tel:
        ld['telephone'] = tel
    robots = '<meta name="robots" content="noindex,nofollow">\n' if NOINDEX else ''
    sec = lambda h, body: f'<h2>{h}</h2>\n{body}\n' if body else ''
    tbl = lambda head, rows: f'<table><tr>{"".join(f"<th>{x}</th>" for x in head)}</tr>{"".join(rows)}</table>' if rows else ''
    nxt = tbl(['', '반', '정원', '올라올 아이', '빈자리(추정)'],
              [f'<tr><th>{a}</th><td>{n}개</td><td>{cap}명</td><td>{"-" if up is None else f"{up}명"}</td><td>{"-" if v is None else f"약 {v}명"}</td></tr>' for a, n, cap, up, v in nx])
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{robots}<link rel="canonical" href="{SITE}k/{r["id"]}.html">
<meta property="og:type" content="website">
<meta property="og:site_name" content="킨더맵">
<meta property="og:title" content="{e(name)} · {gu} 유치원 원비·정원·내년 빈자리">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{SITE}k/{r["id"]}.html">
<meta property="og:image" content="{SITE}og.png?v={OG_V}">
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
h1{{font-size:22px;margin:8px 0}}h2{{font-size:17px;margin:24px 0 8px}}
.lead{{background:#fff;border-radius:12px;padding:14px 16px}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;font-size:14px}}
th,td{{padding:8px 10px;border-bottom:1px solid #e6ece8;text-align:left}}
.cta{{display:block;text-align:center;margin:20px 0;padding:14px;border-radius:12px;background:#1f3a32;color:#ffc94a;font-weight:700;text-decoration:none}}
small{{color:#5b6b64}}a{{color:#1f6f54}}
</style></head><body><main>
<small><a href="../">킨더맵</a> › {gu} › 유치원</small>
<h1>{e(name)}</h1>
{f'<small>{e(full_addr(addr))}</small>' if addr else ''}
<p class="lead">{e(" ".join(lead))}</p>
<a class="cta" href="../#k{r["id"]}">지도에서 주변 유치원과 비교하기</a>
{sec("한 달 비용", tbl(["", "교육비", "방과후", "합계"], cost_lines) + f"<small>정부 지원금을 뺀 학부모 부담 고지액({BASIS} 공시)이에요. 특성화 활동·차량·현장학습 같은 선택 비용은 빠져 있어요.</small>" if cost_lines else "")}
{sec("나이별 반", tbl(["", "반", "정원", "다니는 아이", "찬 정도"], fx) + "<small>올해 만든 반 기준이에요.</small>" if fx else "")}
{sec("내년 예상 빈자리", nxt + f"<small>{e(RC['basis'])}의 나이별 정원에서 올해 한 살 아래 반 아이 수를 뺀 추정치예요. 중도 퇴소·형제 우선은 반영하지 않았어요." + ("<br>올해 혼합반에 다니는 아이는 나이별로 나눌 수 없어서 '올라올 아이'가 실제보다 적게, 빈자리는 많게 나올 수 있어요." if mixed else "") + "</small>" if nxt else "")}
{sec("가까운 유치원과 비교 (반경 1km)", tbl(["", "거리", "만 5세 월 비용"], nrows) + "<small>이 유치원에서 가까운 순이에요. 비용은 정부 지원금을 뺀 부담 고지액이에요.</small>" if nrows else "")}
{sec("선생님·운영", f'<table>{"".join(info)}</table>')}
{sec("위치·연락처", place)}
<p><small>출처: 유치원알리미 정보공시, 유보통합포털 모집요강. 정확한 내용은 유치원에 직접 확인하세요.</small></p>
<p><small>정보가 다르거나 바뀐 게 있으면 <a href="mailto:kindermap2026@gmail.com?subject={urllib.parse.quote("[정정 요청] " + name)}">kindermap2026@gmail.com</a>으로 알려 주세요. 유치원 관계자의 정정 요청도 받아요.</small></p>
</main></body></html>
'''


def main():
    sel = [r for r in ROWS if r['상태'] is None and (GU is None or r['구'] == GU)]
    if LIMIT:
        sel = sel[:LIMIT]
    os.makedirs(os.path.join(root, 'k'), exist_ok=True)
    GEN.update(r['id'] for r in sel)
    # 한 곳에서 오류가 나도 나머지 페이지는 만든다. 오류 난 곳은 예전 파일을 그대로 두고, 끝에 실패로 알린다(워크플로 실패 알림).
    fail = []
    for r in sel:
        try:
            out = page(r)
        except Exception:
            fail.append(r['id'])
            print(f'  페이지 오류 {r["id"]} {r["유치원명"]} (예전 파일 유지):', file=sys.stderr)
            traceback.print_exc(limit=2)
            continue
        open(os.path.join(root, 'k', f'{r["id"]}.html'), 'w', encoding='utf-8').write(out)
    print(len(sel) - len(fail), 'pages -> k/', f'(오류 {len(fail)}곳: {fail})' if fail else '')
    # 대상에서 빠진 곳의 옛 페이지 지우기(옛 숫자가 계속 남지 않게)
    kdir = os.path.join(root, 'k')
    keep = {f'{r["id"]}.html' for r in sel}
    stale = sorted(f for f in os.listdir(kdir) if re.fullmatch(r'\d+\.html', f) and f not in keep)
    if stale and (len(stale) <= max(10, len(sel) * 0.2) or '--prune' in sys.argv) and sel:
        for f in stale:
            os.remove(os.path.join(kdir, f))
        print(f'대상에서 빠진 옛 페이지 {len(stale)}개 지움: {stale[:10]}')
    elif stale:
        print(f'대상에서 빠진 옛 페이지가 {len(stale)}개라 지우지 않음(데이터 이상일 수 있음). 일부러 줄였으면 --prune', file=sys.stderr)
        fail.append('stale')
    # sitemap.xml: 색인을 허용했을 때만(noindex인 동안은 지움)
    sm = os.path.join(root, 'sitemap.xml')
    if NOINDEX:
        if os.path.exists(sm):
            os.remove(sm)
    else:
        today = datetime.date.today().isoformat()
        urls = [SITE] + [f'{SITE}k/{r["id"]}.html' for r in sel if f'{r["id"]}.html' in set(os.listdir(kdir))]
        with open(sm, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                    + ''.join(f'<url><loc>{u}</loc><lastmod>{today}</lastmod></url>\n' for u in urls) + '</urlset>\n')
        print('sitemap.xml', len(urls), '주소')
    if fail:
        sys.exit(1)


main()

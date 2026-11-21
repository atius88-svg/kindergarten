# 기관별 정적 상세 페이지(SEO 시험): python3 scripts/build_pages.py  (저장소 루트에서 실행)
# 시험 단계: 성북구 유치원 30곳만 k/{id}.html 로 만든다. 모든 페이지에 noindex를 넣어 검색에 잡히지 않게 한다.
# 배포를 결정하면 NOINDEX=False, GU=None, LIMIT=None 으로 바꾸고 sitemap.xml 생성을 켠다.
import html, json, os, statistics

NOINDEX, GU, LIMIT = True, '성북구', 30
SITE = 'https://atius88-svg.github.io/kindergarten/'
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
L = lambda p: json.load(open(os.path.join(root, 'src/data', p), encoding='utf-8'))

kg = L('kg_seoul.json.txt')
ROWS = [dict(zip(kg['cols'], r)) for r in kg['rows']]
COSTD = L('kg_cost_seoul.json'); COST = COSTD['cost']
RC = L('kg_rcrt.json'); RCR = RC['r']
BASIS = COSTD['basis'].split('(')[0].strip()
AGE = ['만 3세', '만 4세', '만 5세', '혼합반', '특수반']
e = html.escape


def won(n):
    return f'{round(n / 1000) / 10:g}만원' if n >= 10000 else f'{n:,}원'


def cost_avg(typ, gu, a):
    v = [COST[str(r['id'])][a] + (COST[str(r['id'])][a + 3] or 0) for r in ROWS
         if r['구'] == gu and r['유형'] == typ and r['상태'] is None and COST.get(str(r['id'])) and COST[str(r['id'])][a] is not None]
    return statistics.mean(v) if v else None


def avg(typ, k):
    v = [r[k] for r in ROWS if r['유형'] == typ and r[k] is not None and r['상태'] is None and not (k == '교사1인당원아' and r['데이터주의'])]
    return statistics.mean(v)


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
        lead.append(f'올해 {r["원아수"]}명이 다니고 한 반 평균은 {round(r["학급당원아"])}명이에요.')
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
        info.append(f'<tr><th>선생님 한 명당 아이</th><td>{round(r["교사1인당원아"])}명 (서울 {kind} 평균 {round(avg(typ, "교사1인당원아"))}명)</td></tr>')
    if r['4년이상비율'] is not None:
        info.append(f'<tr><th>4년 넘게 근무한 선생님</th><td>{round(r["4년이상비율"])}%</td></tr>')
    if r['운영시간']:
        info.append(f'<tr><th>운영 시간</th><td>{e(r["운영시간"])} (방과후 포함)</td></tr>')
    if r['방과후참여율'] is not None and r['방과후참여율'] <= 100:
        info.append(f'<tr><th>방과후 참여</th><td>{round(r["방과후참여율"])}%</td></tr>')
    info.append(f'<tr><th>통학 차량</th><td>{"운영" if r["차량운영여부"] == "운영" else "운영 안 함"}</td></tr>')
    title = f'{name} 원비·정원·내년 빈자리 | {gu} 유치원 | 우리동네 유치원'
    desc = ' '.join(lead)[:150]
    ld = {'@context': 'https://schema.org', '@type': 'Preschool', 'name': name,
          'address': {'@type': 'PostalAddress', 'addressRegion': '서울특별시', 'addressLocality': gu, 'addressCountry': 'KR'},
          'geo': {'@type': 'GeoCoordinates', 'latitude': r['위도'], 'longitude': r['경도']}}
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
<small><a href="../">우리동네 유치원</a> › {gu} › 유치원</small>
<h1>{e(name)}</h1>
<p class="lead">{e(" ".join(lead))}</p>
<a class="cta" href="../#k{r["id"]}">지도에서 주변 유치원과 비교하기</a>
{sec("한 달 비용", tbl(["", "교육비", "방과후", "합계"], cost_lines) + f"<small>정부 지원금을 뺀 학부모 부담 고지액({BASIS} 공시)이에요. 특성화 활동·차량·현장학습 같은 선택 비용은 빠져 있어요.</small>" if cost_lines else "")}
{sec("나이별 반", tbl(["", "반", "정원", "다니는 아이", "찬 정도"], fx) + "<small>올해 만든 반 기준이에요.</small>" if fx else "")}
{sec("내년 예상 빈자리", nxt + f"<small>{e(RC['basis'])}의 나이별 정원에서 올해 한 살 아래 반 아이 수를 뺀 추정치예요. 중도 퇴소·형제 우선은 반영하지 않았어요." + ("<br>올해 혼합반에 다니는 아이는 나이별로 나눌 수 없어서 '올라올 아이'가 실제보다 적게, 빈자리는 많게 나올 수 있어요." if mixed else "") + "</small>" if nxt else "")}
{sec("선생님·운영", f'<table>{"".join(info)}</table>')}
<p><small>출처: 유치원알리미 정보공시, 유보통합포털 모집요강. 정확한 내용은 유치원에 직접 확인하세요.</small></p>
</main></body></html>
'''


def main():
    sel = [r for r in ROWS if r['상태'] is None and (GU is None or r['구'] == GU)]
    if LIMIT:
        sel = sel[:LIMIT]
    os.makedirs(os.path.join(root, 'k'), exist_ok=True)
    for r in sel:
        open(os.path.join(root, 'k', f'{r["id"]}.html'), 'w', encoding='utf-8').write(page(r))
    print(len(sel), 'pages -> k/')


main()

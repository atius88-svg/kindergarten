"""공유 미리보기용 기관별 주소: s/{id}.html + s/{id}.png  (python3 scripts/build_share.py, 저장소 루트에서)

카톡·문자 미리보기는 주소의 HTML에 있는 og 태그만 읽는다(스크립트를 실행하지 않고, 주소 뒤 #k… 해시는 무시).
지도 서비스는 한 페이지라 기관마다 미리보기를 다르게 할 수 없어서, 기관마다 작은 HTML을 만들어 og 태그만 넣고
사람이 열면 스크립트로 바로 지도 상세(../#k{id}, ../#kc{stcode})로 보낸다. noindex라 검색에는 안 잡힌다.
- 대상: 지도에 있는 유치원 전부(kg_seoul.json.txt) + 어린이집 전부(dc_seoul.json). 파일 이름은 지도 상세 id와 같다(604, c11290000123).
- 이미지(800×420): 이름·구·유형·정원. 정원은 1년에 한 번 정도만 바뀌어 대부분 그대로 → 글자가 바뀐 곳·새 곳만 다시 그린다(s/images.json에 그린 글자 기록).
- 설명 문구: 유치원은 만 5세 월 비용·원아 수·한 반 인원(공시 기준), 어린이집은 숫자 없이 안내 문구(어린이집 API 약관 확인 전).
- 지도에서 빠진 곳의 s/ 파일은 지운다. 한 번에 많이 지워야 하면(데이터 이상일 수 있음) 지우지 않고 오류로 알린다 → 일부러면 --prune.
필요: Pillow(pip install pillow), scripts/fonts/Jua-Regular.ttf (SIL OFL, scripts/fonts/OFL.txt).
"""
import html, json, os, re, sys

SITE = 'https://atius88-svg.github.io/kindergarten/'
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
OUT = os.path.join(root, 's')
FONT = os.path.join(root, 'scripts', 'fonts', 'Jua-Regular.ttf')
W, H = 800, 420
STYLE = {'kg': ('#1f3a32', '#ffc94a', '유치원'), 'dc': ('#2b2f4a', '#8be0bd', '어린이집')}  # 사이트 맨 위 바 색
e = html.escape


def load(p):
    with open(os.path.join(root, 'src', 'data', p), encoding='utf-8') as f:
        return json.load(f)


def won(n):
    return f'{round(n / 1000) / 10:g}만원' if n >= 10000 else f'{n:,}원'


def items():
    """[(파일 id, 모드, 이름, 구, 유형 글자, 정원, 설명)]"""
    kg, cost, dc = load('kg_seoul.json.txt'), load('kg_cost_seoul.json')['cost'], load('dc_seoul.json')
    out = []
    for v in kg['rows']:
        r = dict(zip(kg['cols'], v))
        i = str(r['id'])
        bits = []
        if r.get('상태'):
            bits.append('지금 휴원' if r['상태'] == '휴원' else '공시 전')
        c = cost.get(i)
        if c and c[2] is not None:
            t = c[2] + (c[5] or 0)
            bits.append('만 5세 월 ' + ('0원' if t == 0 else won(t)))
        if r.get('정원'):
            bits.append(f'정원 {r["정원"]}명')
        if r.get('원아수') is not None:
            bits.append(f'원아 {r["원아수"]}명')
        if r.get('학급당원아') is not None:
            bits.append(f'한 반 {round(r["학급당원아"])}명')
        desc = ' · '.join(bits) + (' — ' if bits else '') + '원비·한 반 인원·내년 빈자리를 지도에서 주변 유치원과 비교해 보세요.'
        out.append((i, 'kg', r['유치원명'], r['구'], f'{r["유형"]} 유치원', r.get('정원'), desc))
    for v in dc['rows']:
        r = dict(zip(dc['cols'], v))
        cap = r.get('정원') or None
        out.append((r['id'], 'dc', r['유치원명'], r['구'], f'{r["설립유형"]} 어린이집', cap,
                    (f'정원 {cap}명 — ' if cap else '') + '평가·입소 대기·연장보육·선생님 근속을 지도에서 주변 어린이집과 비교해 보세요.'))
    return out


def page(fid, mode, name, gu, kind, cap, desc):
    url, img, to = f'{SITE}s/{fid}.html', f'{SITE}s/{fid}.png', f'../#k{fid}'
    title = f'{name} · {gu} {kind}'
    return f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} | 우리동네 {STYLE[mode][2]}</title>
<meta name="robots" content="noindex">
<meta name="description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="우리동네 유치원·어린이집">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{img}">
<meta property="og:image:width" content="{W}"><meta property="og:image:height" content="{H}">
<meta name="twitter:card" content="summary_large_image">
<script>location.replace({json.dumps(to)})</script>
</head><body><p><a href="{e(to)}">{e(name)} 자세히 보기</a></p></body></html>
'''


def draw(mode, name, gu, kind, cap, path):
    from PIL import Image, ImageDraw, ImageFont
    bg, acc, noun = STYLE[mode]
    im = Image.new('RGB', (W, H), bg)
    d = ImageDraw.Draw(im)
    F = lambda s: ImageFont.truetype(FONT, s)
    # 왼쪽 위: 집 아이콘 + '우리동네 유치원/어린이집' (사이트 로고와 같은 모양)
    s, x0, y0 = 1.3, 52, 40
    P = lambda x, y: (x0 + x * s, y0 + y * s)
    d.line([P(5, 19), P(20, 6), P(35, 19)], fill=acc, width=5, joint='curve')
    d.line([P(10, 17), P(10, 32), P(30, 32), P(30, 17)], fill='#ffffff', width=4, joint='curve')
    d.ellipse([P(15.5, 19.5), P(24.5, 28.5)], fill=acc)
    d.text((x0 + 56, y0 + 8), f'우리동네 {noun}', font=F(30), fill='#d7ddda')
    # 오른쪽 위: 지도 마커 점
    for cx, cy, col in [(694, 52, '#d4483b'), (738, 80, '#2f6fd0'), (690, 104, '#e08a00')]:
        d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=col, outline='#ffffff', width=4)
    # 가운데: 이름(길면 줄이고, 그래도 길면 두 줄)
    name = name.replace('＆', '&')
    size, lines = 78, [name]
    while size > 50 and d.textlength(name, font=F(size)) > W - 104:
        size -= 2
    if d.textlength(name, font=F(size)) > W - 104:
        cut = name.rfind(' ', 0, len(name) // 2 + 6)
        cut = cut if cut > 3 else len(name) // 2
        lines = [name[:cut].strip(), name[cut:].strip()]
        size = 64
        while size > 34 and max(d.textlength(l, font=F(size)) for l in lines) > W - 104:
            size -= 2
    y = 215 - (len(lines) * size * 1.15) / 2
    for l in lines:
        d.text((52, y), l, font=F(size), fill=acc)
        y += size * 1.15
    # 아래 오른쪽: 정원 알약, 왼쪽: 구 · 유형
    right = W - 52
    if cap:
        fc = F(36)
        t = f'정원 {cap}명'
        tw = d.textlength(t, font=fc)
        d.rounded_rectangle([right - tw - 44, 306, right, 364], radius=29, fill=acc)
        d.text((right - tw - 22, 314), t, font=fc, fill=bg)
        right -= tw + 44 + 24
    sz = 34
    while sz > 24 and d.textlength(gu + kind, font=F(sz)) + 35 > right - 54:
        sz -= 2
    f2 = F(sz)
    ty = 318 + (34 - sz) // 2
    d.text((54, ty), gu, font=f2, fill='#ffffff')
    gx = 54 + d.textlength(gu, font=f2) + 14
    d.ellipse([gx, ty + 18, gx + 7, ty + 25], fill='#ffffff')
    d.text((gx + 21, ty), kind, font=f2, fill='#ffffff')
    d.rectangle([0, H - 10, W, H], fill=acc)
    im.quantize(colors=48, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = items()
    man_p = os.path.join(OUT, 'images.json')
    man = json.load(open(man_p, encoding='utf-8')) if os.path.exists(man_p) else {}
    drawn = wrote = 0
    for fid, mode, name, gu, kind, cap, desc in rows:
        p = os.path.join(OUT, f'{fid}.html')
        txt = page(fid, mode, name, gu, kind, cap, desc)
        if not os.path.exists(p) or open(p, encoding='utf-8').read() != txt:
            open(p, 'w', encoding='utf-8').write(txt)
            wrote += 1
        key = f'{mode}|{name}|{gu}|{kind}|{cap or ""}'
        png = os.path.join(OUT, f'{fid}.png')
        if man.get(fid) != key or not os.path.exists(png):
            draw(mode, name, gu, kind, cap, png)
            man[fid] = key
            drawn += 1
    # 지도에서 빠진 곳 정리
    keep = {fid for fid, *_ in rows}
    stale = sorted(f for f in os.listdir(OUT) if re.fullmatch(r'c?\d+\.(html|png)', f) and f.rsplit('.', 1)[0] not in keep)
    bad = False
    if stale and (len(stale) <= max(40, len(rows) * 0.05) or '--prune' in sys.argv):
        for f in stale:
            os.remove(os.path.join(OUT, f))
        print(f'지도에서 빠진 곳 파일 {len(stale)}개 지움: {stale[:6]}')
    elif stale:
        print(f'지도에서 빠진 곳 파일이 {len(stale)}개라 지우지 않음(데이터 이상일 수 있음). 일부러면 --prune', file=sys.stderr)
        bad = True
    man = {k: v for k, v in man.items() if k in keep}
    with open(man_p, 'w', encoding='utf-8') as f:
        json.dump(dict(sorted(man.items())), f, ensure_ascii=False, separators=(',', ':'))
    print(f'공유 미리보기: {len(rows)}곳, HTML 새로 씀 {wrote}, 이미지 새로 그림 {drawn}')
    if bad:
        sys.exit(1)


if __name__ == '__main__':
    main()

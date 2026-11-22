# index.html + dc.json 빌드: python3 src/build.py  (저장소 루트에서 실행)
# 어린이집(서울 전체, 약 1.4MB)은 index.html에 넣지 않고 dc.json으로 따로 내보내 어린이집 모드에서만 불러온다.
import hashlib, os
d = os.path.dirname(os.path.abspath(__file__))
r = lambda p: open(os.path.join(d, p), encoding='utf-8').read().strip()
import json, re, shutil
dc = r('data/dc_seoul.json')
# 개편 후 평가결과서(src/data/dc_eval.json, scripts/fetch_dc_eval.py)에서 학부모에게 쓸모 있는 것만 뽑는다.
# 종합의견은 대부분 비슷한 칭찬 문장이라 화면에는 보완 권고만 보여 주고, 전문은 눌러야 펼친다.
#  - 보완 권고: '다만, …' / '…바랍니다.' 문장 → dc.json '평가보완'(개수), dc_tips.json(문장, 상세를 열 때 받음)
#  - 전문: ev/c{stcode}.json(누를 때 받음)
#  - 특색: 다른 곳 글에는 드문 활동·인증 키워드 → dc.json '특색'(드문 것부터 최대 3개)
evp = os.path.join(d, 'data', 'dc_eval.json')
ev = {k: v for k, v in (json.loads(r('data/dc_eval.json')) if os.path.exists(evp) else {}).items() if v.get('a')}
TIP = re.compile(r'^다만|유의하시기 바랍니다|바랍니다\.?$')
FEAT = [  # (표시, 찾을 표현)
    ('실내공기 우수시설', r'실내공기 ?우수'),
    ('안심 공간 인증', r'안심 ?공간'),
    ('장애아 통합보육', r'장애아 ?통합|통합보육'),
    ('다문화 어린이집', r'다문화 ?지정|다문화 ?(?:가정|아동|영유아)'),
    ('AI 식사 분석', r'(?:인공지능|AI)[^.]{0,8}(?:식사|식사량)'),
    ('미술관·박물관 나들이', r'미술관|박물관'),
    ('전통놀이·절기', r'전통 ?놀이|절기|세시'),
    ('도서관 연계', r'도서관'),
    ('부모 급식 모니터링', r'부모[^.]{0,15}모니터링'),
    ('물놀이', r'물놀이'),
    ('요리 활동', r'요리'),
    ('우수 급식소', r'우수 ?급식소|빛나는 급식소|바른 급식|든든 ?급식'),
    ('저염 급식', r'저염'),
    ('숲 놀이', r'숲(?:에서|으로|놀이|체험|산책|길|속)|유아숲'),
    ('생태 체험', r'생태|곤충[^.]{0,10}(?:관찰|탐색|키우)|동물을? (?:키우|기르|돌보)'),
    ('텃밭 가꾸기', r'텃밭'),
]
full = {k: ' '.join(t for _, t in v['a']) for k, v in ev.items()}
freq = {name: sum(1 for t in full.values() if re.search(pat, t)) for name, pat in FEAT}
FEAT.sort(key=lambda f: freq[f[0]])
def tips_of(a):
    out = []
    for area, t in a:
        for x in re.split(r'(?<=[.!?])\s+', t):
            if TIP.search(x):
                out.append([area, re.sub(r'^다만,?\s*', '', x)])
    return out
TIPS = {k: tips_of(v['a']) for k, v in ev.items()}
# AI 4칸 정리(src/data/dc_eval_ai.json, scripts/analyze_dc_eval.py) — 있으면 '평가4' 열과 특색 태그를 이걸로
aip = os.path.join(d, 'data', 'dc_eval_ai.json')
AI = json.loads(r('data/dc_eval_ai.json')) if os.path.exists(aip) else {}
PLAB = {'참여수업': '부모 참여수업', '급식 모니터링': '부모 급식 모니터링', '아빠 참여': '아빠 참여수업', '쿠킹클래스': '부모 쿠킹클래스',
        '가족 프로그램': '가족 프로그램', '현장학습 도우미': '부모 현장학습 도우미', '부모교육': '부모교육'}
def ai_tags(o):
    t = []
    if o['dev']:
        t.append('발달 지원')
    if o['freq'] in ('매주', '매월'):
        t.append(f"{o['freq']} {o['kinds'][0] if len(o['kinds']) == 1 else '바깥 활동'}")  # 종류가 여럿이면 어느 게 그 빈도인지 몰라 '바깥 활동'
    for x in ['아빠 참여', '쿠킹클래스', '가족 프로그램', '참여수업', '급식 모니터링', '현장학습 도우미', '부모교육']:
        if x in o['parent']:
            t.append(PLAB[x]); break
    for x in ['저염 인증', '우수급식소', '전담 영양사']:
        if x in o['meal']:
            t.append(x); break
    return t[:3]
DCJ = json.loads(dc)
DCJ['cols'] += ['평가보완', '특색', '평가4']
n_ai = 0
for row in DCJ['rows']:
    k = row[0][1:]
    a = AI.get(k)
    if k in ev and a and a.get('ym') == ev[k]['ym']:
        o = a['o']; n_ai += 1
        row += [len(TIPS[k]), ai_tags(o), [o['freq'], o['kinds'], o['meal'], o['parent'], o['dev']]]
    elif k in ev:
        row += [len(TIPS[k]), [n for n, pat in FEAT if re.search(pat, full[k])][:3], None]
    else:
        row += [None, None, None]
dc = json.dumps(DCJ, ensure_ascii=False, separators=(',', ':'))
tips_json = json.dumps({'c' + k: v for k, v in sorted(TIPS.items()) if v}, ensure_ascii=False, separators=(',', ':'))
open(os.path.join(d, '..', 'dc_tips.json'), 'w', encoding='utf-8').write(tips_json + '\n')
# 영역별 종합의견 전문: ev/c{stcode}.json({ym, a}) — 상세에서 '평가결과서 전문 보기'를 누를 때만 받는다
evdir = os.path.join(d, '..', 'ev')
os.makedirs(evdir, exist_ok=True)
for f in os.listdir(evdir):
    if f.endswith('.json') and f[1:-5] not in ev:
        os.remove(os.path.join(evdir, f))
for k, v in ev.items():
    body = json.dumps({'ym': v['ym'], 'a': v['a']}, ensure_ascii=False, separators=(',', ':'))
    pth = os.path.join(evdir, f'c{k}.json')
    if not os.path.exists(pth) or open(pth, encoding='utf-8').read() != body:
        open(pth, 'w', encoding='utf-8').write(body)
ev_v = hashlib.md5(tips_json.encode()).hexdigest()[:8]
open(os.path.join(d, '..', 'dc.json'), 'w', encoding='utf-8').write(dc + '\n')
ver = hashlib.sha1(dc.encode()).hexdigest()[:10]  # 데이터가 바뀌면 주소가 바뀌어 캐시를 새로 받음
import json
# 상세정보는 index.html 크기를 줄이려고 배열로 압축: {id: [주소, 전화, 홈페이지, 통학차량 대수, CCTV 대수]}
det = json.dumps({k: [v.get('addr'), v.get('tel'), v.get('web'), v.get('bus'), v.get('cctv')]
                  for k, v in json.loads(r('data/kg_detail.json')).items()}, ensure_ascii=False, separators=(',', ':'))
# 공유 미리보기 주소(s/{id}.html, scripts/build_share.py가 먼저 만듦)가 아직 없는 곳 — 이런 곳은 지도 주소로 공유한다
sdir = os.path.join(d, '..', 's')
kg = json.loads(r('data/kg_seoul.json.txt'))
all_ids = [str(x[kg['cols'].index('id')]) for x in kg['rows']] + [x[0] for x in json.loads(dc)['rows']]
noshare = [i for i in all_ids if not os.path.exists(os.path.join(sdir, f'{i}.html'))]
man = os.path.join(sdir, 'images.json')
share_v = hashlib.md5(open(man, 'rb').read()).hexdigest()[:6] if os.path.exists(man) else '0'
# 원비: 앞 6개 값 + 특성화 합계 [만3,4,5](7번째)만 index.html에, 특성화 프로그램 목록은 kg_sp.json(상세를 열 때 받음)
costd = json.loads(r('data/kg_cost_seoul.json'))
sp_list = {}
for k, v in costd['cost'].items():
    sp = v[6] if len(v) > 6 else None
    v[6:] = [[[a[0], len(a[1])] for a in sp]] if sp else []  # [[월 합계, 프로그램 수] × 만3·4·5]
    if sp and any(a[1] for a in sp):
        sp_list[k] = [[[p[0], p[1], p[2], p[3]] for p in a[1]] for a in sp]
cost_json = json.dumps(costd, ensure_ascii=False, separators=(',', ':'))
sp_json = json.dumps(dict(sorted(sp_list.items(), key=lambda x: int(x[0]))), ensure_ascii=False, separators=(',', ':'))
open(os.path.join(d, '..', 'kg_sp.json'), 'w', encoding='utf-8').write(sp_json + '\n')
sp_v = hashlib.md5(sp_json.encode()).hexdigest()[:8]
# 항목별 자료 기준일(상세 맨 아래 '자료 기준') — 값이 없으면 그 줄은 화면에서 빠짐
kgm = json.loads(r('data/kg_seoul.json.txt'))
dcm = json.loads(r('data/dc_seoul.json'))
ptl = sorted(v['t'] for v in json.loads(r('data/dc_portal.json')).values() if v.get('t'))
dts = sorted(v['t'] for v in json.loads(r('data/kg_detail.json')).values() if v.get('t'))
meta = json.dumps({'kg_pb': kgm.get('pb'), 'kg_t': kgm.get('t'), 'det': dts[-1] if dts else None,
                   'dc_t': dcm.get('t'), 'ptl': [ptl[0], ptl[-1]] if ptl else None}, ensure_ascii=False)
h = (r('template.html').replace('%%NOSHARE%%', json.dumps(noshare)).replace('%%SHARE_V%%', share_v).replace('%%DATA%%', r('data/kg_seoul.json.txt'))
     .replace('%%COST%%', cost_json).replace('%%SP_V%%', sp_v).replace('%%META%%', meta).replace('%%DC_URL%%', f'dc.json?v={ver}')
     .replace('%%RCRT%%', r('data/kg_rcrt.json')).replace('%%DET%%', det).replace('%%EV_V%%', ev_v))
open(os.path.join(d, '..', 'index.html'), 'w', encoding='utf-8').write(h + '\n' if not h.endswith('\n') else h)
print('index.html', len(h), '/ 특성화 목록', len(sp_list), '/ dc.json', len(dc), '/ 공유 주소 없는 곳', len(noshare), '/ 평가결과서', len(ev), '/ AI 정리', n_ai)

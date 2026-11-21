# index.html + dc.json 빌드: python3 src/build.py  (저장소 루트에서 실행)
# 어린이집(서울 전체, 약 1.4MB)은 index.html에 넣지 않고 dc.json으로 따로 내보내 어린이집 모드에서만 불러온다.
import hashlib, os
d = os.path.dirname(os.path.abspath(__file__))
r = lambda p: open(os.path.join(d, p), encoding='utf-8').read().strip()
import json, re, shutil
dc = r('data/dc_seoul.json')
# 개편 후 평가결과서(src/data/dc_eval.json, scripts/fetch_dc_eval.py) → ev/{id}.json(상세 화면에서 불러옴) + dc.json에 '평가보완'(보완 권고 문장 수) 열
evp = os.path.join(d, 'data', 'dc_eval.json')
ev = json.loads(r('data/dc_eval.json')) if os.path.exists(evp) else {}
TIP = re.compile(r'^다만|유의하시기 바랍니다|바랍니다\.?$')
tips = lambda a: sum(1 for _, t in a for x in re.split(r'(?<=[.!?])\s+', t) if TIP.search(x))
evdir = os.path.join(d, '..', 'ev')
os.makedirs(evdir, exist_ok=True)
for f in os.listdir(evdir):  # 결과서가 없어진 곳 정리
    if f.endswith('.json') and f[1:-5] not in ev:
        os.remove(os.path.join(evdir, f))
for k, v in ev.items():
    body = json.dumps({'ym': v['ym'], 'a': v['a']}, ensure_ascii=False, separators=(',', ':'))
    pth = os.path.join(evdir, f'c{k}.json')
    if not os.path.exists(pth) or open(pth, encoding='utf-8').read() != body:
        open(pth, 'w', encoding='utf-8').write(body)
DCJ = json.loads(dc)
DCJ['cols'].append('평가보완')
for row in DCJ['rows']:
    e = ev.get(row[0][1:])
    row.append(tips(e['a']) if e else None)
dc = json.dumps(DCJ, ensure_ascii=False, separators=(',', ':'))
ev_v = hashlib.md5(json.dumps(ev, sort_keys=True).encode()).hexdigest()[:6]
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
h = (r('template.html').replace('%%NOSHARE%%', json.dumps(noshare)).replace('%%SHARE_V%%', share_v).replace('%%DATA%%', r('data/kg_seoul.json.txt'))
     .replace('%%COST%%', r('data/kg_cost_seoul.json')).replace('%%DC_URL%%', f'dc.json?v={ver}')
     .replace('%%RCRT%%', r('data/kg_rcrt.json')).replace('%%DET%%', det).replace('%%EV_V%%', ev_v))
open(os.path.join(d, '..', 'index.html'), 'w', encoding='utf-8').write(h + '\n' if not h.endswith('\n') else h)
print('index.html', len(h), '/ dc.json', len(dc), '/ 공유 주소 없는 곳', len(noshare), '/ 평가결과서', len(ev))

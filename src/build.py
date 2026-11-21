# index.html + dc.json 빌드: python3 src/build.py  (저장소 루트에서 실행)
# 어린이집(서울 전체, 약 1.4MB)은 index.html에 넣지 않고 dc.json으로 따로 내보내 어린이집 모드에서만 불러온다.
import hashlib, os
d = os.path.dirname(os.path.abspath(__file__))
r = lambda p: open(os.path.join(d, p), encoding='utf-8').read().strip()
dc = r('data/dc_seoul.json')
open(os.path.join(d, '..', 'dc.json'), 'w', encoding='utf-8').write(dc + '\n')
ver = hashlib.sha1(dc.encode()).hexdigest()[:10]  # 데이터가 바뀌면 주소가 바뀌어 캐시를 새로 받음
import json
# 상세정보는 index.html 크기를 줄이려고 배열로 압축: {id: [주소, 전화, 홈페이지, 통학차량 대수, CCTV 대수]}
det = json.dumps({k: [v.get('addr'), v.get('tel'), v.get('web'), v.get('bus'), v.get('cctv')]
                  for k, v in json.loads(r('data/kg_detail.json')).items()}, ensure_ascii=False, separators=(',', ':'))
# 기관별 페이지(k/{id}.html, scripts/build_pages.py가 먼저 만듦)가 있는 유치원 id — 상세 공유 주소로 쓴다
kdir = os.path.join(d, '..', 'k')
pages = sorted((f[:-5] for f in (os.listdir(kdir) if os.path.isdir(kdir) else []) if f[:-5].isdigit() and f.endswith('.html')), key=int)
h = (r('template.html').replace('%%PAGES%%', json.dumps(pages)).replace('%%DATA%%', r('data/kg_seoul.json.txt'))
     .replace('%%COST%%', r('data/kg_cost_seoul.json')).replace('%%DC_URL%%', f'dc.json?v={ver}')
     .replace('%%RCRT%%', r('data/kg_rcrt.json')).replace('%%DET%%', det))
open(os.path.join(d, '..', 'index.html'), 'w', encoding='utf-8').write(h + '\n' if not h.endswith('\n') else h)
print('index.html', len(h), '/ dc.json', len(dc), '/ 기관별 페이지', len(pages))

# index.html 빌드: python3 src/build.py  (저장소 루트에서 실행)
import os
d = os.path.dirname(os.path.abspath(__file__))
r = lambda p: open(os.path.join(d, p), encoding='utf-8').read().strip()
h = (r('template.html').replace('%%DATA%%', r('data/kg_seoul.json.txt'))
     .replace('%%COST%%', r('data/kg_cost_seongbuk.json')).replace('%%DC%%', r('data/dc_seongbuk.json')))
open(os.path.join(d, '..', 'index.html'), 'w', encoding='utf-8').write(h + '\n' if not h.endswith('\n') else h)
print('index.html', len(h))

# 모집요강 원본(scripts/fetch_rcrt.js 결과) → src/data/kg_rcrt.json
# 사용: python3 scripts/build_rcrt.py src/data/kg_rcrt_raw.json 2027 2026-11-13
# 원본 행: [포털코드, 교육지원청, 유치원명, 구, 설립유형, 주소, [[과정, 모집대상, 학급수, 시작일, 종료일, 정원], ...]]
# 과정(교육과정 / +방과후 / +오후에듀케어) 행은 따로 모집하는 칸이라 정원은 더하고, 학급 수는 나이별 최댓값(같은 반을 나눠 씀).
# 정원은 '재원예정 포함' 편성 인원 → 화면에서 올라올 아이(올해 한 살 아래 반 원아)를 뺀다.
import json, re, sys, collections, os

raw_path, aid, day = sys.argv[1], int(sys.argv[2]), sys.argv[3]
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
raw = json.load(open(raw_path, encoding='utf-8'))
d = json.load(open(os.path.join(root, 'src/data/kg_seoul.json.txt'), encoding='utf-8'))
rows = [dict(zip(d['cols'], r)) for r in d['rows']]
norm = lambda s: re.sub(r'\s|\(.*?\)', '', s)
idx = collections.defaultdict(list)
for r in rows:
    idx[(r['구'], norm(r['유치원명']))].append(r)

out, miss = {}, []
for x in raw:
    hit = idx.get((x[3], norm(x[2])), [])
    if len(hit) != 1:
        miss.append(f'{x[3]} {x[2]}')
        continue
    if not x[6]:
        continue
    q = [[0, 0] for _ in range(4)]
    mixcls = collections.defaultdict(int)
    for (_, tgt, cls, _s, _e, cap) in x[6]:
        cls, cap = int(cls or 0), int(cap or 0)
        m = re.match(r'([345])세$', tgt)
        if m:
            a = int(m.group(1)) - 3
            q[a][1] += cap
            q[a][0] = max(q[a][0], cls)
        else:  # 혼합연령(3~5세) 등
            q[3][1] += cap
            mixcls[tgt] = max(mixcls[tgt], cls)
    q[3][0] = sum(mixcls.values())
    out[str(hit[0]['id'])] = q

json.dump({'aid': aid, 'basis': f'{aid}학년도 유치원 모집요강(유보통합포털, {day} 수집)', 'r': out},
          open(os.path.join(root, 'src/data/kg_rcrt.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print('saved', len(out), '/ unmatched', len(miss))
for s in miss:
    print('  -', s)

"""네이버 블로그 검색 API → 유치원별 '블로그에서 언급된 프로그램' 키워드 (프로토타입).

사용법 (저장소 루트에서):
    NAVER_CLIENT_ID=... NAVER_CLIENT_SECRET=... python3 scripts/fetch_blog.py
    python3 scripts/fetch_blog.py --gu 성북구 --raw 폴더      # API 응답 원본을 폴더에 저장(점검용)
    python3 scripts/fetch_blog.py --fixtures 폴더              # {id}.json(API 응답)으로 오프라인 시험

결과:
    src/data/kg_blog.json   {basis, updated, gu, b: {id: {n, y: [첫해, 끝해], t: [[태그, 글 수]...], p: [[제목, 링크, 날짜]...]}}}
    blog_report.md          유치원별 수집·제외 수, 태그, 제외 사유 예시 (사람이 품질 점검용, 저장소에 안 올림)

원칙 (법적 리스크 줄이기):
- 본문 크롤링 안 함. 네이버 검색 API가 주는 제목·요약문·날짜만 쓴다.
- 요약문(description)은 태깅에만 쓰고 저장하지 않는다. 저장은 제목·링크·날짜만(원문으로 보내는 용도).
- '평가'·별점·부정 요약은 만들지 않는다. 프로그램 키워드(사실)만 센다.
- 협찬·체험단 글, 다른 지역 같은 이름 유치원 글은 뺀다.
- 하루 한도 25,000회. 성북구 44곳 × 최대 2쪽 = 90회 안팎.
"""
import argparse, html, json, os, re, sys, time, urllib.parse, urllib.request
from collections import Counter
from datetime import date

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
KG = os.path.join(ROOT, 'src', 'data', 'kg_seoul.json.txt')
OUT = os.path.join(ROOT, 'src', 'data', 'kg_blog.json')
REPORT = os.path.join(ROOT, 'blog_report.md')
URL = 'https://openapi.naver.com/v1/search/blog.json'
MIN_YEAR = date.today().year - 3  # 최근 3년 글만

# 구별 동네 이름: 이게 나오면 '우리 구 글'로 확정
LOCAL = {
    '성북구': ['성북', '돈암', '정릉', '길음', '종암', '월곡', '장위', '석관', '삼선', '동선동', '안암', '보문', '동소문'],
}
# 다른 지역 이름: 동네 이름 없이 이것만 나오면 동명 유치원으로 보고 뺀다
SEOUL_GU = ['강남', '강동', '강북', '강서', '관악', '광진', '구로', '금천', '노원', '도봉', '동대문', '동작', '마포',
            '서대문', '서초', '성동', '성북', '송파', '양천', '영등포', '용산', '은평', '종로', '중랑']
OTHER_CITY = ['부산', '대구', '인천', '광주', '대전', '울산', '세종', '수원', '성남', '분당', '고양', '일산', '용인', '부천',
              '안양', '남양주', '의정부', '김포', '평택', '화성', '파주', '청주', '천안', '전주', '창원', '제주', '포항', '구미']
AD = ['체험단', '원고료', '소정의', '협찬', '제공받', '지원받아', '#광고', '[광고]', '유료광고', '업체로부터', '파트너스']
# 학원·상품 홍보 글(유치원 이름이 '근처'로만 나오는 경우)
NOISE = ['학원', '공부방', '교습소', '부동산', '분양', '매매', '전세', '월세', '임장']

# 태그: 프로그램·운영 사실만. (표시 이름, [찾을 낱말])
TAGS = [
    ('숲·생태', ['숲체험', '숲놀이', '숲유치원', '숲반', '숲활동', '생태', '텃밭', '숲']),
    ('영어', ['영어', '원어민']),
    ('체육', ['체육', '축구', '수영', '줄넘기', '인라인', '발레']),
    ('미술', ['미술']),
    ('음악', ['음악', '악기', '바이올린', '오르프', '난타']),
    ('몬테소리', ['몬테소리']),
    ('레지오', ['레지오']),
    ('발도르프', ['발도르프']),
    ('놀이중심', ['놀이중심', '자유놀이', '바깥놀이', '놀이터']),
    ('과학·코딩', ['과학', '코딩', '로봇']),
    ('한글·수학', ['한글', '수학', '한자', '학습지']),
    ('종교', ['성당', '가톨릭', '천주교', '교회', '기독교', '불교']),
    ('방과후·돌봄', ['방과후', '에듀케어', '돌봄', '연장반', '종일반']),
    ('급식', ['급식', '식단', '간식', '친환경']),
    ('통학버스', ['통학버스', '차량']),
    ('행사', ['발표회', '운동회', '재롱잔치', '졸업식', '현장학습', '견학']),
    ('설명회 후기', ['입학설명회', '설명회']),
]


def variants(name):
    """블로그에서 쓰일 만한 이름 변형(공백 없는 형태)."""
    v = {name}
    if name.startswith('서울') and len(name) > 6:
        v.add(name[2:])  # 서울길음유치원 → 길음유치원
    for n in list(v):
        m = re.match(r'(.+)초등학교병설유치원$', n)
        if m:
            v |= {m[1] + '초병설유치원', m[1] + '초등학교유치원', m[1] + '초유치원', m[1] + '초병설'}
        if '여자대학교부속' in n:
            v |= {n.replace('여자대학교부속', '여대부속'), n.replace('여자대학교부속', '여대부설')}
        if n.endswith('분원'):
            v.add(n[:-2])
    return sorted(v, key=len, reverse=True)


def query_of(name):
    """검색어: 가장 흔히 쓰일 짧은 이름 + 구 이름."""
    base = name[2:] if name.startswith('서울') and len(name) > 6 else name
    m = re.match(r'(.+)초등학교병설유치원$', base)
    if m:
        return m[1] + '초 병설유치원'
    return base.replace('여자대학교부속', '여대부속')


def clean(s):
    return html.unescape(re.sub(r'<[^>]+>', '', s or ''))


def fetch(query, cid, secret, start=1):
    q = urllib.parse.urlencode({'query': query, 'display': 100, 'start': start, 'sort': 'sim'})
    req = urllib.request.Request(f'{URL}?{q}', headers={'X-Naver-Client-Id': cid, 'X-Naver-Client-Secret': secret})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError(f'인증 실패({e.code}): 네이버 Client ID/Secret과 "검색" API 사용 설정을 확인하세요.')
            if i == 2:
                raise
        except Exception:
            if i == 2:
                raise
        time.sleep(2 * (i + 1))


def judge(item, names, gu):
    """(남길지, 사유). 남기면 사유는 ''."""
    title, desc = clean(item.get('title')), clean(item.get('description'))
    text = title + ' ' + desc
    flat = re.sub(r'\s+', '', text)
    if not any(n in flat for n in names):
        return False, '이름 없음'
    if any(a in flat for a in AD):
        return False, '협찬·광고'
    d = item.get('postdate') or ''
    if len(d) == 8 and int(d[:4]) < MIN_YEAR:
        return False, '오래된 글'
    local = LOCAL.get(gu, [gu[:-1]])
    if not any(l in flat for l in local):
        others = [g for g in SEOUL_GU if g != gu[:-1]] + OTHER_CITY
        if any(o in flat for o in others):
            return False, '다른 지역'
    if any(w in title for w in NOISE):
        return False, '학원·부동산 글'
    return True, ''


def tag_counts(posts):
    c = Counter()
    for text in posts:
        flat = re.sub(r'\s+', '', text)
        for label, words in TAGS:
            if any(w in flat for w in words):
                c[label] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gu', default='성북구')
    ap.add_argument('--fixtures', help='{id}.json 응답 폴더로 오프라인 시험(결과 파일은 안 씀)')
    ap.add_argument('--raw', help='API 응답 원본 저장 폴더')
    a = ap.parse_args()

    kg = json.load(open(KG, encoding='utf-8'))
    ci = {c: i for i, c in enumerate(kg['cols'])}
    rows = [r for r in kg['rows'] if r[ci['구']] == a.gu]
    cid, secret = os.environ.get('NAVER_CLIENT_ID'), os.environ.get('NAVER_CLIENT_SECRET')
    if not a.fixtures and not (cid and secret):
        sys.exit('NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 환경변수가 필요합니다.')
    if a.raw:
        os.makedirs(a.raw, exist_ok=True)

    out, report = {}, [f'# 블로그 키워드 점검 — {a.gu} ({date.today()})\n',
                       '| 유치원 | 검색어 | 받은 글 | 남긴 글 | 제외(사유별) | 태그 |', '|---|---|---|---|---|---|']
    examples = []
    for r in rows:
        kid, name = r[ci['id']], r[ci['유치원명']]
        names = [re.sub(r'\s+', '', n) for n in variants(name)]
        q = f'{query_of(name)} {a.gu[:-1]}'
        if a.fixtures:
            p = os.path.join(a.fixtures, f'{kid}.json')
            items = json.load(open(p, encoding='utf-8')).get('items', []) if os.path.exists(p) else []
        else:
            res = fetch(q, cid, secret)
            items = res.get('items', [])
            if res.get('total', 0) > 100:  # 2쪽까지
                items += fetch(q, cid, secret, start=101).get('items', [])
            if a.raw:
                json.dump({'query': q, 'items': items}, open(os.path.join(a.raw, f'{kid}.json'), 'w', encoding='utf-8'),
                          ensure_ascii=False)
            time.sleep(0.15)

        kept, dropped, seen = [], Counter(), set()
        for it in items:
            link = it.get('link', '')
            if link in seen:
                continue
            seen.add(link)
            ok, why = judge(it, names, a.gu)
            if ok:
                kept.append(it)
            else:
                dropped[why] += 1
                if why in ('다른 지역', '학원·부동산 글', '협찬·광고') and len(examples) < 40:
                    examples.append(f'- {name} · {why} · {clean(it.get("title"))[:40]}')
        tags = tag_counts([clean(it.get('title')) + ' ' + clean(it.get('description')) for it in kept])
        years = sorted(int(it['postdate'][:4]) for it in kept if len(it.get('postdate') or '') == 8)
        kept.sort(key=lambda it: it.get('postdate') or '', reverse=True)
        if kept:
            out[str(kid)] = {
                'n': len(kept),
                'y': [years[0], years[-1]] if years else None,
                't': [[k, v] for k, v in tags.most_common() if v >= 2],
                'p': [[clean(it['title'])[:60], it['link'], it.get('postdate', '')] for it in kept[:5]],
            }
        drop_txt = ', '.join(f'{k} {v}' for k, v in dropped.most_common()) or '-'
        tag_txt = ', '.join(f'{k} {v}' for k, v in tags.most_common(6)) or '-'
        report.append(f'| {name} | {q} | {len(seen)} | {len(kept)} | {drop_txt} | {tag_txt} |')
        print(f'{name}: {len(kept)}/{len(seen)}  {tag_txt}')

    report += ['\n## 제외 예시 (잘못 뺐는지 확인)\n'] + examples
    found = sum(1 for v in out.values() if v['n'] > 0)
    print(f'\n{len(rows)}곳 중 {found}곳에 글 있음')
    if a.fixtures:
        print('(fixtures 모드: 파일 안 씀)')
        print('\n'.join(report))
        return
    json.dump({'basis': '네이버 블로그 검색 API 제목·요약문 기준, 최근 3년, 협찬·다른 지역 글 제외',
               'updated': str(date.today()), 'gu': a.gu, 'b': out},
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    open(REPORT, 'w', encoding='utf-8').write('\n'.join(report) + '\n')
    print(f'→ {OUT}\n→ {REPORT}')


if __name__ == '__main__':
    main()

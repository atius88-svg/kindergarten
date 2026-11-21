# 시험용: 어린이집 평가 화면·2주기 결과서 원문 받기
import os, re, sys, urllib.request
HOST = 'https://info.childcare.go.kr'
PRE = HOST + '/info_html5/pnis/search/preview/'
def get(u):
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'replace')
out = 'probe/out'; os.makedirs(out, exist_ok=True)
for st in ['11110000013', '11110000014', '11110000012']:
    p = get(PRE + f'AppraisaAuthenticationGradeSlPu.jsp?flag=PI&STCODE_POP={st}')
    open(f'{out}/{st}_eval.html', 'w').write(p)
    m = re.search(r"goTotalComment\('([^']*)',\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'\)", p)
    print(st, m.groups() if m else None)
    # 스크립트 파일도
    for js in set(re.findall(r'src="([^"]+\.js[^"]*)"', p)):
        if 'jquery' in js.lower(): continue
        u = js if js.startswith('http') else HOST + (js if js.startswith('/') else '/info_html5/pnis/search/preview/' + js)
        try:
            t = get(u)
            if 'goTotalComment' in t or 'Evl2nd' in t:
                open(f'{out}/js_{os.path.basename(js.split("?")[0])}', 'w').write(t)
        except Exception as e:
            print('js fail', u, e)
    if m:
        v = m.group(1)
        for name in ['totalGradeCommentEvl2nd.jsp', 'totalGradeComment.jsp']:
            for q in [f'flag=commnetGrade&childHouseId={v}', f'childHouseId={v}']:
                u = f'{HOST}/info_html5/cera/search/{name}?{q}'
                try:
                    t = get(u); open(f'{out}/{st}_{name}_{q.split("&")[0][:10]}.html', 'w').write(t); print('ok', len(t), u)
                except Exception as e:
                    print('fail', u, e)

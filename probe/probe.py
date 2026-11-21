# 시험용 2: evlIdxTy=01 붙여 2주기 결과서 받기
import os, urllib.request
HOST = 'https://info.childcare.go.kr'
def get(u):
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'replace')
os.makedirs('probe/out2', exist_ok=True)
for v in ['SE000088', 'SE000759']:
    t = get(f'{HOST}/info_html5/cera/search/totalGradeCommentEvl2nd.jsp?flag=commnetGrade&childHouseId={v}&evlIdxTy=01')
    open(f'probe/out2/{v}.html', 'w').write(t); print(v, len(t))

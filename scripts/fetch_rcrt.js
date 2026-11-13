// 유치원 모집요강(나이별 학급·정원) 수집 — 1년에 한 번(10월 말 모집요강 공개 뒤), PC 내장 브라우저에서 실행.
// 정부 사이트라 GitHub Actions에서는 못 돌린다. 결과 JSON을 scripts/build_rcrt.py에 넣어 src/data/kg_rcrt.json을 만든다.
//
// 1단계: https://enter.childinfo.go.kr/icms/main/TotalSearchSlPL.html 를 열고 STEP1을 붙여 넣는다.
//        (검색 API는 로그인 불필요. 페이지가 백그라운드면 setTimeout이 크게 늦어지므로 대기 없이 2개씩 돌린다.)
// 2단계: STEP1이 끝나면(S.done) 같은 탭에서 STEP2를 실행 → window.name에 목록을 담고 처음학교로 모집요강 화면으로 이동.
//        (처음학교로 주소를 직접 열면 '잘못된 접근' → 유보통합포털에서 넘어가야 열린다)
// 3단계: 처음학교로 탭에서 STEP3 실행 → progress()가 끝나면 OUTPUT을 실행해 결과를 저장.
//        selectPridInfo.do POST(DATA_YN=Y, CALL_ORIGIN=ENTER)는 같은 출처 요청이면 된다.

/* STEP1 — enter.childinfo.go.kr */
window.S = { list: [], done: false, err: [] };
(async () => {
  const H = { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest' };
  const base = $('#pagingForm').serializeArray().filter((x) => x.name);
  const mkBody = (o) => { const m = base.map((x) => [x.name, x.name in o ? o[x.name] : x.value]); const seen = new Set(m.map((x) => x[0])); for (const k in o) if (!seen.has(k)) m.push([k, o[k]]); return m.map(([a, b]) => a + '=' + encodeURIComponent(b)).join('&'); };
  const gl = (await (await fetch('/icms/nursery/NurseryMapGuGunList.html', { method: 'POST', headers: H, body: 'sidocode=11000' })).json()).guGunList;
  for (const g of gl) for (let pg = 1; pg < 40; pg++) {
    const j = await (await fetch('/icms/main/TotalSearchContentData.html', { method: 'POST', headers: H, body: mkBody({ ctprvn: '11000', ctprvnName: '서울특별시', signgu: g.ARCODE, signguName: g.ARNAME2, cname: '', pageNum: pg, searchDetailCrgb: '02' }) })).json();
    const L = (j.nurseryList || []).filter((x) => x.crgb === '02'); if (!L.length) break;
    for (const x of L) S.list.push({ st: x.stcode, nm: x.crname, gu: g.ARNAME2, type: x.crtypenm, addr: x.craddr });
  }
  const q = [...S.list];
  const worker = async () => { while (q.length) { const k = q.shift(); try { k.u = await (await fetch('/api/callFirstSchoolPridInfoApi.html', { method: 'POST', headers: H, body: 'STCODE=' + encodeURIComponent(k.st) })).text(); } catch (e) { S.err.push(k.st + e); } } };
  await Promise.all([worker(), worker()]);
  S.done = true;
})();

/* STEP2 — 같은 탭 */
window.KL = S.list.filter((x) => /PRESCH_CD=/.test(x.u || '')).map((x) => { const m = x.u.match(/PRESCH_CD=(\w+)&UPPER_EDU_OFFICE_CD=(\w+)&EDU_OFFICE_CD=(\w+)/); return [m[1], m[2], m[3], x.nm, x.gu, x.type, x.addr]; });
window.name = JSON.stringify(KL);
location.href = KL[0] && `https://www.go-firstschool.go.kr/PAMS_SS/selectPridInfo.do?PRESCH_CD=${KL[0][0]}&UPPER_EDU_OFFICE_CD=${KL[0][1]}&EDU_OFFICE_CD=${KL[0][2]}&AID_YEAR=2026&USER_ID=&FST_DFLT_GB=RC928_002&PARENT_YN=N&CODE=ISPOP`;

/* STEP3 — go-firstschool.go.kr */
window.KL = JSON.parse(window.name); window.R = {}; window.RE = [];
{
  const q = [...KL];
  const one = async (k) => {
    const body = new URLSearchParams({ PRESCH_CD: k[0], UPPER_EDU_OFFICE_CD: k[1], EDU_OFFICE_CD: k[2], PRESCH_FOUND_TYPE: '', FST_DFLT_GB: 'RC928_001', PARENT_YN: 'Y', CALL_ORIGIN: 'ENTER', USER_ID: '', DATA_YN: 'Y' });
    const t = await (await fetch('/PAMS_SS/selectPridInfo.do', { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' }, body })).text();
    const d = new DOMParser().parseFromString(t, 'text/html');
    const tb = [...d.querySelectorAll('table')].find((x) => /모집대상/.test(x.innerText) && /정원/.test(x.innerText));
    if (!tb) { RE.push([k[0], k[3], 'notable']); return; }
    R[k[0]] = [...tb.rows].map((r) => [...r.cells].map((c) => c.innerText.trim().replace(/\s+/g, ' '))).filter((c) => c.length >= 6);
  };
  const worker = async () => { while (q.length) { const k = q.shift(); try { await one(k); } catch (e) { RE.push([k[0], k[3], String(e)]); } } };
  window.progress = () => [Object.keys(R).length, RE.length, q.length];
  worker(); worker();
}

/* OUTPUT — 결과(약 250KB)를 저장해 scripts/build_rcrt.py 입력으로 */
JSON.stringify(KL.map((k) => [k[0], k[2], k[3], k[4], k[5], k[6], R[k[0]] || null]));

/* static/js/search.js */
document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("searchRoot");
  if (!root) return;

  // --- data-* endpoints ---
  const API         = root.dataset.api || "";            // /dev/search
  const FRAMES_TPL  = root.dataset.frames || "";         // /dev/frames/__FID__
  const FITS_TPL    = root.dataset.fits || "";           // /dev/fits/__FID__
  const PLACEHOLDER = root.dataset.placeholder || "";

  // --- elements ---
  const el = {
    q:       document.getElementById("q"),
    run:     document.getElementById("runSearch"),
    sortBy:  document.getElementById("sortBy"),
    table:   document.getElementById("resultsTable"),
    tbody:   document.getElementById("resultsBody"),
    empty:   document.getElementById("resultsEmpty"),
    summary: document.getElementById("summary"),
    instPills: document.getElementById("instPills"),
    flagPills: document.getElementById("flagPills"),
    // manual FROM
    yFrom:  document.getElementById("yFrom"),
    mFrom:  document.getElementById("mFrom"),
    dFrom:  document.getElementById("dFrom"),
    apFrom: document.getElementById("apFrom"),
    hhFrom: document.getElementById("hhFrom"),
    mmFrom: document.getElementById("mmFrom"),
    // manual TO
    yTo:  document.getElementById("yTo"),
    mTo:  document.getElementById("mTo"),
    dTo:  document.getElementById("dTo"),
    apTo: document.getElementById("apTo"),
    hhTo: document.getElementById("hhTo"),
    mmTo: document.getElementById("mmTo"),
    resetRange: document.getElementById("resetRange"),
  };

  // 상태 보관
  const framesMap = Object.create(null); // fid -> [{index,url,channel}]

  // ---------- utils ----------
  const pad2 = (n) => String(n).padStart(2, "0");
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
  const fmtLocal = (iso) => { try { return new Date(iso).toLocaleString(); } catch { return "-"; } };

  const getPills = (wrap) =>
    Array.from(wrap?.querySelectorAll(".filter-pill.active") || []).map(n => n.dataset.value);

  // 수동 입력 → "YYYY-MM-DD HH:MM:SS"
  function manualToString(kind/*"from"|"to"*/){
    const y  = parseInt(el[kind === "from" ? "yFrom"  : "yTo"]?.value || "", 10);
    const m  = parseInt(el[kind === "from" ? "mFrom"  : "mTo"]?.value || "", 10);
    const d  = parseInt(el[kind === "from" ? "dFrom"  : "dTo"]?.value || "", 10);
    const ap = (el[kind === "from" ? "apFrom" : "apTo"]?.value || "").toUpperCase();
    let hh   = el[kind === "from" ? "hhFrom" : "hhTo"]?.value;
    let mm   = el[kind === "from" ? "mmFrom" : "mmTo"]?.value;

    // 날짜 세 부분이 완성되지 않으면 미지정으로 간주
    if (!y || !m || !d) return null;

    // 시간/분이 비어 있으면 from=00:00, to=23:59:59 기본값
    let H24, M = 0, S = (kind === "from" ? 0 : 59);
    if (hh === "" || mm === "") {
      H24 = (kind === "from") ? 0 : 23;
      M   = (kind === "from") ? 0 : 59;
    } else {
      let hhNum = clamp(parseInt(hh, 10) || 0, 1, 12);  // 1~12
      let mmNum = clamp(parseInt(mm, 10) || 0, 0, 59);
      // AM/PM 변환
      if (ap === "PM" && hhNum < 12) hhNum += 12;
      if (ap === "AM" && hhNum === 12) hhNum = 0;
      H24 = clamp(hhNum, 0, 23);
      M   = mmNum;
      S   = 0;
    }

    const MMM = pad2(m), DD = pad2(d), HH = pad2(H24), MM = pad2(M), SS = pad2(S);
    return `${y}-${MMM}-${DD} ${HH}:${MM}:${SS}`;
  }

  // 퀵버튼 → 수동 입력란에 세팅
  function setManualFromDate(date){
    // date는 local Date 객체
    const y = date.getFullYear();
    let m = date.getMonth() + 1;
    let d = date.getDate();
    let h = date.getHours();
    const mm = date.getMinutes();
    const ap = (h >= 12) ? "PM" : "AM";
    let h12 = h % 12; if (h12 === 0) h12 = 12;

    if (el.yFrom) el.yFrom.value = y;
    if (el.mFrom) el.mFrom.value = m;
    if (el.dFrom) el.dFrom.value = d;
    if (el.apFrom) el.apFrom.value = ap;
    if (el.hhFrom) el.hhFrom.value = h12;
    if (el.mmFrom) el.mmFrom.value = pad2(mm);
  }
  function setManualToDate(date){
    const y = date.getFullYear();
    let m = date.getMonth() + 1;
    let d = date.getDate();
    let h = date.getHours();
    const mm = date.getMinutes();
    const ap = (h >= 12) ? "PM" : "AM";
    let h12 = h % 12; if (h12 === 0) h12 = 12;

    if (el.yTo) el.yTo.value = y;
    if (el.mTo) el.mTo.value = m;
    if (el.dTo) el.dTo.value = d;
    if (el.apTo) el.apTo.value = ap;
    if (el.hhTo) el.hhTo.value = h12;
    if (el.mmTo) el.mmTo.value = pad2(mm);
  }

  // ---------- 초기값: 최근 24시간 ----------
  (function initManualRange(){
    const now = new Date();
    const from = new Date(now.getTime() - 24*3600*1000);
    setManualFromDate(from);
    setManualToDate(now);
  })();

  // ---------- 퀵 버튼 ----------
  document.querySelectorAll("[data-quick]").forEach(btn => {
    btn.addEventListener("click", () => {
      const k = btn.dataset.quick;
      const now = new Date();
      if (k === "6h" || k === "12h" || k === "24h") {
        const hours = parseInt(k, 10);
        const from = new Date(now.getTime() - hours*3600*1000);
        setManualFromDate(from);
        setManualToDate(now);
      } else if (k === "today") {
        const start = new Date(); start.setHours(0,0,0,0);
        setManualFromDate(start);
        setManualToDate(now);
      } else if (k === "yesterday") {
        const d = new Date(); d.setDate(d.getDate()-1); d.setHours(0,0,0,0);
        const e = new Date(d); e.setHours(23,59,59,0);
        setManualFromDate(d);
        setManualToDate(e);
      }
    });
  });
  el.resetRange?.addEventListener("click", () => {
    ["yFrom","mFrom","dFrom","apFrom","hhFrom","mmFrom","yTo","mTo","dTo","apTo","hhTo","mmTo"].forEach(id=>{
      const n = document.getElementById(id);
      if (n) n.value = "";
    });
  });

  // ---------- pill toggle ----------
  ;[el.instPills, el.flagPills].forEach(wrap => {
    wrap?.addEventListener("click", (e) => {
      const p = e.target.closest(".filter-pill");
      if (!p) return;
      p.classList.toggle("active");
    });
  });

  // ---------- build params ----------
  function buildParams() {
    const p = new URLSearchParams();
    const q = el.q?.value.trim(); if (q) p.set("q", q);

    const fromStr = manualToString("from");
    const toStr   = manualToString("to");
    if (fromStr) p.set("date_from", fromStr);
    if (toStr)   p.set("date_to",   toStr);

    const s = el.sortBy?.value; if (s) p.set("sort", s);

    const inst = getPills(el.instPills); if (inst.length) p.set("instrument", inst.join(","));
    const flags= getPills(el.flagPills); if (flags.length) p.set("flags", flags.join(","));

    const exMin = document.getElementById("expMin")?.value;
    const exMax = document.getElementById("expMax")?.value;
    const frMin = document.getElementById("framesMin")?.value;
    const frMax = document.getElementById("framesMax")?.value;
    if (exMin) p.set("exp_min", exMin); if (exMax) p.set("exp_max", exMax);
    if (frMin) p.set("frames_min", frMin); if (frMax) p.set("frames_max", frMax);

    return p;
  }

  document.getElementById("searchForm")?.addEventListener("submit" , (e) => {
    e.preventDefault();
    search();
  });
  // ---------- render table + detail ----------
  function render(items) {
    const tbody = el.tbody, table = el.table, empty = el.empty;
    if (!tbody || !table || !empty) return;

    tbody.innerHTML = "";

    if (!items?.length) {
      table.classList.add("d-none");
      empty.classList.remove("d-none");
      return;
    }
    empty.classList.add("d-none");
    table.classList.remove("d-none");

    items.forEach((it) => {
      const fid = it.file_id;
      const detailId = `detail_${fid}`;
      const noFits = (it.flags || []).includes("no_fits");
      const fitsHref = FITS_TPL ? FITS_TPL.replace("__FID__", fid) : "#";

      // row
      const tr = document.createElement("tr");
      tr.className = "result-row";
      tr.dataset.fid = fid;
      tr.setAttribute("data-bs-toggle", "collapse");
      tr.setAttribute("data-bs-target", `#${detailId}`);
      tr.innerHTML = `
        <td><img class="thumb" src="${it.thumb_url || PLACEHOLDER}" alt="thumb"></td>
        <td>
          <div><strong>${it.target || it.filename || "(무제)"}</strong></div>
          <div class="meta-sub">${it.filename || ""}</div>
        </td>
        <td>${it.date_obs ? fmtLocal(it.date_obs) : "-"}</td>
        <td>${it.exptime ?? "-"}</td>
        <td>${it.frames ?? "-"}</td>
        <td>${it.instrument ?? "-"}</td>
        <td>
          <div class="d-flex gap-2">
            <button class="btn btn-sm btn-outline-primary" data-action="timeline" data-fid="${fid}">타임라인</button>
          </div>
        </td>
      `;

      // detail row
      const trDetail = document.createElement("tr");
      trDetail.className = "detail-row";
      const td = document.createElement("td");
      td.colSpan = 7;
      td.innerHTML = `
        <div id="${detailId}" class="collapse" data-loaded="0">
          <div class="detail-inner">
            <div class="detail-grid">
              <div class="detail-preview">
                <img alt="preview" src="${it.thumb_url || PLACEHOLDER}">
              </div>
              <div>
                <dl class="detail-meta">
                  <div><dt>원본 파일</dt><dd>${it.filename || "-"} ${noFits ? '<span class="badge text-bg-warning ms-2">FITS 없음</span>' : ''}</dd></div>
                  <div><dt>관측시각</dt><dd>${it.date_obs ? fmtLocal(it.date_obs) : "-"}</dd></div>
                  <div><dt>노출시간</dt><dd>${it.exptime ?? "-"}</dd></div>
                  <div><dt>프레임</dt><dd>${it.frames ?? "-"}</dd></div>
                  <div><dt>장비</dt><dd>${it.instrument ?? "-"}</dd></div>
                </dl>

                <div class="detail-actions d-flex flex-wrap gap-2">
                  <button class="btn btn-primary btn-sm" data-action="timeline" data-fid="${fid}">타임라인</button>
                  <a ${noFits ? 'class="btn btn-secondary btn-sm disabled" aria-disabled="true" tabindex="-1" href="#"' : `class="btn btn-secondary btn-sm" target="_blank" href="${fitsHref}"`}>FITS 열기</a>
                </div>
              </div>
            </div>
          </div>
        </div>
      `;
      trDetail.appendChild(td);

      el.tbody.appendChild(tr);
      el.tbody.appendChild(trDetail);

      // 펼칠 때 첫 프레임 lazy 로드
      const collapsible = td.querySelector(`#${detailId}`);
      collapsible?.addEventListener("show.bs.collapse", async () => {
        if (collapsible.getAttribute("data-loaded") === "1") return;
        collapsible.setAttribute("data-loaded", "1");
        try {
          if (!FRAMES_TPL) return;
          const res = await fetch(FRAMES_TPL.replace("__FID__", fid));
          const data = await res.json();
          framesMap[fid] = data.items || [];
          const first = framesMap[fid][0];
          const img = collapsible.querySelector(".detail-preview img");
          if (first && img) img.src = first.url;
        } catch (e) { console.warn("frames fetch failed", e); }
      });
    });
  }

  // ---------- search ----------
  async function search() {
    if (!API) return;
    try {
      const res = await fetch(`${API}?${buildParams().toString()}`);
      const data = await res.json();
      if (el.summary) el.summary.textContent = `${data.total || 0}건`;
      render(data.items || []);
    } catch (e) {
      console.error(e);
      if (el.summary) el.summary.textContent = "검색 실패";
      render([]);
    }
  }

  // ---------- timeline modal ----------
  ;(function setupTimeline(){
    const modalEl      = document.getElementById("frameViewer");
    if (!modalEl) return;

    const frameImg     = document.getElementById("frameImage");
    const frameSlider  = document.getElementById("frameSlider");
    const framePos     = document.getElementById("framePos");
    const frameTotal   = document.getElementById("frameTotal");
    const frameChannel = document.getElementById("frameChannel");
    const btnPlay      = document.getElementById("btnPlay");
    const btnPause     = document.getElementById("btnPause");
    const playFps      = document.getElementById("playFps");

    let frames = [];
    let timer  = null;

    const bsModal = window.bootstrap?.Modal ? new window.bootstrap.Modal(modalEl) : null;

    function stop(){ if (timer) { clearInterval(timer); timer = null; } }

    function showFrame(i){
      if (!frames.length) return;
      const idx = Math.max(0, Math.min(i, frames.length-1));
      if (frameImg) frameImg.src = frames[idx].url;
      if (frameSlider) frameSlider.value = String(idx);
      if (framePos) framePos.textContent = String(idx + 1);
      if (frameChannel) frameChannel.textContent = frames[idx].channel || "-";
    }

    function play(){
      stop();
      const fps = parseInt(playFps?.value || "6", 10) || 6;
      if (!frames.length || !frameSlider) return;
      timer = setInterval(() => {
        let i = (parseInt(frameSlider.value || "0", 10) || 0) + 1;
        if (i >= frames.length) i = 0;
        showFrame(i);
      }, Math.max(10, Math.floor(1000 / fps)));
    }

    frameSlider?.addEventListener("input", () => {
      const i = parseInt(frameSlider.value || "0", 10) || 0;
      showFrame(i);
    });

    btnPlay?.addEventListener("click", play);
    btnPause?.addEventListener("click", stop);
    playFps?.addEventListener("change", () => { if (timer) play(); });

    // 외부에서 호출
    window.openTimelineFor = async (fid) => {
      try {
        if (!FRAMES_TPL) return alert("프레임 API 미설정");
        const res = await fetch(FRAMES_TPL.replace("__FID__", fid));
        const data = await res.json();
        frames = data.items || [];
        if (!frames.length) return alert("프레임 이미지가 없습니다.");

        if (frameTotal) frameTotal.textContent = String(frames.length);
        if (frameSlider) {
          frameSlider.min = "0";
          frameSlider.max = String(Math.max(0, frames.length-1));
          frameSlider.value = "0";
        }
        showFrame(0);
        if (bsModal) bsModal.show(); else modalEl.style.display = "block";
        play(); // 자동 재생
      } catch (e) {
        console.error(e);
        alert("프레임 로드 실패");
      }
    };

    modalEl.addEventListener("hidden.bs.modal", stop);
  })();

  // ---------- table delegated actions (버블링 차단) ----------
  el.tbody?.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    if (typeof e.stopImmediatePropagation === "function") e.stopImmediatePropagation();

    const fid = btn.dataset.fid;
    const act = btn.dataset.action;

    if (act === "timeline") {
      if (typeof window.openTimelineFor === "function") {
        window.openTimelineFor(fid);
      }
    }
  });
  // ---------- bind + first search ----------
  el.run?.addEventListener("click", search);
  el.sortBy?.addEventListener("change", search);
  search();
});

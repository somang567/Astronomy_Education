const API_BASE = "/fits";
const $ = (id) => document.getElementById(id);

const els = {
  uploadBtn: $("upload-button"),
  fileInput: $("file-input"),
  fitsContainer: $("fits-image-container"),
  slitContainer: $("slit-image-container"),
  spectrumContainer: $("spectrum-plot-container"),
  fileNameEl: $("current-filename"),
  headerMetaEl: $("header-metadata"),
  pixelEl: $("current-pixel-coords"),
  statusEl: $("current-status"),
  // 슬라이스 / 보정
  zWrap: $("z-slider-wrap"),
  zSlider: $("z-slider"),
  zValue: $("z-value"),
  clipToggle: $("clip-toggle"),
};

const G = {
  fileId: null,
  spectrumChart: null,
  lastX: null,
  lastY: null,
  currentZ: 0,
};

function status(s){ if(els.statusEl) els.statusEl.textContent = s; }

document.addEventListener("DOMContentLoaded", () => {
  els.uploadBtn?.addEventListener("click", () => els.fileInput?.click());
  els.fileInput?.addEventListener("change", onFileChosen);

  // z 슬라이더: preview만 갱신 (슬릿/스펙트럼은 전체 z 사용)
  els.zSlider?.addEventListener("input", async (e) => {
    G.currentZ = Number(e.target.value);
    els.zValue.textContent = String(G.currentZ);
    await refreshPreview();
  });

  // 보정 토글: preview/슬릿/스펙트럼 모두 반영
  els.clipToggle?.addEventListener("change", async () => {
    await refreshPreview();
    if(Number.isInteger(G.lastX) && Number.isInteger(G.lastY)){
      await drawSlitAndSpectrum(G.lastX, G.lastY);
    }
  });

  status("준비 완료");
});

function correctionParam(){
  return `apply_correction=${els.clipToggle.checked ? "true" : "false"}`;
}

async function onFileChosen(e){
  const file = e.target.files?.[0]; if(!file) return;
  status("업로드 중...");
  const formData = new FormData(); formData.append("file", file);
  const r = await fetch(`${API_BASE}/upload`, { method: "POST", body: formData });
  const out = await r.json();
  if(!r.ok){ status(out.error || "업로드 실패"); return; }

  G.fileId = out.file_id;
  els.fileNameEl.textContent = out.filename;
  els.headerMetaEl.textContent = `shape=${out.shape} | DATE-OBS=${out.header?.["DATE-OBS"] ?? "-"}`;

  // z 슬라이더 노출/초기화
  if (out.shape && out.shape.length === 3) {
    els.zWrap.style.display = "";
    els.zSlider.max = out.shape[0] - 1;
    els.zSlider.value = "0";
    els.zValue.textContent = "0";
    G.currentZ = 0;
  } else {
    els.zWrap.style.display = "none";
  }

  setFitsPreview(out.preview_png);
  status("업로드 성공");
}

async function refreshPreview(){
  if(!G.fileId) return;
  const params = new URLSearchParams({
    file_id: G.fileId,
    z: String(G.currentZ),
    percent_clip: els.clipToggle.checked ? "1.0" : "0.0",
    apply_correction: els.clipToggle.checked ? "true" : "false",
  });
  const r = await fetch(`${API_BASE}/preview?${params.toString()}`);
  const out = await r.json();
  if(!r.ok){ status(out.error || "프리뷰 실패"); return; }
  setFitsPreview(out.preview_png);

  // 좌표 선택되어 있었으면 슬릿/스펙트럼도 최신 보정 상태로 다시 그림
  if(Number.isInteger(G.lastX) && Number.isInteger(G.lastY)){
    await drawSlitAndSpectrum(G.lastX, G.lastY);
  }
}

function setFitsPreview(dataUrl){
  els.fitsContainer.innerHTML = `
    <div class="plot-box">
      <img id="fits-img" src="${dataUrl}" alt="FITS">
      <div class="axis-x">X (pix)</div>
      <div class="axis-y">Y (pix)</div>
    </div>`;
  $("fits-img").addEventListener("click", onFitsClick);
}

async function onFitsClick(e){
  if(!G.fileId) return;
  const img = e.currentTarget, rect = img.getBoundingClientRect();
  const u=(e.clientX-rect.left)/rect.width, v=(e.clientY-rect.top)/rect.height;
  if(u<0||u>1||v<0||v>1) return;
  // naturalWidth/Height가 없는 환경이면 rect 사용 (fallback)
  const natW = img.naturalWidth || rect.width;
  const natH = img.naturalHeight || rect.height;
  const x = Math.round(u * natW), y = Math.round(v * natH);
  G.lastX=x; G.lastY=y; els.pixelEl.textContent = `x:${x}, y:${y}`;
  await drawSlitAndSpectrum(x, y);
}

async function drawSlitAndSpectrum(x, y){
  status("슬릿 처리 중...");
  let r = await fetch(
    `${API_BASE}/slit?file_id=${G.fileId}&x=${x}&percent_clip=${els.clipToggle.checked ? "1.0" : "0.0"}&${correctionParam()}`
  );
  let out = await r.json();
  if(!r.ok){ status(out.error || "슬릿 실패"); return; }
  // Slit: 축 라벨 포함
  els.slitContainer.innerHTML = `
    <div class="plot-box">
      <img src="${out.slit_png}" alt="Slit (Y vs λ)">
      <div class="axis-x">Wavelength (pix)</div>
      <div class="axis-y">Y (pix)</div>
    </div>`;

  status("스펙트럼 추출 중...");
  r = await fetch(`${API_BASE}/spectrum?file_id=${G.fileId}&x=${x}&y=${y}&${correctionParam()}`);
  out = await r.json();
  if(!r.ok){ status(out.error || "스펙트럼 실패"); return; }
  renderSpectrum(out.wavelength, out.intensity);
  status("완료");
}

function renderSpectrum(wavelength, intensity){
  els.spectrumContainer.innerHTML = `<canvas id="spectrum-canvas"></canvas>`;
  const ctx = document.getElementById("spectrum-canvas").getContext("2d");
  if(G.spectrumChart){ G.spectrumChart.destroy(); G.spectrumChart=null; }
  // eslint-disable-next-line no-undef
  G.spectrumChart = new Chart(ctx, {
    type: "line",
    data: { labels: wavelength, datasets: [{ label: "Intensity", data: intensity, pointRadius: 0, borderWidth: 1, tension: 0 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        x: { title: { display: true, text: "Wavelength (pix)" } },
        y: { title: { display: true, text: "Counts" } }
      },
      plugins: { legend: { display: false } },
    }
  });
}

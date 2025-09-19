// static/js/mainViewer.js
(function () {
  const API_BASE = "/fits";
  const $ = (id) => document.getElementById(id);

  const fitsCanvas = $("fitsCanvas");
  const slitCanvas = $("slitCanvas");
  const spectrumCanvas = $("spectrumCanvas");

  const fileNameEl = $("fitsFileName");     // 상단 메타(옵션)
  const headerMetaEl = $("fitsMeta");
  const pixelEl = $("px") && $("py") ? { x: $("px"), y: $("py") } : null;

  // ✅ 보정과 무관하게 항상 동일한 스트레칭을 쓰도록 고정
  //    (원하면 UI로 따로 빼서 제어 가능)
  const PERCENT_CLIP = "1.0";

  // 전역 상태
  window.G = window.G || {
    fileId: null,
    spectrumChart: null,
    lastX: null,
    lastY: null,
    currentZ: 0,
  };

  // 현재 프리뷰 드로잉 상태(좌표 변환용)
  const fitDraw = { drawX: 0, drawY: 0, drawW: 0, drawH: 0, natW: 0, natH: 0 };

  // 부모 크기에 맞게 캔버스 픽셀 크기 설정 (DPR 안전)
  function sizeToParent(canvas) {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    // CSS 크기 명시
    canvas.style.width  = rect.width  + "px";
    canvas.style.height = rect.height + "px";
    // 실제 캔버스 버퍼 크기
    canvas.width  = Math.max(1, Math.round(rect.width  * dpr));
    canvas.height = Math.max(1, Math.round(rect.height * dpr));
    const ctx = canvas.getContext("2d");
    // 이후 좌표는 CSS px 기준
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  [fitsCanvas, slitCanvas, spectrumCanvas].forEach(sizeToParent);
  window.addEventListener("resize", () => {
    [fitsCanvas, slitCanvas, spectrumCanvas].forEach(sizeToParent);
    if (G._lastPreview) drawFitsPreview(G._lastPreview);
    if (G._lastSlit) drawImageToCanvas(G._lastSlit, slitCanvas);
    if (G._lastSpec) renderSpectrum(G._lastSpec.wavelength, G._lastSpec.intensity);
  });

  // ========= 서버 통신 =========
  async function fetchJSON(url) {
    const r = await fetch(url);
    const out = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(out.error || `HTTP ${r.status}`);
    return out;
  }

  // 헤더에서 호출할 수 있도록 전역 공개
  window.setFitsPreview = function setFitsPreview(dataUrl) {
    G._lastPreview = dataUrl;
    drawFitsPreview(dataUrl);
  };

  window.refreshPreview = async function refreshPreview() {
    if (!G.fileId) return;
    // ✅ 보정 여부만 토글 / 스트레칭은 고정
    const correctionOn = !!window.HeaderControls?.clipOn;

    const params = new URLSearchParams({
      file_id: G.fileId,
      z: String(G.currentZ),
      percent_clip: PERCENT_CLIP,
      apply_correction: correctionOn ? "true" : "false",
    });
    const out = await fetchJSON(`${API_BASE}/preview?${params.toString()}`);
    window.setFitsPreview(out.preview_png);

    if (Number.isInteger(G.lastX) && Number.isInteger(G.lastY)) {
      await window.drawSlitAndSpectrum(G.lastX, G.lastY);
    }
  };

  window.drawSlitAndSpectrum = async function drawSlitAndSpectrum(x, y) {
    const correctionOn = !!window.HeaderControls?.clipOn;

    // 슬릿
    let out = await fetchJSON(
      `${API_BASE}/slit?file_id=${G.fileId}&x=${x}&percent_clip=${PERCENT_CLIP}&apply_correction=${correctionOn ? "true" : "false"}`
    );
    G._lastSlit = out.slit_png;
    drawImageToCanvas(out.slit_png, slitCanvas);

    // 스펙트럼
    out = await fetchJSON(
      `${API_BASE}/spectrum?file_id=${G.fileId}&x=${x}&y=${y}&apply_correction=${correctionOn ? "true" : "false"}`
    );
    G._lastSpec = { wavelength: out.wavelength, intensity: out.intensity };
    renderSpectrum(out.wavelength, out.intensity);
  };

  // ========= 그리기 유틸 =========
  function drawFitsPreview(dataUrl) {
    const ctx = fitsCanvas.getContext("2d");
    const { width: contW, height: contH } = fitsCanvas.getBoundingClientRect();
    ctx.clearRect(0, 0, contW, contH);

    const img = new Image();
    img.onload = () => {
      const { width: contW2, height: contH2 } = fitsCanvas.getBoundingClientRect();
      const natW = img.naturalWidth || img.width;
      const natH = img.naturalHeight || img.height;
      const imgAR = natW / natH;
      const contAR = contW2 / contH2;

      let drawW, drawH, drawX, drawY;
      if (contAR > imgAR) {
        drawH = contH2;
        drawW = Math.floor(drawH * imgAR);
        drawX = Math.floor((contW2 - drawW) / 2);
        drawY = 0;
      } else {
        drawW = contW2;
        drawH = Math.floor(drawW / imgAR);
        drawX = 0;
        drawY = Math.floor((contH2 - drawH) / 2);
      }
      ctx.drawImage(img, drawX, drawY, drawW, drawH);

      Object.assign(fitDraw, { drawX, drawY, drawW, drawH, natW, natH });

      if (!fitsCanvas._clickBound) {
        fitsCanvas.addEventListener("click", onFitsClick);
        fitsCanvas._clickBound = true;
      }

      if (Number.isInteger(G.lastX) && Number.isInteger(G.lastY)) {
        drawMarkerAtDataXY(G.lastX, G.lastY);
      }
    };
    img.src = dataUrl;
  }

  function drawImageToCanvas(dataUrl, canvas) {
    const ctx = canvas.getContext("2d");
    const { width: contW, height: contH } = canvas.getBoundingClientRect();
    ctx.clearRect(0, 0, contW, contH);
    const img = new Image();
    img.onload = () => {
      const { width: cw, height: ch } = canvas.getBoundingClientRect();
      const natW = img.naturalWidth || img.width;
      const natH = img.naturalHeight || img.height;
      const imgAR = natW / natH, contAR = cw / ch;
      let w, h, x, y;
      if (contAR > imgAR) { h = ch; w = Math.floor(h * imgAR); x = Math.floor((cw - w)/2); y = 0; }
      else { w = cw; h = Math.floor(w / imgAR); x = 0; y = Math.floor((ch - h)/2); }
      ctx.drawImage(img, x, y, w, h);
    };
    img.src = dataUrl;
  }

  function drawMarkerAtDataXY(x, y) {
    if (!fitDraw.drawW || !fitDraw.drawH) return;
    const u = x / fitDraw.natW;
    const v = y / fitDraw.natH;
    const cx = fitDraw.drawX + u * fitDraw.drawW;
    const cy = fitDraw.drawY + v * fitDraw.drawH;

    const ctx = fitsCanvas.getContext("2d");
    ctx.save();
    ctx.strokeStyle = "rgba(255,0,0,0.9)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, 6, 0, Math.PI * 2);
    ctx.moveTo(cx - 8, cy); ctx.lineTo(cx + 8, cy);
    ctx.moveTo(cx, cy - 8); ctx.lineTo(cx, cy + 8);
    ctx.stroke();
    ctx.restore();
  }

  function onFitsClick(e) {
    if (!G.fileId) return;
    const rect = fitsCanvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    const { drawX, drawY, drawW, drawH, natW, natH } = fitDraw;
    if (sx < drawX || sx > drawX + drawW || sy < drawY || sy > drawY + drawH) return;

    const u = (sx - drawX) / drawW;
    const v = (sy - drawY) / drawH;

    const x = Math.round(u * natW);
    const y = Math.round(v * natH);
    G.lastX = x; G.lastY = y;

    if (pixelEl) { pixelEl.x.textContent = String(x); pixelEl.y.textContent = String(y); }

    if (G._lastPreview) drawFitsPreview(G._lastPreview);
    drawMarkerAtDataXY(x, y);

    window.drawSlitAndSpectrum(x, y);
  }

  function renderSpectrum(wavelength, intensity) {
    const ctx = spectrumCanvas.getContext("2d");
    if (G.spectrumChart) { G.spectrumChart.destroy(); G.spectrumChart = null; }
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

  window.renderSpectrum = renderSpectrum;
})();

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

  // 부모 크기에 맞게 캔버스 픽셀 크기 설정
  function sizeToParent(canvas) {
    const rect = canvas.getBoundingClientRect();
    // DPR 고려
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(rect.width * dpr));
    canvas.height = Math.max(1, Math.round(rect.height * dpr));
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); // CSS 픽셀 좌표계로 맞춤
  }

  [fitsCanvas, slitCanvas, spectrumCanvas].forEach(sizeToParent);
  window.addEventListener("resize", () => {
    [fitsCanvas, slitCanvas, spectrumCanvas].forEach(sizeToParent);
    // 리사이즈 시 프리뷰/슬릿 재도장 (이미지 캐시가 있다면 재사용)
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
    const clip = !!window.HeaderControls?.clipOn;
    const params = new URLSearchParams({
      file_id: G.fileId,
      z: String(G.currentZ),
      percent_clip: clip ? "1.0" : "0.0",
      apply_correction: clip ? "true" : "false",
    });
    const out = await fetchJSON(`${API_BASE}/preview?${params.toString()}`);
    window.setFitsPreview(out.preview_png);

    if (Number.isInteger(G.lastX) && Number.isInteger(G.lastY)) {
      await window.drawSlitAndSpectrum(G.lastX, G.lastY);
    }
  };

  window.drawSlitAndSpectrum = async function drawSlitAndSpectrum(x, y) {
    const clip = !!window.HeaderControls?.clipOn;

    // 슬릿
    let out = await fetchJSON(
      `${API_BASE}/slit?file_id=${G.fileId}&x=${x}&percent_clip=${clip ? "1.0" : "0.0"}&apply_correction=${clip ? "true" : "false"}`
    );
    G._lastSlit = out.slit_png;
    drawImageToCanvas(out.slit_png, slitCanvas);

    // 스펙트럼
    out = await fetchJSON(
      `${API_BASE}/spectrum?file_id=${G.fileId}&x=${x}&y=${y}&apply_correction=${clip ? "true" : "false"}`
    );
    G._lastSpec = { wavelength: out.wavelength, intensity: out.intensity };
    renderSpectrum(out.wavelength, out.intensity);
  };

  // ========= 그리기 유틸 =========
  function drawFitsPreview(dataUrl) {
    const ctx = fitsCanvas.getContext("2d");
    ctx.clearRect(0, 0, fitsCanvas.width, fitsCanvas.height);

    const img = new Image();
    img.onload = () => {
      // object-fit: contain
      const contW = fitsCanvas.width;
      const contH = fitsCanvas.height;
      const natW = img.naturalWidth || img.width;
      const natH = img.naturalHeight || img.height;
      const imgAR = natW / natH;
      const contAR = contW / contH;

      let drawW, drawH, drawX, drawY;
      if (contAR > imgAR) {
        drawH = contH;
        drawW = Math.floor(drawH * imgAR);
        drawX = Math.floor((contW - drawW) / 2);
        drawY = 0;
      } else {
        drawW = contW;
        drawH = Math.floor(drawW / imgAR);
        drawX = 0;
        drawY = Math.floor((contH - drawH) / 2);
      }
      ctx.drawImage(img, drawX, drawY, drawW, drawH);

      // 저장(좌표 변환에 필요)
      Object.assign(fitDraw, { drawX, drawY, drawW, drawH, natW, natH });

      // 클릭 이벤트 1회만 바인딩
      if (!fitsCanvas._clickBound) {
        fitsCanvas.addEventListener("click", onFitsClick);
        fitsCanvas._clickBound = true;
      }

      // 마지막 클릭 마커 다시 그리기
      if (Number.isInteger(G.lastX) && Number.isInteger(G.lastY)) {
        drawMarkerAtDataXY(G.lastX, G.lastY);
      }
    };
    img.src = dataUrl;
  }

  function drawImageToCanvas(dataUrl, canvas) {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const img = new Image();
    img.onload = () => {
      const contW = canvas.width, contH = canvas.height;
      const natW = img.naturalWidth || img.width;
      const natH = img.naturalHeight || img.height;
      const imgAR = natW / natH, contAR = contW / contH;
      let w, h, x, y;
      if (contAR > imgAR) { h = contH; w = Math.floor(h * imgAR); x = Math.floor((contW - w)/2); y = 0; }
      else { w = contW; h = Math.floor(w / imgAR); x = 0; y = Math.floor((contH - h)/2); }
      ctx.drawImage(img, x, y, w, h);
    };
    img.src = dataUrl;
  }

  // 데이터 좌표(x,y)를 현재 도장 상태에 맞게 표시
  function drawMarkerAtDataXY(x, y) {
    if (!fitDraw.drawW || !fitDraw.drawH) return;
    const u = x / fitDraw.natW;
    const v = y / fitDraw.natH;
    const cx = fitDraw.drawX + u * fitDraw.drawW;
    const cy = fitDraw.drawY + v * fitDraw.drawH;

    const ctx = fitsCanvas.getContext("2d");
    // 마커는 프리뷰 위에 다시 그림 (간단한 십자 표시)
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

  // 캔버스 클릭 -> (x,y) 산출
  function onFitsClick(e) {
    if (!G.fileId) return;
    const rect = fitsCanvas.getBoundingClientRect();
    // CSS px -> 캔버스 좌표 (DPR 고려 setTransform 덕에 1:1)
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    const { drawX, drawY, drawW, drawH, natW, natH } = fitDraw;
    if (sx < drawX || sx > drawX + drawW || sy < drawY || sy > drawY + drawH) return;

    const u = (sx - drawX) / drawW;
    const v = (sy - drawY) / drawH;

    const x = Math.round(u * natW);
    const y = Math.round(v * natH);
    G.lastX = x; G.lastY = y;

    // 메타 텍스트 갱신(있는 경우)
    if (pixelEl) { pixelEl.x.textContent = String(x); pixelEl.y.textContent = String(y); }

    // 이미지 다시 그리고 마커 표시
    if (G._lastPreview) drawFitsPreview(G._lastPreview);
    drawMarkerAtDataXY(x, y);

    // 슬릿/스펙트럼
    window.drawSlitAndSpectrum(x, y);
  }

  // 스펙트럼 그리기
  function renderSpectrum(wavelength, intensity) {
    const ctx = spectrumCanvas.getContext("2d");
    // Chart.js는 자체 캔버스 상태 사용—크기만 유지
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

  // 전역 노출 (헤더에서 호출)
  window.renderSpectrum = renderSpectrum;

  // 초기 사이즈 세팅(이미 함) + 초기화 끝
})();

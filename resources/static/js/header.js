// headerControls.js — 헤더(업로드/보정/슬라이스/상태)만 담당
(function (global) {
    const API_BASE = global.API_BASE || "/fits";
    const $ = (id) => document.getElementById(id);
  
    // 헤더 DOM (header.html의 ID와 1:1 매칭)
    const els = {
      fileInput: $("fileInput"),
      btnClipOn: $("btnClipOn"),
      btnClipOff: $("btnClipOff"),
      sliceIndex: $("sliceIndex"),
      statusEl: $("statusBadge"),
      // 페이지 상단 메타(있으면 갱신)
      fileNameEl: $("current-filename"),
      headerMetaEl: $("header-metadata"),
    };
  
    // 내부 상태: 보정 ON/OFF (기본 OFF: btnClipOff가 active)
    let clipOn = false;
  
    // 상태 배지
    function setStatus(text, level = "success") {
      if (!els.statusEl) return;
      els.statusEl.textContent = text;
      const base = "badge ";
      const map = {
        success: "bg-success-subtle text-success border border-success-subtle",
        warning: "bg-warning-subtle text-warning border border-warning-subtle",
        danger:  "bg-danger-subtle text-danger border border-danger-subtle",
      };
      els.statusEl.className = base + (map[level] || map.success);
    }
  
    // 버튼 active 토글
    function updateClipButtons() {
      els.btnClipOn?.classList.toggle("active", clipOn);
      els.btnClipOff?.classList.toggle("active", !clipOn);
      els.btnClipOn?.setAttribute("aria-pressed", String(clipOn));
      els.btnClipOff?.setAttribute("aria-pressed", String(!clipOn));
    }
  
    // 전역 호환: mainViewer 등에서 사용
    function correctionParam() {
      return `apply_correction=${clipOn ? "true" : "false"}`;
    }
    // 구형 코드 호환(네 main.js가 전역 correctionParam을 부를 수 있음)
    global.correctionParam = correctionParam;
  
    // 좌표 선택 여부
    function hasXY() {
      return global.G && Number.isInteger(global.G.lastX) && Number.isInteger(global.G.lastY);
    }
  
    // 파일 선택 → 업로드
    async function onFileChosen(e) {
      
      const file = e.target.files?.[0];
      if (!file) return;
  
      setStatus("업로드 중...", "warning");
      try {
        const fd = new FormData();
        fd.append("file", file);
        const r = await fetch(`${API_BASE}/upload`, { method: "POST", body: fd });
        const out = await r.json();
        if (!r.ok) throw new Error(out.error || "업로드 실패");
  
        // 전역 상태
        global.G = global.G || {};
        global.G.fileId = out.file_id;
        global.G.currentZ = 0;
        global.G.lastX = null;
        global.G.lastY = null;

        // 업로드 성공 직후
        window.onFitsUploaded && window.onFitsUploaded({
          file_id: out.file_id,
          filename: out.filename,
          header: out.header,
          preview_png: out.preview_png,
          shape: out.shape
        });

  
        // 메타 표시(있으면)
        els.fileNameEl && (els.fileNameEl.textContent = out.filename);
        els.headerMetaEl &&
          (els.headerMetaEl.textContent = `shape=${out.shape} | DATE-OBS=${out.header?.["DATE-OBS"] ?? "-"}`);
  
        // 슬라이스 인풋(3D일 때만 활성화)
        if (out.shape && out.shape.length === 3) {
          if (els.sliceIndex) {
            els.sliceIndex.disabled = false;
            els.sliceIndex.min = "0";
            els.sliceIndex.max = String(out.shape[0] - 1);
            els.sliceIndex.value = "0";
          }
        } else {
          if (els.sliceIndex) {
            els.sliceIndex.disabled = true;
            els.sliceIndex.value = "0";
          }
        }
  
        // 초기 프리뷰
        global.setFitsPreview?.(out.preview_png);
        setStatus("업로드 성공", "success");
      } catch (err) {
        setStatus(err.message || "업로드 실패", "danger");
      } finally {
        // 같은 파일 재선택 허용
        if (els.fileInput) els.fileInput.value = "";
      }
    }
  
    // 보정 ON/OFF 클릭
    async function onClipChange(next) {
      clipOn = !!next;
      updateClipButtons();
      await global.refreshPreview?.();
      if (hasXY()) {
        await global.drawSlitAndSpectrum?.(global.G.lastX, global.G.lastY);
      }
    }
  
    // 슬라이스 변경
    async function onSliceInput(e) {
      const z = parseInt(e.target.value, 10);
      global.G = global.G || {};
      global.G.currentZ = Number.isFinite(z) ? z : 0;
  
      await global.refreshPreview?.();
      if (hasXY()) {
        await global.drawSlitAndSpectrum?.(global.G.lastX, global.G.lastY);
      }
    }
  
    // 바인딩
    document.addEventListener("DOMContentLoaded", () => {
      // 라벨 안에 input이 있으므로 라벨 클릭만으로 파일 다이얼로그가 열림
      els.fileInput?.addEventListener("change", onFileChosen);
  
      els.btnClipOn?.addEventListener("click", () => onClipChange(true));
      els.btnClipOff?.addEventListener("click", () => onClipChange(false));
  
      els.sliceIndex?.addEventListener("input", onSliceInput);
  
      // 초기 상태
      updateClipButtons();
      // 업로드 전에는 슬라이스 비활성화
      if (els.sliceIndex) els.sliceIndex.disabled = true;
      setStatus("준비 완료", "success");
    }); 
  
    // 외부에서 참조 가능하도록 노출
    Object.defineProperty(global, "HeaderControls", {
      value: {
        get clipOn() { return clipOn; },
        setStatus,
        correctionParam,
      },
      writable: false,
      enumerable: true,
      configurable: false,
    });
  })(window);
  
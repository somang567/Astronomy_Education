"""
challan_postprocessing.py
-------------------------
lv05 (Dark/Flat 보정) + lv08 (Slit 곡률 보정) + Spectrum 추출
"""

import numpy as np
import cv2
from typing import Optional, Tuple


class challan_postprocessing:
    def __init__(self, dark: Optional[np.ndarray] = None, flat: Optional[np.ndarray] = None):
        """
        dark: 다크 프레임 (배경 잡음 제거용)
        flat: 플랫 프레임 (픽셀 감도 보정용)
        """
        self.dark = dark
        self.flat = flat

    # ------------------------
    # LV05: Dark / Flat 보정
    # ------------------------
    def apply_dark_flat(self, img: np.ndarray) -> np.ndarray:
        """
        Dark/Flat 보정
        """
        arr = img.astype(np.float32)

        # Dark correction
        if self.dark is not None:
            arr = arr - self.dark

        # Flat correction
        if self.flat is not None:
            arr = arr / (self.flat + 1e-6)

        return arr

    # ------------------------
    # LV08: Slit 곡률 보정
    # ------------------------
    def make_circle(
        self,
        img: np.ndarray,
        angle: float = 0.0,
        center: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        곡률 있는 slit 이미지를 원형 좌표계로 변환해 펴주는 함수.
        """
        h, w = img.shape[:2]

        if center is None:
            center = (w / 2, h / 2)

        # 반경: 이미지 경계 안쪽으로
        radius = min(center[0], center[1], w - center[0], h - center[1])

        # OpenCV polar 변환
        polar = cv2.warpPolar(
            img,
            (w, h),
            center,
            radius,
            cv2.WARP_FILL_OUTLIERS + cv2.WARP_POLAR_LINEAR,
        )

        return polar

    # ------------------------
    # Spectrum 추출
    # ------------------------
    def extract_spectrum(self, cube: np.ndarray, x: int, y: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        3D FITS cube에서 (x,y) 픽셀 위치의 스펙트럼 추출
        """
        if cube.ndim != 3:
            raise ValueError("3D FITS cube required")

        spec = cube[:, y, x].astype(np.float32)
        lam = np.arange(spec.size, dtype=np.float32)
        return lam, spec

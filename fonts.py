# -*- coding: utf-8 -*-
"""한글 폰트 파일 경로 찾기 (텍스트 삽입용)."""
import os

CANDIDATES = [
    r"C:\Windows\Fonts\malgun.ttf",      # 맑은 고딕
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\gulim.ttc",       # 굴림
    r"C:\Windows\Fonts\batang.ttc",      # 바탕
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]


def find_korean_font():
    for p in CANDIDATES:
        if os.path.exists(p):
            return p
    return None

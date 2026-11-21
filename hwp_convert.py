# -*- coding: utf-8 -*-
"""
hwp_convert.py — PDF → HWP 변환 (한컴오피스 COM 사용)
한컴오피스(한글)가 설치된 Windows 에서만 동작한다.
설치돼 있지 않으면 사용자에게 안내 예외를 던진다.
"""


class HwpNotAvailable(Exception):
    pass


def pdf_to_hwp(pdf_path, out_path):
    """
    한컴 '한글'을 COM 으로 띄워 PDF 를 열고 HWP 로 저장한다.
    한컴오피스 2020 이상에서 PDF 열기(→편집 가능한 문서로 변환)를 지원한다.
    """
    try:
        import win32com.client as win32
    except ImportError:
        raise HwpNotAvailable(
            "pywin32 가 필요합니다. 명령창에서  pip install pywin32  실행 후 다시 시도하세요."
        )

    try:
        hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    except Exception:
        raise HwpNotAvailable(
            "한컴오피스(한글)가 설치돼 있지 않거나 COM 등록이 안 돼 있습니다.\n"
            "한글이 설치된 PC 에서만 HWP 변환이 됩니다."
        )

    try:
        # 보안 모듈 경고 없이 파일 접근 허용
        try:
            hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        except Exception:
            pass

        # PDF 열기 (한컴이 내부적으로 편집 가능한 문서로 변환)
        hwp.Open(pdf_path, "PDF", "")

        # HWP 로 저장
        hwp.SaveAs(out_path, "HWP", "")
    finally:
        try:
            hwp.Quit()
        except Exception:
            pass

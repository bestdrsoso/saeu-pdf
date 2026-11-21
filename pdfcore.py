# -*- coding: utf-8 -*-
"""
pdfcore.py — PDF 처리 엔진 (PyMuPDF 래퍼)
GUI와 분리된 순수 로직. 여기 함수들은 화면 없이도 테스트 가능하다.
"""
import io
import os
import pymupdf  # PyMuPDF


class PdfDocument:
    """열려 있는 하나의 PDF 문서를 감싼다."""

    def __init__(self):
        self.doc = None
        self.path = None
        self.dirty = False  # 저장 안 된 변경이 있는가

    # ---- 열기 / 저장 / 닫기 ------------------------------------------
    def open(self, path):
        self.close()
        self.doc = pymupdf.open(path)
        self.path = path
        self.dirty = False

    def new_blank(self):
        """빈 문서 (이미지 합치기 등의 기반)"""
        self.close()
        self.doc = pymupdf.open()
        self.path = None
        self.dirty = True

    def is_open(self):
        return self.doc is not None

    def close(self):
        if self.doc is not None:
            try:
                self.doc.close()
            except Exception:
                pass
        self.doc = None
        self.path = None
        self.dirty = False

    def save(self, path=None):
        """path 가 None 이면 원본 자리에 저장(incremental 아님, 전체 재저장)."""
        target = path or self.path
        if target is None:
            raise ValueError("저장 경로가 없습니다.")
        # 원본 덮어쓰기는 임시파일 거쳐 안전하게
        if target == self.path:
            tmp = target + ".tmp_save"
            self.doc.save(tmp, garbage=3, deflate=True)
            self.doc.close()
            os.replace(tmp, target)
            self.doc = pymupdf.open(target)
        else:
            self.doc.save(target, garbage=3, deflate=True)
        self.path = target
        self.dirty = False

    @property
    def page_count(self):
        return self.doc.page_count if self.doc else 0

    # ---- 렌더링 ------------------------------------------------------
    def render_png(self, page_index, zoom=1.0):
        """페이지를 PNG 바이트로 렌더. GUI는 이 바이트를 QImage 로 읽는다."""
        page = self.doc[page_index]
        mat = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png"), pix.width, pix.height

    def page_size(self, page_index):
        """포인트 단위 (width, height). 회전 반영."""
        r = self.doc[page_index].rect
        return r.width, r.height

    # ---- 검색 --------------------------------------------------------
    def search(self, text):
        """모든 페이지에서 text 를 찾아 [(page_index, [fitz.Rect,...]), ...] 반환."""
        results = []
        if not text:
            return results
        for i in range(self.page_count):
            rects = self.doc[i].search_for(text)
            if rects:
                results.append((i, rects))
        return results

    def words_in_rect(self, page_index, clip):
        """clip(페이지 포인트 사각형)과 겹치는 단어들을 읽어 텍스트로. (선택·복사용)"""
        cr = pymupdf.Rect(clip)
        words = self.doc[page_index].get_text("words")  # x0,y0,x1,y1,word,block,line,n
        sel = [w for w in words if pymupdf.Rect(w[:4]).intersects(cr)]
        sel.sort(key=lambda w: (w[5], w[6], w[7]))
        return " ".join(w[4] for w in sel)

    def word_rects_in(self, page_index, clip):
        """clip과 겹치는 단어들의 사각형 목록 (형광펜/밑줄을 글자에 맞춰 긋기 위함)."""
        cr = pymupdf.Rect(clip)
        return [pymupdf.Rect(w[:4]) for w in self.doc[page_index].get_text("words")
                if pymupdf.Rect(w[:4]).intersects(cr)]

    # ---- 실행취소용 스냅샷 -------------------------------------------
    def snapshot(self):
        """현재 문서 상태를 바이트로 보관 (Ctrl+Z 용)."""
        return self.doc.tobytes(deflate=True)

    def restore(self, data):
        """snapshot 으로 보관한 상태로 되돌린다."""
        path = self.path
        try:
            self.doc.close()
        except Exception:
            pass
        self.doc = pymupdf.open("pdf", data)
        self.path = path
        self.dirty = True

    # ---- 페이지 편집 -------------------------------------------------
    def rotate_page(self, page_index, degrees):
        """degrees 만큼 추가 회전 (90 단위)."""
        page = self.doc[page_index]
        page.set_rotation((page.rotation + degrees) % 360)
        self.dirty = True

    def delete_page(self, page_index):
        self.doc.delete_page(page_index)
        self.dirty = True

    def move_page(self, from_index, to_index):
        self.doc.move_page(from_index, to_index)
        self.dirty = True

    def extract_pages(self, indices, out_path):
        """indices(0-base) 페이지만 모아 새 PDF 로 저장."""
        new = pymupdf.open()
        for i in indices:
            new.insert_pdf(self.doc, from_page=i, to_page=i)
        new.save(out_path, garbage=3, deflate=True)
        new.close()

    def insert_pdf_file(self, other_path, at_index=None):
        """다른 PDF 를 현재 문서에 합친다. at_index=None 이면 맨 뒤."""
        other = pymupdf.open(other_path)
        if at_index is None:
            self.doc.insert_pdf(other)
        else:
            self.doc.insert_pdf(other, start_at=at_index)
        other.close()
        self.dirty = True

    # ---- 주석 / 그리기 ----------------------------------------------
    # 좌표는 모두 '페이지 포인트 좌표'(렌더 zoom 과 무관) 로 받는다.
    def add_highlight(self, page_index, quads):
        page = self.doc[page_index]
        page.add_highlight_annot(quads)
        self.dirty = True

    def add_underline(self, page_index, quads):
        page = self.doc[page_index]
        page.add_underline_annot(quads)
        self.dirty = True

    def add_ink(self, page_index, strokes, color=(1, 0, 0), width=2.0):
        """펜 자유그리기. strokes = [[(x,y),(x,y)...], ...]"""
        page = self.doc[page_index]
        annot = page.add_ink_annot(strokes)
        annot.set_colors(stroke=color)
        annot.set_border(width=width)
        annot.update()
        self.dirty = True

    def add_rect(self, page_index, rect, color=(1, 0, 0), width=2.0, fill=None):
        page = self.doc[page_index]
        annot = page.add_rect_annot(pymupdf.Rect(rect))
        annot.set_colors(stroke=color, fill=fill)
        annot.set_border(width=width)
        annot.update()
        self.dirty = True

    def add_circle(self, page_index, rect, color=(1, 0, 0), width=2.0, fill=None):
        page = self.doc[page_index]
        annot = page.add_circle_annot(pymupdf.Rect(rect))
        annot.set_colors(stroke=color, fill=fill)
        annot.set_border(width=width)
        annot.update()
        self.dirty = True

    def add_line(self, page_index, p1, p2, color=(1, 0, 0), width=2.0):
        page = self.doc[page_index]
        annot = page.add_line_annot(pymupdf.Point(p1), pymupdf.Point(p2))
        annot.set_colors(stroke=color)
        annot.set_border(width=width)
        annot.update()
        self.dirty = True

    def _put_text(self, page, rect, text, fontsize, color, fontfile):
        """
        글자를 실제로 써넣는다.
        - 한글: 폰트파일(맑은고딕)이 있으면 그걸로, 없으면 내장 한글폰트로.
        - 영역이 모자라면 '글자 크기는 그대로' 두고 박스를 늘려서 넣는다.
        """
        r = pymupdf.Rect(rect)

        def attempt(rr, fs):
            if fontfile and os.path.exists(fontfile):
                return page.insert_textbox(rr, text, fontsize=fs, color=color,
                                           fontfile=fontfile, fontname="kor",
                                           align=0)
            if any(ord(c) > 0x7F for c in text):   # 한글 등 → 내장 한글폰트
                return page.insert_textbox(rr, text, fontsize=fs, color=color,
                                           fontname="korea", align=0)
            return page.insert_textbox(rr, text, fontsize=fs, color=color,
                                       fontname="helv", align=0)

        rc = attempt(r, fontsize)
        if rc >= 0:
            return rc
        # 1) 박스를 아래로 넉넉히 늘려 재시도 (사용자가 고른 글자 크기 유지)
        big = pymupdf.Rect(r.x0, r.y0,
                           max(r.x1, r.x0 + 80),
                           min(page.rect.y1 - 2, r.y0 + 2000))
        rc = attempt(big, fontsize)
        if rc >= 0:
            return rc
        # 2) 그래도 안 들어가면 크기를 줄여서라도 넣는다
        fs = fontsize
        while fs > 6:
            fs -= 1
            rc = attempt(big, fs)
            if rc >= 0:
                return rc
        return rc

    def add_textbox(self, page_index, rect, text, fontsize=12,
                    color=(0, 0, 0), fontfile=None, fill=None):
        """
        글자 박스를 '주석'으로 넣는다. 주석이라 나중에 지우개로 지울 수 있다.
        내장 한글 폰트를 쓰므로 한글도 정상 출력된다.
        """
        page = self.doc[page_index]
        r = pymupdf.Rect(rect)
        # 글자가 다 들어가도록 박스 보정 (크기는 사용자가 고른 그대로 유지)
        lines = text.count("\n") + 1
        need_h = fontsize * 1.5 * lines + 10
        if r.height < need_h:
            r = pymupdf.Rect(r.x0, r.y0, r.x1, min(page.rect.y1 - 2, r.y0 + need_h))
        if r.width < fontsize * 5:
            r = pymupdf.Rect(r.x0, r.y0,
                             min(page.rect.x1 - 2, r.x0 + max(140, fontsize * 10)),
                             r.y1)
        annot = page.add_freetext_annot(
            r, text, fontsize=fontsize, fontname="korea",
            text_color=color, fill_color=fill, border_width=0, align=0)
        annot.set_info(content=text)
        annot.update()
        self.dirty = True
        return 0

    # ---- 지우기 ------------------------------------------------------
    def delete_annots_in(self, page_index, rect):
        """
        지정 영역과 겹치는 주석을 지운다. 지운 개수 반환.
        * 순회 중 삭제는 내부 참조가 깨져 프로그램이 죽을 수 있으므로
          delete_annot 이 돌려주는 '다음 주석'을 따라간다.
        """
        page = self.doc[page_index]
        r = pymupdf.Rect(rect)
        n = 0
        annot = page.first_annot
        while annot:
            if annot.rect.intersects(r):
                annot = page.delete_annot(annot)   # 다음 주석을 돌려준다
                n += 1
            else:
                annot = annot.next
        if n:
            self.dirty = True
        return n

    def has_content_in(self, page_index, rect):
        """그 영역에 글자나 그림(주석이 아닌 것)이 있는지."""
        page = self.doc[page_index]
        r = pymupdf.Rect(rect)
        if page.get_text("text", clip=r).strip():
            return True
        for img in page.get_image_info():
            if pymupdf.Rect(img["bbox"]).intersects(r):
                return True
        return False

    def whiteout(self, page_index, rect):
        """그 영역을 흰색으로 덮어 지운다(아래 내용도 같이 지워짐)."""
        page = self.doc[page_index]
        page.add_redact_annot(pymupdf.Rect(rect), fill=(1, 1, 1))
        page.apply_redactions()
        self.dirty = True

    def add_image(self, page_index, rect, image_path):
        """이미지(서명/도장 포함) 삽입."""
        page = self.doc[page_index]
        page.insert_image(pymupdf.Rect(rect), filename=image_path, keep_proportion=True)
        self.dirty = True

    # ---- PDF 안 텍스트 직접 수정 ------------------------------------
    def replace_text_block(self, page_index, rect, new_text,
                           fontsize=11, color=(0, 0, 0), fontfile=None):
        """
        지정 영역의 기존 글자를 지우고(redaction) 새 글자를 얹는다.
        * 원본 폰트/자간을 100% 살리지는 못한다(알PDF 류 한계와 동일).
        """
        page = self.doc[page_index]
        r = pymupdf.Rect(rect)
        page.add_redact_annot(r, fill=(1, 1, 1))
        page.apply_redactions()
        if new_text:
            self._put_text(page, r, new_text, fontsize, color, fontfile)
        self.dirty = True

    # ---- 변환 --------------------------------------------------------
    def export_images(self, out_dir, fmt="png", dpi=150, pages=None):
        """각 페이지를 이미지 파일로. 저장된 경로 리스트 반환."""
        os.makedirs(out_dir, exist_ok=True)
        fmt = fmt.lower()
        ext = "jpg" if fmt in ("jpg", "jpeg") else "png"
        zoom = dpi / 72.0
        mat = pymupdf.Matrix(zoom, zoom)
        pages = pages or range(self.page_count)
        out = []
        base = os.path.splitext(os.path.basename(self.path or "문서"))[0]
        for i in pages:
            pix = self.doc[i].get_pixmap(matrix=mat, alpha=False)
            p = os.path.join(out_dir, f"{base}_{i + 1:03d}.{ext}")
            if ext == "jpg":
                pix.save(p, jpg_quality=90)
            else:
                pix.save(p)
            out.append(p)
        return out

    @staticmethod
    def merge_files(paths, out_path):
        """여러 PDF 를 순서대로 하나로 합친다."""
        new = pymupdf.open()
        for p in paths:
            d = pymupdf.open(p)
            new.insert_pdf(d)
            d.close()
        new.save(out_path, garbage=3, deflate=True)
        n = new.page_count
        new.close()
        return n

    @staticmethod
    def images_to_pdf(image_paths, out_path):
        """여러 이미지를 한 PDF 로."""
        new = pymupdf.open()
        for img in image_paths:
            imgdoc = pymupdf.open(img)
            rect = imgdoc[0].rect
            pdfbytes = imgdoc.convert_to_pdf()
            imgdoc.close()
            imgpdf = pymupdf.open("pdf", pdfbytes)
            new.insert_pdf(imgpdf)
            imgpdf.close()
        new.save(out_path)
        new.close()

    def to_hwp(self, out_path):
        """
        PDF → HWP. 한컴오피스(COM) 변환엔진을 사용한다.
        한컴오피스가 설치돼 있어야 하며, 결과는 한글에서 편집 가능하다.
        한컴이 없으면 hwp_convert 가 안내 예외를 던진다.
        """
        import hwp_convert
        # COM 변환은 '파일'이 필요하므로, 현재 문서를 임시 PDF 로 내보낸 뒤 변환
        tmp_pdf = out_path + ".src.pdf"
        self.doc.save(tmp_pdf, garbage=3, deflate=True)
        try:
            hwp_convert.pdf_to_hwp(tmp_pdf, out_path)
        finally:
            try:
                os.remove(tmp_pdf)
            except OSError:
                pass

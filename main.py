# -*- coding: utf-8 -*-
"""
새우PDF — 가벼운 PDF 뷰어/편집기  (made by 왕새우 · 비공개 · 내수용)
광고 없음. 쓰는 기능만. 연속 스크롤 보기.
"""
import os
import sys
import tempfile
import urllib.parse

from PySide6.QtCore import Qt, QRectF, Signal, QSize, QTimer, QEvent
from PySide6.QtGui import (QAction, QImage, QPixmap, QPainter, QPen, QColor,
                           QBrush, QIcon, QKeySequence)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QFileDialog, QInputDialog, QColorDialog, QMessageBox, QListWidget,
    QListWidgetItem, QLabel, QSpinBox, QDockWidget,
    QLineEdit, QPushButton, QStatusBar, QTabWidget, QToolButton, QSlider,
    QFrame, QWidget, QVBoxLayout, QHBoxLayout, QButtonGroup, QTextEdit,
    QScrollArea, QMenu, QDialog, QKeySequenceEdit, QGridLayout,
    QDialogButtonBox,
)
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog

import pymupdf
from pdfcore import PdfDocument
from hwp_convert import HwpNotAvailable
import fonts

APP_NAME = "새우PDF"
APP_VERSION = "1.0.3"
# 업데이트 파일이 올라가는 곳 (GitHub raw)
UPDATE_BASE = "https://raw.githubusercontent.com/bestdrsoso/saeu-pdf/main/"


def app_dir():
    """설정파일을 둘 폴더. exe 로 묶였을 때는 exe 가 있는 폴더."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# 도구 모드
T_PAN, T_HILITE, T_UNDER, T_PEN, T_RECT, T_CIRCLE, T_LINE, \
    T_TEXT, T_IMAGE, T_EDIT = range(10)

TOOL_LABELS = {
    T_PAN: "손/텍스트선택", T_HILITE: "형광펜", T_UNDER: "밑줄", T_PEN: "펜",
    T_RECT: "사각형", T_CIRCLE: "원", T_LINE: "선", T_TEXT: "텍스트상자",
    T_IMAGE: "이미지", T_EDIT: "텍스트수정",
}

GAP = 14  # 페이지 사이 간격(픽셀)

# 기본 단축키 (같은 폴더의 shortcuts.json 으로 바꿀 수 있음)
DEFAULT_SHORTCUTS = {
    "열기": "Ctrl+O", "저장": "Ctrl+S", "다른이름저장": "Ctrl+Shift+S",
    "인쇄": "Ctrl+P", "검색": "Ctrl+F", "실행취소": "Ctrl+Z",
    "확대": "Ctrl+=", "축소": "Ctrl+-", "폭맞춤": "Ctrl+0", "화면맞춤": "Ctrl+9",
    "이전페이지": "PgUp", "다음페이지": "PgDown",
    "손선택": "V", "형광펜": "H", "펜": "P",
    "사각형": "R", "원": "C", "선": "L", "텍스트상자": "T",
    "이미지": "I",
    "다음찾기": "F3", "이전찾기": "Shift+F3", "검색표시지움": "Ctrl+Shift+F",
}


class ContinuousView(QGraphicsView):
    """모든 페이지를 세로로 이어 붙여 보여주고, 보이는 페이지만 렌더(lazy)."""
    pageChanged = Signal(int)   # 현재(화면 중앙) 페이지가 바뀜
    zoomChanged = Signal(float)  # 줌 배율이 바뀜

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.setRenderHint(QPainter.Antialiasing)
        self.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.setDragMode(QGraphicsView.NoDrag)

        self.zoom = 1.5
        self.tool = T_PAN
        self.color = (1, 0, 0)
        self.width = 2.0

        self.page_rects = []        # [[x,y,w,h], ...] scene 픽셀 좌표
        self.page_items = {}        # index -> QGraphicsPixmapItem (렌더됨)
        self.placeholders = {}      # index -> 흰 배경 rect item
        self.cur_page = 0

        self._start = None
        self._pts = []
        self._temp = []
        self._sel = []              # 텍스트선택 표시 아이템
        self._inline = None         # 화면에서 바로 글 쓰는 입력상자
        self._search_items = []     # 검색 표시(노랑/주황) 아이템

        self.setAcceptDrops(True)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self.render_visible)

    # ---------- 드래그해서 열기 (창으로 넘김) ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        e.acceptProposedAction()
        if paths:
            self.win.open_many(paths)

    # ---------- 레이아웃 ----------
    def rebuild(self):
        """문서 전체를 세로로 재배치 (줌 바뀌거나 페이지 수 바뀔 때)."""
        self.scene_.clear()
        self.page_rects = []
        self.page_items = {}
        self.placeholders = {}
        doc = self.win.doc
        if not doc.is_open():
            self.scene_.setSceneRect(0, 0, 1, 1)
            return
        # 먼저 최대 폭 계산
        sizes = [doc.page_size(i) for i in range(doc.page_count)]
        maxw = max(w * self.zoom for w, h in sizes)
        scene_w = maxw + 2 * GAP
        y = GAP
        for i, (wpt, hpt) in enumerate(sizes):
            w = wpt * self.zoom
            h = hpt * self.zoom
            x = (scene_w - w) / 2
            self.page_rects.append([x, y, w, h])
            ph = self.scene_.addRect(QRectF(x, y, w, h),
                                     QPen(QColor(180, 180, 180)),
                                     QBrush(QColor(255, 255, 255)))
            self.placeholders[i] = ph
            y += h + GAP
        self.scene_.setSceneRect(0, 0, scene_w, y)
        self._search_items = []
        self.render_visible()
        hits = getattr(self.win, "search_hits", None)
        if hits:
            self.show_search_marks(hits, getattr(self.win, "search_idx", -1))

    def _on_scroll(self):
        self._scroll_timer.start(40)   # 스크롤 멈춘 뒤 렌더(디바운스)
        self._update_current()

    def render_visible(self):
        if not self.win.doc.is_open() or not self.page_rects:
            return
        vis = self.mapToScene(self.viewport().rect()).boundingRect()
        margin = vis.height()  # 위아래 한 화면 분 미리 렌더
        vis.adjust(0, -margin, 0, margin)
        doc = self.win.doc
        for i, (x, y, w, h) in enumerate(self.page_rects):
            pr = QRectF(x, y, w, h)
            if pr.intersects(vis):
                if i not in self.page_items:
                    png, pw, ph = doc.render_png(i, zoom=self.zoom)
                    pm = QPixmap.fromImage(QImage.fromData(png, "PNG"))
                    item = self.scene_.addPixmap(pm)
                    item.setPos(x, y)
                    self.page_items[i] = item
        self._trim_cache(vis)

    def _trim_cache(self, vis):
        """멀리 있는 렌더 페이지는 해제해 메모리 관리."""
        if len(self.page_items) <= 16:
            return
        for i in list(self.page_items):
            x, y, w, h = self.page_rects[i]
            if not QRectF(x, y, w, h).intersects(vis):
                self.scene_.removeItem(self.page_items[i])
                del self.page_items[i]

    def _update_current(self):
        center_y = self.mapToScene(self.viewport().rect().center()).y()
        for i, (x, y, w, h) in enumerate(self.page_rects):
            if y <= center_y <= y + h + GAP:
                if i != self.cur_page:
                    self.cur_page = i
                    self.pageChanged.emit(i)
                return

    def invalidate_page(self, i):
        """주석 등으로 바뀐 페이지를 다시 렌더."""
        if i in self.page_items:
            self.scene_.removeItem(self.page_items[i])
            del self.page_items[i]
        self.render_visible()

    # ---------- 검색 표시 ----------
    def clear_search_marks(self):
        for it in self._search_items:
            try:
                self.scene_.removeItem(it)
            except Exception:
                pass
        self._search_items = []

    def show_search_marks(self, hits, cur_index):
        """찾은 곳은 연노랑, 지금 보고 있는 곳은 주황 테두리로 구분."""
        self.clear_search_marks()
        if not self.page_rects:
            return
        z = self.zoom
        for i, (pi, r) in enumerate(hits[:400]):
            if pi >= len(self.page_rects):
                continue
            x, y, _w, _h = self.page_rects[pi]
            rc = QRectF(x + r.x0 * z, y + r.y0 * z,
                        (r.x1 - r.x0) * z, (r.y1 - r.y0) * z)
            if i == cur_index:
                it = self.scene_.addRect(rc, QPen(QColor(255, 60, 0), 2),
                                         QBrush(QColor(255, 150, 0, 130)))
            else:
                it = self.scene_.addRect(rc, QPen(Qt.NoPen),
                                         QBrush(QColor(255, 240, 0, 70)))
            it.setZValue(10)
            self._search_items.append(it)

    def goto_hit(self, pi, r):
        """찾은 위치가 화면 가운데 오도록 이동."""
        if pi >= len(self.page_rects):
            return
        x, y, _w, _h = self.page_rects[pi]
        z = self.zoom
        self.centerOn(x + (r.x0 + r.x1) / 2 * z, y + (r.y0 + r.y1) / 2 * z)
        self.cur_page = pi
        self.render_visible()

    def goto_page(self, i):
        if not self.page_rects or not (0 <= i < len(self.page_rects)):
            return
        x, y, w, h = self.page_rects[i]
        cx = x + w / 2
        self.centerOn(cx, y + self.viewport().height() / 2)
        self.cur_page = i
        self.render_visible()

    def set_zoom(self, z, keep_page=True):
        self.zoom = max(0.25, min(z, 8.0))
        p = self.cur_page
        self.rebuild()
        if keep_page:
            self.goto_page(p)
        self.zoomChanged.emit(self.zoom)

    # ---------- 좌표 ----------
    def page_at(self, sp):
        for i, (x, y, w, h) in enumerate(self.page_rects):
            if y <= sp.y() <= y + h:
                return i
        return None

    def to_page_pt(self, i, sp):
        x, y, w, h = self.page_rects[i]
        return ((sp.x() - x) / self.zoom, (sp.y() - y) / self.zoom)

    def set_tool(self, t):
        self.tool = t

    # ---------- 마우스 ----------
    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
            self.win.fit_mode = None
            self.set_zoom(self.zoom * factor)
            e.accept()
        else:
            super().wheelEvent(e)

    def _clear_temp(self):
        for it in self._temp:
            self.scene_.removeItem(it)
        self._temp = []

    def _clear_sel(self):
        for it in self._sel:
            self.scene_.removeItem(it)
        self._sel = []

    def mousePressEvent(self, e):
        if self.win.doc.is_open() and e.button() == Qt.LeftButton:
            self._start = self.mapToScene(e.position().toPoint())
            self._pts = [self._start]
            self._clear_sel()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._start is None:
            return super().mouseMoveEvent(e)
        cur = self.mapToScene(e.position().toPoint())
        pen = QPen(QColor.fromRgbF(*self.color), self.width)
        self._clear_temp()
        if self.tool == T_PAN:
            r = QRectF(self._start, cur).normalized()
            self._temp.append(self.scene_.addRect(r, QPen(Qt.NoPen),
                                                  QBrush(QColor(0, 120, 215, 60))))
        elif self.tool == T_PEN:
            self._pts.append(cur)
            for i in range(1, len(self._pts)):
                self._temp.append(self.scene_.addLine(
                    self._pts[i - 1].x(), self._pts[i - 1].y(),
                    self._pts[i].x(), self._pts[i].y(), pen))
        elif self.tool in (T_RECT, T_HILITE, T_UNDER, T_TEXT, T_IMAGE, T_EDIT):
            r = QRectF(self._start, cur).normalized()
            if self.tool == T_HILITE:
                self._temp.append(self.scene_.addRect(r, QPen(Qt.NoPen),
                                                      QBrush(QColor(255, 255, 0, 90))))
            else:
                self._temp.append(self.scene_.addRect(r, pen))
        elif self.tool == T_CIRCLE:
            self._temp.append(self.scene_.addEllipse(
                QRectF(self._start, cur).normalized(), pen))
        elif self.tool == T_LINE:
            self._temp.append(self.scene_.addLine(
                self._start.x(), self._start.y(), cur.x(), cur.y(), pen))
        e.accept()

    def mouseReleaseEvent(self, e):
        if self._start is None:
            return super().mouseReleaseEvent(e)
        end = self.mapToScene(e.position().toPoint())
        self._clear_temp()
        try:
            if self.tool == T_PAN:
                self._select_text(self._start, end)
            else:
                self._commit(end)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"작업 실패: {ex}")
        self._start = None
        self._pts = []
        e.accept()

    def _select_text(self, start, end):
        """손도구 드래그 → 영역 텍스트 복사."""
        r = QRectF(start, end).normalized()
        if r.width() < 3 and r.height() < 3:
            return
        doc = self.win.doc
        parts = []
        for i, (x, y, w, h) in enumerate(self.page_rects):
            inter = QRectF(x, y, w, h).intersected(r)
            if inter.isEmpty():
                continue
            clip = ((inter.x() - x) / self.zoom, (inter.y() - y) / self.zoom,
                    (inter.right() - x) / self.zoom, (inter.bottom() - y) / self.zoom)
            t = doc.words_in_rect(i, clip)
            if t:
                parts.append(t)
            self._sel.append(self.scene_.addRect(inter, QPen(Qt.NoPen),
                                                 QBrush(QColor(0, 120, 215, 70))))
        text = "\n".join(parts)
        if text:
            QApplication.clipboard().setText(text)
            self.win.statusBar().showMessage(f"복사됨: {text[:30]}…", 3000)
        else:
            self.win.statusBar().showMessage("선택 영역에 글자가 없습니다", 2000)

    def _commit(self, end):
        doc = self.win.doc
        pi = self.page_at(self._start)
        if pi is None:
            return
        sx, sy = self.to_page_pt(pi, self._start)
        ex, ey = self.to_page_pt(pi, end)
        rect = (min(sx, ex), min(sy, ey), max(sx, ex), max(sy, ey))

        # 글상자 / 텍스트수정 : 팝업 없이 화면에서 바로 입력
        if self.tool in (T_TEXT, T_EDIT):
            # 드래그하지 않고 그냥 클릭만 해도 그 자리에 상자 하나가 생긴다
            if rect[2] - rect[0] < 15 or rect[3] - rect[1] < 12:
                fs = self.win.fontsize
                rect = (rect[0], rect[1],
                        rect[0] + max(200, fs * 12), rect[1] + max(36, fs * 2.4))
            initial = doc.words_in_rect(pi, rect) if self.tool == T_EDIT else ""
            x0, y0, _w, _h = self.page_rects[pi]
            srect = QRectF(x0 + rect[0] * self.zoom, y0 + rect[1] * self.zoom,
                           (rect[2] - rect[0]) * self.zoom,
                           (rect[3] - rect[1]) * self.zoom)
            self._begin_inline(pi, rect, srect, initial,
                               "edit" if self.tool == T_EDIT else "text")
            return

        self.win.push_undo()
        if self.tool == T_PEN:
            stroke = [self.to_page_pt(pi, p) for p in self._pts]
            if len(stroke) >= 2:
                doc.add_ink(pi, [stroke], color=self.color, width=self.width)
        elif self.tool == T_HILITE:
            rs = doc.word_rects_in(pi, rect)
            if rs:
                doc.add_highlight(pi, [r.quad for r in rs])
            else:
                doc.add_highlight(pi, [pymupdf.Rect(rect).quad])
        elif self.tool == T_UNDER:
            rs = doc.word_rects_in(pi, rect)
            if rs:
                doc.add_underline(pi, [r.quad for r in rs])
            else:
                doc.add_underline(pi, [pymupdf.Rect(rect).quad])
        elif self.tool == T_RECT:
            doc.add_rect(pi, rect, color=self.color, width=self.width)
        elif self.tool == T_CIRCLE:
            doc.add_circle(pi, rect, color=self.color, width=self.width)
        elif self.tool == T_LINE:
            doc.add_line(pi, (sx, sy), (ex, ey), color=self.color, width=self.width)
        elif self.tool == T_IMAGE:
            if self.win.pending_image:
                doc.add_image(pi, rect, self.win.pending_image)
            else:
                self.win.statusBar().showMessage(
                    "먼저 [보기 → 이미지 삽입할 파일 고르기]", 3000)
                return
        self.invalidate_page(pi)
        self.win.update_title()

    # ---------- 오른쪽 클릭 메뉴 ----------
    def contextMenuEvent(self, e):
        if not self.win.doc.is_open():
            return
        sp = self.mapToScene(e.pos())
        pi = self.page_at(sp)
        w = self.win
        mnu = QMenu(self)

        mnu.addAction("📝 여기에 텍스트상자", lambda: self._ctx_textbox(sp, pi))
        mnu.addAction("🖼 여기에 이미지 넣기", lambda: self._ctx_image(pi))
        mnu.addSeparator()
        mnu.addAction("↩ 실행취소 (Ctrl+Z)", w.undo)
        mnu.addSeparator()

        tools = mnu.addMenu("도구 바꾸기")
        for t in (T_PAN, T_HILITE, T_PEN, T_RECT, T_CIRCLE, T_LINE, T_TEXT):
            act = tools.addAction(TOOL_LABELS[t], lambda tt=t: w.pick_tool(tt))
            act.setCheckable(True)
            act.setChecked(self.tool == t)

        pages = mnu.addMenu("이 쪽")
        pages.addAction("왼쪽 90° 회전", lambda: w.rotate(-90))
        pages.addAction("오른쪽 90° 회전", lambda: w.rotate(90))
        pages.addAction("이 쪽 삭제", w.delete_page)
        pages.addSeparator()
        pages.addAction("쪽 추출", w.extract_pages)
        pages.addAction("여러 PDF 병합", w.merge_many)

        mnu.addSeparator()
        mnu.addAction("폭맞춤 (Ctrl+0)", w.fit_width)
        mnu.addAction("화면맞춤 (Ctrl+9)", w.fit_page)
        mnu.addSeparator()
        mnu.addAction("💾 저장 (Ctrl+S)", w.save_file)
        mnu.addAction("🖨 인쇄 미리보기 (Ctrl+P)", w.print_doc)
        mnu.addSeparator()
        mnu.addAction("⌨ 단축키 설정…", w.open_shortcut_dialog)
        mnu.exec(e.globalPos())

    def _ctx_textbox(self, sp, pi):
        """우클릭한 자리에 바로 텍스트상자."""
        if pi is None:
            return
        px, py = self.to_page_pt(pi, sp)
        fs = self.win.fontsize
        rect = (px, py, px + max(200, fs * 12), py + max(36, fs * 2.4))
        x0, y0, _w, _h = self.page_rects[pi]
        srect = QRectF(x0 + rect[0] * self.zoom, y0 + rect[1] * self.zoom,
                       (rect[2] - rect[0]) * self.zoom,
                       (rect[3] - rect[1]) * self.zoom)
        self._begin_inline(pi, rect, srect, "", "text")

    def _ctx_image(self, pi):
        self.win.choose_image()

    # ---------- 화면에서 바로 글쓰기 ----------
    def _begin_inline(self, pi, page_rect, scene_rect, initial="", mode="text"):
        self._finish_inline(False)
        ed = QTextEdit(self.viewport())
        tl = self.mapFromScene(scene_rect.topLeft())
        br = self.mapFromScene(scene_rect.bottomRight())
        ed.setGeometry(tl.x(), tl.y(),
                       max(80, br.x() - tl.x()), max(30, br.y() - tl.y()))
        f = ed.font()
        f.setPointSizeF(max(8.0, self.win.fontsize * self.zoom * 0.72))
        ed.setFont(f)
        ed.setPlainText(initial)
        ed.setStyleSheet(
            "QTextEdit{background:rgba(255,255,255,0.97);"
            "border:2px solid #0078d7;border-radius:2px;}")
        ed.show()
        ed.setFocus()
        if initial:
            ed.selectAll()
        ed.installEventFilter(self)

        # 마우스로도 확정/취소할 수 있게 작은 버튼 두 개
        g = ed.geometry()
        by = g.bottom() + 3
        if by + 26 > self.viewport().height():      # 아래가 모자라면 위쪽에
            by = max(0, g.top() - 27)
        ok = QPushButton("✔ 확정", self.viewport())
        no = QPushButton("✖ 취소", self.viewport())
        for b, x in ((ok, g.left()), (no, g.left() + 70)):
            b.setGeometry(x, by, 66, 24)
            b.setFocusPolicy(Qt.NoFocus)   # 눌러도 입력칸 포커스가 안 빠지게
            b.show()
        ok.setStyleSheet("background:#0078d7;color:white;border:none;border-radius:3px;")
        no.setStyleSheet("background:#e81123;color:white;border:none;border-radius:3px;")
        ok.clicked.connect(lambda: self._finish_inline(True))
        no.clicked.connect(lambda: self._finish_inline(False))

        self._inline = {"ed": ed, "pi": pi, "rect": page_rect, "mode": mode,
                        "btns": [ok, no]}
        self.win.toggle_letter_shortcuts(False)
        self.win.statusBar().showMessage(
            "글 입력 후 [확정] 또는 Ctrl+Enter · [취소] 또는 Esc", 8000)

    def eventFilter(self, obj, ev):
        if self._inline and obj is self._inline["ed"]:
            if ev.type() == QEvent.KeyPress:
                if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and \
                        (ev.modifiers() & Qt.ControlModifier):
                    self._finish_inline(True)
                    return True
                if ev.key() == Qt.Key_Escape:
                    self._finish_inline(False)
                    return True
            elif ev.type() == QEvent.FocusOut:
                self._finish_inline(True)
                return True
        return super().eventFilter(obj, ev)

    def _finish_inline(self, apply_):
        info = self._inline
        if not info:
            return
        self._inline = None
        ed = info["ed"]
        txt = ed.toPlainText()
        ed.removeEventFilter(self)
        ed.hide()
        ed.deleteLater()
        for b in info.get("btns", []):
            b.hide()
            b.deleteLater()
        self.win.toggle_letter_shortcuts(True)
        if not apply_:
            return
        doc = self.win.doc
        if info["mode"] == "text" and not txt.strip():
            return
        self.win.push_undo()
        if info["mode"] == "text":
            rc = doc.add_textbox(info["pi"], info["rect"], txt,
                                 fontsize=self.win.fontsize, color=self.color,
                                 fontfile=self.win.kfont)
            if rc is not None and rc < 0:
                self.win.statusBar().showMessage(
                    "글자가 너무 많아 넣지 못했습니다. 영역을 더 크게 잡아주세요", 5000)
        else:
            doc.replace_text_block(info["pi"], info["rect"], txt,
                                   fontsize=self.win.fontsize, color=(0, 0, 0),
                                   fontfile=self.win.kfont)
        self.invalidate_page(info["pi"])
        self.win.update_title()


def _ver_tuple(s):
    out = []
    for part in str(s).split("."):
        try:
            out.append(int(part))
        except ValueError:
            out.append(0)
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])


class ShortcutDialog(QDialog):
    """앱 안에서 단축키를 직접 지정하는 창."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("단축키 설정")
        self.resize(460, 620)
        outer = QVBoxLayout(self)
        info = QLabel("바꿀 칸을 클릭하고 원하는 키를 누르세요.\n"
                      "· 그 단축키를 없애려면 오른쪽 [지우기] 버튼을 누르세요.\n"
                      "· 백스페이스·Delete 도 키로 인식되니, 지울 때는 [지우기] 를 쓰세요.")
        info.setStyleSheet("color:#555;")
        outer.addWidget(info)

        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(4, 4, 4, 4)
        self.edits = {}
        for row, name in enumerate(DEFAULT_SHORTCUTS.keys()):
            grid.addWidget(QLabel(name), row, 0)
            ed = QKeySequenceEdit(QKeySequence(win.shortcut_keys.get(name, "")))
            try:
                ed.setMaximumSequenceLength(1)   # 한 조합만 받기
            except Exception:
                pass
            grid.addWidget(ed, row, 1)
            btn = QPushButton("지우기")
            btn.setFixedWidth(62)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(lambda _=False, e=ed: e.clear())
            grid.addWidget(btn, row, 2)
            self.edits[name] = ed
        sa = QScrollArea()
        sa.setWidget(inner)
        sa.setWidgetResizable(True)
        outer.addWidget(sa, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel
                                | QDialogButtonBox.RestoreDefaults)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._defaults)
        btns.button(QDialogButtonBox.Save).setText("저장하고 적용")
        btns.button(QDialogButtonBox.Cancel).setText("취소")
        btns.button(QDialogButtonBox.RestoreDefaults).setText("기본값으로")
        outer.addWidget(btns)

    def _defaults(self):
        for name, ed in self.edits.items():
            ed.setKeySequence(QKeySequence(DEFAULT_SHORTCUTS[name]))

    def _save(self):
        import json
        data, used = {}, {}
        for name, ed in self.edits.items():
            s = ed.keySequence().toString()
            if not s:
                continue
            if s in used:
                QMessageBox.warning(self, APP_NAME,
                                    f"'{s}' 키가 '{used[s]}' 와 겹칩니다.")
                return
            used[s] = name
            data[name] = s
        cfg = os.path.join(app_dir(), "shortcuts.json")
        try:
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as ex:
            QMessageBox.critical(self, APP_NAME, f"저장 실패: {ex}")
            return
        self.win.reload_shortcuts()
        self.win.statusBar().showMessage("단축키를 저장하고 바로 적용했습니다", 4000)
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.doc = PdfDocument()
        self.fontsize = 12
        self.kfont = fonts.find_korean_font()
        self.pending_image = None
        self.search_hits = []
        self.search_idx = -1
        self.undo_stack = []
        self._shortcut_actions = []
        self.fit_mode = "width"     # width | page | None(수동 줌)

        self.setWindowTitle(APP_NAME)
        self.resize(1200, 820)
        self.setAcceptDrops(True)

        self.view = ContinuousView(self)
        self.view.pageChanged.connect(self._page_changed)
        self.setCentralWidget(self.view)

        self._build_thumbs()
        self._build_ribbon()
        self._build_statusbar()
        self._build_shortcuts()
        self.view.zoomChanged.connect(self._on_zoom)
        self.update_title()
        QTimer.singleShot(2000, lambda: self.check_update(silent=True))

    # ---------- 썸네일 ----------
    def _build_thumbs(self):
        self.thumbs = QListWidget()
        self.thumbs.setIconSize(QSize(120, 160))
        self.thumbs.setFixedWidth(160)
        self.thumbs.setDragDropMode(QListWidget.InternalMove)
        self.thumbs.currentRowChanged.connect(self._thumb_clicked)
        self.thumbs.model().rowsMoved.connect(self._thumb_moved)
        dock = QDockWidget("페이지", self)
        dock.setWidget(self.thumbs)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def _thumb_clicked(self, row):
        if 0 <= row < self.doc.page_count:
            self.view.goto_page(row)

    def _thumb_moved(self, *_):
        order = [self.thumbs.item(i).data(Qt.UserRole) for i in range(self.thumbs.count())]
        cur = list(range(self.doc.page_count))
        for new_pos, orig in enumerate(order):
            old_pos = cur.index(orig)
            if old_pos != new_pos:
                self.doc.move_page(old_pos, new_pos)
                cur.insert(new_pos, cur.pop(old_pos))
        self._reload_thumbs()
        self.view.rebuild()

    def _reload_thumbs(self):
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        for i in range(self.doc.page_count):
            png, w, h = self.doc.render_png(i, zoom=0.18)
            img = QImage.fromData(png, "PNG")
            it = QListWidgetItem(QIcon(QPixmap.fromImage(img)), f"{i + 1}")
            it.setData(Qt.UserRole, i)
            self.thumbs.addItem(it)
        self.thumbs.blockSignals(False)
        if 0 <= self.view.cur_page < self.doc.page_count:
            self.thumbs.setCurrentRow(self.view.cur_page)

    def _page_changed(self, i):
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(i + 1)
        self.page_spin.blockSignals(False)
        self.thumbs.blockSignals(True)
        self.thumbs.setCurrentRow(i)
        self.thumbs.blockSignals(False)
        self.update_title()

    # ---------- 툴바 ----------
    # ---------- 리본 UI ----------
    def _rbtn(self, icon, label, fn=None, tool=None):
        b = QToolButton()
        b.setText(f"{icon}\n{label}")
        b.setToolButtonStyle(Qt.ToolButtonTextOnly)
        b.setAutoRaise(True)
        b.setMinimumWidth(50)
        b.setMaximumHeight(58)
        if tool is not None:
            b.setCheckable(True)
            b.clicked.connect(lambda: self._tool_clicked(tool))
            self.tool_btns.addButton(b, tool)
        elif fn:
            b.clicked.connect(fn)
        return b

    def _file_button(self):
        """열기/저장/인쇄를 버튼 하나(메뉴)로."""
        b = QToolButton()
        b.setText("📁\n파일")
        b.setToolButtonStyle(Qt.ToolButtonTextOnly)
        b.setAutoRaise(True)
        b.setMinimumWidth(52)
        b.setMaximumHeight(58)
        b.setPopupMode(QToolButton.InstantPopup)
        mnu = QMenu(self)
        mnu.addAction("열기\tCtrl+O", self.open_file)
        mnu.addAction("저장\tCtrl+S", self.save_file)
        mnu.addAction("다른 이름으로 저장\tCtrl+Shift+S", self.save_as)
        mnu.addSeparator()
        mnu.addAction("인쇄 미리보기\tCtrl+P", self.print_doc)
        mnu.addSeparator()
        mnu.addAction("단축키 설정…", self.open_shortcut_dialog)
        mnu.addSeparator()
        mnu.addAction(f"업데이트 확인  (현재 {APP_VERSION})",
                      lambda: self.check_update(silent=False))
        b.setMenu(mnu)
        return b

    def _vline(self):
        f = QFrame()
        f.setFrameShape(QFrame.VLine)
        f.setStyleSheet("color:#dcdcdc;")
        return f

    def _group(self, title, widgets):
        box = QWidget()
        outer = QVBoxLayout(box)
        outer.setContentsMargins(4, 2, 4, 1)
        outer.setSpacing(1)
        row = QHBoxLayout()
        row.setSpacing(2)
        for w in widgets:
            row.addWidget(w)
        outer.addLayout(row)
        lab = QLabel(title)
        lab.setAlignment(Qt.AlignHCenter)
        f = lab.font()
        f.setPointSize(8)
        lab.setFont(f)
        lab.setStyleSheet("color:#8a8a8a;")
        outer.addWidget(lab)
        return box

    def _tab(self, groups):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(6, 3, 6, 1)
        lay.setSpacing(3)
        for i, g in enumerate(groups):
            if i:
                lay.addWidget(self._vline())
            lay.addWidget(g)
        lay.addStretch(1)
        sa = QScrollArea()
        sa.setWidget(w)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        return sa

    def _build_ribbon(self):
        self.tool_btns = QButtonGroup(self)
        self.tool_btns.setExclusive(True)

        # 검색 묶음
        search_w = QWidget()
        sl = QHBoxLayout(search_w)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(2)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("검색어")
        self.search_box.setFixedWidth(130)
        self.search_box.returnPressed.connect(self.do_search)
        self.search_box.installEventFilter(self)
        sl.addWidget(self.search_box)
        sl.addWidget(self._rbtn("🔎", "찾기/다음", self.do_search))
        sl.addWidget(self._rbtn("▲", "이전", self.prev_hit))
        sl.addWidget(self._rbtn("✖", "표시지움", self.clear_search))

        # 색/굵기 묶음
        self.color_btn = QPushButton("색")
        self.color_btn.setFixedWidth(40)
        self.color_btn.clicked.connect(self.pick_color)
        self._apply_color_btn()
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 20)
        self.width_spin.setValue(2)
        self.width_spin.setFixedWidth(46)
        self.width_spin.valueChanged.connect(lambda v: setattr(self.view, "width", float(v)))
        self.font_spin = QSpinBox()
        self.font_spin.setRange(6, 96)
        self.font_spin.setValue(self.fontsize)
        self.font_spin.setFixedWidth(52)
        self.font_spin.valueChanged.connect(self._set_fontsize)
        style_w = QWidget()
        stl = QHBoxLayout(style_w)
        stl.setContentsMargins(0, 0, 0, 0)
        stl.addWidget(QLabel("색"))
        stl.addWidget(self.color_btn)
        stl.addWidget(QLabel(" 굵기"))
        stl.addWidget(self.width_spin)
        stl.addWidget(QLabel(" 글자크기"))
        stl.addWidget(self.font_spin)

        rib = QTabWidget()
        rib.setMaximumHeight(98)

        # [홈]
        home = self._tab([
            self._group("파일", [self._file_button()]),
            self._group("보기", [
                self._rbtn("↔", "폭맞춤", self.fit_width),
                self._rbtn("⛶", "화면맞춤", self.fit_page),
                self._rbtn("1:1", "실제크기", self.zoom_actual)]),
            self._group("주석", [
                self._rbtn("🖍", "형광펜", tool=T_HILITE),
                self._rbtn("✏", "펜", tool=T_PEN),
                self._rbtn("▭", "사각형", tool=T_RECT),
                self._rbtn("◯", "원", tool=T_CIRCLE),
                self._rbtn("╱", "선", tool=T_LINE)]),
            self._group("삽입/수정", [
                self._rbtn("🅰", "텍스트상자", tool=T_TEXT),
                self._rbtn("🖼", "이미지", self.choose_image)]),
            self._group("스타일", [style_w]),
            self._group("찾기", [search_w]),
            self._group("설정", [
                self._rbtn("⌨", "단축키", self.open_shortcut_dialog)]),
        ])
        rib.addTab(home, "홈")

        # [변환]
        conv = self._tab([
            self._group("변환", [
                self._rbtn("🖼", "PDF→이미지", self.to_images),
                self._rbtn("📑", "이미지→PDF", self.imgs_to_pdf),
                self._rbtn("한", "PDF→HWP", self.to_hwp)]),
        ])
        rib.addTab(conv, "변환")

        self.ribbon = rib
        self.setMenuWidget(rib)
        # 기본 도구: 손/선택
        if self.tool_btns.button(T_PAN):
            self.tool_btns.button(T_PAN).setChecked(True)

    def _set_tool(self, t):
        self.view.set_tool(t)
        self.statusBar().showMessage(f"도구: {TOOL_LABELS[t]}", 2500)

    def _apply_color_btn(self):
        r, g, b = [int(c * 255) for c in self.view.color]
        self.color_btn.setStyleSheet(f"background:rgb({r},{g},{b}); color:white;")

    BASIC_COLORS = [
        ("빨강", (1.0, 0.0, 0.0)), ("파랑", (0.0, 0.0, 1.0)),
        ("검정", (0.0, 0.0, 0.0)), ("초록", (0.0, 0.6, 0.0)),
        ("노랑", (1.0, 0.85, 0.0)), ("주황", (1.0, 0.5, 0.0)),
        ("보라", (0.6, 0.0, 0.8)), ("하늘", (0.0, 0.7, 1.0)),
        ("회색", (0.5, 0.5, 0.5)), ("흰색", (1.0, 1.0, 1.0)),
    ]

    def pick_color(self):
        """색은 자주 쓰는 것만 간단히. 정 필요하면 '다른 색…' 으로."""
        mnu = QMenu(self)
        for name, c in self.BASIC_COLORS:
            pm = QPixmap(18, 18)
            pm.fill(QColor.fromRgbF(*c))
            act = mnu.addAction(QIcon(pm), name)
            act.triggered.connect(lambda _=False, cc=c: self.set_color(cc))
        mnu.addSeparator()
        mnu.addAction("다른 색…", self._pick_color_dialog)
        mnu.exec(self.color_btn.mapToGlobal(
            self.color_btn.rect().bottomLeft()))

    def set_color(self, c):
        self.view.color = c
        self._apply_color_btn()

    def _pick_color_dialog(self):
        c = QColorDialog.getColor(parent=self)
        if c.isValid():
            self.set_color((c.redF(), c.greenF(), c.blueF()))

    # ---------- 메뉴 ----------
    def _build_statusbar(self):
        sb = self.statusBar()
        self.btn_prev = QToolButton(); self.btn_prev.setText("◀")
        self.btn_prev.setAutoRaise(True); self.btn_prev.clicked.connect(self.prev_page)
        self.page_spin = QSpinBox(); self.page_spin.setMinimum(1)
        self.page_spin.setFixedWidth(62)
        self.page_spin.valueChanged.connect(lambda v: self.view.goto_page(v - 1))
        self.page_total = QLabel(" / 0 ")
        self.btn_next = QToolButton(); self.btn_next.setText("▶")
        self.btn_next.setAutoRaise(True); self.btn_next.clicked.connect(self.next_page)
        for w in (self.btn_prev, self.page_spin, self.page_total, self.btn_next):
            sb.addWidget(w)

        # 쪽 관련 기능을 아래쪽에 전부 배치
        sb.addWidget(self._vline())
        for icon, label, fn in (
                ("↺", "왼쪽90°", lambda: self.rotate(-90)),
                ("↻", "오른쪽90°", lambda: self.rotate(90)),
                ("🗑", "쪽삭제", self.delete_page),
                ("✂", "쪽추출", self.extract_pages),
                ("➕", "뒤에합치기", self.merge_pdf),
                ("📚", "여러개병합", self.merge_many)):
            b = QToolButton()
            b.setText(f"{icon} {label}")
            b.setAutoRaise(True)
            b.clicked.connect(fn)
            sb.addWidget(b)
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setFixedWidth(150)
        self.zoom_slider.setRange(25, 400)
        self.zoom_slider.setValue(150)
        self.zoom_slider.valueChanged.connect(self._slider_zoom)
        self.zoom_label = QLabel("150%")
        self.zoom_label.setFixedWidth(42)
        sb.addPermanentWidget(QLabel("확대"))
        sb.addPermanentWidget(self.zoom_slider)
        sb.addPermanentWidget(self.zoom_label)

    def _slider_zoom(self, v):
        self.fit_mode = None
        self.view.set_zoom(v / 100.0)

    def _on_zoom(self, z):
        pct = int(round(z * 100))
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(max(25, min(pct, 400)))
        self.zoom_slider.blockSignals(False)
        self.zoom_label.setText(f"{pct}%")

    def _build_shortcuts(self):
        import json
        keys = dict(DEFAULT_SHORTCUTS)
        cfg = os.path.join(app_dir(), "shortcuts.json")
        try:
            if os.path.exists(cfg):
                with open(cfg, encoding="utf-8") as f:
                    keys.update(json.load(f))
        except Exception:
            pass
        self.shortcut_keys = keys
        actions = {
            "열기": self.open_file, "저장": self.save_file,
            "다른이름저장": self.save_as, "인쇄": self.print_doc,
            "검색": lambda: self.search_box.setFocus(),
            "실행취소": self.undo,
            "확대": lambda: self.zoom_by(1.25),
            "축소": lambda: self.zoom_by(1 / 1.25),
            "폭맞춤": self.fit_width, "화면맞춤": self.fit_page,
            "이전페이지": self.prev_page, "다음페이지": self.next_page,
            "손선택": lambda: self.pick_tool(T_PAN),
            "형광펜": lambda: self.pick_tool(T_HILITE),
            "펜": lambda: self.pick_tool(T_PEN),
            "사각형": lambda: self.pick_tool(T_RECT),
            "원": lambda: self.pick_tool(T_CIRCLE),
            "선": lambda: self.pick_tool(T_LINE),
            "텍스트상자": lambda: self.pick_tool(T_TEXT),
            "이미지": lambda: self.pick_tool(T_IMAGE),
            "다음찾기": self.next_hit, "이전찾기": self.prev_hit,
            "검색표시지움": self.clear_search,
        }
        self._shortcut_actions = []
        for name, fn in actions.items():
            k = keys.get(name)
            if not k:
                continue
            a = QAction(self)
            a.setShortcut(QKeySequence(k))
            a.triggered.connect(fn)
            self.addAction(a)
            self._shortcut_actions.append(a)

    def reload_shortcuts(self):
        for a in self._shortcut_actions:
            self.removeAction(a)
            a.deleteLater()
        self._shortcut_actions = []
        self._build_shortcuts()

    # ---------- 업데이트 ----------
    def check_update(self, silent=True):
        """version.json 을 보고 새 버전이 있으면 알려준다."""
        import json
        import urllib.request
        try:
            req = urllib.request.Request(
                UPDATE_BASE + "version.json",
                headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=6) as r:
                info = json.loads(r.read().decode("utf-8"))
        except Exception as ex:
            if not silent:
                QMessageBox.information(
                    self, APP_NAME,
                    f"업데이트 서버에 연결하지 못했습니다.\n\n{ex}")
            return
        latest = info.get("version", "0")
        if _ver_tuple(latest) <= _ver_tuple(APP_VERSION):
            if not silent:
                QMessageBox.information(
                    self, APP_NAME,
                    f"최신 버전입니다. (현재 {APP_VERSION})")
            return

        notes = info.get("notes", "")
        if getattr(sys, "frozen", False):
            QMessageBox.information(
                self, APP_NAME,
                f"새 버전 {latest} 이 나왔습니다.\n\n{notes}\n\n"
                f"exe 로 쓰고 계셔서 자동 교체가 안 됩니다.\n"
                f"소스 폴더에서 'exe만들기.bat' 을 다시 실행해 주세요.")
            return

        r = QMessageBox.question(
            self, APP_NAME,
            f"새 버전 {latest} 이 나왔습니다. (현재 {APP_VERSION})\n\n"
            f"{notes}\n\n지금 업데이트할까요?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if r == QMessageBox.Yes:
            self._do_update(info)

    def _do_update(self, info):
        import urllib.request
        files = info.get("files") or [
            "main.py", "pdfcore.py", "hwp_convert.py", "fonts.py",
            "requirements.txt", "사용설명서.txt"]
        dest = app_dir()
        got = {}
        try:
            for f in files:
                url = UPDATE_BASE + urllib.parse.quote(f)
                with urllib.request.urlopen(url, timeout=30) as r:
                    got[f] = r.read()
        except Exception as ex:
            QMessageBox.critical(self, APP_NAME, f"내려받기 실패: {ex}")
            return
        try:
            for f, data in got.items():
                with open(os.path.join(dest, f), "wb") as fp:
                    fp.write(data)
        except Exception as ex:
            QMessageBox.critical(self, APP_NAME, f"파일 교체 실패: {ex}")
            return

        if self.doc.is_open() and self.doc.dirty:
            QMessageBox.information(
                self, APP_NAME,
                "업데이트를 받았습니다.\n저장할 내용이 있어 재시작은 하지 않습니다.\n"
                "저장한 뒤 새우PDF 를 다시 켜면 적용됩니다.")
            return
        QMessageBox.information(
            self, APP_NAME, "업데이트 완료. 새우PDF 를 다시 시작합니다.")
        try:
            os.execv(sys.executable, [sys.executable,
                                      os.path.join(dest, "main.py")])
        except Exception:
            QMessageBox.information(self, APP_NAME,
                                    "새우PDF 를 직접 다시 켜 주세요.")
            self.close()

    def open_shortcut_dialog(self):
        ShortcutDialog(self).exec()

    def toggle_letter_shortcuts(self, on):
        """글 입력 중에는 한 글자 단축키(H, P, T...)를 꺼 둔다."""
        for a in self._shortcut_actions:
            s = a.shortcut().toString()
            if "+" not in s and len(s) <= 2:
                a.setEnabled(on)

    def eventFilter(self, obj, ev):
        if obj is getattr(self, "search_box", None):
            if ev.type() == QEvent.FocusIn:
                self.toggle_letter_shortcuts(False)
            elif ev.type() == QEvent.FocusOut:
                self.toggle_letter_shortcuts(True)
        return super().eventFilter(obj, ev)

    def _tool_clicked(self, t):
        """같은 도구를 다시 누르면 해제되어 손/선택으로 돌아간다."""
        if self.view.tool == t and t != T_PAN:
            self.pick_tool(T_PAN)
        else:
            self._set_tool(t)

    def pick_tool(self, t):
        b = self.tool_btns.button(t)
        if b:
            b.setChecked(True)
        else:
            # 손/선택 처럼 리본에 버튼이 없는 도구 → 모든 도구 선택 해제
            self.tool_btns.setExclusive(False)
            for btn in self.tool_btns.buttons():
                btn.setChecked(False)
            self.tool_btns.setExclusive(True)
        self._set_tool(t)

    def _set_fontsize(self, v):
        self.fontsize = v

    # ---------- 실행취소 ----------
    def push_undo(self):
        if not self.doc.is_open():
            return
        try:
            self.undo_stack.append(self.doc.snapshot())
            if len(self.undo_stack) > 20:
                self.undo_stack.pop(0)
        except Exception:
            pass

    def undo(self):
        if not self.undo_stack:
            self.statusBar().showMessage("되돌릴 작업이 없습니다", 2000)
            return
        data = self.undo_stack.pop()
        p = self.view.cur_page
        try:
            self.doc.restore(data)
        except Exception as ex:
            QMessageBox.warning(self, APP_NAME, f"되돌리기 실패: {ex}")
            return
        self.page_total.setText(f" / {self.doc.page_count} ")
        self.page_spin.setMaximum(max(1, self.doc.page_count))
        self._reload_thumbs()
        self.view.rebuild()
        self.view.goto_page(min(p, self.doc.page_count - 1))
        self.statusBar().showMessage("되돌렸습니다 (Ctrl+Z)", 2000)
        self.update_title()

    # ---------- 파일 ----------
    def load(self, path):
        self.doc.open(path)
        self.undo_stack = []
        self.search_hits = []
        self.search_idx = -1
        self.view.cur_page = 0
        self.page_spin.setMaximum(max(1, self.doc.page_count))
        self.page_total.setText(f" / {self.doc.page_count} ")
        self._reload_thumbs()
        self.view.rebuild()
        self.fit_width()
        QTimer.singleShot(0, self.fit_width)   # 창 크기 확정 후 한 번 더
        self.update_title()

    def open_file(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "PDF 열기 (여러 개 선택 가능)", "", "PDF (*.pdf)")
        if paths:
            self.open_many(paths)

    def open_many(self, paths):
        """파일 여러 개를 연다. 2개 이상이면 묻지 않고 바로 합쳐서 연다."""
        files = [p for p in paths if p.lower().endswith(".pdf")]
        if not files:
            if paths:
                self.statusBar().showMessage("PDF 파일만 열 수 있습니다", 3000)
            return
        try:
            if len(files) == 1:
                self.load(files[0])
                return
            # 여러 개를 골랐다 = 합쳐서 보려는 것. 묻지 않고 바로 합친다.
            files = sorted(files)
            tmp = os.path.join(tempfile.gettempdir(), "새우PDF_합본.pdf")
            n = PdfDocument.merge_files(files, tmp)
            self.load(tmp)
            self.statusBar().showMessage(
                f"{len(files)}개를 파일명 순서대로 합쳐서 열었습니다 ({n}쪽). "
                f"따로 저장하려면 Ctrl+Shift+S", 10000)
        except Exception as ex:
            QMessageBox.critical(self, APP_NAME, f"열기 실패: {ex}")

    def merge_many(self):
        """여러 PDF 를 골라 하나로 병합해 저장하고 바로 연다."""
        files, _ = QFileDialog.getOpenFileNames(
            self, "병합할 PDF 선택 (여러 개)", "", "PDF (*.pdf)")
        if not files:
            return
        if len(files) < 2:
            QMessageBox.information(self, APP_NAME, "2개 이상 골라주세요.")
            return
        files = sorted(files)
        out, _ = QFileDialog.getSaveFileName(
            self, "합친 파일 저장", "합본.pdf", "PDF (*.pdf)")
        if not out:
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"
        try:
            n = PdfDocument.merge_files(files, out)
            self.load(out)
            QMessageBox.information(
                self, APP_NAME,
                f"{len(files)}개를 합쳤습니다 (총 {n}쪽).\n파일명 순서대로 합칩니다.")
        except Exception as ex:
            QMessageBox.critical(self, APP_NAME, f"병합 실패: {ex}")

    # ---------- 드래그해서 열기 ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        e.acceptProposedAction()
        if paths:
            self.open_many(paths)

    def save_file(self):
        if not self.doc.is_open():
            return
        if self.doc.path:
            try:
                self.doc.save()
                self.statusBar().showMessage("저장됨", 2000)
            except Exception as ex:
                QMessageBox.critical(self, APP_NAME, f"저장 실패: {ex}")
        else:
            self.save_as()
        self.update_title()

    def save_as(self):
        if not self.doc.is_open():
            return
        path, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 저장", "", "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            self.doc.save(path)
            self.statusBar().showMessage("저장됨", 2000)
        except Exception as ex:
            QMessageBox.critical(self, APP_NAME, f"저장 실패: {ex}")
        self.update_title()

    # ---------- 페이지 이동 ----------
    def prev_page(self):
        self.view.goto_page(max(0, self.view.cur_page - 1))

    def next_page(self):
        self.view.goto_page(min(self.doc.page_count - 1, self.view.cur_page + 1))

    def fit_width(self):
        """가로를 화면에 꽉 채운다 (창 크기가 바뀌면 자동으로 따라감)."""
        if not self.doc.is_open():
            return
        self.fit_mode = "width"
        wpt, hpt = self.doc.page_size(self.view.cur_page)
        avail = self.view.viewport().width() - 2 * GAP - 4
        self.view.set_zoom(max(0.25, avail / wpt))

    def fit_page(self):
        """페이지 한 장이 화면에 통째로 들어오게."""
        if not self.doc.is_open():
            return
        self.fit_mode = "page"
        wpt, hpt = self.doc.page_size(self.view.cur_page)
        aw = self.view.viewport().width() - 2 * GAP - 4
        ah = self.view.viewport().height() - 2 * GAP - 4
        self.view.set_zoom(max(0.25, min(aw / wpt, ah / hpt)))

    def zoom_by(self, factor):
        self.fit_mode = None
        self.view.set_zoom(self.view.zoom * factor)

    def zoom_actual(self):
        self.fit_mode = None
        self.view.set_zoom(1.0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.doc.is_open() and self.fit_mode:
            QTimer.singleShot(60, self._refit)

    def _refit(self):
        if self.fit_mode == "width":
            self.fit_width()
        elif self.fit_mode == "page":
            self.fit_page()

    # ---------- 페이지 편집 ----------
    def rotate(self, deg):
        if self.doc.is_open():
            p = self.view.cur_page
            self.push_undo()
            self.doc.rotate_page(p, deg)
            self.view.rebuild()
            self.view.goto_page(p)
            self.update_title()

    def delete_page(self):
        if not self.doc.is_open() or self.doc.page_count <= 1:
            return
        p = self.view.cur_page
        if QMessageBox.question(self, APP_NAME, f"{p + 1}페이지를 삭제할까요?") == QMessageBox.Yes:
            self.push_undo()
            self.doc.delete_page(p)
            self.page_total.setText(f" / {self.doc.page_count} ")
            self.page_spin.setMaximum(self.doc.page_count)
            self.view.cur_page = min(p, self.doc.page_count - 1)
            self._reload_thumbs()
            self.view.rebuild()
            self.update_title()

    def extract_pages(self):
        if not self.doc.is_open():
            return
        txt, ok = QInputDialog.getText(self, "페이지 추출",
                                       f"추출할 페이지 (예: 1,3,5-7)  전체 {self.doc.page_count}p:")
        if not ok or not txt.strip():
            return
        idx = self._parse_pages(txt)
        if not idx:
            return
        path, _ = QFileDialog.getSaveFileName(self, "추출 저장", "", "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        self.doc.extract_pages(idx, path)
        QMessageBox.information(self, APP_NAME, f"{len(idx)}페이지를 저장했습니다.")

    def _parse_pages(self, txt):
        out = []
        for part in txt.replace(" ", "").split(","):
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-")
                out.extend(range(int(a) - 1, int(b)))
            else:
                out.append(int(part) - 1)
        return [i for i in out if 0 <= i < self.doc.page_count]

    def merge_pdf(self):
        if not self.doc.is_open():
            return
        path, _ = QFileDialog.getOpenFileName(self, "합칠 PDF 선택", "", "PDF (*.pdf)")
        if not path:
            return
        self.push_undo()
        self.doc.insert_pdf_file(path)
        self.page_total.setText(f" / {self.doc.page_count} ")
        self.page_spin.setMaximum(self.doc.page_count)
        self._reload_thumbs()
        self.view.rebuild()
        QMessageBox.information(self, APP_NAME, "뒤에 합쳤습니다.")

    # ---------- 변환 ----------
    def to_images(self):
        if not self.doc.is_open():
            return
        d = QFileDialog.getExistingDirectory(self, "이미지 저장 폴더")
        if not d:
            return
        fmt, ok = QInputDialog.getItem(self, "형식", "이미지 형식:", ["png", "jpg"], 0, False)
        if not ok:
            return
        files = self.doc.export_images(d, fmt=fmt, dpi=150)
        QMessageBox.information(self, APP_NAME, f"{len(files)}개 저장 완료:\n{d}")

    def imgs_to_pdf(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "PDF 로 만들 이미지들", "", "이미지 (*.png *.jpg *.jpeg *.bmp *.tif)")
        if not files:
            return
        path, _ = QFileDialog.getSaveFileName(self, "PDF 저장", "", "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        PdfDocument.images_to_pdf(files, path)
        QMessageBox.information(self, APP_NAME, "PDF 생성 완료.")

    def to_hwp(self):
        if not self.doc.is_open():
            return
        path, _ = QFileDialog.getSaveFileName(self, "HWP 저장", "", "HWP (*.hwp)")
        if not path:
            return
        if not path.lower().endswith(".hwp"):
            path += ".hwp"
        try:
            self.doc.to_hwp(path)
            QMessageBox.information(self, APP_NAME, "HWP 변환 완료.")
        except HwpNotAvailable as ex:
            QMessageBox.warning(self, APP_NAME, str(ex))
        except Exception as ex:
            QMessageBox.critical(self, APP_NAME, f"변환 실패: {ex}")

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "삽입할 이미지", "", "이미지 (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.pending_image = path
            self.tool_combo.setCurrentIndex(T_IMAGE)
            self.statusBar().showMessage("이미지를 넣을 영역을 드래그하세요", 4000)

    # ---------- 검색 ----------
    def do_search(self):
        if not self.doc.is_open():
            return
        q = self.search_box.text().strip()
        if not q:                       # 검색어를 비우고 Enter → 표시 지우기
            self.clear_search()
            return
        # 같은 검색어를 다시 누르면 다음 결과로 이동
        if q == getattr(self, "_last_query", None) and self.search_hits:
            self.next_hit()
            return
        self._last_query = q
        self.search_hits = []
        for pi, rects in self.doc.search(q):
            for r in rects:
                self.search_hits.append((pi, r))
        if not self.search_hits:
            self.view.clear_search_marks()
            self.statusBar().showMessage("결과 없음", 2000)
            return
        self.search_idx = -1
        self.next_hit()

    def clear_search(self):
        """검색 결과와 노란 표시를 모두 지운다."""
        self.search_hits = []
        self.search_idx = -1
        self._last_query = None
        self.view.clear_search_marks()
        self.search_box.clear()
        self.statusBar().showMessage("검색 표시를 지웠습니다", 2000)

    def _show_hit(self):
        pi, r = self.search_hits[self.search_idx]
        self.view.goto_hit(pi, r)
        self.view.show_search_marks(self.search_hits, self.search_idx)
        self.statusBar().showMessage(
            f"{self.search_idx + 1} / {len(self.search_hits)}  ({pi + 1}쪽)  "
            f"— 주황색이 지금 보고 있는 곳", 5000)

    def next_hit(self):
        if not self.search_hits:
            return
        self.search_idx = (self.search_idx + 1) % len(self.search_hits)
        self._show_hit()

    def prev_hit(self):
        if not self.search_hits:
            return
        self.search_idx = (self.search_idx - 1) % len(self.search_hits)
        self._show_hit()

    # ---------- 인쇄 ----------
    def print_doc(self):
        """Ctrl+P → 인쇄 미리보기 창 (여기서 확인하고 인쇄)."""
        if not self.doc.is_open():
            return
        printer = QPrinter(QPrinter.HighResolution)
        printer.setDocName(os.path.basename(self.doc.path or "문서"))
        dlg = QPrintPreviewDialog(printer, self)
        dlg.setWindowTitle("인쇄 미리보기")
        dlg.resize(1000, 820)
        dlg.paintRequested.connect(self._paint_pages)
        dlg.exec()

    def _paint_pages(self, printer):
        painter = QPainter(printer)
        pr = printer.pageRect(QPrinter.DevicePixel)
        for i in range(self.doc.page_count):
            if i > 0:
                printer.newPage()
            png, w, h = self.doc.render_png(i, zoom=2.0)
            img = QImage.fromData(png, "PNG")
            scaled = img.scaled(int(pr.width()), int(pr.height()),
                                Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = max(0, (pr.width() - scaled.width()) / 2)
            y = max(0, (pr.height() - scaled.height()) / 2)
            painter.drawImage(int(x), int(y), scaled)
        painter.end()

    # ---------- 기타 ----------
    def update_title(self):
        name = os.path.basename(self.doc.path) if self.doc.path else "새 문서"
        star = "*" if self.doc.dirty else ""
        total = self.doc.page_count
        if total:
            self.setWindowTitle(
                f"{APP_NAME} — {name}{star}  ({self.view.cur_page + 1}/{total})")
        else:
            self.setWindowTitle(APP_NAME)

    def closeEvent(self, e):
        if self.doc.is_open() and self.doc.dirty:
            r = QMessageBox.question(self, APP_NAME, "저장하지 않은 변경이 있습니다. 저장할까요?",
                                     QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if r == QMessageBox.Yes:
                self.save_file()
            elif r == QMessageBox.Cancel:
                e.ignore()
                return
        e.accept()


def apply_theme(app, dark=False):
    """업무용 밝은 테마 고정."""
    app.setStyle("Fusion")
    app.setPalette(app.style().standardPalette())


def main():
    app = QApplication(sys.argv)
    apply_theme(app, False)
    w = MainWindow()
    w.show()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pdf"):
        try:
            w.load(sys.argv[1])
        except Exception:
            pass
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
LiveDraw - Overlay de dessin / sketch sur le Viewer de Nuke
------------------------------------------------------------
Overlay confine a la zone du Viewer. Ne bloque QUE le pan/zoom du Viewer ;
node graph, properties, timeline restent utilisables normalement.

L'interface (palette verticale) est ancree en haut a gauche du Viewer,
a taille fixe, quelle que soit la taille du Viewer.

Outils : Crayon, Ligne, Rectangle, Ovale, Gomme.
Couleurs, 3 tailles, opacite globale, Undo/Redo (Clear inclus), Hide,
Save versionne (Viewer + traits), bouton dossier, persistance auto.

Auteur : genere pour Gabin (ArtFX).
Compatible PySide2 (Nuke < 15) et PySide6 (Nuke >= 15).
"""

import os
import json

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    _PYSIDE = 6
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    _PYSIDE = 2

Qt = QtCore.Qt


# --- Constantes --------------------------------------------------------------
COLORS = [
    "#3B5BC4", "#4FA8D8", "#5FCE5A", "#EBCB4A", "#F0902B",
    "#E24A4A", "#C463D6", "#E6E6E6", "#8A8A8A", "#2B2B2B",
]
DEFAULT_COLOR = "#F0902B"  # orange
WIDTHS = {"S": 4, "M": 10, "L": 20}
DOT_R = {"S": 2.5, "M": 4.5, "L": 7.0}

AUTOSAVE = os.path.join(os.path.expanduser("~"), ".nuke", "livedraw_autosave.json")
ACCENT = "#E8853B"

# Position/taille fixe de la palette (relative au coin haut-gauche du Viewer)
PAL_MARGIN = 16    # marge gauche
PAL_TOP = 54       # decalage vers le bas (dans la zone noire du viewer)


# ---------------------------------------------------------------- utilitaires
def _nuke_main_window():
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    candidates = []
    for w in app.topLevelWidgets():
        try:
            cls = w.metaObject().className()
        except Exception:
            cls = ""
        if "DockMainWindow" in cls:
            return w
        if isinstance(w, QtWidgets.QMainWindow) and w.isVisible():
            candidates.append(w)
    if candidates:
        return max(candidates, key=lambda x: x.width() * x.height())
    return None


def _find_viewer_widget():
    """Trouve le widget du viewport (image) du Viewer actif de Nuke."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None

    def scan(pred):
        best, ba = None, 0
        for w in app.allWidgets():
            try:
                if not w.isVisible():
                    continue
                cls = w.metaObject().className()
                name = w.objectName()
            except Exception:
                continue
            if pred(cls, name):
                a = w.width() * w.height()
                if a > ba:
                    best, ba = w, a
        return best

    w = scan(lambda c, n: "glviewport" in c.lower())
    if w:
        return w
    w = scan(lambda c, n: "viewport" in c.lower())
    if w:
        return w
    return scan(lambda c, n: "viewer" in c.lower() or n.lower().startswith("viewer"))


def _sketch_dir():
    try:
        import nuke
        root = nuke.root().name()
        if root and root != "Root":
            base = os.path.dirname(root)
            if base and os.path.isdir(base):
                return os.path.join(base, "LiveDraw")
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents", "LiveDraw")


def _screen_of(point):
    app = QtWidgets.QApplication.instance()
    if _PYSIDE == 6:
        return app.screenAt(point) or app.primaryScreen()
    n = app.desktop().screenNumber(point)
    return app.screens()[n]


# ------------------------------------------------------------------- icones
def _icon(kind, px=18, r=4.0):
    pm = QtGui.QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    col = QtGui.QColor("#e2e2e2")
    pen = QtGui.QPen(col, 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    a, b, c = px * 0.20, px * 0.80, px * 0.5
    P = QtCore.QPointF

    if kind == "dot":
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(P(c, c), r, r)

    elif kind == "pen":
        p.drawLine(P(b, a), P(a + px * 0.12, b - px * 0.12))
        p.setBrush(col)
        p.drawPolygon([P(a, b), P(a + px * 0.10, b - px * 0.16), P(a + px * 0.16, b - px * 0.10)])

    elif kind == "line":
        p.drawLine(P(a, b), P(b, a))

    elif kind == "rect":
        p.setBrush(Qt.NoBrush)
        p.drawRect(QtCore.QRectF(a, px * 0.28, b - a, px * 0.44))

    elif kind == "ellipse":
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QtCore.QRectF(a, px * 0.28, b - a, px * 0.44))

    elif kind == "eraser":
        p.setBrush(QtGui.QColor("#e2e2e2"))
        p.save()
        p.translate(c, c)
        p.rotate(-35)
        p.drawRoundedRect(QtCore.QRectF(-px * 0.28, -px * 0.16, px * 0.56, px * 0.32), 2, 2)
        p.drawLine(QtCore.QPointF(0, -px * 0.16), QtCore.QPointF(0, px * 0.16))
        p.restore()

    elif kind in ("undo", "redo"):
        rect = QtCore.QRectF(px * 0.22, px * 0.24, px * 0.56, px * 0.56)
        if kind == "undo":
            p.drawArc(rect, 90 * 16, 200 * 16)
            head = P(px * 0.30, px * 0.30)
            p.drawLine(head, P(px * 0.30, px * 0.50))
            p.drawLine(head, P(px * 0.48, px * 0.30))
        else:
            p.drawArc(rect, 90 * 16, -200 * 16)
            head = P(px * 0.70, px * 0.30)
            p.drawLine(head, P(px * 0.70, px * 0.50))
            p.drawLine(head, P(px * 0.52, px * 0.30))

    elif kind == "trash":
        p.drawLine(P(a, px * 0.32), P(b, px * 0.32))
        p.drawLine(P(px * 0.40, px * 0.24), P(px * 0.60, px * 0.24))
        body = QtGui.QPainterPath()
        body.moveTo(px * 0.30, px * 0.32)
        body.lineTo(px * 0.35, px * 0.78)
        body.lineTo(px * 0.65, px * 0.78)
        body.lineTo(px * 0.70, px * 0.32)
        p.drawPath(body)

    elif kind == "save":
        p.drawRoundedRect(QtCore.QRectF(a, a, b - a, b - a), 2, 2)
        p.drawRect(QtCore.QRectF(px * 0.34, px * 0.20, px * 0.32, px * 0.20))
        p.drawRect(QtCore.QRectF(px * 0.34, px * 0.52, px * 0.32, px * 0.26))

    elif kind == "folder":
        path = QtGui.QPainterPath()
        path.moveTo(a, px * 0.32)
        path.lineTo(px * 0.44, px * 0.32)
        path.lineTo(px * 0.52, px * 0.42)
        path.lineTo(b, px * 0.42)
        path.lineTo(b, b)
        path.lineTo(a, b)
        path.closeSubpath()
        p.drawPath(path)

    elif kind in ("eye", "eye_off"):
        path = QtGui.QPainterPath()
        path.moveTo(a, c)
        path.quadTo(c, px * 0.22, b, c)
        path.quadTo(c, px * 0.78, a, c)
        p.drawPath(path)
        p.setBrush(col)
        p.drawEllipse(P(c, c), px * 0.10, px * 0.10)
        if kind == "eye_off":
            p.setBrush(Qt.NoBrush)
            p.drawLine(P(a, b), P(b, a))

    elif kind == "close":
        p.drawLine(P(a, a), P(b, b))
        p.drawLine(P(a, b), P(b, a))

    p.end()
    return QtGui.QIcon(pm)


# ----------------------------------------------------------------- structures
class Element(object):
    """Un element de dessin : free / line / rect / ellipse (+ gomme)."""
    def __init__(self, kind, color, width, eraser=False):
        self.kind = kind
        self.points = []
        self.color = color
        self.width = width
        self.eraser = eraser

    def to_dict(self):
        c = self.color
        return {
            "kind": self.kind,
            "color": [c.red(), c.green(), c.blue(), c.alpha()],
            "width": self.width,
            "eraser": self.eraser,
            "points": [[p.x(), p.y()] for p in self.points],
        }

    @staticmethod
    def from_dict(d):
        e = Element(d.get("kind", "free"), QtGui.QColor(*d["color"]),
                    d["width"], d.get("eraser", False))
        e.points = [QtCore.QPoint(int(x), int(y)) for x, y in d["points"]]
        return e


# ======================================================================= CANVAS
class Canvas(QtWidgets.QWidget):
    """Fenetre superposee au Viewer : surface de dessin + palette enfant."""

    def __init__(self, controller, parent=None):
        super(Canvas, self).__init__(parent)
        self.controller = controller

        flags = Qt.FramelessWindowHint | Qt.Tool
        # PAS de WindowStaysOnTopHint : sinon la fenetre flotte au-dessus de
        # toutes les applications. Parentee a Nuke, elle reste au-dessus du
        # Viewer mais passe derriere quand on change d'appli.
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("LiveDraw")
        self.setCursor(Qt.CrossCursor)
        self.resize(400, 300)

        # etat de dessin
        self.strokes = []
        self._undo = []
        self._redo = []
        self.current = None
        self.color = QtGui.QColor(DEFAULT_COLOR)
        self.width = WIDTHS["M"]
        self.tool = "pen"
        self.strokes_visible = True
        self.global_opacity = 1.0

        self.canvas = QtGui.QPixmap(self.size())
        self.canvas.fill(Qt.transparent)

        # palette : fenetre Tool separee, "possedee" par le canvas (reste
        # au-dessus de lui, deplacable nativement, ne flotte pas sur les
        # autres applis). Positionnee par le controleur.
        self.palette = Palette(self)

    # -- historique (undo/redo, Clear inclus) --------------------------------
    def _commit(self, new_strokes):
        self._undo.append(list(self.strokes))
        if len(self._undo) > 200:
            self._undo.pop(0)
        self._redo = []
        self.strokes = new_strokes
        self._render_all()
        self.update()
        self.controller.autosave()

    def undo(self):
        if self._undo:
            self._redo.append(list(self.strokes))
            self.strokes = self._undo.pop()
            self._render_all()
            self.update()
            self.controller.autosave()

    def redo(self):
        if self._redo:
            self._undo.append(list(self.strokes))
            self.strokes = self._redo.pop()
            self._render_all()
            self.update()
            self.controller.autosave()

    def clear_all(self):
        if self.strokes:
            self._commit([])

    # -- rendu ----------------------------------------------------------------
    def _draw_element(self, painter, el):
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        if el.eraser:
            painter.setCompositionMode(QtGui.QPainter.CompositionMode_Clear)
            pen = QtGui.QPen(QtGui.QColor(0, 0, 0, 255), el.width)
        else:
            painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
            pen = QtGui.QPen(el.color, el.width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        pts = el.points
        if not pts:
            return
        if el.kind == "free":
            if len(pts) == 1:
                painter.drawPoint(pts[0])
            else:
                for i in range(1, len(pts)):
                    painter.drawLine(pts[i - 1], pts[i])
        elif len(pts) >= 2:
            if el.kind == "line":
                painter.drawLine(pts[0], pts[1])
            elif el.kind == "rect":
                painter.drawRect(QtCore.QRect(pts[0], pts[1]).normalized())
            elif el.kind == "ellipse":
                painter.drawEllipse(QtCore.QRect(pts[0], pts[1]).normalized())

    def _render_all(self):
        self.canvas = QtGui.QPixmap(self.size())
        self.canvas.fill(Qt.transparent)
        p = QtGui.QPainter(self.canvas)
        for e in self.strokes:
            self._draw_element(p, e)
        p.end()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 1))
        if self.strokes_visible:
            painter.setOpacity(self.global_opacity)
            painter.drawPixmap(0, 0, self.canvas)
            if self.current is not None and self.current.kind != "free":
                self._draw_element(painter, self.current)
            painter.setOpacity(1.0)

    # -- souris ---------------------------------------------------------------
    def _pos(self, event):
        if _PYSIDE == 6:
            return event.position().toPoint()
        return event.pos()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        kind = "free" if self.tool in ("pen", "eraser") else self.tool
        eraser = (self.tool == "eraser")
        self.current = Element(kind, QtGui.QColor(self.color), self.width, eraser)
        self.current.points.append(self._pos(event))

    def mouseMoveEvent(self, event):
        if self.current is None:
            return
        pt = self._pos(event)
        if self.current.kind == "free":
            self.current.points.append(pt)
            p = QtGui.QPainter(self.canvas)
            seg = Element("free", self.current.color, self.current.width, self.current.eraser)
            seg.points = self.current.points[-2:]
            self._draw_element(p, seg)
            p.end()
        else:
            if len(self.current.points) == 1:
                self.current.points.append(pt)
            else:
                self.current.points[1] = pt
        self.update()

    def mouseReleaseEvent(self, event):
        if self.current is None:
            return
        el = self.current
        self.current = None
        if el.kind != "free" and len(el.points) < 2:
            return
        # ajoute via l'historique (annulable)
        self._commit(self.strokes + [el])

    def resizeEvent(self, event):
        self._render_all()

    # -- reglages -------------------------------------------------------------
    def set_color(self, hexc):
        self.color = QtGui.QColor(hexc)

    def set_width(self, key):
        self.width = WIDTHS[key]

    def set_tool(self, name):
        self.tool = name

    def set_visible(self, visible):
        self.strokes_visible = visible
        self.update()

    def set_opacity(self, value):
        self.global_opacity = max(0.0, min(1.0, value))
        self.update()

    # -- save -----------------------------------------------------------------
    def _next_version(self, folder):
        v = 1
        if os.path.isdir(folder):
            import re
            for f in os.listdir(folder):
                m = re.match(r"sketch_v(\d+)\.png$", f)
                if m:
                    v = max(v, int(m.group(1)) + 1)
        return v

    def save_version(self):
        region = self.geometry()
        folder = _sketch_dir()
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            self.controller.notify("Impossible de creer le dossier : %s" % e)
            return
        v = self._next_version(folder)

        app = QtWidgets.QApplication.instance()
        scr = _screen_of(region.topLeft())
        self.palette.hide()
        app.processEvents()
        full = scr.grabWindow(0)
        self.palette.show()
        dpr = full.devicePixelRatio()
        sg = scr.geometry()
        crop = full.copy(
            int((region.x() - sg.x()) * dpr), int((region.y() - sg.y()) * dpr),
            int(region.width() * dpr), int(region.height() * dpr))
        crop.setDevicePixelRatio(1.0)
        crop.save(os.path.join(folder, "sketch_v%03d.png" % v), "PNG")
        self.canvas.save(os.path.join(folder, "sketch_v%03d_draw.png" % v), "PNG")
        self.controller.notify("Sauvegarde v%03d -> %s" % (v, folder))

    # -- clavier --------------------------------------------------------------
    def keyPressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_Z:
            if event.modifiers() & Qt.ShiftModifier:
                self.redo()
            else:
                self.undo()
        elif event.key() == Qt.Key_Escape:
            self.controller.close()

    # -- persistance ----------------------------------------------------------
    def serialize(self):
        return {"strokes": [e.to_dict() for e in self.strokes]}

    def restore(self, data):
        try:
            self.strokes = [Element.from_dict(d) for d in data.get("strokes", [])]
            self._undo = []
            self._redo = []
            self._render_all()
            self.update()
        except Exception as e:
            print("LiveDraw: restauration echouee:", e)


# ====================================================================== PALETTE
class _DragBar(QtWidgets.QWidget):
    """Barre de titre : permet de deplacer la palette a la souris."""

    def __init__(self, palette):
        super(_DragBar, self).__init__(palette)
        self.palette = palette
        self._press = None
        self._start = None
        self.setCursor(Qt.SizeAllCursor)
        self.setMinimumHeight(20)

    def paintEvent(self, event):
        # fond alpha=1 : rend TOUTE la bande cliquable (sinon seuls les pixels
        # opaques - le texte - captent la souris sur une fenetre translucide)
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 1))
        p.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        # 1) deplacement natif de l'OS (fonctionne dans Nuke)
        if self.palette.system_move():
            event.accept()
            return
        # 2) repli manuel
        self._press = _gpos(event)
        self._start = self.palette.pos()
        self.grabMouse()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._press is not None:
            self.palette.move(self._start + (_gpos(event) - self._press))
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._press is not None:
            self._press = None
            self.releaseMouse()
            event.accept()


class Palette(QtWidgets.QFrame):
    """Palette verticale, enfant du Canvas, ancree en haut a gauche."""

    def __init__(self, canvas):
        super(Palette, self).__init__(canvas)
        self.canvas = canvas
        # fenetre Tool separee possedee par le canvas : deplacable nativement
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setObjectName("bar")
        self.setStyleSheet(self._style())
        self._build()

    def _style(self):
        return """
        QFrame#bar { background-color: #3a3a3a; border: 1px solid #262626;
                     border-radius: 5px; }
        QLabel#title { color: #cfcfcf; font-weight: bold; font-size: 10px; }
        QLabel { color: #b0b0b0; font-size: 9px; }
        QPushButton { background-color: #4a4a4a; color: #dcdcdc;
                      border: 1px solid #262626; border-radius: 3px; }
        QPushButton:hover { background-color: #565656; }
        QPushButton:checked { background-color: #5a5a5a; border: 1px solid %s; }
        QPushButton#flat { background: transparent; border: none; }
        QPushButton#flat:hover { background-color: #4a4a4a; }
        QSlider::groove:vertical { width: 8px; background: #2b2b2b;
                                   border-radius: 4px; }
        QSlider::handle:vertical { background: %s; height: 18px;
                                   margin: 0 -8px; border-radius: 4px; }
        QSlider::add-page:vertical { background: #6a6a6a; border-radius: 4px; }
        QSlider::sub-page:vertical { background: #2b2b2b; border-radius: 4px; }
        """ % (ACCENT, ACCENT)

    CBTN = 24   # taille bouton couleur
    BTN = 26    # taille bouton outil/action
    HEADER_H = 24  # zone de drag (barre de titre)

    def _mk(self, icon, tip, slot, checkable=False):
        b = QtWidgets.QPushButton()
        b.setFixedSize(self.BTN, self.BTN)
        b.setIcon(icon)
        b.setToolTip(tip)
        b.setCheckable(checkable)
        b.clicked.connect(slot)
        return b

    def _build(self):
        self._drag = None
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(7, 5, 7, 7)
        root.setSpacing(6)
        root.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)

        # header : barre de titre deplacable + fermer
        bar = _DragBar(self)
        head = QtWidgets.QHBoxLayout(bar)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(2)
        title = QtWidgets.QLabel("LiveDraw")
        title.setObjectName("title")
        title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        head.addWidget(title)
        head.addStretch()
        b_close = QtWidgets.QPushButton()
        b_close.setObjectName("flat")
        b_close.setFixedSize(16, 16)
        b_close.setIcon(_icon("close", 13))
        b_close.setToolTip("Fermer")
        b_close.clicked.connect(self.canvas.controller.close)
        head.addWidget(b_close)
        root.addWidget(bar)

        # ---- corps : grille [ couleurs | tailles+outils ] + opacite ---------
        # Les couleurs occupent la colonne 0 ; tailles+outils la colonne 1 sur
        # les memes rangees. Les actions sont alignees en bas sur 2 colonnes :
        # gauche (undo/clear/save) sous les couleurs, droite (redo/hide/folder)
        # sous les outils.
        body = QtWidgets.QHBoxLayout()
        body.setSpacing(8)

        g = QtWidgets.QGridLayout()
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(4)

        # couleurs (colonne 0)
        self.color_btns = []
        for i, hexc in enumerate(COLORS):
            b = QtWidgets.QPushButton()
            b.setFixedSize(self.CBTN, self.CBTN)
            b.setCheckable(True)
            b.setStyleSheet(
                "QPushButton { background-color: %s; border-radius: %dpx;"
                " border: 2px solid #2b2b2b; }"
                " QPushButton:checked { border: 2px solid white; }"
                % (hexc, self.CBTN // 2))
            b.clicked.connect(lambda checked=False, c=hexc: self._pick_color(c))
            g.addWidget(b, i, 0, Qt.AlignHCenter)
            self.color_btns.append((b, hexc))
        n_colors = len(COLORS)

        # tailles (colonne 1, en haut)
        self.width_btns = {}
        for i, key in enumerate(("L", "M", "S")):
            b = QtWidgets.QPushButton()
            b.setFixedSize(self.BTN, self.BTN)
            b.setCheckable(True)
            b.setIcon(_icon("dot", 22, DOT_R[key]))
            b.setToolTip("Taille %s (%dpx)" % (key, WIDTHS[key]))
            b.clicked.connect(lambda checked=False, k=key: self._pick_width(k))
            g.addWidget(b, i, 1, Qt.AlignHCenter)
            self.width_btns[key] = b

        # outils (colonne 1) : dessin, puis clear + hide empiles avec eux
        # (pas de separateur : colonnes a hauteur egale, aucun trou)
        self.tool_btns = {}
        for i, (name, tip) in enumerate(
                (("pen", "Crayon"), ("line", "Ligne"), ("rect", "Rectangle"),
                 ("ellipse", "Ovale / cercle"), ("eraser", "Gomme"))):
            b = self._mk(_icon(name), tip,
                         lambda checked=False, n=name: self._pick_tool(n), True)
            g.addWidget(b, 3 + i, 1, Qt.AlignHCenter)
            self.tool_btns[name] = b

        self.btn_hide = self._mk(_icon("eye"), "Masquer / afficher les traits",
                                 self._toggle_hide, True)
        g.addWidget(self._mk(_icon("trash"), "Tout effacer (annulable)", self.canvas.clear_all),
                    8, 1, Qt.AlignHCenter)
        g.addWidget(self.btn_hide, 9, 1, Qt.AlignHCenter)

        # actions alignees en bas : 2 colonnes (undo/redo, save/explorer)
        ar = 10
        g.addWidget(self._mk(_icon("undo"), "Annuler (Ctrl+Z)", self.canvas.undo), ar, 0, Qt.AlignHCenter)
        g.addWidget(self._mk(_icon("redo"), "Retablir (Ctrl+Shift+Z)", self.canvas.redo), ar, 1, Qt.AlignHCenter)
        g.addWidget(self._mk(_icon("save"), "Enregistrer (Viewer + traits)", self.canvas.save_version), ar + 1, 0, Qt.AlignHCenter)
        g.addWidget(self._mk(_icon("folder"), "Ouvrir le dossier des croquis", self._open_folder), ar + 1, 1, Qt.AlignHCenter)
        body.addLayout(g)
        body.addSpacing(6)

        # colonne droite : opacite (en haut, slider descend jusqu'en bas, aere)
        col_o = QtWidgets.QVBoxLayout()
        col_o.setSpacing(8)
        col_o.setContentsMargins(0, 0, 0, 6)
        op_title = QtWidgets.QLabel("Opacity")
        op_title.setAlignment(Qt.AlignHCenter)
        op_title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        col_o.addWidget(op_title)
        self.op_lbl = QtWidgets.QLabel("100")
        self.op_lbl.setAlignment(Qt.AlignHCenter)
        self.op_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        col_o.addWidget(self.op_lbl)
        self.slider = QtWidgets.QSlider(Qt.Vertical)
        self.slider.setRange(10, 100)
        self.slider.setValue(100)
        self.slider.setFixedWidth(26)
        self.slider.setSizePolicy(QtWidgets.QSizePolicy.Fixed,
                                  QtWidgets.QSizePolicy.Expanding)
        self.slider.setToolTip("Opacite du dessin")
        self.slider.valueChanged.connect(self._set_opacity)
        col_o.addWidget(self.slider, 1, Qt.AlignHCenter)
        body.addLayout(col_o)

        root.addLayout(body)

        # etats initiaux
        self._pick_color(DEFAULT_COLOR)
        self._pick_width("M")
        self._pick_tool("pen")
        self.adjustSize()

    # -- deplacement de la palette (drag depuis le fond / le titre) ----------
    def system_move(self):
        """Delegue le deplacement a l'OS (fiable pour fenetre sans bord)."""
        try:
            win = self.windowHandle()
            if win is not None:
                win.startSystemMove()
                return True
        except Exception:
            pass
        return False

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            self._drag = None
            return
        if self.system_move():
            event.accept()
            return
        self._drag = (_gpos(event), self.pos())
        self.grabMouse()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self.move(self._drag[1] + (_gpos(event) - self._drag[0]))

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            self._drag = None
            self.releaseMouse()

    def _sep(self):
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet("background:#2b2b2b; border:none;")
        return line

    # -- slots ---------------------------------------------------------------
    def _pick_color(self, hexc):
        self.canvas.set_color(hexc)
        for b, c in self.color_btns:
            b.setChecked(c == hexc)
        if self.canvas.tool == "eraser":
            self._pick_tool("pen")

    def _pick_width(self, key):
        self.canvas.set_width(key)
        for k, b in self.width_btns.items():
            b.setChecked(k == key)

    def _pick_tool(self, name):
        self.canvas.set_tool(name)
        for n, b in self.tool_btns.items():
            b.setChecked(n == name)

    def _toggle_hide(self):
        hidden = self.btn_hide.isChecked()
        self.canvas.set_visible(not hidden)
        self.btn_hide.setIcon(_icon("eye_off" if hidden else "eye"))

    def _set_opacity(self, value):
        self.canvas.set_opacity(value / 100.0)
        self.op_lbl.setText("%d" % value)

    def _open_folder(self):
        open_sketch_folder()


# =================================================================== CONTROLLER
class LiveDrawController(QtCore.QObject):
    """Coordonne la fenetre, la persistance et le suivi du Viewer."""

    _instance = None

    def __init__(self):
        super(LiveDrawController, self).__init__()
        self.main = _nuke_main_window()
        self.canvas = Canvas(self, parent=self.main)

        self._palette_placed = False

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._sync)

        if self.main is not None:
            self.main.installEventFilter(self)

    def open(self):
        self._load_autosave()
        self._sync(force_show=True)
        # cache le bouton launcher pendant l'edition
        if LiveDrawLauncher._instance is not None:
            LiveDrawLauncher._instance.hide()
        self.timer.start()

    def close(self):
        self.timer.stop()
        self.autosave()
        if self.main is not None:
            try:
                self.main.removeEventFilter(self)
            except Exception:
                pass
        for w in (self.canvas.palette, self.canvas):
            try:
                w.close()
            except Exception:
                pass
        LiveDrawController._instance = None
        # reaffiche le bouton launcher
        if LiveDrawLauncher._instance is not None:
            LiveDrawLauncher._instance._sync()

    # -- suivi du Viewer ------------------------------------------------------
    def _sync(self, force_show=False):
        viewer = _find_viewer_widget()
        pal = self.canvas.palette
        minimized = self.main is not None and self.main.isMinimized()
        if viewer is None or not viewer.isVisible() or minimized:
            self.canvas.hide()
            pal.hide()
            return
        tl = viewer.mapToGlobal(QtCore.QPoint(0, 0))
        geo = QtCore.QRect(tl, viewer.size())
        if self.canvas.geometry() != geo:
            self.canvas.setGeometry(geo)
        if not self.canvas.isVisible():
            self.canvas.show()
        # place la palette une seule fois (en haut a gauche du viewer),
        # ensuite l'utilisateur peut la deplacer librement
        if not self._palette_placed:
            pal.move(geo.x() + PAL_MARGIN, geo.y() + PAL_TOP)
            self._palette_placed = True
        if not pal.isVisible():
            pal.show()
        pal.raise_()
        if force_show:
            self.canvas.raise_()
            pal.raise_()
            self.canvas.setFocus()

    # -- persistance ----------------------------------------------------------
    def autosave(self):
        try:
            os.makedirs(os.path.dirname(AUTOSAVE), exist_ok=True)
            with open(AUTOSAVE, "w") as f:
                json.dump(self.canvas.serialize(), f)
        except Exception as e:
            print("LiveDraw: autosave echoue:", e)

    def _load_autosave(self):
        if os.path.isfile(AUTOSAVE):
            try:
                with open(AUTOSAVE, "r") as f:
                    self.canvas.restore(json.load(f))
            except Exception as e:
                print("LiveDraw: lecture autosave echouee:", e)

    def notify(self, msg):
        print("LiveDraw:", msg)

    def eventFilter(self, obj, event):
        if obj is self.main and event.type() == QtCore.QEvent.Close:
            self.close()
        return False


# ----------------------------------------------------------------- lancement
def toggle_livedraw():
    """Ouvre LiveDraw, ou le ferme s'il est deja ouvert."""
    if LiveDrawController._instance is not None:
        try:
            LiveDrawController._instance.close()
        except Exception:
            pass
        LiveDrawController._instance = None
        return
    c = LiveDrawController()
    LiveDrawController._instance = c
    c.open()
    return c


def open_sketch_folder():
    """Ouvre le dossier des croquis dans l'explorateur."""
    folder = _sketch_dir()
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        pass
    try:
        if os.name == "nt":
            os.startfile(folder)
        else:
            import subprocess
            subprocess.Popen(["xdg-open", folder])
    except Exception as e:
        print("LiveDraw: ouverture dossier echouee:", e)


# ------------------------------------------------- bouton dans la barre Viewer
_VIEWER_BTN_NAME = "LiveDraw_ViewerButton"


def _viewer_image_widget():
    """La zone image du Viewer (Image_Window) - le grand enfant sous la barre."""
    v = _find_viewer_widget()
    if v is None:
        return None
    best = None
    for ch in v.children():
        if not isinstance(ch, QtWidgets.QWidget) or not ch.isVisible():
            continue
        cls = ch.metaObject().className()
        if "Image_Window" in cls:
            return ch
        if ch.height() > 150 and (best is None or ch.height() > best.height()):
            best = ch
    return best or v


class LiveDrawLauncher(QtWidgets.QWidget):
    """Petite fenetre flottante (bouton stylo) epinglee au coin du Viewer.
    Fenetre separee car le viewport est en OpenGL et repeint tout enfant."""

    _instance = None

    def __init__(self, main):
        super(LiveDrawLauncher, self).__init__(main)
        self.main = main
        self.setObjectName(_VIEWER_BTN_NAME)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.btn = QtWidgets.QToolButton(self)
        self.btn.setIcon(_icon("pen", 20))
        self.btn.setIconSize(QtCore.QSize(18, 18))
        self.btn.setFixedSize(26, 26)
        self.btn.setToolTip("LiveDraw (Shift+D)")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setStyleSheet(
            "QToolButton { background: rgba(45,45,45,175);"
            " border: 1px solid #565656; border-radius: 5px; }"
            " QToolButton:hover { background: rgba(90,90,90,225); }")
        self.btn.clicked.connect(toggle_livedraw)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.btn)
        self.resize(26, 26)

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self._sync)
        self.timer.start()
        self._sync()

    def _sync(self):
        img = _viewer_image_widget()
        minimized = self.main is not None and self.main.isMinimized()
        open_now = LiveDrawController._instance is not None
        # cache le bouton quand LiveDraw est ouvert (il reapparait a la fermeture)
        if img is None or not img.isVisible() or minimized or open_now:
            self.hide()
            return
        tl = img.mapToGlobal(QtCore.QPoint(10, 10))  # haut-gauche, cote palette
        if self.pos() != tl:
            self.move(tl)
        if not self.isVisible():
            self.show()
        self.raise_()


_SHORTCUT = None
_QShortcut = getattr(QtGui, "QShortcut", None) or QtWidgets.QShortcut


def install_shortcut():
    """Installe le raccourci Shift+D directement en Qt, sans menu Nuke.
    Idempotent. Permet de garder le raccourci apres suppression du menu."""
    global _SHORTCUT
    try:
        if _SHORTCUT is not None:
            return True
        main = _nuke_main_window()
        if main is None:
            return False
        sc = _QShortcut(QtGui.QKeySequence("Shift+D"), main)
        sc.setContext(Qt.ApplicationShortcut)
        sc.activated.connect(toggle_livedraw)
        _SHORTCUT = sc
        return True
    except Exception as e:
        print("LiveDraw: raccourci echoue:", e)
        return False


def install_viewer_button():
    """Cree le launcher flottant (bouton stylo) s'il n'existe pas. Idempotent."""
    try:
        install_shortcut()
        if LiveDrawLauncher._instance is not None:
            return True
        main = _nuke_main_window()
        if main is None:
            return False
        LiveDrawLauncher._instance = LiveDrawLauncher(main)
        return True
    except Exception as e:
        print("LiveDraw: launcher echoue:", e)
        return False

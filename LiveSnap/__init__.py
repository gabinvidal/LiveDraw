# -*- coding: utf-8 -*-
"""
LiveSnap - Journal visuel d'avancees pour le Viewer de Nuke
-----------------------------------------------------------
Prend des snapshots de ce que MONTRE le Viewer (display-referred, plein plan),
les range/versionne, et permet de re-comparer les etats visuels dans le temps
via une galerie pellicule + un overlay cale sur le Viewer (fit).

Purement image : aucun snapshot du .nk, aucune restauration de comp, aucun node.

Meme ADN / patte graphique que LiveDraw : fenetres flottantes translucides qui
suivent le Viewer, aucun menu dans la barre du haut. Le bouton camera se place
a cote du bouton stylo de LiveDraw dans le coin du Viewer.

Etape 1 (tranchee) : Nuke 16 n'expose pas le pan/zoom 2D du Viewer. Plutot que
de le LIRE, on le PARTAGE : le snap est affiche dans le Viewer Nuke lui-meme
(entree temporaire + Viewer Process "None"), donc pan/zoom communs -> A/B
aligne a tout niveau de zoom, sans ajouter de node permanent au comp.

Auteur : Gabin Vidal. Licence : MIT.
Compatible PySide2 (Nuke < 15) et PySide6 (Nuke >= 15).
"""

import os
import re
import json
import time
import datetime

import nuke

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    _PYSIDE = 6
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    _PYSIDE = 2

Qt = QtCore.Qt


# --- Constantes (patte graphique LiveDraw) ----------------------------------
ACCENT = "#E8853B"
AUTOSAVE = os.path.join(os.path.expanduser("~"), ".nuke", "livesnap_autosave.json")

THUMB_H = 58          # hauteur des vignettes
GALLERY_H = 96        # hauteur de la bande galerie
GALLERY_MARGIN = 10   # marge par rapport aux bords du Viewer


# ---------------------------------------------------------------- utilitaires
def _gpos(event):
    if _PYSIDE == 6:
        return event.globalPosition().toPoint()
    return event.globalPos()


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
    """Widget du viewport (image) du Viewer actif de Nuke."""
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


def _livedraw_open():
    """Vrai si la palette LiveDraw est ouverte (canvas titre 'LiveDraw' ou
    palette objectName 'bar' visible). Sert a effacer les icones LiveSnap tant
    que LiveDraw occupe le coin du Viewer."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        return False
    for w in app.topLevelWidgets():
        try:
            if not w.isVisible():
                continue
            if w.windowTitle() == "LiveDraw" or w.objectName() == "bar":
                return True
        except Exception:
            continue
    return False


def _livedraw_button():
    """Le bouton flottant de LiveDraw s'il est present (pour s'ancrer a cote)."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    for w in app.topLevelWidgets():
        try:
            if w.objectName() == "LiveDraw_ViewerButton" and w.isVisible():
                return w
        except Exception:
            pass
    return None


# Fenetres reconnues comme "les notres" (LiveDraw + LiveSnap), pour ne pas se
# masquer quand on clique l'une d'elles.
_OUR_WIN_NAMES = {"LiveDraw_ViewerButton", "LiveSnap_ViewerButton", "gbar", "bar"}
_OUR_WIN_TITLES = {"LiveDraw", "LiveSnap"}


def _is_ours(aw, main):
    """Vrai si 'aw' est la fenetre principale ou une de nos fenetres flottantes
    (boutons / palette / galerie, LiveDraw + LiveSnap). Sert a decider si on peut
    remonter (raise_) au premier plan sans passer devant un dialogue Nuke."""
    if aw is None:
        return False
    if aw is main:
        return True
    try:
        if aw.objectName() in _OUR_WIN_NAMES:
            return True
        if aw.windowTitle() in _OUR_WIN_TITLES:
            return True
    except Exception:
        pass
    return False


def _reset_viewer_fit():
    """Tente de remettre le Viewer en 'fit' (envoi de la touche F au viewport).
    Nuke n'expose pas de zoom() en 16 ; a defaut, appuie sur F manuellement."""
    w = _find_viewer_widget()
    if w is None:
        return
    try:
        w.setFocus(Qt.OtherFocusReason)
        for et in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
            ev = QtGui.QKeyEvent(et, Qt.Key_F, Qt.NoModifier, "f")
            QtWidgets.QApplication.postEvent(w, ev)
    except Exception as e:
        print("LiveSnap: fit Viewer echoue:", e)


# ------------------------------------------------------------------- icones
def _icon(kind, px=18):
    pm = QtGui.QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    col = QtGui.QColor("#e2e2e2")
    pen = QtGui.QPen(col, 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    P = QtCore.QPointF
    a, b, c = px * 0.20, px * 0.80, px * 0.5

    if kind == "camera":
        # corps
        p.setBrush(Qt.NoBrush)
        body = QtCore.QRectF(px * 0.14, px * 0.30, px * 0.72, px * 0.48)
        p.drawRoundedRect(body, 2.5, 2.5)
        # bosse viseur
        p.drawLine(P(px * 0.36, px * 0.30), P(px * 0.42, px * 0.22))
        p.drawLine(P(px * 0.42, px * 0.22), P(px * 0.58, px * 0.22))
        p.drawLine(P(px * 0.58, px * 0.22), P(px * 0.64, px * 0.30))
        # objectif
        p.drawEllipse(P(c, px * 0.55), px * 0.13, px * 0.13)

    elif kind == "film":
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QtCore.QRectF(px * 0.16, px * 0.26, px * 0.68, px * 0.48), 2, 2)
        p.drawLine(P(px * 0.40, px * 0.26), P(px * 0.40, px * 0.74))
        p.drawLine(P(px * 0.60, px * 0.26), P(px * 0.60, px * 0.74))

    elif kind == "fit":
        # crochets aux 4 coins
        s = px * 0.16
        for cx, cy, dx, dy in ((a, a, 1, 1), (b, a, -1, 1),
                               (a, b, 1, -1), (b, b, -1, -1)):
            p.drawLine(P(cx, cy), P(cx + dx * s, cy))
            p.drawLine(P(cx, cy), P(cx, cy + dy * s))

    elif kind == "folder":
        path = QtGui.QPainterPath()
        path.moveTo(a, px * 0.32)
        path.lineTo(px * 0.44, px * 0.32)
        path.lineTo(px * 0.52, px * 0.42)
        path.lineTo(b, px * 0.42)
        path.lineTo(b, b)
        path.lineTo(a, b)
        path.closeSubpath()
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    elif kind == "close":
        p.drawLine(P(a, a), P(b, b))
        p.drawLine(P(a, b), P(b, a))

    p.end()
    return QtGui.QIcon(pm)


# ============================================================= CAPTURE (coeur)
def comp_name():
    """Racine du .nk sans extension, ex. 'SH0420_comp'. 'untitled' si non sauve."""
    path = _saved_nk_path()
    if not path:
        return "untitled"
    return os.path.splitext(os.path.basename(path))[0]


def _saved_nk_path():
    """Chemin du .nk SI reellement sauve (pas un temporaire), sinon None."""
    import tempfile
    root = nuke.root().name()
    if not root or root == "Root" or not os.path.isabs(root):
        return None
    tmp = os.path.realpath(tempfile.gettempdir())
    if os.path.realpath(root).startswith(tmp):
        return None
    return root


def snap_dir(comp=None):
    """LiveSnap/<comp>/ a cote du .nk, fallback ~/Documents/LiveSnap/<comp>/."""
    comp = comp or comp_name()
    path = _saved_nk_path()
    if path:
        base = os.path.join(os.path.dirname(path), "LiveSnap", comp)
    else:
        base = os.path.join(os.path.expanduser("~"), "Documents", "LiveSnap", comp)
    return base


def next_version(directory, comp):
    if not os.path.isdir(directory):
        return 1
    rx = re.compile(r"^%s_v(\d+)\.png$" % re.escape(comp), re.IGNORECASE)
    maxv = 0
    for f in os.listdir(directory):
        m = rx.match(f)
        if m:
            maxv = max(maxv, int(m.group(1)))
    return maxv + 1


def _viewed_node(viewer):
    vnode = viewer.node()
    try:
        idx = viewer.activeInput()
    except Exception:
        idx = 0
    if idx is None:
        idx = 0
    return vnode.input(idx)


def _node_format(node):
    try:
        f = node.format()
        if f is not None and f.width() > 0:
            return f.width(), f.height()
    except Exception:
        pass
    f = nuke.root().format()
    return f.width(), f.height()


def _resolve_outdir(comp):
    """Renvoie un dossier de sortie garanti inscriptible pour ce comp.

    Essaie d'abord le dossier a cote du .nk (comportement normal). Sur un
    poste ou le script est sauve dans un emplacement en lecture seule pour
    l'utilisateur (dossier reseau/partage d'un poste ecole, par ex.), la
    creation du dossier ou l'ecriture du PNG echouait auparavant en silence
    (exception non affichee) : plus aucun snapshot n'etait ecrit nulle part,
    d'ou l'impression de "captures qui disparaissent". On teste maintenant
    l'ecriture, et si ca echoue on replie sur ~/Documents/LiveSnap/<comp>
    (toujours inscriptible) en le signalant dans la console."""
    primary = snap_dir(comp)
    fallback = os.path.join(os.path.expanduser("~"), "Documents", "LiveSnap", comp)
    if os.path.realpath(primary) == os.path.realpath(fallback):
        os.makedirs(primary, exist_ok=True)
        return primary
    try:
        os.makedirs(primary, exist_ok=True)
        probe = os.path.join(primary, ".livesnap_write_test")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        return primary
    except Exception as e:
        print("LiveSnap : dossier '%s' non inscriptible (%s) -> repli sur %s"
              % (primary, e, fallback))
        os.makedirs(fallback, exist_ok=True)
        return fallback


def capture(note=None, datatype="16 bit"):
    """Capture l'image affichee par le Viewer -> PNG full-res + side-car JSON.
    Renvoie le chemin du PNG, ou None."""
    viewer = nuke.activeViewer()
    if viewer is None:
        nuke.message("LiveSnap : aucun Viewer actif.")
        return None
    vnode = viewer.node()
    src = _viewed_node(viewer)
    if src is None:
        nuke.message("LiveSnap : le Viewer ne montre aucun node.")
        return None

    comp = comp_name()
    outdir = _resolve_outdir(comp)
    version = next_version(outdir, comp)
    frame = int(nuke.frame())
    stem = "%s_v%03d" % (comp, version)
    png_path = os.path.join(outdir, stem + ".png")
    exr_path = os.path.join(outdir, stem + ".exr")
    json_path = os.path.join(outdir, stem + ".json")

    gain = vnode["gain"].value()
    gamma = vnode["gamma"].value()
    vp_name = vnode["viewerProcess"].value()
    width, height = _node_format(src)

    temp = []
    try:
        nuke.Undo().disable()
    except Exception:
        pass
    error = None
    try:
        last = src
        if gain != 1.0 or (gamma != 1.0 and gamma != 0.0):
            grade = nuke.nodes.Grade(inputs=[last])
            grade["white"].setValue(gain)
            grade["gamma"].setValue(gamma if gamma != 0.0 else 1.0)
            temp.append(grade)
            last = grade
        try:
            vp = nuke.ViewerProcess.node()
        except Exception:
            vp = None
        if vp is not None:
            vp.setInput(0, last)
            temp.append(vp)
            last = vp
        w = nuke.nodes.Write(inputs=[last])
        w["file"].setValue(png_path.replace("\\", "/"))
        w["file_type"].setValue("png")
        try:
            w["datatype"].setValue(datatype)
        except Exception:
            pass
        w["raw"].setValue(True)
        w["create_directories"].setValue(True)
        temp.append(w)
        nuke.execute(w, frame, frame)

        # 2e sortie : EXR scene-lineaire = source de comparaison (couleurs
        # exactes, re-passee par le meme Viewer Process que le live a l'affichage)
        we = nuke.nodes.Write(inputs=[src])
        we["file"].setValue(exr_path.replace("\\", "/"))
        we["file_type"].setValue("exr")
        try:
            we["datatype"].setValue("16 bit half")
        except Exception:
            pass
        # DWAA : compression lossy performante pour des snapshots (leger tout en
        # gardant le detail). dw_compression_level : plus haut = plus compresse /
        # plus leger ; ~45 est un bon compromis detail/poids.
        try:
            we["compression"].setValue("DWAA")
        except Exception:
            pass
        try:
            we["dw_compression_level"].setValue(45)
        except Exception:
            pass
        we["raw"].setValue(True)
        we["create_directories"].setValue(True)
        temp.append(we)
        nuke.execute(we, frame, frame)
    except Exception as e:
        error = e
    finally:
        for t in reversed(temp):
            try:
                nuke.delete(t)
            except Exception:
                pass
        try:
            nuke.Undo().enable()
        except Exception:
            pass

    if error is not None:
        # Avant, une erreur ici (permissions, disque plein, Write invalide...)
        # remontait en silence dans la Script Editor et l'utilisateur ne
        # voyait rien : d'ou l'impression que le clic camera ne faisait
        # "rien". Desormais on le dit clairement, avec le dossier vise.
        nuke.message(
            "LiveSnap : la capture a echoue.\n\n%s\n\nDossier vise :\n%s"
            % (error, outdir))
        return None

    meta = {
        "version": version, "file": os.path.basename(png_path),
        "exr": os.path.basename(exr_path), "comp": comp,
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
        "frame": frame, "note": note or "", "source_node": src.name(),
        "viewer_process": vp_name, "gain": gain, "gamma": gamma,
        "width": width, "height": height,
    }
    try:
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2, ensure_ascii=False)
    except Exception as e:
        print("LiveSnap : side-car JSON non ecrit :", e)

    print("LiveSnap : capture v%03d enregistree -> %s  (f%d)" % (version, png_path, frame))
    return png_path


def list_snaps(comp=None):
    """[(png_path, meta_dict), ...] trie par version croissante."""
    comp = comp or comp_name()
    directory = snap_dir(comp)
    if not os.path.isdir(directory):
        return []
    rx = re.compile(r"^%s_v(\d+)\.png$" % re.escape(comp), re.IGNORECASE)
    items = []
    for f in os.listdir(directory):
        m = rx.match(f)
        if not m:
            continue
        png = os.path.join(directory, f)
        meta = {"version": int(m.group(1))}
        jp = os.path.splitext(png)[0] + ".json"
        if os.path.isfile(jp):
            try:
                with open(jp, encoding="utf-8") as fh:
                    meta.update(json.load(fh))
            except Exception:
                pass
        items.append((png, meta))
    items.sort(key=lambda t: t[1].get("version", 0))
    return items


def open_snap_folder():
    folder = snap_dir()
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        pass
    try:
        if os.name == "nt":
            os.startfile(folder)
        elif os.uname().sysname == "Darwin":
            import subprocess
            subprocess.Popen(["open", folder])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", folder])
    except Exception as e:
        print("LiveSnap: ouverture dossier echouee:", e)


def set_snap_note(png_path, note):
    """Ecrit/maj la note d'un snap dans son side-car JSON."""
    jp = os.path.splitext(png_path)[0] + ".json"
    data = {}
    if os.path.isfile(jp):
        try:
            with open(jp, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            pass
    data["note"] = note
    try:
        with open(jp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except Exception as e:
        print("LiveSnap: note non enregistree:", e)


# =========================================================== (plus d'overlay Qt)
# Route B : la comparaison se fait DANS le Viewer Nuke (cf. LiveSnapController).
# Le snap est branche sur une entree temporaire du Viewer et affiche avec le
# Viewer Process sur "None" (le PNG est deja display-referred). Consequence :
# le pan/zoom est partage avec le live -> A/B parfaitement aligne a tout zoom.


# =================================================================== GALLERY
class _Thumb(QtWidgets.QFrame):
    """Vignette cliquable : pixmap + label (vNNN . fNNNN . HHhMM)."""

    def __init__(self, gallery, png_path, meta, is_live=False):
        super(_Thumb, self).__init__(gallery)
        self.gallery = gallery
        self.png_path = png_path
        self.meta = meta or {}
        self.is_live = is_live
        self.selected = False
        self.setCursor(Qt.PointingHandCursor)
        self._build()

    def _label_text(self):
        if self.is_live:
            return "LIVE"
        v = self.meta.get("version", 0)
        f = self.meta.get("frame", "?")
        t = self.meta.get("time", "")
        hh = ""
        try:
            dt = datetime.datetime.fromisoformat(t)
            hh = "%dh%02d" % (dt.hour, dt.minute)
        except Exception:
            pass
        return "v%03d . f%s . %s" % (v, f, hh)

    def _build(self):
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.img = QtWidgets.QLabel()
        self.img.setAlignment(Qt.AlignCenter)
        self.img.setFixedHeight(THUMB_H)
        if self.is_live:
            self.img.setText("LIVE")
            self.img.setStyleSheet(
                "color:#e2e2e2; font-weight:bold; font-size:12px;"
                " background:#202020; border-radius:3px;")
            self.img.setFixedWidth(int(THUMB_H * 1.4))
        else:
            pm = QtGui.QPixmap(self.png_path)
            if not pm.isNull():
                pm = pm.scaledToHeight(THUMB_H, Qt.SmoothTransformation)
                self.img.setPixmap(pm)
                self.img.setFixedWidth(pm.width())
            else:
                self.img.setText("?")
                self.img.setFixedWidth(int(THUMB_H * 1.4))
        lay.addWidget(self.img, 0, Qt.AlignCenter)
        self.lbl = QtWidgets.QLabel(self._label_text())
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setStyleSheet("color:#b0b0b0; font-size:8px;")
        lay.addWidget(self.lbl)
        # les enfants laissent passer souris -> clic gauche (select) et clic
        # droit (note) atteignent toujours la vignette
        self.img.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._apply_style()

        # petite croix de suppression (coin haut-droit, visible au survol)
        if not self.is_live:
            self.del_btn = QtWidgets.QPushButton("×", self)
            self.del_btn.setFixedSize(16, 16)
            self.del_btn.setCursor(Qt.PointingHandCursor)
            self.del_btn.setToolTip("Supprimer ce snap")
            self.del_btn.setStyleSheet(
                "QPushButton { background: rgba(20,20,20,205); color:#fff;"
                " border:1px solid #000; border-radius:8px; font-weight:bold;"
                " font-size:12px; padding:0px; }"
                " QPushButton:hover { background: rgba(214,64,64,240); }")
            self.del_btn.clicked.connect(lambda: self.gallery.delete_snap(self))
            self.del_btn.hide()

        self._apply_note()

    def contextMenuEvent(self, event):
        # clic droit sur une vignette -> ajouter / editer une note
        if self.is_live:
            return
        self._edit_note()

    def _edit_note(self):
        cur = (self.meta or {}).get("note", "")
        text, ok = QtWidgets.QInputDialog.getText(
            self, "LiveSnap - Note", "Note pour ce snapshot :",
            QtWidgets.QLineEdit.Normal, cur)
        if not ok:
            return
        note = text.strip()
        set_snap_note(self.png_path, note)
        self.meta["note"] = note
        self._apply_note()

    def _apply_note(self):
        """Reflete la note : marqueur crayon dans le label + infobulle."""
        if self.is_live:
            return
        note = (self.meta or {}).get("note", "")
        base = self._label_text()
        if note:
            self.lbl.setText("✎ " + base)
            self.setToolTip(note)
        else:
            self.lbl.setText(base)
            self.setToolTip("Clic droit : ajouter une note")

    def resizeEvent(self, event):
        if not self.is_live and hasattr(self, "del_btn"):
            self.del_btn.move(self.width() - self.del_btn.width() - 3, 3)
        super(_Thumb, self).resizeEvent(event)

    def enterEvent(self, event):
        if not self.is_live and hasattr(self, "del_btn"):
            self.del_btn.move(self.width() - self.del_btn.width() - 3, 3)
            self.del_btn.show()
            self.del_btn.raise_()

    def leaveEvent(self, event):
        if not self.is_live and hasattr(self, "del_btn"):
            self.del_btn.hide()

    def _apply_style(self):
        border = ACCENT if self.selected else "#262626"
        self.setStyleSheet(
            "QFrame { background:#3a3a3a; border:2px solid %s;"
            " border-radius:4px; }" % border)

    def set_selected(self, on):
        self.selected = on
        self._apply_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.gallery.select(self)


class GalleryBar(QtWidgets.QFrame):
    """Bande pellicule le long du bas du Viewer : LIVE + vignettes des snaps."""

    def __init__(self, controller, main=None):
        super(GalleryBar, self).__init__(main)
        self.controller = controller
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setObjectName("gbar")
        self.setStyleSheet(self._style())
        self.thumbs = []
        self.current = None
        self._build()

    def _style(self):
        return """
        QFrame#gbar { background-color: rgba(42,42,42,235);
                      border: 1px solid #262626; border-radius: 6px; }
        QPushButton { background-color:#4a4a4a; color:#dcdcdc;
                      border:1px solid #262626; border-radius:3px; padding:2px 6px; }
        QPushButton:hover { background-color:#565656; }
        QPushButton:checked { background-color:#5a5a5a; border:1px solid %s; }
        QLabel#hint { color:#8a8a8a; font-size:9px; }
        """ % ACCENT

    def _build(self):
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(8)

        # zone scrollable des vignettes
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setStyleSheet("background:transparent;")
        self.strip = QtWidgets.QWidget()
        self.strip_lay = QtWidgets.QHBoxLayout(self.strip)
        self.strip_lay.setContentsMargins(0, 0, 0, 0)
        self.strip_lay.setSpacing(6)
        self.strip_lay.addStretch()
        self.scroll.setWidget(self.strip)
        root.addWidget(self.scroll, 1)

    def refresh(self):
        """Reconstruit la pellicule depuis le disque (LIVE + snaps)."""
        # vide
        for t in self.thumbs:
            t.setParent(None)
            t.deleteLater()
        self.thumbs = []
        # retire le stretch
        while self.strip_lay.count():
            it = self.strip_lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)

        live = _Thumb(self, None, {}, is_live=True)
        self.strip_lay.addWidget(live)
        self.thumbs.append(live)
        for png, meta in list_snaps():
            th = _Thumb(self, png, meta)
            self.strip_lay.addWidget(th)
            self.thumbs.append(th)

        # bouton dossier a la fin de la pellicule (cote gauche, apres les snaps)
        fbtn = QtWidgets.QPushButton()
        fbtn.setIcon(_icon("folder", 18))
        fbtn.setIconSize(QtCore.QSize(20, 20))
        fbtn.setToolTip("Ouvrir le dossier des snaps")
        fbtn.setFixedSize(THUMB_H, THUMB_H + 20)
        fbtn.setStyleSheet(
            "QPushButton { background:#3a3a3a; border:2px solid #262626;"
            " border-radius:4px; }"
            " QPushButton:hover { background:#484848; }")
        fbtn.clicked.connect(open_snap_folder)
        self.strip_lay.addWidget(fbtn)
        self.strip_lay.addStretch()

        # selection : garde LIVE si rien
        if self.current not in self.thumbs:
            self.current = live
        self._refresh_selection()

    def _refresh_selection(self):
        for t in self.thumbs:
            t.set_selected(t is self.current)

    def select(self, thumb):
        self.current = thumb
        self._refresh_selection()
        if thumb.is_live:
            self.controller.show_live()
        else:
            self.controller.show_snap(thumb.png_path)

    def delete_snap(self, thumb):
        """Supprime le snap (PNG + EXR + JSON) et rafraichit la pellicule."""
        if thumb.is_live:
            return
        # repasse en live et libere le Read temporaire (evite le verrou fichier)
        self.controller.show_live()
        self.controller._teardown()
        self.current = None
        stem = os.path.splitext(thumb.png_path)[0]
        for path in (thumb.png_path, stem + ".exr", stem + ".json"):
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except Exception as e:
                print("LiveSnap: suppression echouee (%s): %s" % (path, e))
        self.refresh()


# =================================================================== CONTROLLER
class LiveSnapController(QtCore.QObject):
    """Coordonne la galerie et la comparaison DANS le Viewer (route B)."""

    _instance = None

    def __init__(self):
        super(LiveSnapController, self).__init__()
        self.main = _nuke_main_window()
        self.gallery = GalleryBar(self, self.main)

        # etat de la comparaison (le snap est affiche dans le Viewer)
        self._read = None
        self._backdrop = None
        self._snap_input = None
        self._prev_input = None
        self._prev_vp = None
        self._prev_gain = None
        self._prev_gamma = None
        self._saved = False
        self._miss = 0
        self._raise_stable = 0  # anti-course avec les nouveaux dialogues Nuke (cf. _sync)

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self._sync)

        if self.main is not None:
            self.main.installEventFilter(self)

    # -- ouverture / fermeture galerie ---------------------------------------
    def open_gallery(self):
        self.gallery.refresh()
        self._sync(force=True)
        self.timer.start()

    def close_gallery(self):
        self.timer.stop()
        self.show_live()
        self._teardown()
        try:
            self.gallery.hide()
        except Exception:
            pass

    def is_gallery_open(self):
        return self.gallery.isVisible()

    # -- comparaison via le Viewer (route B) ---------------------------------
    def _save_state(self, viewer):
        if self._saved:
            return
        vnode = viewer.node()
        try:
            self._prev_input = viewer.activeInput() or 0
            self._prev_vp = vnode["viewerProcess"].value()
            self._prev_gain = vnode["gain"].value()
            self._prev_gamma = vnode["gamma"].value()
        except Exception:
            self._prev_input = 0
        self._saved = True

    def _snap_read_position(self):
        """Position du Read temporaire : juste sous le Viewer actif plutot
        que tres loin dans le node graph (cf. _ensure_read / _wrap_in_backdrop).
        """
        try:
            v = nuke.activeViewer()
            vnode = v.node() if v is not None else None
            if vnode is not None:
                return vnode.xpos() + 40, vnode.ypos() + 160
        except Exception:
            pass
        return 0, 400

    def _wrap_in_backdrop(self, node):
        """Range le Read temporaire dans un petit backdrop "LiveDraw", gris
        neutre et quasi transparent (juste une bordure + un libelle), plutot
        que de le laisser flotter seul dans le node graph."""
        try:
            try:
                w = node.screenWidth()
                h = node.screenHeight()
            except Exception:
                w, h = 80, 70
            pad_x, pad_top, pad_bottom = 50, 60, 40
            bx = node.xpos() - pad_x
            by = node.ypos() - pad_top
            bw = w + pad_x * 2
            bh = h + pad_top + pad_bottom
            self._backdrop = nuke.nodes.BackdropNode(
                xpos=bx, ypos=by, bdwidth=bw, bdheight=bh,
                label="LiveDraw", note_font_size=22)
            try:
                # gris neutre, remplissage quasi transparent (0x28 d'alpha) :
                # on ne veut qu'une bordure + un libelle discrets, pas un pave
                # colore qui accroche l'oeil dans le node graph.
                self._backdrop["tile_color"].setValue(0x33333328)
            except Exception:
                pass
            try:
                self._backdrop["selected"].setValue(False)
            except Exception:
                pass
        except Exception as e:
            print("LiveSnap: backdrop echoue:", e)
            self._backdrop = None

    def _ensure_read(self, png_path):
        """Cree (ou reutilise) le Read temporaire de comparaison.

        Nuke n'offre pas de moyen, via l'API Python publique, de rendre un
        node reellement invisible dans le Node Graph tant qu'il est branche
        sur un input du Viewer. On le place donc juste sous le Viewer actif,
        range dans un petit backdrop "LiveDraw" (cf. _wrap_in_backdrop) plutot
        que de le "parquer" tres loin de la zone de travail. On n'altere par
        ailleurs jamais la selection de nodes en cours de l'utilisateur (la
        creation d'un node selectionne habituellement tout et deselectionne
        le reste : on annule cet effet de bord)."""
        p = png_path.replace("\\", "/")
        if self._read is None:
            prev_selection = nuke.selectedNodes()
            rx, ry = self._snap_read_position()
            self._read = nuke.nodes.Read(file=p, name="LiveSnap_tmp")
            try:
                self._read.setXYpos(rx, ry)
            except Exception:
                pass
            try:
                self._read["raw"].setValue(True)   # PNG deja display-referred
            except Exception:
                pass
            try:
                self._read["selected"].setValue(False)
                for n in prev_selection:
                    n["selected"].setValue(True)
            except Exception:
                pass
            self._wrap_in_backdrop(self._read)
        else:
            self._read["file"].setValue(p)
        return self._read

    def show_snap(self, png_path):
        viewer = nuke.activeViewer()
        if viewer is None:
            return
        vnode = viewer.node()
        self._save_state(viewer)
        # source de comparaison : EXR scene-lineaire si dispo (couleurs exactes
        # via le meme Viewer Process que le live), sinon repli sur le PNG.
        exr = os.path.splitext(png_path)[0] + ".exr"
        use_exr = os.path.isfile(exr)
        source = exr if use_exr else png_path
        try:
            nuke.Undo().disable()
        except Exception:
            pass
        try:
            read = self._ensure_read(source)
            if self._snap_input is None:
                idx = vnode.inputs()
                if idx >= 10:
                    nuke.message("LiveSnap : Viewer plein (10 entrees).")
                    return
                self._snap_input = idx
            vnode.setInput(self._snap_input, read)
            viewer.activateInput(self._snap_input)
            if not use_exr:
                # ancien PNG display-referred -> affichage brut (Viewer Process
                # "None", gain/gamma neutres). L'EXR, lui, garde le VP du live.
                try:
                    vnode["viewerProcess"].setValue("None")
                    vnode["gain"].setValue(1.0)
                    vnode["gamma"].setValue(1.0)
                except Exception:
                    pass
        finally:
            try:
                nuke.Undo().enable()
            except Exception:
                pass

    def show_live(self):
        if not self._saved:
            return
        viewer = nuke.activeViewer()
        if viewer is None:
            return
        vnode = viewer.node()
        try:
            nuke.Undo().disable()
        except Exception:
            pass
        try:
            viewer.activateInput(self._prev_input)
            if self._prev_vp is not None:
                vnode["viewerProcess"].setValue(self._prev_vp)
            if self._prev_gain is not None:
                vnode["gain"].setValue(self._prev_gain)
            if self._prev_gamma is not None:
                vnode["gamma"].setValue(self._prev_gamma)
        except Exception:
            pass
        finally:
            try:
                nuke.Undo().enable()
            except Exception:
                pass

    def _teardown(self):
        """Detache et supprime le Read temporaire, restaure l'etat."""
        try:
            nuke.Undo().disable()
        except Exception:
            pass
        try:
            v = nuke.activeViewer()
            vnode = v.node() if v is not None else None
            if vnode is not None and self._snap_input is not None:
                try:
                    vnode.setInput(self._snap_input, None)
                except Exception:
                    pass
            if self._read is not None:
                try:
                    nuke.delete(self._read)
                except Exception:
                    pass
            if self._backdrop is not None:
                try:
                    nuke.delete(self._backdrop)
                except Exception:
                    pass
        finally:
            self._read = None
            self._backdrop = None
            self._snap_input = None
            self._saved = False
            try:
                nuke.Undo().enable()
            except Exception:
                pass

    # -- suivi du Viewer (position de la galerie) ----------------------------
    def _place_gallery(self):
        img = _viewer_image_widget()
        if img is None:
            return
        tl = img.mapToGlobal(QtCore.QPoint(0, 0))
        avail = img.width() - 2 * GALLERY_MARGIN
        try:
            content = self.gallery.strip.sizeHint().width() + 34
        except Exception:
            content = avail
        w = max(280, min(avail, content))
        x = tl.x() + GALLERY_MARGIN
        y = tl.y() + img.height() - GALLERY_H - GALLERY_MARGIN
        self.gallery.setGeometry(x, y, w, GALLERY_H)

    def _sync(self, force=False):
        # 'Q' (HUD Viewer masque) -> on masque la galerie aussi ; le polling ne
        # doit pas la re-afficher tant que l'etat partage reste actif.
        if getattr(nuke, "_gvtools_hud_hidden", False):
            self.gallery.hide()
            return
        # LiveDraw vient d'etre ouvert -> on ferme la galerie LiveSnap pour ne pas
        # empiler les deux interfaces (restaure le live + nettoie le Read temp).
        if _livedraw_open():
            self.close_gallery()
            return
        img = _viewer_image_widget()
        app = QtWidgets.QApplication.instance()
        minimized = self.main is not None and self.main.isMinimized()
        aw = app.activeWindow() if app is not None else None
        if img is None or not img.isVisible() or minimized or aw is None:
            self._miss += 1
            if self._miss >= 2:
                self.gallery.hide()
            return
        self._miss = 0
        self._place_gallery()
        if not self.gallery.isVisible():
            self.gallery.show()
        # On ne remonte pas la galerie au premier tick ou "aw" redevient "a nous" :
        # un nouveau dialogue Nuke (Write, browse fichier...) peut naitre pendant
        # ce meme tick (300ms) si le clic qui l'a ouvert venait de la fenetre
        # principale (donc "a nous" l'instant d'avant). Exiger 2 ticks stables
        # laisse au dialogue le temps de s'installer avant qu'on repasse devant.
        # `force=True` (ouverture volontaire de la galerie) court-circuite ce
        # delai : l'utilisateur vient d'interagir avec nous, pas de course possible.
        if _is_ours(aw, self.main):
            self._raise_stable = 2 if force else self._raise_stable + 1
            if self._raise_stable >= 2:
                self.gallery.raise_()
        else:
            self._raise_stable = 0

    def eventFilter(self, obj, event):
        if obj is self.main and event.type() == QtCore.QEvent.Close:
            self.close_gallery()
        return False


# ----------------------------------------------------------------- lancement
def do_capture():
    """Prend un snapshot ; rafraichit la galerie si ouverte."""
    path = capture()
    c = LiveSnapController._instance
    if path and c is not None and c.is_gallery_open():
        c.gallery.refresh()
    return path


def toggle_gallery():
    """Ouvre/ferme la galerie."""
    c = LiveSnapController._instance
    if c is not None and c.is_gallery_open():
        c.close_gallery()
        return
    if c is None:
        c = LiveSnapController()
        LiveSnapController._instance = c
    c.open_gallery()
    return c


# ------------------------------------------------- bouton dans la barre Viewer
_VIEWER_BTN_NAME = "LiveSnap_ViewerButton"


class LiveSnapLauncher(QtWidgets.QWidget):
    """Fenetre flottante (camera + galerie) epinglee au coin du Viewer,
    a cote du bouton stylo de LiveDraw."""

    _instance = None

    def __init__(self, main):
        super(LiveSnapLauncher, self).__init__(main)
        self.main = main
        self.setObjectName(_VIEWER_BTN_NAME)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        style = ("QToolButton { background: rgba(45,45,45,175);"
                 " border: 1px solid #565656; border-radius: 5px; }"
                 " QToolButton:hover { background: rgba(90,90,90,225); }")

        self.btn_cam = QtWidgets.QToolButton(self)
        self.btn_cam.setIcon(_icon("camera", 20))
        self.btn_cam.setIconSize(QtCore.QSize(18, 18))
        self.btn_cam.setFixedSize(26, 26)
        self.btn_cam.setToolTip("LiveSnap : capturer (Shift+S)")
        self.btn_cam.setCursor(Qt.PointingHandCursor)
        self.btn_cam.setStyleSheet(style)
        self.btn_cam.clicked.connect(do_capture)

        self.btn_gal = QtWidgets.QToolButton(self)
        self.btn_gal.setIcon(_icon("film", 20))
        self.btn_gal.setIconSize(QtCore.QSize(18, 18))
        self.btn_gal.setFixedSize(26, 26)
        self.btn_gal.setToolTip("LiveSnap : galerie")
        self.btn_gal.setCursor(Qt.PointingHandCursor)
        self.btn_gal.setStyleSheet(style)
        self.btn_gal.clicked.connect(toggle_gallery)

        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.btn_cam)
        lay.addWidget(self.btn_gal)
        self.resize(56, 26)

        self._miss = 0
        self._raise_stable = 0  # anti-course avec les nouveaux dialogues Nuke (cf. _sync)
        self._created_at = time.time()  # cf. _sync : delai de grace pour LiveDraw
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self._sync)
        self.timer.start()
        self._sync()

    def _sync(self):
        # 'Q' (HUD Viewer masque) -> on masque le launcher aussi.
        if getattr(nuke, "_gvtools_hud_hidden", False):
            self.hide()
            return
        img = _viewer_image_widget()
        app = QtWidgets.QApplication.instance()
        minimized = self.main is not None and self.main.isMinimized()
        aw = app.activeWindow() if app is not None else None
        # LiveDraw ouvert : on efface les icones LiveSnap (elles reviennent a la
        # fermeture de LiveDraw). L'inverse n'est PAS vrai : quand la galerie
        # LiveSnap est ouverte, on garde ces icones (capture + fermeture).
        if _livedraw_open():
            self.hide()
            return
        # on ne se cache VRAIMENT que si une autre appli est devant (aw None) ou
        # si le Viewer n'est pas la. Un dialogue Nuke actif -> on reste visible
        # mais sans remonter (voir plus bas).
        if img is None or not img.isVisible() or minimized or aw is None:
            self._miss += 1
            if self._miss >= 2:
                self.hide()
            return
        self._miss = 0
        # position figee : a droite du slot du bouton LiveDraw (calcule depuis le
        # coin du Viewer, meme si le bouton LiveDraw est masque -> pas de saut sur
        # la palette quand LiveDraw est ouvert)
        ld = _livedraw_button()
        if ld is not None and ld.isVisible():
            gp = ld.mapToGlobal(QtCore.QPoint(ld.width() + 6, 0))
        elif time.time() - self._created_at < 3.0:
            # le bouton LiveDraw n'est pas encore visible, mais on est encore
            # dans la fenetre de demarrage : il est peut-etre juste en cours
            # d'installation (course au lancement de Nuke). On garde la place
            # reservee pour eviter un saut visuel s'il apparait juste apres.
            gp = img.mapToGlobal(QtCore.QPoint(10 + 26 + 6, 10))
        else:
            # passe le delai de grace, toujours pas de bouton LiveDraw : il
            # n'est vraiment pas installe (ou desactive). On prend directement
            # le coin du Viewer au lieu de laisser un decalage vide.
            gp = img.mapToGlobal(QtCore.QPoint(10, 10))
        if self.pos() != gp:
            self.move(gp)
        if not self.isVisible():
            self.show()
        # ne remonter au premier plan que si une de NOS fenetres est active :
        # sinon (dialogue Nuke) on reste visible dans le coin mais derriere lui.
        # 2 ticks stables requis avant de remonter (cf. LiveSnapController._sync) :
        # laisse le temps a un nouveau dialogue Nuke ne du meme clic de s'installer.
        if _is_ours(aw, self.main):
            self._raise_stable += 1
            if self._raise_stable >= 2:
                self.raise_()
        else:
            self._raise_stable = 0


# ------------------------------------------------- masquage synchro sur 'Q'
# 'Q' est le raccourci natif Nuke qui masque le reste du HUD du Viewer
# (barres d'outils, player...). On ne peut pas s'abonner a cet evenement via
# l'API Python de Nuke (pas de callback expose) : on observe donc la touche
# nous-memes via un filtre applicatif, SANS jamais consommer l'evenement, pour
# que le traitement natif de Nuke continue de se produire normalement.
#
# L'etat (cache/visible) est stocke comme attribut sur le module `nuke`
# (nuke._gvtools_hud_hidden) plutot que dans une variable locale a ce fichier :
# LiveDraw doit s'y aligner aussi (cf. LiveDraw/__init__.py, meme attribut),
# et les deux outils importent deja `nuke` sans se connaitre l'un l'autre.
_HUD_FILTER = None


def _focus_is_textish():
    """Vrai si le widget qui a le focus est un champ editable (ligne de texte,
    Script Editor, spinbox...) : on ne veut surtout pas voler le 'q' tape la."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        return False
    w = app.focusWidget()
    if w is None:
        return False
    textish = (QtWidgets.QLineEdit, QtWidgets.QTextEdit,
               QtWidgets.QPlainTextEdit, QtWidgets.QAbstractSpinBox,
               QtWidgets.QComboBox)
    return isinstance(w, textish)


def _viewer_has_focus():
    """Vrai si le widget qui a le focus est le Viewer ou un de ses enfants
    (Nuke fonctionne en focus-follows-mouse : survoler le Viewer lui donne
    deja le focus Qt, comme pour les autres raccourcis du Viewer)."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        return False
    w = app.focusWidget()
    v = _find_viewer_widget()
    if w is None or v is None:
        return False
    p = w
    while p is not None:
        if p is v:
            return True
        p = p.parentWidget()
    return False


def _our_floating_windows():
    """Toutes nos fenetres flottantes actuellement visibles, LiveSnap +
    LiveDraw confondus (meme reperage que _is_ours : objectName/titre)."""
    app = QtWidgets.QApplication.instance()
    out = []
    if app is None:
        return out
    for w in app.topLevelWidgets():
        try:
            if w.objectName() in _OUR_WIN_NAMES or w.windowTitle() in _OUR_WIN_TITLES:
                out.append(w)
        except Exception:
            continue
    return out


def _toggle_hud_hide():
    """Bascule l'affichage de nos fenetres flottantes en phase avec 'Q'."""
    hidden = not getattr(nuke, "_gvtools_hud_hidden", False)
    nuke._gvtools_hud_hidden = hidden
    for w in _our_floating_windows():
        try:
            w.setVisible(not hidden)
        except Exception:
            pass
    print("LiveSnap : Q -> %s" % ("masque" if hidden else "affiche"))


class _HudKeyFilter(QtCore.QObject):
    """Filtre applicatif : detecte 'Q' quand le Viewer a le focus. Ne consomme
    jamais l'evenement (return False dans tous les cas) : Nuke continue de
    traiter 'Q' normalement, on se contente d'observer en parallele."""

    def eventFilter(self, obj, event):
        try:
            if (event.type() == QtCore.QEvent.KeyPress
                    and event.key() == Qt.Key_Q
                    and not event.isAutoRepeat()
                    and event.modifiers() == Qt.NoModifier
                    and _viewer_has_focus()
                    and not _focus_is_textish()):
                _toggle_hud_hide()
        except Exception as e:
            print("LiveSnap: filtre Q echoue:", e)
        return False


def install_hud_hide():
    """Installe le suivi du 'Q'. Idempotent."""
    global _HUD_FILTER
    if _HUD_FILTER is not None:
        return True
    app = QtWidgets.QApplication.instance()
    if app is None:
        return False
    try:
        f = _HudKeyFilter()
        app.installEventFilter(f)
        _HUD_FILTER = f
        return True
    except Exception as e:
        print("LiveSnap: install hide-Q echoue:", e)
        return False


def uninstall_hud_hide():
    """Retire le filtre 'Q' et force le retour a l'etat visible (utile au
    reload du module en dev, pour ne pas rester bloque cache)."""
    global _HUD_FILTER
    app = QtWidgets.QApplication.instance()
    if app is not None and _HUD_FILTER is not None:
        try:
            app.removeEventFilter(_HUD_FILTER)
        except Exception:
            pass
    _HUD_FILTER = None
    try:
        nuke._gvtools_hud_hidden = False
    except Exception:
        pass


_SHORTCUT = None
_QShortcut = getattr(QtGui, "QShortcut", None) or QtWidgets.QShortcut


def install_shortcut():
    """Raccourci Shift+S -> capture. Idempotent, sans menu Nuke."""
    global _SHORTCUT
    try:
        if _SHORTCUT is not None:
            return True
        main = _nuke_main_window()
        if main is None:
            return False
        sc = _QShortcut(QtGui.QKeySequence("Shift+S"), main)
        sc.setContext(Qt.ApplicationShortcut)
        sc.activated.connect(do_capture)
        _SHORTCUT = sc
        return True
    except Exception as e:
        print("LiveSnap: raccourci echoue:", e)
        return False


def uninstall():
    """Ferme et detruit tout (launcher, galerie, overlay, raccourci).
    Pratique pour reloader le module pendant le dev."""
    global _SHORTCUT
    c = LiveSnapController._instance
    if c is not None:
        try:
            c.close_gallery()
        except Exception:
            pass
        try:
            c.gallery.deleteLater()
        except Exception:
            pass
        LiveSnapController._instance = None
    ln = LiveSnapLauncher._instance
    if ln is not None:
        try:
            ln.timer.stop()
            ln.hide()
            ln.deleteLater()
        except Exception:
            pass
        LiveSnapLauncher._instance = None
    if _SHORTCUT is not None:
        try:
            _SHORTCUT.setEnabled(False)
            _SHORTCUT.deleteLater()
        except Exception:
            pass
        _SHORTCUT = None
    uninstall_hud_hide()


def install_viewer_button():
    """Cree le launcher flottant (camera + galerie). Idempotent."""
    try:
        install_shortcut()
        install_hud_hide()
        if LiveSnapLauncher._instance is not None:
            return True
        main = _nuke_main_window()
        if main is None:
            return False
        LiveSnapLauncher._instance = LiveSnapLauncher(main)
        return True
    except Exception as e:
        print("LiveSnap: launcher echoue:", e)
        return False

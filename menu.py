# -*- coding: utf-8 -*-
# =============================================================================
# LiveDraw (+ option LiveSnap) - a AJOUTER a votre fichier  ~/.nuke/menu.py
# -----------------------------------------------------------------------------
# Copiez le bloc ci-dessous a la fin de votre menu.py existant.
# (Si vous n'avez pas encore de menu.py dans ~/.nuke, vous pouvez deposer ce
#  fichier tel quel.)
#
# Pre-requis :
#   - le dossier "LiveDraw" doit etre place dans  ~/.nuke/LiveDraw
#   - (optionnel) le dossier "LiveSnap" doit etre place dans  ~/.nuke/LiveSnap
#
# LiveSnap est optionnel : si vous n'installez pas le dossier LiveSnap,
# supprimez simplement la section "LiveSnap" plus bas (clairement delimitee).
# =============================================================================

import nuke
import LiveDraw

# 1) Entree dans le menu principal de Nuke (barre du haut)
menubar = nuke.menu("Nuke")

# LiveDraw n'ajoute AUCUN menu dans la barre du haut : tout se pilote depuis le
# bouton stylo dans le coin du Viewer. Le raccourci Shift+D est installe
# directement en Qt par install_viewer_button() (via install_shortcut()).

# 2) Bouton stylo flottant dans le coin du Viewer (+ raccourci Shift+D).
# On retente quelques fois, le temps que le Viewer soit construit au demarrage.
try:
    from PySide6 import QtCore as _LD_QtCore
except ImportError:
    from PySide2 import QtCore as _LD_QtCore


def _ld_install_viewer_button(attempt=0):
    if LiveDraw.install_viewer_button():
        return
    if attempt < 15:
        _LD_QtCore.QTimer.singleShot(
            1000, lambda: _ld_install_viewer_button(attempt + 1))


_LD_QtCore.QTimer.singleShot(1500, _ld_install_viewer_button)

# Reinstalle le bouton quand un nouveau Viewer est cree
try:
    nuke.addOnCreate(
        lambda: _LD_QtCore.QTimer.singleShot(1000, _ld_install_viewer_button),
        nodeClass="Viewer")
except Exception as _e:
    print("LiveDraw: hook Viewer echoue:", _e)

# ============================================================================
# LiveSnap (optionnel) - bouton camera epingle au coin du Viewer, a cote de
# LiveDraw. Supprimez ce bloc si vous n'avez pas installe le dossier LiveSnap.
# ============================================================================
import LiveSnap


def _ls_install_viewer_button(attempt=0):
    if LiveSnap.install_viewer_button():
        return
    if attempt < 15:
        _LD_QtCore.QTimer.singleShot(
            1000, lambda: _ls_install_viewer_button(attempt + 1))


_LD_QtCore.QTimer.singleShot(1600, _ls_install_viewer_button)

# Reinstalle le bouton quand un nouveau Viewer est cree
try:
    nuke.addOnCreate(
        lambda: _LD_QtCore.QTimer.singleShot(1000, _ls_install_viewer_button),
        nodeClass="Viewer")
except Exception as _e:
    print("LiveSnap: hook Viewer echoue:", _e)
# ============================================================================
# Fin LiveSnap
# ============================================================================

# -*- coding: utf-8 -*-
# =============================================================================
# LiveDraw - a AJOUTER a votre fichier  ~/.nuke/menu.py
# -----------------------------------------------------------------------------
# Copiez le bloc ci-dessous a la fin de votre menu.py existant.
# (Si vous n'avez pas encore de menu.py dans ~/.nuke, vous pouvez deposer ce
#  fichier tel quel.)
#
# Pre-requis : le dossier "LiveDraw" doit etre place dans  ~/.nuke/LiveDraw
# =============================================================================

import nuke
import LiveDraw

# LiveDraw n'ajoute AUCUN menu dans la barre du haut : tout se pilote depuis le
# bouton stylo dans le coin du Viewer. Le raccourci Shift+D est installe
# directement en Qt par install_viewer_button() (via install_shortcut()).

# Bouton stylo flottant dans le coin du Viewer (+ raccourci Shift+D).
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

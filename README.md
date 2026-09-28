# LiveDraw for Nuke

A lightweight drawing / sketch overlay for the **Foundry Nuke** Viewer — annotate
directly over your comp for reviews, notes and quick explanations, without adding
any node to your script.

**New in v2 — Snapshot option:** LiveDraw now ships with an optional add-on,
**LiveSnap**, a visual snapshot journal for the Viewer — capture, version and
compare what the Viewer shows over time, still without touching your script.
It installs as a separate button right next to LiveDraw's, and is fully
optional (see [LiveSnap](#livesnap-optional-snapshot-add-on) below).

Created by **Gabin Vidal** — v2.0 — <https://www.linkedin.com/in/gabinvidal>

> 🇫🇷 **La version française se trouve [plus bas](#livedraw-pour-nuke-fr).**

---

## Features

- Draw straight over the Viewer (only the Viewer's pan/zoom is captured — the
  Node Graph, Properties, timeline, etc. stay fully usable).
- Tools: **pen** (freehand), **line**, **rectangle**, **ellipse**, **eraser**.
- 10 colors, 3 brush sizes, global **opacity** slider.
- **Undo / Redo** (including *Clear*), **Hide** strokes.
- **Versioned Save**: exports the Viewer (flattened, with your strokes) *and* a
  transparent PNG of the strokes only, auto-numbered (`sketch_v001.png`, …).
- Button to open the **sketches folder** in your file explorer.
- **Auto-persistence**: your drawing comes back when you reopen LiveDraw (no
  manual save needed).
- Movable, transparent palette that follows the Viewer and hides with Nuke.
- A floating **pen button** pinned to the Viewer corner to open/close LiveDraw
  (also toggled with the **Shift+D** shortcut). LiveDraw adds no menu to Nuke's
  top bar — everything is driven from the pen button.

## Requirements

- Foundry Nuke / NukeX (tested on 16, PySide6). Also compatible with PySide2
  (Nuke < 15).
- Windows, macOS or Linux (the "open sketches folder" button is OS-aware).

## Install

1. Copy the **`LiveDraw`** folder into your Nuke user folder:
   - Windows: `%USERPROFILE%\.nuke\LiveDraw`
   - macOS / Linux: `~/.nuke/LiveDraw`
2. (Optional) Copy the **`LiveSnap`** folder the same way, next to `LiveDraw`,
   if you also want the snapshot add-on:
   - Windows: `%USERPROFILE%\.nuke\LiveSnap`
   - macOS / Linux: `~/.nuke/LiveSnap`
3. Add the block(s) from **`menu.py`** (in this repo) to the end of your
   `~/.nuke/menu.py` (create the file if you don't have one — you can just drop
   the provided `menu.py` in `~/.nuke`). If you don't want LiveSnap, just skip
   the "LiveSnap" section of that file.
4. Restart Nuke.

> If you previously used a single `LiveDraw.py` file directly in `~/.nuke`,
> delete it to avoid an import clash with the new `LiveDraw/` folder.

## Usage

- Press **Shift+D**, or click the **pen button** in the top-left corner of the
  Viewer to open the palette.
- Draw over the image. Pick a tool / color / size, adjust opacity.
- **Save** writes two files into a `LiveDraw/` folder next to your `.nk`
  (or `~/Documents/LiveDraw/` if the script isn't saved): the flattened Viewer +
  strokes, and the strokes-only transparent PNG.
- Close with the palette's **✕**, **Shift+D**, or the pen button.

## Notes

- The palette is a separate translucent window (the Viewer is an OpenGL widget,
  so a child widget would be painted over) — that's why it floats rather than
  docking.
- Auto-save lives in `~/.nuke/livedraw_autosave.json`.

## LiveSnap (optional snapshot add-on)

LiveSnap is a visual progress journal for the Viewer: it captures snapshots of
what the Viewer **shows** (display-referred, full frame), versions them, and
lets you compare visual states over time through a filmstrip gallery and an
overlay aligned on the Viewer. Purely image-based — no `.nk` snapshot, no comp
restore, no node ever added to your script.

Same look and feel as LiveDraw: floating, translucent windows that follow the
Viewer, no menu added to Nuke's top bar. The camera button sits right next to
LiveDraw's pen button in the Viewer corner.

- **Capture**: click the camera button, or press **Shift+S**, to version-save
  what the Viewer currently shows.
- **Gallery**: click the filmstrip button to open a strip of thumbnails of your
  captures; pick one to compare it against the current state directly inside
  the Viewer (same pan/zoom, so the comparison stays aligned at any zoom
  level).
- If LiveDraw is also installed, LiveSnap's button automatically docks right
  next to LiveDraw's pen button; if not, it simply anchors to the Viewer
  corner on its own.

LiveSnap can be installed with or without LiveDraw — it works standalone.

## License

MIT — see `LICENSE`.

---
---

# LiveDraw pour Nuke (FR)

Un overlay de dessin / croquis léger pour le Viewer de **Foundry Nuke** — annotez
directement par-dessus votre comp pour les reviews, les notes et les explications
rapides, sans ajouter le moindre node à votre script.

**Nouveau en v2 — option Snapshot :** LiveDraw embarque désormais un module
optionnel, **LiveSnap**, un journal visuel d'avancées pour le Viewer — capturez,
versionnez et comparez ce que montre le Viewer dans le temps, toujours sans
toucher à votre script. Il s'installe via un bouton séparé, juste à côté de
celui de LiveDraw, et reste totalement optionnel (voir [LiveSnap](#livesnap-module-optionnel-de-snapshot)
plus bas).

Créé par **Gabin Vidal** — v2.0 — <https://www.linkedin.com/in/gabinvidal>

## Fonctions

- Dessin directement sur le Viewer (seul le pan/zoom du Viewer est capturé — le
  Node Graph, les Properties, la timeline, etc. restent utilisables normalement).
- Outils : **crayon** (main levée), **ligne**, **rectangle**, **ovale**, **gomme**.
- 10 couleurs, 3 tailles de trait, curseur d'**opacité** globale.
- **Undo / Redo** (y compris *Tout effacer*), **masquer** les traits.
- **Save versionné** : exporte l'image du Viewer (aplatie, avec vos traits) *et*
  un PNG transparent des traits seuls, auto-numéroté (`sketch_v001.png`, …).
- Bouton pour ouvrir le **dossier des croquis** dans l'explorateur.
- **Persistance auto** : votre dessin revient à la réouverture (pas besoin de
  sauvegarder à la main).
- Palette déplaçable et transparente, qui suit le Viewer et disparaît avec Nuke.
- Un **bouton stylo** flottant épinglé au coin du Viewer pour ouvrir/fermer
  LiveDraw (aussi via le raccourci **Shift+D**). LiveDraw n'ajoute aucun menu
  dans la barre du haut de Nuke — tout se pilote depuis le bouton stylo.

## Pré-requis

- Foundry Nuke / NukeX (testé sur 16, PySide6). Compatible aussi PySide2
  (Nuke < 15).
- Windows, macOS ou Linux (le bouton « ouvrir le dossier des croquis » s'adapte
  à l'OS).

## Installation

1. Copiez le dossier **`LiveDraw`** dans votre dossier utilisateur Nuke :
   - Windows : `%USERPROFILE%\.nuke\LiveDraw`
   - macOS / Linux : `~/.nuke/LiveDraw`
2. (Optionnel) Copiez le dossier **`LiveSnap`** de la même façon, à côté de
   `LiveDraw`, si vous voulez aussi le module snapshot :
   - Windows : `%USERPROFILE%\.nuke\LiveSnap`
   - macOS / Linux : `~/.nuke/LiveSnap`
3. Ajoutez le(s) bloc(s) du fichier **`menu.py`** (fourni ici) à la fin de votre
   `~/.nuke/menu.py` (créez le fichier si vous n'en avez pas — vous pouvez
   simplement déposer le `menu.py` fourni dans `~/.nuke`). Si vous ne voulez
   pas de LiveSnap, ignorez simplement la section « LiveSnap » de ce fichier.
4. Redémarrez Nuke.

> Si vous utilisiez auparavant un fichier `LiveDraw.py` seul directement dans
> `~/.nuke`, supprimez-le pour éviter un conflit d'import avec le nouveau dossier
> `LiveDraw/`.

## Utilisation

- Appuyez sur **Shift+D**, ou cliquez le **bouton stylo** en haut à gauche du
  Viewer pour ouvrir la palette.
- Dessinez sur l'image. Choisissez un outil / une couleur / une taille, réglez
  l'opacité.
- **Save** écrit deux fichiers dans un dossier `LiveDraw/` à côté de votre `.nk`
  (ou `~/Documents/LiveDraw/` si le script n'est pas sauvé) : le Viewer aplati +
  les traits, et le PNG transparent des traits seuls.
- Fermez avec le **✕** de la palette, **Shift+D**, ou le bouton stylo.

## Notes

- La palette est une fenêtre translucide séparée (le Viewer est un widget OpenGL,
  un widget-enfant serait repeint par-dessus) — d'où le fait qu'elle flotte au
  lieu de se docker.
- L'auto-sauvegarde est dans `~/.nuke/livedraw_autosave.json`.

## LiveSnap (module optionnel de snapshot)

LiveSnap est un journal visuel d'avancées pour le Viewer : il capture ce que le
Viewer **montre** (display-referred, plein cadre), le versionne, et permet de
recomparer les états visuels dans le temps via une galerie pellicule et un
overlay calé sur le Viewer. Purement image : aucun snapshot du `.nk`, aucune
restauration de comp, aucun node ajouté à votre script.

Même ADN visuel que LiveDraw : fenêtres flottantes translucides qui suivent le
Viewer, aucun menu ajouté dans la barre du haut. Le bouton caméra se place juste
à côté du bouton stylo de LiveDraw, dans le coin du Viewer.

- **Capture** : cliquez le bouton caméra, ou appuyez sur **Shift+S**, pour
  enregistrer une version de ce que montre le Viewer.
- **Galerie** : cliquez le bouton pellicule pour ouvrir une bande de vignettes
  de vos captures ; choisissez-en une pour la comparer à l'état actuel
  directement dans le Viewer (même pan/zoom, donc la comparaison reste alignée
  à tout niveau de zoom).
- Si LiveDraw est aussi installé, le bouton de LiveSnap se cale automatiquement
  juste à côté du bouton stylo de LiveDraw ; sinon, il se cale simplement dans
  le coin du Viewer.

LiveSnap peut être installé avec ou sans LiveDraw — il fonctionne de façon
autonome.

## Licence

MIT — voir `LICENSE`.

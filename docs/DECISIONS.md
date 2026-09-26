# Decision log

How Photobook got to where it is: every default below was measured in `pruebas/`
(kept locally, not in the repository). Newest decisions are at the end. For install
and use, see the [README](../README.md).


## How a shoot is made

```
 client photos ─┐
 choices ───────┼─> plan: 30 shots spread over the chosen poses, one seed each
                │
 for each block of 5 shots:
   1. compose     QwenStudio /api/generar   16:9 person sheet + pose in words, 1.5K, 40 steps
   2. score       ArcFace vs the close-up   >= 0.78 -> done, no face pass
   3. find face   SAM 3 ("face")            one subprocess for the block
   4. rebuild     QwenStudio /api/editar    face crop enlarged to 1024, close-up as <image2>,
                                            cfg 3 + negative, colour matched, feathered paste
   5. keep        ArcFace again             rebuilt kept unless it scores worse (-0.03)
```

Blocks rather than phases so the first finished photos show up in minutes.

## Decisions and what they were measured on

All on the RTX 5090 Laptop (24 GB), one seed, synthetic clients made with the
same model (`avatares/`). ArcFace = cosine against the close-up (buffalo_l).

**Which photo goes in as the person** (`pruebas/exp1`). Same prompt, pose, seed:

| shot | full-length photo | close-up | both (3 refs, 0.66 MP) |
|---|---|---|---|
| full body (walking) | **0.70** | 0.55 | 0.46 |
| waist up (arms crossed) | 0.71 | **0.89** | 0.87 |

Passing both as two references costs resolution and helped neither.

**One 16:9 sheet instead** (`pruebas/exp3`, the client's idea): close-up and
full-length side by side on one image, passed as the single person reference.
Same prompts and seed: full body **0.74** (vs 0.70), waist up **0.88** (vs 0.89),
and the person is not duplicated — QwenStudio's closing identity sentence ("the
one person in the result is the subject from <image1>") holds it. This is what
the service uses: the client uploads two photos and `caras.hoja_identidad()`
builds the sheet.

**Resolution against the skeleton** (`pruebas/exp4`, 40 steps, HQ avatar).
QwenStudio's ceiling is per number of references: sheet + skeleton is two, so
1.0 MP; the sheet alone is one, so up to 2.30 MP. With the pose written in words
at 1.77 MP (1120x1664 / 1184x1568) the likeness rose on both framings
(0.67 → 0.73, 0.76 → 0.82) and the posture still followed. Cost 170 s against
105 s. `servicio.CALIDAD["pose_en_texto"] = False` brings the skeleton back.

**The face pass** (`pruebas/exp2`). SAM 3 mask → square crop 2.3× the face →
enlarged to 1024 → whole-frame edit with the close-up → pasted back inside the
mask grown 10% and feathered 6%.

| shot | before | cfg 3 | cfg 1 |
|---|---|---|---|
| full body, face 126 px | 0.70 | **0.84** | 0.83 |
| waist up, face 274 px | 0.71 | 0.67 | 0.63 |

- It is what makes full-length shots hold the likeness: a 126 px face redrawn at 1024.
- cfg 3 with a negative prompt is visibly better than cfg 1 (QwenStudio's rule: an
  edit without guidance repaints). Cost: ~135 s against ~75 s.
- The rebuild carries the reference photo's white balance — a golden-hour face came
  back orange. Colour is now matched to the original inside the mask (mean/std per channel).
- A face that is already large and right has nothing to gain, hence the skip at 0.78
  and the keep-the-better rule.

**Prompt length.** ~35 words (concept + scene + wardrobe + light + framing);
QwenStudio adds the identity/pose scaffolding and puts the identity sentence last.
Longer prompts lose the face (QwenStudio README).

**End to end** (`sesiones/20260924-195237-7594da`, through the page, 6 shots,
Lifestyle / cafe / window light / cream knit). 30 minutes: ~168 s to compose,
~182 s per face pass. Two shots were already at 0.80+ and skipped the pass; the
other four all rose (0.75→0.79, 0.77→0.76 kept, 0.55→0.74, 0.60→0.72). The 0.55
one had drifted to a different person, beard included — the pass is what
caught it.

## Ready-made packages

A package is a curated set of photographs (`catalogo/paquetes/<id>/`): a trip,
one wardrobe, many places. The client picks one and is **regenerated** into each
photo — not pasted. Curation happens once per package, before any client sees it:

```
herramientas/crear_paquete.py <id>       make the photos with a house model (or drop real ones in)
herramientas/preparar_paquete.py <id>    Qwen3-VL reads each photo -> recipe + face-pass prompt in paquete.json
```

Per client, each recipe is generated with the client's 16:9 sheet at 1.5K / 40
steps, then the same ArcFace gate and face pass as a custom shoot; the face pass
is told the expression and the light read from the sample.

What was measured to get there (all shown in chat, sheets in `pruebas/exp5-9`):

| approach | result |
|---|---|
| swap face + hair on the photo (exp5-6) | 0.57-0.82, but it reads as a composite: the head brings the close-up's flat light and neutral face, and the body stays the model's. **Rejected by eye.** |
| R1 photo as scene reference (exp7-8) | most faithful to place and framing; the sheet leaks the client's own clothes unless the wardrobe is named; weak face on full-length until the face pass |
| **R2 the package's recipe (exp7, exp9)** | natural, place faithful, 1.5K. Mean 0.75 on the stress test (a man and a 62-year-old woman on a slim 30-year-old model, leap / sitting laughing / spin), pose and energy kept |
| R3 recipe + DWPose skeleton | exact pose, lowest likeness (0.70), 1.0 MP |
| R4 Qwen3-VL writes the recipe | 0.75 but the place drifts (invented a balcony, a bookcase) and the energy is lost (the leap stood still) |

**Then the eye overruled the score:** on the stress sheets R3 kept the moment
best — the leap with the knees up, the coat flying in the spin, the real laugh —
and ArcFace undervalues it only because those faces are small and turned. So
packages run **R3**: the sample's DWPose skeleton + the recipe, 1.0 MP, then
the gate and the expression-aware face pass. QwenStudio's upscale to 1.77 MP
(exp10) sharpens but moves the face a little (0.60→0.52, 0.80→0.74) and
hardens skin; it is behind `CALIDAD["ampliar_esqueleto"]`, off.

**Any folder becomes a package** — the working logic: a folder of photos of
anything, any file names, plus the client's two photos:

```
herramientas/importar_carpeta.py <folder> <id> ["Label"] ["hint"]
```

copies them as 01.png…, extracts each skeleton, reads each photo, writes the
recipes. Read `paquete.json` once: the reader missed Sacre-Coeur ("possibly a
courthouse") and wrote the wardrobe too tersely ("navy stripes"), which let the
client's own teal blouse in on the first end-to-end run (3 photos, 16 min,
`sesiones/20260925-003540-5f9cfa`). The wardrobe question now asks for every
garment by name.

Open: the client's build only partly carries over (a plus-size client came out
slimmer), the client's own shoes leak in from the full-length photo, and the
reader tends to under-read a broad laugh as a soft smile.

## Face pass on fal (superseded by Enhance face, below)

The local face pass kept failing on turned heads (pruebas/exp11-12): Qwen's edit
has no mask, redraws the whole crop, the head moves (up to 26 px), and pasting it
back leaves a ghost contour. Landmark alignment fixed the face and moved the
background with it. Detailers that survive odd angles (Impact Pack's FaceDetailer)
work because they never redraw from scratch around the face.

So the face pass now follows a SUNBURST inpainting workflow: SAM 3 "head and neck"
mask -> SmartMaskCrop-style crop, head and shoulders (x1.9), long side 1536 ->
**GPT Image 2.5 Sunburst edit on fal** (`openai/gpt-image-2.5/sunburst/edit`) with
the crop, the client's close-up and a real mask -> pasted back only inside the mask.
`photobook/fal_inpaint.py` (plain HTTP to fal's queue, key in `.env`),
`detailer.reforzar_fal()`, `servicio.CALIDAD["cara_motor"] = "fal"`. The base
generation stays local; fal is only this step.

exp13, the whole pipeline through the service, face pass forced on every shot:

| client | leap | sitting, laughing | spin |
|---|---|---|---|
| Marcus | 0.78 -> **0.88** | 0.56 -> **0.70** | 0.68 -> **0.84** |
| Rosa | 0.69 -> **0.79** | 0.65 -> **0.69** | 0.66 -> **0.82** |

No seam or ghost on any angle, laughs kept, ~37 s per face (against ~180 s local).
Open: a wide smile can soften (Rosa's spin); the client's own top leaked into the
leap on both clients because `prueba_carpeta` was read before the wardrobe question
asked for every garment -- re-run `preparar_paquete.py` on it.

**The mask edge** (exp14-16, same six raw shots, only the fal pass changing):

| version | crop sent | mask | result |
|---|---|---|---|
| v1 | 1536 | silhouette +6% | right size, soft halo where hair meets sky, smear across the neck |
| v2 | **2048** | silhouette +6% | the eyewear prompt ported to faces + IDENTITY SPEC: better likeness, same soft edge |
| v3 | 2048 | loose, +12% smooth | clean edge, but the head grows **16-37%** (eye distance) -- the mask sets the head size |
| v4 | 2048 | v3 + landmark warp back | size right, background inside the mask breaks (black edges, doubled coat) -- rejected |
| **v2 + band** | 2048 | v2, then a 2nd pass on the outline band only | clean hair/neck edge, head keeps v2's size |

Wider blends on the saved outputs did not remove the soft edge: it is in the model's
output, because a tight mask makes it fit new hair inside the old outline. The fix is
the SUNBURST frame band: a second masked edit on the ring (mask grown 10% minus
eroded 5%) that may knit the edge but cannot touch the face -- `detailer.pasada_banda`,
`CALIDAD["pasada_banda"]`. Two fal calls per face, ~75 s. Every raw fal output is
kept (`*_fal_crudo.png`, `*_banda_crudo.png`) so the stitch can be re-tuned free.

## Enhance face, on demand and local (current default)

The user's call after comparing (exp18): **Qwen is the base**. Photos come out as
generated -- no automatic face pass -- and "✨ Enhance face" is a button in the photo
viewer. It runs locally: the head-and-shoulders crop (SAM 3 "head and neck", x1.9) is
redrawn by QwenStudio as an upscale-style edit with the client's close-up injected as
<image2> (`detailer.reforzar_qwen_upscale`), colour matched inside the head mask,
pasted back. ~110 s, no API.

Against fal on the same shots it keeps the expression (the open smile fal closed) and
never moves the head; it raises the likeness less (+0.04..+0.16 against +0.14..+0.25),
because it improves the face Qwen drew instead of replacing it. The fal path is still
in the code (`CALIDAD["cara_auto"] = True`, `cara_motor = "fal"`).

## Image weight

Every input goes through `optimizar.normalizar()` (EXIF upright, RGB, long side 2048):
client uploads, and every photo of an imported folder. The browser also shrinks the
client's photo to 2048 px JPEG 92% before sending it (a 12 MP phone photo was 5-8 MB
on the wire). The page loads cached JPEG thumbnails from `/mini/<path>?w=240|480|960`
(`_mini/` next to each source); only the lightbox opens an original. Measured: the
six results of a session went from ~15 MB of PNGs to 362 KB. `importar_carpeta.py`
prints source weight -> working weight.

## The app (2026-09-26)

One screen, three things:

1. **Character sheet** -- a drop zone for one 16:9 image: a close-up of the face on the
   left, the full body on the right (the shape measured in exp3). An illustrated
   silhouette shows the layout. `/api/sesion/<id>/hoja` stores it, cuts the close-up the
   likeness check and Enhance need from the largest detected face, and falls back to the
   left half when there is no face (a mannequin). "Build the sheet from two photos"
   composes it in the browser.
2. **Scenes** -- the **Experience library**, split into Women / Men (`genero` in each
   paquete.json), or **My own images**: drop a folder or photos (up to 30). Own photos are
   uploaded one by one (`/escena`), then the worker turns them into a private package
   (`u_<session>`: DWPose skeleton + Qwen3-VL recipe per photo) before composing.
3. **Generate** -- ~100 s per photo (R3). **Enhance** (W2: identity pass at 1 MP + 2K
   upscale of the whole photo, ~5 min) is per photo, from the viewer.

The old step-by-step custom-shoot wizard is at `/web/design.html`.

Library experiences are built with `herramientas/crear_experiencia_20.py` ("City weekend",
20 photos, women and men). Samples are text-only (`"sujeto"` in paquete.json): a person
reference pinned every sample to a frontal centred framing (art portraits v2), text lets
each shot take its angle. The stored prompt keeps "the subject" so the client's recipe
never carries the sample person's looks.

## Tested and rejected (2026-09-26)

- **Multi-angle grid sheet** (pruebas/exp27): four head views + front and side full body on
  the 16:9 sheet. Same images, likeness lower on 14 of 16 shots (art 0.64 -> 0.54, action
  0.29 -> 0.26): at 1 MP each face in the reference gets smaller. Keep the two-photo sheet.
- **Mannequin sample library** (pruebas/exp28): the art portraits with a 3D mannequin in the
  samples. Likeness the same (0.61 vs 0.64), but the art direction is lost -- the reader takes
  the eyeless mannequin for "eyes closed", misses black and white and motion blur. The sample
  image never enters the generation (R3 uses its skeleton and recipe only), so a real model
  in the samples costs nothing in identity. Libraries keep real (generated) models.

## Known and open

- **The face pass flattened expression** (a laugh came back closed-mouthed).
  Fixed for packages by naming the read expression in the face prompt
  (`lectura.prompt_cara`); custom shoots still use the generic prompt.
- **2026-09-24 driver reset** after ~6 h of continuous generation. Every engine
  call now waits for the card to be under 75 C and blocks rest 60 s
  (`motor_qwen.enfriar`, `servicio.DESCANSO_S`).
- **Pose in words is less exact than a skeleton** for unusual poses. Fine on the
  ten tested; the skeleton path is one flag away.
- **Speed.** ~5 min per photo at 1.5K / 40 steps with a face pass; 30 photos is
  ~2–2.5 h on this laptop. The 6-photo preview exists for that reason.

## SAM 3

transformers 5.17 has `Sam3Model`, but the weights (`facebook/sam3`) are gated.
This machine already has ComfyUI's SAM 3 port and `sam3.1_multiplex_fp16.safetensors`,
so `sam3/sam3_masks.py` imports ComfyUI's code headless with ComfyUI's embedded
Python — no server. Loads in ~2 s, ~0.35 s per image. It runs in its own process
that exits before the next generation, so it never shares the card with Qwen
(QwenStudio's allocator ceiling assumes it is alone on the GPU).

## Layout

```
photobook/servidor.py   HTTP server, API, zip download
photobook/servicio.py   sessions on disk + the single worker thread
photobook/tomas.py      catalogue, shot planning, prompts
photobook/caras.py      SAM 3 + ArcFace subprocesses, face rebuild and stitch
photobook/motor_qwen.py client for QwenStudio's HTTP API
photobook/web/          the page (one file)
catalogo/               catalogue.json, thumbnails, pose skeletons (all made with Qwen)
sam3/sam3_masks.py      SAM 3 headless (ComfyUI embedded Python)
herramientas/           faceid.py, crear_catalogo.py, build_poses.py, hoja.py
sesiones/<id>/          one folder per shoot: entrada/, fotos/, estado.json
pruebas/                the experiments behind the decisions above
```

## Dependencies

See the README. Since 2026-09-26 Photobook has its own light environment (no torch):
ArcFace and DWPose run on onnxruntime; SAM 3 (optional, the retired automatic face pass)
still needs ComfyUI's Python via `PHOTOBOOK_COMFY_PY`.

## Timing

~170 s to compose a shot at 1.5K / 40 steps, ~180 s for a face pass. A 30-photo
shoot is roughly 2–2.5 hours depending on how many faces need the pass.

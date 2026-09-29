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

---

## Likeness of a real person: which input (2026-09-27, pruebas/exp40–42)

The worry: avatars came out right, real people did not. Tested with a real person (a consenting
volunteer; her photos and the results stay on this machine, never in the repository)
on six realistic travel shots (Paris, Alps: close-up, half, full length), skeleton control,
same seeds, one description of her. **Likeness = mean ArcFace similarity against 11 distinct
photos of her that are never used as input.** Every row was also looked at: the comparison
comparison sheets (kept locally in `pruebas/`, with the photos) are the
evidence, the numbers only sort them.

A trap worth remembering: her folders held the same photos twice under different names, and
the first yardstick contained copies of two input photos -- which inflated exactly those
inputs (0.61 for one of them). The yardstick was rebuilt from de-duplicated photos (32 files
→ 20 distinct) and everything re-scored; no image was regenerated. **Always de-duplicate a
client's photos before scoring against them.**

### 1 · What goes in (exp40)

| Input (person references) | likeness |
|---|---|
| **F2 — one close-up only** | **0.50** |
| F6 — three separate references: two close-ups + full body | 0.42 (one shot came back with **two women**) |
| F5 — a collage: four real face photos (2x2) + full body, in one image | 0.41 |
| F1 — the app's sheet: close-up + full body (the default until now) | 0.41 |
| F3 — the sheet with a very tight close-up | 0.34 |
| F4 — the sheet + a second close-up as another reference | 0.34 |

One clean close-up beats every combination. Each extra reference — a body photo, a second
face — dilutes the face, and with several images of the person the model may draw her twice.
Her build still comes through without a body photo: the description ("curvy, full-figured
build") carries it.

### 2 · What else moves it (exp41, on F2)

| Variant | likeness |
|---|---|
| base (1.0 MP, with her description) | 0.50 |
| without her description | 0.48 |
| + Enhance (W2) | **0.46** |
| "1.5 MP" | 0.50 — identical images |

- The description helps a little: keep it.
- **Enhance hurts a real person**: it re-draws the face harder and more contrasted, a step
  away from her. A button, never automatic.
- "1.5 MP" changed nothing because it could not: the skeleton counts as a reference, so
  person + skeleton are two images and the engine's memory ceiling for two is 1.0 MP.

### 3 · Which close-up to ask for (exp42)

| The one close-up | likeness |
|---|---|
| **outdoors, natural daylight, little make-up** | **0.55** |
| studio, frontal, even light | 0.50 |
| selfie at arm's length, red lips | 0.47 |
| very tight, the face filling the frame | 0.32 |

(Without the one yardstick photo from the same outdoor session: 0.52 / 0.50 / 0.46 / 0.31 —
the order holds.) Make-up and lighting of the reference **carry into every photo**: with the
selfie and the tight close-up she wears red lips and eye shadow everywhere. A very tight crop
loses the head's shape and hairline.

### What this suggests (not applied yet — the user decides)

1. Use **one close-up as the only person reference** instead of the 16:9 sheet, and keep the
   description (it carries hair and build; the body photo can still feed the description).
2. Ask the client for **a natural-light close-up, head and shoulders, not too tight, little
   make-up**; the app already crops head-and-shoulders, which is the right framing.
3. Keep Enhance off by default for real clients.

### 4 · A likeness LoRA (exp43–44) — and a loader bug that hid it

References alone keep the *type* of person (hair colour, skin, build) but not a real face:
looking at the sheets, none of the faces was really her, whatever the number said. A LoRA of
the person is the standard answer. The first test of an existing AI-Toolkit LoRA (rank 16,
2000 steps) looked useless — **alone it scored 0.16** — until the engine log showed why:

> *Loading adapter weights … unexpected keys: transformer_blocks.N.img_mlp.gate_up.lora_A/B*

AI-Toolkit trains Qwen-Image 2.1's image MLP as one fused linear, `img_mlp.gate_up` =
`[gate_layer; proj]`; diffusers has the two separately, so it **silently dropped every MLP
adapter of all 32 blocks** and used the attention part only. `herramientas/convertir_lora_qwen21.py`
splits them (A shared, B's rows halved). Same LoRA, converted:

| | likeness |
|---|---|
| the app's sheet (today) | 0.41 |
| natural close-up, no LoRA | 0.55 |
| LoRA alone, no photo | 0.16 → **0.46** after the fix |
| **LoRA + the natural close-up** | 0.51 → **0.59** (step 1000: **0.60**) |

For the first time her fringe and face shape come through. LoRA and reference complement each
other: the LoRA carries traits one photo cannot, the photo pins the face in each shot. (That
LoRA was trained on her photos, some of which are in the yardstick: part of the rise may be
memory — trust the sheets over the number.)

**Every AI-Toolkit LoRA for Qwen-Image 2.1 must be converted before QwenStudio loads it.**

Retraining (v2) with the community's advice for characters: captions that name only what
changes (clothes, place, pose, framing, light) and never her traits — the old captions tied
"black hair, bangs, fair skin, red lipstick" to those words instead of the trigger; face
crops where the face was small; the heavily filtered photo out; rank 32; 3000 steps;
`timestep_type: weighted`, content-weighted (the v2 config in AI-Toolkit, kept locally).

Result, LoRA + the natural close-up (exp45–46; v2 resumed from 3000 to 4000 without restarting —
AI-Toolkit reads the step from the file's metadata and reloads `optimizer.pt`):

| v2 step | 1000 | 1500 | 2000 | 2500 | 3000 | 3500 | 4000 |
|---|---|---|---|---|---|---|---|
| likeness | 0.47 | 0.50 | 0.52 | 0.52 | 0.54 | **0.55** | 0.53 |

v2 peaks around 3500 and never reaches v1 (0.60 at step 1000); alone it scores 0.39 against v1's
0.46. On the sheets v2 always gets her fringe, but the face comes out rounder and softer; v1 is
still the closest. The "best practice" retrain was worse.

### 5 · Why v2 lost — read from what was run, no new tests yet

What actually differed between the two runs (both adamw8bit, LR 1e-4, batch 1, alpha = rank so
the LoRA scale is 1.0 in both — the learning rate was *not* what changed):

| | v1 | v2 |
|---|---|---|
| rank / alpha | 16 / 16 | 32 / 32 |
| captions | describe her traits | trait-free (trigger only) |
| dataset | 33 originals | 32 originals + 8 upscaled face crops |
| timesteps | shift | weighted |
| best step | 1000 (of 2000) | 3500 (of 4000) |

- **Learning rate.** 1e-4 is the published default for Qwen character LoRAs; the usual advice is
  to drop to 5e-5 when the face "morphs" or averages out — which is what v2's rounder, softer
  face looks like. Those guides also pair rank 32 with alpha 16 (scale 0.5), i.e. half the
  effective step we used at rank 32. v1 peaking at 1000 and staying flat to 2000 also says 1e-4
  is on the fast side for one person. A slower LR is the most likely single gain.
- **Captions.** The trait-free rule is the community standard, but here the descriptive captions
  won. Plausibly because with ~20 distinct photos the words gave the model anchors, and the
  reference photo in the pipeline already carries the face.
- **Face crops.** Upscaled from small faces: they teach a smoother, lower-detail face — consistent
  with the softness.
- **Rank 32 + weighted timesteps** make each step move more of the model: slower to converge,
  more room to drift into an average face.
- **Methods (Prodigy, LoKr, DOP/differential guidance).** No published side-by-side for real
  people on Qwen-Image was found; only anecdotes. Nothing to adopt from evidence.
- Caveat on all of it: the yardstick gallery overlaps both training sets.

If a v3 is tried: v1's photos and captions (no crops), rank 16–32 with alpha half the rank,
LR 5e-5, `timestep_type: shift`, 3000 steps saved every 500 — one variable family, compared on
the same 6 shots.

## Saved people (2026-09-28)

A character is the hash of its close-up (`_personaje`); its profile in `sesiones/_personajes.json`
now also holds `lora` and `trigger`. *New shoot* from a saved person copies the photos and sheet
of that person's latest session into a new one — the originals are never shared between
sessions, so deleting one shoot cannot break another. With a LoRA set, `_procesar` swaps the
reference from the sheet to the close-up alone and adds the trigger word to the recipe and the
description (exp43–46); without one nothing changes. A LoRA file that disappears from `loras/`
falls back to the photos-only path instead of failing the shoot.

## BFS face / body swap as a second pass (exp48, 2026-09-28) — test only, not in the app

[BFS](https://huggingface.co/Alissonerdx/BFS-Best-Face-Swap) LoRAs for Qwen-Image 2.1, run over the
app's output today (sheet, no LoRA) through QwenStudio `/api/editar` with `crudo=True` and the
authors' exact prompts. Both files ship with the fused `img_mlp.gate_up` and need the converter.

| | likeness |
|---|---|
| app today | 0.41 |
| + BFS head v1.1 (scene + natural close-up) | **0.59** |
| + BFS body v1.0 (scene + full-body photo at 0.59 MP) | 0.54 |
| LoRA v1 + photo (needs training) | 0.60 |

The head swap matches the trained LoRA with no training, and keeps the scene, outfit and pose
exactly; the user judged it closer on sight. It swaps the whole head, so headwear goes (the
beanie in alpes_f_04 disappeared). The body swap is not usable for us: it carries the
reference's clothes, and in two of six it pasted the reference photo's room in whole.

## BFS in every shoot; the likeness LoRA optional (2026-09-28, the user's call)

After exp48–52 the user decided: **the BFS head swap always runs**, right after each photo is
composed (`CALIDAD["bfs"]`, `servicio._procesar` → `motor_qwen.cambiar_cabeza`), with the client's
close-up as `<image2>` at ~0.59 MP and the authors' prompt verbatim. The composed photo stays as
"Before"; Enhance starts from the swapped one. If the BFS file is missing from QwenStudio's
`loras/`, shoots run as before. A likeness LoRA stays optional, per profile, and is used while
composing at **0.25** (`lora_escena`; exp50: 0.25–0.5 all reach ~0.60 alone and ~0.65 with BFS, and
the lower weight keeps the scene closest to the no-LoRA one).

Two LoRAs at once works (QwenStudio `loras_extra`, exp52: BFS 1.0 + the likeness LoRA in the same
swap) but did not beat BFS alone — café 0.65→0.67, 80s 0.45→0.42/0.44, comic 0.66→0.64/0.62. The user judged on sight that it
helps, so `lora_en_bfs` is 0.25 for characters with a likeness LoRA.

A body that came out too full was the description's doing: the AI one said "curvy, full-figured",
and the profile's "1.61, 65 kg" reads the same way — with a LoRA the reference is the close-up only,
so the build comes from the words. Describe the build in words ("petite and slim"), not numbers.

Six galleries (exp51, LoRA 0.25 + BFS): comic 0.22→0.66 and 3D animated 0.12→0.52 keep their style;
80s 0.31→0.45, sci-fi 0.53→0.60. Two failures to watch: the abstract-light portrait (BFS dropped
the rainbow light and pasted the reference photo, straps included — the number rose to 0.73 all
the same), and far shots (Amalfi, a tiny face: nothing for BFS to work on).

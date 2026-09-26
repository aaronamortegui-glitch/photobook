"""The 2026-09-26 library: every package is one STORY -- a day, a trip, an adventure --
told in shots people would actually post. Variety inside (close-ups, half and full
body, day and night), but the same character, outfit logic and place from start to end.

Three photographic stories and four illustrated ones, each in a women's and a men's
version. Writes each paquete.json (if missing); the samples are drawn on fal in 4K
by crear_paquete_fal.py. House models: lucia (women), marcus (men).

Shot: (framing, camera, what the subject does, where[, outfit for that shot])
"""
import json, os
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(RAIZ, "catalogo", "paquetes")
FOTO = "Shot on a full-frame camera, natural skin texture, true-to-life colour, Instagram-worthy travel photography"

HISTORIAS = {
 # ------------------------------------------------------------------ photographic
 "paris": dict(
  label="A day in Paris", hint="Croissants, the Seine, Montmartre, the Eiffel Tower sparkling at night",
  estilo="A warm editorial travel photograph, soft Parisian light, 35mm look",
  cierre=FOTO + ".",
  vest={"f": "a camel trench coat over a striped Breton top, high-waisted jeans and white sneakers",
        "m": "a camel overcoat over a navy knit sweater, dark chinos and white sneakers"},
  noche={"f": "a little black dress with a light coat", "m": "a dark blazer over a black shirt"},
  tomas=[
   ("half", "eye level, 50mm", "sitting at a café terrace with a croissant and coffee, laughing", "at a classic Parisian café with rattan chairs, morning"),
   ("full", "wide, from behind then turning", "walking along the Seine, looking back over the shoulder", "on the quay by the Seine with the bouquinistes' green stalls"),
   ("full", "low angle, 24mm", "arms open wide, joyful", "at the Trocadéro with the Eiffel Tower behind, clear morning"),
   ("closeup", "close-up, 85mm, shallow depth of field", "soft smile, looking into the lens", "with Haussmann buildings blurred behind"),
   ("full", "wide, symmetrical", "standing in front of the glass pyramid, hands in pockets", "at the Louvre courtyard"),
   ("half", "three-quarter view", "browsing a book, candid", "inside a cluttered old Paris bookshop"),
   ("full", "high angle, looking down the steps", "sitting on the steps, eating a crêpe", "on the Montmartre steps below the Sacré-Cœur, afternoon"),
   ("full", "side view, motion", "riding a vintage bicycle with a baguette in the basket, smiling", "on a tree-lined Paris street"),
   ("half", "golden hour, backlit", "leaning on the ornate railing, wind in the face", "on Pont Alexandre III at sunset", "noche"),
   ("full", "wide, night, long lens", "looking up in wonder, holding a glass of champagne", "at night with the Eiffel Tower sparkling behind", "noche"),
  ]),
 "amalfi": dict(
  label="Amalfi summer", hint="Positano balconies, a boat day, lemon groves and a night in the piazza",
  estilo="A sun-drenched summer travel photograph, Mediterranean light, vivid turquoise and warm tones",
  cierre=FOTO + ".",
  vest={"f": "a flowing white linen dress, straw hat and sandals", "m": "an open white linen shirt, beige linen trousers and loafers"},
  bano={"f": "a terracotta swimsuit", "m": "navy swim shorts"},
  noche={"f": "a silky emerald slip dress", "m": "a cream linen suit, no tie"},
  tomas=[
   ("half", "eye level", "having breakfast on a balcony, holding an espresso, smiling", "on a Positano balcony overlooking the colourful cliff village"),
   ("full", "wide, from the stairs above", "walking down narrow stairs lined with bougainvillea", "in a Positano alley"),
   ("full", "high angle from the bow", "lying on the deck of a small wooden boat, relaxed", "on turquoise water along the Amalfi coast", "bano"),
   ("full", "wide", "diving from the boat into the sea, mid-air", "in a turquoise bay", "bano"),
   ("closeup", "close-up, 85mm", "squinting into the sun, freckles of salt water, big smile", "with the sea sparkling behind", "bano"),
   ("half", "three-quarter view", "picking a lemon, laughing", "in a lemon grove terrace"),
   ("full", "side view", "riding a mint-green Vespa along the coast road", "on the winding Amalfi coast road"),
   ("half", "eye level", "eating a gelato, playful", "in a small piazza with a fountain"),
   ("full", "golden hour, backlit", "standing at a terrace railing, hair in the wind", "above the sea at sunset"),
   ("half", "night, candle light", "raising a glass of limoncello, laughing", "at a candle-lit restaurant terrace at night", "noche"),
  ]),
 "alpes": dict(
  label="Alpine adventure", hint="A cabin morning, a lake, the summit, a cable car and a campfire night",
  estilo="An outdoor adventure photograph, crisp mountain air, epic alpine scenery",
  cierre=FOTO + ".",
  vest={"f": "a rust-orange puffer jacket, cream knit beanie, black hiking leggings and boots",
        "m": "a forest-green puffer jacket, grey beanie, hiking trousers and boots"},
  tomas=[
   ("half", "eye level, window light", "wrapped in a blanket with a steaming mug, smiling", "inside a wooden alpine cabin with a mountain view"),
   ("full", "wide from behind", "hiking up a trail with a backpack, looking at the peaks", "on an alpine trail with wildflowers"),
   ("full", "wide, reflection", "sitting on a rock by the water", "at a mirror-still turquoise alpine lake"),
   ("closeup", "close-up, cold light", "rosy cheeks, breath visible, bright eyes", "with snowy peaks blurred behind"),
   ("full", "epic wide, low angle", "arms raised in triumph", "on a summit above a sea of clouds"),
   ("half", "through the window", "pressing a hand on the glass, amazed", "inside a red cable car above the valley"),
   ("full", "wide", "lying in the grass laughing", "in a green alpine meadow with cows far behind"),
   ("half", "side light", "soaking, relaxed, eyes closed", "in an outdoor hot spring with snow around"),
   ("full", "blue hour", "walking across a wooden suspension bridge", "over a deep gorge"),
   ("half", "night, firelight", "roasting a marshmallow, laughing", "by a campfire under the stars"),
  ]),
 # ------------------------------------------------------------------ conceptual (the user's pick:
 # the abstract portraits work because each shot has one strong visual idea)
 "scifi": dict(
  label="Sci-fi 2089", hint="A day in the future: holograms, a neon megacity, a spaceport and zero gravity",
  estilo="A cinematic science-fiction film still, anamorphic lens, volumetric light, teal and magenta neon, high production value",
  cierre="Cinematic sci-fi film still, photographic, one strong visual idea.",
  vest={"f": "a sleek silver-white techwear jacket with a high collar and black fitted trousers",
        "m": "a sleek silver-white techwear jacket with a high collar and black fitted trousers"},
  tomas=[
   ("closeup", "tight close-up", "calm gaze, a glowing holographic interface reflected across the face", "in a dark control room"),
   ("half", "three-quarter view", "reaching out to touch a floating hologram of a planet", "in a minimalist white lab"),
   ("full", "wide, low angle", "walking through the rain under towering neon signs", "in a futuristic megacity street at night"),
   ("closeup", "close-up, side light", "eyes closed, lines of light scanning the face", "inside a biometric scanner"),
   ("full", "wide symmetrical", "standing before a giant window, a starship lifting off behind", "in a spaceport terminal"),
   ("half", "eye level", "riding a hover-bike, wind in the face, focused", "above a canyon at dusk"),
   ("full", "wide", "floating weightless, arms open, serene", "inside a round spaceship module with Earth in the window"),
   ("half", "backlit", "silhouette with a glowing visor pushed up, looking at two moons", "on an alien desert ridge at twilight"),
  ]),
 "ochentas": dict(
  label="Back to the 80s", hint="Film grain, synthwave neon, an arcade, a roller rink, a Polaroid and a sunset drive",
  estilo="A 1980s photograph shot on 35mm film, grain, warm faded colour, synthwave neon accents",
  cierre="Authentic 1980s look, film grain, not modern.",
  vest={"f": "a pastel windbreaker jacket, high-waisted jeans, white high-top sneakers and big hoop earrings",
        "m": "a pastel windbreaker jacket, stonewash jeans and white high-top sneakers"},
  tomas=[
   ("half", "eye level, neon glow", "playing an arcade machine, laughing, face lit by the screen", "in a crowded 80s arcade"),
   ("full", "wide, motion blur", "roller skating, arms out, joyful", "at a roller rink with a disco ball and neon lights"),
   ("closeup", "close-up, flash photo", "blowing a bubblegum bubble, playful look", "against a pink and teal backdrop"),
   ("half", "three-quarter view", "holding a boombox on the shoulder, confident grin", "on a graffiti-covered city street"),
   ("full", "wide", "sitting on the hood of a red convertible, sunglasses on", "on a palm-lined boulevard at sunset"),
   ("closeup", "instant-photo framing", "laughing, hair teased up, glitter on the cheeks", "at a neon-lit party"),
   ("half", "eye level", "browsing vinyl records, headphones around the neck", "in a small record shop"),
   ("full", "wide, synthwave", "standing on a rooftop, arms raised", "under a giant retro sunset with a neon grid skyline"),
  ]),
 # ------------------------------------------------------------------ illustrated
 "comic": dict(
  label="Comic book hero", hint="One day as the city's hero: the alarm, the leap, the rescue, the rooftop at dawn",
  estilo="A bold graphic-novel comic illustration, bold black ink outlines, flat saturated colours, halftone dot shading, dynamic panel composition",
  cierre="Comic book art, inked and coloured, not a photograph.",
  vest={"f": "an original teal and silver hero suit with a glowing star emblem and a long scarf", "m": "an original teal and silver hero suit with a glowing star emblem and a long scarf"},
  civil={"f": "a denim jacket and a yellow t-shirt", "m": "a denim jacket and a yellow t-shirt"},
  tomas=[
   ("half", "eye level", "yawning, holding a coffee mug, a phone buzzing with an alert", "in a small apartment kitchen, morning", "civil"),
   ("full", "low heroic angle", "pulling off the jacket, the hero suit showing underneath", "in a city alley", "civil"),
   ("full", "dynamic low angle", "leaping between two rooftops, scarf flying", "above the city skyline"),
   ("full", "wide", "catching a falling taxi above the street", "in a busy downtown avenue"),
   ("closeup", "tight close-up, strong ink shadows", "fierce stare into the lens", "against a burst of action lines"),
   ("half", "three-quarter view", "high-fiving a smiling kid", "in a crowded street after the rescue"),
   ("full", "wide, dusk", "standing on a gargoyle, looking over the city", "on a gothic rooftop at dusk"),
   ("half", "sunrise, backlit", "sitting on the roof edge, tired but smiling", "on a rooftop at dawn"),
  ]),
 "manga": dict(
  label="Manga summer", hint="A summer in a Japanese town: the train, the festival, fireworks — as manga pages",
  estilo="A Japanese manga illustration, black and white ink, screentone shading, clean expressive linework, speed lines",
  cierre="Manga art, black and white ink with screentones, not a photograph.",
  vest={"f": "a white t-shirt, pleated skirt and canvas sneakers", "m": "a white t-shirt, loose trousers and canvas sneakers"},
  yukata={"f": "a floral yukata", "m": "a dark striped yukata"},
  tomas=[
   ("full", "low angle, speed lines", "sprinting to catch a train, bag swinging", "on a small countryside station platform"),
   ("half", "through the window", "looking out at the sea, peaceful", "inside a local train by the coast"),
   ("closeup", "extreme close-up", "eyes wide with excitement, sweat drop", "with sparkling screentone background"),
   ("full", "wide", "riding a bicycle down a hill, arms out", "on a seaside road with cicada-summer clouds"),
   ("half", "three-quarter view", "eating shaved ice, brain freeze face", "at a small shop with hanging wind chimes"),
   ("half", "eye level", "holding a paper lantern, smiling shyly", "at a summer festival with stalls", "yukata"),
   ("full", "wide, night", "looking up at huge fireworks", "on a riverbank crowded with people", "yukata"),
   ("closeup", "close-up, fireworks light", "tears of joy, big smile", "with fireworks bursting behind", "yukata"),
  ]),
 "pixel": dict(
  label="Pixel quest", hint="A 16-bit adventure: the village, the forest, the dungeon, the dragon, the treasure",
  estilo="A 16-bit pixel art video game scene, crisp visible pixels, limited retro palette, clean dithering",
  cierre="Pixel art, every edge made of square pixels, not a photograph.",
  vest={"f": "a green adventurer tunic, brown boots and a small backpack", "m": "a green adventurer tunic, brown boots and a small backpack"},
  tomas=[
   ("full", "top-down RPG view", "stepping out of a cottage, waving", "in a cosy pixel village with a fountain"),
   ("closeup", "dialogue-box portrait", "winking, cheerful", "on a plain retro blue background"),
   ("full", "side-scroller view", "jumping between floating platforms, collecting coins", "in a colourful forest level"),
   ("full", "side view", "sailing a small boat, looking at the horizon", "on a pixel ocean at sunset"),
   ("half", "three-quarter view", "holding a torch, cautious", "in a torch-lit dungeon"),
   ("full", "boss-battle view", "raising a glowing sword", "facing a huge pixel dragon"),
   ("half", "character portrait framing", "opening a treasure chest, surprised and happy", "in the dragon's treasure room"),
   ("full", "wide", "celebrating with villagers, confetti", "back in the village square at night with lanterns"),
  ]),
 "animado3d": dict(
  label="3D animated day", hint="A feature-film day: puddles, a paper-plane flight, a cosy kitchen, the stars",
  estilo="A 3D animated feature film still, stylised characters, soft global illumination, rich colour, subsurface skin",
  cierre="3D animated film render, stylised, not a photograph.",
  vest={"f": "a yellow raincoat, striped sweater and red rubber boots", "m": "a yellow raincoat, striped sweater and red rubber boots"},
  tomas=[
   ("full", "wide low angle", "jumping into a puddle, laughing", "on a rainy cobblestone street"),
   ("half", "three-quarter view", "holding an umbrella for a soaked puppy, tender", "under a bakery awning in the rain"),
   ("closeup", "close-up", "big joyful smile, eyes sparkling", "with warm bokeh fairy lights"),
   ("full", "wide shot", "flying on a giant paper airplane, arms out", "above a toy-like city in the clouds"),
   ("half", "eye level", "baking, flour on the cheek, grinning", "in a cosy cluttered kitchen"),
   ("full", "wide", "dancing in a living room with the puppy", "in a warm lamp-lit living room"),
   ("half", "window light", "reading a book by the window, the puppy asleep on the lap", "on a window seat, rain outside"),
   ("closeup", "close-up, rim light", "thoughtful, looking up at the stars", "on a rooftop at night"),
  ]),
}
MODELO = {"f": "lucia", "m": "marcus"}

if __name__ == "__main__":
    for e, d in HISTORIAS.items():
        for g in ("f", "m"):
            pid = f"{e}_{g}"
            f = os.path.join(P, pid, "paquete.json")
            if os.path.exists(f):
                continue
            os.makedirs(os.path.dirname(f), exist_ok=True)
            tomas = []
            for k, t in enumerate(d["tomas"], 1):
                x = {"id": f"{k:02d}", "encuadre": t[0], "camara": t[1], "desc": t[2], "lugar": t[3]}
                if len(t) > 4:
                    x["vestuario"] = d[t[4]][g]
                tomas.append(x)
            pk = {"id": pid, "label": d["label"], "hint": d["hint"], "genero": g, "modelo": MODELO[g],
                  "estilo": d["estilo"], "estilo_cierre": d["cierre"], "vestuario": d["vest"][g],
                  "ilustrado": e in ("comic", "manga", "pixel", "animado3d"), "version": "2026-09-26",
                  "tomas": tomas}
            json.dump(pk, open(f, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            print("written", pid, len(tomas))

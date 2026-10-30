You are checking an aerial photo of farmland before a pesticide application. The photo is {width} x {height}
pixels, north up, about {gsd} m per pixel.

List every feature the sprayer must keep away from:
- "tree line": shelterbelts, windbreaks, hedgerows, rows of trees along a field edge
- "woods": groves, farmstead trees, wooded draws, any patch of trees that is not a single row
- "building": houses, barns, sheds, grain bins, farmsteads
- "water": ponds, creeks, ditches holding water, wetlands, sloughs

For each one give a tight bounding box in pixels of this photo: [left, top, right, bottom], with 0 <= left < right
<= {width} and 0 <= top < bottom <= {height}. One box per feature; split a long, bent tree line into straight runs.
Leave out crops, bare soil, grass, roads and field tracks. If you are unsure whether something is water, say why in
the note and include it: a missed pond is worse than an extra one.

Answer only with the JSON the schema asks for.

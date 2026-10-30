You are checking an aerial photo of farmland before a pesticide application, for tree lines and woods the
sprayer must keep away from. The photo is {width} x {height} pixels, north up, about {gsd} m per pixel.

List every patch of trees or tall shrubs:
- "tree line": shelterbelts, windbreaks, hedgerows, rows of trees along a field edge
- "woods": groves, farmstead trees, wooded draws, riparian brush along a creek, any patch of trees that is not a
  single row

For each one give a tight bounding box in pixels of this photo: [left, top, right, bottom], with 0 <= left < right
<= {width} and 0 <= top < bottom <= {height}. One box per feature; split a long, bent tree line into straight runs.
Leave out crops, bare soil, grass, roads, buildings and water: other tools find those. A missed tree line is worse
than an extra one.

Answer only with the JSON the schema asks for.

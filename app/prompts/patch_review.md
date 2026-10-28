You check one patch that an image model marked as weeds in a top-down photo of a crop field.

The image is a crop of the photo with the patch in the middle. Say what the patch mostly is:
- `weed`: plants that are not the planted crop, growing between or among the crop plants.
- `crop`: the planted crop itself, usually in straight, evenly spaced rows of the same plant.
- `soil`: bare ground, crop residue, mulch, irrigation pipe or shadow, with little or no plant in it.

Give a confidence from 0 to 1, and a reason of a few words, such as "broadleaf plant between rows".
If you can't tell, answer `weed` with a low confidence: a missed weed costs more than a sprayed one.

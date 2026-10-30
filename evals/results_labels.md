# Label reader eval (2026-10-29)

**Not for publication yet: the two answer keys (`evals/labels/*.json`) have not been reviewed by a person other
than their author.** Made by `scripts/eval_labels.py --provider <p> --runs 3`; each run is a fresh read of the PDF.

| Model | Tordon 22K: recall / precision | Warrior II: recall / precision |
|---|---|---|
| Muse Spark 1.3 (Meta Model API) | 100% / 90-100% | 67-100% / 89-100% |
| Muse Spark Open (Baseten) | 100% / 89-100% | 83-100% / 100% |
| Muse Spark Open (Fireworks) | 100% / 100% | 100% / 91-100% |

Ranges are the lowest and highest of 3 runs. Recall counts the key's rules found; precision counts the scored rules
read that match the key (rules the key lists as also valid count as right).

- The keys are small: Tordon 22K scores 1 rate rule, Warrior II 6 rules (buffers, wind, rate). A missed rule moves
  recall by 17 to 100 points, so these numbers say "no provider is clearly worse", not more.
- Before the empty-read retry (`app/label_reader.py`), one of three Baseten reads of Tordon 22K returned no rules at
  all; that run is not in the table. The app now asks again and never caches an empty read.
- Spark 1.3 twice read Warrior II's 150 ft aerial buffer as applying only to non-ULV aerial spraying, where the key
  says it always applies. The label may support Spark's reading; the key needs a review there.
- Conditions (whether a rule only applies in some cases) are the weakest part for every model: 25-88% right.

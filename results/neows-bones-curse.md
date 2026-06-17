# Neow's Bones Curse

Command:

```bash
uv run python scripts/reproduce_neows_bones_curse.py
```

Output:

```text
Offsets
  act roll:        0 (new Rng(hash(seed)))
  NEOW event:      348630328 (1 + hash('NEOW'))
  niche:           497466721 (hash('niche'))

Neow curse option: NeowsBones index 4 of 8
Available curses:  10
Weighting: exact over all 32-bit values after StringHelper.GetDeterministicHashCode(seed).

Available curse order
  0: Clumsy [Clumsy]
  1: Debt [Debt]
  2: Decay [Decay]
  3: Doubt [Doubt]
  4: Guilty [Guilty]
  5: Injury [Injury]
  6: Normality [Normality]
  7: Regret [Regret]
  8: Shame [Shame]
  9: Writhe [Writhe]

Neow's Bones curse, conditioned on underdocks and Neow's Bones option
  conditional seed count: 279,331,200
  Debt                54.237403%  [Debt]
  Decay               40.354628%  [Decay]
  Writhe               3.800525%  [Writhe]
  Doubt                1.507315%  [Doubt]
  Clumsy               0.100130%  [Clumsy]

Neow's Bones curse, conditioned on overgrowth and Neow's Bones option
  conditional seed count: 257,539,712
  Writhe              73.483296%  [Writhe]
  Shame               18.778750%  [Shame]
  Injury               5.779165%  [Injury]
  Normality            1.244538%  [Normality]
  Clumsy               0.513998%  [Clumsy]
  Guilty               0.200252%  [Guilty]
  Decay                3.883e-07%  [Decay]
```

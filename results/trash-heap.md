# Trash Heap

Commands:

```bash
uv run python scripts/reproduce_trash_heap.py --act underdocks
uv run python scripts/reproduce_trash_heap.py --act overgrowth
```

## Underdocks

```text
Offsets
  act roll:        0 (new Rng(hash(seed)))
  NEOW event:      348630328 (1 + hash('NEOW'))
  TRASH_HEAP event:371692280 (1 + hash('TRASH_HEAP'))

Source arrays
  cards:  Caltrops, Clash, Distraction, DualWield, Entrench, HelloWorld, Outmaneuver, Rebound, RipAndTear, Stack
  relics: DarkstonePeriapt, DreamCatcher, HandDrill, MawBank, TheBoot
Weighting: exact over all 32-bit run seeds in the current same-counter model.

Trash Heap card -> relic mapping
  Caltrops           -> DarkstonePeriapt
  Clash              -> DarkstonePeriapt
  Distraction        -> DreamCatcher
  DualWield          -> DreamCatcher
  Entrench           -> HandDrill
  HelloWorld         -> HandDrill
  Outmaneuver        -> MawBank
  Rebound            -> MawBank
  RipAndTear         -> TheBoot
  Stack              -> TheBoot

Trash Heap random card, conditioned on underdocks
  conditional seed count: 2,147,483,648
  Distraction         20.0000%
  Clash               14.7549%
  DualWield           13.8864%
  Entrench            10.0000%
  HelloWorld          10.0000%
  Caltrops            10.0000%
  Stack               10.0000%
  RipAndTear           6.1136%
  Outmaneuver          5.2451%
  Rebound              0.0000%

Trash Heap random card, conditioned on underdocks and Neow curse pool relic
  CursedPearl         257,539,713  HelloWorld 66.47%, Outmaneuver 32.41%, Stack 0.70%, RipAndTear 0.42%
  HeftyTablet          29,250,189  Outmaneuver 98.72%, RipAndTear 1.28%
  LargeCapsule         35,847,419  RipAndTear 98.95%, Outmaneuver 0.85%, HelloWorld 0.20%
  LeafyPoultice       268,435,456  Stack 63.78%, RipAndTear 35.15%, HelloWorld 0.83%, Entrench 0.24%
  NeowsBones          279,331,200  Caltrops 76.05%, Stack 14.77%, Clash 8.15%, Entrench 0.59%, DualWield 0.44%
  PrecariousShears    507,620,725  Clash 57.09%, Distraction 42.53%, DualWield 0.38%, Rebound 0.00%
  SilkenTress         501,023,491  DualWield 56.52%, Distraction 42.63%, Clash 0.85%
  SilverCrucible      268,435,455  Entrench 79.14%, HelloWorld 15.36%, DualWield 4.42%, Caltrops 0.86%, Stack 0.19%, Clash 0.03%

Neow curse pool order
  0: CursedPearl
  1: HeftyTablet
  2: LargeCapsule
  3: LeafyPoultice
  4: NeowsBones
  5: PrecariousShears
  6: SilkenTress
  7: SilverCrucible
```

## Overgrowth

```text
Offsets
  act roll:        0 (new Rng(hash(seed)))
  NEOW event:      348630328 (1 + hash('NEOW'))
  TRASH_HEAP event:371692280 (1 + hash('TRASH_HEAP'))

Source arrays
  cards:  Caltrops, Clash, Distraction, DualWield, Entrench, HelloWorld, Outmaneuver, Rebound, RipAndTear, Stack
  relics: DarkstonePeriapt, DreamCatcher, HandDrill, MawBank, TheBoot
Weighting: exact over all 32-bit run seeds in the current same-counter model.

Trash Heap card -> relic mapping
  Caltrops           -> DarkstonePeriapt
  Clash              -> DarkstonePeriapt
  Distraction        -> DreamCatcher
  DualWield          -> DreamCatcher
  Entrench           -> HandDrill
  HelloWorld         -> HandDrill
  Outmaneuver        -> MawBank
  Rebound            -> MawBank
  RipAndTear         -> TheBoot
  Stack              -> TheBoot

Trash Heap random card, conditioned on overgrowth
  conditional seed count: 2,147,483,648
  Rebound             20.0000%
  Outmaneuver         14.7549%
  RipAndTear          13.8864%
  Caltrops            10.0000%
  Entrench            10.0000%
  HelloWorld          10.0000%
  Stack               10.0000%
  DualWield            6.1136%
  Clash                5.2451%

Trash Heap random card, conditioned on overgrowth and Neow curse pool relic
  CursedPearl         279,331,199  HelloWorld 76.05%, Entrench 14.77%, Outmaneuver 8.15%, Stack 0.59%, RipAndTear 0.44%
  HeftyTablet         507,620,723  Outmaneuver 57.09%, Rebound 42.53%, RipAndTear 0.38%
  LargeCapsule        501,023,493  RipAndTear 56.52%, Rebound 42.63%, Outmaneuver 0.85%
  LeafyPoultice       268,435,456  Stack 79.14%, Caltrops 15.36%, RipAndTear 4.42%, HelloWorld 0.86%, Entrench 0.19%, Outmaneuver 0.03%
  NeowsBones          257,539,712  Caltrops 66.47%, Clash 32.41%, Entrench 0.70%, DualWield 0.42%
  PrecariousShears     29,250,189  Clash 98.72%, DualWield 1.28%, Rebound 0.00%
  SilkenTress          35,847,421  DualWield 98.95%, Clash 0.85%, Caltrops 0.20%
  SilverCrucible      268,435,455  Entrench 63.78%, DualWield 35.15%, Caltrops 0.83%, Stack 0.24%

Neow curse pool order
  0: CursedPearl
  1: HeftyTablet
  2: LargeCapsule
  3: LeafyPoultice
  4: NeowsBones
  5: PrecariousShears
  6: SilkenTress
  7: SilverCrucible
```

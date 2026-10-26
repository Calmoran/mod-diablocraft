"""Where the old hub's frozen inputs live (diablocraft-976b, the hub move to the Sanctum of Torment).

The hub stood in Scryer's Tier (map 530, areas 3703 and 3898) until it moved to the Sanctum of Torment (map 750,
area 4273). Seven applied migrations were generated from that hub's data files: world_0005 (the relocation),
world_0007 and world_0023 (the placements), world_0009 (the area rules), world_0010 and world_0024 (the fountain
picker and its undoing) and world_0020 (the Tester's Coffer). An applied migration is immutable
(applied_migrations.py), so the generators that wrote them must still regenerate them byte for byte, which they can
only do from the data as it was.

`tests/scryer_hub/` holds that data, copied unchanged before the live files were repointed. It is TEST FIXTURE
data only: the old positions are never shipped again, and no live generator reads it. The live files
(`data/d3/world_hub_points.csv`, `world_hub_placements.csv`, `world_areas.csv`, `world_tester_coffer.csv`) name
map 750 and area 4273, and the old hub appears there only as closed area rules.

Only these frozen generators and their tests import LEGACY; the Sanctum generators read the live files.
"""
from pathlib import Path

LEGACY = Path(__file__).resolve().parents[1] / "tests" / "scryer_hub"

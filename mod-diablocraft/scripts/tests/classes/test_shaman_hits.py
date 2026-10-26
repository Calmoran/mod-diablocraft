"""Every Shaman Defensive record that hits loads a hit above 0 (diablocraft-xnrvn.19; the Architect's rule for every Shaman skill).

The shell loader (dc_combat.cpp, the second pass) gives a record its sheet's `damage_pct` as its hit, except that a record whose
sheet states `dot_duration_seconds`, `duration_seconds` or `duration_minutes` (its own or its skill's) is read as a damage that waits
(DamageWaits) and loads its hit at 0, unless the class's `BasePct` seam claims the record. This test models that rule over the
values sheet and the class's claims, for the Defensive skills that hit an enemy through the engine (Thunderstorm and Purge): every
record of such a skill (the skill and its five runes) has a hit above 0, either because its sheet gives no duration or because the
class claims it. Planted: a claim removed, a duration added to a record.

Spirit Link's cast binds enemies and hits none (its `BasePct` says 0 on purpose; the link deals its own damage each tick), and Elemental Weapon's
cast is a self cast that hits nothing (its `damage_pct` rows are a burn's and a strike again's), and Spirit Wolves' cast hits nothing (each wolf strikes as it passes with the base skill's percent), so none of the three is in SKILLS.

The other two Defensives have no hit of the cast: Elemental Shield's and Ghost Wolf's `damage_pct` rows are a strike back and a trail
that the code deals with its own percent (Combat::Strike), and Ghost Wolf's `BasePct` says 0 on purpose.

    python mod-diablocraft/scripts/tests/classes/test_shaman_hits.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
SHAMAN = MODULE / "src/classes/shaman"
WAITS = ("dot_duration_seconds", "duration_seconds", "duration_minutes")
# skill -> (its source, the header that names its runes)
SKILLS = {"Thunderstorm": "thunderstorm", "Purge": "purge"}


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sheet_rows(skill):
    return [r for r in read(MODULE / "data/d3/shaman_skill_values.csv") if r["skill"] == skill]


def runes_of(skill):
    return [r["rune_name"] for r in read(MODULE / "data/d3/shaman_runes.csv") if r["skill_name"] == skill]


def waits(rows, rune):
    """Whether the loader would read the record's damage as one that waits: its own rows or its skill's name a duration."""
    return any(r["token"] in WAITS and r["rune"] in ("", rune) for r in rows) or \
        any(r["token"] == "damage_pct" and r["qualifier"] == "ramp" and r["rune"] in ("", rune) for r in rows)


def hits(rows, rune):
    return any(r["token"] == "damage_pct" and r["qualifier"] == "" and r["rune"] in ("", rune) for r in rows)


def claimed(skill_file, header_text, cpp_text):
    """The runes whose record the class's BasePct claims, read from the source."""
    names = dict(re.findall(r'name == "([^"]+)"\)\s*return Rune::(\w+);', header_text))
    by_enum = {enum: name for name, enum in names.items()}
    out = set()
    body = cpp_text[cpp_text.index("std::optional<double> BasePct"):]
    body = body[:body.index("\n    }\n")]
    for enum in re.findall(r"Rune::(\w+)", body):
        if enum in by_enum:
            out.add(by_enum[enum])
    # Purge claims through ClaimsHit, defined in its header
    for match in re.finditer(r"inline bool ClaimsHit\(Rune rune\)\s*\{\s*return (.*?);", header_text, re.S):
        out |= {by_enum[e] for e in re.findall(r"Rune::(\w+)", match.group(1)) if e in by_enum}
    return out


def problems(skill, rows, runes, claims):
    bad = []
    if not hits(rows, ""):
        return bad
    for rune in [""] + runes:
        if waits(rows, rune) and rune not in claims:
            bad.append(f"{skill} - {rune or 'the skill'}: its sheet gives a duration, so the loader loads its hit at 0 and the class does not claim it")
    return bad


class Hits(unittest.TestCase):
    def source(self, stem):
        return (SHAMAN / f"dc_shaman_{stem}.h").read_text(encoding="utf-8"), (SHAMAN / f"dc_shaman_{stem}.cpp").read_text(encoding="utf-8")

    def test_every_record_that_hits_loads_a_hit_above_zero(self):
        for skill, stem in SKILLS.items():
            with self.subTest(skill):
                header, cpp = self.source(stem)
                self.assertEqual(problems(skill, sheet_rows(skill), runes_of(skill), claimed(stem, header, cpp)), [])

    def test_the_claims_are_the_records_with_a_duration(self):
        # The rule is not vacuous: each skill has runes the sheet gives a duration and the class claims.
        for skill, stem in SKILLS.items():
            with self.subTest(skill):
                header, cpp = self.source(stem)
                waiting = {rune for rune in runes_of(skill) if waits(sheet_rows(skill), rune)}
                self.assertTrue(waiting, skill)
                self.assertLessEqual(waiting, claimed(stem, header, cpp))

    def test_a_planted_gap_is_caught(self):
        for skill, stem in SKILLS.items():
            header, cpp = self.source(stem)
            claims = claimed(stem, header, cpp)
            for rune in sorted(claims):
                with self.subTest(skill=skill, dropped=rune):
                    self.assertNotEqual(problems(skill, sheet_rows(skill), runes_of(skill), claims - {rune}), [])
            rows = sheet_rows(skill) + [{"skill": skill, "rune": runes_of(skill)[0], "token": "duration_seconds", "qualifier": "", "value": "3"}]
            if runes_of(skill)[0] not in claims:
                with self.subTest(skill=skill, added="a duration"):
                    self.assertNotEqual(problems(skill, rows, runes_of(skill), claims), [])


if __name__ == "__main__":
    unittest.main()

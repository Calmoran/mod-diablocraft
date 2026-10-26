"""The Shaman's Elemental Shield and its five runes (diablocraft-xnrvn.17).

What this proves, and how:

  * **The rules.** tests/shaman_elemental_shield compiles the real src/classes/shaman/dc_shaman_elemental_shield.h with no core and
    runs it over the sheet's numbers: each rune by its name; a hit spends a charge and loses the sheet's percent; the shield strikes
    back at most once an interval while every hit still spends a charge; the last charge breaks it, and an ended or broken shield
    spends nothing; a Lightning Shield's roll adds a charge up to its most and not to a dead shield; a note made when a swing is
    mitigated is paid once, by the hit it was made for, and never by a later hit from another attacker or at another time; a burn tick is
    the per-second percent of a tick. Planted mutations (the interval ignored, the charge not spent, the break not seen, the time never
    ending, no cap, the roll inverted, a note paid for any attacker or time or twice) must each make it fail.
  * **The wiring.** The engine asks the class for the damage a hit leaves (Shaman::Reduce in Mitigate) and tells it of a landed hit
    (Shaman::Landed); the class dispatches to the shield; the cast puts it on (ElementalShield::Casting); the upkeep and the
    logout keep the buffs and the Armor honest; every sheet token the code reads is a row of the rune it is read for; every
    tunable it names is a row of combat.csv and of the newest tunables migration; the six buff records the code names exist and
    their texts state the sheet's numbers. Planted: each seam gone, a token renamed, a tunable renamed, a text's number changed.

What it does not prove: anything on a running server (docs/test-diablocraft-xnrvn.17.md).

    python mod-diablocraft/scripts/tests/classes/test_shaman_elemental_shield.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
SHAMAN = MODULE / "src/classes/shaman"
HEADER = "dc_shaman_elemental_shield.h"
FLAGS = ["-std=c++17", "-O1"]
SKILL = "Elemental Shield"


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def combat():
    return {row["name"]: row["value"] or row["d3_value"] for row in read(MODULE / "data/tunables/combat.csv")}


def value(rune, token, qualifier=""):
    found = [r["value"] for r in read(MODULE / "data/d3/shaman_skill_values.csv")
             if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(found) == 1, (rune, token, qualifier, found)
    return found[0]


def args():
    return [value("", "charge_count"), value("", "damage_reduction_pct"), value("", "interval_seconds"),
            value("Stoneskin", "charge_count", "new"), value("Stoneskin", "absorb_capacity_life_pct"),
            value("Stoneskin", "absorb_duration_seconds"), value("Lightning Shield", "proc_chance_pct"),
            value("Lightning Shield", "max_count"), value("Flame Shield", "damage_pct", "burn"),
            combat()["elemental_shield_burn_tick_seconds"]]


def run_harness(mutation=None):
    text = (SHAMAN / HEADER).read_text(encoding="utf-8")
    if mutation:
        old, new = mutation
        if text.count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        text = text.replace(old, new)
    binary = harness_env.build([MODULE / "tests/shaman_elemental_shield/harness.cpp"], flags=FLAGS,
                               files={"classes/shaman/" + HEADER: text}, includes=[MODULE / "src"])
    return harness_env.run([str(binary), *map(str, args())], capture_output=True, text=True)


class Rules(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        ran = run_harness()
        self.assertEqual(ran.returncode, 0, ran.stdout[-1500:])
        print("\n  elemental shield:", ran.stdout.strip())

    def test_planted_differences_are_caught(self):
        plants = [
            ("the strike interval ignored", "if (!shield.struck || now >= shield.lastStrike + intervalMs)", "if (true)"),
            ("the strike never repeating", "if (!shield.struck || now >= shield.lastStrike + intervalMs)", "if (!shield.struck)"),
            ("the charge not spent", "        --shield.charges;\n", ""),
            ("the break not seen", "        spent.broke = shield.charges == 0;\n", ""),
            ("the time never ending", "return shield.spellId && shield.charges > 0 && shield.until > now;",
             "return shield.spellId && shield.charges > 0;"),
            ("a broken shield still active", "return shield.spellId && shield.charges > 0 && shield.until > now;",
             "return shield.spellId && shield.until > now;"),
            ("no cap on the charges", "if (!Active(shield, now) || shield.charges >= most)", "if (!Active(shield, now))"),
            ("a dead shield gaining", "if (!Active(shield, now) || shield.charges >= most)", "if (shield.charges >= most)"),
            ("the reduction inverted", "return damage * (1.0 - reductionPct / 100.0);", "return damage * (reductionPct / 100.0);"),
            ("the roll inverted", "return roll < chancePct;", "return roll > chancePct;"),
            ("a note paid for any attacker", "if (!pending.set || pending.attacker != attacker || pending.at != now)", "if (!pending.set || pending.at != now)"),
            ("a note paid at any time", "if (!pending.set || pending.attacker != attacker || pending.at != now)", "if (!pending.set || pending.attacker != attacker)"),
            ("a note paid more than once", "        pending = {};\n        return claimed;", "        return claimed;"),
            ("the burn tick not scaled", "return perSecondPct * tickSeconds;", "return perSecondPct;"),
        ]
        for label, old, new in plants:
            with self.subTest(label):
                ran = run_harness((old, new))
                self.assertNotEqual(ran.returncode, 0, f"{label} was not caught: {ran.stdout[-300:]}")


def source(path):
    return (MODULE / path).read_text(encoding="utf-8")


BUFFS = ["Elemental Shield - buff", "Elemental Shield - Lightning Shield - buff", "Elemental Shield - Stoneskin - buff",
         "Elemental Shield - Stoneskin - shield", "Elemental Shield - Water Shield - buff", "Elemental Shield - Flame Shield - buff"]
# The tokens the code reads, with the rune (blank: the skill) and qualifier whose row must hold them.
TOKENS = [("charge_count", "", ""), ("charge_count", "Stoneskin", "new"), ("duration_seconds", "", ""),
          ("damage_reduction_pct", "", ""), ("damage_pct", "", ""), ("damage_pct", "Lightning Shield", ""),
          ("interval_seconds", "", ""), ("gain_resource", "Lightning Shield", ""), ("gain_resource", "Water Shield", ""),
          ("proc_chance_pct", "Lightning Shield", ""), ("max_count", "Lightning Shield", ""), ("armor_pct", "Stoneskin", ""),
          ("absorb_capacity_life_pct", "Stoneskin", ""), ("absorb_duration_seconds", "Stoneskin", ""),
          ("heal_pct", "Water Shield", ""), ("chill_pct", "Water Shield", ""), ("chill_duration_seconds", "Water Shield", ""),
          ("radius_yards", "Flame Shield", "aura"), ("damage_pct", "Flame Shield", "burn"), ("radius_yards", "Flame Shield", "hit"),
          ("damage_pct", "Flame Shield", "hit")]


def wiring_problems(files):
    """What is wrong with the shield's wiring in `files` ({path: text}); [] when it is right."""
    problems = []
    needed = {
        "src/combat/dc_combat.cpp": ["result = Shaman::Reduce(victim, attacker, result);"],
        "src/combat/dc_combat_hooks.cpp": ["Shaman::Damaged(attacker, victim, damage);"],
        "src/combat/dc_combat_resolve.cpp": ["Shaman::Landed(player, target, spellId);"],
        "src/classes/shaman/dc_shaman.cpp": ["return Passive::Reduce(victim, ElementalShield::Reduce(victim, attacker, damage));",
                                              "ElementalShield::Damaged(attacker, victim, damage);", "ElementalShield::Landed(player, spellId);", "ElementalShield::Casting(player, spellId);",
                                              "ElementalShield::Upkeep(player);", "ElementalShield::Forget(player);"],
    }
    for path, lines in needed.items():
        for line in lines:
            if line not in files[path]:
                problems.append(f"{path} lacks {line}")
    cpp = files["src/classes/shaman/dc_shaman_elemental_shield.cpp"]
    # The core mitigates a swing before it rolls it, so Reduce only works the hit's size out; the charge and the answer are paid in
    # Damaged, when the hit has landed, even for a hit other absorbs took whole (damage 0); Stoneskin's absorb is a real core absorb.
    reduce = cpp[cpp.index("double Reduce(Unit* victim"):cpp.index("void Damaged(Unit* attacker")]
    damaged = cpp[cpp.index("void Damaged(Unit* attacker"):cpp.index("void Landed(Player* player")]
    for paid in ("Hit(state.shield", "AddAura(", "AddEventAtOffset", "Answer("):
        if paid in reduce:
            problems.append(f"Reduce pays before the hit lands: {paid}")
    for paid in ("Claim(state.pending", "Hit(state.shield", "Answer(player", "player->AddAura(BuffId(AbsorbBuff), player)",
                 "effect->ChangeAmount(", "double const amount = player->GetMaxHealth() * share * ItemPowers::ShieldFactor(player);"):
        if paid not in damaged:
            problems.append(f"Damaged does not pay: {paid}")
    if "Note(state.pending" not in reduce:
        problems.append("Reduce leaves no note for the landed hit")
    # A hit soaked to nothing must still pay: Damaged does not return on a zero damage, and the hook calls it before its own zero return.
    if "!damage" in damaged:
        problems.append("Damaged returns on a hit of no damage")
    hooks = files["src/combat/dc_combat_hooks.cpp"]
    if "Shaman::Damaged(attacker, victim, damage);" in hooks and hooks.index("Shaman::Damaged(attacker, victim, damage);") > hooks.index("if (!player || !damage)"):
        problems.append("the damage hook returns on a hit of no damage before the shield is paid")
    # Stoneskin's pool is an absorb the core drains on every hit that lands, not a number the module keeps.
    for kept in ("Soakable", "Drain(", "struct Pool", "state.pool"):
        if kept in cpp or kept in files["src/classes/shaman/dc_shaman_elemental_shield.h"]:
            problems.append(f"the module keeps a pool of its own: {kept}")
    sheet = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/d3/shaman_skill_values.csv") if r["skill"] == SKILL}
    for token, rune, qualifier in TOKENS:
        if f'"{token}"' not in cpp:
            problems.append(f"the code does not read {token}")
        if (rune, token, qualifier) not in sheet:
            problems.append(f"the sheet has no {token} {qualifier} for {rune or 'the skill'}")
    numbers = combat()
    names = set(re.findall(r'Tunable\("([a-z_]+)"\)', cpp))
    problems += [f"combat.csv has no {name}" for name in sorted(names) if name not in numbers]
    if len(names) < 2:
        problems.append("the code names fewer than two tunables")
    with (MODULE / "data/generated/spell_helper_ids.csv").open(encoding="utf-8") as stream:
        helpers = {r[0] for r in csv.reader(stream)}
    for name in BUFFS:
        if f'"{name}"' not in cpp:
            problems.append(f"the code does not name {name}")
        if name not in helpers:
            problems.append(f"{name} has no generated record")
    return problems


def numbers_in(text):
    return sorted(set(re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?=%| seconds| yards| Maelstrom)", text)))


class Wiring(unittest.TestCase):
    PATHS = ["src/combat/dc_combat.cpp", "src/combat/dc_combat_resolve.cpp", "src/combat/dc_combat_hooks.cpp", "src/classes/shaman/dc_shaman.cpp",
             "src/classes/shaman/dc_shaman_elemental_shield.cpp", "src/classes/shaman/dc_shaman_elemental_shield.h"]

    def files(self):
        return {path: source(path) for path in self.PATHS}

    def test_the_wiring_is_whole(self):
        self.assertEqual(wiring_problems(self.files()), [])

    def test_a_planted_gap_is_caught(self):
        plants = [
            ("src/combat/dc_combat.cpp", "        result = Shaman::Reduce(victim, attacker, result);\n", ""),
            ("src/combat/dc_combat_resolve.cpp", "            Shaman::Landed(player, target, spellId);\n", ""),
            ("src/combat/dc_combat_hooks.cpp", "Shaman::Damaged(attacker, victim, damage);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "ElementalShield::Damaged(attacker, victim, damage);", ""),
            # a charge spent on a swing that was mitigated and never landed
            ("src/classes/shaman/dc_shaman_elemental_shield.cpp", "        Note(state.pending, attacker ? attacker->GetGUID().GetRawValue() : 0, now, true);\n",
             "        Note(state.pending, attacker ? attacker->GetGUID().GetRawValue() : 0, now, true);\n        Hit(state.shield, now, 1000);\n"),
            # a hit soaked to nothing that pays nothing: the hook's own return first, or Damaged's
            ("src/combat/dc_combat_hooks.cpp", "                Shaman::Damaged(attacker, victim, damage);\n                Player* player = victim ? victim->ToPlayer() : nullptr;\n                if (!player || !damage)\n                    return;\n",
             "                Player* player = victim ? victim->ToPlayer() : nullptr;\n                if (!player || !damage)\n                    return;\n                Shaman::Damaged(attacker, victim, damage);\n"),
            ("src/classes/shaman/dc_shaman_elemental_shield.cpp", "void Damaged(Unit* attacker, Unit* victim, std::uint32_t)\n    {\n        Player* player = victim ? victim->ToPlayer() : nullptr;\n        if (!IsShaman(player))",
             "void Damaged(Unit* attacker, Unit* victim, std::uint32_t damage)\n    {\n        Player* player = victim ? victim->ToPlayer() : nullptr;\n        if (!IsShaman(player) || !damage)"),
            # a pool the module keeps instead of the core's absorb
            ("src/classes/shaman/dc_shaman_elemental_shield.cpp", "double const amount = player->GetMaxHealth() * share * ItemPowers::ShieldFactor(player);",
             "double const amount = player->GetMaxHealth() * share * ItemPowers::ShieldFactor(player); Drain(state.pool, amount);"),
            ("src/classes/shaman/dc_shaman_elemental_shield.cpp", "auto const paid = Claim(state.pending, attacker ? attacker->GetGUID().GetRawValue() : 0, now);",
             "std::optional<Pending> const paid = state.pending;"),
            ("src/classes/shaman/dc_shaman.cpp", "return Passive::Reduce(victim, ElementalShield::Reduce(victim, attacker, damage));", "return Passive::Reduce(victim, damage);"),
            ("src/classes/shaman/dc_shaman.cpp", "ElementalShield::Casting(player, spellId);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "ElementalShield::Upkeep(player);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "ElementalShield::Forget(player);", ""),
            ("src/classes/shaman/dc_shaman_elemental_shield.cpp", '"absorb_capacity_life_pct"', '"absorb_pct"'),
            ("src/classes/shaman/dc_shaman_elemental_shield.cpp", 'Tunable("elemental_shield_burn_tick_seconds")', 'Tunable("elemental_burn_tick")'),
            ("src/classes/shaman/dc_shaman_elemental_shield.cpp", '"Elemental Shield - Flame Shield - buff"', '"Elemental Shield - Fire - buff"'),
        ]
        for path, old, new in plants:
            with self.subTest(old):
                files = self.files()
                self.assertIn(old, files[path])
                files[path] = files[path].replace(old, new)
                self.assertNotEqual(wiring_problems(files), [], f"{old!r} -> {new!r} was not caught")

    def test_the_tunables_are_in_the_newest_migration(self):
        names = set(re.findall(r'Tunable\("([a-z_]+)"\)', source("src/classes/shaman/dc_shaman_elemental_shield.cpp")))
        migration = (MODULE / "data/sql/db-world/updates" / (MODULE / "data/tunables/current_migration.txt").read_text().strip()).read_text(encoding="utf-8")
        for name in sorted(names):
            self.assertIn(f"('combat', '{name}',", migration, name)

    def test_the_buff_texts_state_the_sheets_numbers(self):
        rows = {r["identity"]: r for r in read(MODULE / "data/class_buffs.csv") if r["class"] == "shaman"}
        s = lambda rune, token, qualifier="": float(value(rune, token, qualifier))  # noqa: E731
        expected = {
            "Elemental Shield - buff": {s("", "damage_reduction_pct"), s("", "damage_pct")},
            "Elemental Shield - Lightning Shield - buff": {s("", "damage_reduction_pct"), s("Lightning Shield", "damage_pct"),
                                                           s("Lightning Shield", "gain_resource"), s("Lightning Shield", "proc_chance_pct")},
            "Elemental Shield - Stoneskin - buff": {s("", "damage_reduction_pct"), s("", "damage_pct"), s("Stoneskin", "armor_pct")},
            "Elemental Shield - Stoneskin - shield": {s("Stoneskin", "absorb_capacity_life_pct")},
            "Elemental Shield - Water Shield - buff": {s("", "damage_reduction_pct"), s("", "damage_pct"), s("Water Shield", "heal_pct"),
                                                       s("Water Shield", "gain_resource"), s("Water Shield", "chill_pct"),
                                                       s("Water Shield", "chill_duration_seconds")},
            "Elemental Shield - Flame Shield - buff": {s("", "damage_reduction_pct"), s("Flame Shield", "damage_pct", "burn"),
                                                       s("Flame Shield", "damage_pct", "hit"), s("Flame Shield", "radius_yards", "aura"),
                                                       s("Flame Shield", "radius_yards", "hit")},
        }
        self.assertEqual(sorted(expected), sorted(BUFFS))
        for identity, want in expected.items():
            row = rows[identity]
            self.assertNotIn("$s", row["text"], identity)
            self.assertEqual({float(n) for n in numbers_in(row["text"])}, want, identity)
        self.assertEqual(rows["Elemental Shield - buff"]["max_stacks"], "Elemental Shield/charge_count")
        self.assertEqual(rows["Elemental Shield - Stoneskin - buff"]["max_stacks"], "Elemental Shield - Stoneskin/charge_count/new")
        self.assertEqual(rows["Elemental Shield - Lightning Shield - buff"]["max_stacks"], "Elemental Shield - Lightning Shield/max_count")

    def test_stoneskins_absorb_is_a_real_core_absorb_of_every_school(self):
        import test_spell_records as records
        names, spells = records.parse((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"), every_class=True)
        with (MODULE / "data/generated/spell_helper_ids.csv").open(encoding="utf-8") as stream:
            ids = {r[0]: int(r[1]) for r in csv.reader(stream) if r and r[1].isdigit()}
        row = spells[ids["Elemental Shield - Stoneskin - shield"]]
        field = lambda name: row[names.index(name)]  # noqa: E731
        self.assertEqual((field("Effect_1"), field("EffectAura_1"), field("EffectMiscValue_1")), ("6", "69", "127"),
                         "an apply-aura effect of SCHOOL_ABSORB over every school")
        csv_row = {r["identity"]: r for r in read(MODULE / "data/class_buffs.csv")}["Elemental Shield - Stoneskin - shield"]
        self.assertEqual(csv_row["kind"], "absorb")

    def test_a_changed_text_number_is_caught(self):
        text = {r["identity"]: r for r in read(MODULE / "data/class_buffs.csv") if r["class"] == "shaman"}["Elemental Shield - buff"]["text"]
        self.assertNotEqual(numbers_in(text), numbers_in(text.replace("30%", "35%")))


if __name__ == "__main__":
    unittest.main()

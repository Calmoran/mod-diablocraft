"""Shaman passives, first four (src/classes/shaman/dc_shaman_passives.h and .cpp): Elemental Focus, Call of Flame, Elemental Fury and
Ancestral Knowledge.

What this proves, and how:

  * **The logic that needs no core type.** tests/shaman_passives/harness.cpp compiles the real dc_shaman_passives.h with the sheet's own
    numbers: a ready Elemental Focus cuts the cost and the next cast spends it, not the cast whose critical hit armed it; Call of Flame's
    bonus is for Fire hits only and its burns last the extra seconds longer, dealing the same damage each second. Mutations planted in
    a scratch copy must each make it fail.
  * **The cost auras.** Elemental Focus cuts every Secondary skill through its hidden cost aura: Chain Lightning, Lava Burst, Earthquake
    (Shaman) and Elemental Blast are all among the cost-cut skills, each with a record in the newest combat migration; the sheet's
    cost probe is none of them.
  * **Every burn passes through one place.** Call of Flame lengthens the Burning effects, so no Shaman skill starts a burn or marks an
    enemy Burning except `Burning::Burn`.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of shaman_passive_values.csv for its passive; none of
    these passives has a tunable.
  * **The wiring.** The class dispatch answers the paying, landing, cast, multiplier, upkeep and logout seams; the sheet numbers
    (Critical Hit Damage, Intelligence, maximum Maelstrom) are held and put right by the upkeep.

What it does not prove: anything on a running server. The passives are docs/test-diablocraft-xnrvn.37.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_shaman_passives.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/shaman/dc_shaman_passives.h"
HEADERS = [HEADER, "src/combat/dc_damage_buckets.h"]
HARNESS = MODULE / "tests/shaman_passives/harness.cpp"
CODE = MODULE / "src/classes/shaman/dc_shaman_passives.cpp"
PASSIVES = ["Elemental Focus", "Call of Flame", "Elemental Fury", "Ancestral Knowledge", "Lightning Overload", "Frozen Power", "Rooted in Earth", "Deep Maelstrom", "Storm Surge",
            "Elemental Harmony", "Reincarnation", "Primal Wisdom", "Ancestral Guidance",
            "Elemental Oath", "Echo of the Elements", "Elemental Equilibrium", "Primal Elementalist", "Natural Harmony"]
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0137_shaman_secondary_cost_auras.sql"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(passive, token, qualifier=""):
    rows = [r for r in read(D3 / "shaman_passive_values.csv") if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (passive, "", token, qualifier)]
    assert len(rows) == 1, (passive, token, qualifier, len(rows))
    return float(rows[0]["value"])


def scratch_tree(mutate=None):
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in HEADERS}
    if mutate:
        old, new = mutate
        key = HEADER[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Elemental Focus", "cost_reduction_pct"), value("Call of Flame", "damage_bonus_pct"), value("Call of Flame", "duration_seconds"),
               value("Lightning Overload", "proc_chance_pct"), value("Lightning Overload", "damage_share_pct"), value("Frozen Power", "damage_bonus_pct"),
               value("Rooted in Earth", "duration_seconds"), value("Rooted in Earth", "damage_reduction_pct"), value("Storm Surge", "crit_chance_pct"), 250,
               value("Reincarnation", "life_floor_pct"), value("Reincarnation", "duration_seconds"), value("Reincarnation", "internal_cooldown_seconds"),
               value("Primal Wisdom", "per_trigger_resource"), value("Primal Wisdom", "cooldown_reduction_seconds"),
               value("Ancestral Guidance", "heal_pct", "per_enemy"), value("Ancestral Guidance", "heal_pct", "cap"),
               value("Elemental Oath", "radius_yards", "aura"), value("Echo of the Elements", "cooldown_reduction_pct"),
               value("Elemental Equilibrium", "damage_taken_pct"), value("Elemental Equilibrium", "max_bonus_pct"),
               value("Natural Harmony", "damage_bonus_pct"), value("Natural Harmony", "max_bonus_pct"),
               value("Primal Elementalist", "damage_bonus_pct"), value("Primal Elementalist", "duration_bonus_pct")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 29, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a focus that is not ready cuts", ("return ready && pct > 0 ? pct : 0.0;", "return pct > 0 ? pct : 0.0;")),
            ("a focus cuts nothing", ("return ready && pct > 0 ? pct : 0.0;", "return 0.0;")),
            ("the arming cast spends its own focus", ("return ready && cast > armedAt;", "return ready && cast >= armedAt;")),
            ("a focus is never spent", ("return ready && cast > armedAt;", "return false;")),
            ("a focus is spent by a cast before it", ("return ready && cast > armedAt;", "return ready;")),
            ("every element takes the Fire bonus", ('return on && element == "fire" && pct > 0 ? pct : 0.0;', "return on && pct > 0 ? pct : 0.0;")),
            ("the Fire bonus needs no passive", ('return on && element == "fire" && pct > 0 ? pct : 0.0;', 'return element == "fire" && pct > 0 ? pct : 0.0;')),
            ("a burn lasts no longer", ("return on && seconds > 0 && extraSeconds > 0 ? seconds + extraSeconds : seconds;", "return seconds;")),
            ("a burn lasts longer without the passive", ("return on && seconds > 0 && extraSeconds > 0 ? seconds + extraSeconds : seconds;", "return seconds > 0 && extraSeconds > 0 ? seconds + extraSeconds : seconds;")),
            ("a longer burn deals the same total", ("return seconds > 0 && longer > seconds ? totalPct * longer / seconds : totalPct;", "return totalPct;")),
            ("a roll over the chance casts again", ("return chancePct > 0 && roll * 100.0 < chancePct;", "return chancePct > 0 && roll * 100.0 < chancePct + 50.0;")),
            ("a roll never casts again", ("return chancePct > 0 && roll * 100.0 < chancePct;", "return false;")),
            ("the free cast deals the whole hit", ("return sharePct > 0 && sharePct < 100 ? sharePct - 100.0 : 0.0;", "return 0.0;")),
            ("the free cast deals nothing", ("return sharePct > 0 && sharePct < 100 ? sharePct - 100.0 : 0.0;", "return sharePct > 0 && sharePct < 100 ? -100.0 : 0.0;")),
            ("a Fire Secondary casts again", ('return category == "Secondary" && element == "lightning";', 'return category == "Secondary" && (element == "lightning" || element == "fire");')),
            ("a Primary skill casts again", ('return category == "Secondary" && element == "lightning";', 'return element == "lightning";')),
            ("every enemy takes Frozen Power", ("return chilledOrFrozen && pct > 0 ? pct : 0.0;", "return pct > 0 ? pct : 0.0;")),
            ("moving does not end standing still", ("return moving ? 0 : stillMs + stepMs;", "return stillMs + stepMs;")),
            ("standing still never counts", ("return moving ? 0 : stillMs + stepMs;", "return 0;")),
            ("the cut starts before the seconds", ("double(stillMs) >= seconds * 1000.0 && stillMs > 0", "stillMs > 0")),
            ("the cut needs no time standing", ("double(stillMs) >= seconds * 1000.0 && stillMs > 0", "double(stillMs) >= seconds * 1000.0")),
            ("a stack gives one crit chance", ("return perStackPct > 0 ? double(stacks) * perStackPct : 0.0;", "return perStackPct > 0 && stacks ? perStackPct : 0.0;")),
            ("the bonus is not tripled", ("return on ? HarmonyTimes : 1.0;", "return 1.0;")),
            ("the bonus is tripled without the passive", ("return on ? HarmonyTimes : 1.0;", "return HarmonyTimes;")),
            ("a blow short of the Life left is fatal", ("return health > 0 && damage >= health;", "return health > 0 && damage >= health / 2;")),
            ("a blow under the Life left is not fatal but a dead Shaman is", ("return health > 0 && damage >= health;", "return damage > health;")),
            ("it triggers every time", ("return lastMs == 0 || nowMs >= lastMs + cooldownMs;", "return true;")),
            ("it triggers once ever", ("return lastMs == 0 || nowMs >= lastMs + cooldownMs;", "return lastMs == 0;")),
            ("the immune window never closes", ("return openedMs != 0 && nowMs < openedMs + lastsMs;", "return openedMs != 0;")),
            ("the immune window is open before any save", ("return openedMs != 0 && nowMs < openedMs + lastsMs;", "return nowMs < openedMs + lastsMs;")),
            ("the Life restored is the whole floor", ("std::max(0.0, maxLife * floorPct / 100.0 - health)", "maxLife * floorPct / 100.0")),
            ("a restore lowers the Life", ("std::max(0.0, maxLife * floorPct / 100.0 - health)", "maxLife * floorPct / 100.0 - health")),
            ("every point of Maelstrom makes a step", ("unsigned const steps = unsigned(total / perStep);", "unsigned const steps = unsigned(total);")),
            ("the left over points are lost", ("return {steps, total - double(steps) * perStep};", "return {steps, 0};")),
            ("a step is made by the Maelstrom spent now only", ("double const total = carried + spent;", "double const total = spent;")),
            ("an enemy heals the cap", ("std::min(perEnemyPct, capPct - healedPct)", "capPct - healedPct")),
            ("a cast heals past the cap", ("std::min(perEnemyPct, capPct - healedPct)", "perEnemyPct")),
            ("a cast heals nothing past the first", ("perEnemyPct > 0 && capPct > healedPct ? ", "perEnemyPct > 0 && healedPct == 0 ? ")),
            ("a member outside the radius is in the aura", ("return radius > 0 && distance >= 0 && distance <= radius;", "return radius > 0 && distance >= 0;")),
            ("a member on the edge is out of the aura", ("return radius > 0 && distance >= 0 && distance <= radius;", "return radius > 0 && distance >= 0 && distance < radius;")),
            ("the cooldown loses its whole time", ("leftMs * std::min(pct, 100.0) / 100.0", "leftMs")),
            ("the cooldown loses more than it has", ("leftMs * std::min(pct, 100.0) / 100.0", "leftMs * pct / 100.0")),
            ("the cooldown loses a flat part", ("leftMs * std::min(pct, 100.0) / 100.0", "pct * 10.0")),
            ("physical is no element", ('return element == "physical" ? 3 : -1;', "return -1;")),
            ("an element counts past its seconds", ("nowMs < at[slot] + lastsMs", "nowMs <= at[slot] + lastsMs")),
            ("the element dealt now is counted for itself", ("if (slot != except && at[slot] != 0", "if (at[slot] != 0")),
            ("an element never dealt counts", ("at[slot] != 0 && nowMs < at[slot] + lastsMs", "nowMs < at[slot] + lastsMs")),
            ("the elements add past the cap", ("std::min(double(elements) * perPct, maxPct)", "double(elements) * perPct")),
            ("one element gives the cap", ("std::min(double(elements) * perPct, maxPct)", "maxPct")),
            ("another skill takes the elementals' damage", ("return on && IsElemental(skill) && pct > 0 ? pct : 0.0;", "return on && pct > 0 ? pct : 0.0;")),
            ("the elementals take the damage without the passive", ("return on && IsElemental(skill) && pct > 0 ? pct : 0.0;", "return IsElemental(skill) && pct > 0 ? pct : 0.0;")),
            ("an elemental lasts as long", ("return on && seconds > 0 && pct > 0 ? seconds * (1.0 + pct / 100.0) : seconds;", "return seconds;")),
            ("an elemental lasts the percent in seconds", ("return on && seconds > 0 && pct > 0 ? seconds * (1.0 + pct / 100.0) : seconds;", "return on && seconds > 0 && pct > 0 ? seconds + pct : seconds;")),
            ("a longer burn deals double", ("return seconds > 0 && longer > seconds ? totalPct * longer / seconds : totalPct;", "return seconds > 0 && longer > seconds ? totalPct * 2 : totalPct;")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Sheets(unittest.TestCase):
    def test_the_numbers_are_the_drafts(self):
        self.assertEqual([value("Elemental Focus", "cost_reduction_pct"), value("Call of Flame", "damage_bonus_pct"), value("Call of Flame", "duration_seconds"),
                          value("Elemental Fury", "crit_damage_pct"), value("Ancestral Knowledge", "primary_stat_pct"), value("Ancestral Knowledge", "max_pool_resource")],
                         [40, 15, 2, 50, 10, 10])

    def test_the_second_five_are_the_drafts(self):
        self.assertEqual([value("Lightning Overload", "proc_chance_pct"), value("Lightning Overload", "damage_share_pct"), value("Frozen Power", "damage_bonus_pct"),
                          value("Rooted in Earth", "duration_seconds"), value("Rooted in Earth", "damage_reduction_pct"), value("Deep Maelstrom", "max_pool_resource"),
                          value("Deep Maelstrom", "gain_resource"), value("Storm Surge", "max_stacks_count"), value("Storm Surge", "max_count"),
                          value("Storm Surge", "crit_chance_pct")],
                         [20, 75, 15, 1, 25, 30, 2, 3, 8, 2])

    def test_every_token_the_code_reads_is_a_row_of_the_sheet(self):
        code = CODE.read_text(encoding="utf-8")
        for passive, token in re.findall(r'Num\("([A-Za-z ]+)", "([a-z_]+)"\)', code):
            with self.subTest((passive, token)):
                value(passive, token)
        for passive, token, qualifier in re.findall(r'Num\("([A-Za-z ]+)", "([a-z_]+)", "([a-z_]+)"\)', code):
            with self.subTest((passive, token, qualifier)):
                value(passive, token, qualifier)

    def test_the_four_are_passives_of_the_class(self):
        names = {r["passive_name"] for r in read(D3 / "shaman_passives.csv")}
        for passive in PASSIVES:
            self.assertIn(passive, names)


class CostAuras(unittest.TestCase):
    def test_every_secondary_skill_has_its_cost_aura(self):
        sys.path.insert(0, str(MODULE / "scripts/generate/classes"))
        import generate_spells as spells
        secondaries = [r["skill_name"] for r in read(D3 / "shaman_skills.csv") if r["category"] == "Secondary"]
        self.assertEqual(sorted(secondaries), sorted(["Chain Lightning", "Lava Burst", "Earthquake (Shaman)", "Elemental Blast"]))
        for skill in secondaries:
            self.assertIn(skill, spells.skill_cost_skills(), skill)
        header = (MODULE / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8")
        shells = {r["name"]: r["spell_id"] for r in read(MODULE / "data/generated/spell_shells.csv")}
        migration = MIGRATION.read_text(encoding="utf-8")
        for skill in secondaries:
            aura = shells[f"{skill} cost reduction"]
            self.assertIn('{"%s", %s},' % (skill, aura), header, skill)
            self.assertIn(aura, migration, skill)

    def test_the_migration_is_the_newest_render(self):
        updates = MODULE / "data/sql/db-world/updates"
        self.assertEqual(sorted(p.name for p in updates.glob("combat_0*.sql"))[-1], MIGRATION.name)
        self.assertEqual(MIGRATION.read_text(encoding="utf-8"), (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("Ascendance::Casting(player, spellId); Passive::Casting(player, spellId);", self.dispatch)
        self.assertIn("ChainLightning::Landed(player, target, spellId); Passive::Landed(player, target, spellId, critical);", self.dispatch)
        self.assertNotIn("Passive::Cast(", self.dispatch)
        self.assertIn("Passive::Launched(player, spellId, triggered);", self.dispatch)
        self.assertIn("Ascendance::Multipliers(player, spellId, out); Passive::Multipliers(player, target, spellId, out);", self.dispatch)
        self.assertIn("GhostWolf::Upkeep(player); Passive::Upkeep(player, UpkeepMs);", self.dispatch)
        self.assertIn("GhostWolf::Forget(player); Passive::Forget(player);", self.dispatch)

    def test_elemental_focus_arms_on_a_critical_hit_and_a_later_secondary_cast_spends_it(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("void Launched(")]
        self.assertIn('if (!critical || !On(player, "Elemental Focus")) return;', landed)
        self.assertIn("state.armedAt = state.casts;", landed)
        self.assertIn('Cut(player, FocusCut(true, Num("Elemental Focus", "cost_reduction_pct")));', landed)
        casting = self.code[self.code.index("void Casting("):self.code.index("double Reduce(")]
        self.assertIn("++focus[guid].casts;", casting)
        cast = self.code[self.code.index("void Launched("):self.code.index("bool FreeCasting()")]
        self.assertIn('category != "Secondary"', cast)
        self.assertIn("SpendsFocus(found->second.ready, found->second.armedAt, found->second.casts)", cast)
        self.assertIn("found->second.ready = false;", cast)
        self.assertIn("Cut(player, 0.0);", cast)
        cut = self.code[self.code.index("void Cut("):self.code.index("bool Hold(")]
        self.assertIn('CostCut::Stand(player, skill, PassiveId("Elemental Focus"), pct);', cut)
        self.assertIn('Classes::CategoryOf(row.id) == "Secondary"', self.code)

    def test_call_of_flame_raises_fire_hits_by_the_element_really_dealt(self):
        mult = self.code[self.code.index("void Multipliers("):self.code.index("void Upkeep(")]
        self.assertIn('FireBonus(On(player, "Call of Flame"), ElementDealt(player, spellId), Num("Call of Flame", "damage_bonus_pct"))', mult)
        elem = self.code[self.code.index("ElementDealt(Player* player"):self.code.index("struct Focus")]
        self.assertIn("char const* dealt = DC::Combat::Shaman::Element(player, spellId);", elem)
        self.assertIn('AddFactor(out, "Call of Flame", bonus);', mult)
        self.assertIn('BurnSeconds(On(player, "Call of Flame"), seconds, Num("Call of Flame", "duration_seconds"))', self.code)

    def test_lightning_overload_casts_a_lightning_secondary_again_for_less_and_not_again_from_itself(self):
        cast = self.code[self.code.index("void Launched("):self.code.index("bool FreeCasting()")]
        self.assertIn('if (!IsShaman(player) || triggered) return;', cast)
        self.assertIn('if (category != "Secondary") return;', cast)
        self.assertIn('On(player, "Lightning Overload") && OverloadsElement("Secondary", ElementDealt(player, spellId))', cast)
        self.assertIn('Overloads(frand(0.0f, 1.0f), Num("Lightning Overload", "proc_chance_pct"))', cast)
        self.assertIn("if (rolled) owed.insert({guid, Classes::SkillIdOf(spellId)}); else owed.erase({guid, Classes::SkillIdOf(spellId)});", cast)
        made = self.code[self.code.index("void MakeOverload("):self.code.index("bool Hold(")]
        self.assertIn("if (overloading || !IsShaman(player)", made)
        self.assertIn("owed.erase({player->GetGUID().GetRawValue(), Classes::SkillIdOf(spellId)}) == 0", made)
        self.assertIn("bool const before = FreeCasting(true); Combat::CastSkill(player, row->skill, target); FreeCasting(before);", made)
        self.assertIn("MakeOverload(player, target, spellId);", self.code[self.code.index("void Landed("):self.code.index("void Launched(")])
        mult = self.code[self.code.index("void Multipliers("):self.code.index("double PrimaryGain(")]
        # The free cast's hit is the share of the damage: a factor above -100, so a hit above 0 (the sheet gives a share, not a duration).
        self.assertIn('if (overloading) if (double const cut = OverloadPct(Num("Lightning Overload", "damage_share_pct"))) AddFactor(out, "Lightning Overload", cut);', mult)
        self.assertGreater(value("Lightning Overload", "damage_share_pct") - 100.0, -100.0)
        self.assertIn("thread_local bool overloading = false;", self.code)

    # -- The free cast and the paths a cast reaches its hits by (diablocraft-lqs72).
    MARK_PINS = {
        "src/combat/dc_combat_resolve.cpp": [
            "bool freeCast = false;",
            "freeCast = Shaman::FreeCast(); Shaman::Casting(player, shell.spellId);",
            "Shaman::Launched(player, shell.spellId, GetSpell()->IsTriggered());",
            "void Impact() { Shaman::FreeHits free(freeCast);",
        ],
        "src/classes/shaman/dc_shaman.cpp": [
            "if (!IsShaman(player) || Passive::FreeCasting()) return;",
            "Passive::Launched(player, spellId, triggered);",
        ],
        "src/classes/shaman/dc_shaman_passives.cpp": [
            "if (!IsShaman(player) || triggered) return;",
            "if (overloading || !IsShaman(player) || Classes::CategoryOf(spellId) != \"Secondary\") return;",
            "bool const before = FreeCasting(true); Combat::CastSkill(player, row->skill, target); FreeCasting(before);",
            "MakeOverload(player, target, spellId);",
        ],
        "src/classes/shaman/dc_shaman.h": ["explicit FreeHits(bool on) : before(FreeCast(on)) {}", "~FreeHits() { FreeCast(before); }"],
    }

    def pin_problems(self, files):
        found = []
        for path, pins in self.MARK_PINS.items():
            text = re.sub(r"\s+", " ", files[path])
            found += [f"{path} lacks {pin!r}" for pin in pins if pin not in text]
        resolve = re.sub(r"\s+", " ", files["src/combat/dc_combat_resolve.cpp"])
        # The launch is told before the path to the hits is chosen, so every path (a projectile's impact included) has rolled.
        if "Shaman::Launched(" not in resolve or resolve.index("Shaman::Launched(") > resolve.index("switch (GroundMissile::PathOf("):
            found.append("Launched is not called before the path switch")
        return found

    def pin_files(self):
        return {path: (MODULE / path).read_text(encoding="utf-8") for path in self.MARK_PINS}

    def test_the_free_cast_is_marked_for_its_delayed_hits_and_every_cast_path_rolls(self):
        self.assertEqual(self.pin_problems(self.pin_files()), [])

    def test_a_planted_gap_in_the_marking_is_caught(self):
        plants = [
            ("src/combat/dc_combat_resolve.cpp", "Shaman::FreeHits free(freeCast);", ""),
            ("src/combat/dc_combat_resolve.cpp", "freeCast = Shaman::FreeCast();", ""),
            ("src/combat/dc_combat_resolve.cpp", "Shaman::Launched(player, shell.spellId, GetSpell()->IsTriggered());", ""),
            ("src/classes/shaman/dc_shaman.cpp", "|| Passive::FreeCasting()", ""),
            ("src/classes/shaman/dc_shaman_passives.cpp", "FreeCasting(before);", ""),
            ("src/classes/shaman/dc_shaman_passives.cpp", "if (overloading || !IsShaman(player)", "if (!IsShaman(player)"),
            ("src/classes/shaman/dc_shaman_passives.cpp", "MakeOverload(player, target, spellId);", ""),
            ("src/classes/shaman/dc_shaman_passives.cpp", "|| triggered)", ")"),
        ]
        for path, old, new in plants:
            with self.subTest(old):
                files = self.pin_files()
                self.assertIn(old, files[path])
                files[path] = files[path].replace(old, new, 1)
                self.assertNotEqual(self.pin_problems(files), [], f"{old!r} was not caught")

    def test_frozen_power_reads_the_chill_and_the_stun_hold_of_the_player(self):
        mult = self.code[self.code.index("void Multipliers("):self.code.index("double PrimaryGain(")]
        self.assertIn('if (target && On(player, "Frozen Power")) if (double const bonus = FrozenBonus(Chilled(player, target) || Held(player, target), Num("Frozen Power", "damage_bonus_pct"))) AddFactor(out, "Frozen Power", bonus);', mult)
        chill = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman_chill.cpp").read_text(encoding="utf-8"))
        self.assertIn("constexpr std::uint32_t StunHold = 15878;", chill)
        self.assertIn("target->HasAura(StunHold, player->GetGUID())", chill)

    def test_deep_maelstrom_adds_to_what_a_primary_gives(self):
        self.assertIn('return On(player, "Deep Maelstrom") ? Num("Deep Maelstrom", "gain_resource") : 0.0;', self.code)
        maelstrom = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman_maelstrom.cpp").read_text(encoding="utf-8"))
        self.assertIn("primaryFlat = (*stats)[Stat::PrimaryMaelstrom] + Passive::PrimaryGain(player);", maelstrom)

    def test_the_last_five_are_the_drafts(self):
        self.assertEqual([value("Elemental Oath", "radius_yards", "aura"), value("Elemental Oath", "crit_chance_pct"), value("Echo of the Elements", "cooldown_reduction_pct"),
                          value("Elemental Equilibrium", "damage_taken_pct"), value("Elemental Equilibrium", "duration_seconds"), value("Elemental Equilibrium", "max_bonus_pct"),
                          value("Primal Elementalist", "damage_bonus_pct"), value("Primal Elementalist", "duration_bonus_pct"),
                          value("Natural Harmony", "duration_seconds"), value("Natural Harmony", "damage_bonus_pct"), value("Natural Harmony", "max_bonus_pct")],
                         [50, 5, 20, 5, 5, 15, 100, 50, 8, 6, 24])

    def test_the_third_four_are_the_drafts(self):
        self.assertEqual([value("Reincarnation", "life_floor_pct"), value("Reincarnation", "duration_seconds"), value("Reincarnation", "internal_cooldown_seconds"),
                          value("Primal Wisdom", "per_trigger_resource"), value("Primal Wisdom", "cooldown_reduction_seconds"),
                          value("Ancestral Guidance", "heal_pct", "per_enemy"), value("Ancestral Guidance", "heal_pct", "cap")],
                         [40, 2, 90, 30, 1, 1.5, 7.5])

    def test_elemental_harmony_triples_the_attunement_bonus_on_the_sheet_and_in_the_fire_damage(self):
        self.assertIn('return HarmonyFactor(On(player, "Elemental Harmony"));', self.code)
        attunement = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman_attunement.cpp").read_text(encoding="utf-8"))
        self.assertIn("Bonus const bonus = BonusOf(element, TableNow(), times);", attunement)
        self.assertIn("BonusOf(element, TableNow(), Passive::HarmonyFor(player)).damagePct", attunement)
        self.assertIn("if (!applied || stale || appliedTimes != times)", attunement)
        self.assertIn("state.appliedTimes = times;", attunement)

    def test_reincarnation_saves_a_fatal_blow_once_per_cooldown_and_opens_the_window(self):
        reduce = self.code[self.code.index("double Reduce("):self.code.index("void Landed(")]
        self.assertIn('if (damage <= 0 || !On(player, "Reincarnation")) return damage;', reduce)
        self.assertIn('if (Immune(last, now, Millis(Num("Reincarnation", "duration_seconds")))) return 0.0;', reduce)
        self.assertIn('if (!Fatal(damage, double(player->GetHealth())) || !CooledDown(last, now, Millis(Num("Reincarnation", "internal_cooldown_seconds")))) return damage;', reduce)
        self.assertIn("last = now;", reduce)
        self.assertIn('RestoredLife(double(player->GetHealth()), double(player->GetMaxHealth()), Num("Reincarnation", "life_floor_pct"))', reduce)
        self.assertIn("return 0.0;", reduce)
        self.assertIn("return Passive::Reduce(victim, ElementalShield::Reduce(victim, attacker, damage));", self.dispatch)

    def test_primal_wisdom_counts_what_a_secondary_pays_and_cuts_only_primal_cooldowns_that_run(self):
        casting = self.code[self.code.index("void Casting("):self.code.index("double Reduce(")]
        self.assertIn('Numbers::Get(spellId, "cost_resource").value_or(0.0) * (1.0 - CostCut::Pct(player, row->skill) / 100.0)', casting)
        self.assertIn('made = WisdomSteps(carried, paid, Num("Primal Wisdom", "per_trigger_resource"));', casting)
        self.assertIn('CutPrimals(player, made.steps * Num("Primal Wisdom", "cooldown_reduction_seconds"));', casting)
        cut = self.code[self.code.index("void CutPrimals("):self.code.index("void Guide(")]
        self.assertIn('if (std::uint32_t const left = player->GetSpellCooldownDelay(row.id)) if (Classes::CategoryOf(row.id) == "Primal")', cut)
        self.assertIn("player->ModifySpellCooldown(row.id, -std::int32_t(std::min<std::uint64_t>(left, Millis(seconds))));", cut)

    def test_ancestral_guidance_heals_once_per_enemy_of_a_cast_up_to_the_cap(self):
        guide = self.code[self.code.index("void Guide("):self.code.index("// The contribution a passive holds")]
        self.assertIn("if (guided.enemies.insert(target->GetGUID().GetRawValue()).second)", guide)
        self.assertIn('GuidanceHeal(guided.healedPct, Num("Ancestral Guidance", "heal_pct", "per_enemy"), Num("Ancestral Guidance", "heal_pct", "cap"))', guide)
        self.assertIn("guided.healedPct += heal;", guide)
        self.assertIn('Heal(player, PassiveId("Ancestral Guidance"), double(player->GetMaxHealth()) * heal / 100.0);', guide)
        landed = self.code[self.code.index("void Landed("):self.code.index("void Launched(")]
        self.assertIn('if (target && On(player, "Ancestral Guidance") && Classes::CategoryOf(spellId) == "Secondary") Guide(player, target, spellId);', landed)
        casting = self.code[self.code.index("void Casting("):self.code.index("double Reduce(")]
        self.assertIn("guidance.erase({guid, Classes::SkillIdOf(spellId)});", casting)

    def test_elemental_oath_holds_the_crit_chance_for_the_shaman_and_the_group_in_the_aura_until_nobody_renews_it(self):
        upkeep = self.code[self.code.index("void Upkeep("):self.code.index("void Forget(")]
        self.assertIn('if (On(player, "Elemental Oath")) Renew(player, stepMs);', upkeep)
        renew = self.code[self.code.index("void Renew("):self.code.index("void Record(")]
        self.assertIn('Num("Elemental Oath", "radius_yards", "aura")', renew)
        self.assertIn("std::vector<Player*> holders{shaman};", renew)
        self.assertIn("member != shaman && member->IsAlive() && member->IsInWorld() && member->GetMap() == shaman->GetMap() && InOath(shaman->GetExactDist(member), radius)", renew)
        self.assertIn("fresh = added || found->second <= Now();", renew)
        swear = self.code[self.code.index("void Swear("):self.code.index("void Renew(")]
        self.assertIn('{Source::Passives, Stat::CritChance, id, Num("Elemental Oath", "crit_chance_pct"), Bucket::Flat}', swear)
        self.assertIn("if (until <= Now()) { Swear(holder, false); return; }", swear)

    def test_echo_of_the_elements_shortens_a_primal_cooldown_when_it_launches(self):
        launched = self.code[self.code.index("void Launched("):self.code.index("bool FreeCasting()")]
        self.assertIn('if (category == "Primal") { if (auto const* row = Shells::FindAbility(spellId); row && On(player, "Echo of the Elements")) Echo(player, row->skill); return; }', launched)
        echo = self.code[self.code.index("void Echo("):self.code.index("void Lapse(Player* holder, std::uint64_t guid);")]
        self.assertIn('Num("Echo of the Elements", "cooldown_reduction_pct")', echo)
        self.assertIn("player->ModifySpellCooldown(row.id, -std::int32_t(EchoCut(double(left), pct)));", echo)

    def test_elemental_equilibrium_and_natural_harmony_read_the_element_really_dealt(self):
        record = self.code[self.code.index("void Record("):self.code.index("void MakeOverload(")]
        self.assertIn("int const slot = ElementIndex(ElementDealt(player, spellId));", record)
        self.assertIn("dealt[guid][slot] = now;", record)
        self.assertIn("equilibrium[{guid, target->GetGUID().GetRawValue()}][slot] = now;", record)
        mult = self.code[self.code.index("void Multipliers("):self.code.index("double ElementalLasts(")]
        self.assertIn('ElementsWithin(found->second, slot, now, Millis(Num("Elemental Equilibrium", "duration_seconds")))', mult)
        self.assertIn('ElementsBonus(others, Num("Elemental Equilibrium", "damage_taken_pct"), Num("Elemental Equilibrium", "max_bonus_pct"))', mult)
        self.assertIn('ElementsWithin(found->second, -1, now, Millis(Num("Natural Harmony", "duration_seconds")))', mult)
        self.assertIn('ElementsBonus(elements, Num("Natural Harmony", "damage_bonus_pct"), Num("Natural Harmony", "max_bonus_pct"))', mult)
        landed = self.code[self.code.index("void Landed("):self.code.index("void Launched(")]
        self.assertIn("Record(player, target, spellId);", landed)

    def test_primal_elementalist_raises_the_elementals_damage_and_the_two_skills_use_its_seconds(self):
        mult = self.code[self.code.index("void Multipliers("):self.code.index("double ElementalLasts(")]
        self.assertIn('ElementalDamage(On(player, "Primal Elementalist"), row->skill, Num("Primal Elementalist", "damage_bonus_pct"))', mult)
        self.assertIn('ElementalSeconds(On(player, "Primal Elementalist") && IsElemental(skill), seconds, Num("Primal Elementalist", "duration_bonus_pct"))', self.code)
        fire = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman_fire_elemental.cpp").read_text(encoding="utf-8"))
        earth = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman_earth_elemental.cpp").read_text(encoding="utf-8"))
        self.assertIn("Passive::ElementalLasts(player, Skill, Combat::ModifiedDurationSeconds(player, spellId, Lifetime(", fire)
        self.assertIn("Passive::ElementalLasts( player, Skill, Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(BaseId(), \"duration_seconds\")))", earth)

    def test_the_sheet_numbers_are_held_and_put_right(self):
        upkeep = self.code[self.code.index("void Upkeep("):self.code.index("void Forget(")]
        self.assertIn('Hold(player, Stat::CritDamage, Bucket::Flat, "Elemental Fury", On(player, "Elemental Fury") ? Num("Elemental Fury", "crit_damage_pct") : 0.0)', upkeep)
        self.assertIn('Hold(player, Stat::Intelligence, Bucket::Percent, "Ancestral Knowledge", knowing ? Num("Ancestral Knowledge", "primary_stat_pct") : 0.0)', upkeep)
        self.assertIn('Hold(player, Stat::MaxSecond, Bucket::Flat, "Ancestral Knowledge", knowing ? Num("Ancestral Knowledge", "max_pool_resource") : 0.0)', upkeep)
        self.assertIn('Hold(player, Stat::MaxSecond, Bucket::Flat, "Deep Maelstrom", On(player, "Deep Maelstrom") ? Num("Deep Maelstrom", "max_pool_resource") : 0.0)', upkeep)
        self.assertIn('Hold(player, Stat::CritChance, Bucket::Flat, "Storm Surge", On(player, "Storm Surge") ? SurgeCrit(Overcharge::Stacks(player), Num("Storm Surge", "crit_chance_pct")) : 0.0)', upkeep)
        self.assertIn("stillMs = StillMs(player->isMoving(), stillMs, stepMs);", upkeep)
        self.assertIn('Hold(player, Stat::SpecificReduction, Bucket::Flat, "Rooted in Earth", On(player, "Rooted in Earth") ? RootedCut(stood, Num("Rooted in Earth", "duration_seconds"), Num("Rooted in Earth", "damage_reduction_pct")) : 0.0)', upkeep)
        self.assertIn("Stats::Recompute(player); Inventory::PushSheet(player);", upkeep)
        self.assertIn("{Source::Passives, stat, id, wanted, bucket}", self.code)


def ground_missile():
    """The ground-missile test's own readers of the generated records (their Speed, channelling and aim)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ground_missile_test", MODULE / "scripts/tests/combat/test_ground_missile.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lightning_secondaries():
    """{spell id: name} of every Shaman Secondary skill record, runes included, whose sheet element is Lightning."""
    secondaries = [r["skill_name"] for r in read(D3 / "shaman_skills.csv") if r["category"] == "Secondary"]
    found = {}
    for row in read(MODULE / "data/generated/spell_shells.csv"):
        if row["kind"] in ("active", "rune") and row["element"] == "lightning" and any(row["name"] == s or row["name"].startswith(s + " - ") for s in secondaries):
            found[int(row["spell_id"])] = row["name"]
    return found


def unreached(facts):
    """The names whose cast reaches its hits by arrival at a point: Launched rolls for every path, but a free cast's mark is carried by the
    script of the cast (Begin, Impact), which the arrival path's landing does not see."""
    return sorted(name for name, (speed, channeled, aims) in facts.items() if speed > 0 and not channeled and not aims)


class Paths(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (REPO / "azerothcore-wotlk/src/server/game/Spells/SpellInfo.cpp").is_file():
            raise unittest.SkipTest("no core source")
        cls.module = ground_missile()
        cls.records, _ = cls.module.records()
        cls.units = cls.module.unit_targets()
        cls.secondaries = lightning_secondaries()

    def facts(self):
        out = {}
        for spell_id, name in self.secondaries.items():
            record = self.records[spell_id]
            out[name] = (float(record["Speed"]), bool(int(record["AttributesEx"]) & self.module.SPELL_ATTR1_CHANNELED),
                         self.module.aims_at_a_unit(record, self.units))
        return out

    def test_the_lightning_secondaries_are_the_sheets(self):
        self.assertEqual(sorted(self.secondaries.values()),
                         sorted(["Chain Lightning", "Chain Lightning - Forked Lightning", "Chain Lightning - Thunderhead", "Lava Burst - Volcanic Lightning",
                                 "Earthquake (Shaman) - Thundering Earth", "Elemental Blast", "Elemental Blast - Prismatic Cycle", "Elemental Blast - Elemental Echo",
                                 "Elemental Blast - Unstable Elements", "Elemental Blast - Elemental Mastery", "Elemental Blast - Primal Wellspring"]))

    def test_every_lightning_secondary_is_cast_by_a_path_that_launches_and_marks(self):
        facts = self.facts()
        self.assertEqual(unreached(facts), [])
        # The projectile is the one that was missed before: it must be among the records and reach its hits by impact.
        speed, channeled, aims = facts["Lava Burst - Volcanic Lightning"]
        self.assertTrue(speed > 0 and aims and not channeled)

    def test_a_lightning_secondary_by_arrival_would_be_caught(self):
        facts = self.facts()
        facts["Lava Burst - Volcanic Lightning"] = (20.0, False, False)
        self.assertEqual(unreached(facts), ["Lava Burst - Volcanic Lightning"])
        facts["Lava Burst - Volcanic Lightning"] = (20.0, False, True)
        self.assertEqual(unreached(facts), [])


class OneBurn(unittest.TestCase):
    """Call of Flame lengthens every Burning effect, so every burn starts in one place."""

    def test_no_skill_starts_a_burn_but_through_burning_burn(self):
        for path in sorted((MODULE / "src/classes/shaman").glob("*.cpp")):
            text = path.read_text(encoding="utf-8")
            if path.name == "dc_shaman_burning.cpp":
                continue
            with self.subTest(path.name):
                self.assertNotIn("Burning::Ignite(", text)
                self.assertNotIn("PeriodicStrike::Start(", text)

    def test_burn_lengthens_by_the_passive_and_keeps_the_dps(self):
        burning = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman_burning.cpp").read_text(encoding="utf-8"))
        self.assertIn("double const longer = Passive::BurnSecondsFor(player, seconds);", burning)
        self.assertIn("PeriodicStrike::Start(player, target, spellId, Passive::BurnTotal(totalPct, seconds, longer), longer, tickSeconds); Ignite(player, target, longer);", burning)


if __name__ == "__main__":
    unittest.main()

"""diablocraft-b3zj (buff icons build 2): the buffs of the Barbarian and the Wizard.

  * data/class_buffs.csv against everything the generator made of it: the eighteen new records (their stacks, the one
    stack's number in $s1..$s3, the sentence, no 'per stack', a buff and not a debuff, an icon of its own) and the ten
    records that already were buffs and now state their numbers (82300-82304, Vanguard, the five shields). Every
    expected number is read from the verified d3 sheets by this file's own reader, never from the sheet under test;
  * the header's Helpers, the manifest and the migration carry them;
  * the C++ that puts each one on: the same identities in the CSV, the Wizard's ClassBuffs and the calls that show
    them, one test for what the buff says and what the hit uses (Berserker Rage, Brawler), Vanguard stacking with
    Frenzy, the shields' amount left and Flame Ward's reduction as the addon line, and the contract naming exactly them;
  * the rule that decides when an aura's timer is set again (src/combat/dc_buff_values_math.h, TimerDiffers) is compiled
    and driven against an independent model, and single-rule mutants of it fail the same driver.

Not covered: that the C++ runs (it is compile-checked by syntax_check.sh; the in-game steps are in
docs/test-diablocraft-b3zj.md) and what the client draws.
"""
import csv
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import wizard_source  # noqa: E402
import barbarian_source  # noqa: E402
import test_gem_buffs as gem
import test_spell_records as records

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
D3 = MODULE / "data/d3"
BUFFS = MODULE / "data/class_buffs.csv"
CONTRACT = REPO / "docs/contracts/buff-values-messages.md"
SHEETS = {"bp": "barbarian_passive_values.csv", "bs": "barbarian_skill_values.csv",
          "wp": "wizard_passive_values.csv", "ws": "wizard_skill_values.csv"}
HELPER_BLOCKS = {"barbarian": (82400, 82499), "wizard": (83300, 83399)}


def sheet(key, skill, rune, token, qualifier=""):
    """One number of a verified d3 sheet, read here and not by the generator."""
    with (D3 / SHEETS[key]).open(encoding="utf-8", newline="") as stream:
        found = [float(r["value"]) for r in csv.DictReader(stream)
                 if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (skill, rune, token, qualifier)]
    assert len(found) == 1, (key, skill, rune, token, qualifier)
    return found[0]


# identity -> (class, stacks, the amounts $s1.. as sheet references). stacks: None, ("literal", n) or a sheet reference.
# The literal 255 is the most a stack counter holds (one byte), not a game number.
NEW = {
    "Relentless - buff": ("barbarian", None, [("bp", "Relentless", "", "cost_reduction_pct"),
                                              ("bp", "Relentless", "", "damage_taken_pct")]),
    "Berserker Rage - buff": ("barbarian", None, [("bp", "Berserker Rage", "", "damage_bonus_pct")]),
    "Brawler - buff": ("barbarian", None, [("bp", "Brawler", "", "damage_bonus_pct")]),
    "War Cry - Hardened Wrath - buff": ("barbarian", None, [("bs", "War Cry", "Hardened Wrath", "armor_pct")]),
    "Battle Rage - Into the Fray - buff": ("barbarian", ("literal", 255),
                                           [("bs", "Battle Rage", "Into the Fray", "crit_chance_pct")]),
    "Illusionist - buff": ("wizard", None, [("wp", "Illusionist", "", "movement_speed_pct")]),
    "Unwavering Will - buff": ("wizard", None, [("wp", "Unwavering Will", "", "armor_pct"),
                                                ("wp", "Unwavering Will", "", "resistance_pct"),
                                                ("wp", "Unwavering Will", "", "damage_bonus_pct")]),
    "Arcane Dynamo - flashes - buff": ("wizard", ("wp", "Arcane Dynamo", "", "stack_threshold_count"), []),
    "Arcane Dynamo - empowered - buff": ("wizard", None, [("wp", "Arcane Dynamo", "", "damage_bonus_pct")]),
    "Storm Armor - Scramble - buff": ("wizard", None, [("ws", "Storm Armor", "Scramble", "movement_speed_pct")]),
    "Frost Nova - Deep Freeze - buff": ("wizard", None, [("ws", "Frost Nova", "Deep Freeze", "crit_chance_pct")]),
    "Teleport - Safe Passage - buff": ("wizard", None, [("ws", "Teleport", "Safe Passage", "damage_reduction_pct")]),
    "Energy Twister - Storm Chaser - buff": ("wizard", ("ws", "Energy Twister", "Storm Chaser", "charge_count"),
                                             [("ws", "Energy Twister", "Storm Chaser", "damage_pct")]),
    "Wave of Force - Arcane Attunement - buff": ("wizard", ("literal", 255),
                                                 [("ws", "Wave of Force", "Arcane Attunement", "damage_bonus_pct")]),
    "Arcane Orb - Spark - buff": ("wizard", ("ws", "Arcane Orb", "Spark", "max_count"),
                                  [("ws", "Arcane Orb", "Spark", "damage_bonus_pct")]),
    "Flame Ward - buff": ("wizard", None, [("ws", "Arcane Torrent", "Flame Ward", "max_damage_pct")]),
    "Archon - kills - buff": ("wizard", ("literal", 255), [("ws", "Archon", "", "damage_bonus_pct", "kill")]),
    "Ice Armor - Crystallize - buff": ("wizard", ("ws", "Ice Armor", "Crystallize", "max_stacks_count"),
                                       [("ws", "Ice Armor", "Crystallize", "armor_pct")]),
}
# (kind, name) of the records that already were buffs -> (stacks, amounts). A stack count is only stated where the row
# gives one; Rampage's and Pound of Flesh's were already the sheet's.
EXISTING = {
    ("primary_internal", "Vanguard"): (("bs", "Frenzy", "", "max_stacks_count"), [("bs", "Frenzy", "Vanguard", "movement_speed_pct")]),
    ("passive_effect", "Inspiring Presence"): (None, [("bp", "Inspiring Presence", "", "life_regen_pct")]),
    ("passive_effect", "Nerves of Steel"): (None, [("bp", "Nerves of Steel", "", "damage_taken_pct")]),
    ("passive_effect", "Rampage"): (("bp", "Rampage", "", "max_stacks_count"), [("bp", "Rampage", "", "primary_stat_pct")]),
    ("passive_effect", "Pound of Flesh"): (("bp", "Pound of Flesh", "", "max_stacks_count"),
                                           [("bp", "Pound of Flesh", "", "life_regen_pct"),
                                            ("bp", "Pound of Flesh", "", "movement_speed_pct")]),
}
SHIELDS = ["Galvanizing Ward - shield", "Dominance - shield", "Unstable Anomaly - shield",
           "Magic Weapon - Deflection - shield", "Spectral Blade - Barrier Blades - shield"]
# The auras whose number the record cannot state, so the addon says it (docs/contracts/buff-values-messages.md).
ADDON_LINES = SHIELDS + ["Flame Ward - buff"]


def read(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def number(ref):
    return sheet(*ref)


def stacks_of(spec):
    if spec is None:
        return 0
    return spec[1] if spec[0] == "literal" else int(number(spec))


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The Shaman's five (Overcharge, Attunement) are pinned by test_shaman_maelstrom.py.
        cls.csv = {r["identity"]: r for r in read(BUFFS) if r["class"] in ("barbarian", "wizard")}
        cls.manifest = read(MODULE / "data/generated/spell_shells.csv")
        cls.names, cls.spells = records.parse((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"),
                                              every_class=True)
        cls.id_of = {(r["kind"], r["name"]): int(r["spell_id"]) for r in cls.manifest}
        cls.infinite = cls.field(cls, cls.id_of[("wizard_control", "Wizard - Taunted")], "DurationIndex")

    def field(self, spell, column):
        return self.spells[spell][self.names.index(column)]

    def check_amounts(self, spell, stacks, amounts, who):
        if stacks_of(stacks) > 1:
            self.assertEqual(str(stacks_of(stacks)), self.field(spell, "CumulativeAura"), who)
        for slot, ref in enumerate(amounts, 1):
            value = number(ref)
            self.assertTrue(value.is_integer(), "%s: $s%d is a whole number" % (who, slot))
            base, die = int(self.field(spell, "EffectBasePoints_%d" % slot)), int(self.field(spell, "EffectDieSides_%d" % slot))
            self.assertEqual(int(value), base + die, "%s: $s%d" % (who, slot))
            self.assertEqual(("6", "4", "1"), tuple(self.field(spell, c % slot) for c in ("Effect_%d", "EffectAura_%d", "ImplicitTargetA_%d")), who)

    def test_the_sheet_lists_the_new_buffs_and_the_old_ones(self):
        self.assertEqual(set(NEW), {i for i, r in self.csv.items() if r["mode"] == "new"})
        self.assertEqual({n for _, n in EXISTING} | set(SHIELDS), {i for i, r in self.csv.items() if r["mode"] == "existing"})
        for identity, (cls_, _, _) in NEW.items():
            self.assertEqual(cls_, self.csv[identity]["class"], identity)

    def test_each_new_record_is_the_buff_its_row_names(self):
        icons = []
        for identity, (cls_, stacks, amounts) in NEW.items():
            spell = self.id_of[("class_buff", identity)]
            first, last = HELPER_BLOCKS[cls_]
            self.assertTrue(first <= spell <= last, "%s is in %s's helper block" % (identity, cls_))
            self.assertEqual(identity, records.unquote(self.field(spell, "Name_Lang_enUS")))
            self.assertFalse(int(self.field(spell, "Attributes")) & 0x04000000, "%s: a buff, not a debuff" % identity)
            self.assertEqual("0", self.field(spell, "ProcTypeMask"), identity)
            self.assertEqual(self.infinite, self.field(spell, "DurationIndex"), "the module sets the seconds: " + identity)
            self.assertEqual("1", self.field(spell, "RangeIndex"), identity)   # stock Self Only
            self.assertEqual(("6", "4", "1"), tuple(self.field(spell, c) for c in ("Effect_1", "EffectAura_1", "ImplicitTargetA_1")), identity)
            self.check_amounts(spell, stacks, amounts, identity)
            if not stacks_of(stacks) > 1:
                self.assertEqual("0", self.field(spell, "CumulativeAura"), identity)
            for slot in range(max(2, len(amounts) + 1), 4):
                self.assertEqual("0", self.field(spell, "Effect_%d" % slot), "%s: slot %d is unused" % (identity, slot))
            if not amounts:   # slot 1 is the aura itself and states no number
                self.assertEqual(("0", "0"), (self.field(spell, "EffectBasePoints_1"), self.field(spell, "EffectDieSides_1")))
            icons.append(self.field(spell, "SpellIconID"))
            self.assertNotEqual("0", icons[-1], identity)
        self.assertEqual(len(icons), len(set(icons)), "every class buff has an icon of its own (donor spells)")

    def test_each_old_buff_states_its_numbers(self):
        for (kind, name), (stacks, amounts) in EXISTING.items():
            spell = self.id_of[(kind, name)]
            self.check_amounts(spell, stacks, amounts, name)
        # Nerves of Steel keeps its control immunity in slots 2 and 3 (aura 147 and 77)
        nerves = self.id_of[("passive_effect", "Nerves of Steel")]
        self.assertEqual(("147", "77"), (self.field(nerves, "EffectAura_2"), self.field(nerves, "EffectAura_3")))

    def test_the_text_is_the_sheets_and_states_one_number_per_amount_totals_never_per_stack(self):
        for identity, row in self.csv.items():
            spell = self.id_of[("class_buff", identity)] if row["mode"] == "new" else self.id_of[(row["kind"], identity)]
            text = records.unquote(self.field(spell, "AuraDescription_Lang_enUS"))
            self.assertEqual(row["text"], text, identity)
            amounts = (NEW[identity][2] if row["mode"] == "new" else
                       EXISTING[(row["kind"], identity)][1] if (row["kind"], identity) in EXISTING else [])
            self.assertEqual(["$s%d" % n for n in range(1, len(amounts) + 1)], sorted(re.findall(r"\$s\d", text)), identity)
            self.assertNotRegex(text, r"(?i)per stack|each stack|every stack", "ruling 2026-10-07: the client shows the total")
            if not amounts:
                self.assertNotRegex(text, r"\d", "%s: a number the record cannot state is the addon line's" % identity)

    def test_the_header_the_manifest_and_the_migration_carry_them(self):
        header = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        helpers = {n: int(i) for i, n in re.findall(r'\{(\d+), "([^"]+)", \d+\}', header)}
        table = set(re.findall(r"\d+", re.search(r"ShellIds\[\] = \{(.*?)\};", header, re.S).group(1)))
        migration = (MODULE / "data/sql/db-world/updates/combat_0052_class_buff_shells.sql").read_text(encoding="utf-8")
        self.assertIn("BETWEEN 81000 AND 83419", migration)
        for identity in NEW:
            spell = self.id_of[("class_buff", identity)]
            self.assertEqual(spell, helpers[identity], identity)
            self.assertIn(str(spell), table, identity)
            self.assertRegex(migration, r"(?m)^\(%d," % spell)
        for identity in SHIELDS:
            self.assertEqual(self.id_of[("wizard_shield", identity)], helpers[identity])
        dbc = REPO / "client-patch/dbc/Spell.dbc"
        if dbc.is_file():
            ids = records.dbc_ids(dbc)
            for identity in NEW:
                self.assertIn(self.id_of[("class_buff", identity)], ids)


class Source(unittest.TestCase):
    """The C++ shows each buff where its state is known, from one list, and the addon line is what the contract says."""

    @classmethod
    def setUpClass(cls):
        cls.wizard = wizard_source.CPP.read_text(encoding="utf-8")
        cls.passives = barbarian_source.PASSIVES.read_text(encoding="utf-8")
        cls.abilities = barbarian_source.abilities((".cpp",))
        cls.primaries = (SRC / "classes/barbarian/dc_barbarian_primaries.cpp").read_text(encoding="utf-8")
        cls.manifest = {r["name"]: int(r["spell_id"]) for r in read(MODULE / "data/generated/spell_shells.csv")
                        if r["kind"] in ("class_buff", "wizard_shield")}

    def block(self, text, start, end):
        i = text.index(start)
        return text[i:text.index(end, i)]

    def test_the_wizards_list_the_pushes_and_the_sheet_name_the_same_buffs(self):
        listed = re.findall(r'"([^"]+)",', self.block(self.wizard, "constexpr char const* ClassBuffs[]", "};"))
        sheet_rows = {i for i, (c, _, _) in NEW.items() if c == "wizard"}
        self.assertEqual(sheet_rows, set(listed))
        pushed = re.findall(r'shown\.push_back\(\{"([^"]+)"', self.wizard)
        self.assertEqual(sheet_rows, set(pushed), "every Wizard buff is pushed by Wanted(), and nothing else is")
        shields = re.findall(r'"([^"]+ - shield)"', self.block(self.wizard, "constexpr char const* ShieldBuffs[]", "};"))
        self.assertEqual(SHIELDS, shields)

    def test_the_wizards_wanted_shows_a_buff_where_it_puts_the_stat_on(self):
        wanted = self.block(self.wizard, "std::vector<Want> Wanted(", "// Puts this file's contributions")
        for identity, stat in (("Storm Armor - Scramble - buff", "Stat::MovementSpeed"),
                               ("Illusionist - buff", "Stat::MovementSpeed"),
                               ("Frost Nova - Deep Freeze - buff", "Stat::CritChance"),
                               ("Teleport - Safe Passage - buff", "Stat::SpecificReduction")):
            i = wanted.index('"%s"' % identity)
            self.assertIn(stat, wanted[max(0, i - 400):i], identity)
        self.assertIn('{"Flame Ward - buff", 1, 0, {reduction}}', wanted)
        refresh = self.block(self.wizard, "void Refresh(Player* player, bool force)", "} // namespace DC::Combat::Wizard::Buffs")
        self.assertLess(refresh.index("ShowBuffs(player, shown)"), refresh.index("signature == state.signature"),
                        "the buffs are settled before the sheet's early return")

    def test_the_shields_and_flame_ward_are_the_addon_lines_and_the_contract_names_them(self):
        text = CONTRACT.read_text(encoding="utf-8")
        section = text[text.index("## Values by aura"):]
        listed = {int(i) for i in re.findall(r"^\| [^|]+\| (\d{5}) \|", section, re.M)}
        for identity in ADDON_LINES:
            self.assertIn(self.manifest[identity], listed, identity)
        # only those carry values: the shields through ShowBuffs, Flame Ward through its push
        self.assertEqual(1, len(re.findall(r'shown\.push_back\(\{"[^"]+", [^{}]*\{[^{}]+\}\}\)', self.wizard)))
        self.assertIn("BuffValues::Set(player, id, {double(effect->GetAmount())})", self.wizard)
        self.assertIn("BuffValues::Clear(player, id)", self.wizard)

    def test_the_barbarians_buffs_are_shown_where_the_effect_is_decided(self):
        for identity in ("Relentless - buff", "Berserker Rage - buff", "Brawler - buff"):
            self.assertIn('HelperFor("%s")' % identity, self.passives)
        for identity in ("War Cry - Hardened Wrath - buff", "Battle Rage - Into the Fray - buff"):
            self.assertIn('HelperFor("%s")' % identity, self.abilities)
        sheet_rows = {i for i, (c, _, _) in NEW.items() if c == "barbarian"}
        self.assertEqual(sheet_rows, set(re.findall(r'HelperFor\("([^"]+ - buff)"\)', self.passives + self.abilities)))
        # what the icon says is what the hit uses: one test each
        damage = self.block(self.passives, "double DamageBonus(", "double GenerationFactor(")
        self.assertIn("BerserkerRageOn(p)", damage)
        self.assertIn("BrawlerOn(p)", damage)
        show = self.block(self.passives, "void ShowConditions(", "void Marker(")
        for call in ("Low(p)", "BerserkerRageOn(p)", "BrawlerOn(p)"):
            self.assertIn(call, show)
        self.assertIn("ShowConditions(p, s, diff);", self.passives)
        refresh = self.block(self.abilities, "void Refresh(Player* p)", "void Reduce(")
        self.assertIn("BuffValues::Show(p, WrathBuff(), wrathSeconds > 0 ? 1 : 0, wrathSeconds)", refresh)
        self.assertIn("BuffValues::Show(p, FrayBuff(), unsigned(frayEnemies))", refresh)
        self.assertIn("BuffValues::Show(p, WrathBuff(), 0)", self.abilities)   # not left on the character at logout

    def test_vanguard_stacks_with_frenzy_instead_of_carrying_the_total_in_its_base_points(self):
        self.assertNotIn("CastCustomSpell(D::VANGUARD", self.primaries)
        self.assertIn("BuffValues::Show(player, D::VANGUARD, amount ? stacks : 0, D::frenzy_duration_ms / 1000.0)", self.primaries)
        self.assertIn("Movement(player, movement, frenzyStacks)", self.primaries)

    def test_the_barbarians_upkeep_is_a_combat_row(self):
        self.assertIn('Tunables::Get("combat", "class_buff_refresh_ms")', self.passives)
        rows = {r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}
        self.assertIn("PLACEHOLDER", rows["class_buff_refresh_ms"]["notes"])


class Timer(unittest.TestCase):
    """TimerDiffers: when Show sets an aura's timer again."""

    @staticmethod
    def model(current, wanted):
        return int(wanted > current or current - wanted > 500)

    CASES = [(c, w) for c in (-1, 0, 100, 3000, 3499, 3500, 3501, 4000) for w in (1, 2999, 3000, 3001, 3500, 3999, 4000, 4001)]

    def lines(self):
        return ["timer %d %d" % case for case in self.CASES]

    def test_the_rule_is_the_one_in_the_header_comment(self):
        self.assertEqual([str(self.model(*case)) for case in self.CASES], gem.drive(self.lines()))

    def test_the_boundaries(self):
        self.assertEqual(["1", "1", "0", "0", "1"], gem.drive([
            "timer -1 3000",      # an aura with no timer yet takes one
            "timer 3000 3001",    # the window was renewed: at once, however little
            "timer 3500 3000",    # 500 ms beyond: counting down, left alone
            "timer 3000 3000",
            "timer 3501 3000",    # more than 500 ms beyond: the effect has less left
        ]))

    def test_the_mutants_fail_the_same_driver(self):
        real = gem.MATH.read_text(encoding="utf-8")
        mutants = {
            "a_renewed_window_waits": ("wantedMs > currentMs || ", ""),
            "no_slack": ("currentMs - wantedMs > DurationSlackMs", "currentMs - wantedMs > 0"),
            "slack_is_inclusive": ("currentMs - wantedMs > DurationSlackMs", "currentMs - wantedMs >= DurationSlackMs"),
            "slack_is_a_second": ("DurationSlackMs = 500", "DurationSlackMs = 1000"),
        }
        want = gem.drive(self.lines())
        for name, (old, new) in mutants.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies to the header" % name)
            self.assertNotEqual(want, gem.drive(self.lines(), real.replace(old, new), name), "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()

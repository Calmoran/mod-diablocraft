"""diablocraft-xumo (buff icons build 1): the buffs of the legendary gems.

  * data/legendary_gem_buffs.csv against everything the generator made of it: the nine records (stacks, the one stack's
    number in $s1/$s2, the sentence, no 'per stack'), the header's GemBuffs, the manifest, the migration. Every
    expected number is d3planner's own (the gem's effect text), never the sheet under test;
  * the two shells that were already buffs (the Wreath, the shield) now say what they are, and no other gem shell does;
  * docs/contracts/buff-values-messages.md lists exactly the auras whose numbers a record cannot state;
  * the throttle and the spelling of the addon records (src/combat/dc_buff_values_math.h) are compiled and driven
    against an independent model of the contract, and single-rule mutants of it fail the same driver;
  * source guards that the gem code shows and hides each buff where the state changes (they prove the call is there,
    not that it runs; the C++ is compile-checked by syntax_check.sh and the in-game steps are in
    docs/test-diablocraft-xumo.md).
"""
import csv
import random
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import test_legendary_gem_group_c as groupc
import test_legendary_gems as numbers
import test_spell_records as records

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_buff_values_math.h"
HARNESS = MODULE / "tests/buff_values/harness.cpp"
BUFFS_CSV = MODULE / "data/legendary_gem_buffs.csv"
SHELLS_CSV = MODULE / "data/legendary_gem_spells.csv"
CONTRACT = REPO / "docs/contracts/buff-values-messages.md"
GEM_POWERS = SRC / "combat/dc_gem_powers.cpp"
SCRATCH = numbers.SCRATCH


def read(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def percents(text):
    """The numbers written as 'N%' in a d3planner effect text, in order ('%.2f%' is a rank's number: skipped)."""
    return [float(n) for n in re.findall(r"(?<![%.\d])(\d+(?:\.\d+)?)%(?!\w)", text)]


# What each buff record must be, by spell id. gem name, rank25 band, the stacks and the amounts it states, with the
# d3planner effect text each number is read from (index into planner_texts()[gem]) so the sheet is not its own witness.
# amounts: [(effect text index, which 'N%' of it)] for $s1, $s2.
PLAN = {
    83411: ("Gogok of Swiftness", False, ("stacks", 0), [(0, 0)]),
    83412: ("Gogok of Swiftness", True, ("stacks", 0), [(0, 0), (1, 0)]),
    83413: ("Taeguk", False, ("stacks", 0), []),
    83414: ("Taeguk", True, ("stacks", 0), [(1, 0)]),
    83415: ("Invigorating Gemstone", False, ("stacks", 0), []),
    83416: ("Bane of the Powerful", False, None, [(0, 0)]),
    83417: ("Pain Enhancer", False, ("literal", 255), [(1, 0)]),
    83418: ("Esoteric Alteration", False, None, [(1, 0)]),
    83419: ("Moratorium", False, None, []),
}
# The auras whose numbers the record cannot state: a rank's number or a live amount (the addon line), by contract.
ADDON_LINES = {83411, 83412, 83413, 83414, 83415, 83419, 83400, 83409}
OLD_SHELL_TEXT = {83400: "Lightning pulses every second, hitting nearby enemies.", 83409: "Absorbs damage."}


def planner_stacks(effects):
    """'up to 15 times' / 'Stacks up to 10 times.' in the gem's first effect text."""
    return int(re.search(r"(\d+) times", effects[0]).group(1))


class Sheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.csv = read(BUFFS_CSV)
        cls.gems = {r["gem_id"]: r["gem_name"] for r in numbers.read(numbers.CSV) if r["gem_id"]}
        cls.effects = groupc.planner_texts()
        cls.manifest = {int(r["spell_id"]): r for r in read(MODULE / "data/generated/spell_shells.csv")}
        cls.names, cls.spells = records.parse((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"), every_class=True)

    def field(self, spell, column):
        return self.spells[spell][self.names.index(column)]

    def test_the_sheet_is_the_nine_buffs(self):
        self.assertEqual(sorted(PLAN), sorted(int(r["spell_id"]) for r in self.csv))
        shells = {int(r["spell_id"]) for r in read(SHELLS_CSV)}
        for r in self.csv:
            spell = int(r["spell_id"])
            self.assertTrue(83400 <= spell <= 83499, "outside the gem block")
            self.assertNotIn(spell, shells, "a buff is not a shell of the gem's power")
            name, rank25, _, _ = PLAN[spell]
            self.assertEqual(name, self.gems[r["gem_id"]], spell)
            self.assertEqual("1" if rank25 else "0", r["rank25"], spell)

    def test_each_record_is_the_buff_its_row_names(self):
        for r in self.csv:
            spell = int(r["spell_id"])
            name, _, stacks, amounts = PLAN[spell]
            effects = self.effects[name]
            self.assertEqual(name, records.unquote(self.field(spell, "Name_Lang_enUS")))
            # a buff on the caster that does nothing by itself: SPELL_EFFECT_APPLY_AURA, SPELL_AURA_DUMMY, TARGET_UNIT_CASTER
            self.assertEqual(("6", "4", "1"), tuple(self.field(spell, c) for c in ("Effect_1", "EffectAura_1", "ImplicitTargetA_1")))
            self.assertFalse(int(self.field(spell, "Attributes")) & 0x04000000, "a buff, not a debuff")
            self.assertEqual("0", self.field(spell, "ProcTypeMask"), "a donor's proc must not come with the shell")
            self.assertEqual(self.field(83337, "DurationIndex"), self.field(spell, "DurationIndex"), "the module sets the seconds")
            want_stacks = 0
            if stacks:
                want_stacks = planner_stacks(effects) if stacks[0] == "stacks" else stacks[1]
            self.assertEqual(str(want_stacks), self.field(spell, "CumulativeAura"), spell)
            for slot, (effect, nth) in enumerate(amounts, 1):
                number = percents(effects[effect])[nth]
                self.assertTrue(number.is_integer(), "$s%d is a whole number" % slot)
                base, die = int(self.field(spell, "EffectBasePoints_%d" % slot)), int(self.field(spell, "EffectDieSides_%d" % slot))
                self.assertEqual(int(number), base + die, "%d: $s%d" % (spell, slot))
                self.assertEqual(("6", "4", "1"), tuple(self.field(spell, c % slot) for c in ("Effect_%d", "EffectAura_%d", "ImplicitTargetA_%d")))
            for slot in range(max(2, len(amounts) + 1), 4):
                self.assertEqual("0", self.field(spell, "Effect_%d" % slot), "%d: slot %d is unused" % (spell, slot))
            if not amounts:  # slot 1 is the aura itself and carries no number
                self.assertEqual(("0", "0"), tuple(self.field(spell, "EffectBasePoints_1") for _ in range(2)))

    def test_the_text_states_one_number_per_amount_and_totals_never_per_stack(self):
        for r in self.csv:
            spell = int(r["spell_id"])
            text = records.unquote(self.field(spell, "AuraDescription_Lang_enUS"))
            self.assertEqual(r["text"], text, spell)
            amounts = PLAN[spell][3]
            self.assertEqual(sorted("$s%d" % n for n in range(1, len(amounts) + 1)), sorted(re.findall(r"\$s\d", text)), spell)
            self.assertNotRegex(text, r"(?i)per stack|each stack|every stack", "ruling 2026-10-07: the client shows the total")
            if not amounts:
                self.assertNotRegex(text, r"\d", "%d: a number the record cannot state is the addon line's" % spell)

    def test_a_rank_dependent_number_is_not_in_the_record(self):
        # Gogok's Dodge, Taeguk's damage, Invigorating's healing are '%.2f' in d3planner's text: they scale with the rank.
        for gem in ("Gogok of Swiftness", "Taeguk", "Invigorating Gemstone"):
            self.assertIn("%.2f", self.effects[gem][0], gem)
        for spell in (83411, 83412, 83413, 83414, 83415):
            text = records.unquote(self.field(spell, "AuraDescription_Lang_enUS"))
            self.assertNotRegex(text, r"(?i)dodge|healing received by|\bdamage by", spell)

    def test_the_header_lists_the_same_buffs(self):
        header = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        listed = re.findall(r'\{(\d+), "(Unique_Gem_\d+_x1)", (true|false)\}', header)
        self.assertEqual([(r["spell_id"], r["gem_id"], "true" if r["rank25"] == "1" else "false") for r in self.csv], listed)
        table = re.findall(r"\d+", re.search(r"ShellIds\[\] = \{(.*?)\};", header, re.S).group(1))
        for r in self.csv:
            self.assertIn(r["spell_id"], table, "the own-shell guard must know %s" % r["spell_id"])

    def test_the_manifest_has_a_gem_buff_row_per_record_named_as_the_gem(self):
        rows = {i: r for i, r in self.manifest.items() if r["kind"] == "gem_buff"}
        self.assertEqual(set(PLAN), set(rows))
        for r in self.csv:
            row = rows[int(r["spell_id"])]
            self.assertEqual(self.gems[r["gem_id"]], row["name"])
            self.assertEqual(r["base_spell"], row["base_spell"])

    def test_the_two_old_buff_shells_say_what_they_are_and_no_other_gem_shell_does(self):
        for r in read(SHELLS_CSV):
            spell = int(r["spell_id"])
            text = records.unquote(self.field(spell, "AuraDescription_Lang_enUS"))
            self.assertEqual(OLD_SHELL_TEXT.get(spell, ""), text, spell)
            self.assertEqual(OLD_SHELL_TEXT.get(spell, ""), r["aura_text"], spell)

    def test_the_client_record_exists_for_every_buff(self):
        dbc = REPO / "client-patch/dbc/Spell.dbc"
        if not dbc.is_file():
            self.skipTest("client Spell.dbc is generated, not tracked")
        ids = records.dbc_ids(dbc)
        for spell in PLAN:
            self.assertIn(spell, ids)

    def test_the_migration_carries_the_buffs(self):
        migration = MODULE / "data/sql/db-world/updates/combat_0051_gem_buff_shells.sql"
        sql = migration.read_text(encoding="utf-8")
        for spell in PLAN:
            self.assertRegex(sql, r"(?m)^\(%d," % spell)
        self.assertIn("BETWEEN 81000 AND 83419", sql)

    def test_the_contract_lists_exactly_the_auras_whose_numbers_a_record_cannot_state(self):
        text = CONTRACT.read_text(encoding="utf-8")
        section = text[text.index("## Values by aura"):]
        section = section[:section.index("\n## ", 5)] if "\n## " in section[5:] else section
        # the gem block only: the class buffs' rows (83340-83344, 83361) are test_class_buffs.py's
        listed = {int(i) for i in re.findall(r"^\| [^|]+\| (\d{5}) \|", section, re.M) if 83400 <= int(i) <= 83499}
        self.assertEqual(ADDON_LINES, listed)
        others = set(PLAN) - ADDON_LINES
        for spell in others:
            self.assertIn(str(spell), section, "the contract names the auras with no addon line")
        self.assertRegex(text, r"DCBUFFVAL")
        self.assertRegex(text, r"(?i)total")


def build(header_text, name):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    files = {"combat/dc_buff_values_math.h": header_text}
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
    work = Path(tempfile.mkdtemp(prefix="buffvalues-%s-" % name, dir=str(SCRATCH)))
    return work, binary


def drive(lines, header_text=None, name="real"):
    work, binary = build(header_text or MATH.read_text(encoding="utf-8"), name)
    try:
        (work / "cases.txt").write_text("\n".join(lines) + "\n")
        done = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if done.returncode:
        raise AssertionError(done.stderr)
    return done.stdout.splitlines()


def fmt(value):
    text = ("%.2f" % value).rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


class Model:
    """The contract, written again: the addon is told a value at once the first time and then at most once an interval,
    the latest value always, never one it already has, and told once when the aura is gone."""

    def __init__(self):
        self.auras = {}

    def set(self, aura, values, now, interval):
        entry = self.auras.setdefault(aura, {"sent": None, "at": 0, "held": None})
        spelled = tuple(fmt(v) for v in values)
        if entry["sent"] == spelled:
            entry["held"] = None
            return None
        if entry["sent"] is None or now - entry["at"] >= interval:
            entry.update(sent=spelled, at=now, held=None)
            return "|".join(("V", str(aura)) + spelled)
        entry["held"] = spelled
        return None

    def clear(self, aura):
        entry = self.auras.pop(aura, None)
        return "G|%d" % aura if entry and entry["sent"] is not None else None

    def flush(self, now, interval):
        out = []
        for aura in sorted(self.auras):
            entry = self.auras[aura]
            if entry["held"] is not None and now - entry["at"] >= interval:
                entry.update(sent=entry["held"], at=now, held=None)
                out.append("|".join(("V", str(aura)) + entry["sent"]))
        return ";".join(out) or None


def script(seed, steps=400):
    """A random run of set/clear/flush over three auras and a clock, as harness lines and the model's answers."""
    rng, model, lines, want = random.Random(seed), Model(), [], []
    now = 0
    for _ in range(steps):
        now += rng.choice([0, 1, 50, 100, 249, 250, 251, 600])
        interval = rng.choice([0, 250, 250, 250, 1000])
        aura = rng.choice([83411, 83415, 83419])
        pick = rng.random()
        if pick < 0.6:
            values = [rng.choice([0, 1, 6.12, 6.124, 6.126, 11.1, 1500, 123456.789]) for _ in range(rng.choice([1, 1, 2]))]
            lines.append("set %d %d %d %s" % (aura, now, interval, " ".join(repr(v) for v in values)))
            want.append(model.set(aura, values, now, interval) or "-")
        elif pick < 0.75:
            lines.append("clear %d" % aura)
            want.append(model.clear(aura) or "-")
        else:
            lines.append("flush %d %d" % (now, interval))
            want.append(model.flush(now, interval) or "-")
    return lines, want


class Throttle(unittest.TestCase):
    NUMBERS = [(6.12, "6.12"), (1500, "1500"), (0, "0"), (0.004, "0"), (11.1, "11.1"), (8.88, "8.88"), (99.999, "100"),
               (-0.001, "0"), (123456.789, "123456.79"), (25, "25"), (0.5, "0.5")]

    def test_a_value_is_spelled_as_the_contract_says(self):
        got = drive(["number %r" % value for value, _ in self.NUMBERS])
        self.assertEqual([text for _, text in self.NUMBERS], got)

    def test_a_run_of_sets_clears_and_flushes_is_the_contracts(self):
        for seed in range(8):
            lines, want = script(seed)
            self.assertEqual(want, drive(lines), "seed %d" % seed)

    def test_the_cases_the_contract_names(self):
        got = drive([
            "set 83411 1000 250 6.12",     # the first record goes at once
            "set 83411 1100 250 7.14",     # inside the interval: held
            "set 83411 1200 250 8.16",     # the latest wins
            "flush 1249 250",              # not yet
            "flush 1250 250",              # the interval has passed: the latest, 8.16
            "set 83411 1300 250 8.16",     # the addon has it: nothing
            "set 83411 1300 250 8.160001", # the same to two decimals: nothing
            "clear 83411",                 # told of it, so told it is gone
            "clear 83411",                 # and once
            "set 83415 2000 250 5",
            "set 83415 2010 250 6",        # held
            "set 83415 2020 250 5",        # back to what the addon has: nothing is owed
            "flush 3000 250",
            "set 83419 2000 250 100",
            "clear 83419",
            "set 83419 2001 250 100",      # a new aura after a G is the first record again: at once
        ])
        self.assertEqual(["V|83411|6.12", "-", "-", "-", "V|83411|8.16", "-", "-", "G|83411", "-",
                          "V|83415|5", "-", "-", "-", "V|83419|100", "G|83419", "V|83419|100"], got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "interval_is_exclusive": ("static_cast<std::int32_t>(intervalMs);\n        }", "static_cast<std::int32_t>(intervalMs) + 1;\n        }"),
            "a_value_the_addon_has_is_sent_again": ("if (entry.sent && *entry.sent == spelled)", "if (false)"),
            "a_gone_aura_is_remembered": ("if (entries_.erase(aura) == 0)", "if (entries_.count(aura) == 0)"),
            "a_gone_aura_is_told_though_unknown": ("if (entries_.erase(aura) == 0)\n                return std::nullopt;",
                                                   "entries_.erase(aura);"),
            "the_oldest_held_value_wins": ("entry.held = Held{values, spelled};", "if (!entry.held) entry.held = Held{values, spelled};"),
            "a_flush_does_not_start_the_interval": ("entry.sentAtMs = nowMs;\n                    out.push_back", "out.push_back"),
            "trailing_zeros_stay": ("while (!out.empty() && out.back() == '0')\n            out.pop_back();", ""),
            "a_set_that_goes_does_not_drop_the_held_value": ("entry.sent = spelled;\n                entry.sentAtMs = nowMs;\n                entry.held.reset();",
                                                            "entry.sent = spelled;\n                entry.sentAtMs = nowMs;"),
        }
        lines = []
        for seed in range(8):
            lines += script(seed)[0]
        # the eight scripts share one channel here, so the model must too
        model_want = []
        model = Model()
        for line in lines:
            parts = line.split()
            if parts[0] == "set":
                model_want.append(model.set(int(parts[1]), [float(x) for x in parts[4:]], int(parts[2]), int(parts[3])) or "-")
            elif parts[0] == "clear":
                model_want.append(model.clear(int(parts[1])) or "-")
            else:
                model_want.append(model.flush(int(parts[1]), int(parts[2])) or "-")
        self.assertEqual(model_want, drive(lines), "the real header and the model disagree on the long run")
        for name, (old, new) in mutants.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies to the header" % name)
            self.assertNotEqual(model_want, drive(lines, real.replace(old, new), name), "mutant %s passed" % name)


class Source(unittest.TestCase):
    """The gem code shows each buff where its state changes and takes it off where the state ends."""

    @classmethod
    def setUpClass(cls):
        cls.text = GEM_POWERS.read_text(encoding="utf-8")

    def body(self, signature, end):
        start = self.text.index(signature)
        return self.text[start:self.text.index(end, start)]

    def test_every_gem_with_a_buff_shows_it_where_its_stacks_change(self):
        self.assertIn("ShowGogok(player, powers, gogokStacks, powers.gogok.seconds)", self.body("void Hit(Player* player, Unit* target", "void Critical("))
        self.assertIn("ShowInvigorating(player, powers, invigoratingStacks, powers.invigorating.seconds)",
                      self.body("void Hit(Player* player, Unit* target", "void Critical("))
        self.assertIn("ShowTaeguk(player, powers, count, powers.taeguk.seconds)", self.body("void ChannelSpent(", "double TargetFactor("))
        self.assertIn("ShowBuff(killer, GemPower::Powerful, false, 1, powerfulSeconds)", self.text)
        self.assertIn("ShowBuff(player, GemPower::Pain, false, std::min(bleeding, 255u), 0)", self.body("void Upkeep(", "} // namespace\n\n    void Refresh("))
        self.assertIn("ShowBuff(player, GemPower::Esoteric, false,", self.body("void Sync(", "void SetControlImmunity("))

    def test_moratoriums_debt_follows_the_pool_and_ends_with_it(self):
        self.assertIn("ShowDebt(player, debt)", self.body("void Incoming(", "double ChillBonus("))
        pay = self.body("static void PayStagger(", "static void LapseGogok(")
        self.assertIn("ShowDebt(player, died ? 0 : debt)", pay)
        self.assertIn("ShowDebt(killer, 0)", self.text)

    def test_the_wreath_and_the_shield_publish_their_values_and_end_them(self):
        self.assertIn("BuffValues::Set(player, ShellOf(GemPower::Wreath), {powers.wreathPct, powers.wreathMovePct})", self.text)
        self.assertIn("BuffValues::Clear(owner->ToPlayer(), GetId())", self.text)
        self.assertIn("BuffValues::Set(player, shell, {double(effect->GetAmount())})", self.body("void PutShield(", "void Hurt("))
        upkeep = self.body("void Upkeep(", "} // namespace\n\n    void Refresh(")
        self.assertIn("BuffValues::Clear(player, shell)", upkeep)

    def test_a_lapsed_stack_takes_its_buff_off(self):
        lapse = self.body("static void LapseGogok(", "// Bane of the Powerful.")
        for gem in ("Gogok", "Taeguk", "Invigorating"):
            self.assertIn("ShowBuff(player, GemPower::%s, false, 0, 0)" % gem, lapse)

    def test_refresh_settles_the_buffs_of_a_changed_gem(self):
        refresh = self.body("void Refresh(Player* player, Item* changed", "std::vector<LegendaryGemItem::Socketed> Active(")
        for call in ("ShowGogok(player, powers,", "ShowTaeguk(player, powers,", "ShowInvigorating(player, powers,",
                     "ShowBuff(player, GemPower::Powerful", "ShowBuff(player, GemPower::Pain"):
            self.assertIn(call, refresh)

    def test_the_addon_line_is_the_total_the_sheet_and_the_hit_use(self):
        # the Dodge, the damage and the healing shown are the functions combat itself calls
        self.assertIn("GemPower::DodgePct(powers, stacks)", self.text)
        self.assertIn("GemPower::AdditivePct(powers, stacks)", self.text)
        self.assertIn("GemPower::HealingPct(powers, stacks)", self.text)
        math = (SRC / "combat/dc_gem_power_math.h").read_text(encoding="utf-8")
        self.assertIn("return 1.0 + HealingPct(powers, invigoratingStacks) / 100.0;", math)

    def test_the_wire_is_registered_and_throttled_by_a_combat_row(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        self.assertIn("BuffValues::RegisterScripts();", combat)
        wire = (SRC / "combat/dc_buff_values.cpp").read_text(encoding="utf-8")
        self.assertIn('Tunables::Get("combat", "buff_values_push_ms")', wire)
        self.assertIn('Prefix = "DCBUFFVAL"', wire)
        rows = {r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}
        self.assertIn("buff_values_push_ms", rows)
        self.assertIn("PLACEHOLDER", rows["buff_values_push_ms"]["notes"])


if __name__ == "__main__":
    unittest.main()

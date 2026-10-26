"""diablocraft-c81ak: one hover of Taeguk's buff reads the damage and, at rank 25, the Armor together.

The buff has two halves that the player reads as one tooltip: the record's own text (Spell.dbc, `$s1` shown times the
stacks by the client) and the addon's line under it (dc_buff_values.lua, from the server's DCBUFFVAL record). This test
renders the hover from both halves, each made by the production code:
  * the server half: dc_gem_power_math.h (Resolve, AdditivePct), dc_buff_values_math.h (the record's spelling) and
    dc_spell_shells.h (which of the two records the buff is shown as) are compiled and driven with the generated number
    row (tests/taeguk_hover/harness.cpp);
  * the record half: the generated spell_shells.sql row of that record, `$s1` read as base points + die sides and
    multiplied by the stack count (the 3.3.5 client's aura tooltip scale; the xumo sheet's Frenzy check);
  * the addon half: dc_buff_values.lua under the strict widget mock (scripts/tests/ui/taeguk_hover_lines.lua).
Every expected number is d3planner's own (2% + 0.04% per rank damage a stack; "Gain 2% increased Armor for every
stack"), never the sheet or the code under test. Rank 24 reads the damage alone, rank 25 the damage and the Armor.
Mutants of each half fail the same driver.
What this does NOT cover: the client's own drawing of the record text and the stack scale (the designer's check on dev,
docs/test-diablocraft-c81ak.md), the throttle (test_gem_buffs.py) and when the stacks change (dc_gem_powers.cpp).
"""
import re
import shutil
import subprocess
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
HARNESS = MODULE / "tests/taeguk_hover/harness.cpp"
DRIVER = MODULE / "scripts/tests/ui/taeguk_hover_lines.lua"
ADDON = MODULE / "lua/aio/dc_buff_values.lua"
SHELLS_SQL = MODULE / "data/generated/spell_shells.sql"
GEM_POWERS = SRC / "combat/dc_gem_powers.cpp"
SCRATCH = numbers.SCRATCH
HEADERS = ("combat/dc_gem_power_math.h", "combat/dc_buff_values_math.h", "combat/dc_spell_shells.h",
           "common/dc_legendary_gem.h", "items/dc_legendary_gem_item.h")
GEM = "Taeguk"
DAMAGE_RECORD, ARMOR_RECORD = 83413, 83414  # below rank 25, at rank 25 (contract: Values by aura)


def number(value):
    """The addon line's number as the contract spells it: at most two decimals, trailing zeros dropped."""
    text = ("%.2f" % value).rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def build(headers):
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="taeguk-hover-", dir=str(SCRATCH)))
    for rel in HEADERS:
        target = work / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(headers.get(rel) or (SRC / rel).read_text(encoding="utf-8"), encoding="utf-8")
    binary = work / "harness"
    built = subprocess.run([compiler, "-std=c++17", "-O0", "-I", str(work), str(HARNESS), "-o", str(binary)],
                           capture_output=True, text=True)
    if built.returncode:
        shutil.rmtree(work, ignore_errors=True)
        raise AssertionError("harness did not compile:\n" + built.stderr[-3000:])
    return work, binary


class Hover(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("lua"):
            raise unittest.SkipTest("no lua")
        cls.row = groupc.row_line("Unique_Gem_015_x1", groupc.rows()["Unique_Gem_015_x1"])
        cls.d3p = numbers.planner()[GEM]
        texts = groupc.planner_texts()[GEM]
        cls.armor_per_stack = [float(n) for n in re.findall(r"(\d+(?:\.\d+)?)%", texts[1])][0]
        cls.max_stacks = int(re.search(r"(\d+) times", texts[0]).group(1))
        cls.names, cls.spells = records.parse(SHELLS_SQL.read_text(encoding="utf-8"), every_class=True)
        cls.real_work, cls.real_binary = build({})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "real_work", ""), ignore_errors=True)

    # ---- the three halves -------------------------------------------------------------------------------------

    def server(self, cases, headers=None):
        """[(rank, stacks)] -> [(record id, Armor per stack, 'V|id|total')] from the compiled production headers."""
        work, binary = build(headers) if headers else (self.real_work, self.real_binary)
        try:
            lines = [self.row] + ["hover Unique_Gem_015_x1 %d %d" % case for case in cases]
            (work / "cases.txt").write_text("\n".join(lines) + "\n")
            done = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
        finally:
            if headers:
                shutil.rmtree(work, ignore_errors=True)
        self.assertEqual(0, done.returncode, done.stderr)
        out = []
        for line in done.stdout.splitlines():
            aura, armor, record = line.split(" ", 2)
            out.append((int(aura), float(armor), record))
        return out

    def record_text(self, spell, stacks, text=None):
        """The record's tooltip as the client draws it: `$s1` is the base points + die sides, times the stack count."""
        field = lambda column: self.spells[spell][self.names.index(column)]
        text = text or records.unquote(field("AuraDescription_Lang_enUS"))
        shown = min(stacks, int(field("CumulativeAura")))
        first = (int(field("EffectBasePoints_1")) + int(field("EffectDieSides_1"))) * shown
        return re.sub(r"\$s1", number(first), text)

    def addon_lines(self, aura, record, lua=None):
        env = dict(__import__("os").environ)
        if lua:
            env["DC_BUFF_LUA"] = str(lua)
        done = subprocess.run(["lua", str(DRIVER.relative_to(REPO)), str(aura), record], cwd=str(REPO), env=env,
                              capture_output=True, text=True)
        self.assertEqual(0, done.returncode, done.stderr)
        return done.stdout.splitlines()

    def hover(self, rank, stacks, headers=None, lua=None, text=None):
        """The whole tooltip of the buff at this rank and stack count: the record's text, then the addon's lines."""
        (aura, _, record), = self.server([(rank, stacks)], headers)
        shown = self.record_text(aura, stacks, text)
        return aura, [shown] + self.addon_lines(aura, record, lua)

    # ---- what the player must read ----------------------------------------------------------------------------

    def wanted(self, rank, stacks):
        """d3planner's own: per-stack damage 2% + 0.04% x rank (the gem's text), Armor 2% a stack from rank 25."""
        damage = (self.d3p[1][0] + self.d3p[2][0] * rank) * stacks
        if rank < 25:
            return DAMAGE_RECORD, ["Increases the damage you deal.", "+%s%% damage" % number(damage)]
        armor = self.armor_per_stack * stacks
        return ARMOR_RECORD, ["Increases the damage you deal and increases your Armor by %s%%." % number(armor),
                              "+%s%% damage" % number(damage)]

    def test_rank_24_reads_the_damage_alone_and_rank_25_the_damage_and_the_armor(self):
        full = self.max_stacks
        self.assertEqual((DAMAGE_RECORD, ["Increases the damage you deal.", "+29.6% damage"]), self.hover(24, full))
        self.assertEqual((ARMOR_RECORD, ["Increases the damage you deal and increases your Armor by 20%.",
                                         "+30% damage"]), self.hover(25, full))
        text = " ".join(self.hover(24, full)[1])
        self.assertNotRegex(text, r"(?i)armor", "the Armor comes at rank 25")

    def test_the_hover_follows_the_rank_and_the_stacks(self):
        for rank in (1, 24, 25, 26, 50, 75, 100):
            for stacks in (1, 4, self.max_stacks):
                self.assertEqual(self.wanted(rank, stacks), self.hover(rank, stacks), (rank, stacks))

    def test_the_two_records_are_the_two_halves_of_the_contract(self):
        contract = (REPO / "docs/contracts/buff-values-messages.md").read_text(encoding="utf-8")
        for spell in (DAMAGE_RECORD, ARMOR_RECORD):
            self.assertRegex(contract, r"\| %d \| 1: damage, %% total now" % spell)

    def test_the_server_shows_the_record_the_rank_picks_with_the_damage_total_as_its_one_value(self):
        source = GEM_POWERS.read_text(encoding="utf-8")
        call = re.search(r"void ShowTaeguk\(.*?\n        \}", source, re.S).group(0)
        self.assertRegex(call, r"ShowBuff\(player, GemPower::Taeguk, powers\.taegukArmorPctPerStack > 0, stacks, seconds,\s*"
                               r"\{GemPower::AdditivePct\(powers, stacks\)\}\)")

    # ---- mutants: each half, broken, fails the same checks ----------------------------------------------------

    SCENES = ((24, 10), (25, 10), (25, 3))

    def failing(self, **kwargs):
        """True when the broken half makes a hover differ from what the player must read (or the driver refuse)."""
        try:
            return any(self.hover(rank, stacks, **kwargs) != self.wanted(rank, stacks) for rank, stacks in self.SCENES)
        except AssertionError:
            return True

    def test_mutants_fail(self):
        math = (SRC / "combat/dc_gem_power_math.h").read_text(encoding="utf-8")
        addon = ADDON.read_text(encoding="utf-8")
        work = Path(tempfile.mkdtemp(prefix="taeguk-hover-lua-", dir=str(SCRATCH)))
        try:
            def lua(old, new):
                self.assertIn(old, addon)
                path = work / "dc_buff_values.lua"
                path.write_text(addon.replace(old, new), encoding="utf-8")
                return path

            def header(old, new):
                self.assertIn(old, math)
                return {"combat/dc_gem_power_math.h": math.replace(old, new)}

            mutants = {
                "damage_total_not_times_stacks": dict(headers=header("return powers.taeguk.perStack * taegukStacks;",
                                                                     "return powers.taeguk.perStack;")),
                "armor_record_never_chosen": dict(headers=header("powers.taegukArmorPctPerStack = Rank25Number(*row, 0);",
                                                                 "powers.taegukArmorPctPerStack = 0;")),
                "rank25_damage_line_missing": dict(lua=lua('[83414]={"+%s%% damage"},', "")),
                "rank24_damage_line_missing": dict(lua=lua('[83413]={"+%s%% damage"},', "")),
                "damage_line_says_armor": dict(lua=lua('[83414]={"+%s%% damage"},', '[83414]={"+%s%% Armor"},')),
                "record_names_no_armor": dict(text="Increases the damage you deal."),
            }
            for name, kwargs in mutants.items():
                with self.subTest(mutant=name):
                    self.assertTrue(self.failing(**kwargs), "the mutant %s passed" % name)
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

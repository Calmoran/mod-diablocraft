"""Ricochet hits the enemy you threw at and three more, proved on the core's own chain-target code.

The 2026-09-20 ruling "Spell rewrite step 6 Ricochet and frozen-test contract"
settles a question D3's sheet cannot settle on its own. `barbarian_skill_values.csv`
says Weapon Throw / Ricochet has `target_count = 3`, and its source note says
that number "excludes the primary target - three MORE enemies". AzerothCore's
`EffectChainTarget` column does not mean that. The ruling therefore says the
generated record carries `EffectChainTargets_1 = 4`, "because the core's
ChainTarget includes the primary", and that the regression has to prove, among
other things, "native primary plus three".

That last clause is a claim about the core's arithmetic, so this suite makes
the core do the arithmetic. Nothing here models it:

    uint32 maxTargets = m_spellInfo->Effects[effIndex].ChainTarget;   Spell.cpp:1879
    if (maxTargets > 1)                                               Spell.cpp:1883
        SearchChainTargets(targets, maxTargets - 1, ...)              Spell.cpp:1892
        // Chain primary target is added earlier                      Spell.cpp:1895

and the last comment is only true because of the two call sites, which are
extracted whole for exactly that reason: `SelectImplicitTargetObjectTargets`
adds the primary at Spell.cpp:1866 and only then chains at :1870, and
`SelectImplicitNearbyTargets` adds it at :1192 and chains at :1229. A suite
that took the "+1" on trust would be quoting the comment; this one runs the
code that makes the comment true, on both routes.

`tests/chain_targets/chain_shim.h` compiles those four functions, the record
reads that feed them (`ChainTarget = spellEntry->EffectChainTarget[effIndex];`
at SpellInfo.cpp:346 above all), `WorldObject::GetDistanceOrder` and
`Player::ApplySpellMod`, all extracted from the pin at test time.
`tests/chain_targets/chain_harness.cpp` hands them the generated records and a
candidate list. The shim's header lists every stub and says why each one
cannot move a count. The last tests mutate the core's own lines - the `- 1`,
the `> 1` guard and `tempTargets.remove(target)` - and show the answers move
with them, so the evidence provably comes from the core's code and not from
the harness.

Four things are test-owned rather than extracted and are named here so nobody
has to go looking: `struct SpellEntry` and the shell of `class SpellInfo`,
which hold the generated columns the extracted constructor lines read;
`Spell::SearchAreaTargets`, which decides WHICH units are nearby and is
replaced by the driver's candidate list, because the selection is not under
test and the COUNT THAT SURVIVES is; and `Spell::AddUnitTarget`, which here
only appends - it does not deduplicate as the real one does, so a lost
`tempTargets.remove(target)` shows up rather than being swallowed.

    python mod-diablocraft/scripts/tests/combat/test_chain_targets.py
"""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import tempfile
import unittest
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE = REPO_ROOT / "mod-diablocraft"
HARNESS = MODULE / "tests" / "chain_targets"
GENERATED = MODULE / "data" / "generated"
SHEETS = MODULE / "data" / "d3"
CORE = REPO_ROOT / "azerothcore-wotlk"
# Scratch belongs in the build tree (AGENTS.md), not the system temp; the
# fallback is for a checkout that has never been configured.
SCRATCH = CORE / "build" / "_agent-scratch" / "chain_targets"
PIN = (REPO_ROOT / "core-commit.txt").read_text(encoding="utf-8").split()[0]
PATCH = REPO_ROOT / "core-patches" / "0014-spell-modifier-d3-arithmetic.patch"

# The record the ruling names, and the sheet row it was derived from.
RICOCHET = 81029
RICOCHET_SKILL = "Weapon Throw"
RICOCHET_RUNE = "Ricochet"
RICOCHET_NAME = "Weapon Throw - Ricochet"

# The generated spell_dbc column the core reads as SpellInfo::DmgClass. The
# DBC field is called DmgClass; the SQL column azerothcore ships is called
# DefenseType, and the generated INSERT uses the SQL name.
DMG_CLASS_COLUMN = "DefenseType"

# Everything in a case sits on the x axis one yard apart, so that every hop is
# comfortably inside the 7.5-yard ranged jump radius SearchChainTargets picks
# for DmgClass 3 and the ordering GetDistanceOrder computes is unambiguous.
PRIMARY_X = 0.0
CANDIDATE_SPACING = 1.0


def generated_records():
    """{spell id: {column: value}} straight out of the generated spell SQL.

    What the core will be handed, not what a sheet says: the migration carries
    these rows into `spell_dbc` and AzerothCore layers them over the client's
    Spell.dbc at startup.
    """
    text = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    names = [name.strip(" `") for name in
             re.search(r"INSERT INTO `spell_dbc` \(([^)]*)\) VALUES", text)[1].split(",")]
    out = {}
    for line in text.splitlines():
        line = line.strip().rstrip(",;")
        if not line.startswith("(") or not line.endswith(")"):
            continue
        cells, current, quoted = [], "", False
        index = 1
        while index < len(line) - 1:
            char = line[index]
            if quoted:
                if char == "'" and line[index + 1:index + 2] == "'":
                    current += "'"
                    index += 1
                elif char == "'":
                    quoted = False
                else:
                    current += char
            elif char == "'":
                quoted = True
            elif char == ",":
                cells.append(current)
                current = ""
            else:
                current += char
            index += 1
        cells.append(current)
        if len(cells) == len(names):
            out[int(cells[0])] = dict(zip(names, cells))
    return out


def generated_jump_distances():
    """{spell id: jump distance} out of the generated spell_jump_distance rows.

    Not a DBC column: `SpellInfo::JumpDistance` is filled by SpellMgr from this
    world table, and it is what `SearchChainTargets` uses for `jumpRadius`
    instead of the 7.5/10/12.5 default its DmgClass switch would pick. The
    harness therefore has to be handed the same number the migration carries,
    or the chain would be tested at a reach the server does not use.
    """
    text = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    out = {}
    for line in text.splitlines():
        if not line.startswith("INSERT INTO spell_jump_distance"):
            continue
        for spell, distance in re.findall(r"\((\d+),([0-9.]+)\)", line):
            out[int(spell)] = float(distance)
    return out


def sheet_value(sheet, skill, rune, token):
    """One verified D3 number, by skill, rune and token. Read-only."""
    with (SHEETS / sheet).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["skill"] == skill and row["rune"] == rune and row["token"] == token:
                return row
    raise AssertionError("%s has no %s row for %s / %s" % (sheet, token, skill, rune))


# --- the core's own code, taken out of the pin -----------------------------

def at_pin(path):
    """A core file exactly as the pin has it. The core is never written to."""
    shown = subprocess.run(["git", "-C", str(CORE), "show", "%s:%s" % (PIN, path)],
                           capture_output=True, text=True)
    if shown.returncode:
        raise AssertionError("the core pin has no %s:\n%s" % (path, shown.stderr))
    return shown.stdout


def block(text, opener, what):
    """The text from `opener` through the brace that closes it."""
    start = text.find(opener)
    if start < 0:
        raise AssertionError("the core pin no longer has %s" % what)
    depth = 0
    for position in range(text.index("{", start), len(text)):
        if text[position] == "{":
            depth += 1
        elif text[position] == "}":
            depth -= 1
            if depth == 0:
                return text[start:text.find("\n", position) + 1]
    raise AssertionError("%s is not closed" % what)


def lines_matching(text, pattern, what, count=1):
    """The whole lines a pattern matches, verbatim and in file order."""
    found = [line for line in text.splitlines() if re.search(pattern, line)]
    if len(found) < count:
        raise AssertionError("the core pin no longer has %s (%d of %d lines)"
                             % (what, len(found), count))
    return "\n".join(found[:count]) + "\n"


def player_cpp(work):
    """Player.cpp at the pin with core-patches/0014 applied.

    The patch is applied to a copy in a temporary tree; the core checkout is
    read-only here, as it is everywhere. Only ApplySpellMod is taken from it,
    and only one test drives it, but that test has to run the arithmetic the
    running server runs and not the stock one.
    """
    text = at_pin("src/server/game/Entities/Player/Player.cpp")
    target = work / "src/server/game/Entities/Player"
    target.mkdir(parents=True, exist_ok=True)
    (target / "Player.cpp").write_text(text, encoding="utf-8")
    applied = subprocess.run(["git", "apply", "--unsafe-paths", "--directory", ".", str(PATCH)],
                             cwd=str(work), capture_output=True, text=True)
    if applied.returncode:
        raise AssertionError("core-patches/0014 does not apply at the pin:\n" + applied.stderr)
    return (target / "Player.cpp").read_text(encoding="utf-8")


# The four lines the ruling rests on. They are asserted to still be there
# before anything is compiled, so a core bump that moves them fails loudly
# here rather than quietly changing what this suite proves.
CHAIN_ARITHMETIC = [
    "    uint32 maxTargets = m_spellInfo->Effects[effIndex].ChainTarget;",
    "    if (maxTargets > 1)",
    "        SearchChainTargets(targets, maxTargets - 1, target, targetType.GetObjectType()",
    "        // Chain primary target is added earlier",
]
# ...and the ordering at the two call sites, which is what makes the comment
# above true. Each pair is (the line that adds the primary, the line that
# chains), and the first has to come before the second.
CALL_SITE_ORDER = [
    ("            AddUnitTarget(unit, effMask, true, false);",
     "    SelectImplicitChainTargets(effIndex, targetType, target, effMask);"),
    ("            AddUnitTarget(unit, 1 << effIndex, true, false);",
     "        SelectImplicitChainTargets(effIndex, targetType, target, 1 << effIndex);"),
]


def extract(into, mutate=None):
    """Write every piece of the core the shim includes, out of the pin.

    `mutate` is {file: (before, after)} and is how the evidence tests show the
    proof rests on the extracted code: change a line of the core here and the
    count moves.
    """
    mutate = mutate or {}
    into.mkdir(parents=True, exist_ok=True)

    def put(name, text):
        if name in mutate:
            before, after = mutate[name]
            if before not in text:
                raise AssertionError("the mutation target %r is not in %s" % (before, name))
            text = text.replace(before, after)
        (into / name).write_text(text, encoding="utf-8")

    shared = at_pin("src/server/shared/SharedDefines.h")
    spell_info_h = at_pin("src/server/game/Spells/SpellInfo.h")
    put("chain_enums.inc",
        lines_matching(at_pin("src/server/shared/DataStores/DBCStructure.h"),
                       r"^#define MAX_SPELL_EFFECTS ", "MAX_SPELL_EFFECTS")
        + "\n" + block(shared, "enum SpellEffIndex : uint8", "SpellEffIndex")
        + "\n" + block(shared, "enum SpellAttr2 : uint32", "SpellAttr2")
        + "\n" + block(shared, "enum SpellAttr4 : uint32", "SpellAttr4")
        + "\n" + block(shared, "enum SpellDmgClass", "SpellDmgClass")
        + "\n" + block(shared, "enum Targets\n{", "the Targets enum")
        + "\n" + block(spell_info_h, "enum SpellTargetSelectionCategories",
                       "SpellTargetSelectionCategories")
        + "\n" + block(spell_info_h, "enum SpellTargetReferenceTypes", "SpellTargetReferenceTypes")
        + "\n" + block(spell_info_h, "enum SpellTargetObjectTypes", "SpellTargetObjectTypes")
        + "\n" + block(spell_info_h, "enum SpellTargetCheckTypes", "SpellTargetCheckTypes"))

    spell_h = at_pin("src/server/game/Spells/Spell.h")
    put("search_reason.inc",
        block(spell_h, "enum class WorldObjectSpellAreaTargetSearchReason",
              "WorldObjectSpellAreaTargetSearchReason"))
    put("model_ignore_flags.inc",
        block(at_pin("src/common/Collision/Models/ModelIgnoreFlags.h"),
              "enum class ModelIgnoreFlags", "ModelIgnoreFlags"))

    put("position_getters.inc",
        lines_matching(at_pin("src/server/game/Entities/Object/Position.h"),
                       r"^    \[\[nodiscard\]\] float GetPosition[XYZ]\(\) const \{ return m_position[XYZ]; \}",
                       "the three position getters", count=3))

    # The ordering the chain walks by. It reads nothing but the three getters
    # above, so it comes out whole rather than being modelled - without it,
    # the early-break test and the never-twice test would prove nothing.
    put("distance_order.inc",
        block(at_pin("src/server/game/Entities/Object/Object.cpp"),
              "bool WorldObject::GetDistanceOrder(", "WorldObject::GetDistanceOrder"))

    put("spell_info_attribute.inc",
        lines_matching(spell_info_h, r"HasAttribute\(SpellAttr2 attribute\)", "HasAttribute(SpellAttr2)")
        + lines_matching(spell_info_h, r"HasAttribute\(SpellAttr4 attribute\)", "HasAttribute(SpellAttr4)"))

    spell_info = at_pin("src/server/game/Spells/SpellInfo.cpp")
    constructor = block(spell_info, "SpellInfo::SpellInfo(SpellEntry const* spellEntry)",
                        "SpellInfo's constructor")
    fields = ["Id", "Attributes", "AttributesEx2", "AttributesEx4", "RequiresSpellFocus", "DmgClass"]
    put("spell_info_fields.inc",
        "".join(lines_matching(constructor, r"^    %s = spellEntry->" % field, field)
                for field in fields))
    # The one line the whole suite exists for: the generated
    # EffectChainTargets_1 column becoming the number the extracted code reads.
    effect_constructor = block(spell_info,
                               "SpellEffectInfo::SpellEffectInfo(SpellEntry const* spellEntry",
                               "SpellEffectInfo's constructor")
    put("effect_chain_target.inc",
        lines_matching(effect_constructor, r"^    ChainTarget = spellEntry->EffectChainTarget\[effIndex\];",
                       "the ChainTarget assignment"))

    spell_mgr = at_pin("src/server/game/Spells/SpellMgr.h")
    put("spell_mgr_lookup.inc",
        lines_matching(spell_mgr, r"^typedef std::vector<SpellInfo\*> SpellInfoMap;", "SpellInfoMap")
        + "\nclass SpellMgr\n{\npublic:\n"
        + lines_matching(spell_mgr, r"GetSpellInfo\(uint32 spellId\) const \{ return spellId <",
                         "SpellMgr::GetSpellInfo")
        + lines_matching(spell_mgr, r"GetSpellInfoStoreSize\(\) const \{ return mSpellInfoMap\.size\(\); \}",
                         "SpellMgr::GetSpellInfoStoreSize")
        + lines_matching(spell_mgr, r"^    SpellInfoMap  *mSpellInfoMap;", "mSpellInfoMap")
        + "};\nstatic SpellMgr* const sSpellMgr = new SpellMgr();\n")

    player_h = at_pin("src/server/game/Entities/Player/Player.h")
    spell_defines = at_pin("src/server/game/Spells/SpellDefines.h")
    put("spell_mod_enums.inc",
        block(spell_defines, "enum SpellModOp", "SpellModOp")
        + "\n" + lines_matching(spell_defines, r"^#define MAX_SPELLMOD ", "MAX_SPELLMOD")
        + "\n" + block(player_h, "enum SpellModType", "SpellModType")
        + "\n" + block(player_h, "struct SpellModifier", "SpellModifier"))
    put("calculate_pct.inc",
        block(at_pin("src/common/Utilities/Util.h"),
              "template <class T, class U>\ninline T CalculatePct(", "CalculatePct"))

    player = player_cpp(into / "tree")
    put("apply_spell_mod.inc",
        block(player, "template <class T>\nvoid Player::ApplySpellMod(", "Player::ApplySpellMod"))

    # The four functions the answer comes out of, whole.
    spell = at_pin("src/server/game/Spells/Spell.cpp")
    for line in CHAIN_ARITHMETIC:
        if line not in spell:
            raise AssertionError("the core pin no longer has the chain line %r" % line)
    for adds_primary, chains in CALL_SITE_ORDER:
        if spell.find(adds_primary) < 0 or spell.find(chains) < 0:
            raise AssertionError("a chain call site no longer looks like %r / %r"
                                 % (adds_primary, chains))
    put("select_implicit_nearby.inc",
        block(spell, "void Spell::SelectImplicitNearbyTargets(",
              "Spell::SelectImplicitNearbyTargets"))
    put("select_implicit_target_object.inc",
        block(spell, "void Spell::SelectImplicitTargetObjectTargets(",
              "Spell::SelectImplicitTargetObjectTargets"))
    put("select_implicit_chain.inc",
        block(spell, "void Spell::SelectImplicitChainTargets(",
              "Spell::SelectImplicitChainTargets"))
    put("search_chain_targets.inc",
        block(spell, "void Spell::SearchChainTargets(", "Spell::SearchChainTargets"))


class ChainTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("c++") or shutil.which("g++")
        if not cls.compiler:
            raise unittest.SkipTest("no C++ compiler")
        if not (GENERATED / "spell_shells.sql").exists():
            raise unittest.SkipTest("generate_spells.py has not written the spell records")
        cls.records = generated_records()
        cls.jump = generated_jump_distances()
        if RICOCHET not in cls.records:
            raise unittest.SkipTest("the generated records do not contain spell %d" % RICOCHET)
        try:
            SCRATCH.mkdir(parents=True, exist_ok=True)
            cls.work = Path(tempfile.mkdtemp(prefix="run-", dir=str(SCRATCH)))
        except OSError:
            cls.work = Path(tempfile.mkdtemp(prefix="dc-chain-targets-"))
        cls.binaries = {}
        cls.records_file = cls.work / "records.tsv"
        cls.records_file.write_text(cls.records_tsv(), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)
        # ...and the suite's own scratch directory too, if this run was the
        # only thing in it. Scratch is not history (AGENTS.md).
        try:
            SCRATCH.rmdir()
        except OSError:
            pass

    @classmethod
    def records_tsv(cls):
        """Every generated record, plus one control per chain count 0 to 6.

        The controls are Ricochet's own record with nothing changed but
        `EffectChainTargets_1`, so a sweep over chain counts is a sweep over
        that one column and nothing else. Their ids sit above every generated
        one, and nothing else in the suite uses them.
        """
        lines = []
        for spell, row in sorted(cls.records.items()):
            lines.append("\t".join(str(cell) for cell in (
                spell, row["EffectChainTargets_1"], row["Attributes"], row["AttributesEx2"],
                row["AttributesEx4"], row[DMG_CLASS_COLUMN], row["RequiresSpellFocus"],
                cls.jump.get(spell, 0))))
        template = cls.records[RICOCHET]
        cls.controls = {}
        for count in range(0, 7):
            cls.controls[count] = max(cls.records) + 1 + count
            lines.append("\t".join(str(cell) for cell in (
                cls.controls[count], count, template["Attributes"], template["AttributesEx2"],
                template["AttributesEx4"], template[DMG_CLASS_COLUMN],
                template["RequiresSpellFocus"], cls.jump.get(RICOCHET, 0))))
        return "\n".join(lines) + "\n"

    def build(self, name="pinned", mutate=None):
        """Compile the harness against the core code extracted from the pin."""
        if name in self.binaries:
            return self.binaries[name]
        into = self.work / name
        extract(into, mutate)
        binary = into / "harness"
        binary = harness_env.build([HARNESS / "chain_harness.cpp"], flags=["-std=c++17", "-O0"], includes=[into, HARNESS])
        self.binaries[name] = binary
        return binary

    def drive(self, cases, name="pinned", mutate=None):
        """Run the harness over `cases`, returning one answer line per case."""
        binary = self.build(name, mutate)
        cases_file = self.work / ("cases-%s-%d.tsv" % (name, len(self.binaries)))
        cases_file.write_text(
            "\n".join("\t".join(str(cell) for cell in case) for case in cases) + "\n",
            encoding="utf-8")
        run = harness_env.run([str(binary), str(self.records_file), str(cases_file)],
                             capture_output=True, text=True)
        if run.returncode:
            raise AssertionError("the harness did not run:\n" + run.stderr[-4000:])
        answers = run.stdout.splitlines()
        self.assertEqual(len(answers), len(cases), "the harness answered a different count")
        return answers

    @staticmethod
    def candidates(count, blind=()):
        """`count` enemies on the x axis, one yard apart, the first at 1.0.

        A candidate whose index is in `blind` has no line of sight, so
        IsWithinLOSInMap answers false for it and the chain's search has to
        step over it - or run out and break.
        """
        return ["%.1f:%d" % ((index + 1) * CANDIDATE_SPACING, 0 if index in blind else 1)
                for index in range(count)]

    def cast(self, spell, count=6, route="object", jump_mod=0, blind=(), positions=None,
             name="pinned", mutate=None):
        """One cast. Returns (the tags hit, in order, the apply-multiplier mask).

        Tag 0 is the primary and 1..n are the candidates in the order they were
        handed to the chain search. A tag appearing twice means the same unit
        was added to the target list twice, which is what
        `tempTargets.remove(target)` is there to stop.
        """
        listed = (["%.1f:1" % x for x in positions] if positions is not None
                  else list(self.candidates(count, blind)))
        case = ["cast", spell, route, jump_mod, "%.1f" % PRIMARY_X] + listed
        answer = self.drive([case], name=name, mutate=mutate)[0]
        hits, _, mask = answer.partition("\t")
        return ([] if hits == "-" else [int(tag) for tag in hits.split(" ")]), int(mask)

    def chain_target(self, spell, name="pinned", mutate=None):
        """What `m_spellInfo->Effects[EFFECT_0].ChainTarget` holds for a record."""
        return int(self.drive([("chaintarget", spell)], name=name, mutate=mutate)[0])

    # --- (a) the ruling's case ---------------------------------------------

    def test_ricochet_hits_the_enemy_you_threw_at_and_exactly_three_more(self):
        """The ruling's whole claim, run rather than quoted.

        Three numbers have to line up. The sheet says 3 and says in its own
        source note that it excludes the primary. The generated record says 4,
        because the core's ChainTarget counts the primary. And the core, handed
        that record and six reachable enemies, puts exactly four units in the
        target list: the one the throw was aimed at plus three more. Nothing
        below is a literal - the 4 is read out of
        data/generated/spell_shells.sql and the 3 out of
        data/d3/barbarian_skill_values.csv.
        """
        record = self.records[RICOCHET]
        self.assertEqual(record["Name_Lang_enUS"], RICOCHET_NAME,
                         "spell %d is no longer Ricochet" % RICOCHET)
        field = int(record["EffectChainTargets_1"])
        sheet = sheet_value("barbarian_skill_values.csv", RICOCHET_SKILL, RICOCHET_RUNE, "target_count")
        additional = int(sheet["value"])

        self.assertEqual(additional, 3,
                         "the values sheet no longer says three additional enemies")
        self.assertIn("excludes the primary", sheet["source"],
                      "the sheet row no longer records that its count excludes the primary")
        self.assertEqual(field, additional + 1,
                         "the generated record says %d where the ruling wants sheet+1 = %d; "
                         "the core's ChainTarget counts the primary "
                         "(docs/decisions.md 2026-09-20, spell rewrite step 6)"
                         % (field, additional + 1))
        self.assertEqual(field, 4, "the ruling names 4 and the record says %d" % field)

        # ...and the core's own assignment is what turns that column into the
        # number SelectImplicitChainTargets reads.
        self.assertEqual(self.chain_target(RICOCHET), field,
                         "the record's column did not reach SpellInfo::Effects[0].ChainTarget")

        hits, _mask = self.cast(RICOCHET, count=6)
        self.assertEqual(len(hits), field,
                         "Ricochet hit %d units where the record asks for %d" % (len(hits), field))
        self.assertEqual(len(hits), additional + 1,
                         "Ricochet did not hit the primary plus the sheet's three")
        self.assertEqual(hits[0], 0, "the primary is not the first unit added")
        self.assertEqual(len(set(hits[1:])), additional,
                         "the chain did not add exactly %d further units" % additional)
        # The chain walks by distance, so with enemies a yard apart in a line
        # it takes the three nearest in order. A constant GetDistanceOrder
        # would not produce this.
        self.assertEqual(hits, [0, 1, 2, 3],
                         "the chain did not walk the three nearest enemies in order")

    def test_both_call_sites_add_the_primary_before_they_chain(self):
        """The "+1" is the call sites' doing, and there are two of them.

        `SelectImplicitChainTargets` never adds the primary. The comment at
        Spell.cpp:1895 says so - "Chain primary target is added earlier" - and
        earlier means Spell.cpp:1866 for an explicit target and Spell.cpp:1192
        for a nearby one. Both functions are extracted whole and both are
        driven here, so the four is the two lines' arithmetic and not an
        assumption about them. The primary is first in the list either way,
        which is what "added earlier" means in practice.
        """
        field = int(self.records[RICOCHET]["EffectChainTargets_1"])
        for route in ("object", "nearby"):
            hits, _mask = self.cast(RICOCHET, count=6, route=route)
            self.assertEqual(hits[0], 0, "the %s route did not add the primary first" % route)
            self.assertEqual(len(hits), field,
                             "the %s route hit %d where the record asks for %d"
                             % (route, len(hits), field))
            self.assertEqual(hits, [0, 1, 2, 3], "the %s route chained differently" % route)

    # --- (b) what happens when the chain runs out --------------------------

    def test_a_chain_that_runs_out_of_enemies_stops_where_it_is(self):
        """Two candidates for a chain that wants three: the total is three.

        `while (chainTargets)` gives up through `if (foundItr ==
        tempTargets.end()) break;`. Two roads reach that break and both are
        driven: an empty candidate list, and a full one where nothing has line
        of sight. A record asking for four never hits more than it can find,
        and it never hits fewer than it found.
        """
        field = int(self.records[RICOCHET]["EffectChainTargets_1"])
        for available in range(0, field):
            hits, _mask = self.cast(RICOCHET, count=available)
            self.assertEqual(len(hits), available + 1,
                             "with %d enemies in reach the chain did not stop at primary + %d"
                             % (available, available))
            self.assertEqual(hits, list(range(available + 1)))

        # The same break by the other road: six enemies, none of them visible.
        blind_all, _mask = self.cast(RICOCHET, count=6, blind=tuple(range(6)))
        self.assertEqual(blind_all, [0],
                         "the chain jumped to an enemy it had no line of sight to")
        # ...and with the two nearest blocked it steps over them rather than
        # stopping, which is what proves the break above is a real search
        # failing and not the loop simply not running.
        stepped, _mask = self.cast(RICOCHET, count=6, blind=(0, 1))
        self.assertEqual(stepped, [0, 3, 4, 5],
                         "the chain did not step over the enemies it cannot see")

    def test_the_chain_reaches_exactly_as_far_as_the_generated_jump_distance(self):
        """`spell_jump_distance` is a generated row, and the core really uses it.

        `SearchChainTargets` picks a jump radius from the record's DmgClass -
        7.5 yards for a ranged spell - and then overrides it with
        `m_spellInfo->JumpDistance` when that is above zero. JumpDistance is
        not a DBC column; it reaches the server from the `spell_jump_distance`
        world table, and the generator writes a row for Ricochet. That row is
        as much a part of "primary plus three" as the chain count is: with it
        the throw bounces across the pack, without it the same four-target
        record can only reach a bit over seven yards and quietly hits fewer
        enemies. So this places one enemy just inside the generated distance
        and one just outside, and checks the chain stops at the right yard.
        """
        reach = self.jump.get(RICOCHET)
        self.assertIsNotNone(reach, "the generator no longer writes Ricochet a jump distance")
        self.assertGreater(reach, 0)

        inside, _mask = self.cast(RICOCHET, positions=[reach - 1.0])
        self.assertEqual(inside, [0, 1],
                         "the chain did not reach an enemy inside its jump distance")
        outside, _mask = self.cast(RICOCHET, positions=[reach + 1.0])
        self.assertEqual(outside, [0],
                         "the chain jumped further than its generated jump distance")

        # And it is the generated row doing the work, not the DmgClass
        # default: an enemy beyond that default but inside the row is reached.
        ranged_default = 7.5
        self.assertGreater(reach, ranged_default,
                           "Ricochet's jump distance no longer exceeds the ranged default, "
                           "so this test can no longer tell the two apart")
        beyond_default, _mask = self.cast(RICOCHET, positions=[ranged_default + 1.0])
        self.assertEqual(beyond_default, [0, 1],
                         "the chain used the 7.5-yard ranged default instead of the "
                         "generated spell_jump_distance row")

    def test_the_primary_is_never_chained_to_twice(self):
        """`tempTargets.remove(target)` and what happens without it.

        The area search hands the chain every unit in range, and the primary is
        always one of them - it is zero yards from itself, so it is also the
        nearest. Spell.cpp:2193 removes it before the loop starts. This asserts
        the primary's tag appears exactly once in the final list, and then
        mutates that single line away: with it gone the primary is picked as
        the first jump, it lands in the list twice, and Ricochet reaches only
        two further enemies instead of three. The real AddUnitTarget would have
        merged the duplicate silently; the harness's does not, on purpose.
        """
        hits, _mask = self.cast(RICOCHET, count=6)
        self.assertEqual(Counter(hits)[0], 1, "the primary was added to the target list twice")
        self.assertEqual(len(set(hits)), len(hits), "a unit appears twice in the target list")

        doubled, _mask = self.cast(RICOCHET, count=6, name="mutated-no-remove", mutate={
            "search_chain_targets.inc": ("    tempTargets.remove(target);",
                                         "    ; // mutated: the primary is left in the pool")})
        self.assertEqual(Counter(doubled)[0], 2,
                         "removing tempTargets.remove(target) did not make the primary "
                         "a chain jump, so the never-twice proof is not coming from that line")
        self.assertEqual(doubled, [0, 0, 1, 2],
                         "the mutated chain did not spend a jump on the primary")

    # --- (c) the off-by-one, made visible in both directions ---------------

    def test_a_record_that_says_one_or_zero_never_chains_at_all(self):
        """ChainTarget 1 and ChainTarget 0 both hit exactly one unit.

        This is the direction the ruling's "+1" has to survive. A skill whose
        sheet says "no extra enemies" is a record carrying 1, not 0, and it
        must hit exactly the enemy it was aimed at - `if (maxTargets > 1)` is
        never entered, so `SearchChainTargets` is never called. A record
        carrying 0 does the same, and for the same reason. If the writer ever
        stopped adding the primary, a one-target skill would carry 0 here and
        nothing would change, which is exactly why both are asserted: the two
        together are what make the off-by-one visible rather than silent.
        """
        for count in (0, 1):
            hits, mask = self.cast(self.controls[count], count=6)
            self.assertEqual(hits, [0],
                             "a record carrying ChainTarget %d hit %d units" % (count, len(hits)))
            self.assertEqual(mask, 0,
                             "a record carrying ChainTarget %d entered the chain branch" % count)
        # And two is the first value that chains at all: one further enemy.
        hits, mask = self.cast(self.controls[2], count=6)
        self.assertEqual(hits, [0, 1], "ChainTarget 2 did not hit the primary and one more")
        self.assertNotEqual(mask, 0, "ChainTarget 2 did not enter the chain branch")

    def test_the_total_is_the_records_number_for_every_chain_count(self):
        """A sweep: ChainTarget N, plenty of enemies, exactly N units hit.

        Same record, same attributes, same enemies, one column changed. The
        total is N and the additional count is N-1 at every step, which is the
        general statement of the rule the ruling applies to Ricochet and tells
        the writer to apply "to any other chain-target token across classes".
        """
        for count in range(2, 7):
            hits, _mask = self.cast(self.controls[count], count=8)
            self.assertEqual(len(hits), count,
                             "ChainTarget %d hit %d units" % (count, len(hits)))
            self.assertEqual(len(hits) - 1, count - 1,
                             "ChainTarget %d did not add %d further units" % (count, count - 1))
            self.assertEqual(hits, list(range(count)),
                             "ChainTarget %d did not walk the nearest enemies in order" % count)

    def test_every_generated_chain_record_hits_its_own_number(self):
        """Not just Ricochet: every generated record that carries a chain count.

        The ruling says the conversion applies to any other chain-target token
        across classes. This casts every generated record whose
        EffectChainTargets_1 is not zero, with more enemies in reach than any
        of them wants, and checks the core hits exactly that many - so a record
        that was written without the +1 shows up here as one enemy short of
        its own column rather than being noticed on a live server.
        """
        chained = {spell: int(row["EffectChainTargets_1"]) for spell, row in self.records.items()
                   if int(row["EffectChainTargets_1"])}
        self.assertTrue(chained, "no generated record carries a chain target at all")
        # The scene is sized from the records, not fixed. It was eight
        # candidates, which is "more than any of them wants" only while the
        # largest count was the Barbarian's 4 (Ricochet): the Wizard's
        # Electrocute - Chain Lightning carries 11 (primary + 10 more), and
        # eight candidates capped every cast at 9 units whatever the record
        # said (diablocraft-wizard-records). Never fewer than the eight the
        # Barbarian's records were proved on.
        enemies = max(8, max(chained.values()) + 2)
        for spell, field in sorted(chained.items()):
            self.assertEqual(self.chain_target(spell), field,
                             "record %d's column did not reach ChainTarget" % spell)
            self.assertLess(field, enemies + 1, "the scene cannot show record %d's count" % spell)
            hits, _mask = self.cast(spell, count=enemies)
            self.assertEqual(len(hits), field,
                             "%s (%d) hit %d units where its record says %d"
                             % (self.records[spell]["Name_Lang_enUS"], spell, len(hits), field))

    # --- (d) the modifier line is live, not dead ---------------------------

    def test_a_jump_targets_modifier_moves_the_count_through_the_extracted_line(self):
        """Spell.cpp:1880-1881, driven rather than assumed unreachable.

        `if (Player* modOwner = m_caster->GetSpellModOwner())` is skipped
        entirely when the caster has no spell-mod owner, and that is the
        honest default for the rest of this suite: a creature, or a player with
        no SPELLMOD_JUMP_TARGETS aura, never reaches it. So that one line would
        otherwise sit in the extract untested. Here a mod owner is installed
        carrying a flat +2 SPELLMOD_JUMP_TARGETS, and Ricochet's four becomes
        six: the primary and five more. The arithmetic is
        `Player::ApplySpellMod` with core-patches/0014 applied, which is what
        the running server uses.
        """
        field = int(self.records[RICOCHET]["EffectChainTargets_1"])
        plain, _mask = self.cast(RICOCHET, count=8)
        self.assertEqual(len(plain), field)
        boosted, _mask = self.cast(RICOCHET, count=8, jump_mod=2)
        self.assertEqual(len(boosted), field + 2,
                         "a +2 SPELLMOD_JUMP_TARGETS did not add two jumps")
        self.assertEqual(boosted, list(range(field + 2)))
        # And it takes them away again, still through the same line.
        reduced, _mask = self.cast(RICOCHET, count=8, jump_mod=-2)
        self.assertEqual(len(reduced), field - 2,
                         "a -2 SPELLMOD_JUMP_TARGETS did not remove two jumps")

    # --- (e) and the evidence is the extracted code ------------------------

    def test_the_evidence_is_the_extracted_minus_one(self):
        """Change `maxTargets - 1` in the core's own line and Ricochet's four moves.

        The point of extracting rather than modelling. With
        `SearchChainTargets(targets, maxTargets, ...)` Ricochet hits five - the
        primary plus four - which is the bug the ruling exists to prevent, seen
        from the other side: a record of 4 meaning four ADDITIONAL enemies.
        With `maxTargets - 2` it hits three, which is what a record written
        straight from the sheet's 3 would look like. Neither number can come
        from the harness, because the harness never subtracts anything.
        """
        field = int(self.records[RICOCHET]["EffectChainTargets_1"])
        pinned, _mask = self.cast(RICOCHET, count=8)
        self.assertEqual(len(pinned), field, "the unmutated cast already fails")

        one_more, _mask = self.cast(RICOCHET, count=8, name="mutated-no-minus-one", mutate={
            "select_implicit_chain.inc": ("SearchChainTargets(targets, maxTargets - 1,",
                                          "SearchChainTargets(targets, maxTargets,")})
        self.assertEqual(len(one_more), field + 1,
                         "dropping the - 1 did not change the count, so the count is not "
                         "coming from the extracted SelectImplicitChainTargets")
        self.assertEqual(len(one_more), 5, "Ricochet did not become primary + four")

        one_fewer, _mask = self.cast(RICOCHET, count=8, name="mutated-minus-two", mutate={
            "select_implicit_chain.inc": ("SearchChainTargets(targets, maxTargets - 1,",
                                          "SearchChainTargets(targets, maxTargets - 2,")})
        self.assertEqual(len(one_fewer), field - 1,
                         "subtracting two did not change the count either")

    def test_the_guard_at_maxtargets_greater_than_one_is_about_the_multiplier_not_the_count(self):
        """`if (maxTargets > 1)` -> `if (maxTargets > 0)`, and what actually moves.

        This mutation is in the brief as the second half of the evidence, and
        the honest answer is that it does NOT change any target count, which is
        worth writing down rather than hiding. At ChainTarget 1 the branch now
        runs, but it runs `SearchChainTargets(targets, 0, ...)` and
        `while (chainTargets)` is false immediately, so no unit is added. At
        ChainTarget 0 the guard still holds either way. What the mutation does
        move is `m_applyMultiplierMask`, which the branch sets before it
        searches: a one-target record starts claiming the chained-damage
        falloff bookkeeping it has no jumps for. So the guard's job is to keep
        a one-target record out of the multiplier path and to keep a
        zero-target record away from `maxTargets - 1` underflowing to
        4294967295 - not to control how many enemies are hit. The count is the
        `- 1` above, and only the `- 1`.
        """
        guard = {"select_implicit_chain.inc": ("    if (maxTargets > 1)", "    if (maxTargets > 0)")}

        for count in (0, 1):
            pinned_hits, pinned_mask = self.cast(self.controls[count], count=6)
            loose_hits, loose_mask = self.cast(self.controls[count], count=6,
                                               name="mutated-guard", mutate=guard)
            self.assertEqual(pinned_hits, [0])
            self.assertEqual(loose_hits, [0],
                             "loosening the guard changed how many units ChainTarget %d hits" % count)
            self.assertEqual(pinned_mask, 0)
            if count == 1:
                self.assertNotEqual(loose_mask, 0,
                                    "ChainTarget 1 did not start marking damage multipliers, so "
                                    "the guard is not the extracted line")
            else:
                self.assertEqual(loose_mask, 0,
                                 "ChainTarget 0 entered a branch that would underflow maxTargets - 1")

        # Ricochet is on the other side of both guards and does not move.
        self.assertEqual(self.cast(RICOCHET, count=8)[0],
                         self.cast(RICOCHET, count=8, name="mutated-guard", mutate=guard)[0],
                         "loosening the guard changed Ricochet, which is already above it")

    def test_the_ordering_the_chain_walks_by_is_the_extracted_one(self):
        """Break `GetDistanceOrder` and the chain stops taking the nearest.

        The early-break test and the never-twice test both depend on the chain
        really preferring closer enemies, so a constant ordering would make
        them prove nothing. `WorldObject::GetDistanceOrder` is extracted whole
        out of Object.cpp; make it always answer false and the chain keeps
        whichever enemy the search listed first instead of the nearest, which
        with a reversed candidate list is a different set of units.
        """
        # The enemies are handed over nearest-first above, so a broken ordering
        # is invisible there. Hand them over farthest-first instead. A tag is
        # the enemy's place in the candidate list, so reversing the list also
        # reverses the tags: the farthest enemy becomes 1 and the nearest
        # becomes 6, and taking the three nearest in order reads "0 6 5 4".
        case = ["cast", RICOCHET, "object", 0, "%.1f" % PRIMARY_X] + list(
            reversed(self.candidates(6)))
        pinned = self.drive([case])[0].partition("\t")[0]
        blunt = self.drive([case], name="mutated-order", mutate={
            "distance_order.inc": ("    return distsq1 < distsq2;", "    return false;")})[0]
        blunt = blunt.partition("\t")[0]
        self.assertEqual(pinned, "0 6 5 4",
                         "the chain did not take the three nearest out of a farthest-first list")
        # With the ordering blunted the chain keeps whichever enemy the search
        # listed first, which here is the farthest one.
        self.assertEqual(blunt, "0 1 2 3",
                         "the chain's ordering does not come from the extracted "
                         "WorldObject::GetDistanceOrder")
        self.assertNotEqual(blunt, pinned)


if __name__ == "__main__":
    unittest.main(verbosity=2)

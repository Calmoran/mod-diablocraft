"""Both paths agree: the frozen tables and the records say the same numbers.

Spell rewrite step 3. Every number the barbarian sheets name is read twice -
once out of the positional tables the module still uses (frozen at the
baseline commit, before any record moved) and once through the real accessor,
`src/combat/dc_spell_numbers.cpp`, compiled here against test doubles for the
core and driven over the records the generator published. Nothing may differ.

The read inventory is frozen. `tests/spell_numbers/positional_reads.csv`
lists all 194 `n[k]` reads as the baseline commit had them, each with the
number the frozen table gave it, so this comparison keeps its full 194 while
step 4 migrates the call sites one file at a time and deletes the tables. A
separate, informational check follows the live sources and reports how many
reads are left; it never lowers the 194 and never skips a migrated read.

It also proves the three things a positional table could never say:

  * a qualifier picks its own number (Boon of Bul-Kathos names three
    cooldown reductions and they must not collapse into one);
  * an exact value comes back from dc_spell_values, not from a field;
  * base and rune stay apart. Where a rune restates one of its skill's
    tokens, the rune answers with its own number, the SKILL still answers
    with the skill's, and the rune reports nothing inherited for that token.
    `Inherited` is not the translation of every `b->n[k]`: a base read is a
    read of the base spell.

    python mod-diablocraft/scripts/tests/classes/test_spell_numbers.py

Skipped, not failed, where the host has no C++ compiler or no extracted
client DBCs.
"""

from __future__ import annotations

import collections
import csv
import importlib.util
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source  # noqa: E402
import harness_env
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = REPO_ROOT / "mod-diablocraft" / "scripts"
MODULE = REPO_ROOT / "mod-diablocraft"
# The two records that state a token they also inherit (Architect ruling,
# decisions.md 8d89601): the field holds the shout duration Inspiring Presence
# doubles, and the exact row holds the record's own side effect, which must
# not. Everywhere else a record states a token or inherits it, never both.
BOTH_ORIGINS = {("81108", "duration_seconds", ""), ("81118", "duration_seconds", "")}
GENERATED = MODULE / "data" / "generated"
D3 = MODULE / "data" / "d3"
HARNESS = MODULE / "tests" / "spell_numbers"
DBC = REPO_ROOT / "azerothcore-wotlk" / "build" / "server" / "data" / "dbc"
BASELINE = "7702de8"
ABILITY_HEADER = "mod-diablocraft/src/combat/dc_ability_data.h"
PASSIVE_HEADER = "mod-diablocraft/src/combat/dc_passive_data.h"

MANIFEST = HARNESS / "positional_reads.csv"
# The test double's radius maximum is deliberately NOT its minimum, and its
# per-level step is deliberately not zero: the generator picks a radius row by
# RadiusMin, so an accessor that read either of the other two fields has to be
# visible here rather than hidden behind equal numbers.
RADIUS_MAX_OFFSET = 1000.0
RADIUS_PER_LEVEL = 1.0

ABILITY_ROW = re.compile(r'\{(\d+), "([^"]*)", "([^"]*)", \{([^}]*)\}')
PASSIVE_ROW = re.compile(r'\{(\d+), "([^"]*)", \{([^}]*)\}')


def _class_blocks():
    """The generator's CLASS_BLOCKS: which class owns which record ids.

    diablocraft-wizard-records: the generator is class-generic, and the value
    map and spell_shells.sql carry the Wizard's rows next to the Barbarian's.
    The blocks are read from the generator rather than copied, the same way
    test_spell_records.py scopes itself, so a new class is picked up by the
    table that reserves it.
    """
    spec = importlib.util.spec_from_file_location("generate_spells_blocks", SCRIPTS / "generate/classes/generate_spells.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    spec.loader.exec_module(module)
    return module


GENERATOR = _class_blocks()
CLASS_BLOCKS = GENERATOR.CLASS_BLOCKS
# The classes with sheets to read back: a class whose blocks come before its sheets (the Crusader until its records)
# has none.
SHEET_CLASSES = [stem for stem in CLASS_BLOCKS if (D3 / ("%s_skills.csv" % stem)).is_file()]


def class_of(identifier):
    """The class stem whose record or helper block holds this id.

    The Barbarian's fixed companion blocks sit outside its CLASS_BLOCKS record
    range, so anything no other class claims is the Barbarian's - the rule
    test_spell_records.barbarian_id() uses.
    """
    identifier = int(identifier)
    for stem, block in CLASS_BLOCKS.items():
        if stem == "barbarian":
            continue
        if any(first <= identifier <= last for first, last in (block.records, block.helpers)):
            return stem
    return "barbarian"


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


# The same read shape skill_tokens_report.py looks for, scanned here without
# its table_index(): the old generated headers disappear in step 4 and the
# coverage check has to keep working after they do.
LIVE_READ = re.compile(r'([A-Za-z_]\w*(?:\("[^"]*"\))?)\s*(?:->|\.)n\[(\d+)\]')


def tidy(line):
    """A source line as a comparison key: whitespace is not information."""
    return " ".join(line.split())


def live_reads(root):
    """Every positional read still in the sources under `root`.

    Line numbers are deliberately not part of what comes back: step 4 adds
    includes and edits call sites, and a read that merely moved down the file
    has not migrated anywhere.
    """
    if not root.is_dir():
        raise AssertionError("no sources to scan at %s" % root)
    found = []
    for path in sorted(root.rglob("*")):
        if path.suffix not in (".cpp", ".h") or not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            for match in LIVE_READ.finditer(line):
                if path.name.endswith("_data.h"):
                    continue        # the generated tables themselves, not reads of them
                found.append({"file": str(path.relative_to(root.parent)).replace("\\", "/"),
                              "expr": match[0], "code": tidy(line)})
    return found


def baseline_sources(into):
    """The module's sources as the baseline commit had them.

    The coverage check's own regressions need a tree that still HAS the reads
    and the generated tables, whatever step 4 has done to the live one.
    """
    archive = subprocess.run(["git", "archive", BASELINE, "mod-diablocraft/src"],
                             cwd=REPO_ROOT, capture_output=True)
    if archive.returncode:
        raise unittest.SkipTest("the baseline commit is not in this clone")
    subprocess.run(["tar", "-x", "-C", str(into)], input=archive.stdout, check=True)
    return into / "mod-diablocraft" / "src"


def coverage(root, frozen):
    """(reads still in place, reads that are not in the frozen inventory).

    Matching is by file, expression and the text of the line, counted as a
    multiset: a read that moved down a file is the same read, and two
    identical reads in one file stay two reads.
    """
    wanted = collections.Counter((site["file"], site["expr"], tidy(site["code"]))
                                 for site in frozen)
    seen, strays = collections.Counter(), []
    for read in live_reads(root):
        key = (read["file"], read["expr"], read["code"])
        seen[key] += 1
        if seen[key] > wanted[key]:
            strays.append(read)
    return sum(seen.values()) - len(strays), strays


def read_manifest():
    """The frozen 194 reads: what the module read, and what it read then."""
    lines = [line for line in MANIFEST.read_text(encoding="utf-8").splitlines()
             if not line.startswith("#")]
    rows = list(csv.DictReader(lines))
    for row in rows:
        row["line"] = int(row["line"])
        row["index"] = int(row["index"])
    return rows


def frozen(path):
    """A file as the baseline commit had it: the old path cannot move."""
    return subprocess.run(["git", "show", f"{BASELINE}:{path}"], cwd=REPO_ROOT,
                          capture_output=True, check=True).stdout.decode("utf-8")


def load_index(name, offset, kind="i", directory=None):
    data = ((directory or DBC) / name).read_bytes()
    magic, count, _fields, size, _strings = struct.unpack("<4sIIII", data[:20])
    if magic != b"WDBC":
        raise AssertionError(f"{name}: not a WDBC file")
    out = {}
    for index in range(count):
        record = data[20 + index * size: 20 + (index + 1) * size]
        out[struct.unpack_from("<I", record, 0)[0]] = struct.unpack_from("<" + kind, record, offset)[0]
    return out


def split_values(text):
    out, current, quoted, index = [], "", False, 0
    while index < len(text):
        char = text[index]
        if quoted:
            if char == "'" and index + 1 < len(text) and text[index + 1] == "'":
                current += "''"
                index += 2
                continue
            quoted = char != "'"
            current += char
        elif char == "'":
            quoted = True
            current += char
        elif char == ",":
            out.append(current)
            current = ""
        else:
            current += char
        index += 1
    out.append(current)
    return out


def parse_records(sql):
    header = re.search(r"INSERT INTO `spell_dbc` \(([^)]*)\) VALUES", sql)
    names = [name.strip(" `") for name in header[1].split(",")]
    rows = {}
    for line in sql.splitlines():
        line = line.strip().rstrip(",;")
        if not line.startswith("(") or not line.endswith(")"):
            continue
        values = split_values(line[1:-1])
        if len(values) == len(names):
            rows[int(values[0])] = values
    return names, rows


class BothPaths(unittest.TestCase):
    """Drives the compiled accessor once and compares every answer."""

    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("g++") or shutil.which("clang++")
        if not cls.compiler:
            raise unittest.SkipTest("no C++ compiler on this host")
        if not DBC.is_dir():
            raise unittest.SkipTest("client DBCs are not extracted")

        sql = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
        names, records = parse_records(sql)
        at = {name: index for index, name in enumerate(names)}
        cls.names, cls.records = names, records
        durations = load_index("SpellDuration.dbc", 4)
        # the client patch's file is the stock table plus the rows the module adds (data/spell_radius_rows.csv), which is the table
        # the server holds once spellradius_dbc overlays its file
        radii = load_index("SpellRadius.dbc", 4, "f", directory=REPO_ROOT / "client-patch" / "dbc")

        cls.value_map = read_csv(GENERATED / "spell_value_map.csv")
        cls.manifest = read_csv(GENERATED / "spell_shells.csv")
        cls.id_of = {(row["kind"], row["name"]): int(row["spell_id"]) for row in cls.manifest}
        # diablocraft-wizard-records: the Wizard's two runes that state a
        # cooldown they also inherit (the generator's CONDITIONAL_COOLDOWNS:
        # Teleport - Reversal, Archon - Teleport). The field keeps the skill's
        # recovery, the exact row the rune's conditional one - the same shape
        # as the Barbarian's BOTH_ORIGINS, which stays exactly its two.
        cls.both_origins = set(BOTH_ORIGINS) | {
            (str(cls.id_of[("rune", "%s - %s" % (skill, rune))]), token, "")
            for skill, rune, token in GENERATOR.CONDITIONAL_COOLDOWNS}
        # diablocraft-wizard-records: every class's sheets, because every
        # class's rows are in the value map and "each row reads back its sheet
        # number" holds for all of them. `sheet_rows` keeps the count per class
        # so the Barbarian's own count is still asserted on its own.
        cls.values, cls.sheet_rows = {}, collections.Counter()
        for stem in SHEET_CLASSES:
            for name, passive in (("%s_skill_values.csv" % stem, False),
                                  ("%s_passive_values.csv" % stem, True)):
                for row in read_csv(D3 / name):
                    key = (row["skill"], row["rune"], passive)
                    if key in cls.values and cls.values[key][0]["_class"] != stem:
                        raise AssertionError("%s is named by two classes' sheets" % (key,))
                    row["_class"] = stem
                    cls.values.setdefault(key, []).append(row)
                    cls.sheet_rows[stem] += 1
            # diablocraft-wizard-mechanics: Archon form's five abilities have
            # a sheet of their own, which the value map names as skill
            # "Archon form" with the ability as its rune.
            if (D3 / ("%s_archon_values.csv" % stem)).is_file():
                for row in read_csv(D3 / ("%s_archon_values.csv" % stem)):
                    row["_class"] = stem
                    # diablocraft-ie3xd: an "Archon" row is the skill's own (the form's display), not a form ability; its
                    # display_id and scale only feed the client's display row (test_archon_algalon_display.py), the server never reads them.
                    if row["ability"] == "Archon" and row["token"] in ("display_id", "scale"):
                        continue
                    key = ("Archon", "", False) if row["ability"] == "Archon" else (GENERATOR.ARCHON_FORM, row["ability"], False)
                    cls.values.setdefault(key, []).append(row)
                    cls.sheet_rows[stem] += 1
            # diablocraft-im7mr.5: a Life cost lives in the skills sheet's health_cost_pct and the runes sheet's
            # modifier cell, not in a values sheet; the one beside an Essence cost is an exact value, read back here
            if (D3 / ("%s_skills.csv" % stem)).is_file() and "health_cost_pct" in read_csv(D3 / ("%s_skills.csv" % stem))[0]:
                skills = {r["skill_name"]: r for r in read_csv(D3 / ("%s_skills.csv" % stem))}
                for skill_row, rune_row in ([(r, None) for r in skills.values()]
                                            + [(skills[r["skill_name"]], r) for r in read_csv(D3 / ("%s_runes.csv" % stem))]):
                    percent = GENERATOR.life_cost_pct(skill_row, rune_row)
                    key = (skill_row["skill_name"], rune_row["rune_name"] if rune_row else "", False)
                    # only where the map names it: a record-held Life cost is the record's field (test_life_costs)
                    if percent is not None and any(e["skill"] == key[0] and e["rune"] == key[1]
                                                   and e["token"] == GENERATOR.HEALTH_COST_TOKEN for e in cls.value_map):
                        cls.values.setdefault(key, []).append({"token": GENERATOR.HEALTH_COST_TOKEN, "qualifier": "",
                                                               "value": "%g" % percent, "_class": stem})
                        cls.sheet_rows[stem] += 1

        # what the harness needs to be the spell store
        record_lines = []
        for identifier, values in sorted(records.items()):
            duration = durations.get(int(values[at["DurationIndex"]]), 0)
            cells = [identifier, values[at["ProcChance"]], values[at["CumulativeAura"]],
                     values[at["ProcCharges"]], values[at["MaxTargets"]],
                     values[at["ManaCost"]], duration,
                     values[at["RecoveryTime"]], values[at["CategoryRecoveryTime"]]]
            for slot in (1, 2, 3):
                radius = radii.get(int(values[at["EffectRadiusIndex_%d" % slot]]))
                cells += [values[at["EffectBasePoints_%d" % slot]],
                          values[at["EffectDieSides_%d" % slot]],
                          values[at["EffectAuraPeriod_%d" % slot]],
                          values[at["EffectChainTargets_%d" % slot]],
                          "%.6f" % radius if radius is not None else "-1",
                          "%.6f" % RADIUS_PER_LEVEL,
                          "%.6f" % (radius + RADIUS_MAX_OFFSET) if radius is not None else "-1"]
            # diablocraft-wizard-records: the record's PowerType, last so the
            # columns before it keep their places. The accessor divides the
            # cost by the registry's scale for the record's slot: ten for a
            # Rage record (the Barbarian's Fury), one for a Mana record (the
            # Wizard's Arcane Power).
            cells.append(values[at["PowerType"]])
            # Class powers P2: then its SpellClassSet, the family that names the record's class. Two classes share
            # Runic Power at different scales (the Monk's Spirit ten a point, the Necromancer's Essence one), so the
            # accessor reads a cost at its own class's scale.
            cells.append(values[at["SpellClassSet"]])
            record_lines.append("\t".join(str(cell) for cell in cells))

        exact_lines = ["\t".join((spell, token, qualifier, value)) for spell, token, qualifier, value
                       in re.findall(r"\((\d+),'([a-z_]+)','([a-z_]*)',([0-9.]+)\)", sql)]
        cls.exact = {(int(spell), token, qualifier): float(value)
                     for spell, token, qualifier, value in
                     re.findall(r"\((\d+),'([a-z_]+)','([a-z_]*)',([0-9.]+)\)", sql)}

        cls.queries, cls.answers = [], {}
        cls.reads = read_manifest()
        cls._plan_queries()

        cls.record_lines, cls.exact_lines = record_lines, exact_lines
        lines, cls.stderr = cls.drive(MODULE / "src" / "combat" / "dc_spell_numbers.cpp")

        if len(lines) != len(cls.queries):
            raise AssertionError("the harness answered %d of %d queries" % (len(lines), len(cls.queries)))
        for query, answer in zip(cls.queries, lines):
            cls.answers[tuple(query)] = answer

    @classmethod
    def drive(cls, accessor):
        """Compile the accessor with the harness, run it, return its answers."""
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "records.tsv").write_text("\n".join(cls.record_lines) + "\n", encoding="utf-8")
            (work / "exact.tsv").write_text("\n".join(cls.exact_lines) + "\n", encoding="utf-8")
            (work / "queries.tsv").write_text(
                "\n".join("\t".join(query) for query in cls.queries) + "\n", encoding="utf-8")
            binary = harness_env.build([HARNESS / "harness.cpp", accessor], flags=["-std=c++17", "-O0"],
                                       includes=[HARNESS / "stubs", MODULE / "src" / "combat"])
            run = harness_env.run([str(binary), str(work / "records.tsv"), str(work / "exact.tsv"),
                                  str(work / "queries.tsv")], capture_output=True, text=True)
            if run.returncode:
                raise AssertionError("the harness did not run:\n" + run.stderr[-4000:])
            return run.stdout.splitlines(), run.stderr

    # --- the queries ------------------------------------------------------
    @classmethod
    def _ask(cls, which, spell, token, qualifier):
        query = (which, str(spell), token, qualifier)
        if query not in cls.queries:
            cls.queries.append(query)
        return query

    @classmethod
    def _plan_queries(cls):
        for entry in cls.value_map:
            for which in ("get", "own", "inherited"):
                cls._ask(which, entry["spell_id"], entry["token"], entry["qualifier"])
        for site in cls.reads:
            resolved = cls.resolve(site)
            if resolved:
                spell, row = resolved
                cls._ask("get", spell, row["token"], row["qualifier"])
                cls._ask("own", spell, row["token"], row["qualifier"])

    @classmethod
    def sheet_row(cls, entry):
        """The values sheet row a map entry names: its own, or its skill's."""
        rune = entry["rune"] if entry["origin"] == "own" else ""
        for passive in (False, True):
            for row in cls.values.get((entry["skill"], rune, passive), []):
                if row["token"] == entry["token"] and row["qualifier"] == entry["qualifier"]:
                    return row
        return None

    @classmethod
    def resolve(cls, site):
        """(spell id, values row) for one frozen read, or None."""
        skill = site["skill"]
        if site["passive"]:
            spell = cls.id_of.get(("passive", site["passive"]))
            rows = cls.values.get((site["passive"], "", True), [])
        elif site["rune"]:
            spell = cls.id_of.get(("rune", "%s - %s" % (skill, site["rune"])))
            rows = cls.values.get((skill, site["rune"], False), [])
        elif skill:
            spell = cls.id_of.get(("active", skill))
            rows = cls.values.get((skill, "", False), [])
        else:
            return None
        if spell is None or site["index"] >= len(rows):
            return None
        return spell, rows[site["index"]]

    def answer(self, which, spell, token, qualifier=""):
        return self.answers[(which, str(spell), token, qualifier)]

    def number(self, which, spell, token, qualifier=""):
        given = self.answer(which, spell, token, qualifier)
        return None if given == "absent" else float(given)

    # --- the comparisons --------------------------------------------------
    def test_every_value_reads_back_through_the_accessor(self):
        """Every sheet number, and every one a rune takes from its skill.

        The Barbarian's 310 and 398, and since diablocraft-wizard-records the
        Wizard's too: a Wizard cost is Mana, one per Arcane Power point, and
        reads back its sheet number through the same accessor.

        Each row is asked of the accessor for ITS origin, which is the only
        way to ask the two records that state a token they also inherit
        (BOTH_ORIGINS) for one number rather than the other. `Get`, which is
        what the module's Num() calls, is checked as well and has to answer
        the record's own number wherever the record has one.
        """
        own = collections.Counter()
        both = {(entry["spell_id"], entry["token"], entry["qualifier"])
                for entry in self.value_map if entry["origin"] == "own"}
        stated_twice = both & {(entry["spell_id"], entry["token"], entry["qualifier"])
                               for entry in self.value_map if entry["origin"] == "inherited"}
        self.assertEqual(stated_twice, self.both_origins,
                         "only the named records state a token they also inherit")
        self.assertEqual({key for key in stated_twice if class_of(key[0]) == "barbarian"},
                         BOTH_ORIGINS)
        for entry in self.value_map:
            row = self.sheet_row(entry)
            self.assertIsNotNone(row, "%s %s has no sheet row" % (entry["spell_id"], entry["token"]))
            key = (entry["spell_id"], entry["token"], entry["qualifier"])
            given = self.number(entry["origin"], *key)
            self.assertIsNotNone(given, "%s %s reads absent" % (entry["spell_id"], entry["token"]))
            self.assertAlmostEqual(given, float(row["value"]), places=3,
                                   msg="%s %s: %s through the record, %s in the sheet"
                                   % (entry["spell_id"], entry["token"], given, row["value"]))
            if entry["origin"] == "own" or key not in both:
                self.assertAlmostEqual(self.number("get", *key), float(row["value"]), places=3,
                                       msg="%s %s: Num() does not read this row"
                                       % (entry["spell_id"], entry["token"]))
            own[class_of(entry["spell_id"])] += entry["origin"] == "own"
        self.assertEqual(own, self.sheet_rows, "every sheet value was read, class by class")
        self.assertGreater(own["barbarian"], 0, "the Barbarian's rows were read")

    def test_a_broken_accessor_is_caught(self):
        """The harness is only worth its runtime if a wrong read fails it.

        Each mutation is applied to a copy of the real accessor, compiled and
        run the same way, and must disagree with the sheets. The radius one is
        here because the first version of this harness gave the test double
        the same number for RadiusMin and RadiusMax, so swapping them changed
        nothing and the suite stayed green: a check that cannot fail is not a
        check.
        """
        mutations = [
            ("base points without their die side",
             "effect.BasePoints + effect.DieSides", "effect.BasePoints"),
            ("the radius maximum instead of the minimum",
             "RadiusEntry->RadiusMin", "RadiusEntry->RadiusMax"),
            ("the qualifier dropped from the lookup",
             "Key{spell, token, qualifier}", 'Key{spell, token, ""}'),
            ("the exact table not read at all",
             "return Exact(row);", "return std::nullopt;"),
            # Step 5: the cost is Rage in the record and Fury in the sheets,
            # so a read that forgets the conversion is a tenfold error.
            ("the cost read in Rage units instead of Fury",
             "info->ManaCost / Resources::Data::ScaleOf(", "double(info->ManaCost) + 0 * Resources::Data::ScaleOf("),
            # diablocraft-wizard-records: only a Rage record is divided; a
            # Mana cost divided like Fury reads a tenth of the Wizard's sheet.
            # The scale is the class resource registry's, keyed by the slot.
            ("a Mana cost divided like Rage",
             "info->PowerType);", "1);"),
            # Class powers P2: the Necromancer's Essence is one Runic Power a point and the Monk's Spirit ten, so a
            # cost read at the slot's first class's scale reads a tenth of every Essence cost.
            ("an Essence cost read at the Monk's Spirit scale",
             "Shells::ClassOfFamily(info->SpellFamilyName)", "3"),
            # Step 6: the record's ChainTarget counts the primary victim and
            # the sheets state the enemies besides it, so a read that forgets
            # the conversion prints one enemy too many.
            ("the chain count read with the primary still in it",
             "info->Effects[row.slot - 1].ChainTarget) - 1",
             "info->Effects[row.slot - 1].ChainTarget)"),
            # diablocraft-wizard-mechanics: part A wrote the armors' ten
            # minutes as ten seconds and read them back as seconds, so the
            # pair agreed with the sheet and nobody noticed. The record holds
            # 600 000 ms now; a read that forgets the unit answers 600.
            ("a duration_minutes read as seconds",
             "inMinutes ? 60000.0 : 1000.0", "1000.0"),
        ]
        accessor = (MODULE / "src" / "combat" / "dc_spell_numbers.cpp").read_text(encoding="utf-8")
        expected = [(entry, self.sheet_row(entry)) for entry in self.value_map]
        for label, before, after in mutations:
            with self.subTest(mutation=label):
                self.assertIn(before, accessor, "the accessor no longer has %r to break" % before)
                with tempfile.TemporaryDirectory() as directory:
                    broken = Path(directory) / "dc_spell_numbers.cpp"
                    broken.write_text(accessor.replace(before, after), encoding="utf-8")
                    lines, _stderr = self.drive(broken)
                answers = {tuple(query): answer for query, answer in zip(self.queries, lines)}
                wrong = 0
                for entry, row in expected:
                    given = answers[("get", entry["spell_id"], entry["token"], entry["qualifier"])]
                    if given == "absent" or abs(float(given) - float(row["value"])) > 0.001:
                        wrong += 1
                self.assertGreater(wrong, 0, "%s changed no answer: this harness would not "
                                             "have caught it" % label)

    def test_the_chain_count_reads_the_additional_enemies_not_the_core_s_total(self):
        """The accessor's half of the chain convention: field four, Num three.

        The record's EffectChainTargets counts the primary victim, because
        Spell::SelectImplicitChainTargets searches `maxTargets - 1` more after
        the caller has already added it (Spell.cpp:1892 at the pin). The
        values sheets state the additional enemies, so Num takes the one back
        off (Architect, decisions.md 2026-09-20). The record the harness reads
        here is the generated one, so the four is not typed in anywhere.
        """
        at = {name: index for index, name in enumerate(self.names)}
        chain = [entry for entry in self.value_map if entry["source"] == "chain"]
        self.assertTrue(chain, "no token is stored as a chain count any more")
        for entry in chain:
            holder = self.records[int(entry["holder_spell_id"])]
            field = int(holder[at["EffectChainTargets_%s" % entry["slot"]]])
            stated = float(self.sheet_row(entry)["value"])
            given = self.number("get", entry["spell_id"], entry["token"], entry["qualifier"])
            self.assertEqual(field, int(stated) + 1,
                             "%s: the field is not the sheet plus the primary" % entry["spell_id"])
            self.assertEqual(given, stated,
                             "%s: the accessor answers %s and the sheet says %s"
                             % (entry["spell_id"], given, stated))
            self.assertEqual(given, field - 1)
        # The Barbarian's own named cases, unchanged.
        self.assertEqual(self.number("get", "81029", "target_count", ""), 3)
        # Brawler's three is the other meaning and no longer a chain count at
        # all: "as long as there are 3 enemies within 12 yards" reaches nobody,
        # so it is `nearby_enemy_count`, stored as ordinary base points with no
        # conversion of its own (Architect, 2026-09-20). dc_passives.cpp reads
        # it by that name, and the record carries no chain count.
        self.assertEqual(self.number("get", "81150", "nearby_enemy_count", ""), 3)
        self.assertEqual(int(self.records[81150][
            {n: i for i, n in enumerate(self.names)}["EffectChainTargets_1"]]), 0,
            "a threshold is not stored in the chain field")
        self.assertNotIn(("get", "81150", "target_count", ""), self.answers,
                         "Brawler still answers to the reach token")

    def test_every_frozen_read_agrees_with_the_record(self):
        """All 194 reads, against the values the frozen tables gave them.

        The manifest is the inventory, so this stays 194 while step 4 moves
        the call sites and deletes the tables underneath them.
        """
        checked, unresolved = 0, []
        for site in self.reads:
            resolved = self.resolve(site)
            if not resolved:
                unresolved.append("%s:%d %s" % (site["file"], site["line"], site["expr"]))
                continue
            spell, row = resolved
            wanted = float(site["frozen_value"])
            given = self.number("get", spell, row["token"], row["qualifier"])
            self.assertIsNotNone(given, "%s:%d (%s) reads absent through the record"
                                 % (site["file"], site["line"], row["token"]))
            self.assertAlmostEqual(given, wanted, places=3,
                                   msg="%s:%d %s: %s through the record, %s in the frozen table"
                                   % (site["file"], site["line"], site["expr"], given, wanted))
            checked += 1
        self.assertEqual(unresolved, [], "every frozen read resolves to a sheet row")
        self.assertEqual(len(self.reads), 194, "the frozen inventory is all 194 reads")
        self.assertEqual(checked, 194)

    def test_the_manifest_is_the_frozen_tables(self):
        """Guard the inventory itself: it must still be what 7702de8 said."""
        try:
            ability_text, passive_text = frozen(ABILITY_HEADER), frozen(PASSIVE_HEADER)
        except subprocess.CalledProcessError:
            raise unittest.SkipTest("the baseline commit is not in this clone")
        ability = {(skill, rune): [piece.strip() for piece in numbers.split(",") if piece.strip()]
                   for _id, skill, rune, numbers in ABILITY_ROW.findall(ability_text)}
        passives = {name: [piece.strip() for piece in numbers.split(",") if piece.strip()]
                    for _id, name, numbers in PASSIVE_ROW.findall(passive_text)}
        for site in self.reads:
            old = passives.get(site["passive"], []) if site["passive"] \
                else ability.get((site["skill"], site["rune"]), [])
            self.assertGreater(len(old), site["index"],
                               "%s:%d reads past the frozen table" % (site["file"], site["line"]))
            self.assertAlmostEqual(float(old[site["index"]]), float(site["frozen_value"]), places=6,
                                   msg="%s:%d: the manifest disagrees with the frozen table"
                                   % (site["file"], site["line"]))

    def test_the_live_migration_coverage_is_reported(self):
        """Informational: which of the frozen reads the module still performs.

        Step 4 empties this out one file at a time. It never lowers the 194
        above and never skips a read that has moved; all it does is say where
        the migration has got to, and refuse a read the inventory does not
        know. A scan that cannot run is a failure, never a report of zero:
        "no reads found" and "I could not look" are different answers.
        """
        remaining, strays = coverage(MODULE / "src", self.reads)
        print("\n  live positional reads: %d of the frozen %d still in place"
              % (remaining, len(self.reads)))
        self.assertEqual([read["code"] for read in strays], [],
                         "a live read is not in the frozen inventory; if it is genuinely new, "
                         "say so to the PM - do not refreeze to make it go away")
        self.assertLessEqual(remaining, len(self.reads))

    def test_coverage_survives_the_edits_step_4_makes(self):
        """A line shift is not a migration, a missing header is not a zero."""
        with tempfile.TemporaryDirectory() as directory:
            root = baseline_sources(Path(directory))

            # 1. an include added above the reads moves every line below it
            moved = root / "combat" / "dc_combat.cpp"
            moved.write_text("\n#include <cstddef>\n" + moved.read_text(encoding="utf-8"),
                             encoding="utf-8")
            remaining, strays = coverage(root, self.reads)
            self.assertEqual(strays, [], "a line shift was mistaken for a new read")
            self.assertEqual(remaining, len(self.reads), "a line shift was mistaken for a migration")

            # 2. the generated tables deleted while the reads are still there
            for header in ("combat/dc_ability_data.h", "combat/dc_passive_data.h",
                           "classes/dc_ancient_data.h"):
                (root / header).unlink()
            remaining, strays = coverage(root, self.reads)
            self.assertEqual(strays, [])
            self.assertEqual(remaining, len(self.reads),
                             "deleting the headers must not report the reads as migrated")

            # 3. and only when the reads themselves are gone is it zero
            for path in root.rglob("*.cpp"):
                text = path.read_text(encoding="utf-8")
                migrated = LIVE_READ.sub("DC::Combat::Numbers::Num(id, \"token\")", text)
                if migrated != text:
                    path.write_text(migrated, encoding="utf-8")
            remaining, strays = coverage(root, self.reads)
            self.assertEqual((remaining, strays), (0, []), "a migrated source still reports reads")

    def test_a_guarded_read_resolves_to_the_rune_it_names(self):
        """A read of a variable guarded as a rune is a read of THAT rune's row.

        Four reads were recorded against a base row because the token report's
        anchors took the first name they recognised near them: dc_combat.cpp
        :1325-1326 read Find(shell.spellId)->n[0] inside `skill == X && rune ==
        Y`, and dc_abilities.cpp:344 reads r->n[0] and r->n[1] inside
        `if (Rune(*r, "Into the Fray"))` on a line that also reads
        Base("Battle Rage")->n[2]. The rows are the runes'; the numbers the
        base rows would have given are the skills' Fury costs and bonuses.
        """
        wanted = {
            ("src/combat/dc_combat.cpp", "1325", "metadata->n[0]"):
                ("Ancient Spear", "Boulder Toss", 20.0, "damage_pct", "cost_resource", 25.0),
            ("src/combat/dc_combat.cpp", "1326", "metadata->n[0]"):
                ("Seismic Slam", "Rumble", 15.0, "damage_pct", "cost_resource", 30.0),
            ("src/combat/dc_abilities.cpp", "344", "r->n[0]"):
                ("Battle Rage", "Into the Fray", 1.0, "crit_chance_pct", "cost_resource", 20.0),
            ("src/combat/dc_abilities.cpp", "344", "r->n[1]"):
                ("Battle Rage", "Into the Fray", 10.0, "radius_yards", "damage_bonus_pct", 10.0),
        }
        seen = 0
        for site in self.reads:
            key = (site["file"], str(site["line"]), site["expr"])
            if key not in wanted:
                continue
            skill, rune, value, token, base_token, base_value = wanted[key]
            self.assertEqual((site["skill"], site["rune"]), (skill, rune),
                             "%s:%s %s must name the rune it is guarded as" % key)
            self.assertAlmostEqual(float(site["frozen_value"]), value, places=6)
            spell, row = self.resolve(site)
            self.assertEqual(int(spell), self.id_of[("rune", "%s - %s" % (skill, rune))],
                             "%s:%s must resolve to the rune's spell" % key[:2])
            self.assertEqual(row["token"], token)
            self.assertAlmostEqual(self.number("get", spell, token, ""), value, places=3)
            # the base row's number this used to be recorded as is still there,
            # on the SKILL, and is not what this read gives
            base = self.id_of[("active", skill)]
            self.assertAlmostEqual(self.number("get", base, base_token, ""), base_value, places=3)
            self.assertNotEqual(int(spell), base)
            seen += 1
        self.assertEqual(seen, 4, "all four guarded reads are in the inventory")

    def test_the_migrated_call_sites_read_the_rune_not_the_cost(self):
        """The substitution those four would have become is refused in source."""
        for rune, token in (("Boulder Toss", "damage_pct"), ("Rumble", "damage_pct")):
            line = next((line for line in barbarian_source.abilities((".cpp",)).splitlines()
                         if 'rune=="%s"' % rune in line and "Numbers::Num(id," in line), None)
            self.assertIsNotNone(line, "the %s call site is gone" % rune)
            self.assertIn('Numbers::Num(id, "%s")' % token, line)
            self.assertNotIn("cost_resource", line,
                             "%s is reading its skill's Fury cost again" % rune)
        abilities = barbarian_source.abilities((".cpp",))
        lines = abilities.splitlines()
        start = next(number for number, line in enumerate(lines)
                     if 'Rune(*r, "Into the Fray")' in line)
        block = "\n".join(lines[start:start + 7])   # b3zj: two lines more, the braces and the count Into the Fray's buff shows
        self.assertIn('Numbers::Num(r->id, "crit_chance_pct")', block)
        self.assertIn('Numbers::Num(r->id, "radius_yards")', block)
        self.assertIn('Numbers::Num(Base("Battle Rage")->id, "crit_chance_pct")', block)
        self.assertNotIn("cost_resource", block,
                         "Into the Fray is reading Battle Rage's Fury cost again")

    def test_no_read_is_anchored_against_its_own_guard(self):
        """The class those four belonged to, checked across all 194.

        The rule is about the read's OWNER, not its line: a line may hold a
        base read and a rune read at once.
        """
        owner_of = re.compile(r'([A-Za-z_]\w*(?:\("[^"]*"\))?)\s*(?:->|\.)n\[')
        sources = {}
        for site in self.reads:
            owner = owner_of.search(site["expr"])[1]
            if owner.startswith(("Base(", "RowFor(")) or owner in ("b", "base"):
                continue        # a named base row, or the base arm of a ternary
            lines = sources.setdefault(
                site["file"], frozen("mod-diablocraft/" + site["file"]).splitlines())
            guard = re.compile(r'Rune\(\s*\*?%s\s*,\s*"([^"]+)"\)' % re.escape(owner))
            named = ""
            for index in range(site["line"] - 1, max(-1, site["line"] - 31), -1):
                found = guard.search(lines[index])
                if found:
                    named = found[1]
                    break
            if not named:
                found = re.search(r'rune\s*==\s*"([^"]+)"', site["code"])
                named = found[1] if found else ""
            if named:
                self.assertEqual(site["rune"], named,
                                 "%s:%s reads a row its own guard contradicts"
                                 % (site["file"], site["line"]))

    def test_only_the_named_exceptions_still_take_fury_for_a_cast(self):
        """Step 5: the core pays, and the module keeps only what it cannot.

        decisions.md 2026-09-20 put every Fury cost in the spell record and the
        payment in the core, with two named module exceptions. (The same day's
        later ruling added core-patches/0014, which changes how the core
        stacks those reductions, not who pays.) So the module must no longer hold its own cost arithmetic,
        and there must be exactly two places left that take Fury for a cast:
        Whirlwind's channel tick, and the surplus the two spend-all runes turn
        into damage. Each is named, with the ruling, where it lives.
        """
        gone = ("CostAfterReduction(", "PayCast(", "CostFactor(", "furyCost", "rcrApplied")
        sources = sorted((MODULE / "src").rglob("*.cpp")) + sorted((MODULE / "src").rglob("*.h"))
        self.assertGreater(len(sources), 20, "the module sources were not found")
        spends = []
        for path in sources:
            lines = path.read_text(encoding="utf-8").splitlines()
            for number, line in enumerate(lines, 1):
                code = line.split("//")[0]
                for name in gone:
                    self.assertNotIn(name, code,
                                     "%s:%d still has the module's own cost arithmetic (%s)"
                                     % (path.name, number, name))
                if not re.search(r"ChangeFury\(\s*\w+\s*,\s*-", code):
                    continue
                owner = ""
                for above in reversed(lines[:number - 1]):
                    found = re.match(r"\s*(?:bool|void|double|int32|std::uint32_t) (\w+)\(", above)
                    if found:
                        owner = found[1]
                        break
                spends.append((path.name, owner))
        self.assertEqual(sorted(spends),
                         [("dc_combat.cpp", "PayWhirlwindTick"), ("dc_combat_resolve.cpp", "Begin")],
                         "something other than the two named exceptions takes Fury")
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src" / "combat" / "dc_combat_internal.h", *sorted((MODULE / "src" / "combat").glob("dc_combat*.cpp"))])
        for exception in ("SpendsEveryPoint", "PayWhirlwindTick"):
            at = combat.index("%s(Player" % exception if exception == "PayWhirlwindTick"
                              else "%s(Shell" % exception)
            preamble = combat[:at].rsplit("\n\n", 1)[-1]
            self.assertIn("exception", preamble,
                          "%s does not say it is an exception to the core paying" % exception)

    def test_a_scan_that_cannot_run_is_not_a_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(AssertionError):
                coverage(Path(directory) / "gone", self.reads)

    def test_a_new_read_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = baseline_sources(Path(directory))
            invented = root / "combat" / "dc_combat.cpp"
            invented.write_text(invented.read_text(encoding="utf-8")
                                + "\n// double stray = row->n[11];\n", encoding="utf-8")
            _remaining, strays = coverage(root, self.reads)
            self.assertEqual(len(strays), 1, "a read the inventory does not know must be rejected")

    def test_a_base_read_keeps_the_base_value_when_a_rune_overrides(self):
        """`b->n[k]` is a read of the base spell, not of the rune's inheritance.

        diablocraft-wizard-records: every class's runes, and the Barbarian's
        alone must still give more than ten overrides with their own number.
        """
        cases = collections.Counter()
        runes = [row for stem in SHEET_CLASSES for row in read_csv(D3 / ("%s_runes.csv" % stem))]
        for row in runes:
            skill, rune = row["skill_name"], row["rune_name"]
            base_id = self.id_of.get(("active", skill))
            rune_id = self.id_of.get(("rune", "%s - %s" % (skill, rune)))
            if base_id is None or rune_id is None:
                continue
            base_rows = {(value["token"], value["qualifier"]): value
                         for value in self.values.get((skill, "", False), [])}
            for value in self.values.get((skill, rune, False), []):
                key = (value["token"], value["qualifier"])
                if key not in base_rows:
                    continue        # not an override
                rune_number = float(value["value"])
                base_number = float(base_rows[key]["value"])
                self.assertAlmostEqual(self.number("get", rune_id, *key), rune_number, places=3,
                                       msg="%s - %s: the rune lost its own %s" % (skill, rune, key[0]))
                self.assertAlmostEqual(self.number("own", rune_id, *key), rune_number, places=3)
                if (str(rune_id), key[0], key[1]) in self.both_origins:
                    # The ruling's two: the rune states this token AND keeps
                    # the skill's in the field a modifier doubles, so both
                    # answers exist and Num() - checked just above - is the
                    # rune's own.
                    self.assertAlmostEqual(self.number("inherited", rune_id, *key),
                                           base_number, places=3,
                                           msg="%s - %s: the skill's %s did not reach the record"
                                           % (skill, rune, key[0]))
                else:
                    self.assertIsNone(self.number("inherited", rune_id, *key),
                                      "%s - %s: %s is the rune's own, nothing is inherited"
                                      % (skill, rune, key[0]))
                self.assertAlmostEqual(self.number("get", base_id, *key), base_number, places=3,
                                       msg="%s: the skill's %s moved when %s overrode it"
                                       % (skill, key[0], rune))
                if abs(rune_number - base_number) > 1e-9:
                    cases[class_of(rune_id)] += 1
        self.assertGreater(cases["barbarian"], 10,
                           "there are overrides with a different number to prove this on")

    def test_a_rune_that_does_not_restate_a_token_inherits_it(self):
        inherited = 0
        for entry in self.value_map:
            if entry["origin"] != "inherited":
                continue
            key = (entry["token"], entry["qualifier"])
            base_rows = {(value["token"], value["qualifier"]): value
                         for value in self.values.get((entry["skill"], "", False), [])}
            self.assertIn(key, base_rows)
            wanted = float(base_rows[key]["value"])
            self.assertAlmostEqual(self.number("inherited", entry["spell_id"], *key), wanted,
                                   places=3, msg="%s: %s is not the skill's number"
                                   % (entry["spell_id"], entry["token"]))
            if (entry["spell_id"], entry["token"], entry["qualifier"]) not in self.both_origins:
                self.assertIsNone(self.number("own", entry["spell_id"], *key),
                                  "%s: %s is inherited, not the row's own"
                                  % (entry["spell_id"], entry["token"]))
            inherited += 1
        self.assertEqual(inherited, sum(1 for entry in self.value_map
                                        if entry["origin"] == "inherited"))

    def test_a_qualifier_picks_its_own_number(self):
        """Boon of Bul-Kathos names three cooldown reductions, not one."""
        by_key = {}
        for entry in self.value_map:
            by_key.setdefault((entry["spell_id"], entry["token"]), set()).add(entry["qualifier"])
        collisions = [(spell, token, sorted(qualifiers))
                      for (spell, token), qualifiers in by_key.items() if len(qualifiers) > 1]
        self.assertTrue(collisions, "the sheets still have qualified tokens")
        for spell, token, qualifiers in collisions:
            rows = {value["qualifier"]: value["value"]
                    for value in self.values.get(
                        next((key for key in self.values
                              if self.id_of.get(("active", key[0])) == int(spell)
                              or self.id_of.get(("passive", key[0])) == int(spell)), None), [])
                    if value["token"] == token}
            for qualifier in qualifiers:
                given = self.number("get", spell, token, qualifier)
                self.assertIsNotNone(given)
                if qualifier in rows:
                    self.assertAlmostEqual(given, float(rows[qualifier]), places=3,
                                           msg="%s %s:%s" % (spell, token, qualifier))
            values = {self.number("get", spell, token, qualifier) for qualifier in qualifiers}
            self.assertEqual(len(values), len({rows.get(q) for q in qualifiers if q in rows}) or len(values),
                             "%s %s: the qualifiers collapsed into one number" % (spell, token))

    def test_an_exact_value_comes_from_the_table(self):
        """The exceptions read from dc_spell_values, never from a field."""
        checked = 0
        for entry in self.value_map:
            if entry["source"] != "exact":
                continue
            key = (int(entry["spell_id"]), entry["token"], entry["qualifier"])
            self.assertIn(key, self.exact, "%s has no dc_spell_values row" % (key,))
            given = self.number("get", entry["spell_id"], entry["token"], entry["qualifier"])
            self.assertAlmostEqual(given, self.exact[key], places=6)
            checked += 1
        # Every exact row in the map, and the table holds exactly those and no
        # more: a number that has moved into a field (step 6 took the 66
        # cooldown and charge-recharge rows) must not keep a second home here.
        self.assertEqual(checked, len(self.exact),
                         "the exact table and the value map disagree on what is exact")
        self.assertGreater(checked, 50, "the exact exceptions were exercised")
        self.assertIn("exact rows loaded", self.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)

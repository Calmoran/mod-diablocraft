"""No hardcoded class check outside a class's own skill code (diablocraft-ikze; docs/briefs/builds-on-brief.md item 6).

Anything that is not one class's own skill reads the class from dc_class_map (class_key,
primary_stat, ...) and never names a class in code. This test counts the lines that do, per file,
and fails when a file has more than its allowance.

A hardcoded class check is a line that, with comments stripped,
  C++:  names a player class constant (CLASS_WARRIOR ... CLASS_DRUID, CLASS_MONK) or compares
        getClass() with a number;
  Lua:  compares GetClass() with a number, writes a number into `class_id =` / `wow_class_id =`
        in query text, or compares with a class key ("barbarian") or class token ("WARRIOR").
Item and spell classes (ITEM_CLASS_*, SPELL_DAMAGE_CLASS_*, UnitClassification) are not class checks.

Not covered: a class id held in a variable first (`local c = p:GetClass()` then `c == 1`), a class
key compared in C++, XML, and the table-lookup uses of getClass() (those are the right pattern).

Allowed: anything under src/classes/<class>/ (a class's own skill code), and elsewhere at most
ALLOWED[file] lines. The counts are the Planner's review at nightly 08960632 and were re-measured
at this branch's base (nightly 5cadaa03): identical. Raising one needs its reason written here,
and the reviewer checks it.

Run from anywhere: `python3 mod-diablocraft/scripts/tests/classes/test_class_checks.py`.
"""
import csv
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]

SCAN = [
    "mod-diablocraft/src",
    "mod-diablocraft/lua",
    "client-patch/addons/Torment",
    "client-patch/addons/ElvUI_Torment",
]
SUFFIXES = {".cpp", ".h", ".hpp", ".lua"}

# file -> (lines allowed, why)
ALLOWED = {
    "mod-diablocraft/src/classes/barbarian/dc_barbarian_primaries.cpp": (3, "Barbarian primary skill cast check; Frenzy reset at login and logout"),
    "mod-diablocraft/src/classes/barbarian/dc_barbarian.cpp": (1, "Barbarian skill charges (Furious Charge, Avalanche, Battle Rage)"),
    "mod-diablocraft/src/combat/dc_combat_internal.h": (1, "Barbarian Fury from damage taken"),
    "mod-diablocraft/src/stats/dc_stats.cpp": (1, "WoW's rage rewards kept off Fury"),
    "mod-diablocraft/lua/aio/dc_tooltip.lua": (2, "main stat per class for item lines (all seven D3 classes)"),
}

MESSAGE = ("Read the class from dc_class_map (class_key, primary_stat, ...) instead. One class's own skill "
           "code goes in src/classes/<class>/. Raising an allowance needs its reason in this test, and the "
           "reviewer checks it.")

WOW = "WARRIOR|PALADIN|HUNTER|ROGUE|PRIEST|DEATH_KNIGHT|SHAMAN|MAGE|WARLOCK|DRUID"
KEYS = "barbarian|wizard|monk|demonhunter|witchdoctor|crusader|necromancer"
TOKENS = "WARRIOR|PALADIN|HUNTER|ROGUE|PRIEST|DEATHKNIGHT|SHAMAN|MAGE|WARLOCK|DRUID"

CPP_RULES = {
    "class constant": re.compile(r"\bCLASS_(?:%s|MONK)\b" % WOW),
    "getClass() against a number": re.compile(r"\bgetClass\(\)\s*[=!<>]=?\s*\d|\b\d+\s*[=!<>]=?\s*\S*getClass\(\)"),
}
_NAME = r"""['"](?:%s|%s)['"]""" % (KEYS, TOKENS)
LUA_RULES = {
    "GetClass() against a number": re.compile(r"\bGetClass\(\)\s*[=~<>]=?\s*\d|\b\d+\s*[=~<>]=?\s*\S*GetClass\(\)"),
    "a number written into class_id": re.compile(r"(?<![A-Za-z0-9])(?:wow_)?class_id\s*=\s*\d"),
    "class key or token comparison": re.compile(r"[=~]=\s*" + _NAME + "|" + _NAME + r"\s*[=~]="),
}

# Strings first so a "//" or "--" inside one is not taken for a comment; then comments, which
# become blanks (newlines kept) so a reported line number is the real one.
_STRING = r"""\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'"""
_COMMENT = {
    ".lua": re.compile(r"--\[(=*)\[.*?\]\1\]|--[^\n]*|" + _STRING, re.S),
    ".cpp": re.compile(r"/\*.*?\*/|//[^\n]*|" + _STRING, re.S),
}
_COMMENT[".h"] = _COMMENT[".hpp"] = _COMMENT[".cpp"]


def strip_comments(text, suffix):
    def blank(m):
        s = m.group(0)
        return s if s[0] in "\"'" else re.sub(r"[^\n]", "", s)
    return _COMMENT[suffix].sub(blank, text)


def class_check_lines(rel, text):
    """[(line number, rule name)] for every hardcoded class check in one file."""
    suffix = Path(rel).suffix
    rules = LUA_RULES if suffix == ".lua" else CPP_RULES
    hits = []
    for number, line in enumerate(strip_comments(text, suffix).splitlines(), 1):
        for name, rule in rules.items():
            if rule.search(line):
                hits.append((number, name))
                break
    return hits


def is_skipped(rel):
    parts = rel.split("/")
    name = parts[-1]
    return ("tests" in parts or "generated" in parts or name.startswith("test_") or name.endswith("_test.lua")
            or name.startswith("generated") or name.endswith(".in"))


def is_class_code(rel):
    # src/classes/<class>/..., not the files directly in src/classes/
    return re.match(r"mod-diablocraft/src/classes/[^/]+/", rel) is not None


def scan_files(root=REPO):
    """[(repo-relative path, text)] for every file the test reads."""
    found = []
    for base in SCAN:
        for path in sorted((root / base).rglob("*")):
            rel = path.relative_to(root).as_posix()
            if path.is_file() and path.suffix in SUFFIXES and not is_skipped(rel):
                found.append((rel, path.read_text(encoding="utf-8-sig", errors="replace")))
    return found


def violations(files):
    """One message per file that has more class checks than it may."""
    out = []
    for rel, text in files:
        if is_class_code(rel):
            continue
        hits = class_check_lines(rel, text)
        allowed = ALLOWED.get(rel, (0, ""))[0]
        if len(hits) > allowed:
            lines = ", ".join("%d (%s)" % h for h in hits)
            out.append("%s: %d hardcoded class check(s), %d allowed; line %s. %s" % (rel, len(hits), allowed, lines, MESSAGE))
    return out


def with_line(files, rel, line):
    return [(r, t + "\n" + line + "\n" if r == rel else t) for r, t in files]


class TheTree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = scan_files()

    def test_reads_what_it_should(self):
        rels = {rel for rel, _ in self.files}
        for rel in ALLOWED:
            self.assertIn(rel, rels, rel + " is allowed a count but the test no longer reads it")
        self.assertTrue(any(r.endswith(".lua") for r in rels) and any(r.endswith(".cpp") for r in rels))
        self.assertFalse([r for r in rels if is_skipped(r)])

    def test_allowances_are_what_the_tree_has(self):
        # The measured counts at the base. Fewer is fine (the allowance is a ceiling); this pins
        # that the scanner still finds every counted line, so a loosened rule cannot go green.
        for rel, text in self.files:
            if rel in ALLOWED:
                self.assertEqual(len(class_check_lines(rel, text)), ALLOWED[rel][0], rel)

    def test_no_new_hardcoded_class_check(self):
        self.assertEqual(violations(self.files), [], "a hardcoded class check outside src/classes/<class>/")


class Planted(unittest.TestCase):
    """The test goes red on a planted class check, with the file and line named."""

    @classmethod
    def setUpClass(cls):
        cls.files = scan_files()

    def test_cpp_constant_in_loot(self):
        files = with_line(self.files, "mod-diablocraft/src/loot/dc_loot.cpp",
                          "    if (player->getClass() == CLASS_WARRIOR) return;")
        found = violations(files)
        self.assertEqual(len(found), 1)
        self.assertIn("dc_loot.cpp", found[0])
        self.assertIn("instead", found[0])

    def test_lua_getclass_number_in_blacksmith(self):
        files = with_line(self.files, "mod-diablocraft/lua/aio/dc_blacksmith.lua", "if player:GetClass() == 1 then end")
        found = violations(files)
        self.assertEqual(len(found), 1)
        self.assertIn("dc_blacksmith.lua", found[0])

    def test_one_more_than_the_allowance_fails(self):
        files = with_line(self.files, "mod-diablocraft/src/combat/dc_combat_internal.h", "x = CLASS_PALADIN;")
        self.assertEqual(len(violations(files)), 1)

    def test_class_folder_is_free(self):
        files = self.files + [("mod-diablocraft/src/classes/monk/dc_monk.cpp", "if (p->getClass() == CLASS_MONK) {}")]
        self.assertEqual(violations(files), [])
        # but a file straight in src/classes/ is not a class folder
        files = self.files + [("mod-diablocraft/src/classes/dc_x.cpp", "if (p->getClass() == CLASS_MONK) {}")]
        self.assertEqual(len(violations(files)), 1)


class Rules(unittest.TestCase):
    """One case per rule, so a rule dropped from the test is red on its own."""

    def hits(self, rel, line):
        return class_check_lines(rel, line)

    def test_cpp_flags(self):
        for line in ("if (p->getClass() == CLASS_PRIEST)", "return t == CLASS_MAGE || t == 3;",
                     "p->getClass() != 1", "2 == p->getClass()", "case CLASS_DEATH_KNIGHT:", "x = CLASS_MONK;"):
            self.assertEqual(len(self.hits("a.cpp", line)), 1, line)

    def test_cpp_passes(self):
        for line in ("ITEM_CLASS_WEAPON", "SPELL_DAMAGE_CLASS_MAGIC", "CLASS_MAGICAL", "auto f = m.find(p->getClass());",
                     "ChrClassesEntry const* e = Lookup(player->getClass());", "// CLASS_WARRIOR in a comment",
                     "/* getClass() == 1 */", "unit->UnitClassification()"):
            self.assertEqual(self.hits("a.cpp", line), [], line)

    def test_lua_flags(self):
        for line in ("if player:GetClass() == 1 then", "if 7 ~= p:GetClass() then",
                     'Q("SELECT x FROM dc_class_map WHERE class_id = 3")', 'Q("... wow_class_id = 1")',
                     'if base.class == "monk" then', "if k ~= 'wizard' then", 'if tok == "WARRIOR" then',
                     'if "DEATHKNIGHT" == tok then'):
            self.assertEqual(len(self.hits("a.lua", line)), 1, line)

    def test_lua_passes(self):
        for line in ('Q("WHERE wow_class_id = " .. player:GetClass())', 'local row = Q("... class_id = " .. id)',
                     'class = "Barbarian",', '-- if p:GetClass() == 1', '--[[ x == "monk" ]]', 'local k = "monk"',
                     'if UnitClassification(u) == "elite" then'):
            self.assertEqual(self.hits("a.lua", line), [], line)

    def test_line_numbers_survive_block_comments(self):
        text = "--[[\n a\n b\n]]\nif p:GetClass() == 1 then end"
        self.assertEqual(class_check_lines("a.lua", text), [(5, "GetClass() against a number")])
        text = "/* a\n b */\nif (p->getClass() == CLASS_ROGUE) {}"
        self.assertEqual(class_check_lines("a.cpp", text), [(3, "class constant")])


SHARED_FOLDERS = ["combat", "items", "stats", "loot", "rifts", "monsters"]

# A class's own skill is named in src/classes/<class>/ and nowhere in the shared folders (R1, R1c).


def skill_classes(root=REPO):
    """{skill name: [class key]} from every data/d3/<class>_skills.csv."""
    names = {}
    for sheet in sorted((root / "mod-diablocraft/data/d3").glob("*_skills.csv")):
        key = sheet.name[: -len("_skills.csv")]
        with sheet.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                names.setdefault(row["skill_name"], []).append(key)
    return names


def shared_sources(root=REPO):
    """[(repo-relative path, text)] for the hand-written C++ of the shared folders; a generated header names every class's skills by design."""
    found = []
    for folder in SHARED_FOLDERS:
        for path in sorted((root / "mod-diablocraft/src" / folder).rglob("*")):
            if path.is_file() and path.suffix in {".cpp", ".h"}:
                text = path.read_text(encoding="utf-8-sig", errors="replace")
                if "Generated by" not in "\n".join(text.splitlines()[:3]):
                    found.append((path.relative_to(root).as_posix(), text))
    return found


def skill_sites(text, suffix, names):
    """[(line, skill name, class key)] for every string literal that is exactly a skill's name."""
    sites = []
    for number, line in enumerate(strip_comments(text, suffix).splitlines(), 1):
        for literal in re.findall(r'"((?:\\.|[^"\\\n])*)"', line):
            for key in names.get(literal, []):
                sites.append((number, literal, key))
    return sites


def named_in(files, names):
    """{path: [(skill name, class key)]} for every shared file that names a skill."""
    found = {}
    for rel, text in files:
        sites = skill_sites(text, Path(rel).suffix, names)
        if sites:
            found[rel] = [(skill, key) for _, skill, key in sites]
    return found


# A passive that needs code lives in its class's folder too (R1), and the engine asks the class through a seam. Every class
# sheet but the Barbarian's, whose passives have a check of their own (diablocraft-iutcl.12). An elite affix that shares a
# passive's name (Illusionist) is the affix in src/monsters/, not the passive.


def class_passives(root=REPO):
    """{passive name: [class key]} from every data/d3/<class>_passives.csv but the Barbarian's."""
    names = {}
    for sheet in sorted((root / "mod-diablocraft/data/d3").glob("*_passives.csv")):
        key = sheet.name[: -len("_passives.csv")]
        if key == "barbarian":
            continue
        with sheet.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                names.setdefault(row["passive_name"], []).append(key)
    return names


def elite_affixes(root=REPO):
    """The elite affixes' names, from data/d3/elite_affixes.csv."""
    with (root / "mod-diablocraft/data/d3/elite_affixes.csv").open(encoding="utf-8", newline="") as stream:
        return {row["affix_name"] for row in csv.DictReader(stream)}


def passives_named_in(files, names, affixes):
    """named_in for passives and skills, less an elite affix of the same name in a monster file (the Shaman's Thunderstorm skill and the
    elite affix Thunderstorm)."""
    found = {}
    for rel, sites in named_in(files, names).items():
        if rel.startswith("mod-diablocraft/src/monsters/"):
            sites = [site for site in sites if site[0] not in affixes]
        if sites:
            found[rel] = sites
    return found


class NoPassiveNamedInSharedCode(unittest.TestCase):
    """R1: a class's passive is named in its class's folder, not in the engine."""

    @classmethod
    def setUpClass(cls):
        cls.names = class_passives()
        cls.affixes = elite_affixes()
        cls.files = shared_sources()

    def test_it_reads_the_sheets(self):
        self.assertEqual(self.names["Prodigy"], ["wizard"])
        self.assertEqual(self.names["Elemental Exposure"], ["wizard"])
        self.assertEqual(self.names["Exalted Soul"], ["monk"])
        self.assertNotIn("Juggernaut", self.names)
        self.assertIn("Illusionist", self.affixes)

    def test_no_passive_is_named_in_a_shared_folder(self):
        found = {rel: sorted(set(sites)) for rel, sites in passives_named_in(self.files, self.names, self.affixes).items()}
        self.assertEqual(found, {}, "a class's passive named outside src/classes/<class>/: the engine asks the class through a seam")

    def test_a_planted_passive_is_found(self):
        planted = [(rel, text + '\nbool x = Passives::Has(p, "Exalted Soul");\n' if rel.endswith("dc_combat.cpp") else text)
                   for rel, text in self.files]
        found = passives_named_in(planted, self.names, self.affixes)
        self.assertIn(("Exalted Soul", "monk"), found["mod-diablocraft/src/combat/dc_combat.cpp"])

    def test_an_affix_of_the_same_name_is_not_a_site_only_in_a_monster_file(self):
        monster = "mod-diablocraft/src/monsters/affixes/dc_affix_planted.cpp"
        self.assertEqual(passives_named_in([(monster, 'auto a = "Illusionist";\n')], self.names, self.affixes), {})
        self.assertEqual(passives_named_in([(monster, 'auto a = "Prodigy";\n')], self.names, self.affixes),
                         {monster: [("Prodigy", "wizard")]})
        combat = "mod-diablocraft/src/combat/dc_planted.cpp"
        self.assertEqual(passives_named_in([(combat, 'auto a = "Illusionist";\n')], self.names, self.affixes),
                         {combat: [("Illusionist", "wizard")]})


class NoSkillNamedInSharedCode(unittest.TestCase):
    """R1, R1c: a skill's name appears in its class's folder, not in the engine."""

    @classmethod
    def setUpClass(cls):
        cls.names = skill_classes()
        cls.affixes = elite_affixes()
        cls.files = shared_sources()

    def test_it_reads_the_sheets_and_the_folders(self):
        self.assertTrue({"barbarian", "monk", "wizard"} <= {key for keys in self.names.values() for key in keys})
        self.assertIn("Whirlwind", self.names)
        rels = {rel for rel, _ in self.files}
        self.assertIn("mod-diablocraft/src/combat/dc_combat.cpp", rels)
        self.assertNotIn("mod-diablocraft/src/combat/dc_spell_shells.h", rels)

    def test_no_skill_is_named_in_a_shared_folder(self):
        found = {rel: sorted(set(sites)) for rel, sites in passives_named_in(self.files, self.names, self.affixes).items()}
        self.assertEqual(found, {}, "a class's skill named outside src/classes/<class>/: the engine asks the class through a hook")

    def test_an_elite_affix_of_a_skills_name_is_not_a_site_only_in_a_monster_file(self):
        self.assertEqual(self.names["Thunderstorm"], ["shaman"])
        self.assertIn("Thunderstorm", self.affixes)
        monster = "mod-diablocraft/src/monsters/affixes/dc_affix_planted.cpp"
        self.assertEqual(passives_named_in([(monster, 'auto a = "Thunderstorm";\n')], self.names, self.affixes), {})
        combat = "mod-diablocraft/src/combat/dc_planted.cpp"
        self.assertEqual(passives_named_in([(combat, 'auto a = "Thunderstorm";\n')], self.names, self.affixes),
                         {combat: [("Thunderstorm", "shaman")]})
        self.assertEqual(passives_named_in([(monster, 'auto a = "Lightning Bolt";\n')], self.names, self.affixes),
                         {monster: [("Lightning Bolt", "shaman")]})

    def test_a_planted_name_is_found(self):
        planted = [(rel, text + '\nbool x = shell.skill == "Whirlwind";\n' if rel.endswith("dc_combat.cpp") else text) for rel, text in self.files]
        found = named_in(planted, self.names)
        self.assertIn(("Whirlwind", "barbarian"), found["mod-diablocraft/src/combat/dc_combat.cpp"])

    def test_a_name_in_a_comment_or_inside_a_longer_string_is_not_a_site(self):
        text = '// "Whirlwind" in a comment\nauto s = "Whirlwind - Dust Devils";\nauto t = "Bash";\n'
        self.assertEqual(skill_sites(text, ".cpp", self.names), [(3, "Bash", "barbarian")])


# The Barbarian's passives that need code live in classes/barbarian/dc_barbarian_passives.cpp (R1); the shared folders
# name none of them. An elite affix that shares a passive's name (Juggernaut) is the affix in src/monsters/, not the passive.


def passive_names(key, root=REPO):
    """{passive name: [class key]} from data/d3/<key>_passives.csv."""
    with (root / "mod-diablocraft/data/d3" / (key + "_passives.csv")).open(encoding="utf-8", newline="") as stream:
        return {row["passive_name"]: [key] for row in csv.DictReader(stream)}


def affix_names(root=REPO):
    """The elite affixes' names, from data/d3/elite_affixes.csv."""
    with (root / "mod-diablocraft/data/d3/elite_affixes.csv").open(encoding="utf-8", newline="") as stream:
        return {row["affix_name"] for row in csv.DictReader(stream)}


def passive_sites(files, names, affixes):
    """named_in for passives, less a monster file's affix of the same name."""
    found = {}
    for rel, sites in named_in(files, names).items():
        if rel.startswith("mod-diablocraft/src/monsters/"):
            sites = [site for site in sites if site[0] not in affixes]
        if sites:
            found[rel] = sites
    return found


class NoBarbarianPassiveNamedInSharedCode(unittest.TestCase):
    """R1: a Barbarian passive's name appears in the Barbarian's folder, not in the engine."""

    @classmethod
    def setUpClass(cls):
        cls.names = passive_names("barbarian")
        cls.affixes = affix_names()
        cls.files = shared_sources()

    def test_it_reads_the_sheets(self):
        self.assertIn("Nerves of Steel", self.names)
        self.assertIn("Juggernaut", self.names)
        self.assertIn("Juggernaut", self.affixes)

    def test_no_barbarian_passive_is_named_in_a_shared_folder(self):
        found = {rel: sorted(set(sites)) for rel, sites in passive_sites(self.files, self.names, self.affixes).items()}
        self.assertEqual(found, {}, "a Barbarian passive named outside src/classes/barbarian/: the engine asks the class through a hook")

    def test_a_planted_passive_is_found(self):
        planted = [(rel, text + '\nbool x = Has(p, "Juggernaut");\n' if rel.endswith("dc_combat.cpp") else text) for rel, text in self.files]
        found = passive_sites(planted, self.names, self.affixes)
        self.assertIn(("Juggernaut", "barbarian"), found["mod-diablocraft/src/combat/dc_combat.cpp"])

    def test_an_affix_of_the_same_name_is_not_a_site_but_another_passive_is(self):
        monster = "mod-diablocraft/src/monsters/affixes/dc_affix_planted.cpp"
        files = [(monster, 'auto a = "Juggernaut";\n')]
        self.assertEqual(passive_sites(files, self.names, self.affixes), {})
        files = [(monster, 'auto a = "Nerves of Steel";\n')]
        self.assertEqual(passive_sites(files, self.names, self.affixes), {monster: [("Nerves of Steel", "barbarian")]})


if __name__ == "__main__":
    unittest.main(verbosity=2)

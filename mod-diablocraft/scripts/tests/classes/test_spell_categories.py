"""The shared cooldown: one timer for a skill and its five runes, proved on the core's own category store.

Step 6 moved the Barbarian cooldowns into the spell record and gave each skill
that has a timer a category of its own, so that casting one rune puts the base
skill and the other four on the same cooldown. The first cut had a hole. A
record's `Category` is not a number the core takes at face value: SpellInfo's
constructor resolves it,

    CategoryEntry = spellEntry->Category ? sSpellCategoryStore.LookupEntry(spellEntry->Category) : nullptr;

(SpellInfo.cpp:789 at pin 9d9b604) and `GetCategory()` answers
`CategoryEntry ? CategoryEntry->Id : 0` (:882), so an id with no row in
SpellCategory.dbc reads back as no category at all,
`Player::AddSpellAndCategoryCooldowns` never enters its
`if (cat && catrec > 0)` branch, and every rune keeps a private timer. The
stock file has 262 rows, ids 1 to 1253, and nothing at 8100. This suite is the
regression the Architect asked for on 2026-09-20: "Prove two runes of one skill
share a cooldown through the real core category store."

The rows now reach the two sides by different routes, and both are proved here.
The client reads `client-patch/dbc/SpellCategory.dbc`, which the writer emits
with all 262 stock rows preserved byte-for-byte plus one row per skill. The
server reads the stock `spellcategory_dbc` world table the migration fills,
because DBCStores.cpp:357 loads that store as
`LOAD_DBC(sSpellCategoryStore, "SpellCategory.dbc", "spellcategory_dbc")` and
the second name is a table azerothcore ships empty (2026-09-20 ruling, "Spell
rewrite step 6 category delivery"). The two artifacts have to agree, and one
test does nothing but check that and then re-run the sharing proof over the
server's rows.

Nothing here models that store. `tests/spell_categories/category_shim.h`
compiles the core's own DBC parser, index table, category multimap, SpellInfo
record reads and `AddSpellAndCategoryCooldowns`, extracted from the pin at test
time, and `tests/spell_categories/category_harness.cpp` hands it the generated
file and the generated records. The shim's header lists every stub and says
why each one is off the path. The last test mutates the extracted
`GetCategory` and the extracted sibling branch and shows the sharing proof
stops holding, so the evidence provably comes from the core's code and not
from the harness.

Two things are test-owned rather than extracted and are named here so nobody
has to go looking: `struct SpellEntry` and the shell of `class SpellInfo`,
which hold the nine columns the extracted constructor lines read. Every method
body on the path, and every line that reads a record, is the core's.

    python mod-diablocraft/scripts/tests/classes/test_spell_categories.py
"""

from __future__ import annotations

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
import harness_env
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE = REPO_ROOT / "mod-diablocraft"
SCRIPTS = MODULE / "scripts"
HARNESS = MODULE / "tests" / "spell_categories"
GENERATED = MODULE / "data" / "generated"
CORE = REPO_ROOT / "azerothcore-wotlk"
# The server's own extracted DBCs, which is where the writer takes the stock
# rows from. Read-only here, as the core is everywhere.
SERVER_DBC = CORE / "build" / "server" / "data" / "dbc" / "SpellCategory.dbc"
CLIENT_DBC = REPO_ROOT / "client-patch" / "dbc" / "SpellCategory.dbc"
CATEGORY_MAP = GENERATED / "spell_cooldown_categories.csv"
# Scratch belongs in the build tree (AGENTS.md), not the system temp; the
# fallback is for a checkout that has never been configured.
SCRATCH = CORE / "build" / "_agent-scratch" / "spell_categories"
PIN = (REPO_ROOT / "core-commit.txt").read_text(encoding="utf-8").split()[0]
PATCH = REPO_ROOT / "core-patches" / "0014-spell-modifier-d3-arithmetic.patch"

# SpellCategory.dbc is two 4-byte fields, id and flags, which is what
# SpellCategoryfmt ("ni") says and what the writer asserts before it touches
# the file.
CATEGORY_RECORD = struct.Struct("<II")
DBC_HEADER = struct.Struct("<4sIIII")


def generator():
    """generate_spells.py as a module, for the constants it owns.

    The reserved block and the flags a new row carries are the writer's
    decisions; reading them from the writer is how this suite avoids stating
    either number twice.
    """
    spec = importlib.util.spec_from_file_location("generate_spells",
                                                  SCRIPTS / "generate/classes/generate_spells.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def generated_custom_attributes():
    """{spell id: attributes} out of the generated spell_custom_attr rows.

    AttributesCu is not a DBC column; the core loads it from this table in
    SpellMgr::LoadSpellCustomAttr, and the harness sets it the same way, so
    SpellInfo::HasAttribute answers from real data on both fields it is asked
    about.
    """
    text = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    out = {}
    for line in text.splitlines():
        if not line.startswith("INSERT INTO spell_custom_attr"):
            continue
        for spell, attributes in re.findall(r"\((\d+),(\d+)\)", line):
            out[int(spell)] = int(attributes)
    return out


def overlay_sql():
    """The `spellcategory_dbc` overlay the migration carries: (first, last), {id: flags}.

    The server never sees client-patch/dbc/SpellCategory.dbc. DBCStores.cpp:357
    is `LOAD_DBC(sSpellCategoryStore, "SpellCategory.dbc", "spellcategory_dbc")`
    and the second name is a world table azerothcore ships empty
    (data/sql/base/db_world/spellcategory_dbc.sql), so the rows reach the
    server as SQL. This reads the DELETE's reserved range and the INSERT's
    rows out of the generated SQL.
    """
    text = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    deleted = re.search(r"DELETE FROM spellcategory_dbc WHERE ID BETWEEN (\d+) AND (\d+);", text)
    if not deleted:
        raise AssertionError("the generated SQL no longer clears the reserved category block")
    rows = {}
    for line in text.splitlines():
        if not line.startswith("INSERT INTO spellcategory_dbc"):
            continue
        for identifier, flags in re.findall(r"\((\d+),(\d+)\)", line):
            if int(identifier) in rows:
                raise AssertionError("category %s is inserted twice" % identifier)
            rows[int(identifier)] = int(flags)
    if not rows:
        raise AssertionError("the generated SQL inserts no category row")
    return (int(deleted[1]), int(deleted[2])), rows


def persisted_categories():
    """({skill name: category id}, {skill name: class}) out of spell_cooldown_categories.csv.

    diablocraft-wizard-records: the map holds every class's skills since the
    second class and says whose each row is in its `class` column. A file
    without the column is the Barbarian-only map it replaced. A skill name
    twice would make the name-keyed checks below silently drop one row, so it
    is refused rather than overwritten.
    """
    categories, classes = {}, {}
    with CATEGORY_MAP.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["skill"] in categories:
                raise AssertionError("%s is in the category map twice" % row["skill"])
            categories[row["skill"]] = int(row["category"])
            classes[row["skill"]] = row.get("class") or "barbarian"
    return categories, classes


def dbc_rows(path):
    """{id: the record's 8 raw bytes} for a two-field DBC, plus its header."""
    raw = path.read_bytes()
    magic, count, fields, size, strings = DBC_HEADER.unpack(raw[:DBC_HEADER.size])
    if magic != b"WDBC":
        raise AssertionError("%s is not a DBC" % path)
    rows = {}
    for index in range(count):
        start = DBC_HEADER.size + index * size
        record = raw[start:start + size]
        rows[CATEGORY_RECORD.unpack(record)[0]] = record
    return rows, (count, fields, size, strings)


def skill_of(name):
    """The base skill a record's name belongs to: "Leap - Launch" is Leap."""
    return name.split(" - ", 1)[0]


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
    read-only here, as it is everywhere. The cooldown functions this suite
    extracts are untouched by the patch, but ApplySpellMod is not, and the
    modifier test needs the arithmetic the server actually runs.
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


# The loop in DBCStores.cpp that turns a category id into "these spells". It is
# the only thing that makes the sibling branch find anything, so it is taken
# out whole and asserted to still be there.
SPELLS_BY_CATEGORY_LOOP = """    for (auto i : sSpellStore)
        if (i->Category)
            sSpellsByCategoryStore[i->Category].emplace(false, i->Id);
"""


def extract(into, mutate=None):
    """Write every piece of the core the shim includes, out of the pin.

    `mutate` is {file: (before, after)} and is how the last test shows the
    proof rests on the extracted code: change a line of the core here and the
    sharing stops.
    """
    mutate = mutate or {}
    into.mkdir(parents=True, exist_ok=True)
    (into / "Utilities").mkdir(exist_ok=True)

    def put(name, text):
        if name in mutate:
            before, after = mutate[name]
            if before not in text:
                raise AssertionError("the mutation target %r is not in %s" % (before, name))
            text = text.replace(before, after)
        (into / name).write_text(text, encoding="utf-8")

    # The core files' own include lines, resolved to the shim without a single
    # one of them being edited. Everything is one translation unit.
    for header in ("Define.h", "Errors.h", "Common.h", "Utilities/ByteConverter.h"):
        (into / header).write_text('#include "category_shim.h"\n', encoding="utf-8")

    # The parser and the index table, whole files.
    put("DBCFileLoader.h", at_pin("src/common/DataStores/DBCFileLoader.h"))
    put("DBCFileLoader.cpp", at_pin("src/common/DataStores/DBCFileLoader.cpp"))
    put("DBCStorageIterator.h", at_pin("src/server/shared/DataStores/DBCStorageIterator.h"))
    put("DBCStore.h", at_pin("src/server/shared/DataStores/DBCStore.h"))

    store = at_pin("src/server/shared/DataStores/DBCStore.cpp")
    put("dbc_store_base.inc",
        block(store, "DBCStorageBase::DBCStorageBase(char const* fmt)", "DBCStorageBase's constructor")
        + "\n" + block(store, "DBCStorageBase::~DBCStorageBase()", "DBCStorageBase's destructor")
        + "\n" + block(store, "bool DBCStorageBase::Load(char const* path, char**& indexTable)",
                       "DBCStorageBase::Load"))

    structure = at_pin("src/server/shared/DataStores/DBCStructure.h")
    put("dbc_structure.inc",
        lines_matching(structure, r"typedef std::set<std::pair<bool, uint32>> SpellCategorySet;",
                       "SpellCategorySet")
        + lines_matching(structure, r"typedef std::unordered_map<uint32, SpellCategorySet> SpellCategoryStore;",
                         "SpellCategoryStore")
        + "\n" + block(structure, "struct SpellCategoryEntry", "SpellCategoryEntry"))

    put("dbc_fmt.inc",
        lines_matching(at_pin("src/server/shared/DataStores/DBCfmt.h"),
                       r"^char constexpr SpellCategoryfmt\[\]", "SpellCategoryfmt"))

    stores = at_pin("src/server/game/DataStores/DBCStores.cpp")
    if SPELLS_BY_CATEGORY_LOOP not in stores:
        raise AssertionError("the core pin no longer fills sSpellsByCategoryStore that way")
    put("dbc_stores.inc",
        "// DBCStores.cpp at the pin: the two stores the proof turns on.\n"
        + lines_matching(stores, r"^SpellCategoryStore sSpellsByCategoryStore;", "sSpellsByCategoryStore")
        + lines_matching(stores, r"^DBCStorage <SpellCategoryEntry> sSpellCategoryStore", "sSpellCategoryStore")
        + "\n"
        + "// Test-owned: the spell store, filled with the core's own SetEntry\n"
        + "// rather than loaded from a 49 MB Spell.dbc, so the format is never read.\n"
        + 'DBCStorage <SpellEntry> sSpellStore("");\n'
        + "\n"
        + "// DBCStores.cpp, the loop that makes a category mean \"these spells\",\n"
        + "// run after the spell store is filled.\n"
        + "inline void BuildSpellsByCategory()\n{\n" + SPELLS_BY_CATEGORY_LOOP + "}\n")

    shared = at_pin("src/server/shared/SharedDefines.h")
    spell_info_h = at_pin("src/server/game/Spells/SpellInfo.h")
    unit = at_pin("src/server/game/Entities/Unit/Unit.h")
    put("spell_constants.inc",
        lines_matching(at_pin("src/common/Common.h"), r"^constexpr auto IN_MILLISECONDS",
                       "IN_MILLISECONDS")
        + lines_matching(at_pin("src/server/game/Entities/Item/Item.h"),
                         r"^#define MAX_ITEM_SPELLS ", "MAX_ITEM_SPELLS")
        + lines_matching(at_pin("src/server/game/ArenaSpectator/ArenaSpectator.h"),
                         r"^#define SPECTATOR_COOLDOWN_(MIN|MAX) ", "the spectator window", count=2)
        + lines_matching(unit, r"^static constexpr uint32 infinityCooldownDelay",
                         "infinityCooldownDelay")
        + lines_matching(unit, r"^typedef std::unordered_map<uint32, uint32> PacketCooldowns;",
                         "PacketCooldowns")
        + "\n" + block(unit, "enum WeaponAttackType : uint8", "WeaponAttackType")
        + "\n" + block(unit, "enum SpellCooldownFlags", "SpellCooldownFlags")
        + "\n" + block(shared, "enum SpellAttr0 : uint32", "SpellAttr0")
        + "\n" + block(shared, "enum SpellAttr2 : uint32", "SpellAttr2")
        + "\n" + block(shared, "enum SpellAttr6 : uint32", "SpellAttr6")
        + "\n" + block(spell_info_h, "enum SpellCustomAttributes", "SpellCustomAttributes")
        + "\n" + block(at_pin("src/server/shared/DataStores/DBCEnums.h"),
                       "enum SpellCategoryFlags", "SpellCategoryFlags")
        # AuraType is 400 enumerators of which the path names exactly one, so
        # only that one is taken; GetTotalAuraModifier is a stub and the shim
        # header says why.
        + "\nenum AuraType\n{\n"
        + lines_matching(at_pin("src/server/game/Spells/Auras/SpellAuraDefines.h"),
                         r"^    SPELL_AURA_MOD_COOLDOWN ", "SPELL_AURA_MOD_COOLDOWN")
        + "};\n")

    spell_info = at_pin("src/server/game/Spells/SpellInfo.cpp")
    # The record reads this whole proof turns on, the CategoryEntry line first.
    fields = ["CategoryEntry", "Id", "Attributes", "AttributesEx2", "AttributesEx6",
              "RecoveryTime", "CategoryRecoveryTime", "SpellFamilyName"]
    constructor = block(spell_info, "SpellInfo::SpellInfo(SpellEntry const* spellEntry)",
                        "SpellInfo's constructor")
    put("spell_info_fields.inc",
        "".join(lines_matching(constructor, r"^    %s = spellEntry->" % field, field)
                for field in fields))
    put("spell_info_methods.inc",
        block(spell_info, "uint32 SpellInfo::GetCategory() const", "SpellInfo::GetCategory")
        + "\n" + block(spell_info, "bool SpellInfo::IsCooldownStartedOnEvent() const",
                       "SpellInfo::IsCooldownStartedOnEvent")
        + "\n" + block(spell_info, "bool SpellInfo::IsAutoRepeatRangedSpell() const",
                       "SpellInfo::IsAutoRepeatRangedSpell"))

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
    put("spell_cooldown_types.inc",
        block(player_h, "struct SpellCooldown", "SpellCooldown")
        + lines_matching(player_h, r"^typedef std::map<uint32, SpellCooldown> SpellCooldowns;",
                         "SpellCooldowns"))
    put("spell_mod_enums.inc",
        block(at_pin("src/server/game/Spells/SpellDefines.h"), "enum SpellModOp", "SpellModOp")
        + "\n" + lines_matching(at_pin("src/server/game/Spells/SpellDefines.h"),
                                r"^#define MAX_SPELLMOD ", "MAX_SPELLMOD")
        + "\n" + block(player_h, "enum SpellModType", "SpellModType")
        + "\n" + block(player_h, "struct SpellModifier", "SpellModifier"))
    put("calculate_pct.inc",
        block(at_pin("src/common/Utilities/Util.h"),
              "template <class T, class U>\ninline T CalculatePct(", "CalculatePct"))

    player = player_cpp(into / "tree")
    put("apply_spell_mod.inc",
        block(player, "template <class T>\nvoid Player::ApplySpellMod(", "Player::ApplySpellMod"))
    put("player_cooldowns.inc",
        block(player, "void Player::AddSpellAndCategoryCooldowns(",
              "Player::AddSpellAndCategoryCooldowns")
        + "\n" + block(player, "void Player::_AddSpellCooldown(", "Player::_AddSpellCooldown"))


class SpellCategoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("c++") or shutil.which("g++")
        if not cls.compiler:
            raise unittest.SkipTest("no C++ compiler")
        if not SERVER_DBC.exists():
            raise unittest.SkipTest("the server's DBCs are not extracted")
        if not CLIENT_DBC.exists() or not CATEGORY_MAP.exists():
            raise unittest.SkipTest("generate_spells.py has not written the category files")
        cls.writer = generator()
        cls.records = generated_records()
        cls.custom = generated_custom_attributes()
        cls.persisted, cls.persisted_class = persisted_categories()
        cls.overlay_range, cls.overlay = overlay_sql()
        # Every category the records actually use, and the six records filed
        # under each of them.
        cls.by_category = {}
        for spell, row in sorted(cls.records.items()):
            category = int(row["Category"])
            if category:
                cls.by_category.setdefault(category, []).append(spell)
        # A name is not unique across the generated records: a skill's aura and
        # companion shells carry the same Name_Lang_enUS as the skill shell.
        # Only the shell that carries the category owns the timer, so that is
        # the one a test means when it names a skill or a rune.
        cls.by_name = {}
        for spells in cls.by_category.values():
            for spell in spells:
                name = cls.records[spell]["Name_Lang_enUS"]
                if name in cls.by_name:
                    raise AssertionError("two categorised records are both called %r" % name)
                cls.by_name[name] = spell
        # The first id of the reserved block the writer has not used: a
        # category the core can never resolve, which is exactly the bug.
        cls.unused_category = next(
            identifier for identifier
            in range(cls.writer.COOLDOWN_CATEGORY_FIRST, cls.writer.COOLDOWN_CATEGORY_LAST + 1)
            if identifier not in cls.by_category)
        try:
            SCRATCH.mkdir(parents=True, exist_ok=True)
            cls.work = Path(tempfile.mkdtemp(prefix="run-", dir=str(SCRATCH)))
        except OSError:
            cls.work = Path(tempfile.mkdtemp(prefix="dc-spell-categories-"))
        cls.binaries = {}
        cls.records_file = cls.work / "records.tsv"
        cls.records_file.write_text(cls.records_tsv(), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    @classmethod
    def records_tsv(cls):
        """Every generated record, plus the two controls the bug needs.

        The controls are a base and a rune that carry the reserved category the
        writer left unused, so SpellCategory.dbc has no row for it. They are
        otherwise an ordinary pair: same family, same cooldown as Ground Stomp,
        the same custom attribute. The only difference is the missing row.
        """
        lines = []
        for spell, row in sorted(cls.records.items()):
            lines.append("\t".join(str(cell) for cell in (
                spell, row["Category"], row["RecoveryTime"], row["CategoryRecoveryTime"],
                row["SpellClassSet"], row["Attributes"], row["AttributesEx2"],
                row["AttributesEx6"], cls.custom.get(spell, 0))))
        template = cls.records[cls.by_name["Ground Stomp"]]
        cls.control_base = max(cls.records) + 1
        cls.control_rune = max(cls.records) + 2
        for spell in (cls.control_base, cls.control_rune):
            lines.append("\t".join(str(cell) for cell in (
                spell, cls.unused_category, template["RecoveryTime"],
                template["CategoryRecoveryTime"], template["SpellClassSet"],
                template["Attributes"], template["AttributesEx2"], template["AttributesEx6"],
                cls.custom[cls.by_name["Ground Stomp"]])))
        return "\n".join(lines) + "\n"

    def build(self, name="pinned", mutate=None):
        """Compile the harness against the core code extracted from the pin."""
        if name in self.binaries:
            return self.binaries[name]
        into = self.work / name
        extract(into, mutate)
        binary = into / "harness"
        binary = harness_env.build([HARNESS / "category_harness.cpp"], flags=["-std=c++17", "-O0"], includes=[into, HARNESS])
        self.binaries[name] = binary
        return binary

    def drive(self, cases, name="pinned", mutate=None, dbc=None, overlay=None):
        """Run the harness over `cases`, returning one answer line per case.

        `dbc` is the SpellCategory.dbc the store loads, the generated
        client-patch file unless a test says otherwise, and `overlay` is the
        {id: flags} the world table lays over it afterwards.
        """
        binary = self.build(name, mutate)
        label = name if overlay is None else "%s-overlay" % name
        cases_file = self.work / ("cases-%s.tsv" % label)
        cases_file.write_text(
            "\n".join("\t".join(str(cell) for cell in case) for case in cases) + "\n",
            encoding="utf-8")
        command = [str(binary), str(dbc or CLIENT_DBC), str(self.records_file), str(cases_file)]
        if overlay is not None:
            overlay_file = self.work / ("overlay-%s.tsv" % label)
            overlay_file.write_text(
                "".join("%d\t%d\n" % row for row in sorted(overlay.items())), encoding="utf-8")
            command.append(str(overlay_file))
        run = harness_env.run(command, capture_output=True, text=True)
        if run.returncode:
            raise AssertionError("the harness did not run:\n" + run.stderr[-4000:])
        answers = run.stdout.splitlines()
        self.assertEqual(len(answers), len(cases), "the harness answered a different count")
        return answers

    def cast(self, spell, flat=0, percent=0, name="pinned", mutate=None, dbc=None, overlay=None):
        """{spell id: (remaining ms, maxduration, category)} after one cast."""
        answer = self.drive([("cast", spell, flat, percent)], name=name, mutate=mutate,
                            dbc=dbc, overlay=overlay)[0]
        if answer == "-":
            return {}
        held = {}
        for cell in answer.split(" "):
            identifier, remaining, maximum, category = (int(part) for part in cell.split(":"))
            held[identifier] = (remaining, maximum, category)
        return held

    def family(self, skill):
        """The base record and its runes, by id, for one skill's name."""
        return sorted(spell for spell, row in self.records.items()
                      if skill_of(row["Name_Lang_enUS"]) == skill and int(row["Category"]))

    def caster(self, skill):
        """The record a whole-file check casts to start one skill's timer.

        Every Barbarian skill with a timer has it on the base skill, and that
        is still what is cast: a Barbarian base that lost its category fails
        here as a KeyError, exactly as before. diablocraft-wizard-records: a
        Wizard skill may have a timer only on one rune - D3 gives Meteor's
        Molten Impact and Wave of Force's Impactful Wave a cooldown the base
        skill does not have - so for another class the lowest categorised
        record of the skill is cast instead.
        """
        if self.persisted_class[skill] == "barbarian":
            return self.by_name[skill]
        return self.family(skill)[0]

    # --- (a) the category has to exist before it means anything ------------

    def test_every_category_the_records_use_resolves_through_the_real_store(self):
        """GetCategory() gives the id back, and an unused id in the block gives 0.

        This is the shape of the bug. `sSpellCategoryStore` is the core's own
        `DBCStorage<SpellCategoryEntry>` loaded from the generated
        client-patch file by the core's own parser, and `GetCategory()` is the
        extracted `CategoryEntry ? CategoryEntry->Id : 0`. A row that is there
        answers with its id; the reserved id the writer never used answers 0,
        because `LookupEntry` gives nullptr and the constructor stores nullptr.
        """
        categories = sorted(self.by_category)
        self.assertTrue(categories, "the generated records carry no category at all")
        cases = [("lookup", category) for category in categories]
        cases += [("category", self.by_category[category][0]) for category in categories]
        cases += [("lookup", self.unused_category), ("category", self.control_base)]
        answers = self.drive(cases)
        for index, category in enumerate(categories):
            found, flags = (int(cell) for cell in answers[index].split(" "))
            self.assertEqual(found, 1, "category %d has no SpellCategory.dbc row" % category)
            self.assertEqual(flags, self.writer.COOLDOWN_CATEGORY_FLAGS,
                             "category %d does not carry the writer's flags" % category)
            self.assertEqual(int(answers[len(categories) + index]), category,
                             "GetCategory() lost category %d" % category)
        self.assertEqual(answers[-2], "0 0", "the control id has a row after all")
        self.assertEqual(int(answers[-1]), 0,
                         "a category with no DBC row did not read back as no category")

    def test_a_category_with_no_dbc_row_installs_no_shared_timer(self):
        """The regression itself: the hole the PM found, reproduced and fenced.

        The two control records are an ordinary base-and-rune pair carrying a
        reserved category the writer never wrote a row for - which is exactly
        what every skill looked like before the writer emitted
        SpellCategory.dbc. Casting one leaves the other free, and the caster's
        own cooldown is filed under category 0, which is
        `AddSpellAndCategoryCooldowns` taking its "self spell cooldown" branch.
        The next test is the same cast on a category that does have a row.
        """
        held = self.cast(self.control_base)
        self.assertEqual(sorted(held), [self.control_base],
                         "a category with no DBC row still shared a timer")
        self.assertEqual(held[self.control_base][2], 0,
                         "the cast went through the category branch after all")
        self.assertNotIn(self.control_rune, held)

    # --- (b) the ruling's case ---------------------------------------------

    def test_casting_ground_stomp_puts_every_rune_on_the_same_cooldown(self):
        """The base skill, cast, and all five runes come back on cooldown.

        Ground Stomp is the case the ruling names. Its CategoryRecoveryTime is
        what every sibling gets, and Deafening Crash's own shorter 8000 ms does
        not change what the other five are given: a sibling is put on the
        *caster's* catrecTime, not on its own record's number. Every id here
        is read out of the generated spell_shells.sql, not typed.
        """
        family = self.family("Ground Stomp")
        base = self.by_name["Ground Stomp"]
        catrec = int(self.records[base]["CategoryRecoveryTime"])
        self.assertEqual(len(family), 6, "Ground Stomp is not a base and five runes")
        held = self.cast(base)
        self.assertEqual(sorted(held), family, "casting the base did not reach every rune")
        for spell, (remaining, maximum, category) in held.items():
            self.assertEqual(remaining, catrec,
                             "%s is not on the caster's cooldown" % self.records[spell]["Name_Lang_enUS"])
            self.assertEqual(maximum, catrec)
            # The caster's own row is filed under 0, the siblings under the
            # skill's category: that is the two _AddSpellCooldown calls.
            self.assertEqual(category, 0 if spell == base else self.persisted["Ground Stomp"])

    def test_casting_a_rune_puts_the_base_skill_and_the_other_runes_on_cooldown(self):
        """The other direction, and the one rune that carries its own number.

        Deafening Crash's record says 8000 ms where the rest of the family says
        12000. Casting it puts the whole family on 8000, because catrec is the
        caster's; casting any other rune puts Deafening Crash on 12000 for the
        same reason. That is one shared timer with the cast record's length,
        which is what a D3 rune does.
        """
        family = self.family("Ground Stomp")
        base = self.by_name["Ground Stomp"]
        short = self.by_name["Ground Stomp - Deafening Crash"]
        plain = self.by_name["Ground Stomp - Trembling Stomp"]
        short_catrec = int(self.records[short]["CategoryRecoveryTime"])
        plain_catrec = int(self.records[plain]["CategoryRecoveryTime"])
        self.assertLess(short_catrec, plain_catrec,
                        "Deafening Crash no longer carries a shorter cooldown")

        held = self.cast(short)
        self.assertEqual(sorted(held), family, "casting a rune did not reach the base skill")
        self.assertIn(base, held, "the base skill kept a timer of its own")
        for spell, (remaining, _maximum, _category) in held.items():
            self.assertEqual(remaining, short_catrec,
                             "%s did not take the cast rune's 8000 ms"
                             % self.records[spell]["Name_Lang_enUS"])

        held = self.cast(plain)
        self.assertEqual(sorted(held), family)
        self.assertEqual(held[short][0], plain_catrec,
                         "Deafening Crash kept its own 8000 ms when another rune was cast")

    def test_a_second_skill_shares_its_timer_the_same_way_both_ways(self):
        """Earthquake, whose rune The Mountain's Call halves the 60 seconds.

        A second skill, so the proof is not one lucky category: the same two
        directions, the same shared number, on a different record set and a
        different timer.
        """
        family = self.family("Earthquake")
        base = self.by_name["Earthquake"]
        short = self.by_name["Earthquake - The Mountain's Call"]
        base_catrec = int(self.records[base]["CategoryRecoveryTime"])
        short_catrec = int(self.records[short]["CategoryRecoveryTime"])
        self.assertLess(short_catrec, base_catrec)

        from_base = self.cast(base)
        self.assertEqual(sorted(from_base), family, "casting Earthquake did not reach its runes")
        self.assertEqual({remaining for remaining, _m, _c in from_base.values()}, {base_catrec})

        from_rune = self.cast(short)
        self.assertEqual(sorted(from_rune), family,
                         "casting The Mountain's Call did not reach Earthquake")
        self.assertEqual({remaining for remaining, _m, _c in from_rune.values()}, {short_catrec})

    # --- (c) and nowhere else ----------------------------------------------

    def test_a_skills_cooldown_stays_inside_its_own_category(self):
        """One cast, and every record of every other skill is still free.

        The sibling loop walks `sSpellsByCategoryStore[cat]`, so a leak would
        mean two skills sharing a category id. This casts the base of every
        skill that has a timer and checks the answer is exactly that skill's
        six records - no more, and never a record belonging to another skill.
        """
        families = {skill: self.family(skill) for skill in self.persisted}
        for skill, family in sorted(families.items()):
            base = self.caster(skill)
            held = sorted(self.cast(base))
            self.assertEqual(held, family, "casting %s did not stop at its own records" % skill)
            for other, other_family in families.items():
                if other == skill:
                    continue
                self.assertFalse(set(held) & set(other_family),
                                 "casting %s reached %s" % (skill, other))

    def test_the_records_that_carry_no_category_never_join_a_shared_timer(self):
        """The companion, aura and passive records sit at Category 0.

        315 of the 381 generated records carry no category: the primaries, the
        runes of skills with no cooldown, and the passive and companion shells.
        None of them may appear in a shared timer, and the extracted
        DBCStores.cpp loop is what keeps them out - it files a record only
        `if (i->Category)`.
        """
        uncategorised = {spell for spell, row in self.records.items()
                         if not int(row["Category"])}
        self.assertTrue(uncategorised, "every generated record carries a category")
        reached = set()
        for skill in sorted(self.persisted):
            reached |= set(self.cast(self.caster(skill)))
        self.assertFalse(reached & uncategorised,
                         "a record with no category was put on a shared timer")
        # And casting one of them installs at most its own timer, never a
        # sibling's.
        for spell in sorted(uncategorised)[:8]:
            held = self.cast(spell)
            self.assertLessEqual(set(held), {spell},
                                 "%s shared a timer with something"
                                 % self.records[spell]["Name_Lang_enUS"])

    # --- (d) a skill whose only timer is the category one -------------------

    def test_furious_charge_shares_a_recharge_it_has_no_cooldown_of_its_own_for(self):
        """RecoveryTime 0, CategoryRecoveryTime 10000, and still one timer.

        Furious Charge's charges recharge; the record has no cooldown of its
        own at all. That makes it the case where `rec` is 0 and only `catrec`
        carries a number, so `recTime = rec ? rec : catrecTime` is what puts
        the cast record itself on the clock. If the category did not resolve,
        this skill would have no timer whatsoever.
        """
        family = self.family("Furious Charge")
        base = self.by_name["Furious Charge"]
        rune = self.by_name["Furious Charge - Cold Rush"]
        self.assertEqual(int(self.records[base]["RecoveryTime"]), 0,
                         "Furious Charge has taken on a cooldown of its own")
        recharge = int(self.records[base]["CategoryRecoveryTime"])
        for cast in (base, rune):
            held = self.cast(cast)
            self.assertEqual(sorted(held), family,
                             "%s did not share its recharge"
                             % self.records[cast]["Name_Lang_enUS"])
            self.assertEqual({remaining for remaining, _m, _c in held.values()}, {recharge})

    # --- (e) the modifiers still land on this path --------------------------

    def test_the_cooldown_modifiers_apply_on_this_path_and_not_only_in_isolation(self):
        """Wrath of the Berserker: 120s, -30s flat, 40% off, and 54s shared.

        core-patches/0014 makes a flat cooldown reduction land before the
        percentage, as D3 does: Boon of Bul-Kathos takes 30 seconds off the
        120 and 40% then leaves 54, not the 42 the core's own order gives.
        tests/cost_math proves that of `ApplySpellMod` on its own. What this
        proves is that `AddSpellAndCategoryCooldowns` runs it on both `rec` and
        `catrec`, so the whole rune family ends up on the reduced timer and not
        on the record's raw number.
        """
        family = self.family("Wrath of the Berserker")
        base = self.by_name["Wrath of the Berserker"]
        catrec = int(self.records[base]["CategoryRecoveryTime"])
        flat, percent = -30000, -40      # the passive's 30 seconds, then 40% CDR
        expected = round((catrec + flat) * (1 + percent / 100))
        self.assertEqual((catrec, expected), (120000, 54000),
                         "the record or the arithmetic moved; 0014's header states these")
        held = self.cast(base, flat=flat, percent=percent)
        self.assertEqual(sorted(held), family, "the modified cast did not reach the runes")
        for spell, (remaining, maximum, _category) in held.items():
            self.assertEqual(remaining, expected,
                             "%s is not on the reduced cooldown"
                             % self.records[spell]["Name_Lang_enUS"])
            self.assertEqual(maximum, expected)
        # And with no modifier the same cast gives the record's own number, so
        # the 54000 above is the modifier's doing and not the record's.
        self.assertEqual({remaining for remaining, _m, _c in self.cast(base).values()}, {catrec})

    # --- (f) the file the client and the server are handed ------------------

    def test_the_generated_dbc_keeps_every_stock_row_byte_for_byte(self):
        """262 stock rows unchanged, and only the reserved block added.

        The client reads this file for every spell in the game, so anything
        the writer disturbs is a bug somewhere else entirely. Every stock
        record is compared as raw bytes against the server's own extracted
        copy, which is where the writer takes them from, and every id the
        generated file adds has to sit inside the writer's reserved block.
        """
        stock, stock_header = dbc_rows(SERVER_DBC)
        ours, our_header = dbc_rows(CLIENT_DBC)
        self.assertEqual(stock_header[1:], our_header[1:],
                         "the generated file changed the DBC record layout")
        self.assertEqual(len(stock), stock_header[0], "the stock file has a duplicate id")
        self.assertEqual(len(ours), our_header[0], "the generated file has a duplicate id")
        for identifier, record in stock.items():
            self.assertIn(identifier, ours, "stock category %d was dropped" % identifier)
            self.assertEqual(ours[identifier], record,
                             "stock category %d was rewritten" % identifier)
        added = sorted(set(ours) - set(stock))
        self.assertEqual(added, sorted(self.by_category),
                         "the generated file adds rows the records do not use")
        # diablocraft-wizard-records: each class reserves its own category
        # block in CLASS_BLOCKS, so an added id has to sit in the block of the
        # class the persisted map files its skill under. The Barbarian's ids
        # are still held to 8100-8199, the writer's own constants.
        for identifier in added:
            owner = self.writer.block_for_category(identifier)
            self.assertIsNotNone(owner, "category %d is outside every reserved block" % identifier)
            skills = [skill for skill, category in self.persisted.items() if category == identifier]
            self.assertEqual([self.persisted_class[skill] for skill in skills], [owner.stem],
                             "category %d sits in the %s block but is not one %s skill's"
                             % (identifier, owner.stem, owner.stem))
            if owner.stem == "barbarian":
                self.assertTrue(self.writer.COOLDOWN_CATEGORY_FIRST <= identifier
                                <= self.writer.COOLDOWN_CATEGORY_LAST,
                                "category %d is outside the reserved block" % identifier)
        self.assertEqual(len(ours), len(stock) + len(added),
                         "the generated file lost or doubled a row")
        # And the core's own index table agrees about how big the file is:
        # AutoProduceData sizes it by the highest id it read.
        self.assertEqual(int(self.drive([("rows",)])[0]), max(ours) + 1,
                         "the core's index table does not span the generated ids")

    def test_the_server_gets_the_same_rows_through_the_world_table_overlay(self):
        """The SQL overlay matches the file, and the sharing holds on its rows.

        The server never reads client-patch/dbc/SpellCategory.dbc. DBCStores.cpp
        loads that store as
        `LOAD_DBC(sSpellCategoryStore, "SpellCategory.dbc", "spellcategory_dbc")`,
        and the second name is a stock world table, so the eleven rows reach
        the server as the DELETE and INSERT the migration carries while the
        client keeps reading the file. Two artifacts, one set of rows, and this
        checks they cannot drift: same ids, same Flags, and a DELETE that
        clears the whole reserved block so a rerun replaces rather than adds.

        WHAT IS EXECUTED here: the core's `DBCStorage<SpellCategoryEntry>`
        loaded by the core's own parser from the *stock* server file, which has
        no row in the reserved block at all; the overlay's rows installed into
        that store through the core's own `DBCStorage::SetEntry` (DBCStore.h at
        the pin); and then the whole proof again - SpellInfo's constructor,
        GetCategory, the DBCStores.cpp category loop and
        AddSpellAndCategoryCooldowns - over the rows the server will hold. The
        control run is the same stock file with no overlay, and it does not
        share, so the sharing is the overlay's doing.

        WHAT IS ONLY READ, and not run: `DBCDatabaseLoader::Load`, which is how
        the server puts those rows into the store. Extracting it would drag in
        QueryResult, Field, WorldDatabase and Acore::StringFormat for no gain,
        so this states its merge semantics from the pin instead
        (src/server/shared/DataStores/DBCDatabaseLoader.cpp):

            std::string query = Acore::StringFormat("SELECT * FROM `{}` ORDER BY `ID` DESC", _sqlTableName);
            uint32 indexTableSize = std::max(records, (*result)[_sqlIndexPos].Get<uint32>() + 1);
            ...
            indexTable[newIndexes[i]] = &dataTable[i * _recordSize];

        - the index table is grown to cover the highest id in the table and
        each row is written into its own id's slot, on top of whatever the file
        left there. SetEntry reaches the same index table the same way, which
        is why it stands in for it; what this test does NOT prove is that the
        SQL column names and order match `SpellCategoryfmt`, because no
        database is involved.
        """
        first, last = self.overlay_range
        # diablocraft-wizard-records: the one DELETE now spans every class's
        # category block, first to last, and the Barbarian's block is still
        # inside it whole.
        blocks = [block.categories for block in self.writer.CLASS_BLOCKS.values()]
        self.assertEqual((first, last), (min(block[0] for block in blocks),
                                         max(block[1] for block in blocks)),
                         "the DELETE does not clear exactly the classes' reserved blocks")
        self.assertTrue(first <= self.writer.COOLDOWN_CATEGORY_FIRST
                        and self.writer.COOLDOWN_CATEGORY_LAST <= last,
                        "the DELETE does not clear the whole reserved block")
        for identifier in self.overlay:
            self.assertTrue(first <= identifier <= last,
                            "the overlay inserts %d outside the range it cleared" % identifier)

        stock, _header = dbc_rows(SERVER_DBC)
        ours, _header = dbc_rows(CLIENT_DBC)
        added = {identifier: CATEGORY_RECORD.unpack(ours[identifier])[1]
                 for identifier in sorted(set(ours) - set(stock))}
        self.assertEqual(self.overlay, added,
                         "the SQL overlay and the generated DBC carry different rows")
        self.assertEqual(set(self.overlay.values()), {self.writer.COOLDOWN_CATEGORY_FLAGS},
                         "an overlay row does not carry the writer's flags")
        self.assertEqual(sorted(self.overlay), sorted(self.by_category),
                         "the overlay does not cover exactly the categories the records use")

        # The server's file, as shipped, knows nothing about the block...
        family = self.family("Ground Stomp")
        base = self.by_name["Ground Stomp"]
        catrec = int(self.records[base]["CategoryRecoveryTime"])
        self.assertNotIn(self.persisted["Ground Stomp"], stock,
                         "the stock file already has a row in the reserved block")
        bare = self.cast(base, dbc=SERVER_DBC, overlay={})
        self.assertEqual(sorted(bare), [base],
                         "the stock file shared a timer it has no row for")

        # ...and with the world table's rows laid over it, it shares.
        held = self.cast(base, dbc=SERVER_DBC, overlay=self.overlay)
        self.assertEqual(sorted(held), family,
                         "the overlay's rows did not give the runes a shared timer")
        for spell, (remaining, maximum, _category) in held.items():
            self.assertEqual((remaining, maximum), (catrec, catrec),
                             "%s is not on the caster's cooldown"
                             % self.records[spell]["Name_Lang_enUS"])

    def test_the_persisted_map_agrees_with_the_records_and_doubles_nothing(self):
        """spell_cooldown_categories.csv is what the records actually carry.

        The map is what the rest of the pipeline reads instead of parsing the
        SQL, so it has to say the same thing: one category per skill, one skill
        per category, and exactly the set the records use. The sibling loop
        cannot tell two skills apart if they share an id, which is why the
        both-ways uniqueness is asserted and not assumed.
        """
        from_records = {}
        for category, spells in self.by_category.items():
            skills = {skill_of(self.records[spell]["Name_Lang_enUS"]) for spell in spells}
            self.assertEqual(len(skills), 1,
                             "category %d covers more than one skill: %s" % (category, skills))
            from_records[skills.pop()] = category
        self.assertEqual(self.persisted, from_records,
                         "the persisted map and the records disagree")
        self.assertEqual(len(set(self.persisted.values())), len(self.persisted),
                         "two skills were given the same category id")
        # diablocraft-wizard-records: and each skill's id sits in the block
        # its own class reserves, as the map's `class` column says.
        for skill, category in sorted(self.persisted.items()):
            owner = self.writer.block_for_category(category)
            self.assertEqual(owner.stem if owner else None, self.persisted_class[skill],
                             "%s's category %d is not in its class's block" % (skill, category))
        # And the multimap the core builds out of the records files exactly the
        # six shells of each skill under its id.
        answers = self.drive([("siblings", self.persisted[skill])
                              for skill in sorted(self.persisted)])
        for skill, answer in zip(sorted(self.persisted), answers):
            self.assertEqual([int(cell) for cell in answer.split(" ")], self.family(skill),
                             "sSpellsByCategoryStore does not hold %s's six records" % skill)

    # --- (g) and the evidence is the extracted code -------------------------

    def test_the_evidence_is_the_extracted_category_code(self):
        """Mutate the core's own lines and the sharing above stops holding.

        The point of extracting rather than modelling. The first mutation is
        `GetCategory`, the line that made the bug: make it answer 0 and the
        cast falls back to a private timer. The second is the sibling branch
        in `AddSpellAndCategoryCooldowns`: close it and the runes are never
        reached even though the category resolves. Either way the proof fails,
        so the proof is coming from the core's code and not from the harness.
        """
        family = self.family("Ground Stomp")
        base = self.by_name["Ground Stomp"]
        self.assertEqual(sorted(self.cast(base)), family, "the unmutated cast already fails")

        blind = self.cast(base, name="mutated-getcategory", mutate={
            "spell_info_methods.inc": ("return CategoryEntry ? CategoryEntry->Id : 0;",
                                       "return 0;")})
        self.assertEqual(sorted(blind), [base],
                         "the sharing proof does not come from the extracted GetCategory")

        closed = self.cast(base, name="mutated-branch", mutate={
            "player_cooldowns.inc": ("    if (cat && catrec > 0)",
                                     "    if (false && cat && catrec > 0)")})
        self.assertEqual(sorted(closed), [base],
                         "the sharing proof does not come from the extracted sibling branch")


if __name__ == "__main__":
    unittest.main(verbosity=2)

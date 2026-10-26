"""The spell records hold exactly the numbers the values sheets name.

Step 1 of the spell rewrite writes every named number of the 157 barbarian
rows into the spell record and points the sentence at it with WoW's own
token. This checker does not trust the generator's own bookkeeping: it
re-derives, from the sheets and the value map, what every field of every
record must be, and compares that against the published SQL. Everything
the sheets do not own must equal the committed baseline byte for byte.

    python mod-diablocraft/scripts/tests/classes/test_spell_records.py

Baseline: 7702de8, the commit that tokenised the sheets and changed no
record. Run it from anywhere; it reads the working tree and git.
"""

from __future__ import annotations

import copy
import csv
import importlib.util
import re
import struct
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = REPO_ROOT / "mod-diablocraft" / "scripts"
GENERATED = REPO_ROOT / "mod-diablocraft" / "data" / "generated"
D3 = REPO_ROOT / "mod-diablocraft" / "data" / "d3"
DBC = REPO_ROOT / "azerothcore-wotlk" / "build" / "server" / "data" / "dbc"
VARIABLES_DBC = REPO_ROOT / "client-patch" / "dbc" / "SpellDescriptionVariables.dbc"
BASELINE = "7702de8"
# Read rather than executed: the module's own stack path and its constants.
PRIMARIES = (REPO_ROOT / "mod-diablocraft" / "src" / "classes" / "barbarian" / "dc_barbarian_primaries.cpp").read_text(encoding="utf-8")
PRIMARY_DATA = (REPO_ROOT / "mod-diablocraft" / "src" / "classes" / "barbarian" / "dc_barbarian_primary_data.h").read_text(encoding="utf-8")
SHELLS = "mod-diablocraft/" + "data/" + "generated/spell_shells.sql"

# The only fields the sheets are allowed to change without owning them: the
# family and mask that let a modifier reach a shell at all, the sentence, and
# the pointer to the client's exact-value row. All three mask words are the
# writer's: step 6 made its family pass their one home (Architect,
# 2026-09-20), so the skill's bit is word one and the other two are cleared
# rather than left holding the donor's family.
# Step 6 adds Category: it is not a number any sheet states, it is the
# grouping id that makes a base skill and its runes share one timer, and its
# own contract - one per skill, the same on every record of that skill, and
# clear of every category the client's Spell.dbc uses - is checked by
# test_the_cooldown_category_groups_each_skill_and_collides_with_nothing.
# AuraDescription_Lang_enUS is deliberately NOT here. Step 13 put it here for a
# while, reasoning that it is a sentence like the one above; the PM planted
# "Unapproved unrelated aura text." on 81000 and the contract returned no
# problems, which is the whole argument against. The unit and binding sweeps
# check that a sentence is WELL FORMED; nothing about them bounds which
# sentences exist. So the aura text is a total expectation instead - see
# aura_text_fields - and every record's is stated: empty except Frenzy, Punish, Flame Blades and
# the worn buffs of diablocraft-buff-text, whose text is derived there.
# Fields a ruling rather than a sheet owns, each with its exact value. Rend's
# six bleed records became native periodic damage auras (226 PERIODIC_DUMMY ->
# 3 PERIODIC_DAMAGE) so the core ticks, logs and procs them and core patch
# 0016's provider supplies the D3 number (decisions.md 2026-09-23 final
# periodic damage hook; diablocraft-pre-beta-bugs-b item 4).
RULED_FIELDS = {(identifier, "EffectAura_1"): "3" for identifier in range(81157, 81163)}
# diablocraft-ground-target-circles: Furious Charge takes its target point in
# slot 2 (CHARGE_DEST, TARGET_DEST_DEST), which had the donor's 0-yard radius;
# the sheet gives the skill no area, so the point is the small marker, the stock
# 2-yard SpellRadius row 7 (combat.csv ground_marker_radius_yards). Six records:
# the skill and its five runes. test_ground_target_circles.py checks the size.
RULED_FIELDS.update({(identifier, "EffectRadiusIndex_2"): "7"
                     for identifier in (81013, 81088, 81089, 81090, 81091, 81092)})
# diablocraft-as1z (ruling q-0930-13): Leap draws the same marker. Its 10 yd is the
# server's hit radius and is now an exact value, so the base and the three runes
# with no area of their own take the marker in slot 1; Call of Arreat and
# Launch keep their own area there. Slot 2 (the leap itself) is the marker on
# all six records.
RULED_FIELDS.update({(identifier, "EffectRadiusIndex_1"): "7" for identifier in (81012, 81084, 81086, 81087)})
RULED_FIELDS.update({(identifier, "EffectRadiusIndex_2"): "7" for identifier in range(81083, 81088)})
RULED_FIELDS[(81012, "EffectRadiusIndex_2")] = "7"
# Gathering Storm's chill is gathering_chill_pct, a tunable the designer ruled at 60 on
# 2026-09-29 (current D3 slow); the shell's base points are -(60) - 1.
RULED_FIELDS[(81197, "EffectBasePoints_1")] = "-61"
# That record's slot was never free: the baseline already holds the D3 default -31.
CHILL_RULED_SLOTS = {(81197, "EffectBasePoints_1")}
# diablocraft-b3zj: Vanguard's slot 1 is a DUMMY since diablocraft-aura-fixes (RULED_FIELDS above), which the baseline
# predates, and it now states the per-stack Movement Speed (class_buff_fields).
CHILL_RULED_SLOTS.add((81195, "EffectBasePoints_1"))
# diablocraft-aura-fixes (aura-conformance rows 4, 5; ruling 2026-10-03): Vanguard 81195 is a
# DUMMY display buff (its speed is the aggregate's), and each Ignore Pain marker and Nerves of
# Steel's helper 82301 carries the control immunity in slots 2 and 3: aura 147 (misc 96, the
# stock all-controls lookup) and aura 77 (silence), with SPELL_ATTR1_IMMUNITY_PURGES_EFFECT.
# test_control_immunity_records.py checks the meaning.
RULED_FIELDS[(81195, "EffectAura_1")] = "4"
# diablocraft-0hl62: Stupefy's record 81192 carries the core's MECHANIC_CHARM (1; 30 is Sapped), the mechanic the Juggernaut and the Guardian
# refuse (test_stupefy_shared_charm.py checks the meaning).
RULED_FIELDS[(81192, "Mechanic")] = "1"
for _identifier in (81320, 81383, 81384, 81385, 81386, 81387, 82301):
    for _field, _value in (("Effect_2", "6"), ("Effect_3", "6"), ("EffectAura_2", "147"), ("EffectAura_3", "77"),
                           ("EffectMiscValue_2", "96"), ("EffectMiscValue_3", "9"), ("EffectDieSides_2", "1"),
                           ("EffectDieSides_3", "1"), ("ImplicitTargetA_2", "1"), ("ImplicitTargetA_3", "1"),
                           ("AttributesEx", "32768")):
        RULED_FIELDS[(_identifier, _field)] = _value
# diablocraft-xecwl (ruling 2026-10-11): Whirlwind and its five runes carry SPELL_ATTR5_ALLOW_ACTION_DURING_CHANNEL, so
# another cast (Rend) leaves the channel running. test_combat_fixes_xecwl.py checks no other record has it.
RULED_FIELDS.update({(identifier, "AttributesEx5"): "1" for identifier in (81004, *range(81043, 81048))})
# GitHub #52 (diablocraft-chain-counts, ruling q-1003-03): a donor spell's chain count is
# zeroed on every Barbarian shell the module resolves itself, each with its own exact
# value 0 - Hammer of the Ancients (the skill and its five runes, their marker auras, the
# Devil's Anvil and Thunderstrike control shells), Cleave's marker auras and the four
# carrier shells (Desecrator, Jailer, Reflects Damage, Thorns). The Wizard's Static
# Discharge is the 25th and not this suite's. test_chain_counts.py checks the rule and why.
RULED_FIELDS.update({(identifier, "EffectChainTargets_1"): "0" for identifier in (
    81007, *range(81058, 81063), 81175, 81178, 81182, 81184, 81313, 81317,
    *range(81348, 81353), *range(81368, 81373), 81770, 81772)})
# GitHub #45 (Architect, 2026-09-29): a record with a TARGET_DEST_DEST (87)
# effect carries TARGET_FLAG_DEST_LOCATION (0x40) in Targets, so the client asks
# for the ground point. A rule over the record, not an id list: each such
# record's Targets is owned and must be exactly its baseline value plus the flag.
TARGET_DEST_DEST, TARGET_FLAG_DEST_LOCATION = 87, 0x40


def passive_icon_fields():
    """{(spell id, "SpellIconID"): the icon} of every class passive: the SpellIcon.dbc id of the stock icon data/d3/passive_icons.csv names
    for it (every passive shell is a copy of one plain passive, which gave all of them its icon)."""
    data = (DBC / "SpellIcon.dbc").read_bytes()
    _magic, count, _fields, size, _strings = struct.unpack("<4sIIII", data[:20])
    strings = data[20 + count * size:]
    by_file = {}
    for index in range(count):
        record = data[20 + index * size:20 + (index + 1) * size]
        key, offset = struct.unpack_from("<II", record)
        by_file[strings[offset:strings.index(b"\0", offset)].decode().lower().rpartition("\\")[2]] = key
    ids = {row["name"]: row["spell_id"] for row in read_csv(GENERATED / "spell_shells.csv") if row["kind"] == "passive"}
    return {(int(ids[row["passive_name"]]), "SpellIconID"): str(by_file[row["icon_name"].lower()])
            for row in read_csv(REPO_ROOT / "mod-diablocraft" / "data" / "d3" / "passive_icons.csv")}


def ground_target_fields(names, before, now):
    """{(spell id, "Targets"): expected} for every DEST_DEST record."""
    at = {name: index for index, name in enumerate(names)}
    expected = {}
    for identifier, values in now.items():
        if any(int(values[at["ImplicitTarget%s_%d" % (side, slot)]]) == TARGET_DEST_DEST
               for side in "AB" for slot in (1, 2, 3)):
            baseline = before.get(identifier, values)
            expected[(identifier, "Targets")] = str(int(baseline[at["Targets"]]) | TARGET_FLAG_DEST_LOCATION)
    return expected


def cleared_donor_fields(names, before, now):
    """{(spell id, field): "0"} for the donor's equipped-item masks on every record the baseline has: the generator's FORCED_ZERO clears
    them (a record asks for no weapon kind and no slot), and the class -1 on every record means nothing read them (diablocraft-u4smw)."""
    return {(identifier, field): "0" for identifier in now if identifier in before
            for field in ("EquippedItemSubclass", "EquippedItemInvTypes")}


FREE_FIELDS = {"SpellClassSet", "SpellClassMask_1", "SpellClassMask_2", "SpellClassMask_3",
               "Category",
               "Description_Lang_enUS", "SpellDescriptionVariableID"}
HELPER_FIRST, HELPER_LAST = 82400, 82499
# Shells added after the baseline on purpose, outside the helper block: the first
# legendary potion's own shell (diablocraft-potion-regeneration, combat_0043), and the
# other ten potions' shells and the potions' power records (diablocraft-87qlt, combat_0063).
# test_bottomless_potion.py and test_potion_powers.py own their fields.
APPENDED_SHELLS = {81205, *range(81211, 81229)}
# Effects that read the record's own duration or stack count.
AURA_EFFECTS = (6, 27, 35, 65, 119, 128, 143)
# Effects a slot may carry and still be free for a tooltip number.
FREE_EFFECTS = (0, 3)
# Step 5: Fury is Rage and the record counts in Rage units, one per Fury since class powers P2 (ten before).
RAGE_PER_FURY = 1
POWER_RAGE = 1
# Step 6: SPELL_ATTR0_CU_FORCE_SEND_CATEGORY_COOLDOWNS (SpellInfo.h:205).
FORCE_SEND_CATEGORY_COOLDOWNS = 0x10000000
FIRST_SHELL, LAST_SHELL = 81000, 83001
# Step 7: the "Cost:" and "Cooldown:" label lines the client now prints from
# the record. Eighteen sheet rows carry one, Earthquake carries both, and
# Whirlwind keeps its cost line because the module still pays it tick by
# tick: seventeen lines dropped from sixteen records. Counted, so a sheet
# edit that adds or loses one is visible here rather than silently changing
# what a tooltip says.
DROPPED_LINES = 17
# The first SpellDescriptionVariables.dbc row we own; stock ids are three
# digits, so a donor's own pointer is recognisable by being below it.
FIRST_VARIABLE_ID = 81000
# The cooldown categories the rune families share, and the DBC the writer emits
# so the core can resolve them at all.
CATEGORY_FIRST, CATEGORY_LAST = 8100, 8199
GENERATED_CATEGORY_DBC = REPO_ROOT / "client-patch" / "dbc" / "SpellCategory.dbc"
# The Spell.dbc the generator writes, which is the one that ships in the MPQ.
GENERATED_SPELL_DBC = REPO_ROOT / "client-patch" / "dbc" / "Spell.dbc"
# Values a sheet row states for the module and no sentence prints (Architect,
# 2026-09-20): Whirlwind's channel terms. They are exact values on the record
# like any other number no field holds, but they are in no sentence, so every
# check that compares the sheet with a sentence leaves them out - and says so.
# Step 8 adds Inspiring Presence's duration_bonus_pct: "doubled" is a word in
# its sentence, the +100 percent behind it is a number only the modifier record
# carries, and no sentence prints it either.
MODULE_READ = {"channel_cost_speed_term_resource", "channel_cost_flat_resource",
               "channel_tick_frames_count", "channel_frames_per_second_count",
               "duration_bonus_pct",
               # diablocraft-proc-coefficients-wiring: each skill's and rune's D3 proc
               # coefficient, read by the crit procs and printed by no sentence.
               "proc_coefficient"}


def printed(rows):
    """The rows of a sheet entry that a sentence prints."""
    return [row for row in rows if row["token"] not in MODULE_READ]


def _other_class_ranges():
    """The record and helper blocks every class but the Barbarian owns.

    diablocraft-wizard-records: this suite is the Barbarian's contract, row for
    row, and the second class's records are checked by test_wizard_records.py.
    The blocks are read from the generator's CLASS_BLOCKS rather than copied,
    so a new class drops out of this suite by the same table that reserves it.
    """
    spec = importlib.util.spec_from_file_location("generate_spells_blocks", SCRIPTS / "generate/classes/generate_spells.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    spec.loader.exec_module(module)
    others = [block for stem, block in module.CLASS_BLOCKS.items() if stem != "barbarian"]
    # The legendary gems' block (diablocraft-y75r) belongs to no class and is checked by test_legendary_gem_group_c.py;
    # the pylon and shrine buffs' (diablocraft-plgq2) likewise, by test_pylon_buffs.py; the legendary power buffs' (diablocraft-pl8fc) by
    # test_legendary_attack_events_and_buffs.py; the bounties' (diablocraft-e719a) by test_bounty_click_shell.py.
    return ([block.records for block in others] + [block.helpers for block in others]
            + [(module.GEM_ID_FIRST, module.GEM_ID_LAST), (module.PYLON_ID_FIRST, module.PYLON_ID_LAST),
               (module.POWER_BUFF_ID_FIRST, module.POWER_BUFF_ID_LAST), (module.BOUNTY_ID_FIRST, module.BOUNTY_ID_LAST)],
            [block.categories for block in others])


OTHER_CLASS_RANGES, OTHER_CLASS_CATEGORIES = _other_class_ranges()


def barbarian_category(identifier):
    """True unless the category sits in another class's category block."""
    return not any(first <= identifier <= last for first, last in OTHER_CLASS_CATEGORIES)


def barbarian_id(identifier):
    """True unless the id sits in another class's record or helper block."""
    identifier = int(identifier)
    return not any(first <= identifier <= last for first, last in OTHER_CLASS_RANGES)


def split_values(text):
    """One SQL row's values, respecting quotes and doubled-quote escapes."""
    out, current, quoted, index = [], "", False, 0
    while index < len(text):
        char = text[index]
        if quoted:
            if char == "'" and index + 1 < len(text) and text[index + 1] == "'":
                current += "''"
                index += 2
                continue
            if char == "'":
                quoted = False
                current += char
            else:
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


def parse(sql, every_class=False):
    """(column names, {spell id: [values as written]}) from the generated SQL.

    The suite is the Barbarian's; `every_class` keeps the Wizard's records too."""
    header = re.search(r"INSERT INTO `spell_dbc` \(([^)]*)\) VALUES", sql)
    if not header:
        raise AssertionError("no spell_dbc INSERT in the generated SQL")
    names = [name.strip(" `") for name in header[1].split(",")]
    rows = {}
    for line in sql.splitlines():
        line = line.strip().rstrip(",;")
        if not line.startswith("(") or not line.endswith(")"):
            continue
        values = split_values(line[1:-1])
        if len(values) != len(names):
            continue
        if every_class or barbarian_id(values[0]):
            rows[int(values[0])] = values
    return names, rows


def frozen_file(path):
    """A file as the baseline had it: step 4 deletes the positional tables,
    and what they used to say is still the thing this compares against."""
    result = subprocess.run(["git", "show", f"{BASELINE}:{path}"], cwd=REPO_ROOT,
                            capture_output=True)
    if result.returncode:
        raise unittest.SkipTest("baseline %s unavailable" % BASELINE)
    return result.stdout.decode("utf-8")


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def dbc_ids(path):
    """Every row id of a WDBC file, in file order."""
    data = path.read_bytes()
    magic, count, _fields, size, _strings = struct.unpack("<4sIIII", data[:20])
    if magic != b"WDBC":
        raise AssertionError("%s: not a WDBC file" % path)
    return [struct.unpack_from("<I", data, 20 + index * size)[0] for index in range(count)]


def load_dbc_column(name, offset):
    """{row id: one int field} of a client DBC, for durations and radii."""
    data = (DBC / name).read_bytes()
    magic, count, _fields, size, _strings = struct.unpack("<4sIIII", data[:20])
    if magic != b"WDBC":
        raise AssertionError(f"{name}: not a WDBC file")
    out = {}
    for index in range(count):
        record = data[20 + index * size: 20 + (index + 1) * size]
        out[struct.unpack_from("<I", record, 0)[0]] = struct.unpack_from(
            "<i" if offset else "<I", record, offset)[0]
    return out


def load_radii():
    data = (DBC / "SpellRadius.dbc").read_bytes()
    _magic, count, _fields, size, _strings = struct.unpack("<4sIIII", data[:20])
    out = {}
    for index in range(count):
        record = data[20 + index * size: 20 + (index + 1) * size]
        out[struct.unpack_from("<I", record, 0)[0]] = struct.unpack_from("<f", record, 4)[0]
    # the rows the module adds on top of the stock table (data/spell_radius_rows.csv), as the server's spellradius_dbc has them
    with (REPO_ROOT / "mod-diablocraft/data/spell_radius_rows.csv").open(encoding="utf-8-sig", newline="") as stream:
        out.update({int(row["id"]): float(row["yards"]) for row in csv.DictReader(stream)})
    return out


def load_dbc_strings(path, field):
    """{row id: one string field} of a client DBC, resolved through its block.

    Takes a path, not a name: this reads the file the generator WRITES, which
    is the one that ships in the MPQ, and not the extracted input beside the
    server that `load_dbc_column` reads its stock durations and radii out of.
    """
    data = path.read_bytes()
    magic, count, fields, size, _strings = struct.unpack("<4sIIII", data[:20])
    if magic != b"WDBC":
        raise AssertionError(f"{path.name}: not a WDBC file")
    if not 0 <= field < fields:
        raise AssertionError(f"{path.name}: no field {field} in a {fields}-field record")
    block = data[20 + count * size:]
    out = {}
    for index in range(count):
        record = data[20 + index * size: 20 + (index + 1) * size]
        offset = struct.unpack_from("<I", record, field * 4)[0]
        end = block.index(b"\0", offset)
        out[struct.unpack_from("<I", record, 0)[0]] = block[offset:end].decode("utf-8")
    return out


# The shape our own rows in SpellDescriptionVariables.dbc are written in, taken
# from the stock rows: `$name=${value}`, several to a row separated by CRLF, no
# terminator. Step 7 wrote ours as `$name=value;` and the client printed the
# token as literal text on client 29; step 11 (2026-09-20) put them in the
# stock shape. The stock file is not all this narrow - most of its pieces are
# conditional expressions - so this regex describes OUR rows, and what the
# stock rows are evidence for is spelled out where they are checked.
VARIABLE_ROW = re.compile(r"^\$[a-z_]+=\$\{[^}]+\}(?:\r\n\$[a-z_]+=\$\{[^}]+\})*$")
# `$d` carries its own unit word from the client's string table, so a sentence
# of ours never supplies one (ruling 2026-09-20). `$t1` is a bare number and
# keeps a word, spelled out in full.
DURATION_WITH_UNIT = re.compile(r"\$d\s+(?:seconds?|secs?|minutes?|mins?)\b", re.I)
PERIOD_WITHOUT_WORD = re.compile(r"\$t1(?!\s+seconds\b)")
# The two text fields of a record the client renders as prose, and the brief
# asks for both. `AuraDescription_Lang_enUS` is empty on most records we write,
# so the sweeps below find little in it; the mutation regressions are what give
# that coverage teeth, by planting an offender in the aura field and failing if
# it goes unseen.
SENTENCE_FIELDS = ("Description_Lang_enUS", "AuraDescription_Lang_enUS")


def sentences_of(values, at):
    """Every rendered text field of one record, in field order."""
    return [values[at[field]] for field in SENTENCE_FIELDS]


def variables_rendered(sentences):
    """The `$<name>` references a record makes, across all of its sentences.

    The union, in first-seen order: the client resolves both fields out of the
    one row `SpellDescriptionVariableID` names, so a name either field asks
    for is a name the record asks for.
    """
    wanted = []
    for text in sentences:
        for name in re.findall(r"\$<([^>]+)>", text):
            if name not in wanted:
                wanted.append(name)
    return wanted


def binding_faults(name, sentences, pointer, rows):
    """Everything wrong with how one record's sentences bind to its row."""
    wanted = variables_rendered(sentences)
    if not wanted:
        if pointer >= FIRST_VARIABLE_ID and pointer in rows:
            return ["%s renders no variable and points at row %d of ours" % (name, pointer)]
        return []
    if pointer not in rows:
        return ["%s renders %s and points at row %d, which does not exist"
                % (name, wanted, pointer)]
    defined = variable_names(rows[pointer])
    faults = []
    for asked in wanted:
        if asked != asked.lower():
            faults.append("%s renders $<%s>, which is not the lower-case name the "
                          "sheets use" % (name, asked))
        if asked not in defined:
            faults.append("%s renders $<%s> and row %d defines %s"
                          % (name, asked, pointer, defined))
    if sorted(defined) != sorted(wanted):
        faults.append("%s: row %d defines %s and the record asks for %s"
                      % (name, pointer, defined, sorted(wanted)))
    return faults


def unit_faults(name, sentences):
    """The units a sentence of ours must not supply, and the words it spells out."""
    faults = []
    for text in sentences:
        found = DURATION_WITH_UNIT.search(text)
        if found:
            faults.append("%s supplies $d's unit: %r" % (name, found.group(0)))
        if PERIOD_WITHOUT_WORD.search(text):
            faults.append("%s writes $t1 without the spelled-out word: %r"
                          % (name, text[:120]))
        if re.search(r"\b(?:sec|min)\b\.?", text, re.I):
            faults.append("%s abbreviates a unit: %r" % (name, text[:120]))
    return faults


def variable_names(text):
    """The names a row of OUR grammar defines, in order, with their casing."""
    return [piece.split("=", 1)[0].lstrip("$")
            for piece in text.split("\r\n") if piece]


def parse_variables(raw):
    """{row id: {name: value string}} from SpellDescriptionVariables.dbc.

    Reads both grammars: the stock rows use `${...}` and CRLF, and a handful
    of them carry conditionals this does not try to evaluate. Ours are the
    rows this suite checks, and they are checked against VARIABLE_ROW.
    """
    magic, count, fields, size, _strings = struct.unpack("<4sIIII", raw[:20])
    if magic != b"WDBC":
        raise AssertionError("SpellDescriptionVariables.dbc: not a WDBC file")
    if (fields, size) != (2, 8):
        raise AssertionError("SpellDescriptionVariables.dbc: expected two 4-byte fields, "
                             f"got {fields} fields of {size} bytes")
    strings = raw[20 + count * size:]
    out = {}
    for index in range(count):
        record = raw[20 + index * size: 20 + (index + 1) * size]
        identifier, offset = struct.unpack("<II", record)
        text = strings[offset:strings.index(b"\x00", offset)].decode("utf-8")
        entries = {}
        for piece in text.replace(";", "\r\n").split("\r\n"):
            if not piece:
                continue
            name, _, value = piece.lstrip("$").partition("=")
            if value.startswith("${") and value.endswith("}"):
                value = value[2:-1]
            entries[name] = value
        out[identifier] = entries
    return out


def load_generator():
    """Import generate_spells.py for the parts this checker exercises directly."""
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("generate_spells", SCRIPTS / "generate/classes/generate_spells.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sheet_rows():
    """(kind, shell name, skill, rune, tokenised text, passive) per sheet row."""
    rows = []
    for row in read_csv(D3 / "barbarian_skills.csv"):
        rows.append(("active", row["skill_name"], row["skill_name"], "",
                     row["full_tooltip_text"], False))
    for row in read_csv(D3 / "barbarian_runes.csv"):
        name = "%s - %s" % (row["skill_name"], row["rune_name"])
        rows.append(("rune", name, row["skill_name"], row["rune_name"],
                     row["full_rune_text"], False))
    for row in read_csv(D3 / "barbarian_passives.csv"):
        rows.append(("passive", row["passive_name"], row["passive_name"], "",
                     row["full_text"], True))
    return rows


def values_by_row():
    """{(skill, rune, passive): [value rows in sheet order]}."""
    out = {}
    for name, passive in (("barbarian_skill_values.csv", False),
                          ("barbarian_passive_values.csv", True)):
        for row in read_csv(D3 / name):
            out.setdefault((row["skill"], row["rune"], passive), []).append(row)
    return out


def value_row(values, entry):
    """The values sheet row an entry names, base skill or rune."""
    if entry["origin"] == "inherited":
        skill, rune = entry["skill"], ""
    else:
        skill, rune = entry["skill"], entry["rune"]
    rows = values.get((skill, rune, False)) or values.get((skill, rune, True)) or []
    return next((row for row in rows
                 if row["token"] == entry["token"] and row["qualifier"] == entry["qualifier"]),
                None)


def quoted(text):
    """A string as the generated SQL writes it."""
    return "'%s'" % text.replace("'", "''")


def rank_fields(manifest, quote=True):
    """{(spell id, "NameSubtext_Lang_enUS"): expected} for every record.

    `quote` says which representation the caller compares against: this
    suite reads values straight out of the SQL text and keeps their quotes,
    test_primaries parses them with csv and does not.

    Step 8 (Architect, 2026-09-20): a rune record carries "Rune: <rune name>"
    in the field Spell.dbc calls Rank, which the 3.3.5 client draws in the top
    right of the tooltip and GetSpellInfo() returns as its second value. That
    replaces the module's own Rune line in the Lua, so the expectation is
    total rather than a spot check: a rune says exactly that, and every other
    record - including the internal Rend Bleed shells, which are named after a
    rune but are not one a player picks - says nothing at all.
    """
    expected = {}
    for row in manifest:
        identifier = int(row["spell_id"])
        text = "Rune: " + row["name"].partition(" - ")[2] if row["kind"] == "rune" else ""
        expected[(identifier, "NameSubtext_Lang_enUS")] = quoted(text) if quote else text
    return expected


# Spell rewrite 13, Architect 2026-09-22 (confirmed). The ONE record that says
# anything in its aura tooltip, and exactly what it says. Everything else says
# nothing, and that is stated rather than left free: see aura_text_fields.
AURA_TEXT = {81196: "Attack speed increased by $s1%."}
# GitHub #44 (brief approved 2026-09-29): Bash - Punish's worn buff, the helper
# record named "Punish", in the Frenzy buff's stock shape. By name, because a
# helper's id comes from the append-only helper map.
AURA_TEXT_BY_NAME = {"Punish": "Damage increased by $s1%.",
                     # diablocraft-o2be: the Wizard's Flame Blades stacking buff, its own sentence.
                     "Flame Blades": "The damage of your Fire spells is increased by $s1%."}


# diablocraft-buff-text (the designer, q-1004-20, 2026-10-04): the player's own buffs show the
# sentence of the skill they stand for - the Wizard's eight buff skills and every
# rune record of them, the Barbarian's worn markers. A rune's buff shows the base
# skill's sentence first, then its own. No Cost, Cooldown, Generate or Requires
# line; nothing where there is no sentence; nothing on an enemy-side debuff.
WIZARD_WORN = ("Ice Armor", "Storm Armor", "Magic Weapon", "Familiar", "Energy Armor",
               "Diamond Skin", "Archon", "Explosive Blast")
# Skill -> the runes whose marker the player wears (None: the base and every rune).
# Read off dc_abilities.cpp Cast: Mark(p, p, ...) and the ally marks of War Cry,
# Forced March and Mob Rule. Threatening Shout, Snow-Capped Mountain and Mutilate
# put theirs on an ENEMY, which is a later bead.
BARBARIAN_WORN = {"Sprint": None, "Ignore Pain": None, "War Cry": None, "Battle Rage": None,
                  "Wrath of the Berserker": None,
                  "Overpower": {"Killing Spree", "Crushing Advance"},
                  "Revenge": {"Best Served Cold"}, "Leap": {"Iron Impact"}}
ENEMY_SIDE = (("Threatening Shout", None), ("Avalanche", {"Snow-Capped Mountain"}),
              ("Rend", {"Mutilate"}))
# The three buffs whose text predates this bead (Frenzy 81196; Punish and Flame Blades by name).
# diablocraft-xumo (buff icons build 1): the legendary gem buffs, pinned here word for word so a changed sentence is
# a change of this file too (data/legendary_gem_buffs.csv and aura_text of legendary_gem_spells.csv hold the same).
GEM_BUFF_TEXT = {
    83400: "Lightning pulses every second, hitting nearby enemies.",
    83409: "Absorbs damage.",
    83411: "Increases Attack Speed by $s1%.",
    83412: "Increases Attack Speed by $s1% and Cooldown Reduction by $s2%.",
    83413: "Increases the damage you deal.",
    83414: "Increases the damage you deal and increases your Armor by $s1%.",
    83415: "Increases healing received.",
    83416: "Damage increased by $s1%.",
    83417: "Attack Speed increased by $s1%.",
    83418: "Resistances to Cold, Fire, Lightning, Poison and Arcane increased by $s1%.",
    83419: "Part of the damage you take is put off and dealt to you over time.",
}
# diablocraft-b3zj (buff icons build 2): the class buffs, pinned word for word like the gem buffs (data/class_buffs.csv
# holds the same). By spell id for the records that already existed (a name such as "Pound of Flesh" is also the passive
# on the skill bar, which has no aura text), by name for the helper records the generator numbers itself.
CLASS_BUFF_TEXT = {
    81195: "Movement speed increased by $s1%.",
    82300: "Regenerating $s1% of maximum Life per second.",
    82301: "You take $s1% reduced damage and are immune to all control-impairing effects.",
    82303: "Strength increased by $s1%.",
    82304: "Regenerating $s1% of maximum Life per second. Movement speed increased by $s2%.",
    "Relentless - buff": "Skills cost $s1% less Fury, Life per Fury Spent is doubled, and damage taken is reduced by $s2%.",
    "Berserker Rage - buff": "Damage increased by $s1%.",
    "Brawler - buff": "Damage increased by $s1%.",
    "War Cry - Hardened Wrath - buff": "Armor increased by $s1%.",
    "Battle Rage - Into the Fray - buff": "Critical Hit Chance increased by $s1%.",
    "Illusionist - buff": "Movement speed increased by $s1%.",
    "Unwavering Will - buff": "Armor increased by $s1%, all resistances by $s2% and damage by $s3%.",
    "Arcane Dynamo - flashes - buff": "Each Signature spell you cast grants a Flash of Insight. With all the Flashes, "
                                     "your next non-Signature spell is empowered.",
    "Arcane Dynamo - empowered - buff": "Your next non-Signature spell deals $s1% additional damage.",
    "Storm Armor - Scramble - buff": "Movement speed increased by $s1%.",
    "Frost Nova - Deep Freeze - buff": "Critical Hit Chance increased by $s1%.",
    "Teleport - Safe Passage - buff": "Damage taken reduced by $s1%.",
    "Energy Twister - Storm Chaser - buff": "Your next Signature spell releases a bolt of Lightning for $s1% weapon damage.",
    "Wave of Force - Arcane Attunement - buff": "Your next Arcane spell deals $s1% additional damage.",
    "Arcane Orb - Spark - buff": "Your next Lightning spell deals $s1% additional damage.",
    "Flame Ward - buff": "You take less damage from attacks while channeling, more with every second, up to $s1%.",
    "Archon - kills - buff": "Damage increased by $s1%.",
    "Ice Armor - Crystallize - buff": "Armor increased by $s1%.",
    "Overcharge - buff": "Your next Secondary skill deals $s1% more damage and uses up every stack.",
    "Attunement - Fire - buff": "Damage dealt increased by $s1%.",
    "Attunement - Cold - buff": "Regenerate 0.5% of your maximum Life every second.",
    "Attunement - Physical - buff": "Armor increased by $s1%.",
    "Attunement - Lightning - buff": "Attack speed increased by $s1%.",
    "Elemental Shield - buff": "Each hit you take uses up a charge, lowers that hit's damage by 30% and strikes the attacker for 200% weapon damage as Lightning.",
    "Elemental Shield - Lightning Shield - buff": "Each hit you take uses up a charge, lowers that hit's damage by 30%, strikes the attacker for 350% weapon damage as Lightning and generates 4 Maelstrom. Your Primary skill hits have a 15% chance to add a charge.",
    "Elemental Shield - Stoneskin - buff": "Each hit you take uses up a charge, lowers that hit's damage by 30% and strikes the attacker for 200% weapon damage as Physical. Armor increased by 40% while any charge remains.",
    "Elemental Shield - Stoneskin - shield": "Absorbs damage equal to 20% of your maximum Life.",
    "Elemental Shield - Water Shield - buff": "Each hit you take uses up a charge, lowers that hit's damage by 30%, strikes the attacker for 200% weapon damage as Cold, heals you for 2% of your maximum Life, restores 4 Maelstrom and Chills the attacker by 40% for 2 seconds.",
    "Elemental Shield - Flame Shield - buff": "Enemies within 8 yards burn for 150% weapon damage as Fire per second. Each hit you take uses up a charge, lowers that hit's damage by 30% and deals 300% weapon damage as Fire to the attacker and enemies within 6 yards of it.",
    "Elemental Weapon - buff": "Your skills deal 5% more damage and generate 5% more Maelstrom.",
    "Elemental Weapon - Flametongue - buff": "Fire skills deal 15% more damage, and your Fire hits burn enemies for 100% weapon damage as Fire over 3 seconds.",
    "Elemental Weapon - Frostbrand - buff": "Cold skills deal 15% more damage, and your Cold hits Chill enemies by 30% for 2 seconds.",
    "Elemental Weapon - Windfury - buff": "Lightning skills deal 15% more damage, and every 5th Lightning hit strikes the target again for 150% weapon damage as Lightning.",
    "Elemental Weapon - Rockbiter - buff": "Physical skills deal 15% more damage and Armor is increased by 20%.",
    "Elemental Weapon - Maelstrom Weapon - buff": "Every 5th Primary skill cast makes your next Secondary skill free.",
    "Elemental Weapon - Maelstrom Weapon - free": "Your next Secondary skill costs no Maelstrom.",
    "Galvanizing Ward - shield": "Absorbs damage.",
    "Dominance - shield": "Absorbs damage.",
    "Unstable Anomaly - shield": "Absorbs damage.",
    "Magic Weapon - Deflection - shield": "Absorbs damage.",
    "Spectral Blade - Barrier Blades - shield": "Absorbs damage.",
}
# diablocraft-plgq2 (pylons and shrines P1): the pylon and shrine buffs, pinned word for word like the gem buffs
# (data/pylon_buffs.csv holds the same; test_pylon_buffs.py checks the rest of each record).
PYLON_BUFF_TEXT = {
    83500: "Damage from all of your attacks is increased by $s1%.",
    83501: "Lightning zaps your surroundings, causing massive damage to nearby enemies.",
    83502: "All resource costs are removed, and cooldowns reduced by $s1%.",
    83503: "Invulnerable to all damage and all control impairing effects.",
    83504: "Your movement speed is increased by $s1% and attack speed by $s2%. Can pass through enemies, knocking them up into the air.",
    83505: "You take $s1% less damage from attacks.",
    83506: "Your resource regeneration is increased by $s1% and your cooldowns are reduced by $s2%.",
    83507: "You gain $s1% more experience from monsters you kill.",
    83508: "You move $s1% faster.",
    83509: "Your chance to find magic items is increased by $s1% and to find gold by $s2%.",
    83510: "Your attack rate is increased by $s1%.",
}
# diablocraft-pl8fc: the legendary power buffs (data/legendary_power_buffs.csv), likewise.
POWER_BUFF_TEXT = {83550: "Damage taken reduced by $s1%.", 83551: "Armor increased by $s1%.", 83552: "Movement speed reduced by $s1%.",
                   83553: "Damage taken reduced by $s1% and damage dealt increased.",
                   83555: "Takes increased damage from the Mystic Ally of the one who marked it.",
                   83556: "Damage taken reduced.",   # a rolled reduction: the record states no number
                   83562: "Your next attack inflicts $s1% additional damage.",
                   83563: "Damage taken reduced by $s1%.",   # Wall of Man (diablocraft-upwsv): the 25% off every hit, one fixed number
                   83564: "Dashing Strike damage increased.",   # a rolled skill bonus: the record states no number
                   83565: "Hydra damage increased."}   # Fragment of Destiny's Spectral: a rolled skill bonus, no number
# The Bottomless potions' power records (diablocraft-87qlt): the sheet's power text, the roll as $s1; Fear (81226) sits on enemies.
POTION_BUFF_TEXT = {
    81221: "Increases Armor by $s1% for 5 seconds.",
    81222: "Increases Resist All by $s1 for 5 seconds.",
    81223: "Restores an additional $s1 Life over 5 seconds.",
    81224: "Increases Life per Hit by $s1 for 5 seconds.",
    81225: "Increases Life per Kill by $s1 for 5 seconds.",
    81227: "Increases healing from all sources by $s1% for 5 seconds.",
    81228: "Become immune to control impairing effects for $s1 seconds after drinking this potion.",
}
OLDER = {81196: AURA_TEXT[81196], 82412: AURA_TEXT_BY_NAME["Punish"],
         "Flame Blades": AURA_TEXT_BY_NAME["Flame Blades"], **GEM_BUFF_TEXT, **CLASS_BUFF_TEXT, **PYLON_BUFF_TEXT, **POWER_BUFF_TEXT,
         **POTION_BUFF_TEXT}
CRLF = "\r\n"
SKILL_LINE = re.compile(r"^(?:cost|cooldown)\s*:|^requires\b", re.I)
BARE = re.compile(r"\$((?:[satxo]\d|[dhuni]))(?![A-Za-z0-9])")
VARIABLE = re.compile(r"\$<([a-z_]+)>")


def unquote(raw):
    """A text as the generated SQL writes it, back to the text."""
    return raw[1:-1].replace("''", "'").replace("\\r\\n", CRLF).replace("\\\\", "\\")


def stored(text):
    """A text as the generated SQL stores it, without the quotes."""
    return text.replace("\\", "\\\\").replace("'", "''").replace("\r", "\\r").replace("\n", "\\n")


def kept_lines(text):
    return [line for line in text.split(CRLF) if line and not SKILL_LINE.match(line)]


def portable(text, owner, prefix):
    """The sentence as another record can print it: the owner's id in every token."""
    return VARIABLE.sub(lambda m: "$<%s%s>" % (prefix, m[1]),
                        BARE.sub(lambda m: "$%d%s" % (owner, m[1]), text))


def expected_aura(buff, sources, descriptions):
    """The aura text one buff record must carry, from its sources' Description.

    `sources` is [(record id, variable prefix)], base skill first; a source that is
    the buff itself is printed as it stands, any other one is made portable. Written
    here from the records' own Description field, not from the generator's function.
    """
    parts = []
    for owner, prefix in sources:
        text = CRLF.join(kept_lines(descriptions[owner]))
        if text and owner != buff:
            text = portable(text, owner, prefix)
        if text:
            parts.append(text)
    return CRLF.join(parts)


def worn_expectations(manifest):
    """{buff record id: [(source id, prefix)]} for every record that must carry text."""
    named = {(row["kind"], row["name"]): int(row["spell_id"]) for row in manifest}
    wanted = {}
    for row in manifest:
        identifier, kind, name = int(row["spell_id"]), row["kind"], row["name"]
        skill, _, rune = name.partition(" - ")
        if kind in ("active", "rune") and skill in WIZARD_WORN:
            wanted[identifier] = ([(named[("active", skill)], "base_")] if rune else []) + [(identifier, "")]
        if kind == "ability_aura" and skill in BARBARIAN_WORN:
            runes = BARBARIAN_WORN[skill]
            if runes is None or rune in runes:
                own = named[("rune" if rune else "active", name)]
                wanted[identifier] = ([(named[("active", skill)], "base_")] if rune else []) + [(own, "")]
    return wanted


def all_descriptions():
    """{spell id: Description_Lang_enUS} for every record of every class in the SQL."""
    sql = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    names, rows = parse(sql, every_class=True)
    column = names.index("Description_Lang_enUS")
    return {identifier: unquote(values[column]) for identifier, values in rows.items()}


def aura_text_fields(manifest, quote=True):
    """{(spell id, "AuraDescription_Lang_enUS"): expected} for EVERY record.

    Total, like rank_fields and for the same reason. A per-field exemption
    would let any record carry any well-formed sentence: the unit and binding
    sweeps say a sentence is well formed, never that it belongs there. With
    this, a tooltip that appears on a record nobody approved fails, and so does
    a wrong wording on the record that does have one. The worn buffs' text is
    derived (see expected_aura); every other record says nothing.
    """
    wanted = worn_expectations(manifest)
    descriptions = all_descriptions() if wanted else {}
    expected = {}
    for row in manifest:
        identifier = int(row["spell_id"])
        if identifier in OLDER:
            text = OLDER[identifier]
        elif row["name"] in OLDER:
            text = OLDER[row["name"]]
        elif identifier in wanted:
            text = expected_aura(identifier, wanted[identifier], descriptions)
        else:
            text = ""
        text = stored(text)
        expected[(identifier, "AuraDescription_Lang_enUS")] = "'%s'" % text if quote else text
    return expected


# The Frenzy buff the player wears is
# 81196 (dc_barbarian_primary_data.h's FRENZY_BUFF), not the 81310 marker whose number the
# SKILL sentence cross-references as `$81310s1`. Its aura tooltip has to render
# the per-stack attack speed, so the number has to be on THAT record's own
# effect - a cross-spell reference would read the other record and could not be
# scaled by this aura's stacks. It is not a new number: it is Frenzy's own
# `attack_speed_pct`, and it is checked against the sheet here exactly like any
# other owned field rather than being waved through as "free".
BUFF_MARKER_NUMBERS = {81196: ("Frenzy", "", "attack_speed_pct", "max_stacks_count")}


def buff_marker_fields(values, quote=True):
    """The one record that carries a sheet number for its aura tooltip alone."""
    owned = {}
    for identifier, (skill, rune, number, stacks) in BUFF_MARKER_NUMBERS.items():
        rows = {row["token"]: row for row in values.get((skill, rune, False), [])}
        for token in (number, stacks):
            assert token in rows, "%s/%s has no %s row" % (skill, rune, token)
        amount = int(float(rows[number]["value"]))
        owned[(identifier, "EffectBasePoints_1")] = str(amount - 1)   # $s1 = base + die
        owned[(identifier, "EffectDieSides_1")] = "1"
        owned[(identifier, "CumulativeAura")] = str(int(float(rows[stacks]["value"])))
    return owned


# diablocraft-b3zj: the class buffs that already existed and now state their numbers, each slot's (skill, rune, passive,
# token). The expected base points are the sheet's own number less one (a record's $s is base + die sides), read here.
CLASS_BUFF_NUMBERS = {
    81195: [("Frenzy", "Vanguard", False, "movement_speed_pct")],
    82300: [("Inspiring Presence", "", True, "life_regen_pct")],
    82301: [("Nerves of Steel", "", True, "damage_taken_pct")],
    82303: [("Rampage", "", True, "primary_stat_pct")],
    82304: [("Pound of Flesh", "", True, "life_regen_pct"), ("Pound of Flesh", "", True, "movement_speed_pct")],
}


def class_buff_fields(values):
    """{(spell id, field): expected} for the records of CLASS_BUFF_NUMBERS."""
    owned = {}
    for identifier, slots in CLASS_BUFF_NUMBERS.items():
        for slot, (skill, rune, passive, token) in enumerate(slots, 1):
            rows = {row["token"]: row for row in values[(skill, rune, passive)] if not row["qualifier"]}
            owned[(identifier, "EffectBasePoints_%d" % slot)] = str(int(float(rows[token]["value"])) - 1)
            owned[(identifier, "EffectDieSides_%d" % slot)] = "1"
            if slot == 2:   # a second dummy aura effect on the caster, beside the first
                owned.update({(identifier, "Effect_2"): "6", (identifier, "EffectAura_2"): "4",
                              (identifier, "ImplicitTargetA_2"): "1"})
    frenzy = {row["token"]: row for row in values[("Frenzy", "", False)]}
    owned[(81195, "CumulativeAura")] = str(int(float(frenzy["max_stacks_count"]["value"])))   # stacks with Frenzy
    return owned


def owned_fields(now, value_map, durations, radii, manifest=None, quote=True):
    """{(spell id, field): expected value} — every field a sheet row owns.

    This is the expected-delta contract of report section 4, per record and
    per field rather than per field NAME: a field appears here only with the
    one value its sheet row implies, so a plausible-looking wrong number in
    the right field is a failure, not a pass.

    `manifest` adds the fields no sheet row states but the writer decides for
    itself, one value each, on the same terms: today that is the rune rank.
    """
    owned, problems = {}, []
    if manifest is not None:
        owned.update(rank_fields(manifest, quote))
        owned.update(aura_text_fields(manifest, quote))
    values = values_by_row()
    owned.update(buff_marker_fields(values, quote))
    owned.update(class_buff_fields(values))
    for entry in value_map:
        row = value_row(values, entry)
        if row is None:
            problems.append("value map names %s/%s %s which no values sheet row has"
                            % (entry["skill"], entry["rune"], entry["token"]))
            continue
        number = float(row["value"])
        holder, slot = int(entry["holder_spell_id"]), int(entry["slot"])
        source = entry["source"]

        def claim(field, expected, holder=holder):
            previous = owned.get((holder, field))
            if previous is not None and previous != expected:
                problems.append("%d %s is claimed as both %s and %s"
                                % (holder, field, previous, expected))
            owned[(holder, field)] = expected

        if source == "base_points":
            claim("EffectBasePoints_%d" % slot, str(int(number) - 1))
            claim("EffectDieSides_%d" % slot, "1")
        elif source == "duration":
            wanted = int(round(number * 1000))
            index = next((key for key, value in sorted(durations.items())
                          if value == wanted), None)
            if index is None:
                problems.append("%d: no stock duration row of %d ms" % (holder, wanted))
            else:
                claim("DurationIndex", str(index))
        elif source == "radius":
            index = next((key for key, value in sorted(radii.items())
                          if abs(value - number) < 0.0005), None)
            if index is None:
                problems.append("%d: no stock radius row of %s yards" % (holder, row["value"]))
            else:
                claim("EffectRadiusIndex_1", str(index))
        elif source == "period":
            claim("EffectAuraPeriod_1", str(int(round(number * 1000))))
        elif source == "chain":
            # The core's ChainTarget counts the primary victim, so the sheet's
            # "three more enemies" is a four in the field: Spell.cpp:1892 at
            # the pin searches `maxTargets - 1` after the primary is already a
            # target (Architect, 2026-09-20). Every reader takes the one off.
            claim("EffectChainTargets_1", str(int(number) + 1))
        elif source == "proc_chance":
            claim("ProcChance", str(int(number)))
        elif source == "stacks":
            claim("CumulativeAura", str(int(number)))
        elif source == "charges":
            claim("ProcCharges", str(int(number)))
        elif source == "max_targets":
            claim("MaxTargets", str(int(number)))
        elif source == "cost":
            # Step 5's two intentional new deltas (decisions.md, 2026-09-20):
            # the cost in Rage units, ten per Fury point, and the power it is
            # paid from. Whirlwind has neither - the module still pays its
            # ticks - so no cost row of its own names these fields.
            claim("ManaCost", str(int(number * RAGE_PER_FURY)))
            claim("PowerType", str(POWER_RAGE))
        elif source == "cooldown":
            # Step 6: the skill's own recovery, in milliseconds, and the timer
            # its runes share - the core reads the second through Category and
            # installs it on every record of the family.
            claim("RecoveryTime", str(int(round(number * 1000))))
            claim("CategoryRecoveryTime", str(int(round(number * 1000))))
        elif source == "recharge":
            # A charge skill has no cooldown of its own; its recharge is the
            # shared timer, and the module clears it while a charge remains.
            claim("CategoryRecoveryTime", str(int(round(number * 1000))))
            claim("RecoveryTime", "0")
        elif source != "exact":
            problems.append("%d: unknown value source %r" % (holder, source))
    return owned, problems


def record_problems(names, before, after, owned):
    """Every field of every record: owned, free, or identical to the baseline."""
    at = {name: index for index, name in enumerate(names)}
    problems = []
    for identifier, published in sorted(after.items()):
        baseline = before.get(identifier)
        if (baseline is None and not HELPER_FIRST <= identifier <= HELPER_LAST
                and identifier not in APPENDED_SHELLS):
            problems.append("%d: a new record outside the helper block" % identifier)
        for field, index in at.items():
            value = published[index]
            expected = owned.get((identifier, field))
            if expected is not None:
                if value != expected:
                    problems.append("%d %s: the sheet says %s, the record says %s"
                                    % (identifier, field, expected, value))
                continue
            if field in FREE_FIELDS or baseline is None:
                continue
            if value != baseline[index]:
                problems.append("%d %s: changed %s -> %s and no sheet row owns it"
                                % (identifier, field, baseline[index], value))
    return problems


def slot_problems(names, before, after, owned):
    """A tooltip number only ever lands in a slot that was free for it."""
    at = {name: index for index, name in enumerate(names)}
    problems = []
    for (identifier, field), _expected in sorted(owned.items()):
        if (identifier, field) in CHILL_RULED_SLOTS:
            continue
        match = re.fullmatch(r"EffectBasePoints_(\d)", field)
        if not match:
            continue
        slot = match[1]
        baseline = before.get(identifier)
        if baseline is None:
            continue
        points = baseline[at[field]]
        sides = baseline[at["EffectDieSides_%s" % slot]]
        effect = int(baseline[at["Effect_%s" % slot]])
        aura = int(baseline[at["EffectAura_%s" % slot]])
        if points != "0" or sides != "0":
            problems.append("%d slot %s already held %s/%s before the writer"
                            % (identifier, slot, points, sides))
        elif effect not in FREE_EFFECTS and not (effect == 6 and aura == 4):
            problems.append("%d slot %s carries effect %d, which is not free for a number"
                            % (identifier, slot, effect))
    return problems


def duration_problems(names, before, after):
    """A written duration never lands on a record that applies an aura."""
    at = {name: index for index, name in enumerate(names)}
    problems = []
    for identifier, published in after.items():
        baseline = before.get(identifier)
        if baseline is None or baseline[at["DurationIndex"]] == published[at["DurationIndex"]]:
            continue
        for slot in (1, 2, 3):
            if int(published[at["Effect_%d" % slot]]) in AURA_EFFECTS:
                problems.append("%d: a duration was written onto an aura effect" % identifier)
    return problems


class SpellRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DBC.is_dir():
            raise unittest.SkipTest("client DBCs are not extracted")
        cls.sql = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
        cls.names, cls.now = parse(cls.sql)
        try:
            baseline = subprocess.run(["git", "show", f"{BASELINE}:{SHELLS}"], cwd=REPO_ROOT,
                                      capture_output=True, check=True).stdout.decode("utf-8")
        except (OSError, subprocess.CalledProcessError) as error:
            raise unittest.SkipTest("baseline %s unavailable: %s" % (BASELINE, error))
        _, cls.before = parse(baseline)
        cls.at = {name: index for index, name in enumerate(cls.names)}
        cls.value_map = [row for row in read_csv(GENERATED / "spell_value_map.csv")
                         if barbarian_id(row["spell_id"])]
        cls.manifest = [row for row in read_csv(GENERATED / "spell_shells.csv")
                        if barbarian_id(row["spell_id"])]
        cls.values = values_by_row()
        cls.durations = load_dbc_column("SpellDuration.dbc", 4)
        cls.radii = load_radii()
        cls.variables = parse_variables(VARIABLES_DBC.read_bytes())
        cls.owned, cls.owned_problems = owned_fields(cls.now, cls.value_map,
                                                     cls.durations, cls.radii,
                                                     cls.manifest)
        cls.owned.update(RULED_FIELDS)
        # Throwing Hammer's proc visual is the throwing_hammer_visual_id row (ruling 2026-09-29).
        cls.owned[(81191, "SpellVisualID_1")] = str(int(float(next(
            row["value"] for row in read_csv(REPO_ROOT / "mod-diablocraft" / "data" / "tunables" / "ability_tunables.csv")
            if row["name"] == "throwing_hammer_visual_id"))))
        # Whirlwind and its five runes spin with stock Bladestorm's visual (ruling 2026-10-11, diablocraft-vz49.3), read
        # from 46924's own record (SpellVisualID_1 is field 131). test_whirlwind_bladestorm_visual.py checks the rest.
        bladestorm = str(load_dbc_column("Spell.dbc", 131 * 4)[46924])
        cls.owned.update({(identifier, "SpellVisualID_1"): bladestorm for identifier in (81004, *range(81043, 81048))})
        cls.owned.update(ground_target_fields(cls.names, cls.before, cls.now))
        cls.owned.update(cleared_donor_fields(cls.names, cls.before, cls.now))
        cls.owned.update(passive_icon_fields())
        # The writer itself, so a rule of its own can be applied here rather
        # than restated (step 11: the unit `$d` supplies for itself).
        cls.gen = load_generator()

    def test_baseline_parsed(self):
        self.assertGreater(len(self.before), 300)
        self.assertGreaterEqual(len(self.now), len(self.before))
        self.assertEqual(self.owned_problems, [])

    def test_every_field_is_owned_free_or_unchanged(self):
        """The expected-delta contract, per record and per field."""
        self.assertEqual(record_problems(self.names, self.before, self.now, self.owned), [])

    def test_an_aura_tooltip_nobody_approved_is_caught(self):
        """The correction the PM's planted text earned.

        While `AuraDescription_Lang_enUS` was a free field, "Unapproved
        unrelated aura text." could be written onto 81000 and the contract
        returned nothing: the unit and binding sweeps say a sentence is well
        formed, never that it belongs on that record. The expectation is total
        now, so both halves fail - text on a record that should have none, and
        the wrong text on the one that should.
        """
        at = {name: index for index, name in enumerate(self.names)}
        field = at["AuraDescription_Lang_enUS"]

        def problems_with(identifier, text):
            planted = {key: list(values) for key, values in self.now.items()}
            planted[identifier][field] = quoted(text)
            return record_problems(self.names, self.before, planted, self.owned)

        # The PM's own plant, on a record with no business carrying one.
        found = problems_with(81000, "Unapproved unrelated aura text.")
        self.assertTrue([p for p in found if p.startswith("81000 AuraDescription_Lang_enUS")],
                        "an unapproved aura tooltip went unseen: %s" % found)
        # Any other record, so the check is not one id deep.
        self.assertTrue([p for p in problems_with(81310, "Attack speed increased by $s1%.")
                         if p.startswith("81310 AuraDescription_Lang_enUS")],
                        "the approved wording on the wrong record went unseen")
        # And the record that does have one has to say exactly what was ruled.
        for wrong in ("Attack speed increased by $s2%.",
                      "Attack speed increased by $s1% per stack.",
                      ""):
            self.assertTrue([p for p in problems_with(81196, wrong)
                             if p.startswith("81196 AuraDescription_Lang_enUS")],
                            "81196 reading %r went unseen" % wrong)
        # The real records still pass, so the plants above are what failed.
        self.assertEqual(record_problems(self.names, self.before, self.now, self.owned), [])

    def test_a_worn_buffs_text_is_exact_and_a_debuffs_is_none(self):
        """diablocraft-buff-text: Sprint's marker says Sprint's sentence, pointed at Sprint's
        record, and Threatening Shout's marker (an enemy-side debuff) says nothing."""
        field = self.at["AuraDescription_Lang_enUS"]
        ids = {row["name"]: int(row["spell_id"]) for row in self.manifest if row["kind"] == "ability_aura"}

        def problems_with(identifier, text):
            planted = {key: list(values) for key, values in self.now.items()}
            planted[identifier][field] = quoted(text)
            return [p for p in record_problems(self.names, self.before, planted, self.owned)
                    if p.startswith("%d AuraDescription_Lang_enUS" % identifier)]

        sprint = ids["Sprint"]
        self.assertEqual(self.now[sprint][field], quoted("Increase movement speed by $81009s1% for $81009d."))
        for wrong in ("Increase movement speed by $s1% for $d.", ""):
            self.assertTrue(problems_with(sprint, wrong), "Sprint reading %r went unseen" % wrong)
        self.assertTrue(problems_with(ids["Threatening Shout"], "Reduce damage dealt by $s1%."))

    def test_a_number_only_lands_in_a_slot_that_was_free(self):
        self.assertEqual(slot_problems(self.names, self.before, self.now, self.owned), [])

    def test_a_written_duration_never_lands_on_an_aura(self):
        self.assertEqual(duration_problems(self.names, self.before, self.now), [])

    def test_a_corrupted_number_is_caught(self):
        """The regression the PM found: a plausible wrong number in a live field."""
        corrupted = copy.deepcopy(self.now)
        corrupted[81004][self.at["EffectBasePoints_1"]] = "462"
        self.assertNotEqual(record_problems(self.names, self.before, corrupted, self.owned), [])
        # and the same number in a field the sheet DOES own is caught too
        owned_field = next(key for key in self.owned if key[1].startswith("EffectBasePoints_"))
        corrupted = copy.deepcopy(self.now)
        corrupted[owned_field[0]][self.at[owned_field[1]]] = "462"
        self.assertNotEqual(record_problems(self.names, self.before, corrupted, self.owned), [])

    def test_the_cost_is_in_the_record_and_the_core_can_read_it(self):
        """Step 5: every Fury cost the core pays is a field on the record.

        The sheets say Fury and the record counts Rage, ten to one - which is
        the same conversion the client uses to print the cost line, so a 25
        Fury skill shows 25. Whirlwind is the named exception (decisions.md,
        2026-09-20): the module charges its ticks, so its records carry no
        cost at all and its Fury number stays an exact value.
        """
        by_name = {(row["kind"], row["name"]): int(row["spell_id"]) for row in self.manifest}
        priced, whirlwind = 0, 0
        for entry in self.value_map:
            if entry["token"] != "cost_resource":
                continue
            identifier = int(entry["spell_id"])
            fury = float(value_row(self.values, entry)["value"])
            record = self.now[identifier]
            if entry["skill"] == "Whirlwind":
                self.assertEqual(entry["source"], "exact",
                                 "%d: Whirlwind's cost left the exact table" % identifier)
                self.assertEqual(record[self.at["ManaCost"]], "0",
                                 "%d: the core would charge a Whirlwind cast" % identifier)
                self.assertEqual(record[self.at["PowerType"]], "0")
                whirlwind += 1
                continue
            self.assertEqual(entry["source"], "cost")
            self.assertEqual(entry["conversion"], "rage_points")
            self.assertEqual(record[self.at["ManaCost"]], str(int(fury * RAGE_PER_FURY)),
                             "%d: the record does not carry %g Fury" % (identifier, fury))
            self.assertEqual(record[self.at["PowerType"]], str(POWER_RAGE))
            priced += 1
        self.assertEqual((priced, whirlwind), (41, 6),
                         "41 records priced, Whirlwind's six left to the module")
        # A rune inherits its skill's cost unless it states one of its own, and
        # the one rune whose sheet takes the cost away has none at all.
        self.assertEqual(self.now[by_name[("rune", "Seismic Slam - Stagger")]][self.at["ManaCost"]],
                         "22")
        self.assertEqual(self.now[by_name[("rune", "Seismic Slam - Rumble")]][self.at["ManaCost"]],
                         "30", "Rumble pays its skill's 30 Fury; the 15 is damage per Fury")
        self.assertEqual(
            self.now[by_name[("rune", "Earthquake - The Mountain's Call")]][self.at["ManaCost"]],
            "0", "its rune sheet removes the cost")

    def test_a_cost_in_the_wrong_units_is_caught(self):
        """The contract is the number itself, not the field being touched."""
        for wrong in ("250", "2", "20"):
            corrupted = copy.deepcopy(self.now)
            corrupted[81005][self.at["ManaCost"]] = wrong      # Ancient Spear, 25 Fury
            self.assertNotEqual(record_problems(self.names, self.before, corrupted, self.owned),
                                [], "ManaCost %s passed for a 25 Fury skill" % wrong)
        corrupted = copy.deepcopy(self.now)
        corrupted[81004][self.at["ManaCost"]] = "100"          # Whirlwind, module-paid
        self.assertNotEqual(record_problems(self.names, self.before, corrupted, self.owned), [],
                            "a Whirlwind cost the core would charge passed")

    def test_a_priced_record_cannot_miss(self):
        """What the core charges is what the module reports as spent.

        Spell::TakePower refunds all but irand(0, cost / 4) of a Rage cost when
        the target's miss condition is not NONE, BLOCK, ABSORB or REFLECT, and
        SPELL_ATTR3_ALWAYS_HIT is what takes miss, dodge and parry off that
        list (Unit::MeleeSpellHitResult, Unit::SpellHitResult). Immunity and
        evade remain reachable, which is why the module measures what the core
        took rather than trusting GetPowerCost().
        """
        ALWAYS_HIT = 0x00040000
        priced = 0
        for row in self.manifest:
            identifier = int(row["spell_id"])
            record = self.now[identifier]
            if record[self.at["ManaCost"]] == "0":
                continue
            self.assertTrue(int(record[self.at["AttributesEx3"]]) & ALWAYS_HIT,
                            "%s can miss and would be refunded a random part of its cost"
                            % row["name"])
            priced += 1
        self.assertEqual(priced, 41)

    def test_a_module_read_value_prints_nothing(self):
        """The channel terms are in the record and in no sentence."""
        in_map = [entry for entry in self.value_map
                  if entry["token"] in MODULE_READ and entry["token"] != "proc_coefficient"]
        procs = {entry["spell_id"] for entry in self.value_map if entry["token"] == "proc_coefficient"}
        self.assertGreaterEqual(len(procs), 138, "every Barbarian skill and rune answers a coefficient")
        self.assertEqual(len(in_map), 25,
                         "four terms on Whirlwind and its five runes, and the duration bonus")
        self.assertEqual([entry["token"] for entry in in_map].count("duration_bonus_pct"), 1,
                         "Inspiring Presence's duration bonus is not in the value map once")
        for entry in in_map:
            # A module-read value is stored the way any other value of its kind
            # is - the channel terms have no field and are exact, Inspiring
            # Presence's duration bonus is whole percent and lands in base
            # points like every other passive percentage - and what makes it
            # module-read is that no sentence prints it, which is what the rest
            # of this test checks.
            self.assertIn(entry["source"], ("exact", "base_points"), entry["token"])
            if entry["token"] != "duration_bonus_pct":
                self.assertEqual(entry["source"], "exact")
            # An exact value carries a variable name the way an inherited one
            # does, and like one it is never written to the client table below.
        for entries in self.variables.values():
            for name in entries:
                self.assertNotIn(name, MODULE_READ, "%s reached the client" % name)
        for _kind, name, skill, rune, text, _passive in sheet_rows():
            for token in MODULE_READ:
                self.assertNotIn("{%s}" % token, text, "%s prints %s" % (name, token))

    def test_the_cost_modifiers_reach_every_shell_and_carry_the_sheet(self):
        """The reductions are stock auras now, and they have to apply.

        A SPELLMOD only reaches a spell whose family matches and whose mask
        the modifier's own mask covers (SpellInfo::IsAffectedBySpellMod), so
        this checks both against the records the modifier has to reach, and
        the percentage against the passive's own sheet row.
        """
        modifiers = {row["name"]: int(row["spell_id"]) for row in self.manifest
                     if row["kind"] == "cost_modifier"}
        self.assertEqual(len(modifiers), 3, "three cost modifiers")
        percent_of = {}
        for row in read_csv(D3 / "barbarian_passive_values.csv"):
            if row["token"] == "cost_reduction_pct":
                percent_of[row["skill"]] = float(row["value"])
        mask = None
        for name, identifier in sorted(modifiers.items()):
            record = self.now[identifier]
            self.assertTrue(HELPER_FIRST <= identifier <= HELPER_LAST,
                            "%s is outside the reserved block" % name)
            self.assertEqual(record[self.at["Effect_1"]], "6")           # APPLY_AURA
            self.assertEqual(record[self.at["EffectAura_1"]], "108")     # ADD_PCT_MODIFIER
            self.assertEqual(record[self.at["EffectMiscValue_1"]], "14") # SPELLMOD_COST
            self.assertEqual(record[self.at["EffectDieSides_1"]], "0",
                             "%s: the amount has to be exact" % name)
            self.assertEqual(record[self.at["SpellClassSet"]], "20")
            owner = name.rsplit(" - cost modifier", 1)[0]
            expected = -int(percent_of.get(owner, 0))
            self.assertEqual(record[self.at["EffectBasePoints_1"]], str(expected),
                             "%s: the record disagrees with the passive's sheet row" % name)
            mask = int(record[self.at["EffectSpellClassMaskA_1"]]) if mask is None else mask
            self.assertEqual(int(record[self.at["EffectSpellClassMaskA_1"]]), mask,
                             "the three modifiers do not reach the same spells")
        self.assertEqual(sorted(percent_of), ["Relentless", "Sword and Board"],
                         "a third passive states a cost reduction and has no modifier")
        reached = 0
        for row in self.manifest:
            if row["kind"] not in ("active", "rune"):
                continue
            record = self.now[int(row["spell_id"])]
            if record[self.at["ManaCost"]] == "0":
                continue
            self.assertEqual(record[self.at["SpellClassSet"]], "20")
            self.assertTrue(int(record[self.at["SpellClassMask_1"]]) & mask,
                            "%s: no cost modifier can reach it" % row["name"])
            reached += 1
        self.assertEqual(reached, 41, "every priced record is reachable")

    def test_the_cooldown_category_groups_each_skill_and_collides_with_nothing(self):
        """Step 6: one category per skill, and no client spell shares it.

        `Category` is how the core makes a base skill and its five runes share
        one timer - `Player::AddSpellAndCategoryCooldowns` installs the cast
        record's `CategoryRecoveryTime` on every spell of the same category and
        family - which is what the module's own "loop the rune family" did. So
        the contract is: every record with a timer has one, every record of a
        skill has the SAME one, two skills never share, and no category the
        client's own Spell.dbc uses is one of ours.

        An id in the field is not yet a category, and the first version of this
        test missed that: `SpellInfo`'s constructor resolves it through
        `sSpellCategoryStore` (SpellInfo.cpp:789 at the pin) and `GetCategory`
        answers 0 when the lookup misses (SpellInfo.cpp:882), so an id with no
        SpellCategory.dbc row is no category at all and the core's sibling
        branch never runs. Every id therefore has to have a row, and the
        persisted map has to be the one the records were written from.
        `scripts/tests/classes/test_spell_categories.py` is where the sharing itself is
        proved by running the core's own store; this checks the artifact that
        store will be given.
        """
        timed = {int(entry["spell_id"]) for entry in self.value_map
                 if entry["source"] in ("cooldown", "recharge")}
        self.assertTrue(timed, "no record carries a cooldown")
        by_skill, categories = {}, {}
        for row in self.manifest:
            identifier = int(row["spell_id"])
            record = self.now.get(identifier)
            if record is None or row["kind"] not in ("active", "rune"):
                continue
            category = int(record[self.at["Category"]])
            if identifier not in timed:
                self.assertEqual(category, 0,
                                 "%s has no timer and still carries a category" % row["name"])
                continue
            self.assertNotEqual(category, 0, "%s has a timer and no category" % row["name"])
            skill = row["name"].split(" - ")[0]
            by_skill.setdefault(skill, set()).add(category)
            categories.setdefault(category, set()).add(skill)
        for skill, found in sorted(by_skill.items()):
            self.assertEqual(len(found), 1,
                             "%s: its runes are in %d categories, not one" % (skill, len(found)))
        for category, skills in sorted(categories.items()):
            self.assertEqual(len(skills), 1,
                             "category %d is shared by %s" % (category, sorted(skills)))
        # The client's own records. A collision would hand a stock spell our
        # cooldown, or ours a stock spell's, through the same store.
        client = load_dbc_column("Spell.dbc", 4)
        used = {value for identifier, value in client.items()
                if value and not (FIRST_SHELL <= identifier <= LAST_SHELL)}
        self.assertTrue(used, "Spell.dbc reports no categories at all")
        self.assertEqual(sorted(set(categories) & used), [],
                         "a Diablocraft cooldown category collides with the client's")

        # Every id the records use has a row in the SpellCategory.dbc the
        # writer emits, and every stock row is still there.
        rows = {identifier for identifier in dbc_ids(GENERATED_CATEGORY_DBC)
                if barbarian_category(identifier)}
        stock = set(dbc_ids(DBC / "SpellCategory.dbc"))
        self.assertEqual(sorted(set(categories) - rows), [],
                         "a cooldown category has no SpellCategory.dbc row, so the core "
                         "reads it back as no category at all")
        self.assertEqual(sorted(stock - rows), [], "a stock spell category was dropped")
        self.assertEqual(sorted(rows - stock - set(categories)), [],
                         "SpellCategory.dbc carries a row no record uses")
        for identifier in sorted(rows - stock):
            self.assertTrue(CATEGORY_FIRST <= identifier <= CATEGORY_LAST,
                            "category %d is outside the reserved block" % identifier)

        # The server gets the same eleven rows through the stock
        # `spellcategory_dbc` world-table override rather than a copied file
        # (Architect, 2026-09-20): DBCStores.cpp:357 names that table on
        # LOAD_DBC, the file loads first and the table is merged on top. Both
        # artifacts come out of the same map, so they have to agree.
        overlay = {}
        for statement in re.findall(
                r"INSERT INTO spellcategory_dbc \(ID,Flags\) VALUES ([^;]*);", self.sql):
            for identifier, flags in re.findall(r"\((\d+),(\d+)\)", statement):
                if barbarian_category(int(identifier)):
                    overlay[int(identifier)] = int(flags)
        self.assertEqual(sorted(overlay), sorted(categories),
                         "the SQL overlay and the records disagree on the categories")
        self.assertEqual(sorted(overlay), sorted(rows - stock),
                         "the SQL overlay and the generated DBC carry different rows")
        for identifier, flags in sorted(overlay.items()):
            self.assertEqual(flags, 0,
                             "category %d starts on an event, not on the cast" % identifier)
        # Since the second class the one DELETE spans every class's block; it
        # has to cover the Barbarian's whole block.
        cleared = re.search(r"DELETE FROM spellcategory_dbc WHERE ID BETWEEN (\d+) AND (\d+);",
                            self.sql)
        self.assertTrue(cleared and int(cleared[1]) <= CATEGORY_FIRST
                        and int(cleared[2]) >= CATEGORY_LAST,
                        "the overlay rows are added to rather than replaced")

        # And the persisted map is what the records were written from, so a
        # rerun cannot renumber a live cooldown group onto other spells.
        persisted = {row["skill"]: int(row["category"])
                     for row in read_csv(GENERATED / "spell_cooldown_categories.csv")
                     if row.get("class", "barbarian") == "barbarian"}
        self.assertEqual(len(persisted), len(set(persisted.values())),
                         "a category is mapped to two skills")
        self.assertEqual({skill: next(iter(found)) for skill, found in by_skill.items()},
                         persisted, "the persisted map and the records disagree")

        # And the client has to be told, which the core only does for the whole
        # category when the record carries this custom attribute; without it
        # the siblings get the cooldown silently, because ours have
        # RecoveryTime == CategoryRecoveryTime (Player.cpp's `catrec != rec`).
        forced = {}
        for statement in re.findall(
                r"INSERT INTO spell_custom_attr \(spell_id,attributes\) VALUES ([^;]*);", self.sql):
            for identifier, attributes in re.findall(r"\((\d+),(\d+)\)", statement):
                if barbarian_id(identifier):
                    forced[int(identifier)] = int(attributes)
        self.assertEqual(sorted(forced), sorted(timed),
                         "the forced-cooldown rows and the timed records disagree")
        for identifier, attributes in sorted(forced.items()):
            self.assertEqual(attributes, FORCE_SEND_CATEGORY_COOLDOWNS,
                             "%d carries some other custom attribute" % identifier)
        # The range runs to the highest record of any class since the second
        # class; it has to cover the Barbarian's whole span.
        cleared = re.search(r"DELETE FROM spell_custom_attr WHERE spell_id BETWEEN (\d+) AND (\d+);",
                            self.sql)
        self.assertTrue(cleared and int(cleared[1]) <= FIRST_SHELL and int(cleared[2]) >= LAST_SHELL,
                        "the custom attributes are not replaced, only added to")

    def test_every_rune_record_says_which_rune_it_is(self):
        """Step 8: the rune name is the record's own rank.

        The 3.3.5 client draws Rank in the top right of a tooltip and
        GetSpellInfo() returns it as its second value, so the rune name comes
        out of the record the client already has instead of out of a line the
        module drew itself. The contract is total - `rank_fields` gives every
        record one expected value and `record_problems` checks all of them -
        and this states what it says and proves it bites.
        """
        expected = rank_fields(self.manifest)
        self.assertEqual(len(expected), len(self.manifest),
                         "a record is missing from the rank contract")
        runes = {identifier: value for (identifier, _field), value in expected.items()
                 if value != "''"}
        self.assertEqual(len(runes), 115, "23 skills' five runes each")
        for row in self.manifest:
            identifier = int(row["spell_id"])
            if row["kind"] != "rune":
                continue
            rune = row["name"].partition(" - ")[2]
            self.assertEqual(runes[identifier], quoted("Rune: " + rune))
            self.assertEqual(self.now[identifier][self.at["NameSubtext_Lang_enUS"]],
                             quoted("Rune: " + rune),
                             "%s does not say which rune it is" % row["name"])
        # An internal shell named after a rune is not one a player picks.
        bleeds = [int(row["spell_id"]) for row in self.manifest
                  if row["kind"] == "bleed" and " - " in row["name"]]
        self.assertEqual(len(bleeds), 5, "Rend's five rune bleeds")
        for identifier in bleeds:
            self.assertEqual(self.now[identifier][self.at["NameSubtext_Lang_enUS"]], "''",
                             "%d is an internal shell and carries a rank" % identifier)
        # and a wrong rank is a failure, not a pass
        corrupted = {key: list(value) for key, value in self.now.items()}
        victim = next(iter(runes))
        corrupted[victim][self.at["NameSubtext_Lang_enUS"]] = quoted("Rune: Vanguard")
        self.assertNotEqual(record_problems(self.names, self.before, corrupted, self.owned), [],
                            "a rune wearing another rune's name passed")

    def test_the_client_record_carries_the_rank_the_sql_does(self):
        """The rank is only useful in the file the client reads.

        `spell_dbc` is the server's overlay and the core does not load this
        column at all (SpellEntry comments NameSubtext out as "not used"), so
        the tooltip's top right comes entirely from the Spell.dbc in the MPQ.
        One generator run writes both, and this is what proves they agree.
        """
        if not GENERATED_SPELL_DBC.exists():
            raise unittest.SkipTest("client-patch/dbc/Spell.dbc has not been generated")
        ranks = load_dbc_strings(GENERATED_SPELL_DBC, self.at["NameSubtext_Lang_enUS"])
        for row in self.manifest:
            identifier = int(row["spell_id"])
            self.assertIn(identifier, ranks, "%d is not in the client Spell.dbc" % identifier)
            wanted = ("Rune: " + row["name"].partition(" - ")[2]
                      if row["kind"] == "rune" else "")
            self.assertEqual(ranks[identifier], wanted,
                             "%s: the client record and the SQL disagree" % row["name"])
        # nothing of Blizzard's lost its own rank on the way through
        stock = [identifier for identifier, text in ranks.items()
                 if identifier < FIRST_SHELL and text]
        self.assertGreater(len(stock), 1000, "the stock ranks were dropped")

    # (spell, the record's own token, the skill it belongs to, what the number
    # is). The three side effects the step 8 ruling protects.
    SIDE_EFFECTS = (
        (81108, "duration_seconds", "War Cry", "the armour window"),
        (81118, "duration_seconds", "Threatening Shout", "the taunt"),
        (81122, "fear_duration_seconds", "Threatening Shout", "the fear"),
    )

    def test_a_side_effect_duration_is_out_of_the_modifier_s_reach(self):
        """Architect ruling, decisions.md 8d89601.

        Inspiring Presence doubles what a record's DurationIndex holds, and it
        reaches every record of a shout. Three of those records' own duration
        is a side effect inside the shout - Hardened Wrath's armour window,
        Demoralize's taunt, Terrify's fear - and must not double. So the field
        holds the SHOUT's duration, which the rune inherits from its skill,
        and the record's own number is an exact value the sentence renders as
        $<name> and the module reads as the same literal.
        """
        sheet_of = {}
        for spell, token, skill, _what in self.SIDE_EFFECTS:
            rune = self.manifest[[int(row["spell_id"]) for row in self.manifest].index(spell)]
            rune_name = rune["name"].partition(" - ")[2]
            own = next(value for value in self.values[(skill, rune_name, False)]
                       if value["token"] == token)
            sheet_of[spell] = float(own["value"])
            entries = [entry for entry in self.value_map
                       if int(entry["spell_id"]) == spell and entry["token"] == token]
            states = [entry for entry in entries if entry["origin"] == "own"]
            self.assertEqual(len(states), 1, "%d states %s once" % (spell, token))
            self.assertEqual(states[0]["source"], "exact",
                             "%d %s is still in a field a modifier moves" % (spell, token))
            self.assertEqual(states[0]["variable"], token,
                             "%d %s renders no $<name>" % (spell, token))
            # the sentence asks for it by name, and never as $d
            sentence = self.now[spell][self.at["Description_Lang_enUS"]]
            self.assertIn("$<%s>" % token, sentence, "%d does not render its own number" % spell)
            # the client can resolve that name
            variables = self.variables[int(self.now[spell][self.at["SpellDescriptionVariableID"]])]
            self.assertEqual(float(variables[token]), float(own["value"]),
                             "%d: the client variables row is not the sheet number" % spell)
            # and the server reads the same literal
            published = dict(((int(a), b, c), d) for a, b, c, d in
                             re.findall(r"\((\d+),'([a-z_]+)','([a-z_]*)',([0-9.]+)\)", self.sql))
            self.assertEqual(float(published[(spell, token, "")]), float(own["value"]),
                             "%d: dc_spell_values does not hold the same literal" % spell)

        # the field now holds the SHOUT's duration, inherited from the skill
        for spell, _token, skill, _what in self.SIDE_EFFECTS:
            base = next(int(row["spell_id"]) for row in self.manifest
                        if row["kind"] == "active" and row["name"] == skill)
            self.assertEqual(self.now[spell][self.at["DurationIndex"]],
                             self.now[base][self.at["DurationIndex"]],
                             "%d does not carry %s's own duration" % (spell, skill))
            self.assertNotEqual(self.durations[int(self.now[spell][self.at["DurationIndex"]])],
                                int(sheet_of[spell] * 1000),
                                "%d's field still holds its side effect" % spell)

    def test_the_shout_records_the_modifier_reaches_all_hold_a_shout_duration(self):
        """Nothing a shout's mask reaches may hold a number that must not move.

        This is the general form of the ruling, checked over every record the
        duration modifier can reach rather than over the three it was written
        for: if a sheet edit puts another side effect on a DurationIndex under
        a shout's bit, this is what says so.
        """
        modifier = next(int(row["spell_id"]) for row in self.manifest
                        if row["kind"] == "duration_modifier")
        mask = int(self.now[modifier][self.at["EffectSpellClassMaskA_1"]])
        bit_of = {row["name"]: int(self.now[int(row["spell_id"])][self.at["SpellClassMask_1"]])
                  for row in self.manifest if row["kind"] == "active"}
        shouts = {skill: bit for skill, bit in bit_of.items() if bit & mask}
        self.assertEqual(sorted(shouts), ["Battle Rage", "Threatening Shout", "War Cry"])
        own_durations = {skill: self.durations[int(self.now[
            next(int(row["spell_id"]) for row in self.manifest
                 if row["kind"] == "active" and row["name"] == skill)][self.at["DurationIndex"]])]
            for skill in shouts}
        checked, infinite = 0, 0
        for row in self.manifest:
            spell = int(row["spell_id"])
            if spell not in self.now or int(self.now[spell][self.at["SpellClassSet"]]) != 20:
                continue
            bit = int(self.now[spell][self.at["SpellClassMask_1"]])
            skill = next((name for name, value in shouts.items() if value & bit), None)
            if skill is None:
                continue
            index = int(self.now[spell][self.at["DurationIndex"]])
            if not index:
                continue
            held = self.durations[index]
            # An infinite duration is never modified: Aura::CalcMaxDuration
            # applies SPELLMOD_DURATION only `if (maxDuration != -1 &&
            # modOwner)` (SpellAuras.cpp:809 at the core pin), so a record the
            # module gives its own duration to is out of reach either way.
            if held == -1:
                infinite += 1
                continue
            # Either the skill's own duration, or a rune's own SHOUT duration
            # that its values sheet states - Falter's 6 s is Threatening Shout
            # made shorter, not a side effect inside it.
            if held != own_durations[skill]:
                rune = row["name"].partition(" - ")[2]
                stated = [value["value"] for value in self.values.get((skill, rune, False), [])
                          if value["token"] == "duration_seconds"]
                self.assertEqual([int(float(value) * 1000) for value in stated], [held],
                                 "%s holds %d ms, which is neither %s's duration nor its own "
                                 "stated shout duration" % (row["name"], held, skill))
            checked += 1
        self.assertGreaterEqual(checked + infinite, 38,
                                "the modifier reaches fewer records than it did")
        self.assertGreater(checked, 0, "no finite duration was checked at all")

    def test_the_duration_modifier_carries_the_sheet_and_names_its_skills(self):
        """Step 8: "the duration of your shouts is doubled" is a modifier.

        The same shape as the cost and cooldown modifiers: a hidden aura on
        the player whose amount is the sheet's percentage and whose mask names
        the skills it reaches. What the core makes of it is
        test_cost_math's to prove; this is the record it is given.
        """
        modifiers = [row for row in self.manifest if row["kind"] == "duration_modifier"]
        self.assertEqual([row["name"] for row in modifiers],
                         ["Inspiring Presence - duration modifier"])
        record = self.now[int(modifiers[0]["spell_id"])]
        field = lambda name: record[self.at[name]]
        self.assertEqual(int(field("Effect_1")), 6, "SPELL_EFFECT_APPLY_AURA")
        self.assertEqual(int(field("EffectAura_1")), 108, "SPELL_AURA_ADD_PCT_MODIFIER")
        self.assertEqual(int(field("EffectMiscValue_1")), 1, "SPELLMOD_DURATION")
        self.assertEqual(int(field("EffectDieSides_1")), 0, "the amount is exact")
        self.assertEqual(int(field("ImplicitTargetA_1")), 1, "TARGET_UNIT_CASTER")
        self.assertEqual(int(field("SpellClassSet")), 20)
        for slot in ("2", "3"):
            self.assertEqual(int(field("Effect_%s" % slot)), 0,
                             "the donor's other effects came along")
        # the amount is the sheet's, and no sentence prints it
        sheet = next(value for value in self.values[("Inspiring Presence", "", True)]
                     if value["token"] == "duration_bonus_pct")
        self.assertEqual(int(field("EffectBasePoints_1")), int(float(sheet["value"])))
        self.assertEqual(sheet["unit"], "pct")
        # the mask reaches the three shouts and no other skill
        bit_of = {row["name"]: int(self.now[int(row["spell_id"])][self.at["SpellClassMask_1"]])
                  for row in self.manifest if row["kind"] == "active"}
        mask = int(field("EffectSpellClassMaskA_1"))
        self.assertEqual(sorted(skill for skill, bit in bit_of.items() if bit & mask),
                         ["Battle Rage", "Threatening Shout", "War Cry"])
        self.assertEqual(mask & ~sum(bit_of.values()), 0, "the mask holds a bit of nobody's")
        # and the aura never expires, so a refresh is the only thing that ends it
        self.assertEqual(self.durations[int(field("DurationIndex"))], -1,
                         "the modifier expires on its own")

    def test_the_cooldown_modifiers_carry_the_sheet_and_name_their_skills(self):
        """Step 6: every cooldown reduction is a SPELLMOD_COOLDOWN aura.

        Boon of Bul-Kathos takes a different number of seconds off each of the
        three skills it names and a spell modifier carries one amount, so it is
        one record per amount with that amount's skills in its mask. The third
        record is the percentage the module keeps in step with the sheet's item
        and paragon Cooldown Reduction, and it has to reach every skill.
        """
        modifiers = {row["name"]: int(row["spell_id"]) for row in self.manifest
                     if row["kind"] == "cooldown_modifier"}
        self.assertEqual(len(modifiers), 3, "two Boon amounts and the gear percentage")
        bit_of = {row["name"]: int(self.now[int(row["spell_id"])][self.at["SpellClassMask_1"]])
                  for row in self.manifest if row["kind"] == "active"}
        every = 0
        for bit in bit_of.values():
            every |= bit
        # The sheet's own rows, by the number of seconds each one takes off.
        wanted = {}
        for row in read_csv(D3 / "barbarian_passive_values.csv"):
            if row["skill"] != "Boon of Bul-Kathos" or row["token"] != "cooldown_reduction_seconds":
                continue
            skill = next(name for name in bit_of
                         if name.lower().replace(" ", "_").replace("'", "") == row["qualifier"])
            wanted.setdefault(int(float(row["value"]) * 1000), 0)
            wanted[int(float(row["value"]) * 1000)] |= bit_of[skill]
        self.assertEqual(len(wanted), 2, "the sheet stopped naming two amounts")
        for name, identifier in sorted(modifiers.items()):
            record = self.now[identifier]
            self.assertTrue(HELPER_FIRST <= identifier <= HELPER_LAST,
                            "%s is outside the reserved block" % name)
            self.assertEqual(record[self.at["Effect_1"]], "6")             # APPLY_AURA
            self.assertEqual(record[self.at["EffectMiscValue_1"]], "11")   # SPELLMOD_COOLDOWN
            self.assertEqual(record[self.at["EffectDieSides_1"]], "0",
                             "%s: the amount has to be exact" % name)
            self.assertEqual(record[self.at["SpellClassSet"]], "20")
            amount = int(record[self.at["EffectBasePoints_1"]])
            mask = int(record[self.at["EffectSpellClassMaskA_1"]])
            if name.startswith("Boon of Bul-Kathos"):
                self.assertEqual(record[self.at["EffectAura_1"]], "107")   # ADD_FLAT_MODIFIER
                self.assertIn(-amount, wanted, "%s: no sheet row states %d ms" % (name, -amount))
                self.assertEqual(mask, wanted[-amount],
                                 "%s: its mask is not the skills the sheet names" % name)
                self.assertEqual("%s - cooldown modifier %ds" % ("Boon of Bul-Kathos",
                                                                 -amount // 1000), name)
            else:
                self.assertEqual(record[self.at["EffectAura_1"]], "108")   # ADD_PCT_MODIFIER
                self.assertEqual(amount, 0, "the gear amount is cast in, not written")
                self.assertEqual(mask, every, "the gear reduction has to reach every skill")
        timed = {int(entry["spell_id"]) for entry in self.value_map
                 if entry["source"] in ("cooldown", "recharge")}
        for identifier in sorted(timed):
            self.assertTrue(int(self.now[identifier][self.at["SpellClassMask_1"]]) & every,
                            "%d has a cooldown no gear reduction can reach" % identifier)

    def test_every_sentence_is_the_sheet_sentence_with_marks(self):
        """Each placeholder renders the mark of ITS key, not of its position."""
        by_name = {(row["kind"], row["name"]): int(row["spell_id"]) for row in self.manifest}
        mark_of = {}
        for entry in self.value_map:
            if entry["origin"] != "own":
                continue
            identifier = int(entry["spell_id"])
            slot, holder = int(entry["slot"]), int(entry["holder_spell_id"])
            source = entry["source"]
            if source == "base_points":
                mark = "$s%d" % slot if holder == identifier else "$%ds%d" % (holder, slot)
            elif source == "duration":
                mark = "$d"
            elif source == "radius":
                mark = "$a1"
            elif source == "period":
                mark = "$t1"
            elif source == "chain":
                # Not a copied variables row: the client's own arithmetic on
                # the field, so the sentence prints the additional enemies the
                # sheet states while the record keeps the core's count.
                mark = "${$x1-1}"
            elif source == "proc_chance":
                mark = "$h"
            elif source == "stacks":
                mark = "$u"
            elif source == "charges":
                mark = "$n"
            elif source == "max_targets":
                mark = "$i"
            else:
                # The writer names a client variable after its token, whether
                # or not a row was written for it - step 7 stopped writing one
                # for a cost or cooldown whose line the client prints itself.
                mark = "$<%s>" % (entry["token"] +
                                  ("_" + entry["qualifier"] if entry["qualifier"] else ""))
            mark_of[(identifier, entry["token"], entry["qualifier"])] = mark
        checked, dropped = 0, 0
        for kind, name, skill, rune, text, passive in sheet_rows():
            identifier = by_name.get((kind, name))
            if identifier is None:
                continue
            rows = self.values.get((skill, rune, passive), [])
            marks = {}
            rows = printed(rows)
            for row in rows:
                mark = mark_of.get((identifier, row["token"], row["qualifier"]))
                self.assertIsNotNone(mark, "%d: %s has no value map entry" % (identifier, row["token"]))
                marks[(row["token"], row["qualifier"])] = mark + ("%" if row["unit"] == "pct" else "")
            body, _, _ = text.partition("Unlocked")
            keys = re.findall(r"\{([a-z_]+)(?::([a-z_]+))?\}", body)
            self.assertEqual([(token, qualifier or "") for token, qualifier in keys],
                             [(row["token"], row["qualifier"]) for row in rows],
                             "%s: the sentence and the values sheet disagree" % name)
            expected = re.sub(r"\{([a-z_]+)(?::([a-z_]+))?\}",
                              lambda match: marks[(match[1], match[2] or "")], body)
            # Step 11: the sheet still writes "for {duration_seconds} seconds"
            # because the sheet is prose, and the writer takes the unit off
            # once the token has become `$d`, which supplies its own. The
            # generator's OWN function is applied here rather than a copy of
            # its rule, so the sentence contract cannot drift from it.
            # Step 12: the same function, and the period it reads is the
            # RECORD's own field rather than a number restated here, so the
            # one-second rule cannot drift from the writer either.
            expected = self.gen.spell_out_units(
                expected, int(self.now[identifier][self.at["EffectAuraPeriod_1"]]))
            parts = [piece.strip() for piece in expected.split("|") if piece.strip()]
            published = self.now[identifier][self.at["Description_Lang_enUS"]].strip("'")
            published = published.replace("''", "'").replace("\\r\\n", "\n").replace("\\\\", "\\")
            record = self.now[identifier]
            for part in parts:
                if part.lower() in ("primary", "secondary", "defensive", "might",
                                    "tactics", "rage", "passive"):
                    continue
                # Step 7: the client builds a cost line from ManaCost and
                # PowerType and a cooldown line from RecoveryTime and the
                # category timer, so a sentence that carries the same label
                # line would say it twice and the writer drops it. Whether it
                # is dropped is the RECORD's answer, re-derived here from the
                # fields rather than from the writer's own rule: Whirlwind is
                # still paid by the module tick by tick and has no ManaCost,
                # so it keeps its line, and so does a cost paid in charges,
                # which no field holds and the client cannot print.
                label = re.match(r"(Cost|Cooldown)\s*:\s*\$<([a-z_]+)>", part)
                if label and label[2] == "cost_resource":
                    says_it_twice = int(float(record[self.at["ManaCost"]])) != 0
                elif label and label[2] == "cooldown_seconds":
                    says_it_twice = bool(int(record[self.at["RecoveryTime"]])
                                         or int(record[self.at["CategoryRecoveryTime"]]))
                else:
                    says_it_twice = False
                if says_it_twice:
                    self.assertNotIn(part.replace("''", "'"), published,
                                     "%d %s: the record prints this line and the sentence "
                                     "says it a second time" % (identifier, name))
                    dropped += 1
                    continue
                self.assertIn(part.replace("''", "'"), published,
                              "%d %s: the sentence is not the sheet's" % (identifier, name))
            # A brace that is not the client's own ${...} expression is a
            # placeholder nobody rendered.
            self.assertIsNone(re.search(r"(?<!\$)\{", published),
                              "%d: an unrendered placeholder" % identifier)
            checked += 1
        self.assertEqual(checked, 157, "every barbarian row is checked")
        self.assertEqual(dropped, DROPPED_LINES,
                         "the number of lines the record prints for itself moved")

    def test_the_frenzy_buff_the_player_wears_says_what_a_stack_is_worth(self):
        """Spell rewrite 13, option A, on the record the module actually applies.

        Two records are called Frenzy and both are dummy auras, which is how
        they came to be confused: 81310 is the marker the SKILL sentence
        cross-references for its number (`$81310s1`), and 81196 is the aura the
        player wears - `FRENZY_BUFF` in dc_barbarian_primary_data.h. The buff tooltip is
        81196's, so the sentence and the number go there, and the constant is
        read out of the module here so the two cannot drift apart.
        """
        buff = int(re.search(r"FRENZY_BUFF = (\d+);", PRIMARY_DATA).group(1))
        self.assertEqual(buff, 81196, "the module wears a different aura now")
        record = self.now[buff]
        self.assertEqual(record[self.at["AuraDescription_Lang_enUS"]],
                         "'Attack speed increased by $s1%.'",
                         "the buff the player hovers has no aura text again")
        # The numbers are the sheet's, not this test's: one stack's worth in
        # $s1, and the sourced maximum in the record's own StackAmount.
        rows = {row["token"]: row for row in values_by_row()[("Frenzy", "", False)]}
        per_stack = int(float(rows["attack_speed_pct"]["value"]))
        stacks = int(float(rows["max_stacks_count"]["value"]))
        self.assertEqual(int(record[self.at["EffectBasePoints_1"]])
                         + int(record[self.at["EffectDieSides_1"]]), per_stack,
                         "$s1 on the buff is not one stack's worth of attack speed")
        self.assertEqual(int(record[self.at["CumulativeAura"]]), stacks,
                         "the buff record does not carry the sourced stack maximum")
        # StackAmount is not decoration: AuraApplication::BuildUpdatePacket sends
        # `StackAmount ? GetStackAmount() : GetCharges()`, so a zero there means
        # the client is told a count of zero however many stacks the module holds.
        self.assertGreater(int(record[self.at["CumulativeAura"]]), 0)
        # And the marker keeps its separate job, so a later edit cannot quietly
        # swap the two roles.
        self.assertIn("$%ds1" % 81310, self.now[81000][self.at["Description_Lang_enUS"]],
                      "the skill sentence no longer reads its number from the marker")

    def test_the_frenzy_stack_path_and_its_haste_are_untouched(self):
        """Display only: the module counts and computes exactly as it did.

        None of this is executed here - it needs a player, a weapon and a swing
        - so it is read, and labelled as read. What it is looking for is that
        the aura is still a marker the module writes to, and never a number the
        module takes its arithmetic from.
        """
        # g0n7f moved both writes into ShowFrenzy(), which takes the count as its
        # own parameter - and Punish below holds an identical SetStackAmount for a
        # different record, so the pins are read inside ShowFrenzy's braces.
        body = PRIMARIES[PRIMARIES.index("void ShowFrenzy("):]
        body = body[:body.index("\n        }\n")]
        self.assertIn("aura = player->AddAura(D::FRENZY_BUFF, player);", body,
                      "the buff aura is no longer applied by the module")
        self.assertIn("aura->SetStackAmount(uint8(stacks));", body,
                      "the module no longer tells the client how many stacks there are")
        self.assertIn("buff.frenzy = std::min(buff.frenzy + 1, cap);",
                      PRIMARIES, "the stack clamp changed")
        # diablocraft-pl8fc: the stacks are Frenzy's own for Frenzy, Echoing Fury's for every other attack (test_primary_provider.py runs it).
        self.assertIn("return std::min(D::aps_cap, base * (1 + stacks * D::frenzy_ias_pct / 100));", PRIMARIES,
                      "the haste arithmetic changed; this task is display only")
        # The constants behind 15/30/45/60/75, from the module rather than here.
        self.assertIn("frenzy_ias_pct = 15", PRIMARY_DATA)
        self.assertIn("frenzy_max_stacks = 5", PRIMARY_DATA)
        # And the sheet agrees with the module, which is what makes 45% at three
        # stacks the same number in both places.
        rows = {row["token"]: row for row in values_by_row()[("Frenzy", "", False)]}
        self.assertEqual(int(float(rows["attack_speed_pct"]["value"])), 15)
        self.assertEqual(int(float(rows["max_stacks_count"]["value"])), 5)
        # Nothing reads the aura's own amount: the record's number is for the
        # client to print, and the server's copy of it is never consulted.
        frenzy = PRIMARIES[PRIMARIES.index("D::FRENZY_BUFF"):]
        self.assertNotIn("GetEffect(", frenzy.split("LOG_INFO")[0],
                         "the module started reading the buff aura's amount")

    def test_a_one_second_period_is_a_word_and_never_a_number(self):
        """Step 12, Architect 2026-09-21: "every second", not "every 1 second".

        D3 does not write the 1. The two rows that have one are Battle Rage -
        Bloodshed and Unforgiving, but nothing here names them: the rule is
        read off every published record, so a third row with a one-second
        period is covered the day it is written.
        """
        period, sentence = self.at["EffectAuraPeriod_1"], self.at["Description_Lang_enUS"]
        one_second, others = 0, 0
        for identifier, values in self.now.items():
            text = values[sentence]
            if int(values[period]) == 1000:
                self.assertNotIn("$t1", text,
                                 "%d has a one-second period and still prints the number" % identifier)
                one_second += 1
            elif "$t1" in text:
                # Every other period keeps its number AND its spelled-out unit.
                self.assertIn("$t1 seconds", text,
                              "%d prints a period without the word seconds" % identifier)
                others += 1
        self.assertGreater(one_second, 0, "no record has a one-second period: the test proves nothing")
        # And the two the ruling names read the way it says they should.
        for identifier, phrase in ((81117, "every second."), (81152, "Fury every second.")):
            self.assertIn(phrase, self.now[identifier][sentence],
                          "%d does not read the way the ruling says" % identifier)

    def test_the_one_second_rule_is_the_records_period_and_not_the_sheets_wording(self):
        """The function itself, both branches, in isolation.

        The sheet writes "every {interval_seconds} second" either way; what
        decides is the period the record carries. And the rule only collapses
        the phrase it is for: a sentence that says something else about a
        period keeps its number, so nothing is lost by accident.
        """
        bound = "Deal damage every $t1 second."
        self.assertEqual(self.gen.spell_out_units(bound, 1000), "Deal damage every second.")
        self.assertEqual(self.gen.spell_out_units(bound, 2000), "Deal damage every $t1 seconds.")
        self.assertEqual(self.gen.spell_out_units(bound), "Deal damage every $t1 seconds.")
        self.assertEqual(self.gen.spell_out_units("Ticks for $t1 seconds.", 1000),
                         "Ticks for $t1 seconds.")
        # The duration rule is untouched by it, in either direction.
        self.assertEqual(self.gen.spell_out_units("for $d seconds every $t1 second.", 1000),
                         "for $d every second.")

    def test_a_field_backed_number_matches_the_sheet_number(self):
        """Read each mark back out of the record and compare with the sheet."""
        for entry in self.value_map:
            row = value_row(self.values, entry)
            number = float(row["value"])
            holder = self.now[int(entry["holder_spell_id"])]
            source, slot = entry["source"], int(entry["slot"])
            if source == "base_points":
                read = int(holder[self.at["EffectBasePoints_%d" % slot]]) + \
                    int(holder[self.at["EffectDieSides_%d" % slot]])
            elif source == "duration":
                read = self.durations[int(holder[self.at["DurationIndex"]])] / 1000.0
            elif source == "radius":
                read = self.radii[int(holder[self.at["EffectRadiusIndex_1"]])]
            elif source == "period":
                read = int(holder[self.at["EffectAuraPeriod_1"]]) / 1000.0
            elif source == "chain":
                read = int(holder[self.at["EffectChainTargets_1"]]) - 1
            elif source == "proc_chance":
                read = int(holder[self.at["ProcChance"]])
            elif source == "stacks":
                read = int(holder[self.at["CumulativeAura"]])
            elif source == "charges":
                read = int(holder[self.at["ProcCharges"]])
            elif source == "max_targets":
                read = int(holder[self.at["MaxTargets"]])
            elif entry["origin"] != "own" or entry["token"] in MODULE_READ:
                # An inherited exact value, and a value stated for the module
                # alone, have no placeholder to render: they live in
                # dc_spell_values, which the exact-table test compares with the
                # sheet.
                continue
            elif source in ("cost", "cooldown", "recharge") and not entry["variable"]:
                # Step 7: the sentence no longer prints a copy, so the FIELD is
                # the check - which is the whole point of the step.
                read = (int(holder[self.at["ManaCost"]]) / RAGE_PER_FURY if source == "cost"
                        else int(holder[self.at["RecoveryTime"] if source == "cooldown"
                                        else "CategoryRecoveryTime"]) / 1000.0)
            else:
                identifier = int(holder[self.at["SpellDescriptionVariableID"]])
                self.assertIn(identifier, self.variables,
                              "%s: no client variables row" % entry["spell_id"])
                self.assertEqual(self.variables[identifier][entry["variable"]], row["value"],
                                 "%s %s: the client variable differs from the sheet"
                                 % (entry["spell_id"], entry["variable"]))
                continue
            self.assertAlmostEqual(read, number, places=3,
                                   msg="%s %s %s: the record reads %s, the sheet says %s"
                                   % (entry["spell_id"], entry["token"], source, read, row["value"]))

    def test_a_chain_token_is_the_additional_enemies_and_the_field_is_one_more(self):
        """The record counts the primary, the sheet and the sentence do not.

        Spell::SelectImplicitChainTargets at the pin reads the field on
        Spell.cpp:1879, enters only on 1883's `maxTargets > 1` and searches
        `maxTargets - 1` further units on 1892, under the comment "Chain
        primary target is added earlier" - the primary was added by the
        caller (Spell.cpp:1229 and 1863). So a field of four hits four: the
        victim plus three. The sheet states the three, the field holds the
        four, and every reader takes the one back off (Architect,
        decisions.md 2026-09-20). This is the field-and-sentence half; the
        accessor is test_spell_numbers and the native count is
        test_chain_targets.
        """
        chain = [entry for entry in self.value_map if entry["source"] == "chain"]
        self.assertTrue(chain, "no chain token is written any more")
        for entry in chain:
            identifier = int(entry["holder_spell_id"])
            stated = float(value_row(self.values, entry)["value"])
            field = int(self.now[identifier][self.at["EffectChainTargets_1"]])
            self.assertEqual(field, int(stated) + 1,
                             "%d: the sheet says %g more enemies and the field says %d"
                             % (identifier, stated, field))
            self.assertGreater(field, 1, "%d: the core never chains on a field of one" % identifier)
            self.assertEqual(entry["conversion"], "field_minus_one",
                             "%d: the index does not record the conversion" % identifier)
            self.assertEqual(int(entry["slot"]), 1)
        # The writer touches this field on the sheet's records and on the
        # shells whose donor count it zeroes (GitHub #52, RULED_FIELDS names
        # each with its exact 0), and nowhere else. Hammer of the Ancients and
        # Cleave were cloned from spells that chain; the module resolves their
        # targets, so the donor's count is gone and nothing else moved.
        holders = {int(entry["holder_spell_id"]) for entry in chain}
        ruled = {identifier for identifier, field in RULED_FIELDS if field == "EffectChainTargets_1"}
        for identifier in ruled:
            self.assertEqual(self.now[identifier][self.at["EffectChainTargets_1"]], "0",
                             "%d: a ruled chain count is not zero" % identifier)
        moved = {identifier for identifier, record in self.now.items()
                 if identifier in self.before
                 and record[self.at["EffectChainTargets_1"]]
                 != self.before[identifier][self.at["EffectChainTargets_1"]]}
        self.assertEqual(moved - holders, ruled & set(self.before),
                         "the writer moved a chain count no values sheet row states and no ruling zeroes")
        # A holder whose field did not move is the interesting case: Ricochet's
        # four was already in the record, put there by primary_spells.py from
        # the retired primary_mechanics.csv copy. The number did not change -
        # its home did, which is the whole point of the correction.
        self.assertNotIn(81029, moved, "Ricochet's four was always four")

    def test_the_chain_sentence_renders_the_sheet_number_not_the_field(self):
        """Evaluate the client's own ${$x1-1} against the published record."""
        expression = re.compile(r"\$\{\$x(\d)-1\}")
        checked = 0
        for entry in self.value_map:
            if entry["source"] != "chain" or entry["origin"] != "own":
                continue
            identifier = int(entry["spell_id"])
            published = self.now[identifier][self.at["Description_Lang_enUS"]]
            match = expression.search(published)
            self.assertIsNotNone(match, "%d: its sentence does not do the arithmetic" % identifier)
            self.assertEqual(int(match[1]), int(entry["slot"]),
                             "%d: the expression reads another effect's chain count" % identifier)
            field = int(self.now[int(entry["holder_spell_id"])][self.at["EffectChainTargets_1"]])
            rendered = field - 1
            self.assertEqual(rendered, int(float(value_row(self.values, entry)["value"])),
                             "%d: the rendered sentence is not the sheet's number" % identifier)
            # And the plain mark is never left in a sentence on its own, which
            # would print the core's count as if it were D3's.
            self.assertIsNone(re.search(r"(?<!\{)\$x\d", published),
                              "%d: a bare $x prints the primary as an extra enemy" % identifier)
            checked += 1
        self.assertTrue(checked, "no sentence prints a chain count")

    def test_the_retired_chain_duplicate_is_gone(self):
        """The values sheet is the single home; the tunable copy is retired."""
        mechanics = REPO_ROOT / "mod-diablocraft" / "data" / "tunables" / "primary_mechanics.csv"
        keys = {row["key"] for row in read_csv(mechanics)}
        self.assertNotIn("ricochet_targets", keys,
                         "the derived four is a second home for the chain count")
        generated = (REPO_ROOT / "mod-diablocraft" / "src" / "classes" / "barbarian"
                     / "dc_barbarian_primary_data.h").read_text(encoding="utf-8")
        self.assertNotIn("ricochet_targets", generated)
        stated = [row for row in read_csv(D3 / "barbarian_skill_values.csv")
                  if row["token"] == "target_count"]
        self.assertTrue(stated, "the values sheet no longer states a chain count")
        for row in stated:
            self.assertIn("excludes the primary", row["source"],
                          "%s: the sheet does not say what its count counts" % row["rune"])

    def test_the_exact_table_holds_the_exceptions_and_nothing_else(self):
        """No field-backed number gets a second, competing home in SQL."""
        rows = re.findall(r"\((\d+),'([a-z_]+)','([a-z_]*)',([0-9.]+)\)", self.sql)
        published = {(int(spell), token, qualifier): value
                     for spell, token, qualifier, value in rows if barbarian_id(spell)}
        expected = {}
        for entry in self.value_map:
            if entry["source"] != "exact":
                continue
            expected[(int(entry["spell_id"]), entry["token"], entry["qualifier"])] = \
                value_row(self.values, entry)["value"]
        self.assertEqual(published, expected,
                         "dc_spell_values must hold the exact exceptions and only those")
        field_backed = {(int(entry["spell_id"]), entry["token"], entry["qualifier"])
                        for entry in self.value_map if entry["source"] != "exact"}
        # The two records the step 8 ruling created say the same token twice,
        # and they are not a duplicate home: the field holds the SKILL's shout
        # duration, which Inspiring Presence's SPELLMOD_DURATION doubles, and
        # the exact row holds the RECORD's own side effect, which must not
        # double. Different numbers, so this checks they are different.
        both = {(81108, "duration_seconds", ""), (81118, "duration_seconds", "")}
        self.assertEqual(field_backed & set(published), both,
                         "a field-backed number is duplicated into SQL")
        durations = {int(entry["spell_id"]): value_row(self.values, entry)["value"]
                     for entry in self.value_map
                     if (int(entry["spell_id"]), entry["token"], entry["qualifier"]) in both
                     and entry["source"] == "duration"}
        for spell, token, qualifier in both:
            self.assertNotEqual(float(published[(spell, token, qualifier)]),
                                float(durations[spell]),
                                "%d states and inherits the same number, which makes the "
                                "second home a duplicate after all" % spell)

    def test_the_value_map_covers_every_sheet_value(self):
        total = sum(len(rows) for rows in self.values.values())
        own = [entry for entry in self.value_map if entry["origin"] == "own"]
        self.assertEqual(len(own), total, "one value map row per sheet value")
        keys = {(entry["skill"], entry["rune"], entry["token"], entry["qualifier"])
                for entry in own}
        self.assertEqual(len(keys), len(own), "a key is mapped twice")
        for entry in self.value_map:
            self.assertIn(int(entry["holder_spell_id"]), self.now)

    def test_placement_follows_the_sentence_not_the_sheet(self):
        """Slots are handed out in the order the sentence asks, not row order.

        The values sheet is a table and an editor may sort it; the sentence
        is the thing that cannot be reordered without being rewritten. The
        map records the order the writer placed the numbers in, so this is
        what makes a shuffled sheet produce byte-identical records.
        """
        by_spell = {}
        for entry in self.value_map:
            if entry["origin"] != "own":
                continue
            by_spell.setdefault(int(entry["spell_id"]), []).append(
                (entry["token"], entry["qualifier"]))
        by_name = {(row["kind"], row["name"]): int(row["spell_id"]) for row in self.manifest}
        for kind, name, skill, rune, text, passive in sheet_rows():
            identifier = by_name.get((kind, name))
            if identifier is None or identifier not in by_spell:
                continue
            body, _, _ = text.partition("Unlocked")
            keys = [(token, qualifier or "")
                    for token, qualifier in re.findall(r"\{([a-z_]+)(?::([a-z_]+))?\}", body)]
            self.assertEqual([key for key in by_spell[identifier] if key[0] not in MODULE_READ],
                             keys,
                             "%s: the writer placed values in another order than the sentence"
                             % name)

    def test_every_rune_inherits_its_skill_and_overrides_only_its_own(self):
        """A rune is the skill plus its change (Architect, 2026-09-20).

        Every value the base skill states and the rune does not restate must
        appear on the rune, marked inherited and carrying the skill's number;
        every value the rune does restate must be the rune's own number and
        nothing else.
        """
        by_name = {(row["kind"], row["name"]): int(row["spell_id"]) for row in self.manifest}
        by_spell = {}
        for entry in self.value_map:
            by_spell.setdefault(int(entry["spell_id"]), []).append(entry)
        checked = 0
        for row in read_csv(D3 / "barbarian_runes.csv"):
            skill, rune = row["skill_name"], row["rune_name"]
            identifier = by_name.get(("rune", "%s - %s" % (skill, rune)))
            base = by_name.get(("active", skill))
            if identifier is None or base is None:
                continue
            own = {(value["token"], value["qualifier"]): value
                   for value in self.values.get((skill, rune, False), [])}
            base_rows = {(value["token"], value["qualifier"]): value
                         for value in self.values.get((skill, "", False), [])}
            entries = {(entry["token"], entry["qualifier"]): entry
                       for entry in by_spell.get(identifier, [])}
            for key, value in own.items():
                self.assertIn(key, entries, "%s - %s: %s is missing" % (skill, rune, key))
                self.assertEqual(entries[key]["origin"], "own",
                                 "%s - %s: %s must be the rune's own" % (skill, rune, key))
            removed_cost = " cost removed" in row["modified_cost_cooldown_damage"]
            for key, value in base_rows.items():
                if key in own:
                    continue        # the rune restates it: its own value wins
                if removed_cost and key[0] == "cost_resource":
                    # The one documented exception to inheritance (step 5): the
                    # rune sheet's own clause takes the cost away, so there is
                    # nothing to inherit and the record carries no cost at all.
                    self.assertNotIn(key, entries,
                                     "%s - %s: its cost is removed and it inherited one"
                                     % (skill, rune))
                    self.assertEqual(self.now[identifier][self.at["ManaCost"]], "0")
                    self.assertEqual(self.now[identifier][self.at["PowerType"]], "0")
                    continue
                self.assertIn(key, entries,
                              "%s - %s: %s was not inherited from the skill" % (skill, rune, key))
                entry = entries[key]
                self.assertEqual(entry["origin"], "inherited")
                self.assertEqual(int(entry["origin_spell_id"]), base,
                                 "%s - %s: %s names the wrong base skill" % (skill, rune, key))
                self.assertEqual(value_row(self.values, entry)["value"], value["value"])
            checked += 1
        self.assertEqual(checked, 115, "every rune is checked")

    def test_an_inherited_number_never_reaches_the_sentence(self):
        """The record carries the skill's numbers; the text stays the rune's."""
        for entry in self.value_map:
            if entry["origin"] != "inherited" or entry["source"] != "exact":
                continue
            identifier = int(entry["spell_id"])
            row = int(self.now[identifier][self.at["SpellDescriptionVariableID"]])
            self.assertNotIn(entry["variable"], self.variables.get(row, {}),
                             "%d: the inherited %s reached the client variables"
                             % (identifier, entry["variable"]))

    def test_the_positional_tables_still_read_the_row_s_own_numbers(self):
        """b->n[k] through a rune is what it was: inheritance never leaks here.

        The tables are read at the baseline commit, not from the working tree,
        because step 4 migrates their readers and then deletes them.

        The module reads skill and rune numbers positionally out of the
        generated headers, and a base-through-rune read (`b->n[k]`) depends on
        those positions meaning exactly what they meant before this step. Each
        header row must therefore still be that sheet row's own values, in
        sentence order, and nothing else.
        """
        rows = re.findall(r"\{(\d+), \"([^\"]*)\", \"([^\"]*)\", \{([^}]*)\}",
                          frozen_file("mod-diablocraft/src/combat/dc_ability_data.h"))
        self.assertEqual(len(rows), 138, "23 skills and 115 runes")
        for _identifier, skill, rune, numbers in rows:
            published = [piece.strip() for piece in numbers.split(",") if piece.strip()]
            wanted = [value["value"] for value in printed(self.values.get((skill, rune, False), []))]
            self.assertEqual([float(number) for number in published],
                             [float(number) for number in wanted],
                             "%s - %s: the positional table moved" % (skill, rune))
        passives = re.findall(r"\{(\d+), \"([^\"]*)\", \{([^}]*)\}",
                              frozen_file("mod-diablocraft/src/combat/dc_passive_data.h"))
        self.assertEqual(len(passives), 19)
        for _identifier, name, numbers in passives:
            published = [piece.strip() for piece in numbers.split(",") if piece.strip()]
            # printed(), as the skill branch above already does: a module-read
            # row is in the record and in no sentence, and these frozen tables
            # are the sentence's numbers.
            wanted = [value["value"] for value in printed(self.values.get((name, "", True), []))]
            self.assertEqual([float(number) for number in published],
                             [float(number) for number in wanted],
                             "%s: the positional table moved" % name)

    def raw_variable_rows(self):
        """{row id: the row's text exactly as the DBC holds it}."""
        raw = VARIABLES_DBC.read_bytes()
        _magic, count, _fields, size, _strings = struct.unpack("<4sIIII", raw[:20])
        block = raw[20 + count * size:]
        rows = {}
        for index in range(count):
            record = raw[20 + index * size: 20 + (index + 1) * size]
            identifier, offset = struct.unpack("<II", record)
            rows[identifier] = block[offset:block.index(b"\x00", offset)].decode("utf-8")
        return rows

    def test_every_row_we_own_is_written_in_the_stock_grammar(self):
        """Step 11: the client parses one grammar, and ours was not it.

        Every value in the stock file is wrapped in `${...}` and variables are
        separated by CRLF with no terminator. Ours were `$name=value;`, so the
        client parsed nothing and printed `$<name>` as text - which is what
        The designer saw on client 29. This is the check that says they are written
        the way the stock rows write them now.

        What the stock rows prove, exactly: the separator, and that a
        semicolon appears nowhere. They do NOT prove that VARIABLE_ROW is the
        whole stock grammar - only four of the thirty match it, because most
        stock pieces are conditional expressions such as
        `$?s56801[${6+2+5}][${6+2}]`. The breakdown is asserted below so that
        claim stays a measurement.
        """
        rows = self.raw_variable_rows()
        ours = {key: text for key, text in rows.items() if key >= FIRST_VARIABLE_ID}
        self.assertTrue(ours, "no rows of ours in the variables table")
        for key, text in sorted(ours.items()):
            self.assertRegex(text, VARIABLE_ROW,
                             "row %d is not in the stock grammar: %r" % (key, text))
            self.assertNotIn(";", text, "row %d still carries a semicolon" % key)
        # and the stock rows are the evidence for what that grammar is, as far
        # as it goes: 30 rows, ids running through 181, 67 name=value pieces.
        stock = [text for key, text in rows.items() if key < FIRST_VARIABLE_ID]
        self.assertEqual(len(stock), 30, "the stock rows are no longer the 30 we preserve")
        self.assertEqual(
            max(key for key in rows if key < FIRST_VARIABLE_ID), 181,
            "the stock ids no longer run through 181")
        self.assertEqual([text for text in stock if ";" in text], [],
                         "a stock row uses a semicolon after all")
        shapes = {"wrapped": 0, "conditional": 0, "bare": 0}
        for text in stock:
            for piece in text.split("\r\n"):
                if not piece:
                    continue
                value = piece.partition("=")[2]
                if value.startswith("$?"):
                    shapes["conditional"] += 1
                elif value.startswith("${") and value.endswith("}"):
                    shapes["wrapped"] += 1
                else:
                    shapes["bare"] += 1
        # 11 plain wrapped values, 54 conditionals whose branches wrap their
        # own values, and two bare: `$junk=1` in row 29 and
        # `$base=($pl-1)*3+10` in row 181.
        self.assertEqual(shapes, {"wrapped": 11, "conditional": 54, "bare": 2},
                         "the stock rows are not the ones this test describes")
        self.assertEqual(sum(1 for text in stock if VARIABLE_ROW.match(text)), 4,
                         "the stock rows written entirely in our shape are no longer four")

    def test_every_rendered_variable_is_defined_in_the_row_it_points_at(self):
        """A `$<name>` the client cannot resolve is printed as text.

        Binding is by exact name, so a capital letter is as fatal as a typo.
        Every `$<name>` a record renders - in its description OR in its aura
        text, which the client resolves out of the same row - has to be
        defined with that casing in the row this record's
        SpellDescriptionVariableID names, and every name that row defines has
        to be asked for by the record, or the row carries a value nothing
        renders.
        """
        rows = self.raw_variable_rows()
        used = 0
        for row in self.manifest:
            spell = int(row["spell_id"])
            sentences = sentences_of(self.now[spell], self.at)
            pointer = int(self.now[spell][self.at["SpellDescriptionVariableID"]])
            faults = binding_faults(row["name"], sentences, pointer, rows)
            self.assertEqual(faults, [], "\n".join(faults))
            used += len(variables_rendered(sentences))
        self.assertGreaterEqual(used, 24, "fewer variables are rendered than step 7 shipped")

    def a_record_that_renders_variables(self):
        """A real record, as a mutable copy, for the planted-offender checks."""
        for row in self.manifest:
            values = list(self.now[int(row["spell_id"])])
            if len(variables_rendered([values[self.at["Description_Lang_enUS"]]])) >= 2:
                return (row["name"], values,
                        int(values[self.at["SpellDescriptionVariableID"]]))
        raise AssertionError("no record renders two variables")

    def test_a_variable_an_aura_text_renders_is_bound_like_any_other(self):
        """The aura field is read, and the two fields are read together.

        Both halves are planted here. Moving a reference out of the
        description and into the aura text has to stay clean, because the
        record still asks for the same names and the client resolves both
        fields out of the one row - a per-field check would report the row as
        defining a value nothing renders. A name no row defines has to be
        caught wherever it is written - a description-only check would miss
        it. Every aura text we generate is empty today, so this is what stops
        the field being dropped from SENTENCE_FIELDS unnoticed.
        """
        name, values, pointer = self.a_record_that_renders_variables()
        rows = self.raw_variable_rows()
        description = values[self.at["Description_Lang_enUS"]]
        moved = re.search(r"\$<[^>]+>", description).group(0)
        values[self.at["Description_Lang_enUS"]] = description.replace(moved, "", 1)
        values[self.at["AuraDescription_Lang_enUS"]] = "Bearing %s." % moved
        self.assertEqual(
            binding_faults(name, sentences_of(values, self.at), pointer, rows), [],
            "a reference only the aura text makes is not counted as the record's")
        values[self.at["AuraDescription_Lang_enUS"]] = (
            "Bearing %s and $<no_such_value>." % moved)
        self.assertTrue(
            binding_faults(name, sentences_of(values, self.at), pointer, rows),
            "an undefined variable in an aura text went unseen")

    def test_a_capital_in_an_aura_text_is_caught_like_one_in_a_description(self):
        """`$<Radius_yards>` does not resolve, in either field."""
        name, values, pointer = self.a_record_that_renders_variables()
        rows = self.raw_variable_rows()
        asked = re.search(r"\$<([^>]+)>",
                          values[self.at["Description_Lang_enUS"]]).group(1)
        values[self.at["AuraDescription_Lang_enUS"]] = "Bearing $<%s>." % asked.capitalize()
        faults = binding_faults(name, sentences_of(values, self.at), pointer, rows)
        self.assertTrue([fault for fault in faults if "lower-case" in fault],
                        "a capitalised variable in an aura text went unseen: %s" % faults)

    def test_no_sentence_supplies_the_unit_that_the_client_supplies(self):
        """Step 11: "for $d seconds" printed "for 2 min seconds".

        The client renders `$d` with its own unit word out of its string
        table, so ours never adds one. `$t1` is the opposite - a bare number -
        and per the same ruling its word is spelled out in full. Both fields
        are swept, for the same reason the binding check sweeps both.
        """
        durations, periods = 0, 0
        for row in self.manifest:
            spell = int(row["spell_id"])
            sentences = sentences_of(self.now[spell], self.at)
            faults = unit_faults(row["name"], sentences)
            self.assertEqual(faults, [], "\n".join(faults))
            durations += sum(len(re.findall(r"\$d", text)) for text in sentences)
            periods += sum(len(re.findall(r"\$t1", text)) for text in sentences)
        self.assertGreater(durations, 0, "no $d is rendered at all, so this proves nothing")
        # Step 12 took the last `$t1` out of every published sentence: the only
        # two rows with a period are one-second ones, and a one-second period is
        # a word now. So the period half of the rule has nothing live to sweep
        # and is proved on a planted sentence instead - which is what this file
        # already does for the aura field that is empty today. Counting zero
        # here is a statement of fact, not a check that stopped checking.
        self.assertEqual(periods, 0,
                         "a sentence prints $t1 again; sweep it rather than planting one")
        self.assertEqual(unit_faults("planted", ["Deal damage every $t1 seconds."]), [])
        self.assertTrue([fault for fault in unit_faults("planted", ["Deal damage every $t1."])
                         if "spelled-out word" in fault],
                        "a bare $t1 with no word went unseen")

    def test_a_unit_word_in_an_aura_text_is_caught(self):
        """The same sweep, planted in the field that is empty today."""
        name, values, _pointer = self.a_record_that_renders_variables()
        self.assertEqual(unit_faults(name, sentences_of(values, self.at)), [],
                         "the record this check mutates is not clean to begin with")
        for offender in ("Lasts $d seconds.", "Lasts 5 sec.", "Ticks every $t1 sec."):
            values[self.at["AuraDescription_Lang_enUS"]] = offender
            self.assertTrue(unit_faults(name, sentences_of(values, self.at)),
                            "an aura text reading %r went unseen" % offender)

    def test_the_client_variables_table_parses_and_matches(self):
        self.assertTrue(self.variables, "no client variables rows")
        wanted = {}
        for entry in self.value_map:
            # A cost is a record field now (step 5) and a cooldown and a
            # charge recharge are (step 6), and the sentence still prints a
            # copy of each, because the client has no description token for
            # the cost or the cooldown line; step 7 drops the clauses and the
            # copies with them.
            if entry["source"] not in ("exact", "cost", "cooldown", "recharge") \
                    or entry["origin"] != "own":
                continue
            if entry["token"] in MODULE_READ:
                continue
            if not entry["variable"]:
                # Step 7: a cost or cooldown whose label line the client prints
                # from the record itself. Nothing renders it, so no row exists.
                continue
            wanted.setdefault(int(entry["spell_id"]), set()).add(entry["variable"])
        # diablocraft-buff-text: a buff prints its source's numbers too, so a name
        # its aura text renders is a name its row defines, `base_`-prefixed or not.
        for identifier, values in self.now.items():
            asked = variables_rendered([values[self.at["AuraDescription_Lang_enUS"]]])
            if asked:
                wanted.setdefault(identifier, set()).update(asked)
        for identifier, names in wanted.items():
            row = int(self.now[identifier][self.at["SpellDescriptionVariableID"]])
            self.assertIn(row, self.variables, "%d has no variables row" % identifier)
            self.assertEqual(set(self.variables[row]), names,
                             "%d: the variables row and the sentence disagree" % identifier)
        # And the converse: a record that needs no variable of OURS points at
        # none of ours, so the client is never sent to a row that says nothing
        # about it. A donor's own stock pointer is its own business - stock
        # rows are three digits and ours start at 81000.
        for identifier in sorted(self.now):
            if identifier in wanted:
                continue
            row = int(self.now[identifier][self.at["SpellDescriptionVariableID"]])
            self.assertLess(row, FIRST_VARIABLE_ID,
                            "%d points at one of our variables rows and renders no variable"
                            % identifier)
        for identifier, entries in self.variables.items():
            if identifier < FIRST_VARIABLE_ID:
                continue          # a stock row, whose grammar is Blizzard's
            for name, value in entries.items():
                self.assertRegex(name, r"^[a-z_]+$")
                self.assertRegex(value, r"^[0-9]+(\.[0-9]+)?$")
        # Step 7 ships this file in patch-4.MPQ, and the client reads the
        # highest-numbered patch's copy INSTEAD of its own, so a row Blizzard
        # ships and we drop is a row no spell can resolve any more - including
        # 167, which one of our own donor shells still points at. Every stock
        # row survives, id and text, and none of them is one of ours.
        stock = parse_variables((DBC / "SpellDescriptionVariables.dbc").read_bytes())
        self.assertTrue(stock, "the stock variables table was not extracted")
        for identifier, entries in stock.items():
            self.assertLess(identifier, FIRST_VARIABLE_ID,
                            "stock row %d is inside the block we own" % identifier)
            self.assertIn(identifier, self.variables,
                          "stock variables row %d was dropped" % identifier)
            self.assertEqual(self.variables[identifier], entries,
                             "stock variables row %d was rewritten" % identifier)
        self.assertEqual(sorted(k for k in self.variables if k < FIRST_VARIABLE_ID),
                         sorted(stock), "a stock variables row was invented")

    def test_the_family_and_mask_reach_every_record_of_a_skill(self):
        """One bit per skill, shared by its runes and companions, unique per skill."""
        bits = {}
        for row in self.manifest:
            identifier, kind = int(row["spell_id"]), row["kind"]
            if kind not in ("active", "rune", "ability_aura", "ability_control",
                            "ability_proc", "bleed", "token_storage"):
                continue
            record = self.now[identifier]
            self.assertEqual(record[self.at["SpellClassSet"]], "20",
                             "%d is not in our spell family" % identifier)
            skill = row["name"].split(" - ")[0]
            bit = record[self.at["SpellClassMask_1"]]
            self.assertEqual(bits.setdefault(skill, bit), bit,
                             "%s: its records carry different mask bits" % skill)
        used = [bit for skill, bit in bits.items() if bit != "0"]
        self.assertEqual(len(set(used)), len(used), "two skills share a mask bit")


def helper_map_problems(gen, rows, manifest):
    """Everything wrong with an identity -> id map, as a list of sentences.

    The map is append-only: an identity keeps its id forever, so an id that has
    ever been used stays used. Most identities own a record; a RETIRED one owns
    none, and the generator names those explicitly (gen.RETIRED_HELPER_IDENTITIES)
    rather than the check inferring retirement from a missing record - which
    would excuse every helper that lost one.
    """
    problems = []
    try:
        ids = gen.validate_helper_map(rows, manifest)
    except SystemExit as refused:
        return [str(refused)]
    retired = dict(gen.RETIRED_HELPER_IDENTITIES)
    for identity, identifier in ids.items():
        if identity in retired:
            if identifier in manifest:
                problems.append("%d is retired but %r has a record" % (identifier, identity))
        elif manifest.get(identifier) != identity:
            problems.append("%d is not the shell the map says it is (%r, found %r)"
                            % (identifier, identity, manifest.get(identifier)))
    for identity, identifier in retired.items():
        if identity not in ids:
            problems.append("%r was retired and then dropped from the map, so its id %d is free "
                            "again" % (identity, identifier))
        elif ids[identity] != identifier:
            # Moving the retired identity is how an id would be handed on: the
            # map refuses two identities on one id, so nothing can take 82409
            # while this row still holds it.
            problems.append("%r was retired holding %d and is now on %d, which frees %d for reuse"
                            % (identity, identifier, ids[identity], identifier))
    # A rerun assigns nothing new, retired ids included.
    for identity, identifier in ids.items():
        again = gen.choose_helper_id(identity, ids, manifest)
        if again != identifier:
            problems.append("a rerun would move %r from %d to %d" % (identity, identifier, again))
    return problems


class GeneratorContractTests(unittest.TestCase):
    """The writer's own rules, exercised directly rather than through output."""

    @classmethod
    def setUpClass(cls):
        cls.gen = load_generator()

    def test_marks_bind_by_name_not_by_order(self):
        text = "Generate {generated_resource} Fury and swing for {damage_pct} weapon damage."
        marks = {("generated_resource", ""): "$s2", ("damage_pct", ""): "$s3%"}
        wanted = "Generate $s2 Fury and swing for $s3% weapon damage."
        self.assertEqual(self.gen.bind_marks(text, marks), wanted)
        # the values sheet is a table: its row order is not a contract
        self.assertEqual(self.gen.bind_marks(text, dict(reversed(list(marks.items())))), wanted)

    def test_a_qualifier_picks_its_own_value(self):
        text = "Reduces {cooldown_reduction_seconds:earthquake} and " \
               "{cooldown_reduction_seconds:call_of_the_ancients} seconds."
        marks = {("cooldown_reduction_seconds", "earthquake"): "$s1",
                 ("cooldown_reduction_seconds", "call_of_the_ancients"): "$s2"}
        self.assertEqual(self.gen.bind_marks(text, marks), "Reduces $s1 and $s2 seconds.")

    def test_a_missing_or_unused_key_is_refused(self):
        with self.assertRaises(SystemExit):
            self.gen.bind_marks("Swing for {damage_pct}.", {})
        with self.assertRaises(SystemExit):
            self.gen.bind_marks("Swing for {damage_pct}.",
                                {("damage_pct", ""): "$s1", ("slow_pct", ""): "$s2"})

    def test_the_helper_map_refuses_every_way_of_being_wrong(self):
        good = [("Weapons Master - token storage", 82400)]
        self.assertEqual(self.gen.validate_helper_map(good),
                         {"Weapons Master - token storage": 82400})
        for broken in ([("a", 82400), ("a", 82401)],          # one identity twice
                       [("a", 82400), ("b", 82400)],          # one id twice
                       [("a", 81000)],                        # outside the block
                       [("a", 82600)]):
            with self.assertRaises(SystemExit):
                self.gen.validate_helper_map(broken)
        with self.assertRaises(SystemExit):                   # an id another shell owns
            self.gen.validate_helper_map([("a", 82400)], {82400: "Frenzy"})

    def test_helper_ids_are_append_only(self):
        ids = {"b - token storage": 82400, "d - token storage": 82401}
        taken = {81000: "Frenzy"}
        # an identity that sorts earlier does not push the existing ones along
        self.assertEqual(self.gen.choose_helper_id("a - token storage", ids, taken), 82402)
        self.assertEqual(self.gen.choose_helper_id("b - token storage", ids, taken), 82400)
        self.assertEqual(self.gen.choose_helper_id("d - token storage", ids, taken), 82401)
        # and removing one leaves the others where they are
        ids.pop("b - token storage")
        self.assertEqual(self.gen.choose_helper_id("d - token storage", ids, taken), 82401)

    def test_the_published_helper_map_is_valid_and_matches_the_records(self):
        # Every class's rows, each checked against its own class's block.
        rows = [(row["identity"], int(row["spell_id"]), row.get("class") or "barbarian")
                for row in read_csv(GENERATED / "spell_helper_ids.csv")]
        manifest = {int(row["spell_id"]): row["name"] for row in read_csv(GENERATED / "spell_shells.csv")}
        self.assertEqual(helper_map_problems(self.gen, rows, manifest), [])

    def test_a_retired_identity_is_the_only_one_allowed_to_have_no_record(self):
        """The narrow exemption, and the two ways it must not widen.

        A retired identity (2026-09-21: the shared elite slow, 82409, replaced
        by one record per affix) keeps its row so its id stays spent and can
        never be handed to anything else. That is the ONLY reason a mapped
        identity may have no record - an active helper that has lost its record
        is a bug, and a retired id that turns up owned by something else is the
        recycling the map exists to prevent. Both are checked here against the
        same function the published map goes through.
        """
        retired, retired_id = self.gen.RETIRED_HELPER_IDENTITIES[0]
        self.assertEqual(retired_id, 82409)
        # The real thing: the retired identities, mapped, with no record.
        # Every retired identity is in the map, or the check reports it
        # dropped (diablocraft-wizard-mechanics retired two more).
        # Each belongs to the class whose block its id sits in (the Witch Doctor's Mana aura, 86201, the last).
        others = [(identity, identifier, "witch_doctor" if identity.startswith("Witch Doctor") else "wizard")
                  for identity, identifier in self.gen.RETIRED_HELPER_IDENTITIES[1:]]
        rows = [(retired, 82409), ("Knockback - affix slow", 82411)] + others
        manifest = {82411: "Knockback - affix slow"}
        self.assertEqual(helper_map_problems(self.gen, rows, manifest), [])

        # An ACTIVE helper with no record still fails: no blanket exemption.
        problems = helper_map_problems(self.gen, rows, {})
        self.assertTrue(any("Knockback - affix slow" in p for p in problems),
                        "an active helper lost its record and nothing complained")

        # The retired id handed to another identity still fails.
        recycled = [(retired, 82412), ("Knockback - affix slow", 82409)] + others
        problems = helper_map_problems(self.gen, recycled, {82409: "Knockback - affix slow"})
        self.assertTrue(any("82409" in p for p in problems),
                        "a retired id was reused and nothing complained")

        # A retired identity that has a record is not retired at all.
        problems = helper_map_problems(self.gen, rows, {82409: retired, 82411: "Knockback - affix slow"})
        self.assertTrue(any("82409" in p for p in problems),
                        "a retired identity kept a record and nothing complained")

        # And a retired identity dropped from the map frees its id again.
        problems = helper_map_problems(self.gen, [("Knockback - affix slow", 82411)], manifest)
        self.assertTrue(any(retired in p for p in problems),
                        "a retired identity was dropped from the map and nothing complained")


if __name__ == "__main__":
    unittest.main(verbosity=2)

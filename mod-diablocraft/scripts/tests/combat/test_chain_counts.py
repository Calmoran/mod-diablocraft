"""diablocraft-chain-counts (GitHub #52): no spell record leaves the writer with a chain count nobody owns.

A shell is cloned from a WoW spell and inherits its EffectChainTargets. The core
acts on that field in three places (AzerothCore 950684036, core-commit.txt; the
line numbers are the pin's, the patched build tree is 19 and 34 lines further on
in Spell.cpp):

- Spell::SelectImplicitChainTargets (Spell.cpp:1931) picks the chain targets. Its
  two callers are SelectImplicitNearbyTargets and SelectImplicitTargetObjectTargets,
  so it runs for a nearby or an explicit target, never for the caster, a cone, an
  area or a ground point;
- Spell::DoAllEffectOnLaunchTarget (Spell.cpp:8687) gives a damaging effect with a
  count above 1 on a non-magic spell the AoE damage reduction and the 10-target
  cap;
- ConditionMgr::isSourceTypeValid (ConditionMgr.cpp:1828) keeps a `conditions` row
  on a non-area effect whose count is above 1.

(A GM command also prints it, cs_spellinfo.cpp:870.) For the 25 below the count is
inert, reader by reader; on a shell that is still natively targeted the first
reader silently changes how many enemies a cast reaches. Before this task 34
generated records carried a count: 9 were placed by a `target_count` values row,
25 were the donor's own number with nothing owning it (24 Barbarian, 1 Wizard).

The writer now gives every count an owner (`settle_chain_counts`): a values row
states it (D3's number, the sheet wins), or the skill's skill_targeting.csv row
says the module resolves the targets and the donor's field is zeroed, or the
writer refuses and names the shell.

Four parts, each failing on the pre-fix writer:

- the rule itself, driven on planted records: a count with neither owner is
  refused, a module-resolved shell is zeroed, a values row's count is never
  touched, and the four single-rule mutants of the check each turn a case red;
- the real generated spell SQL carries no unowned count;
- the server SQL and the client Spell.dbc agree on every chain column of every
  record of ours, and the client file carries no unowned count either (one
  writer, two outputs: the fix is checked on both);
- the 25 zeroed shells are pinned by id with the skill_targeting.csv row that
  marks each module-resolved, so the list in docs/test-diablocraft-chain-counts.md
  cannot drift from the data.

Of the 25, 23 have a record target the core can never chain from (the caster, a
cone, a ground point), which is proved here from the generated records. The other
two, the Hammer of the Ancients control shells 81770 and 81772, take an explicit
enemy; the module applies them with `AddAura` (dc_abilities.cpp `Control`) and
never casts them, so the donor's count never ran. That last part is READ in the
C++, not run, and so is the claim that nothing else casts them. The other two
readers are inert for all 25 for reasons of their own, also read in the C++ and
measured on the generated Spell.dbc, not run and not asserted here: Effect_1 of
every one is DUMMY (11) or APPLY_AURA (14), whose handlers return before the
launch phase sets any damage, so DoAllEffectOnLaunchTarget never reaches the
count; and no tracked SQL inserts a `conditions` row, so ConditionMgr never looks
at it. Also not covered: anything the client does with the DBC; the GM check in
the test doc covers the in-game side.

    python mod-diablocraft/scripts/tests/combat/test_chain_counts.py
"""

from __future__ import annotations

import csv
import inspect
import re
import struct
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as spells  # noqa: E402
import test_chain_targets as chain_targets  # noqa: E402

MODULE = SCRIPTS.parent
REPO_ROOT = MODULE.parent
GENERATED = MODULE / "data" / "generated"
SHEETS = MODULE / "data" / "d3"
SPELL_DBC = REPO_ROOT / "client-patch" / "dbc" / "Spell.dbc"

COLUMNS = ["ID", "EffectChainTargets_1", "EffectChainTargets_2", "EffectChainTargets_3"]

# The 25 donor counts this task zeroed: spell id -> the skill_targeting.csv row
# that marks it module-resolved. A skill's own shells and its companion
# aura/control shells share the skill's row; the four carrier shells the module
# deals the damage of itself (the affixes and Thorns) have a row of their own.
HAMMER, CLEAVE = "Hammer of the Ancients", "Cleave"
ZEROED = {
    81007: HAMMER, **{i: HAMMER for i in range(81058, 81063)},          # the cast skill and its five runes
    81317: HAMMER, **{i: HAMMER for i in range(81368, 81373)},          # their marker auras
    81770: HAMMER, 81772: HAMMER,                                       # Devil's Anvil, Thunderstrike control shells
    81313: CLEAVE, **{i: CLEAVE for i in range(81348, 81353)},          # Cleave's marker auras
    81175: "Desecrator", 81178: "Jailer", 81182: "Reflects Damage", 81184: "Thorns",
    83159: "Arcane Torrent",                                            # the Wizard's Static Discharge rune
}
# The counts a values row places, and they must still be there.
# diablocraft-3mk78 adds the Monk's seven: Fists of Thunder - Bounding Light (83673, target_count 3) and Cyclone Strike
# (83664, target_count 16) with its five runes (83742-83746, which state it through their skill).
OWNED = {81029, 83103, 83141, 83142, 83143, 83144, 83145, 83170, 83222,
         83664, 83673, 83742, 83743, 83744, 83745, 83746}
# diablocraft-im7mr.5 adds the Necromancer's 19, each a target_count row of necromancer_skill_values.csv: Bone Armor, Command Golem, Leech, Revive.
OWNED |= {85109, 85111, 85117, 85166, 85167, 85168, 85169, 85170, 85176, 85177, 85178, 85179, 85180, 85196, 85206, 85207, 85208, 85209, 85210}
# diablocraft-qulab adds the Crusader's twelve: Smite (85402) with its five runes (85434-85438; Shatter's own row states no count and
# inherits it), Blessed Shield (85407) with its four ricocheting runes (85459-85462) and Bombardment's sheet row 85498.
OWNED |= {85402, 85407, 85434, 85435, 85436, 85437, 85438, 85459, 85460, 85461, 85462, 85498}
# diablocraft-vawmy.3 adds the Demon Hunter's eleven, each a target_count row of demon_hunter_skill_values.csv: Entangling Shot (85701)
# with Heavy Burden, Chain Gang, Shock Collar, Justice is Served and Bounty Hunter (85729-85733), Impale - Ricochet (85752),
# Marked for Death - Contagion (85800), Fan of Knives - Assassin's Knives (85805), Spike Trap - Lightning Rod (85813) and
# Multishot - Suppression Fire (85833).
OWNED |= {85701, 85729, 85730, 85731, 85732, 85733, 85752, 85800, 85805, 85813, 85833}
# diablocraft-vxrcu.5 adds the Witch Doctor's two, each a target_count row of witch_doctor_skill_values.csv: Firebomb - Flash Fire (86042,
# 6 targets) and Mass Confusion - Mass Hysteria (86094, 10 targets).
OWNED |= {86042, 86094}
# diablocraft-xnrvn.6 adds the Shaman's 28, each a target_count (or a count the sheet states beside it) row of shaman_skill_values.csv and
# shaman_passive_values.csv: Chain Lightning (86304) with its five runes (86344-86348), Spirit Link (86317) with its five (86409-86413),
# Ascendance (86323) with its five (86439-86443), Flame Shock - Static Shock and - Primal Shock (86332, 86333), Frost Lance - Thunderhail
# (86343), Elemental Blast - Elemental Echo (86360), Searing Totem - Capacitor Totem (86386), Call of the Ancestors - Thundercaller
# Ancestors (86417), Spirit Wolves - Lightning Wolves (86420), Fire Elemental - Storm Elemental (86431), Earth Elemental - Thunder
# Colossus (86437) and the passive Totemic Mastery (86445).
OWNED |= {86304, 86317, 86323, 86332, 86333, 86343, 86344, 86345, 86346, 86347, 86348, 86360, 86386, 86409, 86410, 86411, 86412, 86413,
          86417, 86420, 86431, 86437, 86439, 86440, 86441, 86442, 86443, 86445}
# Piercing Shield (85463) is the rune that does not bounce: the writer holds its slot 1 at 1, the primary victim alone
# (RUNES_WITHOUT_CHAIN). The core acts only on a count above 1, so it is no chain; it has no values row to own it.
NO_BOUNCE = {85463}
# The two zeroed shells whose record takes an explicit enemy (TARGET_UNIT_TARGET_ENEMY,
# 6): the Devil's Anvil and Thunderstrike control auras, applied by AddAura.
CONTROL = {81770, 81772}
# The implicit targets the core never chains from. Spell::SelectImplicitChainTargets
# is called from SelectImplicitNearbyTargets and SelectImplicitTargetObjectTargets
# only (test_chain_targets extracts both from the pin); none = 0, the caster = 1, a
# ground point = 87 and a cone = 104 are routed to SelectImplicitCasterObjectTargets,
# SelectImplicitDestDestTargets and SelectImplicitConeTargets instead.
NO_CHAIN_TARGETS = {0, 1, 87, 104}


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


# --- the rule, on planted records ------------------------------------------

def shell(identifier, name, *chain, kind="rune"):
    chain = list(chain) + [0] * (3 - len(chain))
    return [identifier] + chain, (identifier, name, "physical", 1, kind)


def run(settle, shells, owned=(), targeting=None):
    """(the records afterwards, what was zeroed, the refusal's text or None)."""
    records = [record for record, _entry in shells]
    manifest = [entry for _record, entry in shells]
    try:
        zeroed = settle(records, COLUMNS, manifest, set(owned), targeting or {})
    except SystemExit as refused:
        return records, [], str(refused)
    return records, zeroed, None


def row(kind):
    return {"target_type": kind}


def rule_problems(settle):
    """Every way `settle` can be wrong, as sentences; empty for the real rule."""
    problems = []

    # A count with no values row and no targeting row is refused, by name.
    _, _, refusal = run(settle, [shell(7, "Nova - Deep", 3)])
    if refusal is None:
        problems.append("a donor count with no owner and no row was accepted")
    elif "Nova - Deep" not in refusal or "spell 7" not in refusal:
        problems.append("the refusal does not name the shell and its id: %s" % refusal)

    # The core chains only from an explicit-unit target, so a row that says the
    # shell is still natively targeted - or says something nobody classified -
    # is no marker.
    for kind in ("single_enemy", "line_pierce", "no_such_type"):
        if run(settle, [shell(7, "Bolt", 3)], targeting={"Bolt": row(kind)})[2] is None:
            problems.append("a %s row was accepted as a module marker" % kind)

    # Every module-resolved type zeroes the donor's field, whichever slot holds it.
    for kind in ("cone_enemies", "self", "self_aoe", "self_allies", "self_summon",
                 "self_moving_aoe", "ground_area", "ground_point_aoe", "line_to_point"):
        records, zeroed, refusal = run(settle, [shell(7, "Slam", 3, 2, 4)], targeting={"Slam": row(kind)})
        if refusal is not None or records[0][1:] != [0, 0, 0]:
            problems.append("a %s row did not zero the record: %s %s" % (kind, records[0][1:], refusal))
        if [entry[2] for entry in zeroed] != COLUMNS[1:] or [entry[3] for entry in zeroed] != [3, 2, 4]:
            problems.append("the %s zeroing is not logged field by field: %s" % (kind, zeroed))

    # A rune and a companion aura find their skill's row through the name; a
    # carrier shell finds its own row, and a shell's own row outranks its skill's.
    records, zeroed, refusal = run(
        settle, [shell(1, "Slam - Quake", 3), shell(2, "Thorns", 2), shell(3, "Slam", 3)],
        targeting={"Slam": row("cone_enemies"), "Thorns": row("self")})
    if refusal is not None or [record[1] for record in records] != [0, 0, 0]:
        problems.append("the skill's row did not reach its rune, or a shell's own row its carrier: %s" % refusal)
    if [(entry[6], entry[7]) for entry in zeroed] != [("Slam", "cone_enemies"), ("Thorns", "self"),
                                                         ("Slam", "cone_enemies")]:
        problems.append("the log does not name the row that marked each shell: %s" % zeroed)
    if run(settle, [shell(5, "Slam - Quake", 3)],
           targeting={"Slam": row("cone_enemies"), "Slam - Quake": row("single_enemy")})[2] is None:
        problems.append("a shell's own row did not outrank its skill's")

    # A values row's count is the sheet's and is never touched, even on a
    # natively targeted shell (Ricochet); a donor count beside it in another
    # slot is not owned by that row.
    records, zeroed, refusal = run(settle, [shell(9, "Throw - Ricochet", 4)], owned={9},
                                   targeting={"Throw": row("single_enemy")})
    if refusal is not None or records[0][1] != 4 or zeroed:
        problems.append("an owned count was refused or changed: %s %s %s" % (records[0], zeroed, refusal))
    if run(settle, [shell(9, "Throw - Ricochet", 4, 2)], owned={9},
           targeting={"Throw": row("single_enemy")})[2] is None:
        problems.append("an unowned count in slot 2 was accepted beside an owned slot 1")
    records, _, refusal = run(settle, [shell(9, "Slam - Quake", 4, 2)], owned={9},
                              targeting={"Slam": row("cone_enemies")})
    if refusal is not None or records[0][1:] != [4, 0, 0]:
        problems.append("slot 2 was not zeroed beside an owned slot 1: %s %s" % (records[0], refusal))

    # No count, nothing to say.
    records, zeroed, refusal = run(settle, [shell(1, "Anything"), shell(2, "Else", 0, 0, 0)])
    if refusal is not None or zeroed or any(any(record[1:]) for record in records):
        problems.append("a record with no chain count was reported, changed or refused")
    return problems


def mutant(old, new):
    """`settle_chain_counts` with exactly one rule changed, compiled from its own source."""
    source = inspect.getsource(spells.settle_chain_counts)
    if source.count(old) != 1:
        raise AssertionError("mutation target %r appears %d times" % (old, source.count(old)))
    namespace = dict(vars(spells))
    exec(compile(source.replace(old, new), "mutant", "exec"), namespace)
    return namespace["settle_chain_counts"]


class TheRule(unittest.TestCase):
    def test_the_rule_holds_on_planted_records(self):
        self.assertEqual(rule_problems(spells.settle_chain_counts), [])

    def test_a_check_that_never_refuses_is_caught(self):
        self.assertNotEqual(rule_problems(mutant('raise SystemExit(\n            "chain counts', 'str(\n            "chain counts')), [])

    def test_a_check_that_never_zeroes_is_caught(self):
        self.assertNotEqual(rule_problems(mutant('"skill_targeting.csv", key, kind))\n            values[slot] = 0', '"skill_targeting.csv", key, kind))\n            pass')), [])

    def test_a_check_that_overwrites_an_owned_count_is_caught(self):
        self.assertNotEqual(rule_problems(mutant("number == 1 and identifier in owned", "False")), [])

    def test_a_check_that_trusts_a_native_row_is_caught(self):
        self.assertNotEqual(rule_problems(mutant("kind not in MODULE_TARGETED", "kind is None")), [])


# --- the real generated data ------------------------------------------------

def generated_chain():
    """{spell id: [slot 1, 2, 3 chain counts]} out of the generated spell SQL."""
    return {identifier: [int(record["EffectChainTargets_%d" % slot]) for slot in (1, 2, 3)]
            for identifier, record in chain_targets.generated_records().items()}


def owners():
    """Ids whose chain field a values row placed, from the generated value map."""
    return {int(entry["holder_spell_id"]) for entry in read_csv(GENERATED / "spell_value_map.csv")
            if entry["source"] == "chain"}


def unowned(chain, owned):
    """{id: counts} for every record whose chain count no values row placed (a count of 1 is the primary alone, and only
    the runes that do not bounce hold one)."""
    return {identifier: counts for identifier, counts in sorted(chain.items())
            if any(counts[1:]) or (counts[0] and identifier not in owned
                                   and not (counts == [1, 0, 0] and identifier in NO_BOUNCE))}


def dbc_chain(path, ids):
    """{spell id: [slot 1, 2, 3 chain counts]} for `ids`, read out of a Spell.dbc.

    The DBC's fields are the spell_dbc columns one for one, so the chain
    columns sit where the generated SQL's header puts them.
    """
    text = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    names = [name.strip(" `") for name in
             re.search(r"INSERT INTO `spell_dbc` \(([^)]*)\) VALUES", text)[1].split(",")]
    slots = [names.index("EffectChainTargets_%d" % number) for number in (1, 2, 3)]
    data = Path(path).read_bytes()
    magic, count, _fields, size, _strings = struct.unpack("<4sIIII", data[:20])
    if magic != b"WDBC":
        raise AssertionError("%s is not a WDBC file" % path)
    found = {}
    for index in range(count):
        offset = 20 + index * size
        identifier = struct.unpack_from("<I", data, offset)[0]
        if identifier in ids:
            found[identifier] = [struct.unpack_from("<I", data, offset + 4 * slot)[0] for slot in slots]
    return found


class TheGeneratedSpells(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chain = generated_chain()
        cls.owners = owners()
        cls.manifest = {int(entry["spell_id"]): entry for entry in read_csv(GENERATED / "spell_shells.csv")}
        cls.targeting = {entry["skill"]: entry for entry in read_csv(SHEETS / "skill_targeting.csv")}

    def test_no_chain_count_is_the_donors(self):
        found = unowned(self.chain, self.owners)
        self.assertEqual(found, {}, "%d records carry a chain count no values row owns" % len(found))

    def test_the_counts_a_values_row_places_are_still_there(self):
        self.assertEqual(self.owners, OWNED)
        for identifier in OWNED:
            self.assertGreater(self.chain[identifier][0], 1, "record %d lost its count" % identifier)

    def test_only_owned_records_chain_at_all(self):
        self.assertEqual({identifier for identifier, counts in self.chain.items() if any(counts)}, OWNED | NO_BOUNCE)
        for identifier in NO_BOUNCE:
            self.assertEqual(self.chain[identifier], [1, 0, 0], "%d" % identifier)

    def test_the_zeroed_shells_are_the_pinned_twenty_five_and_each_is_marked(self):
        self.assertEqual(len(ZEROED), 25)
        self.assertFalse(set(ZEROED) & OWNED)
        for identifier, key in sorted(ZEROED.items()):
            name = self.manifest[identifier]["name"]
            self.assertIn(key, (name, name.split(" - ")[0]),
                          "%d (%s) is not %s's shell" % (identifier, name, key))
            self.assertEqual(self.chain[identifier], [0, 0, 0], "%d (%s) still chains" % (identifier, name))
            self.assertIn(key, self.targeting, "%s has no skill_targeting.csv row" % key)
            self.assertIn(self.targeting[key]["target_type"], spells.MODULE_TARGETED,
                          "%s is not marked module-resolved" % key)

    def test_no_zeroed_shell_could_have_chained_natively(self):
        """A zeroed shell's row is never a type the core chains from."""
        for key in set(ZEROED.values()):
            self.assertNotIn(self.targeting[key]["target_type"], ("single_enemy", "line_pierce"), key)

    def test_twenty_three_zeroed_records_cannot_reach_the_chain_code_and_two_take_an_enemy(self):
        """The records themselves: zeroing these removed a count that never ran.

        Not the row's word for it - the generated record's own implicit targets,
        in every effect slot. The two that take an enemy are the control shells
        the module applies with AddAura, named here so a third cannot join them
        unseen.
        """
        records = chain_targets.generated_records()
        enemy = set()
        for identifier in sorted(ZEROED):
            targets = {int(records[identifier]["ImplicitTarget%s_%d" % (side, slot)])
                       for side in "AB" for slot in (1, 2, 3)}
            if not targets <= NO_CHAIN_TARGETS:
                enemy.add(identifier)
        self.assertEqual(enemy, CONTROL)
        for identifier in CONTROL:
            self.assertEqual(records[identifier]["ImplicitTargetA_1"], "6", "%d" % identifier)

    def test_the_client_spell_dbc_agrees_with_the_server_sql(self):
        if not SPELL_DBC.is_file():
            self.skipTest("client-patch/dbc/Spell.dbc is not generated here")
        client = dbc_chain(SPELL_DBC, set(self.chain))
        self.assertEqual(sorted(client), sorted(self.chain), "the DBC lacks records the SQL has")
        self.assertEqual({identifier: counts for identifier, counts in client.items()
                          if counts != self.chain[identifier]}, {},
                         "client and server disagree on a chain count")
        # The same invariant as the server's, on the file the client reads.
        found = unowned(client, self.owners)
        self.assertEqual(found, {}, "the client Spell.dbc carries a chain count no values row owns")


if __name__ == "__main__":
    unittest.main()

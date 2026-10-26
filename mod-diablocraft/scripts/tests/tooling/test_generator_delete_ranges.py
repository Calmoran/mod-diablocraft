"""diablocraft-mapz: no generator's DELETE may cover rows another generator inserts.

generate_rift_elites.py once wrote `DELETE FROM creature_template WHERE entry >= 8000000`, and the family clones that
generate_monster_models.py writes sit at 8950001+ and 9950001+, so applying the elite clones after the family monsters
removed every family elite clone. This reads every world migration (data/sql/db-world/updates) and every generated
mirror that is not a copy of one, finds each DELETE with a key range (`col BETWEEN a AND b`, `>=`, `>`, `<=`, `<`, `=`,
`IN (..)`) and every INSERT with a column list, and fails when a DELETE of one generator covers a key another generator
inserts into the same table. Only a REPLACING delete counts, one in a file that inserts into that table too: a file that
only retires rows (world_0029, world_0034) removes what it means to remove. A generator is the `generate_*.py` named in the file's header (else the file name's
prefix); versions of one generator may overwrite each other, that is what replacing is.

The one offender that cannot be fixed in place is KNOWN_FROZEN: rifts_0006_elite_clones.sql is an applied migration
(applied_migrations.csv), immutable by the designer's 2026-09-23 ruling, so its wide DELETE stays; the test lists it by name
and fails on any other. The generator's own render is checked with made-up clones, so the fix itself is held.
"""
import functools
import hashlib
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
MODULE = HERE.parent
UPDATES = MODULE / "data" / "sql" / "db-world" / "updates"
GENERATED = MODULE / "data" / "generated"

# file name -> why it is allowed to cover another generator's rows (see the bead diablocraft-mapz)
KNOWN_FROZEN = {
    "rifts_0006_elite_clones.sql": "applied, immutable: its DELETE >= 8000000 covers the family clones; rifts_0023_family_clones.sql "
                                   "sorts after it and inserts them again (diablocraft-bilc, test_family_clones_fresh_replay.py)",
}

# file name -> the generator that owns its rows now. items_0015 hand-wrote the Regeneration potion (102200); items_0027's
# generate_potion_icons.py took that row over with the other ten (diablocraft-0knhj) and replaces it, so the two files'
# overlap on 102200 is one generator's, not a clash. 0015 is applied (applied_migrations.csv), so its header cannot name
# the generator; only that file is moved, and 0027 stays checked against everything else.
HANDED_OVER = {
    "items_0015_bottomless_potion.sql": "generate_potion_icons.py",
}


def statements(text):
    """The statements of `text`, split at ';' outside quotes, with `--` comment lines dropped."""
    out, buf, quote, i, n, line_start = [], [], None, 0, len(text), True
    while i < n:
        c = text[i]
        if quote:
            buf.append(c)
            if c == "\\" and i + 1 < n:
                buf.append(text[i + 1]); i += 1
            elif c == quote:
                if i + 1 < n and text[i + 1] == quote:
                    buf.append(text[i + 1]); i += 1
                else:
                    quote = None
        elif line_start and text.startswith("--", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif c in "'\"`":
            quote = c; buf.append(c)
        elif c == ";":
            out.append("".join(buf).strip()); buf = []
        else:
            buf.append(c)
        line_start = c == "\n" if not quote else False
        i += 1
    if "".join(buf).strip():
        out.append("".join(buf).strip())
    return [s for s in out if s]


def split_fields(text):
    """Top-level comma-separated fields of a tuple body, quotes and parentheses respected."""
    fields, buf, depth, quote, i = [], [], 0, None, 0
    while i < len(text):
        c = text[i]
        if quote:
            buf.append(c)
            if c == "\\" and i + 1 < len(text):
                buf.append(text[i + 1]); i += 1
            elif c == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    buf.append(text[i + 1]); i += 1
                else:
                    quote = None
        elif c in "'\"":
            quote = c; buf.append(c)
        elif c == "(":
            depth += 1; buf.append(c)
        elif c == ")":
            depth -= 1; buf.append(c)
        elif c == "," and depth == 0:
            fields.append("".join(buf).strip()); buf = []
        else:
            buf.append(c)
        i += 1
    fields.append("".join(buf).strip())
    return fields


def tuples(values):
    """The parenthesised rows of a VALUES list."""
    rows, depth, quote, start, i = [], 0, None, None, 0
    while i < len(values):
        c = values[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                if i + 1 < len(values) and values[i + 1] == quote:
                    i += 1
                else:
                    quote = None
        elif c in "'\"":
            quote = c
        elif c == "(":
            if depth == 0:
                start = i + 1
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                rows.append(values[start:i])
        i += 1
    return rows


NUMBER = r"-?\d+"


def parse_delete(statement):
    """(table, column, predicate) for a DELETE with an integer key range, else None."""
    m = re.match(r"DELETE\s+FROM\s+`?(\w+)`?\s+WHERE\s+`?(\w+)`?\s*(.*)$", statement, re.S | re.I)
    if not m:
        return None
    table, column, rest = m.groups()
    rest = rest.strip()
    if (b := re.fullmatch(rf"BETWEEN\s+({NUMBER})\s+AND\s+({NUMBER})", rest, re.I)):
        lo, hi = int(b.group(1)), int(b.group(2))
        return table, column, lambda k: lo <= k <= hi, f"{column} BETWEEN {lo} AND {hi}"
    if (b := re.fullmatch(rf"(>=|>|<=|<|=)\s*({NUMBER})", rest)):
        op, n = b.group(1), int(b.group(2))
        test = {">=": lambda k: k >= n, ">": lambda k: k > n, "<=": lambda k: k <= n, "<": lambda k: k < n, "=": lambda k: k == n}[op]
        return table, column, test, f"{column} {op} {n}"
    if (b := re.fullmatch(r"IN\s*\(([^)]*)\)", rest, re.I)):
        try:
            ids = {int(x) for x in b.group(1).split(",")}
        except ValueError:
            return None
        return table, column, lambda k: k in ids, f"{column} IN ({len(ids)} ids)"
    return None


def parse_insert(statement):
    """(table, {column: [int keys]}) for an INSERT with a column list."""
    m = re.match(r"(?:INSERT|REPLACE)\s+(?:IGNORE\s+)?INTO\s+`?(\w+)`?\s*\(([^)]*)\)\s*VALUES\s*(.*)$", statement, re.S | re.I)
    if not m:
        return None
    table, cols, values = m.groups()
    names = [c.strip().strip("`") for c in cols.split(",")]
    keys = {name: [] for name in names}
    for row in tuples(values):
        fields = split_fields(row)
        if len(fields) != len(names):
            continue
        for name, field in zip(names, fields):
            if re.fullmatch(NUMBER, field):
                keys[name].append(int(field))
    return table, keys


def generator_of(name, text):
    if name in HANDED_OVER:
        return HANDED_OVER[name]
    m = re.search(r"generate_\w+\.py", "\n".join(text.splitlines()[:15]))
    return m.group(0) if m else re.sub(r"_\d+.*$", "", name)


@functools.lru_cache(maxsize=None)
def sources():
    """name -> text for every world migration, and each generated mirror that is not a byte copy of one.

    Read once per process (65 MB): nobody changes the dict it returns."""
    files = {p.name: p.read_text(encoding="utf-8") for p in sorted(UPDATES.glob("*.sql"))}
    seen = {hashlib.sha1(t.encode()).hexdigest() for t in files.values()}
    for p in sorted(GENERATED.glob("*.sql")):
        text = p.read_text(encoding="utf-8")
        if hashlib.sha1(text.encode()).hexdigest() not in seen:
            files["generated/" + p.name] = text
    return files


@functools.lru_cache(maxsize=None)
def parsed(text):
    """([parse_delete result], [parse_insert result]) of a file's text, in statement order. Tokenising is the cost, so
    a text is parsed once per process; the generator that owns the file is decided per call, not here."""
    deletes, inserts = [], []
    for statement in statements(text):
        if re.match(r"DELETE\b", statement, re.I) and (d := parse_delete(statement)):
            deletes.append(d)
        elif (i := parse_insert(statement)):
            inserts.append(i)
    return deletes, inserts


def offenders(files):
    """[(deleting file, delete, inserting file, table, count)] where one generator's DELETE covers another's inserted keys."""
    deletes, inserts, inserted_by_file = [], {}, set()
    for name, text in files.items():
        owner = generator_of(name.split("/")[-1], text)
        found_deletes, found_inserts = parsed(text)
        for d in found_deletes:
            deletes.append((name, owner) + d)
        for table, keys in found_inserts:
            inserted_by_file.add((name, table))
            for column, found in keys.items():
                inserts.setdefault((table, column), []).append((name, owner, found))
    out = []
    for name, owner, table, column, test, shown in deletes:
        if (name, table) not in inserted_by_file:
            continue                                   # a pure retirement
        for other, other_owner, found in inserts.get((table, column), []):
            if other_owner == owner:
                continue
            hit = [k for k in found if test(k)]
            if hit:
                out.append((name, f"DELETE FROM {table} WHERE {shown}", other, table, len(hit)))
    return sorted(set(out))


class DeleteRanges(unittest.TestCase):
    def test_no_generator_deletes_another_generators_rows(self):
        bad = [o for o in offenders(sources()) if o[0].split("/")[-1] not in KNOWN_FROZEN]
        self.assertEqual(bad, [], "a generator's DELETE covers rows another generator inserts")

    def test_the_known_frozen_offender_is_still_listed_and_still_real(self):
        found = {o[0] for o in offenders(sources())}
        for name in KNOWN_FROZEN:
            self.assertIn(name, found, f"{name} no longer offends: take it off KNOWN_FROZEN")

    def test_the_handed_over_file_is_still_needed_and_still_a_real_overlap(self):
        files = sources()
        for name, generator in HANDED_OVER.items():
            self.assertIn(name, files)
            self.assertNotIn("generate_", "\n".join(files[name].splitlines()[:15]), f"{name} names its generator now: drop it from HANDED_OVER")
            self.assertTrue(any(o[0] == name for o in self._without_handover(files)), f"{name} no longer overlaps: drop it from HANDED_OVER")
            self.assertIn(f"Generated by {generator}", files["items_0027_bottomless_potions.sql"])

    def _without_handover(self, files):
        saved = dict(HANDED_OVER)
        HANDED_OVER.clear()
        try:
            return offenders(files)
        finally:
            HANDED_OVER.update(saved)

    def test_the_elite_clone_generator_renders_only_its_own_range(self):
        import generate_rift_elites as gen
        import generate_monster_models as models
        built = [({"entry": base + native, "name": "x"}, [{"CreatureID": base + native}])
                 for native in (1663, 2000, 12345, 949999) for base in (gen.CHAMPION_BASE, gen.RARE_BASE)]
        sql = gen.render(built)
        family = [models.CHAMPION_BASE + models.FAMILY_ENTRY_BASE + 1, models.CHAMPION_BASE + models.FAMILY_ENTRY_BASE + 65,
                  models.RARE_BASE + models.FAMILY_ENTRY_BASE + 1, models.RARE_BASE + models.FAMILY_ENTRY_BASE + 65]
        parsed = [d for s in statements(sql) if (d := parse_delete(s)) and re.match(r"DELETE", s)]
        self.assertEqual(sorted(d[0] for d in parsed), ["creature_template"] * 2 + ["creature_template_model"] * 2)
        for _, _, test, _ in parsed:
            self.assertFalse(any(test(k) for k in family), "a family clone is inside the DELETE")
            self.assertTrue(any(test(b + 1663) for b in (gen.CHAMPION_BASE, gen.RARE_BASE)))
        # every generated clone is deleted before it is inserted: the bands cover all natives it can write
        for clone, _ in built:
            self.assertTrue(any(t(clone["entry"]) for _, _, t, _ in parsed))
        # a native in the family range is refused, not written under a wide DELETE
        with self.assertRaises(SystemExit):
            gen.render([({"entry": gen.CHAMPION_BASE + gen.NATIVE_LIMIT, "name": "x"}, [])])

    def test_the_check_catches_the_old_bug_and_other_shapes(self):
        own = "INSERT INTO `creature_template` (`entry`,`name`) VALUES (8001663,'x');\n"
        wide = {"rifts_x.sql": "-- Generated by generate_a.py\nDELETE FROM `creature_template` WHERE `entry` >= 8000000;\n" + own,
                "monsters_x.sql": "-- Generated by generate_b.py\nINSERT INTO `creature_template` (`entry`,`name`) VALUES (8950001,'a;b'),(9950001,'c');\n"}
        self.assertEqual([(o[0], o[2], o[4]) for o in offenders(wide)], [("rifts_x.sql", "monsters_x.sql", 2)])
        narrow = dict(wide, **{"rifts_x.sql": "-- Generated by generate_a.py\nDELETE FROM `creature_template` WHERE `entry` BETWEEN 8000000 AND 8949999;\n" + own})
        self.assertEqual(offenders(narrow), [])
        for shape in ("`entry` IN (8950001, 5)", "`entry` = 9950001", "`entry` > 8950000", "`entry` BETWEEN 8900000 AND 8960000"):
            files = dict(wide, **{"rifts_x.sql": f"-- Generated by generate_a.py\nDELETE FROM `creature_template` WHERE {shape};\n" + own})
            self.assertTrue(offenders(files), shape)
        same = {"a_1.sql": wide["rifts_x.sql"], "a_2.sql": wide["rifts_x.sql"] + "INSERT INTO `creature_template` (`entry`) VALUES (8950001);\n"}
        self.assertEqual(offenders(same), [])          # one generator may replace its own rows
        retire = dict(wide, **{"rifts_x.sql": "-- Generated by generate_a.py\nDELETE FROM `creature_template` WHERE `entry` >= 8000000;\n"})
        self.assertEqual(offenders(retire), [])        # a file that only retires rows is not a replace
        other_table = dict(wide, **{"monsters_x.sql": wide["monsters_x.sql"].replace("creature_template", "creature_model_info")})
        self.assertEqual(offenders(other_table), [])    # another table is not covered


if __name__ == "__main__":
    unittest.main(verbosity=2)

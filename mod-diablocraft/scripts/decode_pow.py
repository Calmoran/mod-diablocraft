#!/usr/bin/env python3
"""Decode Diablo III Power (.pow) files and the legendary item / set-bonus tables out of the client MPQs.

Source: reference/blizzless-diiis/src/DiIiS-NA/DataBase/MPQ/Core*.mpq (the main checkout; reference/blizzless-diiis is
gitignored, so a worktree finds it through the git common dir, or D3_MPQ_DIR). The file layouts follow the community
server's readers (DiIiS-NA Core/MPQ/FileFormats/Power.cs, GameBalance.cs, Types/Common.cs, ItemsSystem/FormulaScript.cs).
Needs /usr/bin/smpq (StormLib) to pull a file out of an archive.

  decode_pow.py power ItemPassive_Unique_Ring_001_x1     the power's script formulas SF_n (label = expression) + named tags
  decode_pow.py item Unique_Ring_001_x1                  the legendary item's attributes (the power it grants, its chance)
  decode_pow.py setbonus "Inferno Set 004 (4)"           a set bonus record's attributes
  decode_pow.py rows                                     the 46 catalogue rows that had no chance / no number (ROWS): CSV on stdout

What the pieces mean (checked on powers whose numbers are known, see test_decode_pow.py):
  * `ScriptFormulaDetails` is the list of labels; entry n is SF_n (the list is longer than the SFs a power fills; its I1 field is
    not the index). The value of SF_n is the tag with id 266496 + 256*(n // 10) + 16*(n % 10) (the server's
    PowerTagHelper.GenerateTagForScriptFormula) in the power's GeneralTagMap (a type-4 entry whose text is the formula source, e.g. "9" or "Table(LegendaryProcDmg,61) / 3.5").
  * An item's attribute 1293 (Item_Power_Passive) names the power by SNO; its formula is the item's own number for that
    power (a proc chance as a fraction, 0.05 = 5%, or 1.0 for a power that is simply on). Formulas are a small stack machine:
    6 pushes a float, 1/4 is a random int between the two on the stack, 14 divides.
"""
import csv
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SF_BASE = 266496  # tag id of SF_0; SF_n is SF_BASE + 256 * (n // 10) + 16 * (n % 10)
TAG_PROC_COEFFICIENT = 329983
ATTR_ITEM_POWER_PASSIVE = 1293
ITEM_REC = 1304
SETBONUS_REC = 464
LIST_ITEM, LIST_SETBONUS = 1, 21  # slot of the list in a GameBalance file (header 40 bytes, 16 per list)
MPQ_SUB = "reference/blizzless-diiis/src/DiIiS-NA/DataBase/MPQ"
SRC_SUB = "reference/blizzless-diiis/src/DiIiS-NA"
ARCHIVES = ("Core2.mpq", "Core.mpq", "Core1.mpq", "Core3.mpq", "Core4.mpq")

ROWS = (  # the 46 rows of docs/research/legendary-pow-data.csv, by catalogue name (+ " N-piece"); a fixed list, not a notes phrase:
    # ews9q reworded 13 of their notes, and the catalogue cites these rows by their decoder.md number (txbke, 2026-10-13)
    'Skull of Resonance', 'Cloak of Deception', 'Hellcat Waistguard',
    "Kekegi's Unbreakable Spirit", 'Flying Dragon', 'Vigilance',
    'Bones of Rathma 2-piece', 'Band of Hollow Whispers', 'The Grin Reaper',
    "Archmage's Vicalyke", "Bul-Kathos's Wedding Band", 'Hellfire Ring',
    "Krede's Flame", 'Oculus Ring', 'Pandemonium Loop',
    'Gladiator Gauntlets', "Andariel's Visage", 'Haunt of Vaxo',
    'Moonlight Ward', 'Overwhelming Desire', 'The Ess of Johan',
    'Defender of Westmarch', 'Freeze of Deflection', 'Wall of Man',
    'Azurewrath', 'Fulminator', 'Genzaniku',
    'Shard of Hate', 'Skycutter', 'The Burning Axe of Sankis',
    'Thunderfury, Blessed Blade of the Windseeker', 'Pauldrons of the Skeleton King', 'Goldskin',
    'Ahavarion, Spear of Lycander', 'Bovine Bardiche', 'Burst of Wrath',
    'Corrupted Ashbringer', 'Hellrack', "Maloth's Focus",
    'Maximus', 'The Tormentor', 'Cord of the Sherma',
    'Sanguinary Vambraces', 'Warzechian Armguards', "Asheara's Vestments 4-piece",
    "Demon's Hide 4-piece",
)


def main_checkout():
    """The checkout that holds reference/blizzless-diiis: this one, or the repo's main one when run from a worktree."""
    if (REPO / MPQ_SUB).is_dir():
        return REPO
    common = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True).stdout.strip()
    return Path(common).parent if common else REPO


def mpq_dir():
    return Path(os.environ.get("D3_MPQ_DIR") or main_checkout() / MPQ_SUB)


def available():
    return (mpq_dir() / "Core2.mpq").is_file() and Path("/usr/bin/smpq").exists()


_cache = {}


def extract(name):
    """The bytes of one file of the Core archives ('Power/X.pow', 'GameBalance/Items_Legendary.gam')."""
    if name not in _cache:
        for arc in ARCHIVES:
            with tempfile.TemporaryDirectory() as tmp:
                subprocess.run(["smpq", "-x", str(mpq_dir() / arc), name], cwd=tmp, capture_output=True)
                f = Path(tmp) / name
                if f.is_file():
                    _cache[name] = f.read_bytes()
                    break
        else:
            raise FileNotFoundError(name)
    return _cache[name]


def list_files(prefix):
    out = subprocess.run(["smpq", "-l", str(mpq_dir() / "Core2.mpq")], capture_output=True, text=True).stdout
    return [l.split(None, 3)[3] for l in out.splitlines() if l.split(None, 3)[3:] and l.split(None, 3)[3].startswith(prefix)]


def tag_names():
    return {int(i): n for n, i in re.findall(r"(\w+) = new\((\d+)\)", _read_src("D3-GameServer/Core/Types/TagMap/PowerKeys.cs"))}


def attr_names():
    return {int(i): n for i, n in re.findall(r'new\((\d+), "(\w+)"', _read_src("D3-GameServer/MessageSystem/GameAttribute.List.cs"))}


def _read_src(rel):
    p = main_checkout() / SRC_SUB / rel
    return p.read_text(encoding="utf-8-sig") if p.is_file() else ""


def _i32(d, p):
    return struct.unpack_from("<i", d, p)[0]


def _cstr(b):
    return b.split(b"\0")[0].decode("latin1")


def _tagmap(d, p):
    """Entries of the serialized tag map whose (offset, size) pair sits at p: (tag, type, value[, opcode bytes])."""
    off, size = struct.unpack_from("<ii", d, p)
    if size <= 0:
        return []
    q = off + 16
    n = _i32(d, q)
    q += 4
    out = []
    for _ in range(n):
        typ, tag = struct.unpack_from("<ii", d, q)
        q += 8
        if typ == 1:
            out.append((tag, typ, struct.unpack_from("<f", d, q)[0]))
            q += 4
        elif typ == 4:  # a script formula: 8 ints, the source text (4-aligned by its NameSize), the opcode bytes
            name_size, op_size = struct.unpack_from("<2i", d, q + 20)[0], _i32(d, q + 28)
            q += 32
            e = d.index(b"\0", q)
            text = d[q:e].decode("latin1")
            q = e + 1 + {0: 0, 1: 3, 2: 2, 3: 1}[name_size % 4]
            out.append((tag, typ, text, d[q:q + op_size]))
            q += op_size
        else:
            out.append((tag, typ, _i32(d, q)))
            q += 4
    return out


def parse_power(d):
    """{'sno', 'labels': [SF_n label], 'sf': {n: formula text}, 'tags': {tag id: value}}; the General tag map only."""
    off = 96 + 16  # TagMap, then the General one (each a pointer pair plus 8 skipped bytes)
    general = _tagmap(d, off)
    off, size = struct.unpack_from("<ii", d, 1088)
    labels = []
    for i in range(max(size, 0) // 776):
        q = off + 16 + i * 776
        labels.append(_cstr(d[q:q + 256]))
    sf, tags = {}, {}
    for e in general:
        t = e[0]
        k = t - SF_BASE
        if 0 <= k < 256 * 10 and k % 16 == 0 and k % 256 < 160:
            sf[10 * (k // 256) + k % 256 // 16] = e[2]
        else:
            tags[t] = e[2]
    return {"sno": _i32(d, 16), "labels": labels, "sf": sf, "tags": tags}


def power_by_sno():
    """{sno: file name} for every Power file in Core2.mpq (one smpq call extracts them all; the bytes are cached)."""
    names = [n for n in list_files("Power/") if n.lower().endswith(".pow")]
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["smpq", "-x", str(mpq_dir() / "Core2.mpq")] + names, cwd=tmp, capture_output=True)
        out = {}
        for n in names:
            _cache[n] = (Path(tmp) / n).read_bytes()
            out[_i32(_cache[n], 16)] = n
    return out


def evaluate(ints):
    """The (lo, hi) of an attribute formula, or None when it reads game attributes (opcode 5). A constant has lo == hi."""
    st, i = [], 0
    while i < len(ints):
        op = ints[i] & 0xFF
        if op == 0:
            return st[-1] if st else None
        if op == 6:
            f = struct.unpack("<f", struct.pack("<i", ints[i + 1]))[0]
            st.append((f, f))
            i += 1
        elif op == 1:  # func: 3 = int in [a, a+b], 4 = int in [a, b]
            fn = ints[i + 1] & 0xFF
            b, a = st.pop(), st.pop()
            st.append((a[0], a[0] + b[0]) if fn == 3 else (a[0], b[0]) if fn == 4 else (None, None))
            i += 1
        elif op in (11, 12, 13, 14):
            b, a = st.pop(), st.pop()
            if op == 14:
                st.append((a[0] / b[0], a[1] / b[0]))
            else:
                f = {11: lambda x, y: x + y, 12: lambda x, y: x - y, 13: lambda x, y: x * y}[op]
                st.append((f(a[0], b[0]), f(a[1], b[1])))
        else:
            return None
        i += 1
    return None


def fmt_range(r):
    if r is None:
        return "(reads game attributes)"
    lo, hi = r
    return f"{lo:g}" if lo == hi else f"{lo:g}-{hi:g}"


def parse_gam_list(d, slot, rec_size):
    """The raw records of one list of a GameBalance file."""
    off, size = struct.unpack_from("<ii", d, 40 + 16 * slot)
    return [d[off + 16 + i * rec_size: off + 16 + (i + 1) * rec_size] for i in range(size // rec_size)] if size > 0 else []


def _attributes(d, rec, start, count):
    """[(attribute id, SNO param, formula ints)] of the AttributeSpecifier array at `start` in a record (24 bytes each)."""
    out = []
    for k in range(count):
        q = start + 24 * k
        aid, sno = struct.unpack_from("<ii", rec, q)
        off, size = struct.unpack_from("<ii", rec, q + 16)
        f = list(struct.unpack_from("<%di" % (size // 4), d, off + 16)) if size > 0 and off else []
        if aid != -1 or sno != -1 or f:
            out.append((aid, sno, f))
    return out


def items():
    """{item name: [(attribute id, SNO param, formula ints)]} for Items_Legendary.gam."""
    d = extract("GameBalance/Items_Legendary.gam")
    return {_cstr(r[:256]): _attributes(d, r, 504, 16) for r in parse_gam_list(d, LIST_ITEM, ITEM_REC)}


def set_bonuses():
    """{bonus record name: (piece count, [(attribute id, SNO param, formula ints)])} for SetItemBonuses.gam."""
    d = extract("GameBalance/SetItemBonuses.gam")
    return {_cstr(r[:256]): (_i32(r, 268), _attributes(d, r, 272, 8)) for r in parse_gam_list(d, LIST_SETBONUS, SETBONUS_REC)}


def power_report(sno_map, sno, an=None):
    """One power as {'file', 'sf': [(n, label, text)], 'coefficient'} (None when no Power file has that SNO)."""
    name = sno_map.get(sno)
    if not name:
        return None
    p = parse_power(extract(name))
    sf = [(n, p["labels"][n] if n < len(p["labels"]) else "", p["sf"][n]) for n in sorted(p["sf"])]
    return {"file": name.split("/", 1)[1], "sf": sf, "coefficient": p["tags"].get(TAG_PROC_COEFFICIENT)}


def describe_attrs(attrs, sno_map):
    an = attr_names()
    lines = []
    for aid, sno, f in attrs:
        pw = f" -> {sno_map.get(sno, 'no Power file for SNO %d' % sno).split('/')[-1]}" if aid == ATTR_ITEM_POWER_PASSIVE else (f" param {sno}" if sno != -1 else "")
        lines.append(f"  {an.get(aid, aid)} ({aid}){pw}: {fmt_range(evaluate(f))}")
    return lines


def cmd_power(arg):
    name = arg if "/" in arg else f"Power/{arg}"
    name = name if name.lower().endswith(".pow") else name + ".pow"
    p = parse_power(extract(name))
    print(f"{name} sno={p['sno']}")
    for n in sorted(p["sf"]):
        print(f"  SF_{n} {p['labels'][n] if n < len(p['labels']) else ''!r} = {p['sf'][n]}")
    tn = tag_names()
    for t, v in p["tags"].items():
        if t in (TAG_PROC_COEFFICIENT,) or tn.get(t) in ("CooldownTime", "ResourceCost", "BaseDamageScalar"):
            print(f"  {tn.get(t, t)} = {v}")


POWER_TABLES = "GameBalance/PowerFormulaTables.gam"
POWER_TABLE_SLOT, POWER_TABLE_REC = 24, 1328  # the list of Table(Name, level) tables: a 1024-byte name and 76 floats, one per level


def power_table(name):
    """The 76 values of a `Table(<name>, level)` of the power formulas ('Healing', 'DmgTier1' ...), indexed by level."""
    data = extract(POWER_TABLES)
    off, size = struct.unpack_from("<ii", data, 40 + 16 * POWER_TABLE_SLOT)
    for i in range(size // POWER_TABLE_REC):
        rec = data[off + 16 + i * POWER_TABLE_REC: off + 16 + (i + 1) * POWER_TABLE_REC]
        if rec[:1024].split(b"\0")[0].decode() == name:
            return list(struct.unpack_from("<76f", rec, 1024))
    raise KeyError(name)


def cmd_table(arg):
    for level, value in enumerate(power_table(arg)):
        print(f"{level},{value:g}")


def cmd_item(arg):
    attrs = items()[arg]
    print(arg)
    print("\n".join(describe_attrs(attrs, power_by_sno())))


def cmd_setbonus(arg):
    cnt, attrs = set_bonuses()[arg]
    print(f"{arg}: {cnt} pieces")
    print("\n".join(describe_attrs(attrs, power_by_sno())))


# Catalogue rows with no item record to follow. A set row is a set-bonus record (identified by its pieces and numbers,
# see the research note); two item rows have no link in their item record, only a Power file named for the item.
SET_ROWS = {"Bones of Rathma": "P6_Necro_Set_1 (2)", "Asheara's Vestments": "Crafted Hell Set 001_x1 (4)",
            "Demon's Hide": "Crafted Inferno Set 001_x1 (5)"}
BY_NAME = {"Hellfire Ring": "Power/ItemPassive_Unique_Ring_Hellfire_x1.pow", "Wall of Man": "Power/itemPassive_Unique_Shield_011.pow"}


def _row_power(sno_map, r, its, bonuses):
    """(how the row reaches its power, the power report or None, the attribute-1293 number or '')."""
    attrs, name = its.get(r["d3_id"]), r["item_or_set"]
    if name in SET_ROWS:
        attrs, how = bonuses[SET_ROWS[name]][1], "set bonus " + SET_ROWS[name]
    else:
        how = "item " + r["d3_id"]
    for a in attrs or []:
        if a[0] == ATTR_ITEM_POWER_PASSIVE and a[1] in sno_map:
            return how, power_report(sno_map, a[1]), fmt_range(evaluate(a[2]))
    if name in BY_NAME:
        sno = parse_power(extract(BY_NAME[name]))["sno"]
        return "named for the item (its record has no link)", power_report(sno_map, sno), ""
    return how + " (no power link)", None, ""


def cmd_rows():
    sno_map, its, bonuses = power_by_sno(), items(), set_bonuses()
    rows = list(csv.DictReader(open(REPO / "docs/research/legendary-catalogue.csv", encoding="utf-8")))
    sel = [r for r in rows if r["item_or_set"] + (f" {r['pieces']}-piece" if r["pieces"] else "") in ROWS]
    assert len(sel) == len(ROWS), "a ROWS name is not in the catalogue: " + str(set(ROWS) - {r["item_or_set"] for r in sel})
    w = csv.writer(sys.stdout, lineterminator="\n")
    w.writerow(["item_or_set", "linked_by", "power_file", "item_number", "script_formulas", "proc_coefficient_of_power"])
    for r in sel:
        how, pw, num = _row_power(sno_map, r, its, bonuses)
        w.writerow([r["item_or_set"] + (f" {r['pieces']}-piece" if r["pieces"] else ""), how, pw["file"] if pw else "", num,
                    "; ".join(f"SF_{n} {l} = {t}" for n, l, t in pw["sf"]) if pw else "",
                    pw["coefficient"] if pw else ""])


if __name__ == "__main__":
    cmds = {"power": cmd_power, "table": cmd_table, "item": cmd_item, "setbonus": cmd_setbonus, "rows": lambda: cmd_rows()}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds or not available():
        sys.exit(__doc__ if available() else "needs reference/blizzless-diiis (the main checkout) and /usr/bin/smpq")
    cmds[sys.argv[1]](*sys.argv[2:])

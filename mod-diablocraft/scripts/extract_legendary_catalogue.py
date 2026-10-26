#!/usr/bin/env python3
"""The factual columns of docs/research/legendary-catalogue.csv (diablocraft-kl0b, research only).

One row per legendary power (base_items.csv rarity legendary, pool_version yes) and one row per set bonus
(2, 3, 4, 6 pieces) of the 57 sets of the pool. item_or_set, d3_id, slot, class, pieces, power_text, power_source
and source_flags are READ from the D3Planner files, nothing typed in: each item from the file base_items.csv names as its
source_file (item_*.js, or data.json for the 168 items only it has). SET BONUSES come from data.json's itemSets,
the current bonuses (the reworked Raekor, Might of the Earth, the patch 7.4 sets, the "(Emanates)" marks): it holds all
61 set keys, the 60 of data_itemsets.js and Guardian's Jeopardy. data_itemsets.js is the older file and differs
from data.json in 61 of the 139 bonus rows, so it is never read for set text (the test refuses its text where the two
differ). Items differ between the two sources too; for items the pool's own source_file decides. The judgement
columns (kind, skills, build, build_source, hooks, needs, notes, and szvt's damage_bucket and bucket_source) come
from docs/research/legendary-judgement.csv, keyed by `key` (an item's d3_id, or `<set key>|<pieces>`), and are the
researcher's.

    python3 mod-diablocraft/scripts/extract_legendary_catalogue.py            # writes the catalogue CSV
    python3 mod-diablocraft/scripts/extract_legendary_catalogue.py --facts    # prints key + facts only

power_text rules (the test re-derives them from the source by its own path):
  * an item with a `required.custom` power: its `format`, the one number placeholder (%d, %.1f, %{0}d) shown as
    [min-max] (or [n] when min = max), `%%` as `%`, a line break as ' / '. `power_source` = custom.
  * `fixed_stats`: the item's other `required` stats beside a custom power (26 rows: Slorak's Madness, Gyana Na Kashu,
    Dread Iron...), rendered from data_stats.js and joined with ' | '. A `skill_<class>_<skill>` stat is not in
    data_stats.js (D3Planner builds its name at runtime): it reads "<skill name from data.json> damage +[n-m]%".
  * an item with no custom power but fixed `required` stats: those stats rendered from data_stats.js formats.
    `power_source` = required_stats.
  * otherwise blank, `power_source` = none (a stat stick or a preset roll only).
  * a set bonus: its entries joined with ' | ', a `stat` entry rendered from data_stats.js, a `format` entry as
    written (`%%` as `%`).
source_flags carries the source's own marks: follower, cube, best=min, altformat.
"""
import csv
import json
import re
import sys
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1]
ROOT = MODULE.parent
D3PLANNER = ROOT / "reference" / "d3planner"
BASE_ITEMS = MODULE / "data" / "d3" / "base_items.csv"
JUDGEMENT = ROOT / "docs" / "research" / "legendary-judgement.csv"
OUTPUT = ROOT / "docs" / "research" / "legendary-catalogue.csv"

FACTS = ["key", "item_or_set", "d3_id", "slot", "class", "pieces", "power_text", "fixed_stats", "power_source", "source_flags"]
JUDGED = ["kind", "skills", "build", "build_source", "hooks", "needs", "notes", "damage_bucket", "bucket_source"]
COLUMNS = ["item_or_set", "d3_id", "slot", "class", "pieces", "power_text", "fixed_stats", "power_source", "source_flags"] + JUDGED
CLASS_ORDER = ["barbarian", "crusader", "demonhunter", "monk", "necromancer", "witchdoctor", "wizard", "any"]

# Four set names exist twice in data.json: the legacy bonuses and the current ones. The pool's pieces are the
# current ones (pool_version yes: P74_ guardian pieces, the _v2 sets), so the current key is the catalogue's.
CURRENT_SET_KEY = {
    "Aughild's Authority": "aughild_v2",
    "Cain's Destiny": "cain_v2",
    "Captain Crimson's Trimmings": "crimson_v2",
    "Guardian's Jeopardy": "guardian_p74",
}

PLACEHOLDER = re.compile(r"%[-+.0-9]*(?:\{\d+\})?[a-zA-Z]")


class SourceError(Exception):
    pass


class JSReader:
    """A small reader for the D3Planner JS files: object and array literals with bare keys, comments, trailing
    commas, `_L("text")` calls and `"a" + "b"` joins. A call comes back as its first argument (the text),
    any other bare name as the string of its name."""

    NAME = re.compile(r"[A-Za-z_$][\w$.]*")
    NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")

    def __init__(self, text, pos=0):
        self.text, self.pos = text, pos

    def skip(self):
        t = self.text
        while self.pos < len(t):
            if t[self.pos] in " \t\r\n":
                self.pos += 1
            elif t.startswith("//", self.pos):
                while self.pos < len(t) and t[self.pos] != "\n":
                    self.pos += 1
            elif t.startswith("/*", self.pos):
                self.pos = t.index("*/", self.pos) + 2
            else:
                break

    def string(self):
        t, quote, out = self.text, self.text[self.pos], []
        self.pos += 1
        while t[self.pos] != quote:
            if t[self.pos] == "\\" and t[self.pos + 1] == "u":
                out.append(chr(int(t[self.pos + 2:self.pos + 6], 16)))
                self.pos += 6
            elif t[self.pos] == "\\":
                out.append({"n": "\n", "r": "\r", "t": "\t"}.get(t[self.pos + 1], t[self.pos + 1]))
                self.pos += 2
            else:
                out.append(t[self.pos])
                self.pos += 1
        self.pos += 1
        return "".join(out)

    def value(self):
        t = self.text
        self.skip()
        c = t[self.pos]
        if c == "{":
            self.pos += 1
            out = {}
            while True:
                self.skip()
                if t[self.pos] == "}":
                    self.pos += 1
                    return out
                if t[self.pos] in "\"'":
                    key = self.string()
                else:
                    found = self.NAME.match(t, self.pos) or re.compile(r"\d+").match(t, self.pos)
                    key, self.pos = found.group(), found.end()
                self.skip()
                if t[self.pos] != ":":
                    raise SourceError(f"JS: expected ':' near {t[max(0, self.pos - 40):self.pos + 20]!r}")
                self.pos += 1
                out[key] = self.value()
                self.skip()
                if t[self.pos] == ",":
                    self.pos += 1
        if c == "[":
            self.pos += 1
            out = []
            while True:
                self.skip()
                if t[self.pos] == "]":
                    self.pos += 1
                    return out
                out.append(self.value())
                self.skip()
                if t[self.pos] == ",":
                    self.pos += 1
        if c in "\"'":
            text = self.string()
            self.skip()
            while t[self.pos] == "+":
                self.pos += 1
                self.skip()
                text += self.string()
                self.skip()
            return text
        found = self.NUMBER.match(t, self.pos)
        if found:
            self.pos = found.end()
            number_ = float(found.group())
            return int(number_) if "." not in found.group() and "e" not in found.group().lower() else number_
        found = self.NAME.match(t, self.pos)
        if not found:
            raise SourceError(f"JS: cannot read a value near {t[self.pos:self.pos + 40]!r}")
        name, self.pos = found.group(), found.end()
        self.skip()
        if name in ("true", "false", "null"):
            return {"true": True, "false": False, "null": None}[name]
        if t[self.pos] == "(":
            self.pos += 1
            args = []
            while True:
                self.skip()
                if t[self.pos] == ")":
                    self.pos += 1
                    break
                args.append(self.value())
                self.skip()
                if t[self.pos] == ",":
                    self.pos += 1
            return args[0] if args else ""
        return name


def read_js_items(name):
    """The item objects of one item_*.js file (DiabloCalc.addItems([...]))."""
    text = (D3PLANNER / name).read_text(encoding="utf-8")
    start = text.index("addItems(") + len("addItems(")
    return JSReader(text, start).value()


def read_js_sets():
    """{set key: set object} of data_itemsets.js (DiabloCalc.itemSets = {...})."""
    text = (D3PLANNER / "data_itemsets.js").read_text(encoding="utf-8")
    start = text.index("itemSets = ") + len("itemSets = ")
    return JSReader(text, start).value()


def load_stats():
    """{stat key: (name, format or None)} from data_stats.js, line by line (the file is a JS literal, not JSON)."""
    stats = {}
    line_re = re.compile(r'^\s{4}"?(\w+)"?: \{(.*)\},?\s*$')
    for line in (D3PLANNER / "data_stats.js").read_text(encoding="utf-8").splitlines():
        found = line_re.match(line)
        if not found:
            continue
        name = re.search(r'name: "((?:[^"\\]|\\.)*)"', found.group(2))
        form = re.search(r'format: "((?:[^"\\]|\\.)*)"', found.group(2))
        if name:
            stats[found.group(1)] = (name.group(1), form.group(1) if form else None)
    return stats


def number(value):
    return str(int(value)) if float(value) == int(value) else str(value)


def span(low, high):
    return f"[{number(low)}]" if low == high else f"[{number(low)}-{number(high)}]"


def clean(text):
    return text.replace("%%", "%").replace("\r\n", " / ").replace("\n", " / ")


def render_custom(custom):
    text = custom["format"].replace("%%", "\0")
    if "min" in custom:
        shown = span(custom["min"], custom["max"])
        text = PLACEHOLDER.sub(lambda _: shown, text)
    return clean(text.replace("\0", "%%"))


def skill_names():
    """{(class, skill key): skill name} from data.json's skills; data_stats.js builds `skill_<class>_<skill>` stat names
    at runtime from these, so it has no entry for them."""
    skills = json.loads((D3PLANNER / "data.json").read_text(encoding="utf-8"))["skills"]
    return {(c, k): v["name"] for c, group in skills.items() for k, v in group.items() if isinstance(v, dict) and "name" in v}


SKILL_STAT = re.compile(r"skill_([a-z]+)_([a-z0-9_]+)")


def render_stat(key, value, stats):
    """One stat with a value: a number list, {min, max}, a named range (string) or empty."""
    name, form = stats.get(key, (key, None))
    skill = SKILL_STAT.fullmatch(key) if key not in stats else None
    names = skill_names() if skill else {}
    if skill and (skill.group(1), skill.group(2)) in names:
        # a per-skill damage bonus, in percent
        name = f"{names[(skill.group(1), skill.group(2))]} damage"
        form = f"{name} +%d%%"
    if isinstance(value, list):
        shown = number(value[0]) if len(value) == 1 else span(value[0], value[-1])
    elif isinstance(value, dict) and "min" in value:
        shown = span(value["min"], value["max"])
    elif isinstance(value, str):
        shown = f"({value})"
    else:
        return name
    if form:
        return clean(PLACEHOLDER.sub(lambda _: shown, form.replace("%%", "\0"), count=1).replace("\0", "%%"))
    return f"{name} {shown}"


def power_of(item, stats):
    required = item.get("required") or {}
    custom = required.get("custom")
    flags = []
    if custom:
        for flag in ("follower", "cube"):
            if custom.get(flag):
                flags.append(flag)
        if custom.get("best"):
            flags.append(f"best={custom['best']}")
        if "altformat" in custom:
            flags.append("altformat")
        others = [render_stat(k, v, stats) for k, v in required.items() if k != "custom"]
        return render_custom(custom), " | ".join(others), "custom", ";".join(flags)
    fixed = [render_stat(k, v, stats) for k, v in required.items()]
    if fixed:
        return " | ".join(fixed), "", "required_stats", ""
    return "", "", "none", ""


def read_pool():
    with BASE_ITEMS.open(encoding="utf-8-sig", newline="") as stream:
        # The catalogue is D3's: a legendary Torment adds (source_file torment_shaman) has no D3 source file to read.
        return [r for r in csv.DictReader(stream) if r["pool_version"] == "yes" and r["rarity"] in ("legendary", "set")
                and r["source_file"] != "torment_shaman"]


def source_items(pool):
    """{source file name: {id or alias: item object}} for the files the pool names (item_*.js, data.json)."""
    out = {}
    for name in sorted({e["source_file"] for e in pool}):
        if name == "data.json":
            items = json.loads((D3PLANNER / name).read_text(encoding="utf-8"))["items"]
        else:
            items = read_js_items(name)
        table = {}
        for item in items:
            for ident in [item["id"]] + list(item.get("ids", [])):
                if ident in table and ident == item["id"]:
                    raise SourceError(f"{name} lists {ident} twice")
                table.setdefault(ident, item)
        out[name] = table
    return out


def source_sets():
    """The current set bonuses: data.json's itemSets (data_itemsets.js is the older file and is not read here)."""
    return json.loads((D3PLANNER / "data.json").read_text(encoding="utf-8"))["itemSets"]


def facts():
    stats = load_stats()
    pool = read_pool()
    tables = source_items(pool)
    rows = []
    for entry in pool:
        if entry["rarity"] != "legendary":
            continue
        item = tables[entry["source_file"]].get(entry["d3_id"])
        if item is None:
            raise SourceError(f"{entry['d3_id']} ({entry['d3_name']}) is not in {entry['source_file']}")
        text, fixed, source, flags = power_of(item, stats)
        rows.append({"key": entry["d3_id"], "item_or_set": entry["d3_name"], "d3_id": entry["d3_id"],
                     "slot": entry["slot"], "class": entry["designated_class"] or "any", "pieces": "",
                     "power_text": text, "fixed_stats": fixed, "power_source": source, "source_flags": flags})
    all_sets = source_sets()
    set_names = sorted({e["set_name"] for e in pool if e["rarity"] == "set"})
    for name in set_names:
        matches = [k for k, v in all_sets.items() if v["name"] == name]
        if not matches:
            raise SourceError(f"set {name!r} is not in data_itemsets.js or data.json")
        key = CURRENT_SET_KEY.get(name)
        if key is None:
            if len(matches) != 1:
                raise SourceError(f"set {name!r} has {matches}; name the current one in CURRENT_SET_KEY")
            key = matches[0]
        elif key not in matches:
            raise SourceError(f"CURRENT_SET_KEY {name!r} -> {key!r} is not in the sources")
        the_set = all_sets[key]
        for pieces in sorted(the_set["bonuses"], key=int):
            parts, follower = [], False
            for bonus in the_set["bonuses"][pieces]:
                if "format" in bonus:
                    parts.append(clean(bonus["format"]))
                    follower = follower or bool(bonus.get("follower"))
                else:
                    parts.append(render_stat(bonus["stat"], bonus["value"], stats))
            rows.append({"key": f"{key}|{pieces}", "item_or_set": name, "d3_id": key, "slot": "set",
                         "class": the_set.get("tclass") or the_set.get("class") or "any", "pieces": pieces,
                         "power_text": " | ".join(parts), "fixed_stats": "", "power_source": "set_bonus",
                         "source_flags": "follower" if follower else ""})
    return rows


def sort_key(row):
    return (CLASS_ORDER.index(row["class"]), row["pieces"] != "", row["slot"], row["item_or_set"], int(row["pieces"] or 0))


def read_judgement(path=JUDGEMENT):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["key"] + JUDGED:
            raise SourceError(f"{path.name}: header is {reader.fieldnames}, expected {['key'] + JUDGED}")
        out = {}
        for number_, row in enumerate(reader, 2):
            if row["key"] in out:
                raise SourceError(f"{path.name}:{number_}: {row['key']} twice")
            out[row["key"]] = row
        return out


def catalogue(rows, judged):
    out = []
    for row in sorted(rows, key=sort_key):
        mine = judged.get(row["key"], {})
        merged = {c: row.get(c, "") for c in COLUMNS[:-len(JUDGED)]}
        merged.update({c: mine.get(c, "") for c in JUDGED})
        out.append(merged)
    return out


def main():
    rows = facts()
    if "--facts" in sys.argv:
        writer = csv.writer(sys.stdout, lineterminator="\n")
        writer.writerow(FACTS)
        for row in sorted(rows, key=sort_key):
            writer.writerow([row[c] for c in FACTS])
        return
    judged = read_judgement()
    missing = [r["key"] for r in rows if r["key"] not in judged]
    extra = sorted(set(judged) - {r["key"] for r in rows})
    if extra:
        raise SourceError(f"judgement rows with no source row: {extra[:5]}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(catalogue(rows, judged))
    print(f"{len(rows)} rows ({sum(1 for r in rows if not r['pieces'])} powers, "
          f"{sum(1 for r in rows if r['pieces'])} set bonuses), {len(missing)} without a judgement row -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        main()
    except SourceError as error:
        sys.exit(f"extract_legendary_catalogue: {error}")

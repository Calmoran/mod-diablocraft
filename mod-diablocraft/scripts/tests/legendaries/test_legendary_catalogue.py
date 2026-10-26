#!/usr/bin/env python3
"""diablocraft-kl0b: every row of docs/research/legendary-catalogue.csv matches its D3Planner source, and no pool
item or set bonus is missing or doubled. Run: python3 mod-diablocraft/scripts/tests/legendaries/test_legendary_catalogue.py

Three sources are cross-read: base_items.csv says which items are the pool, data.json says what each says, and the
original JS files (item_*.js, data_itemsets.js) must also contain each power's and bonus's text. The check function
is run on the committed catalogue and then on mutants (a dropped row, a doubled row, an edited text, a wrong class,
a lost bonus level), each of which must be refused.
"""
import copy
import csv
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import extract_legendary_catalogue as X  # noqa: E402

KINDS = {"K0", "K1", "K2", "K3", "K4", "K5", "K6"}
# 258tf: K6 "a number on a game system" is a kind (the designer, decisions.md 2026-10-10 (2)): the nine rows that were K0 NO-FIT
# (legendary-catalogue.md section 8) and no others.
K6_ROWS = {"P4_Unique_Mojo_002", "Unique_Boots_008_x1", "Unique_Gloves_103_x1", "Unique_Amulet_107_x1",
           "Unique_Amulet_108_x1", "P66_Unique_Amulet_001", "blackthorne|4", "cain_v2|3", "sage|3"}
HOOK_REF = re.compile(r"mod-diablocraft/src/[\w/.-]+\.(?:cpp|h):\d+")
URL = re.compile(r"^https://(?:www\.)?(?:maxroll\.gg|icy-veins\.com)/")
BUCKET = re.compile(r"^(?:multiplier|unknown|additive:[a-z_]+)$")


def problems_in_buckets(judged):
    out = []
    for key, j in judged.items():
        bucket, source = j["damage_bucket"], j["bucket_source"]
        if bucket and not BUCKET.match(bucket):
            out.append(f"{key}: damage_bucket {bucket!r} is not multiplier, unknown or additive:<pool>")
        if bool(bucket) != bool(source):
            out.append(f"{key}: damage_bucket and bucket_source go together")
    return out


# mx25: a power planned into the wrong damage bucket. The terms are the code's own names (damage-buckets.md 6a/6b):
# the additive pool's readers, and the readers and slots that multiply.
ADDITIVE_TERM = re.compile(r"\w*(?:DamageBonus|TargetBonus|ElementalBonus)|elementalDamage|\badditive\b")
MULTIPLYING_TERM = re.compile(r"\w*(?:SkillFactor|TargetFactor|PetFactor)|Standalone|hit\.legendary|AddFactor|Multipliers")


def problems_in_hooks(judged):
    """A multiplier row plans no additive term, an additive row plans no multiplying one; unknown and blank rows are free."""
    out = []
    for key, j in judged.items():
        bucket = j["damage_bucket"]
        if bucket == "multiplier" and (m := ADDITIVE_TERM.search(j["hooks"])):
            out.append(f"{key}: a multiplier plans the additive term {m.group(0)!r}")
        if bucket.startswith("additive:") and (m := MULTIPLYING_TERM.search(j["hooks"])):
            out.append(f"{key}: an additive bonus plans the multiplying term {m.group(0)!r}")
    return out


def problems_in_k0_k6(rows, judged):
    """K0 holds no power to build; K6 is exactly the designer's nine, each a power with its note saying K6."""
    out = []
    for r in rows:
        j = judged[r["key"]]
        if r["power_source"] == "none" and j["kind"] != "K0":
            out.append(f"{r['key']}: no power in the source but {j['kind']}")
        if j["kind"] == "K0" and r["power_source"] == "custom" and not (
                "flavour text only" in j["notes"] or "nothing to build" in j["notes"]):
            out.append(f"{r['key']}: a custom power is K0 only as flavour text or nothing to build")
        if j["notes"].startswith("NO-FIT"):
            out.append(f"{r['key']}: still marked NO-FIT")
        if (j["kind"] == "K6") != (r["key"] in K6_ROWS):
            out.append(f"{r['key']}: {j['kind']}, but K6 is the nine rows of the ruling")
        if j["kind"] == "K6" and not (r["power_text"] and j["notes"].startswith("K6")):
            out.append(f"{r['key']}: a K6 row needs a power and a note that starts with K6")
    return out


# ews9q (decisions.md 2026-10-10, a59b3b3e / dae5052f): the ten rows whose item value is read as the chance, each with the
# fraction the decoder note tabulates from the Power files (legendary-pow-data.csv, column item_number). The Grin Reaper's 0.5
# is the designer's number and is not in this list. Where the text and the data differ, the text wins (Flying Dragon doubles).
ITEM_CHANCE_ROWS = {"Unique_Polearm_001_x1": "Vigilance", "Unique_Axe_1H_003_x1": "Genzaniku", "Unique_Sword_1H_004_x1": "Skycutter",
                    "Unique_XBow_002_x1": "Hellrack", "Unique_Sword_2H_010_x1": "Maximus", "Unique_Staff_007_x1": "The Tormentor",
                    "Unique_Chest_001_x1": "Goldskin", "Unique_Axe_1H_007_x1": "The Burning Axe of Sankis",
                    "Unique_CombatStaff_2H_009_x1": "Flying Dragon", "demon|4": "Demon's Hide 4-piece"}
SANKIS = "Unique_Axe_1H_007_x1"


def problems_in_item_chances(judged, fractions):
    """Each item-fraction row says its chance, where it comes from and that it is a reading; Sankis is Ignore Pain, not a block."""
    out = []
    for key, name in ITEM_CHANCE_ROWS.items():
        j = judged[key]
        want = f"chance {float(fractions[name]):g} "
        if want not in j["notes"]:
            out.append(f"{key}: the notes do not say '{want}' (the Power file's item value of {name})")
        if "item value read as chance" not in j["notes"] and key != SANKIS:
            out.append(f"{key}: the notes do not name the source 'item value read as chance'")
    sankis = judged[SANKIS]
    if sankis["kind"] != "K3" or "Ignore Pain" not in sankis["needs"] or "0.08" not in sankis["notes"]:
        out.append(f"{SANKIS}: Ignore Pain on being hit at 0.08 is K3")
    if re.search(r"block", sankis["needs"] + sankis["hooks"], re.I):
        out.append(f"{SANKIS}: still planned as a block")
    return out


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def own_text(custom):
    """The expected power text, derived by a different route than the extractor: split on the placeholders."""
    pieces = re.split(r"(%%|%[-+.0-9]*(?:\{\d+\})?[a-zA-Z])", custom["format"])
    shown = ""
    if "min" in custom:
        lo, hi = custom["min"], custom["max"]
        f = lambda v: str(int(v)) if v == int(v) else str(v)  # noqa: E731
        shown = f"[{f(lo)}]" if lo == hi else f"[{f(lo)}-{f(hi)}]"
    out = []
    for piece in pieces:
        if piece == "%%":
            out.append("%")
        elif "min" in custom and re.fullmatch(r"%[-+.0-9]*(?:\{\d+\})?[a-zA-Z]", piece):
            out.append(shown)
        else:
            out.append(piece)
    return "".join(out).replace("\r\n", " / ").replace("\n", " / ")


def in_raw(raw, text):
    """Is `text` in the raw JS/JSON file, however the file spells its quotes and non-ASCII characters."""
    return any(v in raw for v in (json.dumps(text)[1:-1], json.dumps(text, ensure_ascii=False)[1:-1],
                                  text, text.replace('"', "'")))


def span_of(value):
    """The number text a required stat must show: [min-max], [n] or the plain number."""
    f = lambda v: str(int(v)) if v == int(v) else str(v)  # noqa: E731
    if isinstance(value, dict) and "min" in value:
        return f"[{f(value['min'])}]" if value["min"] == value["max"] else f"[{f(value['min'])}-{f(value['max'])}]"
    if isinstance(value, list):
        return f(value[0]) if len(value) == 1 else f"[{f(value[0])}-{f(value[-1])}]"
    return str(value)


class Source:
    def __init__(self):
        self.pool = X.read_pool()
        self.tables = X.source_items(self.pool)
        self.legendary = [p for p in self.pool if p["rarity"] == "legendary"]
        self.set_items = [p for p in self.pool if p["rarity"] == "set"]
        self.raw = {name: (X.D3PLANNER / name).read_text(encoding="utf-8") for name in self.tables}
        self.sets_raw = (X.D3PLANNER / "data_itemsets.js").read_text(encoding="utf-8")
        self.json_raw = (X.D3PLANNER / "data.json").read_text(encoding="utf-8")
        # SET RULE (stated in the extractor's docstring): set bonuses are data.json's itemSets, the current ones.
        # Read here straight from the file, not through the extractor; data_itemsets.js is the older file and its
        # text must not be in the catalogue where the two differ.
        self.sets = json.loads(self.json_raw)["itemSets"]
        self.old_sets = X.read_js_sets()
        self.skills = json.loads(self.json_raw)["skills"]
        self.stat_keys = set(re.findall(r'^\s{4}"?(\w+)"?: \{', (X.D3PLANNER / "data_stats.js").read_text(encoding="utf-8"), re.M))
        self.set_class = {r["set_name"]: r["class_key"] for r in read(X.MODULE / "data" / "d3" / "set_classes.csv")}

    def item(self, entry):
        return self.tables[entry["source_file"]][entry["d3_id"]]


def problems(rows, src):
    """Everything wrong with `rows` (the factual columns) against the source; [] when nothing."""
    found = []
    by_key = {}
    for row in rows:
        key = row["d3_id"] if not row["pieces"] else f"{row['d3_id']}|{row['pieces']}"
        if key in by_key:
            found.append(f"{key}: doubled")
        by_key[key] = row
    # every pool legendary is there once, with its own name, slot, class and power
    for entry in src.legendary:
        row = by_key.get(entry["d3_id"])
        if row is None:
            found.append(f"{entry['d3_id']}: missing")
            continue
        item = src.item(entry)
        required = item.get("required") or {}
        custom = required.get("custom")
        if (row["item_or_set"], row["slot"]) != (entry["d3_name"], entry["slot"]):
            found.append(f"{entry['d3_id']}: name or slot differs")
        if row["class"] != (entry["designated_class"] or "any"):
            found.append(f"{entry['d3_id']}: class {row['class']} but the pool says {entry['designated_class'] or 'any'}")
        if custom:
            if row["power_text"] != own_text(custom) or row["power_source"] != "custom":
                found.append(f"{entry['d3_id']}: power_text differs from {entry['source_file']}")
            others = [(k, v) for k, v in required.items() if k != "custom"]
            shown = [p for p in row["fixed_stats"].split(" | ") if p]
            if len(shown) != len(others):
                found.append(f"{entry['d3_id']}: fixed_stats do not match the source's other required stats")
            for (k, v), piece in zip(others, shown):
                if not isinstance(v, str) and span_of(v) not in piece:
                    found.append(f"{entry['d3_id']}: fixed stat {k} shows {piece!r}, not the source's {span_of(v)}")
                m = re.fullmatch(r"skill_([a-z]+)_([a-z0-9_]+)", k)
                if m and k not in src.stat_keys and src.skills[m.group(1)][m.group(2)]["name"] not in piece:
                    found.append(f"{entry['d3_id']}: fixed stat {k} is not shown by its skill's name")
            # the file itself must carry the format string (the reader is not trusted alone)
            if not in_raw(src.raw[entry["source_file"]], custom["format"]):
                found.append(f"{entry['d3_id']}: format not found in {entry['source_file']}")
        elif required:
            if row["power_source"] != "required_stats" or not row["power_text"]:
                found.append(f"{entry['d3_id']}: fixed stats not carried")
        elif row["power_source"] != "none" or row["power_text"]:
            found.append(f"{entry['d3_id']}: a power the source lacks")
    pool_ids = {e["d3_id"] for e in src.legendary}
    for key, row in by_key.items():
        if not row["pieces"] and key not in pool_ids:
            found.append(f"{key}: not in the pool")
    # every set of the pool has exactly the bonus levels the source has, once each, with the source's text
    set_names = sorted({e["set_name"] for e in src.set_items})
    for name in set_names:
        keys = [k for k, v in src.sets.items() if v["name"] == name]
        key = X.CURRENT_SET_KEY.get(name) or keys[0]
        levels = sorted(src.sets[key]["bonuses"], key=int)
        got = sorted(r["pieces"] for r in rows if r["pieces"] and r["item_or_set"] == name)
        if got != levels:
            found.append(f"set {name}: bonus levels {got}, source {levels}")
        raw = src.json_raw
        if key not in src.sets:
            found.append(f"set {name}: key {key} not in data.json")
        want = src.set_class.get(name, "") or "any"
        for row in rows:
            if row["pieces"] and row["item_or_set"] == name and row["class"] != want:
                found.append(f"set {name}: class {row['class']}, set_classes.csv {want}")
        for pieces in levels:
            row = by_key.get(f"{key}|{pieces}")
            if row is None:
                continue
            bonuses = src.sets[key]["bonuses"][pieces]
            texts = [b["format"].replace("%%", "%").replace("\r\n", " / ") for b in bonuses if "format" in b]
            for bonus in bonuses:
                if "format" in bonus:
                    if not in_raw(raw, bonus["format"]):
                        found.append(f"{key}|{pieces}: bonus text not in data.json")
                elif bonus["stat"] not in raw:
                    found.append(f"{key}|{pieces}: stat {bonus['stat']} not in data.json")
            if len(texts) == len(bonuses):
                # all entries are text: the row is exactly their join, nothing added and nothing missing
                if row["power_text"] != " | ".join(texts):
                    found.append(f"{key}|{pieces}: row text is not data.json's bonus text")
            else:
                for text in texts:
                    if text not in row["power_text"]:
                        found.append(f"{key}|{pieces}: bonus text not in the row")
            # the older file's text must not stand where it differs from the current one
            old = src.old_sets.get(key, {}).get("bonuses", {}).get(pieces)
            if old is not None:
                old_texts = [b["format"].replace("%%", "%").replace("\r\n", " / ") for b in old if "format" in b]
                if (old_texts and len(old_texts) == len(old) and old_texts != texts
                        and row["power_text"] == " | ".join(old_texts)):
                    found.append(f"{key}|{pieces}: the row carries data_itemsets.js's older text")
            has_follower = any(b.get("follower") for b in bonuses)
            if has_follower != ("follower" in row["source_flags"]):
                found.append(f"{key}|{pieces}: follower flag differs from data.json")
    stray = [k for k, r in by_key.items() if r["pieces"] and r["item_or_set"] not in set_names]
    if stray:
        found.append(f"set rows for sets outside the pool: {stray[:3]}")
    return found


class Catalogue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = Source()
        cls.rows = X.facts()

    def test_counts_are_the_briefs(self):
        self.assertEqual(len(self.src.legendary), 500)
        self.assertEqual(len(self.src.set_items), 283)
        self.assertEqual(len({e["set_name"] for e in self.src.set_items}), 57)
        self.assertEqual(len(self.rows), 500 + 139)

    def test_extracted_rows_match_the_source(self):
        self.assertEqual(problems(self.rows, self.src), [])

    def test_mutants_are_refused(self):
        def mutate(change):
            rows = copy.deepcopy(self.rows)
            change(rows)
            return problems(rows, self.src)

        item = next(i for i, r in enumerate(self.rows) if r["power_source"] == "custom" and not r["pieces"])
        bonus = next(i for i, r in enumerate(self.rows) if r["pieces"] == "4")

        self.assertTrue(mutate(lambda rows: rows.pop(item)), "a dropped item")
        self.assertTrue(mutate(lambda rows: rows.append(dict(rows[item]))), "a doubled item")
        self.assertTrue(mutate(lambda rows: rows[item].update(power_text=rows[item]["power_text"] + "x")), "edited text")
        self.assertTrue(mutate(lambda rows: rows[item].update(**{"class": "monk" if rows[item]["class"] != "monk" else "wizard"})), "wrong class")
        self.assertTrue(mutate(lambda rows: rows.pop(bonus)), "a lost bonus level")
        self.assertTrue(mutate(lambda rows: rows[bonus].update(power_text="x")), "an edited bonus")
        self.assertTrue(mutate(lambda rows: rows[bonus].update(**{"class": "any" if rows[bonus]["class"] != "any" else "monk"})), "a set with a wrong class")
        self.assertTrue(mutate(lambda rows: rows.append({**rows[item], "d3_id": "Invented_001"})), "an item not in the pool")

        # the set rule: data.json's text stands, data_itemsets.js's older text is refused where the two differ
        old = self.src.old_sets["raekor"]["bonuses"]["6"][0]["format"].replace("%%", "%")
        raekor6 = next(i for i, r in enumerate(self.rows) if r["d3_id"] == "raekor" and r["pieces"] == "6")
        self.assertNotEqual(old, self.rows[raekor6]["power_text"])
        found = mutate(lambda rows: rows[raekor6].update(power_text=old))
        self.assertTrue(any("older text" in f for f in found), found)
        self.assertTrue(mutate(lambda rows: rows[raekor6].update(power_text=rows[raekor6]["power_text"] + " Extra.")), "extra text in a set row")
        flagged = next(i for i, r in enumerate(self.rows) if r["d3_id"] == "cain_v2" and r["pieces"] == "3")
        self.assertTrue(mutate(lambda rows: rows[flagged].update(source_flags="")), "a lost follower mark")
        fixed = next(i for i, r in enumerate(self.rows) if r["d3_id"] == "P2_Unique_BarbBelt_001")
        self.assertTrue(mutate(lambda rows: rows[fixed].update(fixed_stats="skill_barbarian_avalanche [150-200]")), "a raw stat key")
        self.assertTrue(mutate(lambda rows: rows[fixed].update(fixed_stats="Avalanche damage +[100-200]%")), "a wrong stat value")

    def test_the_older_file_differs_in_many_rows(self):
        # the rule matters: data_itemsets.js and data.json disagree, so a test against the wrong one would show
        src = self.src
        rendered = lambda b: [(x["format"].replace("%%", "%").replace("\r\n", " / ") if "format" in x else f"{x['stat']}={x['value']}") for x in b]  # noqa: E731
        differ = [(k, p) for k, v in src.old_sets.items() for p, b in v["bonuses"].items()
                  if rendered(b) != rendered(src.sets[k]["bonuses"].get(p, []))]
        self.assertGreaterEqual(len(differ), 50)
        by_row = {(r["d3_id"], r["pieces"]): r for r in self.rows}
        for k, p in differ:
            old = src.old_sets[k]["bonuses"][p]
            if (k, p) in by_row and all("format" in x for x in old):
                self.assertNotEqual(by_row[(k, p)]["power_text"], " | ".join(rendered(old)), f"{k}|{p}")
        print(f"\n[{len(differ)} bonus rows differ between data_itemsets.js and data.json; {sum(1 for k, p in differ if (k, p) in by_row)} are catalogue rows]", end="")

    def test_every_legacy_twin_is_left_out(self):
        # a name that data.json lists twice resolves to the current key, and the catalogue holds one set per name
        names = [r["item_or_set"] for r in self.rows if r["pieces"] == "2"]
        self.assertEqual(len(names), len(set(names)))
        for name, key in X.CURRENT_SET_KEY.items():
            twins = [k for k, v in self.src.sets.items() if v["name"] == name]
            self.assertIn(key, twins)
            self.assertGreater(len(twins), 1)
            self.assertTrue(any(r["d3_id"] == key for r in self.rows))
            self.assertFalse(any(r["d3_id"] in twins and r["d3_id"] != key for r in self.rows))


class Judgement(unittest.TestCase):
    """The judgement sheet: whole, valid, and with sources where it claims them. Skipped until the sheet exists."""

    @classmethod
    def setUpClass(cls):
        if not X.JUDGEMENT.exists():
            raise unittest.SkipTest("legendary-judgement.csv not written yet")
        cls.judged = X.read_judgement()
        cls.rows = X.facts()

    def test_every_row_judged_once_and_no_extra(self):
        self.assertEqual(set(self.judged), {r["key"] for r in self.rows})

    def test_kinds_and_sources(self):
        for key, j in self.judged.items():
            self.assertIn(j["kind"], KINDS, key)
            if j["build"]:
                urls = [u.strip() for u in j["build_source"].split(";")]
                self.assertEqual(len(urls), len(j["build"].split(";")), f"{key}: one URL per build")
                for url in urls:
                    self.assertRegex(url, URL, f"{key}: a build needs a maxroll or Icy Veins URL")
            if j["build_source"]:
                self.assertTrue(j["build"], f"{key}: build_source without a build")
            for ref in re.findall(r"mod-diablocraft/\S+", j["hooks"]):
                self.assertRegex(ref.rstrip(";,)"), HOOK_REF, f"{key}: hook reference without file:line")
                path = X.ROOT / ref.rstrip(";,)").rsplit(":", 1)[0]
                self.assertTrue(path.exists(), f"{key}: {path} does not exist")

    def test_damage_buckets(self):
        # szvt: a damage row says which D3 bucket its bonus sits in, and where that comes from; other rows stay blank
        self.assertEqual(problems_in_buckets(self.judged), [])
        mutants = {"a bucket off the list": {"damage_bucket": "multiplicative"},
                   "a pool without a name": {"damage_bucket": "additive:"},
                   "a bucket without a source": {"bucket_source": ""}}
        key = next(k for k, j in self.judged.items() if j["damage_bucket"] == "multiplier")
        for name, change in mutants.items():
            self.assertTrue(problems_in_buckets({key: {**self.judged[key], **change}}), name)
        self.assertTrue(problems_in_buckets({key: {**self.judged[key], "damage_bucket": ""}}), "a source on a blank row")

    def test_hooks_plan_the_right_bucket(self):
        # mx25: the plan of a power names a term of its own bucket (damage-buckets.md 6b)
        self.assertEqual(problems_in_hooks(self.judged), [])
        multiplier = next(k for k, j in self.judged.items() if j["damage_bucket"] == "multiplier")
        additive = next(k for k, j in self.judged.items() if j["damage_bucket"].startswith("additive:"))
        for term in ("Items::SkillDamageBonus", "GemPowers::TargetBonus", "DamageBonus, an additive % while a state holds"):
            changed = {**self.judged[multiplier], "hooks": self.judged[multiplier]["hooks"] + "; " + term}
            self.assertTrue(problems_in_hooks({multiplier: changed}), term)
        for term in ("hit.legendary", "GemPowers::TargetFactor", "Wizard::Standalone", "PetFactor"):
            changed = {**self.judged[additive], "hooks": self.judged[additive]["hooks"] + "; " + term}
            self.assertTrue(problems_in_hooks({additive: changed}), term)
        # both directions are about the bucket column: the same text on an unknown or blank row is not judged
        free = {"damage_bucket": "unknown", "hooks": "Items::SkillDamageBonus and hit.legendary"}
        self.assertEqual(problems_in_hooks({"x": free, "y": {**free, "damage_bucket": ""}}), [])

    def test_k0_has_no_power_and_k6_is_the_nine(self):
        self.assertEqual(problems_in_k0_k6(self.rows, self.judged), [])
        by = {r["key"]: r for r in self.rows}
        k6 = next(k for k, j in self.judged.items() if j["kind"] == "K6")
        k1 = next(k for k, j in self.judged.items() if j["kind"] == "K1")
        bare = next(k for k, j in self.judged.items() if by[k]["power_source"] == "none")
        custom = next(k for k, j in self.judged.items() if j["kind"] == "K1" and by[k]["power_source"] == "custom")
        mutants = {"a K6 row back in K0 as NO-FIT": (k6, {"kind": "K0", "notes": "NO-FIT: " + self.judged[k6]["notes"]}),
                   "a K6 row back in K0": (k6, {"kind": "K0"}),
                   "a tenth K6 row": (k1, {"kind": "K6", "notes": "K6 " + self.judged[k1]["notes"]}),
                   "a K6 row without its note": (k6, {"notes": "x"}),
                   "a row with no power out of K0": (bare, {"kind": "K1"}),
                   "a custom power in K0 with no reason": (custom, {"kind": "K0"}),
                   "a K0 row marked NO-FIT": (bare, {"notes": "NO-FIT: x"})}
        for name, (key, change) in mutants.items():
            self.assertTrue(problems_in_k0_k6([by[key]], {key: {**self.judged[key], **change}}), name)

    def test_the_item_fraction_rows_are_chances_and_sankis_is_ignore_pain(self):
        fractions = {r["item_or_set"]: r["item_number"] for r in read(X.ROOT / "docs/research/legendary-pow-data.csv")}
        self.assertEqual(problems_in_item_chances(self.judged, fractions), [])
        self.assertEqual({fractions[n] for n in ("Vigilance", "The Burning Axe of Sankis")}, {"0.05", "0.08"})
        sankis = self.judged[SANKIS]
        mutants = {"a wrong fraction": ("Unique_Polearm_001_x1", {"notes": self.judged["Unique_Polearm_001_x1"]["notes"].replace("chance 0.05 ", "chance 0.5 ")}),
                   "a chance without its source": ("Unique_Axe_1H_003_x1", {"notes": "chance 0.3 per hit"}),
                   "a row with no chance": ("Unique_Staff_007_x1", {"notes": "no chance in the source"}),
                   "Sankis back to a block": (SANKIS, {"needs": sankis["needs"] + "; a block chance"}),
                   "Sankis at a placeholder chance": (SANKIS, {"notes": "PLACEHOLDER FOR ALEX"}),
                   "Sankis in the wrong kind": (SANKIS, {"kind": "K4"})}
        for name, (key, change) in mutants.items():
            self.assertTrue(problems_in_item_chances({**self.judged, key: {**self.judged[key], **change}}, fractions), name)

    def test_committed_catalogue_is_current(self):
        want = X.catalogue(self.rows, self.judged)
        have = read(X.OUTPUT)
        self.assertEqual(have, [{k: str(v) for k, v in w.items()} for w in want], "rerun extract_legendary_catalogue.py")


if __name__ == "__main__":
    unittest.main()

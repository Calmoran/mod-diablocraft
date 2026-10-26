#!/usr/bin/env python3
"""Generate the class resource registry (diablocraft-resource-registry).

One row per class resource, from two sheets joined on (d3_class, resource_key):

  data/d3/class_resources.csv        what D3 says: the resource's name, whether
                                     it is the class's primary or second
                                     resource, pool, regen per second and
                                     whether it decays out of combat.
  data/tunables/class_resources.csv  what Torment chose: the WoW power slot the
                                     resource lives in, how many of that slot's
                                     units one point is (1 or 10), how its decay
                                     is carried, its display colour and whether
                                     a player enters the world with it full
                                     (starts_full; blank for a planned class),
                                     and the power token the client names it
                                     by (token: FURY, WRATH, ...; a resource
                                     that is the slot's own keeps the slot's
                                     stock token, as the Witch Doctor's MANA),
                                     and who pays its regeneration and decay
                                     (paid_by: module, the resource pulse a
                                     fine step at a time; core, the slot's
                                     own stock tick; blank for a planned class).

The registry is compiled into src/classes/dc_resource_data.h and read through
src/classes/dc_resources.h, the one helper every module read or write of a
class resource goes through. generate_spells.py imports registry() for each
class's record PowerType, cost scale and regeneration aura, so moving a
resource to another slot is a sheet edit and a regeneration, never an edit
across the combat code.

The same rows also render client-patch/addons/Torment/ResourceNames.lua, the
name list the Torment addon's resource-name module reads to put each class's
D3 name in place of the slot's WoW word (ruling 2C; the table's shape is
docs/contracts/resource-names.md), with the power token table the client
patch's PowerBarColor and name strings come from, and
mod-diablocraft/data/generated/class_power_tokens.h, the table the rebuilt
client's engine reads to report a class's own power token for a slot. The
three outputs and the server header come from one render of the rows, so they
cannot drift (docs/contracts/class-powers.md).

Cross-checks that fail the run: the primary row's slot against class_map.csv's
wow_power_type, each pool against the class's base-stats sheet at every level
(the second one by its <key>_max column), and the regen of every resource against
<class>_resource.csv's regen_per_second where that sheet exists. A value the registry cannot represent (a decay the slot's stock path
does not do, regeneration on a slot no stock path refills) is refused, not
approximated: that needs a decision and code, not a data row.

A class not yet in class_map.csv is PLANNED (diablocraft-resource-rollout-a
item 2): its rows are data only, checked like any other, and compiled into
nothing. When the class joins class_map.csv its rows go live, and a live row
that needs a mechanism no class has proven in game yet is refused with the
stock path to build (MECHANISMS below) instead of shipping untested.

Maximum Resource from Paragon is per resource, from paragon.csv's
resource_keys column (a resource no row names gains nothing), paid in whole
points: +0.5 per point is +1 per two points (decisions.md 2026-09-23).

Run from the repo root:

    python mod-diablocraft/scripts/generate/classes/generate_class_resources.py
"""

import csv
import re
import struct
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from class_names import sheet_stem
MODULE = Path(__file__).resolve().parents[3]
DATA = MODULE / "data/d3"
TUNABLES = MODULE / "data/tunables"
COMBAT_TUNABLES = MODULE / "data/tunables/combat.csv"
HEADER = MODULE / "src/classes/dc_resource_data.h"
UPDATES = MODULE / "data/sql/db-world/updates"
# ChrClasses.DisplayPower is the stock place a class's shown power lives: the
# core writes it into UNIT_FIELD_BYTES_0 at creation (Player.cpp:519-536) and
# puts it back on every form update (Player::InitDataForForm, Player.cpp:10777-
# 10779). A class whose primary sits in another slot gets a chrclasses_dbc
# overlay row (DBCStores.cpp:285 loads the table over the file) and the same
# row in the client's ChrClasses.dbc.
# world_0019 (Barbarian and Wizard) is applied and frozen; the Crusader's Paladin row (Energy) renders the whole
# overlay into a new number, and a class added later is a new number again: world_0064 is applied, so the Demon
# Hunter's Hunter row renders it into world_0070; world_0070 is applied, so the Witch Doctor's Mana row renders it into world_0076; world_0076 is applied, so the Shaman's Rage row renders it into world_0082.
DISPLAY_POWER_MIGRATION = "world_0082_class_display_power.sql"
# The client and the core draw a class name from ChrClasses.Name_Lang_enUS (item
# "Classes:" line, who list, guild, target frame, chat; GetClassInfo, UnitClass
# and the core's own messages). A live class takes its D3 name there:
# Warrior -> Barbarian, Mage -> Wizard (diablocraft-race-class-unlock).
# world_0027 is applied and frozen; the Crusader's name renders into a new number after the display-power one, whose
# DELETE of every live class's row it must follow; world_0065 is applied, so the Demon Hunter's is world_0071; world_0071 is applied, so the Witch Doctor's is world_0077; world_0077 is applied, so the Shaman's is world_0083.
CLASS_NAMES_MIGRATION = "world_0083_class_names.sql"
SERVER_DBC = MODULE.parent / "azerothcore-wotlk/build/server/data/dbc"
CLIENT_CHRCLASSES = MODULE.parent / "client-patch/dbc/ChrClasses.dbc"
F_DISPLAY_POWER = 2   # ChrClassesEntry powerType, field 2 (DBCStructure.h:652-656)
F_SPELL_CLASS_SET = 56   # ChrClassesEntry spellfamily, field 56 (DBCStructure.h:692)
NAMES_LUA = MODULE.parent / "client-patch/addons/Torment/ResourceNames.lua"
ENGINE_HEADER = MODULE / "data/generated/class_power_tokens.h"

# The pinned core's Powers enum (SharedDefines.h), by the name the sheet uses.
POWERS = {"Mana": 0, "Rage": 1, "Focus": 2, "Energy": 3, "Happiness": 4,
          "Rune": 5, "Runic Power": 6}
# Slots whose stock Player::Regenerate loses power out of combat (Rage 20 and
# Runic Power 30 stored units per 2 s); docs/design/systems/power.md section 2.
STOCK_DECAY = {"Rage", "Runic Power"}
# What a slot gains per second by itself for a player, before any aura:
# Energy's (regen field + 10) per second (Player::Regenerate, pinned core
# Player.cpp:1939-1948). Every other slot gains nothing by itself.
NATIVE_REGEN = {"Energy": 10.0}
# Slots the hidden regeneration aura (generate_spells.py RESOURCE_REGENERATION)
# drives: SPELL_AURA_MOD_POWER_REGEN reaches the player through
# Player::UpdateManaRegen, which only Mana has.
# A row the module pays (paid_by module) gets no such aura: the pulse pays the rate itself, and the aura's own
# terms (its per-five amount and its -100 percent that cancels Spirit) would be read by the pulse as a second source
# and as a multiplier of zero on the sheet's and the gear's regeneration.
AURA_REGEN = {"Mana"}
# Slots whose own timed gain can refill a resource at some rate: the aura's,
# and Energy's native one. A row the module pays (paid_by module) regenerates on
# any slot: the resource pulse pays its rate whatever the slot.
REGEN_SLOTS = AURA_REGEN | set(NATIVE_REGEN)
# Mechanisms a row can need that no live class has proven in game. A live row
# needing one is refused with this text: the stock path to build and test
# when the first class that uses it is added (item 3 of the rollout brief).
# None is waiting today. Runic Power with its decay off is not here: the Monk
# (diablocraft-1cuvw) is a class that is not a Death Knight, and the core
# regenerates and decays Runic Power only for a Death Knight (Player::RegenerateAll,
# pinned core Player.cpp:1844-1847), so its decay is off by construction and
# needs no aura. A Death Knight body (none is planned) would need
# SPELL_AURA_PREVENT_REGENERATE_POWER (294) with MiscValue power+1 on its
# regeneration passive (Player.cpp:1909). Energy at another rate than the
# native 10/s is built (energy_rate_percent below, and generate_spells.py
# ENERGY_RATE); the first class on it is the Crusader's Wrath, whose dev check
# proves it.
MECHANISMS = {}
# Energy's native gain per second is the 10 the core's own UpdateEnergyRegen
# starts from (pinned core StatSystem.cpp:984-992); an Energy class at another
# rate carries one hidden passive that multiplies it.
# The client's token for each slot: what UnitPowerType returns second and the
# key of PowerBarColor (FrameXML UnitFrame.lua:2-8).
POWER_TOKENS = {"Mana": "MANA", "Rage": "RAGE", "Focus": "FOCUS", "Energy": "ENERGY",
                "Happiness": "HAPPINESS", "Rune": "RUNES", "Runic Power": "RUNIC_POWER"}
# A power token: what the client reports for a class's slot once the engine reads class_power_tokens.h.
TOKEN = re.compile(r"[A-Z][A-Z_]*[A-Z]")
SCALES = {1, 10}
ROLES = ("primary", "second")
DECAYS = ("stock", "none", "timed")
# A timed decay (the Shaman's Maelstrom) is a rate and a wait, two rows of data/tunables/combat.csv named for the
# resource: <resource_key>_decay_per_second and <resource_key>_decay_wait_seconds.
TIMED_TUNABLES = ("{key}_decay_per_second", "{key}_decay_wait_seconds")
# Who moves the resource between casts. module: the resource pulse (src/stats/dc_resource_pulse.cpp), every
# combat.resource_pulse_ms, with the core's tick for the slot masked (generate_spells.py REGENERATION_MASK). core: the
# slot's own stock path (Energy's native gain, the Mana aura). Rage and Runic Power are always the module's: the core
# moves them only every 2 seconds. Focus too: the core never moves a player's Focus (Player::RegenerateAll calls no
# Regenerate for it, and Player::Regenerate adds nothing to it, pinned core Player.cpp:1961).
PAYERS = ("module", "core")
MODULE_ONLY_SLOTS = {"Rage", "Runic Power", "Focus"}
# The base-stats column that holds the class's resource maximum per level.
POOL_COLUMNS = ("resource_max", "fury_max")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def number(sheet, row, column):
    try:
        return float(row[column])
    except ValueError:
        raise SystemExit(f"{sheet}: {row['d3_class']} {row['resource_key']} {column} "
                         f"{row[column]!r} is not a number")


def paragon_per_point():
    """resource_key -> Maximum Resource per Paragon point, from paragon.csv.

    Each Maximum Resource row lists the resources it covers in resource_keys;
    its value is the D3 sheet's effect_per_point ("+4", "+0.5"), and where the
    row is also the realm's allocatable stat its per_point must agree. A key
    may appear once. The value is the D3 sheet's, a fraction included; paying
    it in whole points is the module's (dc_resources.h ParagonMaximum)."""
    out = {}
    for row in read(DATA / "paragon.csv"):
        keys = (row.get("resource_keys") or "").strip()
        if not keys:
            continue
        effect = row["effect_per_point"].strip()
        match = re.fullmatch(r"\+((?:0|[1-9][0-9]*)(?:\.[0-9]+)?)", effect)
        if not match:
            raise SystemExit(f"paragon.csv: {row['stat']!r} effect_per_point {effect!r} is not +<points>")
        per_point = Decimal(match.group(1))
        if per_point <= 0 or (per_point * 2) != int(per_point * 2):
            raise SystemExit(f"paragon.csv: {row['stat']!r} effect_per_point {effect} must be a positive "
                             "whole or half point: a half is paid as one point per two")
        if row["per_point"].strip() and Decimal(row["per_point"].strip()) != per_point:
            raise SystemExit(f"paragon.csv: {row['stat']!r} per_point {row['per_point']} disagrees with "
                             f"effect_per_point {effect}")
        for key in keys.split(";"):
            if key in out:
                raise SystemExit(f"paragon.csv: resource {key!r} is in two Maximum Resource rows")
            out[key] = float(per_point)
    if not out:
        raise SystemExit("paragon.csv: no row names resource_keys; Maximum Resource has no source")
    return out


def energy_rate_percent(regen, native):
    """The SPELL_AURA_MOD_POWER_REGEN_PERCENT amount that takes an Energy
    resource from the slot's native gain to the D3 rate, or None when they are
    the same. Player::UpdateEnergyRegen multiplies the native 10/s by
    (100 + amount) / 100 (pinned core StatSystem.cpp:984-992), so Wrath's 2.5/s
    is -75 and Hatred's 5/s is -50. A rate that is not a whole percent of the
    native one cannot be written in the record and is refused."""
    if regen == native:
        return None
    percent = (regen / native - 1) * 100
    if percent != int(percent):
        raise SystemExit("class_resources.csv: Energy regenerating at %g/s is %g%% of the native %g/s, not a "
                         "whole percent" % (regen, percent + 100, native))
    return int(percent)


def rows(include_planned=False):
    """Every class resource, validated, live classes in class_map.csv order and
    then (include_planned) the planned ones in sheet order.

    Each entry: live, class_id (None when planned), class_token, d3_class, key,
    d3_name, role, power (slot name), power_id, scale, pool, regen, aura_regen
    (what the regeneration aura adds beyond the slot's native gain),
    energy_rate_pct (the percent the Energy-rate passive adds to the native
    gain, None for a resource at the native rate or off Energy), decay, colour, token (the power token), starts_full, paragon (Maximum Resource per Paragon point), needs (mechanisms).
    """
    d3_rows = read(DATA / "class_resources.csv")
    torment_rows = read(TUNABLES / "class_resources.csv")
    class_map = {row["d3_class"].strip(): row for row in read(DATA / "class_map.csv")}
    per_point = paragon_per_point()

    def keyed(rows, sheet):
        out = {}
        for row in rows:
            key = (row["d3_class"].strip(), row["resource_key"].strip())
            if key in out:
                raise SystemExit(f"{sheet}: {key} appears twice")
            out[key] = row
        return out

    d3 = keyed(d3_rows, "data/d3/class_resources.csv")
    torment = keyed(torment_rows, "data/tunables/class_resources.csv")
    if set(d3) != set(torment):
        raise SystemExit("class_resources.csv: the D3 and Torment sheets name different resources: "
                         f"{sorted(set(d3) ^ set(torment))}")
    unknown = set(per_point) - {key for _, key in d3}
    if unknown:
        raise SystemExit(f"paragon.csv: resource_keys {sorted(unknown)} name no class_resources.csv row")

    entries = []
    for key, row in d3.items():
        d3_class, resource_key = key
        choice = torment[key]
        live = d3_class in class_map
        if not re.fullmatch(r"[A-Z][A-Za-z]*( [A-Z][A-Za-z]*)*", d3_class):
            raise SystemExit(f"class_resources.csv: d3_class {d3_class!r} is not a class name")
        if not re.fullmatch(r"[a-z][a-z_]*", resource_key):
            raise SystemExit(f"class_resources.csv: resource_key {resource_key!r} is not lower_snake_case")
        role = row["role"].strip()
        if role not in ROLES:
            raise SystemExit(f"class_resources.csv: {key} role {role!r} is not one of {ROLES}")
        power = choice["wow_power"].strip()
        if power not in POWERS:
            raise SystemExit(f"class_resources.csv: {key} wow_power {power!r} is not a WoW power slot")
        scale = number("tunables/class_resources.csv", choice, "storage_scale")
        if scale not in SCALES:
            raise SystemExit(f"class_resources.csv: {key} storage_scale {scale:g} is not 1 or 10")
        pool = number("d3/class_resources.csv", row, "pool")
        regen = number("d3/class_resources.csv", row, "regen_per_second")
        decays = row["decays_out_of_combat"].strip()
        if pool <= 0 or regen < 0 or decays not in ("0", "1"):
            raise SystemExit(f"class_resources.csv: {key} needs pool > 0, regen >= 0 and "
                             "decays_out_of_combat 0 or 1")
        decay = choice["decay"].strip()
        if decay not in DECAYS:
            raise SystemExit(f"class_resources.csv: {key} decay {decay!r} is not one of {DECAYS}")
        needs = []
        if decay == "stock" and (decays != "1" or power not in STOCK_DECAY):
            raise SystemExit(f"class_resources.csv: {key} decay 'stock' needs a resource D3 decays "
                             f"and a slot with stock decay ({sorted(STOCK_DECAY)}), not {power}")
        if decay == "timed":
            if decays != "1" or power not in STOCK_DECAY:
                raise SystemExit(f"class_resources.csv: {key} decay 'timed' needs a resource D3 decays and a slot "
                                 f"whose core tick the mask keeps off ({sorted(STOCK_DECAY)}), not {power}")
            names = {row["name"] for row in read(COMBAT_TUNABLES)}
            for template in TIMED_TUNABLES:
                if template.format(key=resource_key) not in names:
                    raise SystemExit(f"class_resources.csv: {key} decay 'timed' needs the combat.csv row "
                                     f"{template.format(key=resource_key)}")
        if decay == "none":
            if decays != "0":
                raise SystemExit(f"class_resources.csv: {key} decay 'none' needs a resource D3 does "
                                 "not decay")
        native = NATIVE_REGEN.get(power, 0.0)
        rate_percent = energy_rate_percent(regen, native) if power in NATIVE_REGEN else None
        starts_full = choice["starts_full"].strip()
        if starts_full not in ("0", "1", ""):
            raise SystemExit(f"class_resources.csv: {key} starts_full {starts_full!r} is not 0 or 1 (blank: planned class, not decided)")
        colour = choice["display_colour"].strip()
        if not re.fullmatch(r"#[0-9A-F]{6}", colour):
            raise SystemExit(f"class_resources.csv: {key} display_colour {colour!r} is not #RRGGBB")
        paid_by = choice["paid_by"].strip()
        if paid_by not in PAYERS + ("",):
            raise SystemExit(f"class_resources.csv: {key} paid_by {paid_by!r} is not one of {PAYERS} (blank: planned class)")
        if paid_by == "core" and power in MODULE_ONLY_SLOTS:
            raise SystemExit(f"class_resources.csv: {key} paid_by core on {power}, which the core moves only every "
                             "2 seconds or never; it is the module's")
        if regen > 0 and paid_by != "module" and power not in REGEN_SLOTS:
            raise SystemExit(f"class_resources.csv: {key} regenerates, and no stock path refills "
                             f"{power} for a player (the aura drives {sorted(AURA_REGEN)}, "
                             f"native regeneration is {sorted(NATIVE_REGEN)}); the module's pulse would (paid_by module)")
        token = choice["token"].strip()
        if not TOKEN.fullmatch(token):
            raise SystemExit(f"class_resources.csv: {key} token {token!r} is not UPPER_SNAKE_CASE")
        if token in POWER_TOKENS.values() and token != POWER_TOKENS[power]:
            raise SystemExit(f"class_resources.csv: {key} token {token} is another slot's stock token "
                             f"({power} is {POWER_TOKENS[power]})")
        if not choice["notes"].strip() or not row["source"].strip():
            raise SystemExit(f"class_resources.csv: {key} needs its source and notes")
        if live:
            for need in needs:
                raise SystemExit(f"class_resources.csv: {key} is live (class_map.csv) and "
                                 + MECHANISMS[need].format(power=power, regen=regen))
        if live and paid_by == "":
            raise SystemExit(f"class_resources.csv: {key} is live (class_map.csv) and needs paid_by module or core")
        if live and starts_full == "":
            raise SystemExit(f"class_resources.csv: {key} is live (class_map.csv) and needs starts_full 0 or 1")
        entries.append({
            "live": live,
            "class_id": int(class_map[d3_class]["class_id"]) if live else None,
            "class_token": class_token(class_map[d3_class]["wow_class"]) if live else None,
            "wow_class_id": int(class_map[d3_class]["wow_class_id"]) if live else None,
            "d3_class": d3_class, "key": resource_key, "d3_name": row["d3_name"].strip(),
            "role": role, "power": power, "power_id": POWERS[power], "scale": int(scale),
            "pool": pool, "regen": regen, "aura_regen": regen - native if power in AURA_REGEN and paid_by != "module" else 0.0,
            "energy_rate_pct": rate_percent,
            "decay": decay, "colour": colour, "token": token, "paid_by": paid_by, "starts_full": starts_full == "1",
            "paragon": per_point.get(resource_key, 0.0), "needs": needs})

    order = [row["d3_class"].strip() for row in read(DATA / "class_map.csv")]
    planned = list(dict.fromkeys(e["d3_class"] for e in entries if not e["live"]))
    entries.sort(key=lambda e: (order.index(e["d3_class"]) if e["live"]
                                else len(order) + planned.index(e["d3_class"]),
                                ROLES.index(e["role"])))

    by_class = {}
    for entry in entries:
        by_class.setdefault(entry["d3_class"], []).append(entry)
    token_of = {}
    for entry in entries:
        if token_of.setdefault(entry["token"], entry["key"]) != entry["key"]:
            raise SystemExit(f"class_resources.csv: token {entry['token']} names both {token_of[entry['token']]} "
                             f"and {entry['key']}; one token is one power")
    for d3_class, class_rows in by_class.items():
        roles = [e["role"] for e in class_rows]
        if roles.count("primary") != 1 or roles.count("second") > 1:
            raise SystemExit(f"class_resources.csv: {d3_class} needs one primary and at most one "
                             "second resource")
        if len({e["power"] for e in class_rows}) != len(class_rows):
            raise SystemExit(f"class_resources.csv: {d3_class}'s two resources share a slot")
        primary = class_rows[0]
        if not primary["live"]:
            continue
        mapped = class_map[d3_class]["wow_power_type"].strip()
        if primary["power"] != mapped:
            raise SystemExit(f"class_resources.csv: {d3_class}'s primary is in {primary['power']} "
                             f"and class_map.csv wow_power_type says {mapped}")
        base = DATA / f"{sheet_stem(d3_class)}_base_stats.csv"
        if base.is_file():
            levels = read(base)
            column = next((c for c in POOL_COLUMNS if c in levels[0]), None)
            if column is None:
                raise SystemExit(f"{base.name}: no resource maximum column")
            wrong = [r["level"] for r in levels if float(r[column]) != primary["pool"]]
            if wrong:
                raise SystemExit(f"class_resources.csv: {d3_class} pool {primary['pool']:g} disagrees "
                                 f"with {base.name} {column} at levels {wrong}")
            for second in class_rows[1:]:
                column = f"{second['key']}_max"
                wrong = [r["level"] for r in levels if column in r and float(r[column]) != second["pool"]]
                if wrong:
                    raise SystemExit(f"class_resources.csv: {d3_class} {second['key']} pool {second['pool']:g} "
                                     f"disagrees with {base.name} {column} at levels {wrong}")
        sheet = DATA / f"{sheet_stem(d3_class)}_resource.csv"
        if sheet.is_file():
            stated = [float(r["regen_per_second"]) for r in read(sheet)
                      if (r.get("regen_per_second") or "").strip()]
            wanted = [e["regen"] for e in class_rows]
            if stated and stated != wanted:
                raise SystemExit(f"class_resources.csv: {d3_class} regen {wanted} disagrees "
                                 f"with {sheet.name} regen_per_second {stated}")
    for d3_class, row in class_map.items():
        if d3_class not in by_class:
            raise SystemExit(f"class_map.csv: {d3_class} has no row in class_resources.csv")
    return entries if include_planned else [e for e in entries if e["live"]]


def registry():
    """The live class resources: every row of a class in class_map.csv."""
    return rows()


def class_token(wow_class):
    """The client's class file token (UnitClass's second return) for a
    class_map.csv wow_class: the English name in capitals without spaces
    ("Death Knight" is DEATHKNIGHT)."""
    token = re.sub(r"\s+", "", wow_class.strip()).upper()
    if not re.fullmatch(r"[A-Z]+", token):
        raise SystemExit(f"class_map.csv: wow_class {wow_class!r} gives no class token")
    return token


def lua_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_names(entries):
    """The Torment addon's name list: class token -> power token -> the D3
    resource on that slot. Names and colours only; no number the client draws
    is here, and the addon never computes one (docs/contracts/resource-names.md)."""
    lines = [
        "-- Generated by mod-diablocraft/scripts/generate/classes/generate_class_resources.py from",
        "-- data/d3/class_resources.csv, data/tunables/class_resources.csv and",
        "-- data/d3/class_map.csv; never hand-edit. Shape and use:",
        "-- docs/contracts/resource-names.md.",
        "Diablocraft = Diablocraft or {}",
        "Diablocraft.ResourceNames = {",
    ]
    by_token = {}
    for e in entries:
        by_token.setdefault(e["class_token"], []).append(e)
    for token, rows in by_token.items():
        lines.append(f"    {token} = {{")
        for e in rows:
            lines.append(
                f"        {POWER_TOKENS[e['power']]} = {{ name = {lua_string(e['d3_name'])}, "
                f"colour = {lua_string(e['colour'][1:])}, power = {e['power_id']}, "
                f"role = {lua_string(e['role'])}, key = {lua_string(e['key'])}, "
                f"class = {lua_string(e['d3_class'])}, token = {lua_string(e['token'])} }},")
        lines.append("    },")
    lines += ["}",
              "-- By power token: the name and colour a bar, a cost line or PowerBarColor shows for it.",
              "Diablocraft.PowerTokens = {"]
    for e in entries:
        r, g, b = (int(e["colour"][i:i + 2], 16) / 255 for i in (1, 3, 5))
        lines.append(f"    {e['token']} = {{ name = {lua_string(e['d3_name'])}, colour = {lua_string(e['colour'][1:])}, "
                     f"r = {r:.3f}, g = {g:.3f}, b = {b:.3f}, power = {e['power_id']} }},")
    lines += ["}", ""]
    return "\n".join(lines)


def render_engine(entries):
    """The rebuilt client's table: for a player of a class with a row here, the slot reports the row's token in place
    of the stock one. Keyed by the WoW class id (ChrClasses) and the Powers slot; every class and slot absent keeps
    the stock token."""
    lines = [
        "// Generated by mod-diablocraft/scripts/generate/classes/generate_class_resources.py from",
        "// data/d3/class_resources.csv, data/tunables/class_resources.csv and data/d3/class_map.csv;",
        "// never hand-edit. Shape and use: docs/contracts/class-powers.md.",
        "#pragma once",
        "",
        "namespace TormentPowers",
        "{",
        "struct ClassPowerToken",
        "{",
        "    unsigned char classId; // ChrClasses id, the unit's class",
        "    unsigned char power;   // the Powers slot, 0 Mana .. 6 Runic Power",
        "    const char* token;     // what the slot reports in place of the stock token",
        "};",
        "",
        "static const ClassPowerToken ClassPowerTokens[] = {",
    ]
    for e in entries:
        lines.append(f"    {{{e['wow_class_id']}, {e['power_id']}, {cpp_string(e['token'])}}}, // {e['d3_class']} {e['d3_name']}")
    lines += [
        "};",
        "",
        "// The class's own token for the slot, or nullptr: the stock token stays.",
        "inline const char* TokenFor(unsigned classId, unsigned power)",
        "{",
        "    for (const ClassPowerToken& row : ClassPowerTokens)",
        "        if (row.classId == classId && row.power == power)",
        "            return row.token;",
        "    return nullptr;",
        "}",
        "",
        "// Slot units per point of the row's power (storage_scale): a class power's value shows as the slot divided by",
        "// this, in place of the stock divide (Rage and Runic Power a tenth), so a row stored one unit a point shows its",
        "// true number and a row still at ten a point shows as before. Two classes may share a slot at different scales.",
        "struct ClassPowerScale",
        "{",
        "    unsigned char classId;",
        "    unsigned char power;",
        "    unsigned char unitsPerPoint;",
        "};",
        "",
        "static const ClassPowerScale ClassPowerScales[] = {",
    ]
    for e in entries:
        lines.append(f"    {{{e['wow_class_id']}, {e['power_id']}, {int(e['scale'])}}}, // {e['d3_class']} {e['d3_name']}")
    lines += [
        "};",
        "",
        "// The row's units per point, or 0: no row, the stock divide stays.",
        "inline unsigned UnitsPerPointFor(unsigned classId, unsigned power)",
        "{",
        "    for (const ClassPowerScale& row : ClassPowerScales)",
        "        if (row.classId == classId && row.power == power)",
        "            return row.unitsPerPoint;",
        "    return 0;",
        "}",
        "}",
        ""]
    return "\n".join(lines)


def cpp_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(entries):
    lines = [
        "// Generated by generate_class_resources.py from data/d3/class_resources.csv and",
        "// data/tunables/class_resources.csv; never hand-edit. Read it through",
        "// dc_resources.h.",
        "#pragma once",
        "#include <cstdint>",
        "namespace DC::Resources::Data",
        "{",
        "enum class Role : uint8_t { Primary, Second };",
        "// Stock: the slot's own core out-of-combat loss. None: no decay. Timed: a rate after a wait out of combat, the",
        "// combat.csv rows <key>_decay_per_second and <key>_decay_wait_seconds.",
        "enum class Decay : uint8_t { Stock, None, Timed };",
        "struct Row",
        "{",
        "    uint32_t classId;     // class_map.csv class_id",
        "    char const* d3Class;",
        "    char const* key;      // resource_key",
        "    char const* d3Name;",
        "    Role role;",
        "    uint8_t power;        // the WoW Powers slot",
        "    char const* wowPower; // the slot's WoW name",
        "    double scale;         // slot units per resource point",
        "    double pool;          // D3 base maximum, points",
        "    double regenPerSecond;",
        "    Decay decay;",
        "    uint32_t colour;      // 0xRRGGBB",
        "    // Maximum Resource per Paragon point (paragon.csv resource_keys), a",
        "    // whole or half point; dc_resources.h ParagonMaximum pays it whole.",
        "    double paragonPerPoint;",
        "    // The player enters the world with the resource at its maximum (login, and so a new character's first entry):",
        "    // data/tunables/class_resources.csv starts_full, read by dc_stats.cpp Login.",
        "    bool startsFull;",
        "    char const* token;    // the power token the client names it by (FURY, WRATH, ...)",
        "    // The resource pulse pays its regeneration and decay (paid_by module), the core's tick for the slot masked;",
        "    // false: the slot's own stock path does.",
        "    bool modulePaid;",
        "};",
        "inline constexpr Row Rows[] = {",
    ]
    for e in entries:
        lines.append("    {%d, %s, %s, %s, Role::%s, %d, %s, %s, %s, %s, Decay::%s, 0x%s, %s, %s, %s, %s}," % (
            e["class_id"], cpp_string(e["d3_class"]), cpp_string(e["key"]), cpp_string(e["d3_name"]),
            e["role"].capitalize(), e["power_id"], cpp_string(e["power"]), repr(float(e["scale"])),
            repr(e["pool"]), repr(e["regen"]), e["decay"].capitalize(), e["colour"][1:],
            repr(e["paragon"]), "true" if e["starts_full"] else "false", cpp_string(e["token"]),
            "true" if e["paid_by"] == "module" else "false"))
    lines += [
        "};",
        "constexpr bool SameText(char const* a, char const* b)",
        "{",
        "    while (*a && *a == *b)",
        "    {",
        "        ++a;",
        "        ++b;",
        "    }",
        "    return *a == *b;",
        "}",
        "// By class and resource key; nullptr when the registry has no such row.",
        "constexpr Row const* Find(char const* d3Class, char const* key)",
        "{",
        "    for (Row const& row : Rows)",
        "        if (SameText(row.d3Class, d3Class) && SameText(row.key, key))",
        "            return &row;",
        "    return nullptr;",
        "}",
        "// A record's cost is in its PowerType slot's units at its own class's scale: two classes may share a slot",
        "// at different scales (the Monk's Spirit ten a point, the Necromancer's Essence one, both on Runic Power).",
        "// A class with no resource on the slot (or no class, 0) counts one unit per point.",
        "constexpr double ScaleOf(uint32_t classId, uint32_t power)",
        "{",
        "    for (Row const& row : Rows)",
        "        if (row.classId == classId && row.power == power)",
        "            return row.scale;",
        "    return 1.0;",
        "}",
        "}",
        ""]
    return "\n".join(lines)


def created_class_ids():
    """WoW class ids of the classes generate_class_creation.py creates (class_creation.csv). The stock ChrClasses
    file has no row for them: that generator writes the whole row, name and DisplayPower included. A row whose parent is
    its own id is a class on a stock slot (the Crusader on the Paladin's): its stock row is overlaid here like any other."""
    path = DATA / "class_creation.csv"
    if not path.is_file():
        return set()
    ids = {row["d3_class"].strip(): int(row["wow_class_id"]) for row in read(DATA / "class_map.csv")}
    return {ids[row["d3_class"].strip()] for row in read(path)
            if int(row["parent_wow_class_id"]) != ids[row["d3_class"].strip()]}


def stock_slot_class_ids():
    """WoW class ids of the classes on a stock slot that class_creation.csv lists (parent = its own id: the Crusader)."""
    path = DATA / "class_creation.csv"
    if not path.is_file():
        return set()
    ids = {row["d3_class"].strip(): int(row["wow_class_id"]) for row in read(DATA / "class_map.csv")}
    return {ids[row["d3_class"].strip()] for row in read(path)
            if int(row["parent_wow_class_id"]) == ids[row["d3_class"].strip()]}


def display_power(entries, server_dbc=None, client_dbc=None):
    """(sql, client ChrClasses.dbc bytes): every live class's DisplayPower set
    to its primary resource's slot, overlaid only where the stock row differs."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from dbc_store import Store, schema, sql_value
    root = MODULE.parent
    columns = schema(root, "chrclasses_dbc")
    server = Store(Path(server_dbc or SERVER_DBC / "ChrClasses.dbc").read_bytes(), columns)
    client_path = Path(client_dbc or CLIENT_CHRCLASSES)
    client = Store((client_path if client_path.exists() else SERVER_DBC / "ChrClasses.dbc").read_bytes(), columns)
    if columns[F_DISPLAY_POWER][0] != "DisplayPower":
        raise SystemExit("chrclasses_dbc: field 2 is not DisplayPower")
    wow_ids = {row["d3_class"].strip(): int(row["wow_class_id"]) for row in read(DATA / "class_map.csv")}
    if columns[F_SPELL_CLASS_SET][0] != "SpellClassSet":
        raise SystemExit("chrclasses_dbc: field %d is not SpellClassSet" % F_SPELL_CLASS_SET)
    overlays = []
    created = created_class_ids()
    stock_slots = stock_slot_class_ids()
    for e in entries:
        if e["role"] != "primary":
            continue
        wow_id = wow_ids[e["d3_class"]]
        if wow_id in created:
            continue
        if wow_id not in server.rows:
            raise SystemExit(f"ChrClasses.dbc has no class {wow_id} for {e['d3_class']}")
        stock = server.decode(wow_id)
        blank = dict(DisplayPower=0, Name_Lang_enUS="")   # the name is class_names' to set
        # A class on a stock slot (class_creation.csv) has its client SpellClassSet set by generate_class_creation.py
        # once its records exist; the client keeps it and the server row stays stock.
        if wow_id in stock_slots:
            blank["SpellClassSet"] = 0
        if dict(client.decode(wow_id), **blank) != dict(stock, **blank):
            raise SystemExit(f"ChrClasses.dbc: the client row {wow_id} differs from the server's stock "
                             "row outside DisplayPower")
        record = bytearray(server.rows[wow_id])
        struct.pack_into("<I", record, F_DISPLAY_POWER * 4, e["power_id"])
        if wow_id in stock_slots:
            struct.pack_into("<I", record, F_SPELL_CLASS_SET * 4, client.decode(wow_id)["SpellClassSet"])
        client.rows[wow_id] = bytes(record)
        if stock["DisplayPower"] != e["power_id"]:
            overlays.append(dict(stock, DisplayPower=e["power_id"]))
    names = [c[0] for c in columns]
    sql = ["-- Generated by generate_class_resources.py from class_map.csv and the class resource",
           "-- registry: ChrClasses.DisplayPower = the class's primary resource slot, overlaid only",
           "-- where the stock row differs (decisions.md 2026-09-23 Class resource model, Q1=1A).",
           "SET NAMES utf8mb4;",
           "DELETE FROM `chrclasses_dbc` WHERE `ID` IN (%s);" % ",".join(str(i) for i in sorted(set(wow_ids.values()) - created))]
    if overlays:
        sql.append("INSERT INTO `chrclasses_dbc` (" + ",".join(f"`{c}`" for c in names) + ") VALUES\n"
                   + ",\n".join("(" + ",".join(sql_value(r[c]) for c in names) + ")" for r in overlays) + ";")
    return "\n".join(sql) + "\n", client.bytes(), overlays


def class_names(client_bytes, server_dbc=None):
    """(sql, client ChrClasses.dbc bytes): every live class's Name_Lang_enUS set to
    its D3 name on top of the DisplayPower file. The migration overlays the whole
    row (stock + DisplayPower + name) for each live class, so the server draws the
    same name as the client; world_0019 stays as applied."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from dbc_store import Store, schema, sql_value
    columns = schema(MODULE.parent, "chrclasses_dbc")
    store = Store(client_bytes, columns)
    stock = Store(Path(server_dbc or SERVER_DBC / "ChrClasses.dbc").read_bytes(), columns)
    created = created_class_ids()
    live = {int(r["wow_class_id"]): r["d3_class"].strip() for r in read(DATA / "class_map.csv")
            if int(r["wow_class_id"]) not in created}
    rows = []
    for wow_id in sorted(live):
        if wow_id not in stock.rows:
            raise SystemExit(f"ChrClasses.dbc has no class {wow_id} for {live[wow_id]}")
        values = store.decode(wow_id)
        values["Name_Lang_enUS"] = live[wow_id]
        store.encode(values)
        # The server row keeps the stock family: only the client's takes a stock-slot class's records' family.
        rows.append(dict(values, SpellClassSet=stock.decode(wow_id)["SpellClassSet"]))
    names = [c[0] for c in columns]
    sql = ["-- Generated by generate_class_resources.py from class_map.csv: a live class's",
           "-- ChrClasses name is its D3 name (Warrior -> Barbarian, Mage -> Wizard), overlaid on the",
           "-- stock row with the class's DisplayPower (diablocraft-race-class-unlock).",
           "SET NAMES utf8mb4;",
           "DELETE FROM `chrclasses_dbc` WHERE `ID` IN (%s);" % ",".join(str(i) for i in sorted(live)),
           "INSERT INTO `chrclasses_dbc` (" + ",".join(f"`{c}`" for c in names) + ") VALUES\n"
           + ",\n".join("(" + ",".join(sql_value(r[c]) for c in names) + ")" for r in rows) + ";"]
    return "\n".join(sql) + "\n", store.bytes(), rows


def main():
    entries = registry()
    HEADER.write_text(render(entries), encoding="utf-8", newline="\n")
    NAMES_LUA.write_text(render_names(entries), encoding="utf-8", newline="\n")
    ENGINE_HEADER.write_text(render_engine(entries), encoding="utf-8", newline="\n")
    from applied_migrations import write_coupled_outputs, write_migration
    sql, client, overlays = display_power(entries)
    migration = UPDATES / DISPLAY_POWER_MIGRATION
    write_migration(MODULE, migration, sql)
    names_sql, client, _ = class_names(client)
    names_migration = UPDATES / CLASS_NAMES_MIGRATION
    write_migration(MODULE, names_migration, names_sql)
    write_coupled_outputs(MODULE, names_migration, names_sql, [(CLIENT_CHRCLASSES, client)],
                          label="ChrClasses.dbc DisplayPower and names")
    print("  DisplayPower overlays: " + (", ".join(f"class {o['ID']} -> {o['DisplayPower']}" for o in overlays)
                                         or "none"))
    print(f"class resources: {len(entries)} rows -> {HEADER.relative_to(MODULE.parent)}, "
          f"{NAMES_LUA.relative_to(MODULE.parent)}, {ENGINE_HEADER.relative_to(MODULE.parent)}")


if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    sys.exit(main())

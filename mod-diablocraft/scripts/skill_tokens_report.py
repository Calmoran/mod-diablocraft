#!/usr/bin/env python3
"""Build docs/research/skill-tokens.md: the token vocabulary for every class.

Report only (task diablocraft-ou9). Reads, never writes, the sheets and the
reference data; the one file it writes is the report.

    python3 mod-diablocraft/scripts/skill_tokens_report.py [--out <path>]

Source of the sentences: reference/d3planner/data.json.

    skilltips[<class>][<skill>]["x"]        the BASE skill tooltip
    skilltips[<class>][<skill>]["a".."e"]   the five rune tooltips
    passivetips[<class>][<passive>]         the passive tooltip

Blizzard marks every parameter in those sentences with
<span class="d3-color-green">. The unlock level is not a parameter: it sits in
<p class="subtle">Unlocked at level <em>N</em></p>, and the flavour text in a
trailing <div class="tooltip-extension">. Both are dropped before anything is
read, together with the icon <span> and the empty <p>Requires ...</p>.

Naming rule, the same one the tunables sheets use: snake_case ending in the
unit (_pct, _seconds, _yards, _count, _per_second). A token is a ROLE plus a
UNIT, so the same meaning keeps the same name in every class; where one
sentence carries two values of the same unit, the role tells them apart
(slow_pct and slow_duration_seconds, never pct_1/pct_2).
"""
import argparse
import collections
import html
import json
import pathlib
import re
import sys

MODULE_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = MODULE_ROOT.parent
DATA = REPO_ROOT / "reference/d3planner/data.json"
D3 = MODULE_ROOT / "data/d3"
SRC = MODULE_ROOT / "src"
DEFAULT_OUT = REPO_ROOT / "docs/research/skill-tokens.md"

CLASSES = ["barbarian", "crusader", "demonhunter", "monk", "necromancer",
           "witchdoctor", "wizard"]
# The resource NAME is a class attribute, not a token: the sentence says
# "Cost: {resource_cost} Fury" and the class table supplies the word.
RESOURCES = {"barbarian": "Fury", "crusader": "Wrath", "demonhunter": "Hatred",
             "monk": "Spirit", "necromancer": "Essence", "witchdoctor": "Mana",
             "wizard": "Arcane Power"}
RESOURCE_WORDS = ["fury", "wrath", "hatred", "discipline", "spirit", "essence",
                  "mana", "arcane power"]

GREEN = re.compile(r'<span class="d3-color-green">(.*?)</span>', re.S)
SUBTLE = re.compile(r'<p class="subtle">.*?</p>', re.S)
EXTENSION = re.compile(r'<div class="tooltip-extension.*', re.S)
REQUIRES = re.compile(r'<p>Requires <span class="value"></span></p>', re.S)
ICON = re.compile(r'<span class="d3-icon.*?</span>\s*</span>', re.S)
TAG = re.compile(r"<[^>]+>")
NUMBER = re.compile(r"^-?[0-9]+(?:[.,][0-9]+)?$")


def plain(fragment):
    """Tag-free, whitespace-collapsed text."""
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", fragment))).strip()


def body_of(raw):
    """The tooltip with everything that is not a parameter sentence removed."""
    body = EXTENSION.sub("", raw)
    body = SUBTLE.sub("", body)
    body = REQUIRES.sub("", body)
    body = ICON.sub("", body)
    return body


class Value:
    """One green-marked parameter with the sentence around it."""

    def __init__(self, cls, kind, skill, rune, raw, before, after, sentence):
        self.cls = cls              # barbarian ...
        self.kind = kind            # skill | rune | passive
        self.skill = skill
        self.rune = rune            # "" for a base skill or a passive
        self.raw = raw              # "500%", "1.5", "Freeze"
        self.before = before        # plain text before it, whole tip
        self.after = after          # plain text after it, whole tip
        self.sentence = sentence    # the tip as one plain line
        self.token = ""
        self.unit = ""
        self.note = ""

    @property
    def numeric(self):
        return bool(NUMBER.match(self.raw.rstrip("%")))

    @property
    def tail(self):
        return " ".join(self.before.split()[-12:]).lower()

    @property
    def head(self):
        return " ".join(self.after.split()[:8]).lower()

    def where(self):
        what = self.skill if not self.rune else "%s / %s" % (self.skill, self.rune)
        return "%s %s" % (self.cls, what)


def collect(data):
    """Every green-marked value in every tip of every class, in tip order."""
    values = []
    for cls in CLASSES:
        for skill, entry in sorted(data["skilltips"][cls].items()):
            for key in ("x", "a", "b", "c", "d", "e"):
                raw = entry.get(key)
                if not isinstance(raw, str):
                    continue
                body = body_of(raw)
                sentence = plain(body)
                for match in GREEN.finditer(body):
                    values.append(Value(
                        cls, "skill" if key == "x" else "rune", skill,
                        "" if key == "x" else key, plain(match.group(1)),
                        plain(body[:match.start()]), plain(body[match.end():]),
                        sentence))
        for passive, raw in sorted(data["passivetips"][cls].items()):
            body = body_of(raw)
            sentence = plain(body)
            for match in GREEN.finditer(body):
                values.append(Value(cls, "passive", passive, "",
                                    plain(match.group(1)),
                                    plain(body[:match.start()]),
                                    plain(body[match.end():]), sentence))
    return values


# --- units -----------------------------------------------------------------
#
# The unit comes from the value and the word that follows it, which is how a
# reader tells them apart too.
STATE_WORDS = re.compile(r"^(chill|freez|frozen|stun|blind|fear|charm|immobil|"
                         r"root|slow|knock|immunity|taunt)", re.I)
RANGE = re.compile(r"^[0-9][0-9,. ]*-[0-9,. ]*[0-9]$")


def unit_of(value):
    head = value.head
    if not value.numeric:
        if RANGE.match(value.raw.strip()):
            return "range"          # "69735 - 91192": two numbers in one span
        if STATE_WORDS.match(value.raw.strip()):
            return "state"          # Frozen, Chilled, Stuns: a control effect
        return "word"               # Fire, Cold, Teleport: prose Blizzard colours
    if value.raw.endswith("%"):
        return "pct"
    if re.match(r"((consecutive|additional|more) )?(seconds?\b|secs?\b)", head):
        return "seconds"
    if re.match(r"(minute)", head):
        return "minutes"
    if re.match(r"yards?\b", head):
        return "yards"
    if re.match(r"(%s)\b" % "|".join(RESOURCE_WORDS), head):
        return "resource"
    if re.match(r"(times|stacks)\b", head):
        return "count"
    if re.match(r"(life|health)\b", head) or re.search(r"(life|health)$", value.tail):
        return "life"
    return "count"


# --- roles -----------------------------------------------------------------
#
# Ordered: the first rule whose pattern matches the words just before the
# value (`tail`) or just after it (`head`) names the role. Specific before
# general, because "increase your damage by N%" and "deals N% weapon damage"
# are both about damage and are not the same number.
ROLE_RULES = [
    # cost, generation, cooldown: the three label lines of a tooltip
    ("tail", r"cost:\s*$", "resource_cost"),
    ("tail", r"generate:\s*$", "resource_generated"),
    ("tail", r"increase (fury|wrath|hatred|spirit|essence|mana|arcane power) generated to$", "resource_generated"),
    ("tail", r"cooldown:\s*$", "cooldown"),
    ("tail", r"cooldown (is )?(reduced|lowered) by$", "cooldown_reduction"),
    ("tail", r"reduce[sd]? the cooldown of [^.]* by$", "cooldown_reduction"),
    ("tail", r"(gain|regain) a charge every$", "charge_recharge"),
    ("tail", r"(store|stores) up to$", "charge"),
    ("tail", r"(number of )?charges to$", "charge"),
    ("head", r"^charges?\b", "charge"),
    ("tail", r"(once|more than once) every$", "internal_cooldown"),
    ("tail", r"every$", "interval"),

    # damage the skill deals, and damage the character deals in general
    ("head", r"^(of (your )?)?(total |additional )?weapon damage", "damage"),
    ("tail", r"maximum total of$", "max_damage"),
    ("tail", r"(increase|increases|increased) (your |the )?(total )?damage (dealt )?(by|to)$", "damage_bonus"),
    ("tail", r"(deal|deals|take|takes) $|(deal|deals) an additional$", "damage_bonus"),
    ("tail", r"additional damage$", "damage_bonus"),
    ("tail", r"damage (taken|from [a-z ]+) (is )?(increased|reduced) by$", "damage_taken"),
    ("tail", r"(reduce|reduces|reducing) (all )?damage taken by$", "damage_reduction"),
    ("tail", r"(all|non-physical|physical|elemental) damage taken by$", "damage_taken"),
    ("tail", r"(increase|increases) (all )?damage (you )?(take|taken) by$", "damage_taken"),

    # crowd control, each with its own duration
    ("tail", r"(slow|slows|slowed|slowing)[^.]{0,30}(by|amount to)$", "slow"),
    ("tail", r"(life|health) on hit by$", "life_per_hit"),
    ("head", r"^(additional )?(life|health) on hit", "life_per_hit"),
    ("tail", r"(health|life) lower than$|(health|life) below$", "life_threshold"),
    ("head", r"^of damage dealt", "damage_share"),
    ("head", r"^(strength|dexterity|intelligence|vitality)\b", "primary_stat"),
    ("tail", r"(chill|chills|chilled)[^.]{0,30}by$", "chill"),
    ("tail", r"(slow|slowed|slowing)[^.]{0,40}for$", "slow_duration"),
    ("tail", r"(chill|chilled)[^.]{0,40}for$", "chill_duration"),
    ("tail", r"(stun|stuns|stunned|stunning)[^.]{0,40}for$", "stun_duration"),
    ("tail", r"(freeze|freezes|frozen)[^.]{0,40}for$", "freeze_duration"),
    ("tail", r"(blind|blinds|blinded)[^.]{0,40}for$", "blind_duration"),
    ("tail", r"(fear|feared|flee)[^.]{0,40}for$", "fear_duration"),
    ("tail", r"(immobiliz|root)[a-z]*[^.]{0,40}for$", "immobilize_duration"),
    ("tail", r"(charm|charmed)[^.]{0,40}for$", "charm_duration"),
    ("tail", r"knock(ed)? (back|up)[^.]{0,20}$", "knockback"),
    ("tail", r"chance to (stun|freeze|blind|fear|immobilize|slow)[a-z]* (enemies )?(for|by)?$", "cc_chance"),

    ("tail", r"reduce (the )?cooldown( of [a-z\' ]+)? by$", "cooldown_reduction"),
    ("tail", r"reduce (the )?cooldown( of [a-z\' ]+)? to$", "cooldown"),
    ("tail", r"cooldown of [a-z\' ]+ to$", "cooldown"),
    ("tail", r"reduce all cooldowns by$", "cooldown_reduction"),
    ("tail", r"recharge time is reduced by$", "charge_recharge_reduction"),
    ("tail", r"reduce (the )?cost (of [a-z\' ]+ )?to$", "resource_cost"),
    ("tail", r"(increase|increases|increase the) damage( of [a-z\' ]+)?( bonus)? to$", "damage"),
    ("tail", r"movement speed (is )?reduced by$", "slow"),
    ("tail", r"(is|are) at$", "stack_threshold"),

    # geometry
    ("tail", r"within$|in a$|of the impact location$", "radius"),
    ("head", r"^yards?\b", "radius"),
    ("head", r"^yard (line|long|wide)", "length"),

    # a label list — "Critical Hit Chance: 10% Attack Speed: 25%" — where the
    # noun AFTER the value belongs to the next label, not to this one
    ("tail", r"(critical hit chance|crit chance):$", "crit_chance"),
    ("tail", r"critical hit damage:$", "crit_damage"),
    ("tail", r"attack speed:$", "attack_speed"),
    ("tail", r"movement speed:$", "movement_speed"),
    ("tail", r"dodge( chance)?:$", "dodge"),
    ("tail", r"block( chance| amount)?:$", "block"),
    ("tail", r"armor:$", "armor"),
    ("tail", r"(all )?resistances?:$", "resistance"),
    ("tail", r"(life|health) (regeneration|per second):$", "life_regen"),
    ("tail", r"thorns:$", "thorns"),

    # "enemies instead take 25% increased damage" is a debuff on them, not a
    # bonus the character carries
    ("tail", r"(enemies|they|you|targets|it)( instead| also)? takes?$", "damage_taken"),
    # the noun after the value, for the many sentences that read
    # "gain 3% critical hit chance" instead of "critical hit chance by 3%"
    ("head", r"^(increased |additional |more )?critical hit chance", "crit_chance"),
    ("head", r"^(increased |additional |more )?critical hit damage", "crit_damage"),
    ("head", r"^(increased |additional |more )?attack speed", "attack_speed"),
    ("head", r"^(increased |additional |more )?movement speed", "movement_speed"),
    ("head", r"^(increased |additional |more )?armor\b", "armor"),
    ("head", r"^(increased |additional |more )?(all )?resistances?\b", "resistance"),
    ("head", r"^(increased |additional |more )?damage reduction", "damage_reduction"),
    ("head", r"^(increased |additional |more )?dodge", "dodge"),
    ("head", r"^(increased |additional |more )?block", "block"),
    ("head", r"^(increased |additional |more )?thorns", "thorns"),
    ("head", r"^(increased |additional )?(life|health) regeneration", "life_regen"),
    ("head", r"^(life|health) per (hit|attack|kill|second|fury|point)", "life_per_hit"),
    ("head", r"^(increased |additional |more )?(damage|attack damage)\b", "damage_bonus"),
    ("head", r"^of (the|your|their) damage", "damage_share"),
    ("head", r"^(%s)\b" % "|".join(RESOURCE_WORDS), "resource_gain"),
    ("head", r"^(piercing |charged |homing |additional )*(bolts|projectiles|missiles|arrows|daggers|spears|grenades|shards|orbs|blades|bombs)", "projectile_count"),
    ("head", r"^or more stacks", "stack_threshold"),
    # Two meanings wear the same words. A count that the ability REACHES - it
    # ricochets to, chains to, pulls, entangles - is a `target_count`. A count
    # of enemies that are ALREADY near you, which gates or scales an effect
    # and reaches nobody, is a `nearby_enemy_count` (Architect, 2026-09-20,
    # spell rewrite step 6). The threshold phrasing is the tail, so it is
    # tested first; everything else keeps the reach meaning.
    ("tail", r"(as long as|while|when|whenever|if|where) there are$", "nearby_enemy_count"),
    ("tail", r"\bis near$", "nearby_enemy_count"),
    ("head", r"^(nearby |all |other |additional |more )*(enemies|targets|corpses|allies|minions|monsters)\b", "target_count"),

    # defensive and offensive stats
    ("tail", r"(armor)( is increased by| by| to|:)?$", "armor"),
    ("tail", r"(additional armor|armor for)$", "armor"),
    ("tail", r"(all )?resistances?( by| to|:)?$", "resistance"),
    ("tail", r"(critical hit chance|crit chance)( by| to|:)?$", "crit_chance"),
    ("tail", r"chance to be critically hit (for|by)$", "crit_taken"),
    ("tail", r"critical hit damage( by| to|:)?$", "crit_damage"),
    ("tail", r"attack speed( by| to| increases by)?$", "attack_speed"),
    ("tail", r"movement speed( by| to|:)?$", "movement_speed"),
    ("tail", r"dodge( chance)?( by| to|:)?$", "dodge"),
    ("tail", r"block (chance|amount)( by| to|:)?$", "block"),
    ("tail", r"thorns( by| to|:)?$", "thorns"),
    ("tail", r"(life|health) regeneration( by| to| per second)?$", "life_regen"),
    ("tail", r"maximum (life|health)( by| to|:)?$", "max_life"),
    ("tail", r"maximum (fury|wrath|hatred|spirit|essence|mana|arcane power|discipline)( by| to|:)?$", "max_resource"),
    ("tail", r"(heal|heals|healed|healing)[^.]{0,30}(for|by)$", "heal"),
    ("tail", r"(gain|gains|restore|restores|grant|grants)[^.]{0,20}(life|health)$", "heal"),
    ("tail", r"(life|health) (per|each) (hit|attack|second|kill)$", "heal"),
    ("tail", r"of your (maximum )?(life|health)$", "heal"),
    ("head", r"^of your (maximum )?(life|health)", "heal"),
    ("tail", r"(resource )?cost (of [^.]{0,30})?(is )?(reduced|lowered) by$", "resource_cost_reduction"),
    ("tail", r"shield[^.]{0,30}(for|by|absorbs)$", "shield"),
    ("tail", r"absorb[a-z]*[^.]{0,30}(for|up to)?$", "shield"),

    # the subject sits in front of "is increased by" / "by"
    ("tail", r"thorns[^.]{0,25}by$", "thorns"),
    ("tail", r"(critical )?hit chance[^.]{0,25}by$", "crit_chance"),
    ("tail", r"resistances?[^.]{0,30}by$", "resistance"),
    ("tail", r"(strength|dexterity|intelligence|vitality)( bonus)? (by|to)$", "primary_stat"),
    ("tail", r"(fury|wrath|hatred|spirit|essence|mana|arcane power|discipline) (generation|regeneration)[^.]{0,20}(by|to)$", "resource_regen"),
    ("tail", r"regeneration from [a-z\' ]+ to$", "resource_regen"),
    ("tail", r"\bgenerate$", "resource_generated"),   # never "regenerate"
    ("tail", r"cooldowns? of [^.]{0,60}by$", "cooldown_reduction"),
    ("tail", r"(cost|costs)[^.]{0,20}(by|to)$", "resource_cost_reduction"),
    ("tail", r"(skills |all )?cost$", "resource_cost_reduction"),
    ("tail", r"(while |when |enemies |are )?(below|above|under|at or below)$", "life_threshold"),
    ("tail", r"reduces you to$", "life_floor"),
    ("tail", r"(you |they )?take$", "damage_taken"),
    ("tail", r"(increase|increases) healing to$", "heal"),
    ("tail", r"regenerate$", "life_regen"),
    ("head", r"^(secondary |additional )?(tremors|explosions|waves|charges|strikes|hits|bolts)\b", "hit_count"),
    ("head", r"^(life|health)\b", "life_threshold"),
    ("head", r"^(life|health)\b", "heal"),
    ("tail", r"for the (first|next|last)$", "duration"),
    ("head", r"^(increased|reduced|greater|lower) chance", "proc_chance"),
    ("tail", r"(is |are )?reduced to$", "duration"),
    ("tail", r"duration of (the )?[a-z\' ]* to$", "duration"),
    ("tail", r"(splits? into|scatters|raining|ricochets? to|crack into|force that|unleash(ing)? it after)$", "spawn_count"),

    # an enemy debuff: "enemies hit deal 20% reduced damage"
    ("head", r"^(reduced|less|increased|more) damage", "enemy_damage"),
    ("tail", r"damage done by [^.]{0,40}by$", "enemy_damage"),
    ("tail", r"(deal|deals|dealing)$", "enemy_damage"),
    ("head", r"^of (your|their) thorns", "thorns_share"),
    ("head", r"^cooldown reduction", "cooldown_reduction"),
    ("tail", r"(critically struck|crit) by$", "crit_taken"),
    ("tail", r"(life|health) per second by$", "life_regen"),
    ("tail", r"(increases|increase) your (life|health) by$", "max_life"),
    ("tail", r"maximum (fury|wrath|hatred|spirit|essence|mana|arcane power|discipline) is increased (by|to)$", "max_resource"),
    ("head", r"^[a-z ]{0,20}(darts|orbs|meteors|explosions|spiders|traps|shots|skeletons|wave attacks|guns|pulses|charges)\b", "spawn_count"),

    # counts of things
    ("tail", r"stacks? up to$|stacks to$", "max_stacks"),
    ("head", r"^(times|stacks)\b", "max_stacks"),
    ("tail", r"up to$|a maximum of$|maximum number of$|maximum total of$", "max_count"),
    ("tail", r"(chance|chances) to$|chance of$", "proc_chance"),
    ("head", r"^chance\b", "proc_chance"),
    ("tail", r"(summon|summons|spawn|spawns|have|controls)[^.]{0,25}$", "pet_count"),
    ("tail", r"(hits|strikes|pierces|bounces|ricochets)[^.]{0,20}$", "hit_count"),

    # durations that belong to no effect above
    ("tail", r"over$", "dot_duration"),
    ("tail", r"(for|lasts|lasting|duration to|duration of)$", "duration"),
]


# When no rule fires, the stat being changed is usually named earlier in the
# same sentence ("Increase armor of you and your allies by 20%"), further back
# than the twelve-word window. The fallback takes the LAST stat word in the
# sentence the value sits in.
SUBJECT_KEYWORDS = [
    (r"critical hit damage", "crit_damage"),
    (r"critical hit chance|chance to critically hit", "crit_chance"),
    (r"attack speed", "attack_speed"),
    (r"movement speed|run speed", "movement_speed"),
    (r"resistances?\b", "resistance"),
    (r"\barmor\b", "armor"),
    (r"damage reduction|reduced damage", "damage_reduction"),
    (r"\bthorns\b", "thorns"),
    (r"\bdodge\b", "dodge"),
    (r"\bblock\b", "block"),
    (r"life regeneration|health regeneration", "life_regen"),
    (r"maximum (life|health)", "max_life"),
    (r"\b(heal|heals|healing|healed)\b", "heal"),
    (r"cooldowns? of|reduce[sd]? (the )?cooldowns?|cooldowns? (is|are) reduced", "cooldown_reduction"),
    (r"\bcosts?\b", "resource_cost_reduction"),
    (r"\b(strength|dexterity|intelligence|vitality)\b", "primary_stat"),
    (r"(fury|wrath|hatred|spirit|essence|mana|arcane power|discipline) (generation|regeneration)", "resource_regen"),
    (r"\bdamage\b", "damage_bonus"),
]
# Words that follow a bare count and say what is being counted.
COUNTABLE = (r"^(small |smaller |nearby |burning |additional |secondary )*"
             r"(fragments|beams|hammers|mines|spheres|avatars|bolts|orbs|bolas|"
             r"missiles|projectiles|spirits|allies|enemies|targets|corpses|"
             r"charges|times|stacks|shards|blades|copies|images|minions|dogs|"
             r"rockets|beasts|monsters|sentries|turrets|hydras|zombies)")


def role_of(value, unit=None):
    for side, pattern, role in ROLE_RULES:
        text = value.tail if side == "tail" else value.head
        if not re.search(pattern, text):
            continue
        if unit and role in ROLE_UNITS and unit not in ROLE_UNITS[role]:
            continue  # the right words, the wrong unit: keep looking
        return role
    if re.match(COUNTABLE, value.head):
        return "target_count" if re.match(r"^(nearby )?(enemies|targets|allies|corpses)", value.head) else "spawn_count"
    # Separator-agnostic on purpose: the same sentence reaches this function as
    # a tip ("... by 15 seconds. Call of the Ancients by 30 seconds.") and as a
    # sheet cell ("... by 15 seconds. | Call of the Ancients by 30 seconds."),
    # and both have to name the value the same way, so `|` is whitespace here
    # and the search is a plain window of words rather than a sentence count.
    window = " ".join(re.sub(r"\|", " ", value.before.lower()).split()[-40:])
    best, best_end = "", -1
    for keyword, role in SUBJECT_KEYWORDS:
        if unit and role in ROLE_UNITS and unit not in ROLE_UNITS[role]:
            continue
        for found in re.finditer(keyword, window):
            if found.end() > best_end:      # the stat word nearest the value
                best, best_end = role, found.end()
    return best


# A role only fits some units: "within 9 yards" is a radius, "gain a 35%
# chance" is not, even though both sentences contain "a". A rule whose role
# does not accept the value's unit is skipped and the next rule gets its turn.
ROLE_UNITS = {
    "radius": {"yards"}, "length": {"yards"}, "knockback": {"yards"},
    "cooldown": {"seconds", "minutes"}, "cooldown_reduction": {"seconds", "pct"},
    "internal_cooldown": {"seconds"}, "charge_recharge": {"seconds"},
    "charge_recharge_reduction": {"seconds"}, "interval": {"seconds", "resource", "count", "yards"},
    "duration": {"seconds", "minutes"}, "dot_duration": {"seconds"},
    "slow_duration": {"seconds"}, "chill_duration": {"seconds"},
    "stun_duration": {"seconds"}, "freeze_duration": {"seconds"},
    "blind_duration": {"seconds"}, "fear_duration": {"seconds"},
    "immobilize_duration": {"seconds"}, "charm_duration": {"seconds"},
    "slow": {"pct"}, "chill": {"pct"}, "cc_chance": {"pct"},
    "damage": {"pct"}, "damage_bonus": {"pct"}, "damage_taken": {"pct"},
    "damage_reduction": {"pct"}, "damage_share": {"pct"}, "max_damage": {"pct"},
    "crit_chance": {"pct"}, "crit_damage": {"pct"}, "crit_taken": {"pct"},
    "attack_speed": {"pct"}, "movement_speed": {"pct"}, "dodge": {"pct"},
    "block": {"pct"}, "thorns": {"pct", "count"}, "armor": {"pct", "count"},
    "resistance": {"pct", "count"}, "primary_stat": {"pct", "count"},
    "max_life": {"pct"}, "life_threshold": {"pct"}, "life_floor": {"pct"},
    "heal": {"pct", "life", "count"}, "life_per_hit": {"life", "count"},
    "life_regen": {"pct", "life", "count"}, "shield": {"life", "count", "pct", "seconds"},
    "resource_cost": {"resource", "count"}, "resource_generated": {"resource", "count", "pct"},
    "resource_gain": {"resource", "count", "pct"}, "max_resource": {"resource", "count", "pct"},
    "resource_cost_reduction": {"pct", "resource", "count"},
    "resource_regen": {"pct", "resource", "count"},
    "max_stacks": {"count"}, "max_count": {"count", "pct"}, "charge": {"count", "resource"},
    "stack_threshold": {"count"}, "proc_chance": {"pct"},
    "pet_count": {"count"}, "hit_count": {"count"}, "target_count": {"count"},
    "nearby_enemy_count": {"count"},
    "spawn_count": {"count"}, "projectile_count": {"count"},
    "enemy_damage": {"pct"}, "thorns_share": {"pct"},
}
# The unit is written into the token name, except where the role already says
# it: a cost is in resource points, a heal in Life, a cooldown in seconds.
# Families where a bare number is not a count.
LIFE_ROLES = {"heal", "life_per_hit", "life_regen", "shield"}
RESOURCE_ROLES = {"resource_cost", "resource_generated", "resource_gain",
                  "resource_regen", "max_resource", "resource_cost_reduction"}
STAT_POINT_ROLES = {"armor", "resistance", "primary_stat", "thorns"}
UNIT_SUFFIX = {"pct": "_pct", "seconds": "_seconds", "minutes": "_minutes",
               "yards": "_yards", "count": "_count", "resource": "_resource",
               "life": "_life", "points": "_points", "state": ""}
# (role, unit) pairs that get a different name from role+suffix. Every token
# ends in its unit: _pct, _seconds, _minutes, _yards, _count, and for the three
# families where the number is not a count — _resource (resource points, the
# class table supplies the word Fury/Spirit/...), _life (Life points),
# _points (a flat stat amount). See the vocabulary section: those three unit
# suffixes are the one thing in this report that needs the designer's yes or no.
TOKEN_OF = {
    ("resource_cost", "resource"): "cost_resource",
    ("resource_cost_reduction", "resource"): "cost_resource",
    ("resource_cost_reduction", "pct"): "cost_reduction_pct",
    ("resource_generated", "resource"): "generated_resource",
    ("resource_generated", "pct"): "generation_pct",
    ("resource_gain", "resource"): "gain_resource",
    ("resource_gain", "pct"): "gain_pct",
    ("resource_regen", "resource"): "regen_per_second_resource",
    ("resource_regen", "pct"): "regen_pct",
    ("max_resource", "resource"): "max_pool_resource",
    ("max_resource", "pct"): "max_pool_pct",
    ("interval", "resource"): "per_trigger_resource",
    ("interval", "count"): "trigger_count",
    ("interval", "yards"): "distance_yards",
    ("charge", "resource"): "gain_resource",
    ("heal", "life"): "heal_life",
    ("life_per_hit", "life"): "heal_per_hit_life",
    ("life_regen", "life"): "heal_per_second_life",
    ("shield", "life"): "absorb_life",
    ("shield", "pct"): "absorb_pct",
    ("shield", "seconds"): "absorb_duration_seconds",
    ("max_count", "pct"): "max_bonus_pct",
}


def name(value):
    """Set token/unit on one value; an empty token means it needs a human."""
    value.unit = unit_of(value)
    if value.unit in ("state", "word", "range"):
        value.token = ""
        value.note = {"state": "state word, not a number",
                      "word": "prose Blizzard colours, not a number",
                      "range": "a range written as one span"}[value.unit]
        return
    role = role_of(value, value.unit)
    if not role:
        # a bare "for 5 seconds" that no rule and no subject claims is a plain
        # duration; nothing else in the corpus is a naked number of seconds
        if value.unit in ("seconds", "minutes"):
            role = "duration"
        else:
            return
    # A bare number in these families is not a count: it is Life, resource
    # points or a flat stat amount, and the token has to say which.
    if role == "resource_cost" and value.head.startswith("charge"):
        value.token = "charge_cost_count"
        return
    if value.unit == "count":
        if role in LIFE_ROLES:
            value.unit = "life"
        elif role in RESOURCE_ROLES:
            value.unit = "resource"
        elif role in STAT_POINT_ROLES:
            value.unit = "points"
    suffix = UNIT_SUFFIX[value.unit]
    if role.endswith(suffix):
        suffix = ""          # target_count, pet_count: the role is already it
    value.token = TOKEN_OF.get((role, value.unit), role + suffix)


# --- our own sheets --------------------------------------------------------
#
# generate_spells.py builds AbilityData::Row::n[] by taking EVERY number in
# `full_tooltip_text` / `full_rune_text`, in order, after cutting the text at
# "Unlocked". The same rules name those numbers, so n[k] can be read as a
# token name; that mapping is the migration checklist.
GENERATOR_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?")


def read_csv(path):
    import csv
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sheet_values(cls, kind, skill, rune, text):
    """Every number the generator would take, named, in generator order.

    The cell arrives tokenised since the spell rewrite, so the numbers are
    put back first: this function is about how a NUMBER gets named, and a
    placeholder has no number to name.
    """
    body = detokenise(cls, skill, rune, text).split("Unlocked")[0]
    values = []
    for match in GENERATOR_NUMBER.finditer(body):
        value = Value(cls, kind, skill, rune, match.group(0),
                      body[:match.start()], body[match.end():], body)
        # The sheet writes "220% weapon damage"; the % sits after the number.
        if value.after.startswith("%"):
            value.raw += "%"
            value.after = value.after[1:]
        name(value)
        values.append(value)
    return values


def barbarian_index_map():
    """(skill, rune) -> [token per n[] index], exactly as the generator orders."""
    rows = {}
    for row in read_csv(D3 / "barbarian_skills.csv"):
        rows[(row["skill_name"], "")] = sheet_values(
            "barbarian", "skill", row["skill_name"], "", row["full_tooltip_text"])
    for row in read_csv(D3 / "barbarian_runes.csv"):
        rows[(row["skill_name"], row["rune_name"])] = sheet_values(
            "barbarian", "rune", row["skill_name"], row["rune_name"], row["full_rune_text"])
    return rows


# --- the positional reads --------------------------------------------------
#
# Three generated tables are read by index: AbilityData (skills and runes),
# AncientData (the same table under another namespace) and PassiveData. The
# skill a read belongs to is named in the code beside it — Base("Sprint"),
# Buff(p, "Sprint"), Rune(*r, "Marathon"), RowFor("Animosity"), Find(81007) —
# and a rune name is unique across the table, so it names its skill too.
READ = re.compile(r'([A-Za-z_]\w*(?:\("[^"]*"\))?)\s*(?:->|\.)n\[(\d+)\]')
RUNE_ANCHOR = re.compile(r'Rune\(\*?\w+,\s*"([^"]+)"\)')
PASSIVE_ANCHOR = re.compile(r'RowFor\("([^"]+)"\)')
SKILL_ANCHORS = [re.compile(p) for p in (
    r'Base\("([^"]+)"\)',
    r'Buff\(\s*\w+\s*,\s*"([^"]+)"',
    r'(?:r|row)\.skill\)\s*==\s*"([^"]+)"',
    r'skill\s*==\s*"([^"]+)"',
    r'Is\(\s*\*?\w+,\s*"([^"]+)"',
)]
FIND_ANCHOR = re.compile(r"Find\((\d+)\)")
SOURCES = ["src/classes/barbarian/dc_barbarian.cpp", "src/combat/dc_passives.cpp",
           "src/classes/barbarian/dc_barbarian_call_of_the_ancients.cpp", "src/combat/dc_combat.cpp"]


def table_index(header_path, namespace_rows=2):
    """id -> (skill, rune) and rune -> (skill, rune) from a generated table.

    The spell rewrite retired the positional tables: a number is read by name
    now, through `dc_spell_values.h` and `Numbers::Num`. When the header is
    gone the checklist below has nothing left to check, and says so rather
    than failing.
    """
    if not (MODULE_ROOT / header_path).is_file():
        return {}, {}
    text = (MODULE_ROOT / header_path).read_text(encoding="utf-8")
    by_id, by_rune = {}, {}
    for row in re.finditer(r'\{(\d+), "([^"]*)", "([^"]*)", \{', text):
        key = (row.group(2), row.group(3))
        by_id[int(row.group(1))] = key
        if row.group(3):
            by_rune[row.group(3)] = key
    return by_id, by_rune


def positional_reads():
    """Every n[k] in the module, with the row it reads."""
    by_id, by_rune = table_index("src/combat/dc_ability_data.h")
    if not by_id and not by_rune:
        return []
    reads = []
    for relative in SOURCES:
        lines = (MODULE_ROOT / relative).read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            for match in READ.finditer(line):
                variable, index = match.group(1), int(match.group(2))
                skill, rune, passive, how = "", "", "", ""
                window = [match.group(0), line] + lines[max(0, number - 18):number - 1][::-1]
                for candidate in window:
                    found = PASSIVE_ANCHOR.search(candidate)
                    if found:
                        passive, how = found.group(1), "RowFor"
                        break
                    found = RUNE_ANCHOR.search(candidate)
                    if found and found.group(1) in by_rune:
                        skill, rune = by_rune[found.group(1)]
                        how = "Rune name"
                        break
                    found = FIND_ANCHOR.search(candidate)
                    if found and int(found.group(1)) in by_id:
                        skill, rune = by_id[int(found.group(1))]
                        how = "Find(id)"
                        break
                    hit = next((a.search(candidate) for a in SKILL_ANCHORS
                                if a.search(candidate)), None)
                    if hit:
                        skill, how = hit.group(1), "skill name"
                        break
                # `b` is the base row of whatever skill `r` belongs to
                if variable in ("b", "base"):
                    rune = ""
                reads.append({"file": relative, "line": number, "expr": match.group(0),
                              "variable": variable, "index": index, "skill": skill,
                              "rune": rune, "passive": passive, "how": how,
                              "code": line.strip()})
    return reads


# --- our sheets against d3planner ------------------------------------------
def tip_numbers(entry_html):
    """The green-marked numbers of one tip, in order."""
    body = body_of(entry_html)
    out = []
    for match in GREEN.finditer(body):
        raw = plain(match.group(1))
        if NUMBER.match(raw.rstrip("%")):
            out.append(raw.rstrip("%").rstrip("."))
    return out


PLACEHOLDER = re.compile(r"\{([a-z_]+)(?::([a-z_]+))?\}")
_VALUES_CACHE = {}


def values_sheet(cls):
    """{(skill, rune, token, qualifier): "220%"} for a class that has sheets.

    The spell rewrite tokenised the sheets: a cell says `{damage_pct}` where
    it used to say `220%`, and the number moved to `<class>_skill_values.csv`.
    Everything below compares SENTENCES, so it needs the cell the way a reader
    sees it; this is the one place that puts the numbers back.
    """
    if cls in _VALUES_CACHE:
        return _VALUES_CACHE[cls]
    found = {}
    for name_, kind in (("%s_skill_values.csv" % cls, "skill"),
                        ("%s_passive_values.csv" % cls, "passive")):
        path = D3 / name_
        if not path.is_file():
            continue
        for row in read_csv(path):
            raw = row["value"] + ("%" if row["unit"] == "pct" else "")
            found[(row["skill"], row["rune"], row["token"], row["qualifier"])] = raw
    _VALUES_CACHE[cls] = found
    return found


def detokenise(cls, skill, rune, text):
    """One sheet cell with its `{token}` placeholders filled back in."""
    values = values_sheet(cls)
    if not values:
        return text

    def put(match):
        key = (skill, rune, match[1], match[2] or "")
        if key not in values and rune:
            key = (skill, "", match[1], match[2] or "")   # inherited from the skill
        return values.get(key, match[0])

    return PLACEHOLDER.sub(put, text)


def sheet_numbers(text):
    """The numbers generate_spells.py would take from one sheet cell."""
    return GENERATOR_NUMBER.findall(text.split("Unlocked")[0])


SPECIAL = re.compile(r'<p class="special">.*?</p>', re.S)
QUOTES = {"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
          "\u2013": "-", "\u2014": "-", "\u00a0": " "}


def normalize(text):
    """Text as compared: the same sentence from either source must land here.

    Explicitly excluded, in both directions, because they are presentation or
    metadata rather than the sentence:
      * HTML tags, entities and the icon span (tips only);
      * the unlock line, `<p class="subtle">` in a tip and the trailing
        "| Unlocked at level N." segment in a sheet cell;
      * the flavour quote, the tip's trailing `tooltip-extension` div and
        anything after the unlock segment in a sheet cell;
      * the category line, the tip's `<p class="special">` and the sheet's
        "| Primary |" segment, which is already the `category` column;
      * the empty "Requires ..." line a tip carries;
      * the sheet's "|" separators, whitespace runs, curly quotes and dashes;
      * letter case.
    Everything else — every word, number, comma and full stop — is compared.
    """
    for bad, good in QUOTES.items():
        text = text.replace(bad, good)
    text = re.sub(r"\s+", " ", html.unescape(text))
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    return text.strip().strip(".").lower()


def tip_text(raw):
    return normalize(plain(SPECIAL.sub("", body_of(raw))))


def sheet_text(cell, category=""):
    parts = []
    for part in cell.split("|"):
        part = part.strip()
        if not part:
            continue
        if part.lower().startswith("unlocked at level"):
            break                      # the unlock line and the flavour after it
        if category and part.lower() == category.strip().lower():
            continue                   # the category column, repeated in the text
        parts.append(part)
    return normalize(" ".join(parts))


def first_difference(ours, theirs):
    """Where the two texts part company, for the report's mismatch table."""
    a, b = ours.split(), theirs.split()
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return "word %d: ours %r, d3planner %r" % (i + 1, x, y)
    if len(a) != len(b):
        longer, which = (a, "ours") if len(a) > len(b) else (b, "d3planner")
        return "%s has %d extra word(s): %s" % (which, abs(len(a) - len(b)),
                                                " ".join(longer[min(len(a), len(b)):])[:60])
    return "identical"


def text_check(data, cls):
    """Every row whose TEXT differs from the tip, beyond the exclusions above."""
    problems = []
    tips = data["skilltips"][cls]
    by_name = {entry["name"]: (key, entry) for key, entry in data["skills"][cls].items()}
    for row in read_csv(D3 / ("%s_skills.csv" % cls)):
        if row["skill_name"] not in by_name:
            continue
        key, _ = by_name[row["skill_name"]]
        ours = sheet_text(detokenise(cls, row["skill_name"], "",
                                     row.get("full_tooltip_text", "")), row.get("category", ""))
        theirs = tip_text(tips[key]["x"])
        if ours != theirs:
            problems.append((row["skill_name"], "", ours, theirs))
    for row in read_csv(D3 / ("%s_runes.csv" % cls)):
        if row["skill_name"] not in by_name:
            continue
        key, entry = by_name[row["skill_name"]]
        letter = next((l for l, r in entry.get("runes", {}).items()
                       if r == row["rune_name"]), "")
        if not letter:
            continue
        ours = sheet_text(detokenise(cls, row["skill_name"], row["rune_name"],
                                     row.get("full_rune_text", "")))
        theirs = tip_text(tips[key][letter])
        if ours != theirs:
            problems.append((row["skill_name"], row["rune_name"], ours, theirs))
    for row in read_csv(D3 / ("%s_passives.csv" % cls)):
        key = re.sub(r"[^a-z]", "", row["passive_name"].lower())
        if key not in data["passivetips"][cls]:
            continue
        ours = sheet_text(detokenise(cls, row["passive_name"], "", row.get("full_text", "")))
        theirs = tip_text(data["passivetips"][cls][key])
        if ours != theirs:
            problems.append((row["passive_name"], "passive", ours, theirs))
    return problems


def cross_check(data, cls):
    """Every row where our sheet and the d3planner tip disagree."""
    problems = []
    tips = data["skilltips"][cls]
    catalogue = data["skills"][cls]
    by_name = {entry["name"]: (key, entry) for key, entry in catalogue.items()}
    skills = read_csv(D3 / ("%s_skills.csv" % cls))
    runes = read_csv(D3 / ("%s_runes.csv" % cls))
    passives = read_csv(D3 / ("%s_passives.csv" % cls))

    for row in skills:
        name_ = row["skill_name"]
        if name_ not in by_name:
            problems.append((name_, "", "no d3planner skill of that name", "", ""))
            continue
        key, _ = by_name[name_]
        ours = sheet_numbers(detokenise(cls, name_, "", row.get("full_tooltip_text", "")))
        theirs = tip_numbers(tips[key]["x"])
        if ours != theirs:
            problems.append((name_, "", "numbers differ", " ".join(ours), " ".join(theirs)))

    for row in runes:
        name_, rune = row["skill_name"], row["rune_name"]
        if name_ not in by_name:
            problems.append((name_, rune, "no d3planner skill of that name", "", ""))
            continue
        key, entry = by_name[name_]
        letter = next((l for l, r in entry.get("runes", {}).items() if r == rune), "")
        if not letter:
            problems.append((name_, rune, "no d3planner rune of that name", "", ""))
            continue
        ours = sheet_numbers(detokenise(cls, name_, rune, row.get("full_rune_text", "")))
        theirs = tip_numbers(tips[key][letter])
        if ours != theirs:
            problems.append((name_, rune, "numbers differ (rune %s)" % letter,
                             " ".join(ours), " ".join(theirs)))

    tip_passives = {plain(raw).split(".")[0]: raw for raw in data["passivetips"][cls].values()}
    for row in passives:
        name_ = row["passive_name"]
        key = next((k for k in data["passivetips"][cls]
                    if k == re.sub(r"[^a-z]", "", name_.lower())), "")
        if not key:
            problems.append((name_, "passive", "no d3planner passive of that name", "", ""))
            continue
        ours = sheet_numbers(detokenise(cls, name_, "", row.get("full_text", "")))
        theirs = tip_numbers(data["passivetips"][cls][key])
        if ours != theirs:
            problems.append((name_, "passive", "numbers differ", " ".join(ours), " ".join(theirs)))
    return problems


# --- the report ------------------------------------------------------------
MEANINGS = {
    "damage_pct": "weapon damage the hit deals",
    "damage_bonus_pct": "a damage increase the character gains",
    "enemy_damage_pct": "how much less (or more) damage an affected enemy deals",
    "damage_taken_pct": "a change to the damage the character takes",
    "damage_reduction_pct": "damage removed before it is applied",
    "damage_share_pct": "a share of some other damage number",
    "max_damage_pct": "the cap on a stacking damage number",
    "duration_seconds": "how long the effect lasts",
    "duration_minutes": "the same in minutes, where Blizzard writes minutes",
    "dot_duration_seconds": "the window damage is spread over",
    "cooldown_seconds": "the skill's cooldown",
    "cooldown_reduction_seconds": "seconds taken off a cooldown",
    "cooldown_reduction_pct": "a percentage taken off a cooldown",
    "internal_cooldown_seconds": "how often the effect may happen at all",
    "interval_seconds": "the period of a repeating effect",
    "charge_recharge_seconds": "how long one charge takes to come back",
    "charge_recharge_reduction_seconds": "seconds off that recharge",
    "charge_count": "how many charges are stored",
    "charge_cost_count": "charges one cast costs",
    "radius_yards": "the radius the effect covers",
    "length_yards": "the length of a line effect",
    "distance_yards": "a distance that scales something",
    "knockback_yards": "how far enemies are thrown",
    "cost_resource": "resource points one cast costs",
    "generated_resource": "resource points the skill gives back",
    "generation_pct": "a change to resource generation",
    "gain_resource": "resource points gained by an effect",
    "gain_pct": "the same as a share of maximum",
    "regen_per_second_resource": "resource regenerated per second",
    "regen_pct": "a change to that regeneration",
    "cost_reduction_pct": "a discount on the cost",
    "per_trigger_resource": "resource spent per step of another effect",
    "max_pool_resource": "the maximum resource pool",
    "max_pool_pct": "a change to that maximum",
    "slow_pct": "how much movement is slowed",
    "slow_duration_seconds": "how long the slow lasts",
    "chill_pct": "how much a chill slows",
    "chill_duration_seconds": "how long the chill lasts",
    "stun_duration_seconds": "how long the stun lasts",
    "freeze_duration_seconds": "how long the freeze lasts",
    "blind_duration_seconds": "how long the blind lasts",
    "fear_duration_seconds": "how long the fear lasts",
    "immobilize_duration_seconds": "how long the root lasts",
    "charm_duration_seconds": "how long the charm lasts",
    "cc_chance_pct": "the chance to apply that control effect",
    "proc_chance_pct": "the chance an effect happens",
    "crit_chance_pct": "critical hit chance gained",
    "crit_damage_pct": "critical hit damage gained",
    "crit_taken_pct": "extra chance the enemy is critically hit",
    "attack_speed_pct": "attack speed gained",
    "movement_speed_pct": "movement speed gained",
    "armor_pct": "armor gained, as a percentage",
    "armor_points": "armor gained, as a flat amount",
    "resistance_pct": "resistance gained, as a percentage",
    "resistance_points": "resistance gained, as a flat amount",
    "thorns_pct": "thorns gained",
    "thorns_share_pct": "a share of the character's thorns",
    "primary_stat_pct": "Strength/Dexterity/Intelligence gained, as a percentage",
    "primary_stat_points": "the same, as a flat amount",
    "dodge_pct": "dodge chance gained",
    "block_pct": "block chance gained",
    "max_life_pct": "a change to maximum Life",
    "life_threshold_pct": "the Life level a rule turns on at",
    "life_floor_pct": "the Life a lethal hit leaves",
    "life_regen_pct": "Life regenerated per second, as a percentage",
    "heal_pct": "healing, as a share of maximum Life",
    "heal_life": "healing, as a flat number of Life",
    "heal_per_hit_life": "Life restored per hit or per point spent",
    "heal_per_second_life": "Life restored each second",
    "absorb_life": "damage a shield swallows",
    "absorb_pct": "the share of incoming damage a shield swallows",
    "absorb_duration_seconds": "how long the shield lasts",
    "bonus_duration_seconds": "how long each stack of a bonus lasts",
    "max_stacks_count": "how many times the effect stacks",
    "stack_threshold_count": "the stack count a rule turns on at",
    "max_bonus_pct": "the cap on a stacking percentage",
    "max_count": "the cap on a count",
    "target_count": "how many enemies the ability reaches",
    "nearby_enemy_count": "how many enemies are already near you, for a threshold",
    "pet_count": "how many followers are summoned",
    "spawn_count": "how many secondary things the skill creates",
    "projectile_count": "how many projectiles are fired",
    "hit_count": "how many hits an effect lands",
    "trigger_count": "how many events it takes to fire",
}


# The 35 sentences no rule names. Each proposal is a reading of that one
# sentence, for the designer to accept or change; ten of them would add a token to the
# vocabulary (marked NEW). Keyed by class, skill, rune and the value itself.
PROPOSALS = {
    ("barbarian", "calloftheancients", "e", "50%"): "damage_share_pct",
    ("barbarian", "overpower", "e", "35%"): "damage_share_pct",
    ("barbarian", "juggernaut", "50%"): "cc_duration_reduction_pct (NEW)",
    ("barbarian", "juggernaut", "", "50%"): "cc_duration_reduction_pct (NEW)",
    ("crusader", "condemn", "a", "50%"): "damage_share_pct",
    ("crusader", "smite", "e", "5"): "target_count",
    ("demonhunter", "caltrops", "", "60%"): "slow_pct",
    ("demonhunter", "companion", "e", "10%"): "gold_find_pct (NEW)",
    ("demonhunter", "hungeringarrow", "d", "50%"): "proc_chance_pct",
    ("demonhunter", "rainofvengeance", "d", "8"): "pet_count",
    ("demonhunter", "rapidfire", "c", "2"): "projectile_count",
    ("demonhunter", "customengineering", "", "100%"): "duration_bonus_pct (NEW)",
    ("demonhunter", "customengineering", "", "5"): "max_count",
    ("demonhunter", "grenadier", "", "20%"): "radius_bonus_pct (NEW)",
    ("monk", "breathofheaven", "d", "14"): "gain_resource",
    ("monk", "cripplingwave", "d", "2.5"): "generated_resource",
    ("monk", "deadlyreach", "b", "100%"): "damage_pct",
    ("monk", "wayofthehundredfists", "b", "7"): "the BASE skill's hit_count, quoted in a rune sentence",
    ("monk", "wayofthehundredfists", "b", "10"): "hit_count",
    ("monk", "harmony", "", "40%"): "resistance_share_pct (NEW)",
    ("necromancer", "devour", "d", "50%"): "radius_share_pct (NEW)",
    ("necromancer", "frailty", "e", "50%"): "radius_share_pct (NEW)",
    ("necromancer", "siphonblood", "b", "19"): "gain_resource",
    ("necromancer", "siphonblood", "c", "6%"): "heal_pct",
    ("necromancer", "extendedservitude", "", "25%"): "duration_bonus_pct (NEW)",
    ("witchdoctor", "spiritwalk", "d", "20%"): "gain_pct",
    ("witchdoctor", "bloodritual", "", "20%"): "resource_cost_share_pct (NEW)",
    ("witchdoctor", "fierceloyalty", "", "30%"): "the same token again, on a second row with a condition column",
    ("witchdoctor", "swamplandattunement", "", "120"): "resistance_points",
    ("witchdoctor", "zombiehandler", "", "20%"): "pet_life_pct (NEW)",
    ("wizard", "arcanetorrent", "a", "5%"): "damage_bonus_pct",
    ("wizard", "electrocute", "b", "10"): "target_count",
    ("wizard", "frostnova", "e", "10%"): "crit_chance_pct",
    ("wizard", "mirrorimage", "c", "200%"): "pet_life_pct (NEW)",
    ("wizard", "slowtime", "", "90%"): "projectile_slow_pct (NEW)",
    ("wizard", "arcanedynamo", "", "5"): "stack_threshold_count",
}


def proposal_for(value):
    return PROPOSALS.get((value.cls, value.skill, value.rune, value.raw), "needs a name")


def table(header, rows, aligns=None):
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(out)


def quote(value, width=88):
    """One short line of the sentence, with the value in [brackets]."""
    before = " ".join(value.before.split()[-7:])
    after = " ".join(value.after.split()[:5])
    line = ("%s **[%s]** %s" % (before, value.raw, after)).strip()
    return line if len(line) <= width else line[:width - 1] + "…"


def hard_cases(values):
    """Sentences the naming rule cannot settle on its own."""
    unnamed = [v for v in values
               if not v.token and v.unit not in ("state", "word", "range")]
    crowded = []
    seen = set()
    for value in values:
        if not value.token:
            continue
        same = [o for o in values
                if o.token and o.sentence == value.sentence and o.unit == value.unit
                and o.cls == value.cls and o.skill == value.skill and o.rune == value.rune]
        if len(same) >= 3 and (value.cls, value.skill, value.rune, value.unit) not in seen:
            seen.add((value.cls, value.skill, value.rune, value.unit))
            crowded.append((value, [o.token for o in same]))
    ranges = [v for v in values
              if re.search(r"\d+\s*(-|to)\s*\d+\s*$", v.before) or v.raw.count("-") == 1]
    return unnamed, crowded, ranges


def tip_values(cls, kind, skill, rune, raw):
    """The green-marked NUMBERS of one tip, named, in tip order."""
    body = body_of(raw)
    values = []
    for match in GREEN.finditer(body):
        text = plain(match.group(1))
        if not NUMBER.match(text.rstrip("%")):
            continue                      # a state word, a range, coloured prose
        value = Value(cls, kind, skill, rune, text,
                      plain(body[:match.start()]), plain(body[match.end():]),
                      plain(body))
        name(value)
        values.append(value)
    return values


def token_consistency(data, cls):
    """The tip's token sequence against the sheet's, row by row.

    The numeric check proves the two sources hold the same VALUES. This proves
    the classifier reads them the same way from either wording, which is a
    different thing: a sheet cell separates its sentences with "|" and a tip
    does not, and a rule that counts sentences would name the same number
    differently on each side.
    """
    problems = []
    rows = 0
    tips = data["skilltips"][cls]
    by_name = {entry["name"]: (key, entry) for key, entry in data["skills"][cls].items()}

    def compare(skill, rune, ours, theirs):
        for index in range(max(len(ours), len(theirs))):
            mine = ours[index] if index < len(ours) else None
            yours = theirs[index] if index < len(theirs) else None
            if (mine.token if mine else "") != (yours.token if yours else ""):
                problems.append((skill, rune, index,
                                 mine.raw if mine else "-",
                                 (yours.token or "unnamed") if yours else "missing",
                                 (mine.token or "unnamed") if mine else "missing"))

    for row in read_csv(D3 / ("%s_skills.csv" % cls)):
        if row["skill_name"] not in by_name:
            continue
        key, _ = by_name[row["skill_name"]]
        rows += 1
        compare(row["skill_name"], "",
                sheet_values(cls, "skill", row["skill_name"], "", row["full_tooltip_text"]),
                tip_values(cls, "skill", key, "", tips[key]["x"]))
    for row in read_csv(D3 / ("%s_runes.csv" % cls)):
        if row["skill_name"] not in by_name:
            continue
        key, entry = by_name[row["skill_name"]]
        letter = next((l for l, r in entry.get("runes", {}).items()
                       if r == row["rune_name"]), "")
        if not letter:
            continue
        rows += 1
        compare(row["skill_name"], row["rune_name"],
                sheet_values(cls, "rune", row["skill_name"], row["rune_name"],
                             row["full_rune_text"]),
                tip_values(cls, "rune", key, letter, tips[key][letter]))
    for row in read_csv(D3 / ("%s_passives.csv" % cls)):
        key = re.sub(r"[^a-z]", "", row["passive_name"].lower())
        if key not in data["passivetips"][cls]:
            continue
        rows += 1
        compare(row["passive_name"], "passive",
                sheet_values(cls, "passive", row["passive_name"], "", row["full_text"]),
                tip_values(cls, "passive", key, "", data["passivetips"][cls][key]))
    return rows, problems


def verify_mapping():
    """Check the sheet-derived index map against the generated tables.

    The checklist is only worth reading if n[k] really is the k-th number of
    the sheet cell, so this compares every row of dc_ability_data.h and
    dc_passive_data.h against the numbers this script reads from the CSV.
    """
    problems = []
    ability = MODULE_ROOT / "src/combat/dc_ability_data.h"
    passives = MODULE_ROOT / "src/combat/dc_passive_data.h"
    if not ability.is_file() or not passives.is_file():
        return 0, []     # the positional tables are retired; nothing to verify
    header = ability.read_text(encoding="utf-8")
    index_map = barbarian_index_map()
    rows = re.findall(r'\{(\d+), "([^"]*)", "([^"]*)", \{([^}]*)\}', header)
    for _id, skill, rune, numbers in rows:
        theirs = [n.strip() for n in numbers.split(",") if n.strip()]
        ours = [v.raw.rstrip("%") for v in index_map.get((skill, rune), [])]
        if ours != theirs:
            problems.append(("dc_ability_data.h", skill, rune, " ".join(ours), " ".join(theirs)))
    passive_header = (MODULE_ROOT / "src/combat/dc_passive_data.h").read_text(encoding="utf-8")
    passive_rows = re.findall(r'\{(\d+), "([^"]*)", \{([^}]*)\}', passive_header)
    sheet = {row["passive_name"]: sheet_values("barbarian", "passive", row["passive_name"],
                                               "", row["full_text"])
             for row in read_csv(D3 / "barbarian_passives.csv")}
    for _id, passive, numbers in passive_rows:
        theirs = [n.strip() for n in numbers.split(",") if n.strip()]
        ours = [v.raw.rstrip("%") for v in sheet.get(passive, [])]
        if ours != theirs:
            problems.append(("dc_passive_data.h", passive, "", " ".join(ours), " ".join(theirs)))
    return len(rows) + len(passive_rows), problems


def report(data):
    values = collect(data)
    for value in values:
        name(value)
    named = [v for v in values if v.token]
    states = [v for v in values if v.unit in ("state", "word", "range")]
    per_token = collections.defaultdict(collections.Counter)
    example = {}
    for value in named:
        per_token[value.token][value.cls] += 1
        example.setdefault(value.token, value)
    tokens = sorted(per_token, key=lambda t: (-len(per_token[t]), -sum(per_token[t].values()), t))
    units_of_token = {}
    for value in named:
        units_of_token.setdefault(value.token, value.unit)

    out = []
    w = out.append
    w("# Skill text tokens — the vocabulary for all seven classes")
    w("")
    w("Report for `diablocraft-ou9`, 2026-09-20. Generated by")
    w("`mod-diablocraft/scripts/skill_tokens_report.py`; re-run it to rebuild this file.")
    w("Nothing here changes code or sheets — the designer approves the vocabulary first.")
    w("")
    w("Second revision, after the PM's review. What changed: three rule families")
    w("were naming values wrongly and are fixed — `\\bgenerate` no longer matches")
    w("\"regenerate\" (Inspiring Presence's 3% is `life_regen_pct`, not resource")
    w("generation, and that corrects `dc_passives.cpp:220` and `:391` in the")
    w("checklist), a value followed by the word \"seconds\" is no longer taken for a")
    w("duration when the sentence says it is a cooldown reduction (Boon of")
    w("Bul-Kathos is three `cooldown_reduction_seconds`), and a count followed by")
    w("\"nearby enemies\" is `target_count` rather than something spawned. Every")
    w("token now ends in its unit, with no exception taken for resource points,")
    w("Life or flat stat amounts — see the approval question in section a. The")
    w("sheets are now compared on TEXT as well as numbers, the hard-case lists are")
    w("complete rather than sampled, and the index map behind the checklist is")
    w("verified against the generated tables instead of assumed.")
    w("")
    w("Third revision: the Boon of Bul-Kathos fix above was only half a fix, and")
    w("the claim that all three of its values were corrected was wrong. Two were.")
    w("The third kept `duration_seconds` on the SHEET side — the checklist row")
    w("`dc_passives.cpp:591` — because the fallback counted sentences, and a sheet")
    w("cell separates its sentences with `|` where a tip uses a full stop. The")
    w("fallback is separator-agnostic now, and the cross-check section carries a")
    w("third check that compares the token sequence from the raw tip with the one")
    w("from the sheet, row by row, so a difference of that kind is reported rather")
    w("than claimed away.")
    w("")
    w("Fourth revision: `target_count` was carrying two meanings. A count the")
    w("ability REACHES — the weapon ricochets to three enemies, the chains break")
    w("off and strike up to three, the lightning jumps to two more — is not the")
    w("same fact as a count of enemies who are ALREADY near you and whose number")
    w("turns an effect on. The second is now `nearby_enemy_count`, and across the")
    w("seven classes it is exactly two values: barbarian Brawler's \"as long as")
    w("there are 3 enemies within 12 yards\" and witchdoctor Gargantuan /")
    w("Restless Giant's \"or is near 5 enemies, it enrages\". The other 23 keep")
    w("`target_count`. The split matters beyond naming: a reach count is stored")
    w("in the record's `EffectChainTargets`, whose value includes the primary")
    w("victim, so the writer stores one more than the sheet and every reader")
    w("takes it back off; a threshold reaches nobody, so it is an ordinary")
    w("base-points number with no conversion of its own (Architect, 2026-09-20,")
    w("spell rewrite step 6). Only the barbarian sheets are edited here — the")
    w("other classes have no sheets yet, and their split is reported, not")
    w("applied. Four values are NEITHER meaning and are left as `target_count`")
    w("for a ruling: necromancer Bone Armor's \"up to a maximum of 10 enemies\"")
    w("and Leech's \"up to 20 enemies\" are caps on how many enemies CONTRIBUTE,")
    w("and monk Mystic Ally / Air Ally's \"splits into 2 allies\" and Command")
    w("Golem's \"a pile of 5 corpses\" count things the skill CREATES.")
    w("")
    w("Two repairs came with that rerun, both caused by the spell rewrite and")
    w("neither by the split. The sheets are TOKENISED now — a cell says")
    w("`{damage_pct}` where it said `220%` — so every comparison that reads a")
    w("number out of a cell was reading nothing, and the numbers check reported")
    w("154 barbarian mismatches with an empty \"ours\" column. The cells are")
    w("detokenised from `<class>_skill_values.csv` and")
    w("`<class>_passive_values.csv` before they are compared, which restores")
    w("all three checks: numbers, text and tokens are back to zero for both")
    w("classes. And section e's checklist had no tables left to read —")
    w("`dc_ability_data.h` and `dc_passive_data.h` are gone, the migration it")
    w("tracked is finished — so it says so instead of failing, and fills itself")
    w("in again if either table returns.")
    w("")
    w("## Where the sentences come from")
    w("")
    w("`reference/d3planner/data.json`:")
    w("")
    w("- `skilltips[<class>][<skill>][\"x\"]` — the **base** skill tooltip. The rune")
    w("  texts are the same entry's `\"a\"`…`\"e\"`, and `skills[<class>][<skill>].runes`")
    w("  says which letter is which rune by name.")
    w("- `passivetips[<class>][<passive>]` — the passive tooltip.")
    w("")
    w("Blizzard marks every parameter with `<span class=\"d3-color-green\">`. That is")
    w("the whole extraction rule: **a parameter is a green span, and nothing else is**.")
    w("")
    w("%d green values across the seven classes: %s."
      % (len(values), ", ".join("%s %d" % (cls, sum(1 for v in values if v.cls == cls))
                                for cls in CLASSES)))
    w("")
    w("## a. Vocabulary")
    w("")
    w("%d tokens name %d of the %d values (%.0f%%). %d are state words rather than"
      % (len(tokens), len(named), len(values), 100.0 * len(named) / len(values), len(states)))
    w("numbers (section b) and %d are hard cases (section c)."
      % (len(values) - len(named) - len(states)))
    w("")
    w("Naming rule, the tunables one: snake_case, ending in the unit. A token is a")
    w("ROLE plus a UNIT, so the same meaning keeps the same name in every class, and")
    w("every one of the %d tokens ends in one of eight unit suffixes:" % len(tokens))
    w("")
    w(table(["suffix", "unit", "example"], [
        ["`_pct`", "a percentage", "`damage_pct`"],
        ["`_seconds`", "seconds", "`cooldown_seconds`"],
        ["`_minutes`", "minutes, where Blizzard writes minutes", "`duration_minutes`"],
        ["`_yards`", "yards", "`radius_yards`"],
        ["`_count`", "a plain count of things", "`max_stacks_count`"],
        ["`_resource`", "resource points — **needs the designer's yes**", "`cost_resource`"],
        ["`_life`", "Life points — **needs the designer's yes**", "`heal_life`"],
        ["`_points`", "a flat stat amount — **needs the designer's yes**", "`armor_points`"],
    ]))
    w("")
    w("**Approval question.** The brief names `_pct`, `_seconds`, `_yards`, `_count`,")
    w("`_per_second`. Three kinds of number in this corpus are none of those: a")
    w("number of resource points (a cost, a gain, a maximum pool), a number of Life,")
    w("and a flat stat amount. I have NOT taken an exception to the rule for them —")
    w("every token still ends in a unit — but the three suffixes above are new and")
    w("are the designer's to accept or rename. If they are not accepted, the alternative is")
    w("to spell the unit out (`cost_resource_points`, `heal_life_points`), which is")
    w("longer and says the same thing. The renames this costs are small and")
    w("mechanical: `resource_cost` became `cost_resource`, `resource_generated`")
    w("became `generated_resource`, `max_resource` became `max_pool_resource`.")
    w("")
    rows = []
    for token in tokens:
        counts = per_token[token]
        rows.append([("`%s`" % token), units_of_token[token],
                     MEANINGS.get(token, ""),
                     quote(example[token], 70)]
                    + [counts.get(cls, "") for cls in CLASSES])
    w(table(["token", "unit", "meaning", "example"] + [c[:4] for c in CLASSES], rows))
    w("")
    return out, values, named, states, per_token, tokens, example


def report_rest(data, out, values, named, states, per_token, tokens, example):
    w = out.append
    everywhere = [t for t in tokens if len(per_token[t]) == 7]
    several = [t for t in tokens if 2 <= len(per_token[t]) <= 6]
    alone = [t for t in tokens if len(per_token[t]) == 1]

    w("## b. Interchangeability")
    w("")
    w("Tokens are class-agnostic by construction, and the counts above show it is")
    w("not a hope: **%d of %d tokens are used by more than one class**, and %d appear"
      % (len(everywhere) + len(several), len(tokens), len(everywhere)))
    w("in all seven.")
    w("")
    w("- **All seven classes (%d):** %s" % (len(everywhere), ", ".join("`%s`" % t for t in everywhere)))
    w("- **Several classes (%d):** %s" % (len(several), ", ".join("`%s`" % t for t in several)))
    w("- **One class (%d):** %s" % (len(alone), ", ".join(
        "`%s` (%s)" % (t, list(per_token[t])[0]) for t in alone)))
    w("")
    w("The one-class tokens are not class-specific by nature — `knockback_yards`")
    w("happens to be written once, in a barbarian rune — so they stay in the same")
    w("vocabulary. Nothing in the list is a per-class name.")
    w("")
    w("### What genuinely belongs to a class")
    w("")
    w("The resource **name**. The sentence says `Cost: {resource_cost} Fury`, and the")
    w("word Fury comes from a class table, not from the text:")
    w("")
    w(table(["class", "resource"], [[c, RESOURCES[c]] for c in CLASSES]))
    w("")
    w("The demon hunter has two, Hatred and Discipline, so its rows carry the pool")
    w("as a column (`resource: hatred|discipline`) beside `resource_cost`; the client")
    w("renders the word. No token ever contains a resource name.")
    w("")
    by_kind = collections.defaultdict(collections.Counter)
    for value in states:
        by_kind[value.unit][value.raw] += 1
    w("### Green content that is not a number (%d)" % len(states))
    w("")
    w("Blizzard greens three other things, and none of them is a token.")
    w("")
    w("**States (%d uses, %d words)** — the control effect a skill applies: %s."
      % (sum(by_kind["state"].values()), len(by_kind["state"]),
         ", ".join("%s (%d)" % (word, n) for word, n in by_kind["state"].most_common())))
    w("")
    w("Proposal: leave them as plain text and let the client colour a known list of")
    w("state words the way Blizzard does. A state the server must apply is already a")
    w("mechanic in C++ (`MECHANIC_STUN`, `MECHANIC_FREEZE`); the word in the sentence")
    w("is its label, not its source. If the designer wants them marked, the cheapest mark is")
    w("the same brace form with no value behind it — `{state:frozen}` — which the")
    w("generator can check against the mechanic list and the client can colour.")
    w("")
    w("**Prose (%d uses, %d words)** — %s."
      % (sum(by_kind["word"].values()), len(by_kind["word"]),
         ", ".join("%s (%d)" % (word, n) for word, n in by_kind["word"].most_common())))
    w("")
    w("Element names, weapon types and skill names. They are colour, not parameters:")
    w("the element a rune converts damage to is already its own column")
    w("(`element` in `<class>_runes.csv`, and `skilltips[...].elements` upstream).")
    w("")
    w("**Ranges (%d)** — %s."
      % (sum(by_kind["range"].values()),
         ", ".join("`%s`" % word for word in by_kind["range"])))
    w("")
    w("These are flat damage numbers written as a span in one green mark. They are")
    w("the one shape the brace form cannot hold as a single value, and section c")
    w("says what to do with them.")
    w("")

    unnamed, crowded, ranges = hard_cases(values)
    w("## c. Hard cases")
    w("")
    w("### Sentences carrying three or more values of the same unit (%d)" % len(crowded))
    w("")
    w("The role qualifier is what keeps most of them apart — `life_threshold_pct`,")
    w("`resource_cost_reduction_pct` and `damage_taken_pct` are three percentages in")
    w("one passive and name themselves. The ones where it does not is the next")
    w("subsection.")
    w("")
    w(table(["class", "skill", "unit", "tokens in that sentence"],
            [[v.cls, v.where().split(" ", 1)[1], v.unit, ", ".join("`%s`" % t for t in toks)]
             for v, toks in sorted(crowded, key=lambda c: (c[0].cls, c[0].skill, c[0].rune))]))
    w("")
    w("### Values the rule cannot name (%d)" % len(unnamed))
    w("")
    w("Each is a one-off sentence rather than a missing rule, and each proposal is a")
    w("reading of that sentence for the designer to accept or change. %d of the rows need a"
      % sum(1 for v in unnamed if "NEW" in proposal_for(v)))
    w("name the vocabulary does not have, %d new names between them, marked NEW; the"
      % len({proposal_for(v) for v in unnamed if "NEW" in proposal_for(v)}))
    w("rest fit a token that already exists.")
    w("")
    rows = []
    for value in unnamed:
        rows.append([value.cls, value.where().split(" ", 1)[1], value.unit,
                     quote(value, 64), "`%s`" % proposal_for(value)])
    w(table(["class", "skill / rune", "unit", "sentence", "proposal"], rows))
    w("")
    by_row = collections.defaultdict(list)
    for value in values:
        if value.token:
            by_row[(value.cls, value.skill, value.rune)].append(value)
    clashes = []
    for key, group in by_row.items():
        counts = collections.Counter(v.token for v in group)
        repeated = {token: n for token, n in counts.items() if n > 1}
        if repeated:
            clashes.append((key, repeated, group))
    w("### The same token twice in one sentence (%d rows of %d)"
      % (len(clashes), len(by_row)))
    w("")
    w("This is the collision the naming rule has to answer, and it is the one thing")
    w("in this report that needs a decision rather than a reading. Two shapes:")
    w("")
    w("1. **The same role, different targets** — Fist of the Heavens deals")
    w("   `damage_pct` to the target, `damage_pct` again in the explosion and a third")
    w("   `damage_pct` from the lightning. Proposal: qualify by what deals it —")
    w("   `damage_pct`, `explosion_damage_pct`, `secondary_damage_pct` — keeping the")
    w("   qualifier generic so it means the same in every class.")
    w("2. **A label list** — Wrath of the Berserker writes four stats as")
    w("   `Critical Hit Chance: 10% | Attack Speed: 25% | Dodge Chance: 20% |")
    w("   Movement Speed: 20%`. Those name themselves once the labels are read, and")
    w("   our sheet already separates them with `|`.")
    w("")
    w("The %d rows below are every one that repeats a token today:" % len(clashes))
    w("")
    w(table(["class", "skill / rune", "repeated"],
            [[key[0], (key[1] + (" / " + key[2] if key[2] else "")),
              ", ".join("`%s` x%d" % (token, n) for token, n in sorted(repeated.items()))]
             for key, repeated, _ in sorted(clashes)]))
    w("")
    w("### A value that is a multiplier of another")
    w("")
    w("`Hammer of the Ancients` is the live example: the base row carries both the")
    w("Fury step (`resource_per_trigger`) and the crit bonus per step")
    w("(`crit_chance_pct`), and `dc_combat.cpp` divides one by the other. Tokens")
    w("keep that readable — `n[3]` and `n[2]` become `{resource_per_trigger}` and")
    w("`{crit_chance_pct}` — but the RELATION stays in C++ where it is today. A")
    w("token is a value, never a formula.")
    w("")
    w("### Ranges")
    w("")
    spans = [v for v in values if v.unit == "range"]
    if spans:
        w("Three green spans hold a range rather than a value:")
        w("")
        w(table(["class", "skill / rune", "span", "sentence"],
                [[v.cls, v.where().split(" ", 1)[1], "`%s`" % v.raw, quote(v, 56)]
                 for v in spans]))
        w("")
        w("Proposal: two tokens, `<role>_min` and `<role>_max` — here")
        w("`damage_min_life` and `damage_max_life` — and the client renders them as")
        w("`{damage_min_life} - {damage_max_life}`. One token never holds two numbers,")
        w("because a values sheet row is one number.")
    else:
        w("None of the values is written as a range.")
    w("")
    w("### A value inside a proper name")
    w("")
    w("None in this corpus. Skill and rune names carry no numbers, so no token ever")
    w("has to sit inside one. The generator should reject a token whose name matches")
    w("a skill or rune name, to keep it that way.")
    w("")
    return out


def report_sheets_and_migration(data, out):
    w = out.append
    w("## d. Sheet shape after the rewrite")
    w("")
    w("`<class>_skills.csv`, `<class>_runes.csv` and `<class>_passives.csv` keep every")
    w("column they have. Only the text column changes: the numbers in it become")
    w("tokens.")
    w("")
    w("```")
    w("barbarian_skills.csv   ... ,full_tooltip_text, ...")
    w("  Frenzy   Generate: {resource_generated} Fury per attack | Swing for")
    w("           {damage_pct} weapon damage. Frenzy's attack speed increases by")
    w("           {attack_speed_pct} for {duration_seconds} seconds with each swing.")
    w("           This effect stacks up to {max_stacks_count} times. | Primary |")
    w("```")
    w("")
    w("One values sheet per class holds the numbers:")
    w("")
    w("```")
    w("barbarian_skill_values.csv")
    w("  skill,rune,token,value,unit,source")
    w("  Frenzy,,resource_generated,4,resource,d3planner skilltips.barbarian.frenzy.x")
    w("  Frenzy,,damage_pct,220,pct,d3planner skilltips.barbarian.frenzy.x")
    w("  Frenzy,Maniac,damage_bonus_pct,2.5,pct,d3planner skilltips.barbarian.frenzy.a")
    w("```")
    w("")
    w("Per class, so a lane owns one file and a lock is one file. Passives use the")
    w("same file with an empty `skill` and the passive in `rune`, or their own")
    w("`<class>_passive_values.csv` if the designer prefers one row shape per sheet.")
    w("")
    w("The generator emits the table keyed by name instead of by position:")
    w("")
    w("```cpp")
    w("struct Row { uint32_t id; char const* skill; char const* rune;")
    w("             std::array<Named,16> n; double radius; };")
    w("double Value(Row const&, char const* token);   // fails loudly if absent")
    w("```")
    w("")
    w("and refuses to generate when a token in the text has no row in the values")
    w("sheet, or a row in the values sheet is named by no text. Both checks are the")
    w("point of the rewrite: a missing or renamed number stops the build instead of")
    w("silently reading the wrong index.")
    w("")

    reads = positional_reads()
    index_map = barbarian_index_map()
    passive_values = {}
    for row in read_csv(D3 / "barbarian_passives.csv"):
        passive_values[row["passive_name"]] = sheet_values(
            "barbarian", "passive", row["passive_name"], "", row["full_text"])
    for read in reads:
        source = (passive_values.get(read["passive"]) if read["passive"]
                  else index_map.get((read["skill"], read["rune"])))
        if source and read["index"] < len(source):
            value = source[read["index"]]
            read["token"] = value.token
            read["value"] = value.raw
            read["sentence"] = quote(value, 60).replace("|", "\\|")
        else:
            read["token"], read["value"], read["sentence"] = "", "", ""

    resolved = [r for r in reads if r["token"]]
    w("## e. Migration checklist — the barbarian's positional reads")
    w("")
    if not reads:
        w("**Done, and the checklist is retired with it.** The spell rewrite")
        w("finished this migration: `dc_ability_data.h` and `dc_passive_data.h`")
        w("no longer exist, no `n[k]` is left in the module, and every number is")
        w("read by name through `dc_spell_values.h` and `Numbers::Num`.")
        w("`test_spell_numbers.py` keeps the inventory of all 194 reads frozen and")
        w("reports how many are still positional; it reports zero. This section")
        w("stays as the record of what the checklist was for, and fills itself in")
        w("again if either generated table ever comes back.")
        w("")
        return
    w("`grep -c 'n\\['` reports 174 lines across five files, which is where the")
    w("number in the brief comes from. Counting the reads themselves gives **%d**:"
      % len(reads))
    w("some lines carry two, one file's hit is not a read at all")
    w("(`dc_stash.cpp:654` is `destination[0]`), and `dc_combat.cpp:803` is a comment.")
    w("They read three generated tables — `AbilityData` (skills and runes),")
    w("`AncientData` (the same table under another namespace) and `PassiveData`.")
    w("")
    w(table(["file", "reads"],
            [[("`%s`" % f), sum(1 for r in reads if r["file"] == f)] for f in SOURCES]))
    w("")
    w("%d of %d resolve to a token from the sheet; the %d that do not are listed"
      % (len(resolved), len(reads), len(reads) - len(resolved)))
    w("under the table. The rewrite is then a rename with a byte-identical generated")
    w("table as its acceptance test: emit the new table, sort both by id and token,")
    w("and the values must match one for one.")
    w("")
    checked, mismatched = verify_mapping()
    w("**The mapping itself is verified, not assumed.** `n[k]` is only the k-th")
    w("number of the sheet cell if this script reads the cell the way")
    w("`generate_spells.py` does, so every row of the two generated tables is")
    w("compared against the numbers read here: %d rows, %d disagreements."
      % (checked, len(mismatched)))
    if mismatched:
        w("")
        w(table(["table", "skill / passive", "rune", "ours", "generated"],
                [list(m) for m in mismatched]))
    w("")
    w("The `sentence` column is the words around that number in the sheet cell, so")
    w("each row can be checked by reading it rather than by trusting the rule.")
    w("")
    rows = [[("`%s`" % r["file"].split("/")[-1]), r["line"], r["expr"].replace("|", "\\|"),
             r["skill"] or r["passive"], r["rune"], r["index"], r["value"],
             ("`{%s}`" % r["token"]) if r["token"] else "**unresolved**",
             r.get("sentence", "")]
            for r in reads]
    w(table(["file", "line", "expression", "skill / passive", "rune", "n[k]", "value",
             "token", "sentence"], rows))
    w("")
    unresolved = [r for r in reads if not r["token"]]
    if unresolved:
        w("Unresolved, needing a human eye in the rewrite task:")
        w("")
        for r in unresolved:
            w("- `%s:%d` `%s` — %s" % (r["file"], r["line"], r["expr"],
                                       "no row anchor in the surrounding code"
                                       if not (r["skill"] or r["passive"])
                                       else "the sheet value at that index has no token yet"))
        w("")
    return out


def report_tail(data, out):
    w = out.append
    w("## f. Numbers that are not parameters")
    w("")
    w("The rule: **a parameter is green. Everything else in the tooltip is not.**")
    w("")
    w(table(["number", "where it lives", "why it is not a token"], [
        ["unlock level", "`<p class=\"subtle\">Unlocked at level <em>26</em></p>`",
         "character progression, already a column (`unlock_level`)"],
        ["icon id", "`skilltips[...].icon`, and the `background-image` url",
         "an asset id"],
        ["skill range", "`skills[<class>][<skill>].range`",
         "a targeting property, not a sentence value"],
        ["rune slot letter", "`skills[...].runes` keys a–e",
         "an index into the rune list"],
        ["flavour text", "`<div class=\"tooltip-extension\">`",
         "quotes and lore; sometimes contains numerals"],
        ["our own separators", "`| Primary |`, `| Tactics |`",
         "the category column repeated in the text"],
    ]))
    w("")
    w("Our sheets already exclude the unlock level the crude way: `generate_spells.py`")
    w("cuts `full_tooltip_text` at the word `Unlocked` before reading numbers. After")
    w("the rewrite the cut is unnecessary — a number is only read if a token names")
    w("it — but the column stays where it is.")
    w("")
    w("## Cross-check: our sheets against the tips")
    w("")
    w("Only two classes have sheets today: `barbarian_*.csv` and `wizard_*.csv`.")
    w("Both are checked twice — once on the NUMBERS, once on the TEXT — and the two")
    w("results are kept apart, because they answer different questions.")
    w("")
    w("### Numbers")
    w("")
    rows = []
    total_rows = 0
    all_problems = []
    for cls in ("barbarian", "wizard"):
        problems = cross_check(data, cls)
        all_problems += [(cls,) + p for p in problems]
        counts = [len(read_csv(D3 / ("%s_skills.csv" % cls))),
                  len(read_csv(D3 / ("%s_runes.csv" % cls))),
                  len(read_csv(D3 / ("%s_passives.csv" % cls)))]
        total_rows += sum(counts)
        rows.append([cls, counts[0], counts[1], counts[2], len(problems)])
    w(table(["class", "skills", "runes", "passives", "mismatches"], rows))
    w("")
    if all_problems:
        w("Mismatches, listed and **not fixed** (this task changes no sheet):")
        w("")
        w(table(["class", "skill", "rune", "what differs", "ours", "d3planner"],
                [list(p) for p in all_problems]))
    else:
        w("**No mismatches.** Every number in all %d rows appears in the matching" % total_rows)
        w("d3planner tip, in the same order, with the same value — the comparison is")
        w("the ordered list of numbers our generator would read against the ordered")
        w("list of green values in the tip. That is what makes the byte-identical")
        w("acceptance test in section e possible.")
    w("")
    w("### Text")
    w("")
    w("The second check compares the sentence itself, normalised on both sides.")
    w("Excluded, deliberately and in both directions: HTML tags, entities and the")
    w("icon span; the unlock line (`<p class=\"subtle\">` in a tip, the trailing")
    w("`| Unlocked at level N.` segment in a sheet cell); the flavour quote (the")
    w("tip's `tooltip-extension` div, anything after the unlock segment in a cell);")
    w("the category line (`<p class=\"special\">` and the `| Primary |` segment,")
    w("which is the `category` column repeated); the tip's empty `Requires` line;")
    w("the sheet's `|` separators; whitespace runs; curly quotes and dashes; and")
    w("letter case. Two more, precisely: a **terminal** full stop is stripped from")
    w("the end of each side, and whitespace directly BEFORE a `.,;:!?` is removed,")
    w("because the tips put a space there after a closing tag and the sheets do")
    w("not. Every other word, number and punctuation mark — including full stops")
    w("inside the text and every comma — is compared as it stands.")
    w("")
    rows, skipped = [], []
    for cls in ("barbarian", "wizard"):
        problems = text_check(data, cls)
        counts = [len(read_csv(D3 / ("%s_skills.csv" % cls))),
                  len(read_csv(D3 / ("%s_runes.csv" % cls))),
                  len(read_csv(D3 / ("%s_passives.csv" % cls)))]
        rows.append([cls, sum(counts), len(problems)])
        skipped += [(cls,) + p for p in problems]
    w(table(["class", "rows compared", "text mismatches"], rows))
    w("")
    if skipped:
        w("Every mismatch, listed and **not fixed**:")
        w("")
        w(table(["class", "skill", "rune", "where they part", "ours", "d3planner"],
                [[cls, nm, rn, first_difference(ours, theirs), ours[:90], theirs[:90]]
                 for cls, nm, rn, ours, theirs in skipped]))
    else:
        w("**No text mismatches either.** Every row's sentence is word for word the")
        w("d3planner tip once the exclusions above are applied, and no row was")
        w("skipped for want of a matching tip — the %d rows in the table are all of" % sum(r[1] for r in rows))
        w("them. Our sheets are a faithful transcription, which is why the numbers")
        w("agree as well.")
    w("")
    w("### Tokens")
    w("")
    w("The third check is the one that matters for the rewrite: it names every")
    w("number twice, once from the raw tip and once from our sheet cell, and")
    w("compares the two token sequences row by row. The numeric check proves the")
    w("two sources hold the same values; this proves the classifier reads them the")
    w("same way from either wording. They are not the same claim — a sheet cell")
    w("separates its sentences with `|` and a tip does not, so a rule that counted")
    w("sentences could name the same number differently on each side, and one did.")
    w("")
    rows, disagreements = [], []
    for cls in ("barbarian", "wizard"):
        count, problems = token_consistency(data, cls)
        rows.append([cls, count, len(problems)])
        disagreements += [(cls,) + p for p in problems]
    w(table(["class", "rows compared", "token disagreements"], rows))
    w("")
    if disagreements:
        w(table(["class", "skill", "rune", "n[k]", "value", "from the tip", "from the sheet"],
                [list(d) for d in disagreements]))
    else:
        w("**No disagreements.** Every number in all %d rows gets the same token from"
          % sum(r[1] for r in rows))
        w("the tip and from the sheet.")
    w("")
    w("This check is new in this revision, and it was written because it was")
    w("needed: run against the previous classifier it reports exactly one")
    w("disagreement — `Boon of Bul-Kathos`, `n[2]`, `cooldown_reduction_seconds`")
    w("from the tip against `duration_seconds` from the sheet. The sentence-count")
    w("fallback reached far enough back through a tip's full stops and not far")
    w("enough through a sheet cell's `|`, so the third of three cooldown")
    w("reductions kept the wrong name on the sheet side, and the checklist row")
    w("`dc_passives.cpp:591` showed it. The fallback is a plain window of words")
    w("now, with `|` treated as whitespace, which is why the two sides agree.")
    w("")
    w("## What this report does not do")
    w("")
    w("No sheet, no C++ and no generator is touched. The rewrite waits for the designer to")
    w("approve the vocabulary; the five other classes have no sheets yet, and their")
    w("counts above are from the reference data alone.")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    data = json.loads(DATA.read_text(encoding="utf-8"))
    out, values, named, states, per_token, tokens, example = report(data)
    report_rest(data, out, values, named, states, per_token, tokens, example)
    report_sheets_and_migration(data, out)
    report_tail(data, out)
    text = "\n".join(out).rstrip() + "\n"
    pathlib.Path(args.out).write_text(text, encoding="utf-8")
    print("%s: %d lines, %d values, %d tokens"
          % (args.out, text.count("\n"), len(values), len(tokens)))


if __name__ == "__main__":
    main()

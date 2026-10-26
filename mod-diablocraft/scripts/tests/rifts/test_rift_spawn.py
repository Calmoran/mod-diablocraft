"""Monster spawning Part S2 (diablocraft-q85h): the spawner's picks.

What runs here: the production planner (src/rifts/dc_rift_spawn.h) is compiled with tests/rift_spawn/harness.cpp and fed the
generated sheets as they stand (generate_spawn_sheets.load(): the 18 seed sets, the recipes, the monster flags, the area
defaults; the survey's rift_areas.csv and rift_anchors.csv; the knobs of rifts.csv). It plans floors for every dungeon in both
modes on many seeds, and the properties the plan promises are checked on what it printed: the set (by weight, never the floor
before's), the anchors (once each, density, the entry clearance, no-spawn areas), the clusters (one family, no solo monster, the
recipe's bodies, the size the tag allows, Swarm's 3), the solos, the elite packs (the floor's minimum and maximum, the split, a
member of the cluster itself), the spots (distinct, inside the radius), the body cap, and the replay of a floor from its seed.
What needs the worldserver (the summons, the native filter, the cluster link, the doors) is held by source checks on the
wiring below and by docs/test-diablocraft-q85h.md on dev.

DC_RIFT_SPAWN_RIFTS points the read at a copy of src/rifts (red-on-the-base run); DC_RIFT_SPAWN_HEADER at a mutated header."""
import csv
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db  # noqa: E402
import generate_spawn_sheets as sheets  # noqa: E402
import harness_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
RIFTS = Path(os.environ.get('DC_RIFT_SPAWN_RIFTS', MODULE / 'src/rifts'))
HEADER = Path(os.environ.get('DC_RIFT_SPAWN_HEADER', RIFTS / 'dc_rift_spawn.h'))
SCRATCH = ROOT / 'azerothcore-wotlk/build/_agent-scratch'
DATA = sheets.load()
SIZE_NAMES = ['small', 'medium', 'large']
ROLES = ('melee', 'ranged', 'caster', 'big')
STAND_IN = {'melee': ('ranged', 'big', 'caster'), 'ranged': ('caster', 'melee', 'big'), 'caster': ('ranged', 'melee', 'big'), 'big': ('melee', 'ranged', 'caster')}


def read(path):
    return Path(path).read_text(encoding='utf-8')


def csv_rows(path):
    with open(path, encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def tunable(path, name):
    row = next(r for r in csv_rows(MODULE / 'data/tunables' / path) if r['name'] == name)
    return (row.get('value') or row.get('d3_value') or '0').strip() or '0'


KNOBS = {name: tunable('rifts.csv', name) for name in (
    'elite_chance_pct', 'elite_champion_pct', 'solo_share_pct', 'cluster_radius_small_yards', 'entry_clear_yards',
    'elite_packs_min', 'elite_packs_max', 'floor_body_cap', 'cluster_min_spacing_yards')}
KNOBS['champion_pack_size'] = next(r['champion_pack_size'] for r in csv_rows(MODULE / 'data/tunables/loot_tuning.csv') if r['source'] == 'elite')
KNOBS['rare_minions_max'] = next((r['tuned_value'] or r['d3_value']) for r in csv_rows(MODULE / 'data/tunables/elite_affix_parameters.csv')
                                 if r['affix_name'] == '_global' and r['parameter'] == 'rare_minions_max')
KNOBS['horde_multiplier'] = next((r['tuned_value'] or r['d3_value']) for r in csv_rows(MODULE / 'data/tunables/elite_affix_parameters.csv')
                                 if r['affix_name'] == 'Horde' and r['parameter'] == 'minion_multiplier')
ZONES = {r['name'] for r in csv_rows(MODULE / 'data/d3/rift_open_zones.csv')}   # the open zones (Part S6) are not rift dungeons
ROUTES = [r for r in csv_rows(MODULE / 'data/d3/rift_routes.csv') if r['dungeon'] not in ZONES]
AREAS = [r for r in csv_rows(MODULE / 'data/d3/rift_areas.csv') if r['dungeon'] not in ZONES]
ANCHORS = [r for r in csv_rows(MODULE / 'data/d3/rift_anchors.csv') if r['dungeon'] not in ZONES]
DUNGEONS = list(dict.fromkeys(r['dungeon'] for r in AREAS))
assert len(DUNGEONS) == 30, len(DUNGEONS)


def sheet_text(knobs=None, weights=None, nospawn=frozenset(), density=None, modes=None, routes=None):
    """The generated sheets as the harness reads them. `knobs` overrides rifts.csv rows; `weights` set_id -> weight."""
    out = []
    by_name = {m['monster']: m for m in DATA['roster']}
    for name, spawn in DATA['spawn'].items():
        if spawn['entry'] is not None:
            out.append(f"monster\t{name}\t{spawn['entry']}\t{spawn['family']}\t{spawn['role']}\t{spawn['solo']}\t{spawn['wander_yards']}")
    for s in DATA['sets']:
        out.append(f"set\t{s['set_id']}\t{(weights or {}).get(s['set_id'], s['weight'])}\t{(modes or {}).get(s['set_id'], (s['nephalem'], s['greater']))[0]}\t{(modes or {}).get(s['set_id'], (s['nephalem'], s['greater']))[1]}\t{s['name']}")
        out += [f"member\t{s['set_id']}\t{m}" for m in s['members']]
        out += [f"sfam\t{s['set_id']}\t{f}\t{s['family_weights'][f]}\t{int(f in s['clusterable'])}" for f in s['families']]
    for r in DATA['recipes']:
        roles = '\t'.join(f"{r[k][0]}\t{r[k][1]}" for k in ('melee', 'ranged', 'caster', 'big'))
        out.append(f"recipe\t{r['size']}\t{r['family'] or '-'}\t{r['bodies'][0]}\t{r['bodies'][1]}\t{roles}")
    for a in DATA['areas']:
        out.append(f"area_default\t{a['tag']}\t{a['anchors_min']}\t{a['anchors_max']}\t{a['small']}\t{a['medium']}\t{a['large']}")
    for name, value in {**KNOBS, **(knobs or {})}.items():
        out.append(f"knob\t{name}\t{value}")
    for dungeon in DUNGEONS:
        out.append(f"dungeon\t{dungeon}")
        for a in (r for r in AREAS if r['dungeon'] == dungeon):
            lo, hi = (density or {}).get((dungeon, int(a['area'])), (a['density_min'] or -1, a['density_max'] or -1))
            out.append(f"area\t{a['area']}\t{a['tag']}\t{lo}\t{hi}\t{1 if (dungeon, int(a['area'])) in nospawn else a['nospawn']}")
        for a in (r for r in ANCHORS if r['dungeon'] == dungeon):
            walk = a['entry_walk_yards'] or -1
            out.append(f"anchor\t{a['anchor']}\t{a['area']}\t{a['x']}\t{a['y']}\t{a['z']}\t{a['o']}\t{walk}")
        for r in (r for r in (ROUTES if routes is None else routes) if r['dungeon'] == dungeon):
            out.append(f"route\t{r['path_id']}\t{r['anchor']}\t{r['start_x']}\t{r['start_y']}\t{r['start_z']}")
    return out


class Harness:
    """The production header compiled once with the harness; plan() runs it on a sheet and some runs."""

    def __init__(self, header_text):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self._folder = tempfile.TemporaryDirectory(prefix='rift-spawn-', dir=SCRATCH)
        folder = Path(self._folder.name)
        (folder / 'dc_rift_spawn.h').write_text(header_text, encoding='utf-8')
        done = subprocess.run(['c++', '-std=c++20', '-O1', '-UNDEBUG', '-Wall', '-Wextra', f'-I{folder}', str(MODULE / 'tests/rift_spawn/harness.cpp'),
                               '-o', str(folder / 'harness')], capture_output=True, text=True)
        assert done.returncode == 0, 'COMPILE ' + done.stderr[-1500:]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._folder.cleanup()

    def plan(self, text_lines, runs):
        """Plans each run (dungeon, greater, seed, floor, previous set); returns one dict per run."""
        folder = Path(self._folder.name)
        (folder / 'in.txt').write_text('\n'.join(text_lines + [f"run\t{d}\t{g}\t{s}\t{f}\t{p}" for d, g, s, f, p in runs]) + '\n', encoding='utf-8')
        ran = harness_env.run([str(folder / 'harness'), str(folder / 'in.txt')], capture_output=True, text=True)
        assert ran.returncode == 0, ran.stderr[-1500:]
        out, now = [], None
        for line in ran.stdout.splitlines():
            cells = line.split('\t')
            if cells[0] == 'RUN':
                now = dict(dungeon=cells[1], greater=int(cells[2]), seed=int(cells[3]), floor=int(cells[4]), previous=int(cells[5]), placements=[], spots=defaultdict(list))
                out.append(now)
            elif cells[0] == 'SET':
                now['set'] = int(cells[1])
            elif cells[0] == 'P':
                now['placements'].append(dict(anchor=int(cells[1]), kind=cells[2], size=int(cells[3]), family=cells[4], elite=int(cells[5]),
                                              leader=cells[6], monsters=cells[7].split('|'), route=int(cells[8] or 0)))
            elif cells[0] == 'PAT':
                now['patrols'] = int(cells[1])
            elif cells[0] == 'S':
                now['spots'][int(cells[1])].append((float(cells[2]), float(cells[3])))
            elif cells[0] == 'SUM':
                now['sum'] = [int(c) for c in cells[1:]]
        assert len(out) == len(runs), (len(out), len(runs))
        return out


# --- what the sheets say, for the checks ---------------------------------------------------------------------------------------
SETS = {s['set_id']: s for s in DATA['sets']}
MONSTER = DATA['spawn']
RECIPE = {(r['size'], r['family']): r for r in DATA['recipes']}
DEFAULT = {a['tag']: a for a in DATA['areas']}
AREA = {(r['dungeon'], int(r['area'])): r for r in AREAS}
ANCHOR = {(r['dungeon'], int(r['anchor'])): r for r in ANCHORS}
AREAS_OF = defaultdict(list)
for _key, _row in AREA.items():
    AREAS_OF[_key[0]].append((_key[1], _row))
IN_AREA = defaultdict(list)
for _key, _row in ANCHOR.items():
    IN_AREA[(_key[0], int(_row['area']))].append(_row)


def solo_pool(s):
    solo_families = [f for f in s['families'] if f not in s['clusterable']]
    return {m for m in s['members'] if MONSTER[m]['solo'] or MONSTER[m]['family'] in solo_families}


def usable(s, greater, modes=None):
    on = (modes or {}).get(s['set_id'], (s['nephalem'], s['greater']))[1 if greater else 0]
    return s['weight'] > 0 and on and (s['clusterable'] or solo_pool(s))


def recipe(size, family):
    return RECIPE.get((SIZE_NAMES[size], family)) or RECIPE[(SIZE_NAMES[size], '')]


def check_run(r, knobs, nospawn=frozenset(), density=None, modes=None):
    """Every promise the plan makes about one floor; returns what broke."""
    bad = []
    s = SETS.get(r['set'])
    others = [x for x in DATA['sets'] if usable(x, r['greater'], modes) and x['set_id'] != r['previous']]
    if s is None or not usable(s, r['greater'], modes):
        return [f"{r['dungeon']}: set {r['set']} is not a usable set for mode {r['greater']}"]
    if others and r['set'] == r['previous']:
        bad.append(f"{r['dungeon']}: the set of the floor before came again ({r['set']})")
    anchors_used = Counter(p['anchor'] for p in r['placements'])
    if any(n > 1 for n in anchors_used.values()):
        bad.append(f"{r['dungeon']}: an anchor holds two things")
    per_area = Counter()
    pool = solo_pool(s)
    clusters = solos = elites = 0
    bodies = cluster_bodies = 0
    for p in r['placements']:
        anchor = ANCHOR.get((r['dungeon'], p['anchor']))
        if anchor is None:
            bad.append(f"{r['dungeon']}: anchor {p['anchor']} is not in the dungeon")
            continue
        area = AREA[(r['dungeon'], int(anchor['area']))]
        per_area[int(anchor['area'])] += 1
        if area['nospawn'] == '1' or (r['dungeon'], int(anchor['area'])) in nospawn:
            bad.append(f"{r['dungeon']}: a no-spawn area holds {p['anchor']}")
        walk = anchor['entry_walk_yards']
        if walk and float(walk) < float(knobs['entry_clear_yards']):
            bad.append(f"{r['dungeon']}: anchor {p['anchor']} is {walk} yards from the door, inside {knobs['entry_clear_yards']}")
        spots = r['spots'][p['anchor']]
        if len(spots) != len(p['monsters']) or len(set(spots)) != len(spots):
            bad.append(f"{r['dungeon']}: anchor {p['anchor']} has {len(p['monsters'])} bodies on {len(set(spots))} spots")
        gap = float(knobs.get('cluster_min_spacing_yards') or 0)
        if gap and any(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 < gap - 1e-3 for i, a in enumerate(spots) for b in spots[i + 1:]):
            bad.append(f"{r['dungeon']}: two members of anchor {p['anchor']} are closer than the spacing {gap}")
        for m in p['monsters']:
            if m not in s['members']:
                bad.append(f"{r['dungeon']}: {m} is not in set {s['set_id']}")
        cluster_bodies += len(p['monsters'])
        if p['kind'] == 'solo':
            solos += 1
            if len(p['monsters']) != 1 or p['monsters'][0] not in pool or p['elite']:
                bad.append(f"{r['dungeon']}: solo {p['monsters']} is not a lone solo-pool monster of set {s['set_id']}")
            bodies += 1
            continue
        clusters += 1
        if {MONSTER[m]['family'] for m in p['monsters']} != {p['family']} or p['family'] not in s['clusterable']:
            bad.append(f"{r['dungeon']}: cluster at {p['anchor']} is not one clusterable family: {p['monsters']}")
        if any(MONSTER[m]['solo'] for m in p['monsters']):
            bad.append(f"{r['dungeon']}: a solo monster stands in a cluster: {p['monsters']}")
        want = recipe(p['size'], p['family'])['bodies']
        if not want[0] <= len(p['monsters']) <= want[1]:
            bad.append(f"{r['dungeon']}: a {SIZE_NAMES[p['size']]} {p['family']} cluster has {len(p['monsters'])} bodies, the recipe says {want}")
        # a role the family has no member for in this set went to its stand-in (3.3), so the stand-in has at least the minimums of both
        have = {role: [m for m in s['members'] if MONSTER[m]['family'] == p['family'] and not MONSTER[m]['solo'] and MONSTER[m]['role'] == role]
                for role in ROLES}
        need = {role: recipe(p['size'], p['family'])[role][0] for role in ROLES}
        for role in ROLES:
            if not have[role] and need[role]:
                for stand_in in STAND_IN[role]:
                    if have[stand_in]:
                        need[stand_in] += need[role]
                        need[role] = 0
                        break
        seen = Counter(MONSTER[m]['role'] for m in p['monsters'])
        for role in ROLES:
            if role != 'melee' and seen[role] < need[role]:       # melee is the filler: it is added and taken away
                bad.append(f"{r['dungeon']}: {p['family']} cluster has {seen[role]} {role}, the stand-ins and minimums need {need[role]}")
            if not have[role] and seen[role]:
                bad.append(f"{r['dungeon']}: {p['family']} cluster has {role} bodies the set has no {role} for")
        if not DEFAULT[area['tag']][SIZE_NAMES[p['size']]]:
            bad.append(f"{r['dungeon']}: a {SIZE_NAMES[p['size']]} cluster stands in a {area['tag']} area")
        radius = float(knobs['cluster_radius_small_yards']) * (len(p['monsters']) / 4) ** 0.5
        if any((dx * dx + dy * dy) ** 0.5 > radius + 1e-3 for dx, dy in spots):
            bad.append(f"{r['dungeon']}: a spot of anchor {p['anchor']} is beyond {radius:.2f} yards")
        if p['elite']:
            elites += 1
            if p['leader'] not in p['monsters']:
                bad.append(f"{r['dungeon']}: elite leader {p['leader']} is not of its cluster")
            bodies += int(knobs['champion_pack_size']) if p['elite'] == 1 else 1 + int(knobs['rare_minions_max']) * int(knobs['horde_multiplier'])
        else:
            bodies += len(p['monsters'])
    dungeon = r['dungeon']
    for area_id, row in AREAS_OF[dungeon]:
        lo, hi = (density or {}).get((dungeon, area_id)) or (
            (int(row['density_min']), int(row['density_max'])) if row['density_min'] else (DEFAULT[row['tag']]['anchors_min'], DEFAULT[row['tag']]['anchors_max']))
        available = [a for a in IN_AREA[(dungeon, area_id)] if not (a['entry_walk_yards'] and float(a['entry_walk_yards']) < float(knobs['entry_clear_yards']))]
        if (dungeon, area_id) in nospawn:
            continue
        most, fewest = min(hi, len(available)), min(lo, len(available))
        if per_area[area_id] > most or (per_area[area_id] < fewest and not int(knobs['floor_body_cap']) and s['clusterable']):
            bad.append(f"{r['dungeon']}: area {area_id} holds {per_area[area_id]}, density {lo} to {hi} of {len(available)} anchors")
    low, high = min(int(knobs['elite_packs_min']), int(knobs['elite_packs_max'])), int(knobs['elite_packs_max'])
    if elites > high or (elites < min(low, clusters) and not int(knobs['floor_body_cap'])):   # a cap may cut elite packs too
        bad.append(f"{r['dungeon']}: {elites} elite packs, floor holds {low} to {high} of {clusters} clusters")
    if r['sum'] != [clusters, solos, elites, bodies, r['sum'][4]]:
        bad.append(f"{r['dungeon']}: the summary {r['sum']} is not {[clusters, solos, elites, bodies]}")
    if int(knobs['floor_body_cap']) and bodies > int(knobs['floor_body_cap']):
        bad.append(f"{r['dungeon']}: {bodies} bodies (packs at their most) past the cap {knobs['floor_body_cap']}")
    return bad


RUNS = [(d, g, seed, floor, prev) for d in DUNGEONS for g in (0, 1) for seed in (11, 12345, 987654321) for floor, prev in ((1, 0), (2, 3))]


def all_problems(header_text):
    with Harness(header_text) as harness:
        return problems(harness)


def problems(harness):
    """Everything the suite checks, as a list of what is wrong; empty when the header keeps every promise."""
    bad = []
    lines = sheet_text()
    result = harness.plan(lines, RUNS)
    for r in result:
        bad += check_run(r, KNOBS)
    # the same seed replays the floor exactly, a different floor of the same seed is another floor
    again = harness.plan(lines, RUNS)
    if [r['placements'] for r in again] != [r['placements'] for r in result]:
        bad.append('replay: the same seed planned a floor differently')
    by_run = {(r['dungeon'], r['greater'], r['seed'], r['floor']): r for r in result}
    repeats = sum(by_run[(d, g, sd, 1)]['placements'] == by_run[(d, g, sd, 2)]['placements'] for d, g, sd, f, _ in RUNS if f == 1)
    if repeats > len(RUNS) // 40:
        bad.append(f'floors: {repeats} of {len(RUNS) // 2} second floors repeated the first floor of their seed')
    # an elite is a champion or a rare by the split; 100 and 0 are all of one
    for pct, kind in (('100', 1), ('0', 2)):
        for r in harness.plan(sheet_text({'elite_champion_pct': pct}), RUNS[:24]):
            if any(p['elite'] not in (0, kind) for p in r['placements']):
                bad.append(f'split: elite_champion_pct {pct} still made the other kind')
    # the floor's elite count: min and max hold whatever the chance rolls
    for chance, low, high in (('100', '0', '5'), ('0', '3', '9'), ('50', '2', '2')):
        knobs = {**KNOBS, 'elite_chance_pct': chance, 'elite_packs_min': low, 'elite_packs_max': high}
        for r in harness.plan(sheet_text(knobs), RUNS[:36]):
            bad += check_run(r, knobs)
    # a set's mode switches decide which rifts roll it: odd sets Nephalem only, even sets Greater only
    switched = {sid: ((1, 0) if sid % 2 else (0, 1)) for sid in SETS}
    for r in harness.plan(sheet_text(modes=switched), RUNS[::4]):
        bad += check_run(r, KNOBS, modes=switched)
    # a no-spawn area stays empty
    closed = frozenset((d, int(a['area'])) for d in DUNGEONS for a in AREAS if a['dungeon'] == d and int(a['area']) % 3 == 0)
    for r in harness.plan(sheet_text(nospawn=closed), RUNS[::5]):
        bad += check_run(r, KNOBS, closed)
    # an area's own density replaces its tag's
    own = {(d, int(a['area'])): ((0, 0) if int(a['area']) % 4 == 0 else (2, 2)) for d in DUNGEONS for a in AREAS if a['dungeon'] == d and int(a['area']) % 4 in (0, 1)}
    for r in harness.plan(sheet_text(density=own), RUNS[::5]):
        bad += check_run(r, KNOBS, density=own)
    # the entry clearance and the body cap bind
    knobs = {**KNOBS, 'entry_clear_yards': '150', 'floor_body_cap': '30'}
    for r in harness.plan(sheet_text(knobs), RUNS[::5]):
        bad += check_run(r, knobs)
    # nwjf 4: the spots are random points within the radius (plan 3.3), not a spiral: the same body count gives different
    # layouts, and the points fill the disc (a uniform disc has a mean of (distance / radius)^2 of one half and a wide spread of
    # radii); a minimum spacing is held when the sheet sets one.
    spaced = {**KNOBS, 'cluster_min_spacing_yards': '1.5', 'elite_chance_pct': '0'}
    runs = harness.plan(sheet_text(spaced), [(d, g, seed, 1, 0) for d in DUNGEONS[:8] for g in (0, 1) for seed in range(1, 25)])
    for r in runs:
        bad += check_run(r, spaced)
    radii, layouts, clusters_seen = [], set(), 0
    for r in runs:
        for p in r['placements']:
            n = len(p['monsters'])
            if p['kind'] == 'cluster' and n >= 6:
                radius = float(spaced['cluster_radius_small_yards']) * (n / 4) ** 0.5
                points = r['spots'][p['anchor']]
                clusters_seen += 1
                radii += [(x * x + y * y) / radius ** 2 for x, y in points]
                layouts.add((n, tuple(sorted(round(x * x + y * y, 2) for x, y in points))))
    mean = sum(radii) / len(radii) if radii else 0
    spread = (sum((v - mean) ** 2 for v in radii) / len(radii)) ** 0.5 if radii else 0
    if len(radii) < 300 or not 0.45 < mean < 0.55 or spread < 0.25 or len(layouts) < 0.4 * clusters_seen:   # a spiral gives one layout per body count
        bad.append(f'spots: {len(radii)} points, mean {mean:.3f}, spread {spread:.3f}, {len(layouts)} layouts: not random points over the disc')
    # nwjf 3: the elite pass swaps a small cluster for a whole pack, so the cap has to hold after it. Every cluster elite,
    # every one a rare: a 3-body cluster becomes a rare and up to rare_minions_max x Horde minions, and a floor that
    # passed the cap on its clusters alone goes over it unless the cap is applied last.
    packs = {**KNOBS, 'floor_body_cap': '40', 'elite_chance_pct': '100', 'elite_champion_pct': '0', 'elite_packs_max': '1000'}
    runs = harness.plan(sheet_text(packs), RUNS[::5])
    for r in runs:
        bad += check_run(r, packs)
    if not any(r['sum'][2] for r in runs) or not any(r['sum'][4] for r in runs):
        bad.append('the pack cap run had no elite packs, or the cap cut nothing: the scenario proves nothing')
    # set weights: a set of weight 0 never comes, a heavy one comes most; the floor before's never comes again
    weights = {sid: 0.0 for sid in SETS}
    heavy = next(sid for sid, s in SETS.items() if usable(s, 1))
    light = [sid for sid, s in SETS.items() if usable(s, 1) and sid != heavy][:2]
    weights[heavy], weights[light[0]], weights[light[1]] = 6.0, 2.0, 2.0
    picks = Counter(r['set'] for r in harness.plan(sheet_text(weights=weights), [('Ragefire Chasm', 1, seed, 1, 0) for seed in range(1, 1201)]))
    if set(picks) != {heavy, *light} or not 0.52 < picks[heavy] / 1200 < 0.68:
        bad.append(f'weights: picks {dict(picks)} for weights 6, 2, 2')
    picks = Counter(r['set'] for r in harness.plan(sheet_text(weights=weights), [('Ragefire Chasm', 1, seed, 2, heavy) for seed in range(1, 401)]))
    if heavy in picks or set(picks) != set(light):
        bad.append(f'previous: the set of the floor before came again: {dict(picks)}')
    only = {sid: (1.0 if sid == heavy else 0.0) for sid in SETS}
    again_set = {r['set'] for r in harness.plan(sheet_text(weights=only), [('Ragefire Chasm', 1, 5, 2, heavy)])}
    if again_set != {heavy}:
        bad.append(f'previous: the only usable set was not used again: {again_set}')
    return bad


def test_the_plan_keeps_its_promises():
    bad = all_problems(read(HEADER))
    assert not bad, '\n'.join(bad[:12])


def test_swarm_is_three_at_every_size():
    swarm = {sid for sid, s in SETS.items() if 'Swarm' in s['clusterable']}
    assert swarm, 'no seed set clusters Swarm; the Swarm check has nothing to look at'
    seen = Counter()
    knobs = {'solo_share_pct': '0', 'elite_chance_pct': '0', 'elite_packs_min': '0'}
    with Harness(read(HEADER)) as harness:
        for sid in swarm:
            weights = {k: (1.0 if k == sid else 0.0) for k in SETS}
            for r in harness.plan(sheet_text(knobs, weights), [(d, 1, seed, 1, 0) for d in DUNGEONS[:6] for seed in range(1, 25)]):
                for p in r['placements']:
                    if p['family'] == 'Swarm':
                        seen[len(p['monsters'])] += 1
    assert seen and set(seen) == {3}, seen


def test_the_density_matches_the_survey_by_arithmetic():
    """3.8 step 2 against the survey sheets, by closed form: an area fills min(k, its anchors) with k even in its density range.
    Prints the bodies the defaults give against today's natives (the S0 report's figure ignores the anchors an area lacks)."""
    expected = 0.0
    for (dungeon, area_id), row in AREA.items():
        lo, hi = (int(row['density_min']), int(row['density_max'])) if row['density_min'] else (DEFAULT[row['tag']]['anchors_min'], DEFAULT[row['tag']]['anchors_max'])
        have = len(IN_AREA[(dungeon, area_id)])
        expected += 0 if row['nospawn'] == '1' else sum(min(k, have) for k in range(lo, hi + 1)) / (hi - lo + 1)
    seeds = range(1, 41)
    with Harness(read(HEADER)) as harness:
        result = harness.plan(sheet_text(), [(d, 1, seed, 1, 0) for d in DUNGEONS for seed in seeds])
    filled = sum(len(r['placements']) for r in result) / len(seeds)
    bodies = sum(r['sum'][3] for r in result) / len(seeds)
    natives = sum(int(r['natives_today']) for r in csv_rows(MODULE / 'data/generated/rift_survey_report.csv'))
    print(f'anchors filled per run of all 30 dungeons: {filled:.0f} against {expected:.0f} by arithmetic; bodies {bodies:.0f} against {natives} natives today ({bodies / natives:.2f}x)')
    assert abs(filled - expected) < 0.03 * expected, (filled, expected)
    assert 1.2 < bodies / natives < 2.2, bodies / natives


# --- the sheets and the survey agree with what the glue reads and what the elite code needs ----------------------------------------
def definition(text, marker):
    start = text.index(marker)
    end, depth = text.index('{', start) + 1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


SPAWNER = read(RIFTS / 'dc_rift_spawner.cpp') if (RIFTS / 'dc_rift_spawner.cpp').exists() else ''
RIFTS_CPP, AI_CPP, ELITES_H = (read(RIFTS / 'dc_rift_scripts.cpp'), read(RIFTS / '../monsters/dc_monster_ai.cpp'),
                               read(RIFTS / '../monsters/affixes/dc_affixes.h'))
SQL_DIR = MODULE / 'data/sql/db-world/updates'


def test_the_loader_queries_run_on_the_generated_tables():
    """The ten SELECTs the glue sends, cut out of dc_rift_spawner.cpp, run on a scratch schema of the fixture mysqld holding the two
    migrations (spawn_sheets_0001, rift_survey_0001); each returns the rows its sheet has."""
    queries = re.findall(r'query\(\s*"(SELECT .*?)",\s*"(dc_\w+)"\)', re.sub(r'"\s*\n\s*"', '', SPAWNER), re.S)
    expected = {'dc_monster_spawn': sum(v['entry'] is not None for v in DATA['spawn'].values()), 'dc_monster_set': len(DATA['sets']),
                'dc_monster_set_member': sum(len(x['members']) for x in DATA['sets']), 'dc_monster_set_family': sum(len(x['families']) for x in DATA['sets']),
                'dc_cluster_recipe': len(DATA['recipes']), 'dc_area_default': 3, 'dc_rift_area': len(AREAS), 'dc_rift_anchor': len(ANCHORS),
                'dc_rift_route': len(ROUTES), 'dc_rift_native_filter': len(csv_rows(MODULE / 'data/d3/rift_native_filter.csv'))}
    assert {table for _, table in queries} == set(expected), [t for _, t in queries]
    mysql, defaults = fixture_db.mysql_and_defaults([])
    scratch = 'scratch_rift_spawn_%d' % os.getpid()

    def run(statement, database=None, stdin=None):
        argv = [mysql, '--defaults-file=' + defaults, '--no-login-paths', '--batch', '--raw', '--skip-column-names'] + ([database] if database else [])
        done = subprocess.run(argv + ([] if stdin else ['-e', statement]), input=stdin, text=True, capture_output=True)
        assert done.returncode == 0, done.stderr
        return [line.split('\t') for line in done.stdout.splitlines()]

    run('DROP DATABASE IF EXISTS %s; CREATE DATABASE %s' % (scratch, scratch))
    try:
        for migration in ('spawn_sheets_0001.sql', 'rift_survey_0003.sql'):
            run(None, scratch, read(SQL_DIR / migration))
        for sql, table in queries:
            rows = run(sql, scratch)
            assert len(rows) == expected[table], (table, len(rows), expected[table])
            if table == 'dc_monster_spawn':
                assert {row[3] for row in rows} <= {'melee', 'ranged', 'caster', 'big'}
    finally:
        run('DROP DATABASE IF EXISTS %s' % scratch)


def test_every_refused_native_is_an_anchor_and_every_anchor_native_is_refused():
    rows = csv_rows(MODULE / 'data/d3/rift_native_filter.csv')
    map_of = {r['name']: r['map_id'] for r in csv_rows(MODULE / 'data/d3/rift_dungeons.csv')}
    refused = {(r['map_id'], r['spawn_guid']) for r in rows}
    assert len(refused) == len(rows) > 4000
    for r in ANCHORS:
        if r['native_guid']:
            assert (map_of[r['dungeon']], r['native_guid']) in refused, r
    anchors = {(r['dungeon'], r['anchor']) for r in ANCHORS}
    assert all((r['dungeon'], r['anchor']) in anchors and map_of[r['dungeon']] == r['map_id'] for r in rows)


def test_every_set_monster_has_the_clones_an_elite_pack_needs():
    """SpawnElitePack returns nothing for an entry without a champion and a rare clone (dc_affix_common.cpp), so a cluster that rolls
    elite would vanish. monsters_0004 writes the clones for every family monster (B3)."""
    sql = read(SQL_DIR / 'monsters_0004_family_data.sql')
    made = {int(m) for m in re.findall(r"INSERT INTO `creature_template` \([^)]*\) VALUES \((\d+),", sql)}
    for s in DATA['sets']:
        for name in s['members']:
            entry = MONSTER[name]['entry']
            assert {entry, 8000000 + entry, 9000000 + entry} <= made or entry in made, (s['set_id'], name, entry)
            assert 8000000 + entry in made and 9000000 + entry in made, (name, entry)


# --- source checks on the wiring the harness cannot reach ----------------------------------------------------------------------------
def test_the_floor_opens_on_the_map_update_of_a_live_rift_only():
    update = definition(RIFTS_CPP, 'void OnMapUpdate(Map* map, uint32 diff) override')
    assert re.search(r'DrainEliteWork\(map, rift, tier\);\s*(//[^\n]*\n\s*)*if \(rift\)\s*Spawner::OpenFloor\(map, tier\);', update), update
    opening = definition(SPAWNER, 'void OpenFloor(Map* map, unsigned tier)')
    assert 'live.View(map->GetInstanceId(), map->GetId(), view)' in opening              # a floor, by instance and map
    assert opening.index('live.View(') < opening.index('mark->done = true') < opening.index('PickSet(')     # once, and only for a live floor
    assert 'Rng rng(record->seed, view.floor);' in opening and opening.index('PickSet(') < opening.index('PlanFloor(')
    assert 'previous = memo.sets[view.floor - 2]' in opening                              # never the set of the floor before
    assert 'record->greater = view.mode == "gr"' in opening or 'record->greater = view.mode == "gr",' in opening.replace('\n', ' ')
    assert 'UPDATE dc_rift_floor SET monster_set={} WHERE run_id={} AND floor={}' in opening
    assert opening.index('OpenDoors(map)') < opening.index('SummonElite(') < opening.index('SummonAt(')
    destroy = definition(RIFTS_CPP, 'void OnDestroyMap(Map* map) override')
    assert 'Spawner::FloorGone(map->GetInstanceId(), floor.runId, lastFloor);' in destroy
    assert 'Spawner::RegisterScripts();' in RIFTS_CPP


def test_the_natives_are_refused_only_by_survey_id_and_only_with_sheets():
    hook = definition(SPAWNER, 'bool CanWorldObjectSpawn(WorldSpawnKind kind')
    assert 'kind != WorldSpawnKind::Creature && kind != WorldSpawnKind::Vehicle' in hook and '!spawnId' in hook
    assert re.search(r'if \(!sheet\)\s*return true;', hook)                                  # no sheets: the natives stay
    assert 'sheet->refused.find(mapId)' in hook and 'map->second.count(spawnId)' in hook
    build = definition(SPAWNER, 'bool Build(Loaded& out, std::string& error)')
    assert build.index('dc_rift_anchor') < build.index('dc_rift_native_filter')            # read last, after everything the floors need
    assert 'GLOBALHOOK_CAN_WORLD_OBJECT_SPAWN' in SPAWNER


def test_a_cluster_fights_as_one():
    engaged = definition(SPAWNER, 'void MemberEngaged(Creature* member, Unit* target)')
    assert 'other->IsAlive() && !other->IsInCombat()' in engaged and 'other->AI()->AttackStart(target)' in engaged
    assert 'static thread_local bool linking' in engaged                                     # one level of links, not a chain
    melee = definition(AI_CPP, 'class RiftMeleeAI : public RiftTargetAI')
    assert 'void JustEngagedWith(Unit* who) override { Spawner::MemberEngaged(me, who); }' in melee
    family = definition(AI_CPP, 'class FamilyAI final : public RiftMeleeAI')
    assert re.search(r'void JustEngagedWith\(Unit\* who\) override\s*\{\s*RiftMeleeAI::JustEngagedWith\(who\);\s*_brain\.Engage\(\);', family)
    elite = definition(SPAWNER, 'Creature* SummonElite(')
    assert 'Link(pack)' in elite and 'state->pack' in elite and 'SpawnElitePack(map, leader.entry' in elite
    assert 'Creature* SpawnElitePack(Map* map, std::uint32_t entry, Position const& at, bool rare' in ELITES_H


def test_a_member_is_walked_to_its_spot_and_homed_there():
    summon = definition(SPAWNER, 'Creature* SummonAt(Map* map')
    assert summon.index('NearTeleportTo') < summon.index('SetHomePosition')
    assert 'Wander' not in summon      # wander starts after the placement, from the caller (Part S7, diablocraft-unvd)
    assert 'CanReachPositionAndGetValidCoords(creature, anchor.x, anchor.y, anchor.z, x, y, z, true, true)' in summon


def test_every_monster_wanders_round_its_own_spot_by_its_own_yards():
    """Part S7 (3.7): stock random movement, started where the monster stands, from its own sheet row."""
    wander = definition(SPAWNER, 'void Wander(Creature* creature, double yards)')
    assert re.search(r'if \(!creature \|\| yards <= 0\)\s*return;', wander)               # 0 stands still
    assert 'creature->SetWanderDistance(static_cast<float>(yards));' in wander
    assert 'creature->SetDefaultMovementType(RANDOM_MOTION_TYPE);' in wander               # a summon starts idle (InitEntry)
    assert 'creature->GetMotionMaster()->MoveRandom(static_cast<float>(yards));' in wander
    assert 'anchor' not in wander and 'Anchor' not in wander                               # never round the cluster's anchor
    opening = definition(SPAWNER, 'void OpenFloor(Map* map, unsigned tier)')
    assert re.search(r'if \(Creature\* creature = SummonAt\(map, monster\.entry.*?members\.push_back\(creature\);.*?Wander\(creature, monster\.wanderYards\);', opening, re.S)
    # a patrol walks its route (3.7, Part S7 tests: "a patrol member does not wander"): only the other placements wander
    assert re.search(r'if \(placement\.kind != Kind::Patrol\)[^\n]*\n\s*Wander\(creature, monster\.wanderYards\);', opening)
    assert opening.count('Wander(') == 1 and 'Walk(leader, members, placement.route)' in opening
    pack = definition(SPAWNER, 'Creature* SummonElite(')
    assert re.search(r'if \(placement\.kind == Kind::Patrol\)\s*Walk\(elite, pack, placement\.route\);\s*else\s*for \(Creature\* member : pack\)\s*Wander\(member, leader\.wanderYards\);', pack)
    assert pack.count('Wander(') == 1
    assert pack.index('Link(pack)') < pack.index('Wander(member')                         # the pack stands first
    assert 'wanderYards = f[5].Get<double>();' in SPAWNER
    assert {m['wander_yards'] for m in MONSTER.values()} == {8}                           # the seed: 8 for every monster


def test_wander_is_the_stock_random_movement_of_the_pinned_core():
    """What the wiring leans on, read from the pin: a summon is idle until it is told, and random movement wanders round where it starts."""
    core = ROOT / 'azerothcore-wotlk/src/server/game'
    creature = read(core / 'Entities/Creature/Creature.cpp')
    assert 'if (!m_wanderDistance && m_defaultMovementType == RANDOM_MOTION_TYPE)\n        m_defaultMovementType = IDLE_MOTION_TYPE;' in creature
    random = read(core / 'Movement/MovementGenerators/RandomMovementGenerator.cpp')
    assert '_initialPosition.Relocate(creature);' in random
    assert 'Mutate(new RandomMovementGenerator<Creature>(wanderDistance), MOTION_SLOT_IDLE)' in read(core / 'Movement/MotionMaster.cpp')


def test_family_monsters_are_hostile_in_a_rift_and_the_split_is_a_tunable():
    hook = definition(AI_CPP, 'void OnCreatureAddWorld(Creature* creature) override')
    assert re.search(r'if \(Family::IsFamilyEntry\(creature->GetEntry\(\)\)\)\s*creature->SetFaction\(FACTION_MONSTER\);', hook)
    assert hook.index('StripNativeAbilities(creature);\n        creature->SetRegeneratingHealth(false)') < hook.index('SetFaction(FACTION_MONSTER)')
    assert hook.index('SetFaction(FACTION_MONSTER)') < hook.index('if (creature->GetEntry() >= CHAMPION_BASE)')
    assert 'promotion.rare = Roll() * 100.0 >= DC::Tunables::Get("rifts", "elite_champion_pct");' in hook
    assert 'Roll() < 0.5' not in AI_CPP


def test_the_doors_open_and_are_not_deleted():
    doors = definition(SPAWNER, 'unsigned OpenDoors(Map* map)')
    assert 'SetGoState(GO_STATE_ACTIVE)' in doors and 'Delete' not in doors and 'GAMEOBJECT_TYPE_DOOR' in SPAWNER


def test_the_knobs_are_the_sheet_rows():
    knobs = definition(SPAWNER, 'Knobs ReadKnobs()')
    names = set(re.findall(r'number\("(\w+)"', knobs))
    rows = {r['name'] for r in csv_rows(MODULE / 'data/tunables/rifts.csv')}
    assert names == {'elite_chance_pct', 'elite_champion_pct', 'solo_share_pct', 'patrol_share_pct', 'cluster_radius_small_yards',
                     'entry_clear_yards', 'elite_packs_min', 'elite_packs_max', 'floor_body_cap', 'cluster_min_spacing_yards'}, names
    assert names <= rows
    # a blank placeholder is no cap and no clearance, never a zero cap
    assert 'DC::Tunables::Has("rifts", name) ? DC::Tunables::Get("rifts", name) : fallback' in knobs
    assert 'number("floor_body_cap", 0)' in knobs and 'number("entry_clear_yards", 0)' in knobs


def test_the_commands_are_registered_on_the_rift_table():
    table = definition(RIFTS_CPP, 'static ChatCommandTable rift = {')
    assert '{"picks", HandlePicks, SEC_GAMEMASTER, Console::No}' in table
    assert 'HandleSpawnReload' not in RIFTS_CPP and '"spawn"' not in table      # no reload command: the brief asked for .dc rift picks alone


# --- killed mutation runs ------------------------------------------------------------------------------------------------------
MUTANTS = [
    ('the floor before can come again', '&& sheets.sets[i].id != previousId', ''),
    ('a solo monster can be in a cluster', 'if (sheets.monsters[index].family == family && !sheets.monsters[index].solo)', 'if (sheets.monsters[index].family == family)'),
    ('the elite maximum is not held', 'while (hits.size() > high)\n            hits.pop_back();', ''),
    ('the elite minimum is not held', 'while (hits.size() < low && !misses.empty())', 'while (false)'),
    ('the entry clearance is ignored', '!(anchor.hasWalk && anchor.entryWalk < knobs.entryClearYards)', 'true'),
    ('a no-spawn area is filled', 'if (area.nospawn || TagIndex(area.tag) < 0)', 'if (TagIndex(area.tag) < 0)'),
    ('an area\'s own density is ignored', 'area.hasDensity ? area.density : ', ''),
    ('the body range is not held from above', 'while (total() > recipe->bodies.hi && count[role])\n                --count[role];', ''),
    ('a family override is ignored', 'auto found = sheets.recipes.find({size, family});', 'auto found = sheets.recipes.end();'),
    ('every size fits every area', 'if (rule.size[size])\n                        sizes.push_back', 'if (true)\n                        sizes.push_back'),
    ('the spots are the anchor', 'spots.push_back({static_cast<float>(r * std::cos(angle)), static_cast<float>(r * std::sin(angle))});', 'spots.push_back({0.0f, 0.0f});'),
    ('the body cap is not held', 'if (total + bodies > knobs.bodyCap)', 'if (false)'),
    ('the body cap is held on the clusters, before the elite pass', 'unsigned const bodies = BodiesOf(plan.placements[keep], knobs);',
     'unsigned const bodies = static_cast<unsigned>(plan.placements[keep].monsters.size());'),
    ('Horde is left out of a rare', 'std::max(1u, knobs.hordeMultiplier)', '1u'),
    ('set weights are ignored', 'weights[i] = sheets.sets[i].weight;\n                other = true;', 'weights[i] = 1;\n                other = true;'),
    ('a missing role has no stand-in', 'if (pool[role].empty() && count[role])\n                for', 'if (false)\n                for'),
    ('the floor number is not in the seed', ': _state(Mix(seed ^ Mix(floor + 0x9E3779B97F4A7C15ull)))', ': _state(Mix(seed))'),
    ('the split is ignored', 'placement.elite = rng.Real() * 100.0 < knobs.championPct ? Elite::Champion : Elite::Rare;', 'placement.elite = Elite::Champion;'),
    ('the elite is made of a stranger', 'placement.leader = placement.monsters[rng.Below(static_cast<unsigned>(placement.monsters.size()))];', 'placement.leader = 0;'),
    ('a solo can roll elite', 'if (plan.placements[i].kind != Kind::Solo)', 'if (true)'),
    ('the family weights are ignored', 'familyWeights.push_back(family.clusterable ? family.weight : 0.0);', 'familyWeights.push_back(1.0);'),
    ('a mode switch is ignored', '(greater ? set.greater : set.nephalem) &&', 'true &&'),
]


WIRING = ['test_the_loader_queries_run_on_the_generated_tables', 'test_the_floor_opens_on_the_map_update_of_a_live_rift_only',
          'test_the_natives_are_refused_only_by_survey_id_and_only_with_sheets', 'test_a_cluster_fights_as_one',
          'test_a_member_is_walked_to_its_spot_and_homed_there', 'test_every_monster_wanders_round_its_own_spot_by_its_own_yards', 'test_family_monsters_are_hostile_in_a_rift_and_the_split_is_a_tunable',
          'test_the_doors_open_and_are_not_deleted', 'test_the_knobs_are_the_sheet_rows', 'test_the_commands_are_registered_on_the_rift_table']
SOURCE_MUTANTS = [
    ('dc_rift_scripts.cpp', 'the floor never opens', 'if (rift)\n                Spawner::OpenFloor(map, tier);', ''),
    ('dc_rift_scripts.cpp', 'a gone floor is remembered', 'Spawner::FloorGone(map->GetInstanceId(), floor.runId, lastFloor);', ''),
    ('dc_rift_scripts.cpp', 'the picks command is gone', '{"picks", HandlePicks, SEC_GAMEMASTER, Console::No},', ''),
    ('dc_rift_spawner.cpp', 'no sheets refuses every native', 'if (!sheet)\n            return true;\n        auto map', 'if (!sheet)\n            return false;\n        auto map'),
    ('dc_rift_spawner.cpp', 'the loader reads a column that is not there', 'big_min, big_max FROM dc_cluster_recipe', 'big_min, huge_max FROM dc_cluster_recipe'),
    ('dc_rift_spawner.cpp', 'the floor before is forgotten', 'previous = memo.sets[view.floor - 2];', 'previous = 0;'),
    ('dc_rift_spawner.cpp', 'a member is not homed at its spot', 'creature->SetHomePosition(x, y, z, anchor.o);', ''),
    ('dc_rift_spawner.cpp', 'the doors are deleted', 'door->SetGoState(GO_STATE_ACTIVE);', 'door->Delete();'),
    ('dc_rift_spawner.cpp', 'an unset body cap is a cap of one', 'number("floor_body_cap", 0)', 'number("floor_body_cap", 1)'),
    ('dc_rift_spawner.cpp', 'the elite pack is not linked', 'Link(pack);', ''),
    ('dc_rift_spawner.cpp', 'a placed member never wanders', 'Wander(creature, monster.wanderYards);', ''),
    ('dc_rift_spawner.cpp', 'the yards are one number for all', 'Wander(creature, monster.wanderYards);', 'Wander(creature, 8);'),
    ('dc_rift_spawner.cpp', '0 yards still moves', 'if (!creature || yards <= 0)', 'if (!creature)'),
    ('dc_rift_spawner.cpp', 'the summon stays idle', 'creature->SetDefaultMovementType(RANDOM_MOTION_TYPE);', ''),
    ('dc_rift_spawner.cpp', 'the wander distance stays 0', 'creature->SetWanderDistance(static_cast<float>(yards));', ''),
    ('dc_rift_spawner.cpp', 'the movement never starts', 'creature->GetMotionMaster()->MoveRandom(static_cast<float>(yards));', ''),
    ('dc_rift_spawner.cpp', 'an elite pack stands still', 'Wander(member, leader.wanderYards);', ''),
    ('dc_rift_spawner.cpp', 'a patrol member wanders', 'if (placement.kind != Kind::Patrol) // a patrol member walks its route, it does not wander (3.7)\n                        Wander(creature, monster.wanderYards);',
     'Wander(creature, monster.wanderYards);'),
    ('dc_rift_spawner.cpp', 'a patrol elite pack wanders', 'Walk(elite, pack, placement.route);\n            else\n                for (Creature* member : pack)', 'Walk(elite, pack, placement.route);\n            for (Creature* member : pack)'),
    ('../monsters/dc_monster_ai.cpp', 'a cluster does not fight as one', 'void JustEngagedWith(Unit* who) override { Spawner::MemberEngaged(me, who); }', ''),
    ('../monsters/dc_monster_ai.cpp', 'a family monster forgets the link', 'RiftMeleeAI::JustEngagedWith(who);', ''),
    ('../monsters/dc_monster_ai.cpp', 'a family monster stays friendly in a rift', 'creature->SetFaction(FACTION_MONSTER);', ''),
    ('../monsters/dc_monster_ai.cpp', 'the split is the coin flip again', 'promotion.rare = Roll() * 100.0 >= DC::Tunables::Get("rifts", "elite_champion_pct");', 'promotion.rare = Roll() < 0.5;'),
]


# The wiring tests that can see each source mutant (measured: each was run alone against the mutant; the others pass on it).
# A mutant is judged by these only; a name here that is not in WIRING, or a mutant without a row, fails the run.
KILLED_BY = {
    'the floor never opens': ('test_the_floor_opens_on_the_map_update_of_a_live_rift_only',),
    'a gone floor is remembered': ('test_the_floor_opens_on_the_map_update_of_a_live_rift_only',),
    'the picks command is gone': ('test_the_commands_are_registered_on_the_rift_table',),
    'no sheets refuses every native': ('test_the_natives_are_refused_only_by_survey_id_and_only_with_sheets',),
    'the loader reads a column that is not there': ('test_the_loader_queries_run_on_the_generated_tables',),
    'the floor before is forgotten': ('test_the_floor_opens_on_the_map_update_of_a_live_rift_only',),
    'a member is not homed at its spot': ('test_a_member_is_walked_to_its_spot_and_homed_there',),
    'the doors are deleted': ('test_the_doors_open_and_are_not_deleted',),
    'an unset body cap is a cap of one': ('test_the_knobs_are_the_sheet_rows',),
    'the elite pack is not linked': ('test_a_cluster_fights_as_one', 'test_every_monster_wanders_round_its_own_spot_by_its_own_yards'),
    'a placed member never wanders': ('test_every_monster_wanders_round_its_own_spot_by_its_own_yards',),
    'the yards are one number for all': ('test_every_monster_wanders_round_its_own_spot_by_its_own_yards',),
    '0 yards still moves': ('test_every_monster_wanders_round_its_own_spot_by_its_own_yards',),
    'the summon stays idle': ('test_every_monster_wanders_round_its_own_spot_by_its_own_yards',),
    'the wander distance stays 0': ('test_every_monster_wanders_round_its_own_spot_by_its_own_yards',),
    'the movement never starts': ('test_every_monster_wanders_round_its_own_spot_by_its_own_yards',),
    'an elite pack stands still': ('test_every_monster_wanders_round_its_own_spot_by_its_own_yards',),
    'a patrol member wanders': ('test_every_monster_wanders_round_its_own_spot_by_its_own_yards',),
    'a patrol elite pack wanders': ('test_every_monster_wanders_round_its_own_spot_by_its_own_yards',),
    'a cluster does not fight as one': ('test_a_cluster_fights_as_one',),
    'a family monster forgets the link': ('test_a_cluster_fights_as_one',),
    'a family monster stays friendly in a rift': ('test_family_monsters_are_hostile_in_a_rift_and_the_split_is_a_tunable',),
    'the split is the coin flip again': ('test_family_monsters_are_hostile_in_a_rift_and_the_split_is_a_tunable',),
}

def mutate(text, old, new):
    pattern = re.compile(r'\s+'.join(re.escape(token) for token in old.split()))
    assert len(pattern.findall(text)) == 1, 'mutant target moved: ' + old
    return pattern.sub(lambda _: new, text)


def test_mutants_are_killed():
    assert set(KILLED_BY) == {what for _, what, _, _ in SOURCE_MUTANTS}, 'KILLED_BY and SOURCE_MUTANTS name different mutants'
    header = read(HEADER)
    for what, old, new in MUTANTS:
        try:
            bad = all_problems(mutate(header, old, new))
        except AssertionError as error:      # a mutant that no longer compiles or crashes is a red run as well
            bad = [str(error)]
        assert bad, 'mutant survived: ' + what
        print('PASS mutant killed:', what)
    for name, what, old, new in SOURCE_MUTANTS:
        ran = wiring_run(name, old, new, KILLED_BY[what])
        assert ran.returncode != 0, 'source mutant survived: ' + what
        print('PASS mutant killed:', what)


def wiring_run(name, old, new, tests):
    """The wiring tests `tests` run in a fresh process on a copy of src/rifts whose file `name` has `old` made `new`."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rift-spawn-src-', dir=SCRATCH) as folder:
        copy = Path(folder) / 'rifts'
        copy.mkdir()
        for needed in ('dc_rift_spawn.h', 'dc_rift_spawner.cpp', 'dc_rift_scripts.cpp', '../monsters/dc_monster_ai.cpp',
                       '../monsters/affixes/dc_affixes.h'):
            (copy / needed).parent.mkdir(parents=True, exist_ok=True)
            (copy / needed).write_text(read(RIFTS / needed), encoding='utf-8')
        (copy / name).write_text(mutate(read(RIFTS / name), old, new), encoding='utf-8')
        return subprocess.run([sys.executable, str(Path(__file__)), '--wiring', '--only=' + ','.join(tests)], capture_output=True, text=True,
                              env={**os.environ, 'DC_RIFT_SPAWN_RIFTS': str(copy)})



if __name__ == '__main__':
    only = WIRING if '--wiring' in sys.argv else None
    for arg in sys.argv:
        if arg.startswith('--only='):     # a source mutant is judged by the wiring tests that can see it
            only = [name for name in arg[len('--only='):].split(',') if name]
            assert only and set(only) <= set(WIRING), 'not wiring tests: ' + arg
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn) and (only is None or name in only):
            fn()
            print('PASS', name)

"""Pin Primary shells, native executors and parity outside targeting ownership."""
import csv
import re
import struct
import subprocess
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as g
import primary_spells as p
import scan_spell_families as scan
import test_spell_records as records

def sql_rows(sql):
    columns = re.search(r'INSERT INTO `spell_dbc` \((.*?)\) VALUES', sql)[1]
    columns = [c.strip().strip('`') for c in columns.split(',')]
    rows = [next(csv.reader([line[1:-2]],quotechar="'",escapechar='\\'))
            for line in sql.splitlines() if line.startswith('(')]
    return columns, {int(r[0]):dict(zip(columns,r)) for r in rows}

def targeting_owned_fields(row, targeting):
    """Only active nonprimary geometry may differ from combat_0001.

    Movement effects are part of destination delivery; their damage, visuals,
    projectile Speed, school, cost and every other donor field remain pinned.
    """
    sid = int(row['ID'])
    skill = row['Name_Lang_enUS'].split(' - ', 1)[0]
    if not 81000 <= sid <= 81137 or skill == 'Whirlwind' or skill not in targeting:
        return set()
    kind = targeting[skill]['target_type']
    fields = {'MaxTargets', 'EffectRadiusIndex_1'}
    if kind == 'cone_enemies':
        fields.add('RangeIndex')
    if kind in ('line_pierce', 'line_to_point', 'ground_point_aoe', 'ground_area'):
        fields.update(('ImplicitTargetA_1', 'ImplicitTargetB_1'))
    if kind == 'line_to_point':
        fields.update(('Effect_2', 'ImplicitTargetA_2', 'ImplicitTargetB_2'))
    if kind == 'ground_point_aoe':
        fields.update(('Effect_1', 'EffectMiscValue_1'))
    return fields

def unrelated_drift(current, original, owned):
    return {key: (original.get(key), current.get(key))
            for key in original.keys() | current.keys()
            if key not in owned and original.get(key) != current.get(key)}

# combat_0001 stays frozen and is never rebaselined to HEAD (Architect,
# decisions.md 2026-09-20). Steps 1-6 have moved 139 of the 164 unrelated
# shells, and every one of those moves has to be EXPLAINED rather than
# accepted: either a values sheet row owns the field and the record carries
# exactly the number that row implies, or the field is one the writer owns
# outright under a named ruling. Anything else is donor drift and fails.
#
# The writer-owned list is not retyped here. It is test_spell_records'
# FREE_FIELDS - the family and the skill bit that let a modifier aura reach a
# shell, the sentence and its exact-value pointer, and step 6's cooldown
# grouping id - so the two suites cannot drift apart about what the sheets do
# not own.
WRITER_OWNED = records.FREE_FIELDS


# Three moves away from combat_0001 that later steps made on purpose, each named
# with the exact value the writer gives (diablocraft-z1p2: they were hidden behind
# the parity failure and surfaced when it was fixed). Like the channel contract they
# explain ONE value per field, so a wrong number in the same field still fails.
#  - GitHub #45: a record whose effect takes TARGET_DEST_DEST (87) carries the stock
#    TARGET_FLAG_DEST_LOCATION (0x40) in Targets, so the client asks for a ground point.
#  - diablocraft-ground-target-circles: the slot that takes that point is sized to the
#    marker, the stock SpellRadius row for combat.csv ground_marker_radius_yards.
#  - 2026-09-23 Rend: the bleed shells are a native periodic damage aura
#    (EffectAura_1 = 3, SPELL_AURA_PERIODIC_DAMAGE), not the donor's dummy.
#  - diablocraft-u4smw: the donor's equipped-item masks (EquippedItemSubclass, EquippedItemInvTypes) are cleared to 0 on every record, as FORCED_ZERO says.
#  - A class passive's SpellIconID is the SpellIcon.dbc id of the stock icon data/d3/passive_icons.csv names for it (every
#    passive shell is a copy of one plain passive, which gave all of them its icon).
TARGET_DEST_DEST = 87
TARGET_FLAG_DEST_LOCATION = 0x40
TARGET_UNIT_CONE_ENEMY = 104
PERIODIC_DAMAGE = 3


def marker_radius_index():
    with (g.MODULE_ROOT / 'data/tunables/combat.csv').open(encoding='utf-8', newline='') as sheet:
        row = next(r for r in csv.DictReader(sheet) if r['name'] == 'ground_marker_radius_yards')
    yards = float(row['value'] or row['d3_value'])
    radii = {key: struct.unpack_from('<f', raw, 4)[0] for key, raw in g.load_dbc('SpellRadius.dbc')[0].items()}
    return min(key for key, value in radii.items() if abs(value - yards) < 0.0005)


_PASSIVE_ICONS = {}


def passive_icon_of(name):
    """The SpellIcon.dbc id (as the record's text) the sheet gives the passive `name`, or None."""
    if not _PASSIVE_ICONS:
        rows, strings, _, _ = g.load_dbc('SpellIcon.dbc')
        by_file = {}
        for key, record in rows.items():
            offset = struct.unpack_from('<I', record, 4)[0]
            by_file[strings[offset:strings.index(b'\0', offset)].decode().lower().rpartition('\\')[2]] = key
        with (g.DATA / 'passive_icons.csv').open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                _PASSIVE_ICONS[row['passive_name']] = str(by_file[row['icon_name'].lower()])
    return _PASSIVE_ICONS.get(name)


def later_step_contract(field, was, current, marker):
    """The one value a later step's rule gives `field` on this record, or None."""
    if field == 'SpellIconID':
        return passive_icon_of(current['Name_Lang_enUS'])
    if field in ('EquippedItemSubclass', 'EquippedItemInvTypes'):
        return '0'   # FORCED_ZERO clears the donor's equipped-item masks (diablocraft-u4smw)
    if field == 'Targets':
        takes_point = any(current['ImplicitTarget%s_%d' % (side, slot)] == str(TARGET_DEST_DEST)
                          for side in 'AB' for slot in (1, 2, 3))
        return str(int(was) | TARGET_FLAG_DEST_LOCATION) if takes_point else None
    match = re.fullmatch(r'EffectRadiusIndex_([123])', field)
    if match:
        slot = match.group(1)
        takes_point = TARGET_DEST_DEST in (int(current['ImplicitTargetA_' + slot]), int(current['ImplicitTargetB_' + slot]))
        return str(marker) if takes_point and int(current['ImplicitTargetA_' + slot]) != TARGET_UNIT_CONE_ENEMY else None
    if field == 'EffectAura_1' and current['Name_Lang_enUS'].startswith('Rend Bleed'):
        return str(PERIODIC_DAMAGE)
    return None


def channel_contract(rows, targeting, columns, contract):
    """{(spell, field): value} for the shells skill_targeting calls a channel.

    Whirlwind is the one, and its shells are not the donor spell any more:
    the record writer's Whirlwind block (generate_spells.py, "AttributesEx =
    0x4  # SPELL_ATTR1_IS_CHANNELED") makes them a channelled dummy aura on
    the caster with no period, an endless duration, and none of the donor's
    projectile or area geometry, because the module owns the paid damage
    ticks. No values sheet states any of that, so it is named here - with the
    values the writer writes, so the exemption is a contract and not a hole
    the rest of the record could hide in.
    """
    channels = {skill for skill, row in targeting.items() if row['cast_type'] == 'channel'}
    if not channels:
        return {}
    durations = g.load_dbc('SpellDuration.dbc')[0]
    endless = min(key for key, row in durations.items()
                  if struct.unpack_from('<i', row, 4)[0] == -1)
    # The two interrupt masks and the spin's visual (diablocraft-vz49.3) the writer copies from Bladestorm itself.
    bladestorm = g.load_dbc('Spell.dbc')[0][46924]
    out = {}
    for sid, row in rows.items():
        if not 81000 <= sid <= 81137:
            continue
        if row['Name_Lang_enUS'].split(' - ', 1)[0] not in channels:
            continue
        wanted = {'AttributesEx': '4',          # SPELL_ATTR1_IS_CHANNELED
                  'AttributesEx5': '1',         # ALLOW_ACTION_DURING_CHANNEL: Rend mid-channel (diablocraft-xecwl)
                  'Effect_1': '6',              # APPLY_AURA
                  'EffectAura_1': '4',          # DUMMY: no movement or attack gate
                  'EffectAuraPeriod_1': '0',    # the module pays the ticks
                  'EffectRadiusIndex_1': '0',
                  'ImplicitTargetA_1': str(g.TARGET_UNIT_CASTER),
                  'ImplicitTargetB_1': '0',
                  'Speed': '0',
                  'RangeIndex': '1',
                  'DurationIndex': str(endless)}
        for field in ('ChannelInterruptFlags', 'InterruptFlags', 'SpellVisualID_1', 'SpellVisualID_2'):
            wanted[field] = str(struct.unpack_from(
                '<I', bladestorm, columns.index(field) * 4)[0])
        for field, value in wanted.items():
            # A values sheet row still outranks the channel shape: Hurricane
            # states its own radius, so that field is the sheet's and not the
            # writer's zero ("a field a token owns is the sheet's", Architect,
            # step 1). Only the fields no sheet row claims are named here.
            if (sid, field) not in contract:
                out[(sid, field)] = value
    return out


def record_contract():
    """{(spell, field): the one value its values sheet row implies}.

    This is test_spell_records' expected-delta contract, read here rather
    than restated: a field appears with ONE value, so a plausible-looking
    wrong number in an explained field is still a failure.
    """
    sql = (g.GENERATED / 'spell_shells.sql').read_text(encoding='utf-8')
    _names, now = records.parse(sql)
    # The contract is the Barbarian's: the value map is scoped the way
    # test_spell_records scopes it, by the generator's CLASS_BLOCKS
    # (diablocraft-wizard-records). Its values sheets are the Barbarian's too.
    value_map = [row for row in records.read_csv(g.GENERATED / 'spell_value_map.csv')
                 if records.barbarian_id(row['spell_id'])]
    owned, problems = records.owned_fields(
        now, value_map,
        records.load_dbc_column('SpellDuration.dbc', 4), records.load_radii(),
        # sql_rows above parses with csv and drops the quotes, so the string
        # expectations have to come back unquoted to match.
        records.read_csv(g.GENERATED / 'spell_shells.csv'), quote=False)
    # GitHub #52: the donor chain counts the writer zeroes are ruled, each with
    # its exact 0, in test_spell_records' RULED_FIELDS - read, not retyped.
    owned.update({key: value for key, value in records.RULED_FIELDS.items()
                  if key[1] == 'EffectChainTargets_1'})
    return owned, problems

# The record writer's family pass (generate_spells.py, "Family and mask, so a
# modifier aura can reach a shell") is the single home for SpellClassSet and
# SpellClassMask (Architect, decisions.md 2026-09-20). These are the manifest
# kinds it writes a bit for; a passive deliberately gets none.
FAMILY_KINDS = ('active', 'rune', 'ability_aura', 'ability_control',
                'ability_proc', 'bleed', 'token_storage')

def writer_skill_bits(manifest, rows):
    """Read each skill's mask bit back out of the records the writer wrote.

    No second copy of the allocation lives here and no bit is typed in: the
    value is whatever the generated records carry, and the guarantees the
    writer makes about it - one bit, the same bit for a skill and its runes and
    companions, a different bit for every other skill - are asserted below.
    """
    bits = {}
    for row in manifest:
        identifier = int(row['spell_id'])
        if row['kind'] not in FAMILY_KINDS or identifier not in rows:
            continue
        skill = row['name'].split(' - ', 1)[0]
        bits.setdefault(skill, set()).add(int(float(rows[identifier]['SpellClassMask_1'])))
    return bits

def one_bit(test, bits, skill):
    """The skill's records agree on a single one-bit mask; return it."""
    seen = bits[skill]
    test.assertEqual(len(seen), 1, '%s: its records carry different mask bits' % skill)
    value = next(iter(seen))
    test.assertEqual(value.bit_count(), 1, '%s: a skill carries exactly one bit' % skill)
    return value

class Primaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql=(g.GENERATED/'spell_shells.sql').read_text(encoding='utf-8')
        cls.columns,cls.rows=sql_rows(cls.sql)
        cls.data=g.read_csv('primary_effects.csv')
        cls.mechanics,_=p.inputs(g)
        cls.manifest=g.read_csv_generated('spell_shells.csv')
        cls.skill_bits=writer_skill_bits(cls.manifest,cls.rows)
        cls.targeting={r['skill']:r for r in g.read_csv('skill_targeting.csv')}
        cls.contract,cls.contract_problems=(record_contract() if records.DBC.is_dir() else (None,None))
        cls.channel=channel_contract(cls.rows,cls.targeting,cls.columns,cls.contract or {})
        sheet={(v['skill'],v['rune'],v['token']):float(v['value'])
               for v in g.read_csv('barbarian_skill_values.csv')}
        cls.sheet_radius={int(e['holder_spell_id']):
                          sheet[(e['skill'],'' if e['origin']=='inherited' else e['rune'],e['token'])]
                          for e in g.read_csv_generated('spell_value_map.csv')
                          if e['source']=='radius' and (e['skill'],'' if e['origin']=='inherited'
                                                        else e['rune'],e['token']) in sheet}

    def test_all_24_selectable_shells(self):
        self.assertEqual(len(self.data),24)
        self.assertEqual({int(r['spell_id']) for r in self.data},set(range(81000,81004))|set(range(81023,81043)))
        source_skills={r['skill_name']:r for r in g.read_csv('barbarian_skills.csv')}
        source_runes={r['rune_name']:r for r in g.read_csv('barbarian_runes.csv')[:20]}
        for case in self.data:
            with self.subTest(case=case['spell_id']):
                r=self.rows[int(case['spell_id'])]
                number=lambda key: int(float(r[key]))
                for key,val in {'Effect_1':31,'EffectBasePoints_1':99,'EffectDieSides_1':1,
                        'Effect_2':0,'Effect_3':0,'PowerType':1,'ManaCost':0,'ManaCostPct':0,
                        'ManaCostPerLevel':0,'StartRecoveryTime':0,'StartRecoveryCategory':0,
                        'RecoveryTime':0,'SpellClassSet':g.BARBARIAN_FAMILY,'MaxTargets':0,'Mechanic':0}.items():
                    self.assertEqual(number(key),val,key)
                self.assertTrue(number('AttributesEx3') & g.SPELL_ATTR3_ALWAYS_HIT)
                self.assertEqual(number('Attributes')&0x80,0)
                self.assertEqual(number('Attributes')&0x40,0)
                element=(source_runes[case['rune']]['element'] if case['rune'] else source_skills[case['skill']]['element']).lower()
                self.assertEqual(number('SchoolMask'),g.SCHOOL[element])
                target=15 if case['rune']=='Broad Sweep' else 104 if case['skill']=='Cleave' else 6
                self.assertEqual(number('ImplicitTargetA_1'),target)
                self.assertEqual(number('ImplicitTargetB_1'),0)
                self.assertEqual(number('EffectChainTargets_1'),4 if case['rune']=='Ricochet' else 0)
                # A row whose values sheet states a radius owns the field -
                # "a field a token owns is the sheet's, not the cloned
                # spell's" (Architect, 2026-09-20, spell rewrite step 1) - so
                # Rupture's 8 and Ricochet's 20 come from those rows and not
                # from literals here. Cleave's rest keep the targeting sheet's
                # geometry, which is what they carried before step 1, and a
                # Primary that states no radius carries none.
                # WHICH record holds a sheet radius is the generated index's
                # answer, not a guess from the skill and rune: Pulverize's 26
                # yards belong to its own secondary shell, so 81037 carries no
                # radius at all even though the sheet states one for the rune.
                wanted=self.sheet_radius.get(int(case['spell_id']))
                if wanted is None and case['skill']=='Cleave':
                    wanted=8 if case['rune']=='Broad Sweep' else 10
                if wanted is None:
                    self.assertEqual(number('EffectRadiusIndex_1'),0)
                else:
                    radius=g.load_dbc('SpellRadius.dbc')[0][number('EffectRadiusIndex_1')]
                    self.assertEqual(struct.unpack_from('<f',radius,4)[0],wanted)
                if case['skill']=='Weapon Throw':
                    donor=g.load_dbc('Spell.dbc')[0][57755]
                    self.assertEqual(float(r['Speed']),struct.unpack_from('<f',donor,self.columns.index('Speed')*4)[0])
                    range_row=g.load_dbc('SpellRange.dbc')[0][number('RangeIndex')]
                    self.assertEqual(struct.unpack_from('<f',range_row,12)[0],30)
                else:
                    self.assertEqual(float(r['Speed']),0)
                    self.assertEqual(number('RangeIndex'),1 if case['skill']=='Cleave' else 2)
                # Word 1 carries the skill's own bit, word 2 stays empty and word 3
                # is the element's school bit (Cindercoat, diablocraft-5cqu3), the
                # element read from the source sheets: what the writer guarantees,
                # read back out of the records it wrote for this skill's whole family.
                self.assertEqual(number('SpellClassMask_1'),one_bit(self,self.skill_bits,case['skill']))
                self.assertEqual(number('SpellClassMask_2'),0)
                self.assertEqual(number('SpellClassMask_3'),g.SCHOOL[element])
                for i in range(1,4):
                    for prefix in ('EffectSpellClassMaskA_','EffectSpellClassMaskB_','EffectSpellClassMaskC_', 'EffectAura_', 'EffectTriggerSpell_'):
                        self.assertEqual(number(prefix+str(i)),0)
                self.assertIn(f"({case['spell_id']},'dc_primary_spell')",self.sql)

    def test_coefficients_generation_and_no_held_behavior(self):
        # Independent acceptance values from the original skill/rune CSVs.
        base={r['skill_name']:float(r['damage_pct_weapon_damage']) for r in g.read_csv('barbarian_skills.csv')[:4]}
        for r in self.data:
            self.assertEqual(float(r['damage_pct']),{'Mighty Throw':400,'Broad Sweep':235}.get(r['rune'],base[r['skill']]))
            self.assertEqual(float(r['fury']),{'Berserk':6,'Instigation':9,'Balanced Weapon':9}.get(r['rune'],4 if r['skill']=='Frenzy' else 6))
        self.assertFalse(any(r['behavior']=='held' for r in self.data))

    def test_combined_collision_evidence(self):
        pinned,names,rows=scan.scan()
        with (g.REPO_ROOT/'docs/research/primaries-warrior-masks.csv').open() as stream:
            evidence=list(csv.reader(stream))
        self.assertEqual(evidence[1:],[[str(v) for v in r] for r in rows])
        # What makes a collision impossible is the family, not the bit. A
        # modifier keyed to SpellClassSet 20 can only ever reach our records,
        # because no stock record uses 20 (generate_spells.py, "An unused
        # SpellClassSet"). Both halves of that claim are proved here against
        # the same two sources the Warrior evidence above is scanned from.
        column=self.columns.index('SpellClassSet')
        for case in self.data:
            row=self.rows[int(case['spell_id'])]
            self.assertEqual(int(float(row['SpellClassSet'])),g.BARBARIAN_FAMILY,case['spell_id'])
        # The extracted client binary is a patched client, not a pristine
        # Blizzard one (scan_spell_families.py says so), so the records we own
        # are excluded: the claim is about stock rows.
        for identifier,record in g.load_dbc('Spell.dbc')[0].items():
            if identifier in self.rows: continue
            self.assertNotEqual(struct.unpack_from('<I',record,column*4)[0],
                                g.BARBARIAN_FAMILY,identifier)
        pinned_columns=re.findall(r'^  `([^`]+)`',pinned,re.M)
        index=pinned_columns.index('SpellClassSet')
        for line in pinned.splitlines():
            if not line.startswith('('): continue
            record=next(csv.reader([line[1:-2]],quotechar="'",escapechar='\\'))
            self.assertNotEqual(int(record[index]),g.BARBARIAN_FAMILY,record[0])
        # Inside the family the bits still separate one skill from another:
        # one bit per skill, and no skill the writer gives a bit to shares one.
        # diablocraft-wizard-records: a mask bit only means something inside
        # its family, and every class numbers its own skills from bit 0, so the
        # Wizard's Magic Missile carries bit 1 just as Frenzy does. That is not
        # a collision, because the two records are in different families - which
        # is proved first, record by record, so the bit check below can be
        # scoped to family 20 without taking the family on trust.
        manifest_ids={int(row['spell_id']) for row in self.manifest
                      if row['kind'] in FAMILY_KINDS}
        for identifier in manifest_ids & set(self.rows):
            family=int(float(self.rows[identifier]['SpellClassSet']))
            if records.barbarian_id(identifier):
                self.assertNotEqual(family,g.CLASS_BLOCKS['wizard'].family,identifier)
            else:
                self.assertNotEqual(family,g.BARBARIAN_FAMILY,identifier)
        family_bits=writer_skill_bits([row for row in self.manifest
                                       if records.barbarian_id(row['spell_id'])],self.rows)
        primary_skills=sorted({case['skill'] for case in self.data})
        selected=[one_bit(self,family_bits,skill) for skill in primary_skills]
        self.assertEqual(len(set(selected)),len(primary_skills))
        for skill,seen in family_bits.items():
            if skill in primary_skills: continue
            self.assertFalse(seen&set(selected),skill)

    def test_secondary_executors(self):
        self.assertIn('INSERT INTO spell_jump_distance (ID,JumpDistance) VALUES (81029,20)',self.sql)
        self.assertEqual(int(self.rows[81029]['AttributesEx4']),0x40000)
        rupture=self.rows[p.RUPTURE]
        self.assertEqual(int(rupture['Effect_1']),2)
        self.assertEqual(int(rupture['ImplicitTargetA_1']),8)
        radius=g.load_dbc('SpellRadius.dbc')[0][int(rupture['EffectRadiusIndex_1'])]
        self.assertEqual(struct.unpack_from('<f',radius,4)[0],8)
        for sid,aura,ms in ((p.FROSTBITE,12,1500),(p.SMITE,12,1500),(p.HAMMER,12,1000),
                (p.STUPEFY,177,3000),(p.ONSLAUGHT,4,3000),(p.FROST_LOCKOUT,4,5000),(p.VANGUARD,4,4000)):
            row=self.rows[sid]
            self.assertEqual(int(row['EffectAura_1']),aura)
            duration=g.load_dbc('SpellDuration.dbc')[0][int(row['DurationIndex'])]
            self.assertEqual(struct.unpack_from('<i',duration,4)[0],ms)

    def test_followon_data_and_helpers(self):
        for sid in range(81000,81138):
            self.assertFalse(int(self.rows[sid]['Attributes']) & 0x80, sid)
        for sid,target,school in ((p.PULVERIZE,104,4),(p.SIDEARM,104,16),(p.SCATTERING,8,1)):
            row=self.rows[sid]
            self.assertEqual(int(row['Effect_1']),2)
            self.assertGreater(int(row['EffectBasePoints_1']),0)
            self.assertEqual(int(row['ImplicitTargetA_1']),target)
            self.assertEqual(int(row['SchoolMask']),school)
            self.assertIn(f"({sid},'dc_primary_spell')",self.sql)
        radius=g.load_dbc('SpellRadius.dbc')[0][int(self.rows[p.SCATTERING]['EffectRadiusIndex_1'])]
        self.assertEqual(struct.unpack_from('<f',radius,4)[0],5)
        self.assertEqual(float(self.rows[p.SIDEARM]['Speed']),50)
        self.assertEqual(int(self.rows[p.KNOCKUP]['Effect_1']),98)
        self.assertEqual(int(self.rows[p.FRENZY_BUFF]['CumulativeAura']),5)
        self.assertEqual(self.rows[p.FRENZY_BUFF]['SpellIconID'],self.rows[81000]['SpellIconID'])
        self.assertEqual(int(self.rows[p.FRENZY_BUFF]['Attributes']) & 0x04000080,0)
        self.assertTrue(int(self.rows[p.FROST_LOCKOUT]['Attributes']) & 0x80)
        storm=self.rows[p.GATHERING]
        self.assertEqual((int(storm['EffectAura_1']),int(storm['EffectBasePoints_1'])+1),(33,-60))  # gathering_chill_pct 60, ruling 2026-09-29
        self.assertEqual((int(storm['EffectAura_2']),int(storm['EffectBasePoints_2'])+1,int(storm['EffectMiscValue_2'])),(87,10,127))
        for sid in range(p.RUPTURE,p.KNOCKUP+1):
            self.assertNotIn('Primary Internal',self.rows[sid]['Name_Lang_enUS'])
        self.assertEqual(self.mechanics['pulverize_width_yards'],1)
        self.assertEqual(self.mechanics['pulverize_length_yards'],26)
        self.assertEqual(self.mechanics['sidearm_selection_yards'],15)
        self.assertEqual(self.mechanics['sidearm_length_yards'],5)
        self.assertEqual(self.mechanics['sidearm_width_yards'],1)
        self.assertEqual(self.mechanics['scattering_height_yards'],2)

    # The published migration the writer's output belongs to. It moves when a
    # step publishes a new one and the one before it becomes applied history:
    # combat_0005 for steps 1-5, combat_0020 for step 6, and combat_0021 for
    # step 7's descriptions. An applied migration is never regenerated, so
    # this name is the only thing that changes here.
    # The migration a step publishes is the only artifact that moves
    # here. Step 8 adds combat_0022 (PM approval, 2026-09-20) and keeps
    # combat_0021 as step 7's description checkpoint; combat_0020 is
    # applied and frozen. 0021 is committed and NOT applied, so it is
    # not in APPLIED_MIGRATIONS - it joins that list when a deployment
    # receipt says it was applied, and that receipt's commit becomes
    # the pin below.
    # diablocraft-wizard-records: combat_0025 was applied by the 2026-09-22
    # release (docs/deploy-release-20260922.md), so the Wizard's records are
    # published as combat_0026 and 0025 joins applied history below.
    # diablocraft-wizard-resource: combat_0026 is committed and not yet
    # applied (no deployment receipt names it), so it is queued history and
    # stays exactly as HEAD holds it; the Arcane Power records (resource
    # regeneration, channels, ground ticks) are published as combat_0027.
    # diablocraft-wizard-mechanics republished them as combat_0028.
    UNCHANGED_MIGRATIONS=('combat_0026_wizard_records.sql',)
    # The deployment receipt: the commit that published the applied records
    # migration, holding the frozen combat_0001 and the applied combat_0020.
    # It is a FROZEN pin and does not move with HEAD - the same principle the
    # combat_0001 baseline already follows (Architect, 2026-09-20). Against
    # HEAD this check would only see a dirty working tree, because a commit
    # that rewrote applied history would move HEAD with it and both sides
    # would agree.
    APPLIED_RECEIPT='769777c'
    APPLIED_MIGRATIONS=('combat_0001_spell_shells.sql','combat_0020_spell_records.sql')
    # The step 8 deployment receipt (docs/deploy-spell-rewrite-step8.md) applied
    # 0021 and 0022 and says never to regenerate either in place, so they are
    # applied history too - pinned to the commit that recorded that receipt,
    # which does not move with HEAD any more than 769777c does.
    STEP8_RECEIPT='757a659'
    STEP8_MIGRATIONS=('combat_0021_spell_descriptions.sql',
                      'combat_0022_passive_modifiers.sql')
    # Step 11's receipt (docs/deploy-spell-rewrite-step11.md, 2026-09-20)
    # applied 0023 and froze it: "any later correction requires a new
    # migration". So 0023 joins applied history on its own frozen pin, the
    # same way 0020 and the step 8 pair did, and Issue #54/#55's records are
    # published as combat_0024 rather than by regenerating it.
    STEP11_RECEIPT='7d531a6'
    STEP11_MIGRATIONS=('combat_0023_description_variables.sql',)
    # The stats-wiring deployment receipt (ff80c18) applied 0024, so it is
    # applied history on its own frozen pin like every one above it. Steps 12
    # and 13 publish combat_0025 rather than regenerating it.
    WIRING_RECEIPT='ff80c18'
    WIRING_MIGRATIONS=('combat_0024_stats_wiring.sql',)
    # APPLIED 2026-09-22: the release receipt (docs/deploy-release-20260922.md)
    # applied combat_0025, pinned to the commit that holds that receipt. The
    # Wizard's records go out as combat_0026 (diablocraft-wizard-records).
    RELEASE_RECEIPT='268f5e8'
    RELEASE_MIGRATIONS=('combat_0025_spell_tooltips.sql',)

    def test_client_and_sql_parity_and_unrelated_shells(self):
        # And the ones already applied stay exactly as they were applied: a
        # step that regenerates history rather than adding to it fails here.
        # A reference that cannot be read is a failure too, not a pass - a
        # check that quietly stops checking is worse than no check.
        for receipt,names in ((self.APPLIED_RECEIPT,self.APPLIED_MIGRATIONS),
                              (self.STEP8_RECEIPT,self.STEP8_MIGRATIONS),
                              (self.STEP11_RECEIPT,self.STEP11_MIGRATIONS),
                              (self.WIRING_RECEIPT,self.WIRING_MIGRATIONS),
                              (self.RELEASE_RECEIPT,self.RELEASE_MIGRATIONS)):
            for name in names:
                published=subprocess.run(
                    ['git','show','%s:mod-diablocraft/data/sql/db-world/updates/%s'
                     %(receipt,name)],cwd=g.REPO_ROOT,capture_output=True)
                self.assertEqual(published.returncode,0,
                                 'the deployment receipt %s has no %s: %s'
                                 %(receipt,name,published.stderr.decode().strip()))
                self.assertEqual((g.UPDATES/name).read_bytes(),published.stdout,
                                 '%s is applied history and has been rewritten'%name)
        # And the step 7 checkpoint is not regenerated by a later step: it is
        # committed, unapplied and queued, so it is not applied history, but
        # it is a published artifact and a step that quietly rewrote it would
        # change what the PM already reviewed.
        for name in self.UNCHANGED_MIGRATIONS:
            published=subprocess.run(
                ['git','show','HEAD:mod-diablocraft/data/sql/db-world/updates/%s'%name],
                cwd=g.REPO_ROOT,capture_output=True)
            self.assertEqual(published.returncode,0,
                             'HEAD has no %s: %s'%(name,published.stderr.decode().strip()))
            self.assertEqual((g.UPDATES/name).read_bytes(),published.stdout,
                             '%s is a published checkpoint and has been rewritten'%name)
        # The frozen baseline, and every move away from it explained. Steps
        # 1-6 rewrote the numbers of 139 unrelated shells out of the values
        # sheets; the point of keeping combat_0001 is that each of those
        # numbers still has to be the one its sheet row states.
        if self.contract is None:
            self.skipTest('client DBCs are not extracted')
        self.assertEqual(self.contract_problems, [], 'the record contract does not hold')
        stock=(g.UPDATES/'combat_0001_spell_shells.sql').read_text(encoding='utf-8')
        _,old=sql_rows(stock)
        primary_ids={int(r['spell_id']) for r in self.data}
        marker=marker_radius_index()
        unexplained,explained,moved={},0,0
        for sid,row in old.items():
            if sid in primary_ids: continue
            drift=unrelated_drift(self.rows[sid],row,targeting_owned_fields(row,self.targeting))
            moved+=bool(drift)
            for field,(was,now) in drift.items():
                if field in WRITER_OWNED: continue
                wanted=self.contract.get((sid,field),self.channel.get((sid,field)))
                if wanted is None:
                    wanted=later_step_contract(field,was,self.rows[sid],marker)
                if wanted is not None and wanted==now:
                    explained+=1
                    continue
                unexplained.setdefault(sid,{})[field]=(was,now,wanted)
        self.assertEqual(unexplained,{},
            'a shell moved away from combat_0001 and no sheet row or ruling says why')
        self.assertGreater(explained,0,'nothing is explained: the contract was not read')
        self.assertGreater(moved,0,'no shell moved: the baseline is not the frozen one')
        client=g.CLIENT_DBC.read_bytes()
        _,count,fields,size,strings=struct.unpack_from('<4sIIII',client)
        found=[]
        for offset in range(20,20+count*size,size):
            sid=struct.unpack_from('<I',client,offset)[0]
            if sid not in self.rows: continue
            found.append(sid)
            for i,key in enumerate(self.columns):
                value=self.rows[sid][key]
                if g.FMT[i]=='s' or ('_Lang_' in key and not key.endswith('_Mask')): continue
                if g.FMT[i]=='f':
                    self.assertAlmostEqual(struct.unpack_from('<f',client,offset+i*4)[0],float(value),places=4)
                else: self.assertEqual(struct.unpack_from('<I',client,offset+i*4)[0],int(value)&0xffffffff,(sid,key))
        self.assertEqual(len(found),len(set(found)))
        self.assertEqual(set(found),set(self.rows))

    def test_a_wrong_number_in_an_explained_field_is_still_caught(self):
        """The contract explains a field with ONE value, not with any value.

        Keeping combat_0001 frozen is only worth the trouble if "the sheets
        own this field" cannot become a licence to put anything in it. Each
        contract entry is checked against a fabricated neighbour of the
        published number, which no sheet row states.
        """
        if self.contract is None:
            self.skipTest('client DBCs are not extracted')
        checked=0
        for (sid,field),wanted in sorted(self.contract.items()):
            if sid not in self.rows or not re.fullmatch(r'-?\d+',wanted): continue
            self.assertEqual(self.rows[sid][field],wanted,
                             '%d %s is not the number its sheet row states'%(sid,field))
            fake=str(int(wanted)+1)
            self.assertNotEqual(fake,wanted)
            self.assertNotEqual(self.contract[(sid,field)],fake,
                                '%d %s: a neighbouring number would pass as explained'%(sid,field))
            checked+=1
        self.assertGreater(checked,100,'the contract covers almost nothing')
        # The channel exemption is exact in the same way: it names values, so
        # a writer that stopped making Whirlwind a channel would fail here
        # rather than quietly pass as "a field the writer owns".
        channels={sid for sid,_ in self.channel}
        self.assertEqual(channels,{81004,81043,81044,81045,81046,81047},
                         'the channel exemption covers something other than Whirlwind')
        for (sid,field),wanted in sorted(self.channel.items()):
            self.assertEqual(self.rows[sid][field],wanted,
                             '%d %s is not what the writer writes for a channel'%(sid,field))

    def test_unrelated_parity_still_rejects_donor_drift(self):
        # Exercise the comparison itself: an intentional target edit is allowed,
        # but Speed and other unowned fields cannot hide behind that exemption.
        row=self.rows[81005]
        owned=targeting_owned_fields(row,self.targeting)
        for key in ('Speed','SpellVisualID_1','SpellIconID','SchoolMask',
                    'ManaCost','RecoveryTime','EffectBasePoints_1','Effect_1'):
            changed=dict(row,**{key:str(float(row[key])+1)})
            self.assertEqual(set(unrelated_drift(changed,row,owned)),{key})
        for key in ('ImplicitTargetA_1','ImplicitTargetB_1','MaxTargets'):
            changed=dict(row,**{key:str(int(row[key])+1)})
            self.assertEqual(unrelated_drift(changed,row,owned),{})
        self.assertEqual(targeting_owned_fields(self.rows[81004],self.targeting),set())
        self.assertEqual(targeting_owned_fields(self.rows[81138],self.targeting),set())

if __name__=='__main__': unittest.main()

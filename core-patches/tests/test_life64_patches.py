"""Core patches 0027 (Life in 64 bits), 0028 (hits in 64 bits) and 0029 (the Life tripwire): what they leave in the core.

The arithmetic is run in test_unit_life64.py. This one reads the shape: the three files are header-less, apply to a clean
pin plus the patches before them with a plain `git apply` and change exactly the files they name, own the next free
numbers, and have their README rows. Then the rules the review pins, read from the core as the stack builds it:

  * one writer of the four health update-field dwords (`Unit::WriteHealthFields`: the stock two and the two the layout grew
    by), which writes the real Life with no projection; the getters read the 64-bit members;
  * `Unit::DealDamage` asks the module's exact-hit hook first, gives each 32-bit consumer a view, and checks the tripwire
    after the Life moves; `Unit::DealHeal` does the same for a heal;
  * the spell damage log, its reflect form, the gameobject sender of the same opcode and the periodic damage log write the
    hit and the overkill in 64 bits, always: no clamp and no hook for a cut line (melee, shields and heals keep 32 bits);
  * the two providers hand their damage over in 64 bits, the periodic tick keeps the provided tick exact to `DealDamage`
    and takes absorb and resist off it by what they took from its view;
  * the creature's max Life is built from an exact 64-bit base; its regen, damage requirement and save column are 64-bit
    and saturate where a column is 32.

Then it proves it can fail: the same rules are checked with each patch left out and with each file the rules read left
at its pinned text, and every one of those must name the rule it broke.
"""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import life64_patched as lp  # noqa: E402

UNIT_H = 'src/server/game/Entities/Unit/Unit.h'
UNIT_CPP = 'src/server/game/Entities/Unit/Unit.cpp'
UNIT_SCRIPT_H = 'src/server/game/Scripting/ScriptDefines/UnitScript.h'
UNIT_SCRIPT_CPP = 'src/server/game/Scripting/ScriptDefines/UnitScript.cpp'
SCRIPT_MGR_H = 'src/server/game/Scripting/ScriptMgr.h'
SPELL_CPP = 'src/server/game/Spells/Spell.cpp'
AURA_EFFECTS = 'src/server/game/Spells/Auras/SpellAuraEffects.cpp'
OBJECT_CPP = 'src/server/game/Entities/Object/Object.cpp'
CREATURE_H = 'src/server/game/Entities/Creature/Creature.h'
CREATURE_CPP = 'src/server/game/Entities/Creature/Creature.cpp'
UPDATE_FIELDS = 'src/server/game/Entities/Object/Updates/UpdateFields.h'
UPDATE_FLAGS = 'src/server/game/Entities/Object/Updates/UpdateFieldFlags.cpp'
STAT_SYSTEM = 'src/server/game/Entities/Unit/StatSystem.cpp'
RULE_FILES = (UNIT_H, UNIT_CPP, UNIT_SCRIPT_H, UNIT_SCRIPT_CPP, SCRIPT_MGR_H, SPELL_CPP, AURA_EFFECTS, OBJECT_CPP, CREATURE_H,
              CREATURE_CPP, STAT_SYSTEM, UPDATE_FIELDS, UPDATE_FLAGS)


def body(text, signature):
    """The whole definition that starts with `signature` (braces inside strings and comments do not count)."""
    assert text.count(signature) == 1, f'{signature!r} occurs {text.count(signature)} times'
    start = text.index(signature)
    open_at = text.index('{', start)
    depth, i = 0, open_at
    while True:
        if text.startswith('//', i):
            i = text.index('\n', i)
            continue
        c = text[i]
        if c in '"\'':
            i += 1
            while text[i] != c:
                i += 2 if text[i] == '\\' else 1
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1


def problems(files):
    """[(rule, what is wrong)] in the patched files; empty when the rules hold."""
    out = []

    def need(rule, fragment, text):
        if fragment not in text:
            out.append((rule, f'missing: {fragment}'))

    def forbid(rule, fragment, text):
        if fragment in text:
            out.append((rule, f'present: {fragment}'))

    unit_h, unit_cpp = files[UNIT_H], files[UNIT_CPP]

    # one writer of the health fields, and the layout they live in
    rule = 'one writer of the health fields'
    for field in ('UNIT_FIELD_HEALTH', 'UNIT_FIELD_MAXHEALTH', 'UNIT_FIELD_HEALTH_HI', 'UNIT_FIELD_MAXHEALTH_HI'):
        if unit_cpp.count(f'SetUInt32Value({field},') != 1:
            out.append((rule, f'{field} is written {unit_cpp.count(f"SetUInt32Value({field},")} times in Unit.cpp'))
        forbid(rule, f'GetUInt32Value({field})', unit_h)
    if 'void Unit::WriteHealthFields()' in unit_cpp:
        writer = body(unit_cpp, 'void Unit::WriteHealthFields()')
        need(rule, 'SetUInt32Value(UNIT_FIELD_HEALTH, static_cast<uint32>(m_health64));', writer)
        need(rule, 'SetUInt32Value(UNIT_FIELD_MAXHEALTH, static_cast<uint32>(m_maxHealth64));', writer)
        need(rule, 'SetUInt32Value(UNIT_FIELD_HEALTH_HI, static_cast<uint32>(m_health64 >> 32));', writer)
        need(rule, 'SetUInt32Value(UNIT_FIELD_MAXHEALTH_HI, static_cast<uint32>(m_maxHealth64 >> 32));', writer)
        forbid(rule, '__int128', writer)
        forbid(rule, 'IsControlledByPlayer', writer)
    else:
        out.append((rule, 'Unit::WriteHealthFields is missing'))
    forbid(rule, 'LIFE_BAR_LINE', unit_h)
    need(rule, 'case UNIT_FIELD_HEALTH:\n        case UNIT_FIELD_HEALTH_HI:\n            InvalidateValuesUpdateCache();', unit_cpp)
    rule = 'the update-field layout grew by two dwords'
    fields_h = files[UPDATE_FIELDS]
    need(rule, 'UNIT_FIELD_PADDING                        = OBJECT_END + 0x008D,', fields_h)
    need(rule, 'UNIT_FIELD_HEALTH_HI                      = OBJECT_END + 0x008E, // Size: 1, Type: INT, Flags: PUBLIC', fields_h)
    need(rule, 'UNIT_FIELD_MAXHEALTH_HI                   = OBJECT_END + 0x008F, // Size: 1, Type: INT, Flags: PUBLIC', fields_h)
    need(rule, 'UNIT_END                                  = OBJECT_END + 0x0090,', fields_h)
    need(rule, 'UF_FLAG_NONE,                                           // UNIT_FIELD_PADDING\n'
         '    UF_FLAG_PUBLIC,                                         // UNIT_FIELD_HEALTH_HI\n'
         '    UF_FLAG_PUBLIC,                                         // UNIT_FIELD_MAXHEALTH_HI\n', files[UPDATE_FLAGS])
    need(rule, 'uint64 GetHealth()    const { return m_health64; }', unit_h)
    need(rule, 'uint64 GetMaxHealth() const { return m_maxHealth64; }', unit_h)
    need(rule, 'void SetHealth(uint64 val);', unit_h)
    need(rule, 'void SetMaxHealth(uint64 val);', unit_h)
    need(rule, 'int64 ModifyHealth(int64 val);', unit_h)
    need(rule, 'int64 GetHealthGain(int64 dVal);', unit_h)

    # DealDamage and DealHeal
    rule = 'DealDamage in 64 bits'
    if 'uint64 Unit::DealDamage(' in unit_cpp:
        deal = body(unit_cpp, 'uint64 Unit::DealDamage(Unit* attacker, Unit* victim, uint64 damage,')
        need(rule, 'sScriptMgr->ModifyExactDamage(attacker, victim, damage, damagetype);', deal)
        if 'ModifyExactDamage' in deal and 'sScriptMgr->DealDamage(' in deal and deal.index('ModifyExactDamage') > deal.index('sScriptMgr->DealDamage('):
            out.append((rule, 'the exact-hit hook is asked after the 32-bit hook'))
        for consumer in ('sScriptMgr->DealDamage(attacker, victim, view, damagetype)', 'victim->GetAI()->DamageTaken(attacker, view,',
                         'attacker->GetAI()->DamageDealt(victim, view,', 'sScriptMgr->OnDamage(attacker, victim, view)'):
            if not re.search(r'ApplyThroughView\(damage, \[&\]\(uint32& view\) \{ [^\n]*' + re.escape(consumer), deal):
                out.append((rule, f'no view around {consumer}'))
        need(rule, 'uint64 health = victim->GetHealth();', deal)
        need(rule, 'uint64 unDamage = health < damage ? health : damage;', deal)
        need(rule, 'victim->ModifyHealth(lifeChange);\n        victim->CheckLifeAfter(attacker, spellProto, health, lifeChange);', deal)
        forbid(rule, 'uint32 health = victim->GetHealth()', deal)
        forbid(rule, 'ModifyHealth(- (int32)damage)', deal)
    else:
        out.append((rule, 'Unit::DealDamage does not take 64 bits'))
    rule = 'DealHeal in 64 bits'
    if 'int64 Unit::DealHeal(' in unit_cpp:
        heal = body(unit_cpp, 'int64 Unit::DealHeal(Unit* healer, Unit* victim, uint64 addhealth)')
        need(rule, 'victim->GetAI()->HealReceived(healer, view)', heal)
        need(rule, 'sScriptMgr->OnHeal(healer, victim, view)', heal)
        need(rule, 'victim->CheckLifeAfter(healer, nullptr, lifeBefore, lifeChange);', heal)
        forbid(rule, '(uint32&)gain', heal)
    else:
        out.append((rule, 'Unit::DealHeal does not take 64 bits'))

    # the combat log
    rule = 'the combat log carries 64 bits'
    for fragment in ('CombatLogAmount', 'COMBAT_LOG_AMOUNT_MAX', 'SpellLogAmount', 'OnCombatLogClamp'):
        for path in (UNIT_H, UNIT_CPP, UNIT_SCRIPT_H, UNIT_SCRIPT_CPP, SCRIPT_MGR_H, OBJECT_CPP):
            forbid(rule, fragment, files[path])
    for sender, calls in (('void Unit::SendSpellNonMeleeReflectLog(', ('data << uint64(damage);', 'data << uint64(LifeOverkill(damage, log->target->GetHealth()));')),
                          ('void Unit::SendSpellNonMeleeDamageLog(SpellNonMeleeDamage* log)', ('data << uint64(damage);', 'data << uint64(LifeOverkill(damage, log->target->GetHealth()));')),
                          ('void Unit::SendPeriodicAuraLog(', ('data << uint64(damage);', 'data << uint64(pInfo->overDamage);')),
                          ('void Unit::SendAttackStateUpdate(CalcDamageInfo* damageInfo)', ('data << uint32(tmpDamage[0] + tmpDamage[1]);', 'data << uint32(tmpDamage[i]);'))):
        if sender in unit_cpp:
            for call in calls:
                need(rule, call, body(unit_cpp, sender))
        else:
            out.append((rule, f'{sender} is missing'))
    need(rule, 'data << uint64(damage);', files[OBJECT_CPP])
    need(rule, 'data << uint64(LifeOverkill(damage, target->GetHealth()));', files[OBJECT_CPP])

    # the hits
    rule = 'the structs carry 64 bits'
    need(rule, 'uint64 damage;\n    uint64 overkill;', unit_h)
    need(rule, 'uint64 damage;\n    uint64 overDamage;', unit_h)
    need(rule, 'static void DealDamageMods(Unit const* victim, uint64& damage, uint32* absorb);', unit_h)
    rule = 'the providers hand over 64 bits'
    need(rule, 'uint8 /*effectMask*/, uint64& /*damage*/, bool& /*critical*/) { return false; }', files[UNIT_SCRIPT_H])
    need(rule, 'Unit* /*target*/, uint64& /*damage*/, bool& /*critical*/) { return false; }', files[UNIT_SCRIPT_H])
    need(rule, 'SpellInfo const* info, uint8 effectMask, uint64& damage, bool& critical);', files[SCRIPT_MGR_H])
    need(rule, 'Unit* target, uint64& damage, bool& critical);', files[SCRIPT_MGR_H])
    need(rule, 'uint64 providedDamage = 0;', files[SPELL_CPP])
    rule = 'the exact-hit hook'
    script_h = files[UNIT_SCRIPT_H]
    if 'UNITHOOK_MODIFY_EXACT_DAMAGE' in script_h and 'UNITHOOK_END' in script_h:
        enum = script_h[script_h.index('enum UnitHook'):script_h.index('UNITHOOK_END')]
        need(rule, 'UNITHOOK_MODIFY_EXACT_DAMAGE,', enum)
    else:
        out.append((rule, 'no hook id'))
    need(rule, 'virtual void ModifyExactDamage(Unit* /*attacker*/, Unit* /*victim*/, uint64& /*damage*/, DamageEffectType /*damagetype*/) { }', script_h)
    need(rule, 'CALL_ENABLED_HOOKS(UnitScript, UNITHOOK_MODIFY_EXACT_DAMAGE, script->ModifyExactDamage(attacker, victim, damage, damagetype));', files[UNIT_SCRIPT_CPP])
    rule = 'the tick stays exact'
    aura = files[AURA_EFFECTS]
    if 'uint64 exactDamage = damage;' in aura:
        need(rule, 'ProvideFinalPeriodicDamage(this, caster, target, exactDamage, crit)', aura)
        need(rule, 'exactDamage -= damageView - dmgInfo.GetDamage();', aura)
        need(rule, 'Unit::DealDamageMods(target, exactDamage, &absorb);', aura)
        need(rule, 'Unit::DealDamage(caster, target, exactDamage, &cleanDamage, DOT,', aura)
    else:
        out.append((rule, 'the periodic tick has no exact damage'))
    rule = 'the direct hit stays exact'
    need(rule, 'LifeToInt32(damageInfo.damage)', files[SPELL_CPP])
    need(rule, 'LifeToUInt32(damageInfo.damage), m_attackType', files[SPELL_CPP])

    # the creature
    rule = 'the creature in 64 bits'
    need(rule, 'void SetBaseHealth(uint64 baseHealth);', files[CREATURE_H])
    need(rule, 'uint64 _playerDamageReq;', files[CREATURE_H])
    need(rule, 'void LowerPlayerDamageReq(uint64 unDamage,', files[CREATURE_H])
    need(rule, 'data.curhealth = LifeToUInt32(GetHealth());', files[CREATURE_CPP])
    need(rule, 'stmt->SetData(index++, LifeToUInt32(GetHealth()));', files[CREATURE_CPP])
    need(rule, 'SetBaseHealth(health);', files[CREATURE_CPP])
    need(rule, 'uint64 addvalue = 0;', files[CREATURE_CPP])
    need(rule, 'long double value = static_cast<long double>(m_baseHealth64)', files[STAT_SYSTEM])
    return out


class Shape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = lp.replay(RULE_FILES)

    def test_the_numbers_are_the_next_free_ones(self):
        numbers = [int(patch.name[:4]) for patch in lp.STACK]
        self.assertEqual(len(numbers), len(set(numbers)), 'a patch number is used twice')
        self.assertEqual([27, 28, 29], [n for n in numbers if n >= 27], '0027-0029 are the Life patches and nothing follows them')
        self.assertEqual(['0027-life-64bit.patch', '0028-hits-64bit.patch', '0029-life-tripwire.patch'], [p.name for p in lp.LIFE])

    def test_the_patches_are_headerless_and_apply_to_a_clean_pin_plus_the_stack(self):
        for patch in lp.LIFE:
            self.assertNotIn('diff --git', patch.read_text(encoding='utf-8'), f'{patch.name} carries diff --git lines: git apply --directory . skips them silently')
        changed = lp.fresh_tree()
        for patch in lp.LIFE:
            self.assertEqual(sorted(lp.core_files(patch)), changed[patch.name], f'{patch.name} must change exactly the files it names')

    def test_readme_rows_and_paragraphs(self):
        readme = (lp.PATCHES / 'README.md').read_text(encoding='utf-8')
        for patch in lp.LIFE:
            number = patch.name[:4]
            self.assertIn(f'| {number} | [{patch.name}]({patch.name}) |', readme, f'{patch.name} has no row in the table')
            self.assertRegex(readme, rf'(?m)^{number} \(20\d\d-\d\d-\d\d, `diablocraft-sbxl`', f'{patch.name} has no dated paragraph')

    def test_the_rules_hold(self):
        self.assertEqual([], problems(self.files))

    def test_the_rules_fail_with_a_patch_left_out(self):
        for left_out in lp.LIFE:
            stack = [patch for patch in lp.STACK if patch != left_out]
            if left_out == lp.LIFE[0]:
                stack = [patch for patch in stack if patch not in lp.LIFE]     # 0028 and 0029 sit on 0027
            elif left_out == lp.LIFE[1]:
                stack = [patch for patch in stack if patch != lp.LIFE[2]]      # 0029 sits on 0028
            found = problems(lp.replay(RULE_FILES, stack))
            self.assertTrue(found, f'the rules passed without {left_out.name}')

    def test_the_rules_fail_with_a_file_left_at_its_pinned_text(self):
        # each file the rules read, with the three patches' hunks in it left out, must break a rule that names that file
        broken = {}
        for path in RULE_FILES:
            stack = lp.STACK
            lp.OUT.mkdir(parents=True, exist_ok=True)
            tree = Path(tempfile.mkdtemp(dir=lp.OUT))
            try:
                subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
                lp.seed(tree, RULE_FILES)
                include = [f'--include={p}' for p in RULE_FILES]
                for patch in stack:
                    exclude = [f'--exclude={path}'] if patch in lp.LIFE else []
                    done = subprocess.run(['git', 'apply', *exclude, *include, str(patch)], cwd=tree, capture_output=True, text=True)
                    self.assertEqual(0, done.returncode, f'{patch.name} (without {path}):\n{done.stderr}')
                partial = {p: (tree / p).read_text(encoding='utf-8') for p in RULE_FILES}
            finally:
                shutil.rmtree(tree)
            broken[path] = problems(partial)
        for path, found in broken.items():
            self.assertTrue(found, f'the rules passed with {path} left at the pin')


if __name__ == '__main__':
    unittest.main(verbosity=2)

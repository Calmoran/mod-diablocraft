#!/usr/bin/env python3
"""World's half of the native 64-bit Life cutover (diablocraft-88i0; plan docs/proposals/core-64bit-health.md section 4, Part 3).

The core holds the real Life (core patch 0027) and hands the exact hit to the module first (0028's ModifyExactDamage), so
the World files keep no pool, no scaled copy and no conversion. These are source pins on the files Part 3 owns; the
arithmetic of the Life handover and of the Health Link split is run in test_gr_scaling.py and test_elite_affixes_round_two.py.
Each rule has a killed mutant: the same check run on a copy with the rule broken must fail.

What it does NOT cover (needs the server): that the core calls the hook, and the compile (the module's .cpp files are
compiled against the patched core by the worker's syntax check and the Part 4 build).
"""
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / 'src'

# The World lane's sources that used to read or write the pool (every file that includes the BigLife headers or names it).
FILES = [
    'common/dc_tiers.h',
    'difficulty/dc_difficulty.cpp',
    'rifts/dc_rifts.cpp',
    'rifts/dc_rift_open.cpp',
    'rifts/dc_rift_scripts.cpp',
    'monsters/dc_monster_ai.cpp',
    'monsters/affixes/dc_affix_common.cpp',
    'monsters/affixes/dc_affix_health_link.cpp',
    'monsters/affixes/dc_affix_hazards.cpp',
    'monsters/affixes/dc_affix_juggernaut.cpp',
    'monsters/affixes/dc_affix_internal.h',
    'monsters/affixes/dc_affix_unit_script.cpp',
]
GONE = re.compile(r'BigLife|dc_big_life|LifePerCore|TrueMax|TrueHealth|CoreOfTrue|TrueOfCore|SplitLink|CORE_MAX|ToU64')


def block(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


def check(files):
    for name, text in files.items():
        found = GONE.findall(re.sub(r'//[^\n]*', '', text))   # a comment may say what was retired
        assert not found, '%s still names the pool: %s' % (name, sorted(set(found)))

    difficulty = files['difficulty/dc_difficulty.cpp']
    # the tier balance hands over the real Life and adopts nothing into a pool
    assert 'health = scaling.health;' in difficulty and 'Adopt(' not in difficulty
    log = block(difficulty, 'void LogCreature(', 'class TierWorld')
    assert 'creature->GetMaxHealth()' in log
    refresh = block(difficulty, 'uint64 previous', 'catch (std::exception')
    assert refresh.count('creature->GetMaxHealth()') == 2
    # `.dc tier` prints one number for the selected creature: its Life, and no second "Big:" line
    tier = block(difficulty, 'static bool HandleTier(', 'LogCreature(creature);')
    assert 'creature->GetMaxHealth()' in tier and 'Big:' not in tier and tier.count('PSendSysMessage') == 2
    # the logs
    assert 'leader->GetMaxHealth()' in block(files['rifts/dc_rift_scripts.cpp'], 'static void Describe(', 'static bool HandleOpen(')
    guardian = block(files['monsters/dc_monster_ai.cpp'], 'void LogGuardianLife(', 'Charm::Body CharmBodyOf(')
    assert guardian.count('boss->GetMaxHealth()') == 2

    # Juggernaut's and an Illusionist copy's Life: the owner is asked, and the fallback writes the 64-bit Life whole
    common = files['monsters/affixes/dc_affix_common.cpp']
    scale = block(common, 'void ScaleLife(Creature* creature, double factor)', '// The always-on affixes')
    assert 'SetMaxHealth(life);' in scale and 'static_cast<std::uint32_t>' not in scale

    # Health Link: on the exact-hit hook, a plain whole-number split, none of the 32-bit damage path
    internal = files['monsters/affixes/dc_affix_internal.h']
    link = files['monsters/affixes/dc_affix_health_link.cpp']
    unit = files['monsters/affixes/dc_affix_unit_script.cpp']
    decl = 'void HealthLinkStruck(Creature* elite, EliteState* state, AffixNumbers const& n, std::uint64_t& damage)'
    assert decl + ';' in internal and decl + '\n{' in link
    assert 'damage / count' in link and 'damage % count' in link and 'uint32' not in link
    hook = block(unit, 'void ModifyExactDamage(', 'uint32 DealDamage(Unit*')
    assert 'uint64& damage' in hook and 'HealthLinkStruck(elite, state, *numbers, damage)' in hook
    # the same guard OnDamage has: a player's hit on a living elite that carries the state
    assert 'attacker->ToPlayer()' in hook and 'elite->IsAlive()' in hook and 'DCRiftElite' in hook
    struck = block(unit, 'static void EliteStruck(', '// This elite hit a player.')
    assert 'HealthLinkStruck(' not in struck and 'IllusionistStruck(' in struck

    # Juggernaut (diablocraft-86qcn): the +30% is on the exact hit too, before Health Link shares it as it did in OnDamage; a 32-bit
    # view would wrap a hit past 3.3 billion and ApplyThroughView would let the wrapped number replace the exact one
    jug_decl = 'void JuggernautStruck(EliteState const* state, AffixNumbers const& n, std::uint64_t& damage)'
    jug = files['monsters/affixes/dc_affix_juggernaut.cpp']
    assert jug_decl + ';' in internal and jug_decl + '\n{' in jug
    jug_body = block(jug, 'void JuggernautStruck(', 'void JuggernautPassive(')   # the passive below keeps its uint32 mechanic ids
    assert 'LifeMulDiv(damage,' in jug_body and 'uint32' not in re.sub(r'//[^\n]*', '', jug_body)
    assert 'JuggernautStruck(' not in struck
    assert hook.index('JuggernautStruck(state, *numbers, damage)') < hook.index('HealthLinkStruck(elite, state, *numbers, damage)')


def load():
    return {name: (SRC / name).read_text(encoding='utf-8') for name in FILES}


def mutated(name, old, new):
    files = load()
    assert files[name].count(old) >= 1, 'mutation target is gone: %r' % old
    files[name] = files[name].replace(old, new, 1)
    return files


class WorldNativeLife(unittest.TestCase):
    def test_the_world_files_hold_no_pool_and_use_the_exact_hit_hook(self):
        check(load())

    def test_each_rule_has_a_killed_mutant(self):
        files = load()
        link = files['monsters/affixes/dc_affix_health_link.cpp']
        mutants = {
            'a BigLife header comes back into the tiers header': ('common/dc_tiers.h', '#include <cmath>', '#include "dc_big_life.h"\n#include <cmath>'),
            'the tier balance adopts into a pool again': ('difficulty/dc_difficulty.cpp', 'health = scaling.health;', 'Combat::BigLife::Adopt(creature, scaling.life); health = scaling.health;'),
            'the creature log reads a pool': ('difficulty/dc_difficulty.cpp', 'void LogCreature(Creature* creature)\n{', 'void LogCreature(Creature* creature)\n{\n    (void) BigLife::TrueMax(creature);'),
            '.dc tier prints the Big line again': ('difficulty/dc_difficulty.cpp', 'LogCreature(creature);\n        }\n        return true;', 'handler->PSendSysMessage("Big: core {}", 1);\n            LogCreature(creature);\n        }\n        return true;'),
            'the Guardian log goes back to a pool read': ('monsters/dc_monster_ai.cpp', 'std::uint64_t const life = boss->GetMaxHealth();', 'std::uint64_t const life = DC::Combat::BigLife::TrueMax(boss);'),
            'the Juggernaut fallback writes the Life through 32 bits': ('monsters/affixes/dc_affix_common.cpp', 'SetMaxHealth(life);', 'SetMaxHealth(static_cast<std::uint32_t>(life));'),
            'Health Link goes back to the 32-bit damage': ('monsters/affixes/dc_affix_internal.h', 'AffixNumbers const& n, std::uint64_t& damage);', 'AffixNumbers const& n, std::uint32_t& damage);'),
            'Health Link splits by a float': ('monsters/affixes/dc_affix_health_link.cpp', 'damage / count', 'damage * (1.0 / count)'),
            'Health Link goes back to the 32-bit OnDamage': ('monsters/affixes/dc_affix_unit_script.cpp', '        IllusionistStruck(elite, state, n, now);', '        HealthLinkStruck(elite, state, n, damage);\n        IllusionistStruck(elite, state, n, now);'),
            'Juggernaut goes back to the 32-bit damage': ('monsters/affixes/dc_affix_internal.h', 'void JuggernautStruck(EliteState const* state, AffixNumbers const& n, std::uint64_t& damage);', 'void JuggernautStruck(EliteState const* state, AffixNumbers const& n, std::uint32_t& damage);'),
            'Juggernaut multiplies in a double again': ('monsters/affixes/dc_affix_juggernaut.cpp', 'damage = LifeMulDiv(damage,', 'damage = static_cast<uint32>(damage * n.juggernautTaken); (void) (damage,'),
            'Juggernaut goes back to the 32-bit OnDamage': ('monsters/affixes/dc_affix_unit_script.cpp', '        IllusionistStruck(elite, state, n, now);', '        JuggernautStruck(state, n, damage);\n        IllusionistStruck(elite, state, n, now);'),
            'Juggernaut runs after Health Link has split the hit': ('monsters/affixes/dc_affix_unit_script.cpp', '                        JuggernautStruck(state, *numbers, damage);\n                        HealthLinkStruck(elite, state, *numbers, damage);', '                        HealthLinkStruck(elite, state, *numbers, damage);\n                        JuggernautStruck(state, *numbers, damage);'),
            'the exact hook drops the player guard': ('monsters/affixes/dc_affix_unit_script.cpp', 'if (attacker->ToPlayer() && elite->IsAlive())', 'if (elite->IsAlive())'),
        }
        self.assertIn('damage / count', link)   # the table below must be able to find its targets
        for name, (path, old, new) in mutants.items():
            with self.subTest(mutant=name):
                with self.assertRaises(AssertionError):
                    check(mutated(path, old, new))


if __name__ == '__main__':
    unittest.main(verbosity=2)

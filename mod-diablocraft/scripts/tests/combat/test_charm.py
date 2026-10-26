"""N-CHARM (diablocraft-spr13, switched to D3's rules by diablocraft-hdrct): a charmed monster fights for the player, and the
rift and family AI accept it; the pack attacks it, and a charmed elite's affixes keep working against its former allies.

What can run here runs: the pure rules (src/rifts/dc_charm.h) are compiled with tests/charm/harness.cpp. The class bodies
that carry them cannot run without the worldserver, so source checks hold the wiring (each anchor must exist, and a missing
one is a loud failure, never a skipped check), and cross-source checks hold the pinned core behaviour the design leans on:
Unit::UpdateCharmAI parks the creature's own AI and keeps it, SetCharmedBy calls that AI's OnCharmed(true), and the player
kill hook fires for a Player killer only. The contract (docs/contracts/legendary-world-pieces.md) must name what the code
exports. The other tests that cut these functions out and compile them (test_gr_guardian_clear.py, test_bounties.py,
test_monster_targeting.py) carry the charmed cases for IsRiftTrash, ClearedByGuardian and RiftTargetAI::OnCharmed.

DC_CHARM_RIFTS points the read at src/rifts in a copy of src (mutation runs)."""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
sys.path.insert(0, str(MODULE / 'scripts'))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
from split_sources import affixes_text  # noqa: E402

RIFTS = Path(os.environ.get('DC_CHARM_RIFTS', MODULE / 'src/rifts'))
CORE = ROOT / 'azerothcore-wotlk/src/server/game'
text = lambda name: (RIFTS / name).read_text(encoding='utf-8')
QUESTS, SPAWNER, HEADER = (text(n) for n in ('dc_rift_quests.cpp', 'dc_rift_spawner.cpp', 'dc_rifts.h'))
AI, ELITES = text('../monsters/dc_monster_ai.cpp'), affixes_text(RIFTS.parent)


def body(source, anchor):
    """The brace-balanced text from `anchor` to the end of its block; the anchor must exist."""
    start = source.find(anchor)
    assert start >= 0, 'anchor missing (renamed or moved; update this test): ' + anchor
    brace = source.index('{', start)
    depth = 0
    for index in range(brace, len(source)):
        depth += {'{': 1, '}': -1}.get(source[index], 0)
        if depth == 0:
            return source[start:index + 1]
    raise AssertionError('unbalanced braces after ' + anchor)


def before(text_, first, second):
    assert first in text_ and second in text_, (first, second)
    assert text_.index(first) < text_.index(second), (first, 'must come before', second)


# --- the pure rules, compiled -------------------------------------------------------------------------------------------
scratch = ROOT / 'azerothcore-wotlk/build/_agent-scratch'
with tempfile.TemporaryDirectory(prefix='charm-', dir=scratch) as folder:
    binary = Path(folder) / 'harness'
    subprocess.run(['c++', '-std=c++20', '-O0', '-UNDEBUG', '-Wall', '-Werror', '-I', str(RIFTS),
                    str(MODULE / 'tests/charm/harness.cpp'), '-o', str(binary)], check=True)
    done = harness_env.run([str(binary)], capture_output=True, text=True)
    assert done.returncode == 0 and 'charm harness: ok' in done.stdout, done.stdout + done.stderr

# --- the pinned core the design leans on ----------------------------------------------------------------------------------
unit = (CORE / 'Entities/Unit/Unit.cpp').read_text(encoding='utf-8')
update_charm = body(unit, 'void Unit::UpdateCharmAI()')
assert 'i_disabledAI = i_AI;' in update_charm and 'i_AI = new PetAI(ToCreature());' in update_charm   # parked, not deleted
assert 'i_AI = i_disabledAI;' in update_charm and 'delete i_AI;' in update_charm                       # and brought back
set_charmed = body(unit, 'bool Unit::SetCharmedBy(')
assert 'ToCreature()->AI()->OnCharmed(true);' in set_charmed        # the original AI hears it, once, as the charm lands
assert '_oldFactionId = GetFaction();' in set_charmed and 'SetFaction(charmer->GetFaction());' in set_charmed
assert 'charmer->SetCharm(this, true);' in set_charmed       # the charmer's one slot holds the monster, whichever charm type
remove_charmed = body(unit, 'void Unit::RemoveCharmedBy(')
assert 'Attack(charmer, true)' in remove_charmed and 'creature->AI()->OnCharmed(false);' in remove_charmed
kill = body(unit, 'void Unit::Kill(')
assert re.search(r'if \(Player\* killerPlr = killer->ToPlayer\(\)\)\s*\{[^}]*OnPlayerCreatureKill\(killerPlr, killedCre\)', kill, re.S), \
    'the player kill hook is for a Player killer only: a charmed monster needs the module hook (RiftCharmKills)'
assert 'sScriptMgr->OnUnitDeath(victim, killer);' in kill
assert 'player = killer ? killer->GetCharmerOrOwnerPlayerOrPlayerItself()' in kill   # loot rights and XP already go to the charmer
died = body(unit, 'void Unit::setDeathState(')
assert 'RemoveAllAurasOnDeath();' in died                            # a charm ends with the monster's death

# --- the rift AI: parked while charmed, a clean slate on the way in, the Guardian is not charmable -----------------------
on_charmed = body(AI, 'void OnCharmed(bool apply) override')
for fragment in ('_policy.Clear();', '_hits.clear();', '_busy = false;', 'CharmStarted();'):
    assert fragment in on_charmed, fragment
before(on_charmed, 'CharmStarted();', 'AggressorAI::OnCharmed(apply);')
assert re.search(r'if \(apply\)\s*\{[^}]*\}\s*AggressorAI::OnCharmed\(apply\);', on_charmed, re.S), \
    'the base call (it asks the core to swap the AI) runs for apply and for release alike'
assert 'void CharmStarted() override { _brain.Engage(); }' in AI                                   # the family brain restarts
guardian = body(AI, 'GuardianAI(Creature* creature, Guardian definition)')
assert 'ApplySpellImmune(0, IMMUNITY_MECHANIC, MECHANIC_CHARM, true)' in guardian
assert 'ApplySpellImmune(0, IMMUNITY_STATE, SPELL_AURA_MOD_CHARM, true)' in guardian
assert 'ApplySpellImmune(0, IMMUNITY_STATE, SPELL_AURA_AOE_CHARM, true)' in guardian

# --- trash and the Guardian's clear read the charm-aware rules -----------------------------------------------------------
trash = body(AI, 'bool IsRiftTrash(Creature const* creature)')
assert 'Charm::PlayerOwned(CharmBodyOf(creature))' in trash and 'IsControlledByPlayer' not in trash
cleared = body(AI, 'bool ClearedByGuardian(Creature const* creature, Unit const* reference)')
assert 'Charm::ClearedByGuardian(creature->IsHostileTo(reference), CharmBodyOf(creature))' in cleared
assert 'return creature && Charm::IsCharmedMonster(CharmBodyOf(creature));' in body(AI, 'bool IsCharmedMonster(Creature const* creature)')
assert 'bool IsCharmedMonster(Creature const* creature);' in HEADER                                   # the one export

# --- the pack attacks a charmed monster (D3, hdrct): it is an aggro actor beside the players -------------------------------
actors = body(AI, 'static std::vector<Unit*> ActorsOf(Player* player)')
assert 'player->GetCharm()' in actors and 'IsCharmedMonster(monster)' in actors                    # the core's one charm slot
assert 'DC::Combat::CharmEffect::CharmedBy(player)' in actors                                      # and each the shared charm holds
assert 'IsCharmedMonster(unit->ToCreature())' in body(AI, 'static bool IsActor(Unit const* unit)')
assert 'IsActor(requested)' in body(AI, 'void AttackStart(Unit* requested) override')
damaged = body(AI, 'void DamageTaken(Unit* attacker, uint32& damage, DamageEffectType, SpellSchoolMask) override')
before(damaged, 'IsCharmedMonster(attacker->ToCreature()) ? attacker', 'GetCharmerOrOwnerPlayerOrPlayerItself()')   # itself, not its charmer
ticked = body(AI, 'void Tick()')
assert ticked.count('ActorsOf(player)') == 2                                                       # in a fight and idle
assert 'ValidTarget(actor)' in ticked and 'Evaluate(actor' in ticked

# --- elites: a charmed elite's affixes keep running for the charmer, aimed at its former allies ----------------------------
update = body(ELITES, 'void OnUnitUpdate(Unit* unit, uint32) override')
assert '!elite->IsAlive() || !elite->IsInCombat())' in update and 'elite->IsAlive() || !elite->IsInCombat() || elite->IsCharmed()' not in update
assert 'AffixTick const tick{' in update                                                          # every affix aims through AffixTick
assert 'elite->IsCharmed() ? PickFoe(elite, reach) : Pick(reach)' in body(ELITES, 'Unit* AffixTick::Aim(float reach) const')
mortar = body(ELITES, 'void MortarTick(AffixTick const& t')
assert 'if (elite->IsCharmed())' in mortar and 'AffixFoesOf(elite)' in mortar
jailer = body(ELITES, 'void JailerTick(AffixTick const& t')
assert 'else if (elite->IsCharmed() && now >= pack->nextCastFor["jailer"])' in jailer and 'HoldFoe(elite, foe, JAILER_DEBUFF' in jailer
assert 'AffixFoesOf(elite)' in body(ELITES, 'void DesecratorTick(AffixTick const& t')
members = body(ELITES, 'PackMembers(Creature* leader, EliteState const& state)\n{')
assert 'IsCharmed' not in members                                                                   # a charmed member is in the pack again
assert 'std::vector<Unit*> AffixFoesOf(Unit* source);' in text('../monsters/dc_monster_ai.h')
foes = body(AI, 'std::vector<Unit*> AffixFoesOf(Unit* source)')
assert 'source->IsValidAttackTarget(creature)' in foes                                              # the charmer's side is never among them
assert 'if (source->IsCharmed())\n        ApplyHazardToFoes(source, h);' in body(ELITES, 'void ApplyHazard(Creature* source, Map* map, Hazard& h)')
assert 'if (source->IsCharmed())\n        ObservePoolContactFoes(source, h, now);' in body(ELITES, 'void ObservePoolContact(')
assert 'HazardTarget(map, h.target)' in body(ELITES, 'void MoveHazard(')
assert 'b->IsCharmed() && !a->IsCharmed()' in body(ELITES, 'void DrainHazards(Map* map)')           # a link with a charmed end serves the charmer

# --- a cluster does not drag a charmed member into its fight -------------------------------------------------------------
engaged = body(SPAWNER, 'void MemberEngaged(Creature* member, Unit* target)')
assert '!other->IsCharmed()' in engaged

# --- a charmed monster's kill is its charmer's rift kill -----------------------------------------------------------------
credit = body(QUESTS, 'static void CreditRiftKill(Player* killer, Creature* killed)')
for fragment in ('DCRiftIllusion', 'Current(killer, rift)', 'CompleteGuardianKill(killed, killer)', 'rift.state != "open"',
                 'AddProgress(killer, rift.id, KillUnits(killed, rift), 1);'):
    assert fragment in credit, fragment
hook = body(QUESTS, 'void OnPlayerCreatureKill(Player* killer, Creature* killed) override')
assert 'CreditRiftKill(killer, killed);' in hook and 'AddProgress' not in hook                      # one writer
charm_kills = body(QUESTS, 'class RiftCharmKills final : public UnitScript')
assert 'UNITHOOK_ON_UNIT_DEATH' in charm_kills and 'dead != body' in charm_kills
assert 'IsCharmedMonster(body)' in charm_kills and 'DC::Combat::CharmEffect::MasterOf(body)' in charm_kills   # the shared charm too
assert 'CreditRiftKill(master, dead);' in charm_kills
assert 'new RiftCharmKills();' in body(QUESTS, 'void RegisterQuestScripts()')

# --- the contract names what the code exports ----------------------------------------------------------------------------
contract = (ROOT / 'docs/contracts/legendary-world-pieces.md').read_text(encoding='utf-8')
for name in ('IsCharmedMonster', 'N-CHARM', 'RiftCharmKills', 'CreditRiftKill', 'MECHANIC_CHARM', 'a3ycm', 'AffixFoesOf', 'hdrct'):
    assert name in contract, name

print('PASS: N-CHARM: the charmed-monster rules, the AI park and restart, the Guardian, the pack, the elites, the cluster, the kill credit.')

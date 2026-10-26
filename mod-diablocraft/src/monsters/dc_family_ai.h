/*
 * World of DiabloCraft - the family AI (monster-families.md section 5 Part 3).
 *
 * One brain for every family monster. It runs the ability rows (dc_family_ability, joined to
 * dc_family_ability_ai) on top of the rift targeting AI: it picks the next ability whose trigger holds, winds it up as
 * a real stock cast so the bar shows, and strikes. The pure rules are in dc_family_ability.h.
 *
 * The brain holds no rift state and no pack state, so it also runs for a `.npc add` or `.dc lineup` monster on dev.
 * An ability aims at a position and a caster creature rather than at "me", so an invisible trigger creature can be
 * the caster later (trigger creatures for enemy scripting are planned).
 *
 * Internal to the rifts folder.
 */

#ifndef DC_FAMILY_AI_H
#define DC_FAMILY_AI_H

#include "dc_family_ability.h"

#include "ObjectGuid.h"

#include <cstdint>
#include <string>
#include <vector>

class ChatHandler;
class Creature;
class Player;
class SpellInfo;
class Unit;

namespace DC::Rifts::Family
{
    // The clones of a base entry are 8000000 + entry (champion) and 9000000 + entry (rare); the abilities belong to the
    // base entry. The base entries run 950001..950999.
    std::uint32_t BaseEntry(std::uint32_t entry);
    bool IsFamilyEntry(std::uint32_t entry);

    // The one target picker (conformance C3, D8): a valid player of `source` inside [minYd, maxYd], by `rule`. Null
    // when none. The family abilities and the elite affixes both choose through it, so a single-target ability never
    // lands on "whoever the chase happens to hold" by accident.
    Player* PickPlayer(Creature* source, Rule rule, float minYd, float maxYd, bool needLineOfSight);

    class Brain
    {
    public:
        explicit Brain(Creature* creature);

        void Engage();                   // compile the rows with today's numbers; new fight
        void Update(std::uint32_t diff); // every AI tick while the monster has a victim
        void OnSpellCast(SpellInfo const* spell);
        void OnSpellFailed(SpellInfo const* spell);
        void OnChannelFinished(SpellInfo const* spell);
        void OnMovement(std::uint32_t type, std::uint32_t id);
        void OnDamageDealt(Unit* victim, std::uint32_t damage, bool swing);
        void OnDeath();

        bool Busy() const
        {
            return _state != State::Idle;
        }
        bool CanSwing() const
        {
            return _hasSwing;
        }
        // How close the chase should stop: 0 for a monster that swings (the core's melee approach); a caster with no
        // swing keeps a fraction of its shortest reach.
        float ChaseDistance() const
        {
            return _standoff;
        }
        void Report(ChatHandler* handler) const;

    private:
        enum class State : std::uint8_t
        {
            Idle,
            Winding, // the donor cast (or its timer) is running
            Channeling,
            Moving // a charge or a leap is in the air
        };

        void Compile();
        void TryStart();
        void Begin(int index, Player* target);
        void Strike();
        void EndPhase();
        void Finish();
        bool CastDonor(Ability const& ability, Unit* target, bool ourNumber, bool instant);
        bool CastDonorAt(Ability const& ability, float x, float y, float z, bool ourNumber, bool instant);
        Unit* CastTargetOf(Ability const& ability, Player* target) const;
        void FireVolley(Ability const& ability);
        void Summon(Ability const& ability);
        void Land(Ability const& ability);
        void ResumeChase();
        void HitPlayers(Ability const& ability, float x, float y, float z, float radius);
        void HitCone(Ability const& ability, float length);
        void HitOne(Ability const& ability, Player* player);
        void PutGroundEffect(Ability const& ability, float x, float y, float z);
        double Damage(Ability const& ability) const;
        Player* Active() const;

        Creature* me;
        std::vector<Ability> _abilities;
        EventMap _events; // cooldowns, the idle scan and the phase deadline (dc_family_ability.h)
        State _state = State::Idle;
        int _active = -1;
        ObjectGuid _target;
        float _aimX = 0, _aimY = 0, _aimZ = 0;
        bool _castless = false, _firing = false, _hasSwing = false, _compiled = false, _riding = false;
        float _standoff = 0;
    };

    // The brain of a creature running the family AI, or null (defined where the AI class lives, dc_rift_ai.cpp).
    Brain* BrainOf(Creature* creature);

    void RegisterFamilyAiScripts();
} // namespace DC::Rifts::Family

#endif // DC_FAMILY_AI_H

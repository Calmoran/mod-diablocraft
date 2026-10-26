/*
 * The Shaman's totems. A Totems skill's record keeps the stock summon properties of its slot (fire, earth, water or
 * air): the core's own totem class, one totem a slot and a new one replacing the old, the model of the slot for the
 * Shaman's race. The cast sets the creature of the slot (data/d3/shaman_summons.csv) down at the Shaman's feet for the
 * skill's duration_seconds; the creature runs its skill's update (each totem skill's own file) and strikes as the
 * Shaman, as the Wizard's Hydra does. It is untargetable and the core's totem, so the monsters and the rifts already
 * count it as no monster, and it ends with the Shaman: on logout, on a change of floor, on death.
 */

#include "dc_shaman_totems.h"
#include "dc_shaman_common.h"
#include "dc_shaman_earthbind_totem.h"
#include "dc_shaman_healing_stream_totem.h"
#include "dc_shaman_searing_totem.h"
#include "dc_shaman_totems_math.h"
#include "DBCStores.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "ScriptMgr.h"
#include "ScriptedCreature.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "TemporarySummon.h"

#include <string_view>

namespace DC::Combat::Shaman::Totems
{
    namespace
    {
        // One look at a standing totem of the skill its record belongs to, `diff` milliseconds after the last.
        void Update(Player* player, Creature* totem, std::uint32_t source, State& state, std::uint32_t diff)
        {
            auto const* row = Shells::FindAbility(source);
            if (!row)
                return;
            if (std::string_view(row->skill) == "Searing Totem")
                Searing::Update(player, totem, source, state, diff);
            else if (std::string_view(row->skill) == "Earthbind Totem")
                Earthbind::Update(player, totem, source, state, diff);
            else if (std::string_view(row->skill) == "Healing Stream Totem")
                HealingStream::Update(player, totem, source, state, diff);
        }

        class TotemAI final : public ScriptedAI
        {
            ObjectGuid owner;
            std::uint32_t source = 0;
            State state;

        public:
            explicit TotemAI(Creature* creature)
                : ScriptedAI(creature)
            {
            }

            void IsSummonedBy(WorldObject* summoner) override
            {
                Player* player = summoner ? summoner->ToPlayer() : nullptr;
                if (!player)
                    return;
                owner = player->GetGUID();
                source = me->GetUInt32Value(UNIT_CREATED_BY_SPELL);
                me->SetFaction(player->GetFaction());
                me->SetLevel(player->GetLevel());
                me->SetReactState(REACT_PASSIVE);
            }

            void UpdateAI(uint32 diff) override
            {
                Player* player = ObjectAccessor::FindConnectedPlayer(owner);
                if (!player || !player->IsAlive() || !player->IsInMap(me))
                {
                    if (TempSummon* summon = me->ToTempSummon())
                        summon->UnSummon();
                    return;
                }
                if (source)
                    Update(player, me, source, state, diff);
            }
        };

        class TotemScript final : public CreatureScript
        {
        public:
            TotemScript()
                : CreatureScript("dc_shaman_totem")
            {
            }

            CreatureAI* GetAI(Creature* creature) const override
            {
                return new TotemAI(creature);
            }
        };

        class Owner final : public PlayerScript
        {
        public:
            Owner()
                : PlayerScript("dc_shaman_totems", {PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerLogout(Player* player) override
            {
                Away(player);
            }

            void OnPlayerMapChanged(Player* player) override
            {
                Away(player);
            }
        };
    } // namespace

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!IsShaman(player) || Classes::CategoryOf(spellId) != "Totems")
            return;
        // A rune places its skill's totem: the slot is the skill's own record's (a rune record keeps the stock summon
        // of its donor).
        auto const* cast = Shells::FindAbility(spellId);
        SpellInfo const* info = cast ? sSpellMgr->GetSpellInfo(BaseId(cast->skill)) : nullptr;
        SummonPropertiesEntry const* properties =
            info ? sSummonPropertiesStore.LookupEntry(info->Effects[EFFECT_0].MiscValueB) : nullptr;
        std::uint32_t const entry = properties ? EntryOfSlot(properties->Slot) : 0;
        std::uint32_t const duration = DurationMs(Numbers::Num(spellId, "duration_seconds"));
        if (!entry || !duration)
            return;
        // At the Shaman's feet, never at range; the core puts the old totem of the slot away.
        player->GetMap()->SummonCreature(entry, player->GetPosition(), properties, duration, player, spellId);
    }

    Creature* Totem(Player const* player, unsigned slot)
    {
        if (!player || slot < FireSlot || slot > AirSlot || !player->m_SummonSlot[slot] || !player->GetMap())
            return nullptr;
        Creature* totem = player->GetMap()->GetCreature(player->m_SummonSlot[slot]);
        return totem && totem->IsAlive() ? totem : nullptr;
    }

    std::uint32_t Standing(Player const* player, unsigned slot)
    {
        Creature* totem = Totem(player, slot);
        return totem ? totem->GetUInt32Value(UNIT_CREATED_BY_SPELL) : 0;
    }

    void Away(Player* player)
    {
        for (unsigned slot = FireSlot; slot <= AirSlot; ++slot)
            if (player->m_SummonSlot[slot])
                if (Creature* totem = player->GetMap()->GetCreature(player->m_SummonSlot[slot]);
                    totem && totem->IsSummon())
                    totem->ToTempSummon()->UnSummon();
    }

    void RegisterScripts()
    {
        new TotemScript();
        new Owner();
    }
} // namespace DC::Combat::Shaman::Totems

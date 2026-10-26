#include "dc_wizard_hydra.h"
#include "../../combat/dc_item_powers.h"
#include "ObjectAccessor.h"
#include "ScriptedCreature.h"
#include "SpellMgr.h"
#include "Map.h"
#include "TemporarySummon.h"
#include <algorithm>
#include <cmath>
#include <numbers>

namespace DC::Combat::Wizard::Hydra
{
    using namespace Shared;

    namespace
    {
        // The Hydra, a stock totem summon (one at a time, gone after the
        // record's duration). It attacks on D3's cadence: floor(base frames
        // / attack speed) rounded up to the step (wizard.js:584-585), 60
        // frames a second, projectile_count bolts at the nearest enemy
        // within its range (:609).
        class HydraAI final : public ScriptedAI
        {
            ObjectGuid owner;
            uint32 source = 0, clock = 0;

        public:
            explicit HydraAI(Creature* creature)
                : ScriptedAI(creature)
            {
            }

            void IsSummonedBy(WorldObject* summoner) override
            {
                Player* player = summoner ? summoner->ToPlayer() : nullptr;
                if (!player)
                    return;
                owner = player->GetGUID();
                for (Row const& row : Shells::Abilities)
                    if (IsSkill(row.id, "Hydra"))
                        if (SpellInfo const* info = sSpellMgr->GetSpellInfo(row.id);
                            info && uint32(info->Effects[EFFECT_0].MiscValue) == me->GetEntry())
                            source = row.id;
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
                // Mammoth Hydra's river of flame has no carrier yet (reported
                // blocked): it does not attack.
                if (!source || IsRune(source, "Mammoth Hydra"))
                    return;
                // Tasker and Theo: the item powers' pet attack speed (1 when none) on the owner's attacks per second.
                double const aps = Combat::AttacksPerSecond(player, source) * Combat::ItemPowers::PetSpeedFactor(player);
                double const step = Num(source, "attack_frames_count", "step");
                if (aps <= 0 || step <= 0)
                    return;
                double const frames = std::ceil(std::floor(Num(source, "attack_frames_count") / aps) / step) * step;
                clock += diff;
                if (clock < frames / 60 * 1000)
                    return;
                clock = 0;
                // Arcane and Blazing Hydra state their own radius_yards, the
                // area their attack covers; the range is the base's.
                bool const area = IsRune(source, "Arcane Hydra") || IsRune(source, "Blazing Hydra");
                double const range =
                    area ? Numbers::Inherited(source, "radius_yards").value_or(0) : Num(source, "radius_yards");
                auto enemies = Combat::Enemies(player, source, me->GetPosition(), range);
                if (enemies.empty())
                    return;
                Unit* target = *std::min_element(enemies.begin(), enemies.end(), [this](Unit* a, Unit* b)
                                                 { return me->GetExactDist(a) < me->GetExactDist(b); });
                me->SetFacingToObject(target);
                // Frost Hydra: "breathes a short range cone of frost" -
                // radius_yards long, cone_width_degrees across in all, the
                // simulator's count of three per attack (wizard.js:621,
                // math.js:489).
                if (IsRune(source, "Frost Hydra"))
                {
                    float const arc = float(Num(source, "cone_width_degrees") * std::numbers::pi / 180);
                    unsigned const breaths = unsigned(Num(source, "projectile_count"));
                    if (arc <= 0)
                        return;
                    for (Unit* enemy : enemies)
                        if (me->HasInArc(arc, enemy))
                            for (unsigned i = 0; i < breaths; ++i)
                                Combat::Strike(player, enemy, source);
                    return;
                }
                if (area)
                {
                    Combat::StrikeArea(player, source, target->GetPosition(),
                                       Numbers::Own(source, "radius_yards").value_or(0));
                    return;
                }
                unsigned const bolts =
                    IsRune(source, "Lightning Hydra") ? 1 : unsigned(Num(source, "projectile_count"));
                for (unsigned i = 0; i < bolts; ++i)
                    Combat::Strike(player, target, source);
            }
        };

        // Whether `entry` is a Hydra's creature: a Hydra record's SUMMON names it (as HydraAI finds its source).
        bool IsHydraEntry(uint32 entry)
        {
            for (Row const& row : Shells::Abilities)
                if (IsSkill(row.id, "Hydra"))
                    if (SpellInfo const* info = sSpellMgr->GetSpellInfo(row.id);
                        info && uint32(info->Effects[EFFECT_0].MiscValue) == entry)
                        return true;
            return false;
        }

        class Summons final : public PlayerScript
        {
        public:
            Summons()
                : PlayerScript("dc_wizard_hydra_summons", {PLAYERHOOK_ON_BEFORE_TEMP_SUMMON_INIT_STATS})
            {
            }

            // N-HYDRA, "You may have one extra Hydra active at a time". The record's totem slot keeps one Hydra
            // (TempSummon::InitStats unsummons the slot's holder right after this hook); the Wizard may have the core's one
            // plus the items' extra (ItemPowers::ActiveCount) up at once, so the oldest past that go here and the slot is
            // cleared, the survivors then lasting their own time. With no item it is the core's one Hydra.
            void OnPlayerBeforeTempSummonInitStats(Player* player, TempSummon* summon, uint32&) override
            {
                if (!summon || !IsHydraEntry(summon->GetEntry()))
                    return;
                unsigned const cap = unsigned(std::max(0.0, ItemPowers::ActiveCount(player, "Hydra", 1)));
                std::vector<ObjectGuid> dismissed;
                {
                    std::lock_guard<std::recursive_mutex> guard(mutex);
                    std::vector<ObjectGuid>& up = StateOf(player).hydras;
                    up.erase(std::remove_if(up.begin(), up.end(),
                                            [player](ObjectGuid guid)
                                            {
                                                Creature* hydra = player->GetMap()->GetCreature(guid);
                                                return !hydra || !hydra->IsAlive();
                                            }),
                             up.end());
                    std::size_t const gone = ItemPower::Dismissed(up.size(), cap);
                    dismissed.assign(up.begin(), up.begin() + gone);
                    up.erase(up.begin(), up.begin() + gone);
                    up.push_back(summon->GetGUID());
                }
                for (ObjectGuid guid : dismissed)
                    if (Creature* hydra = player->GetMap()->GetCreature(guid); hydra && hydra->IsSummon())
                        hydra->ToTempSummon()->UnSummon();
                if (uint32 const slot = summon->m_Properties ? summon->m_Properties->Slot : 0; slot && slot < MAX_SUMMON_SLOT)
                    player->m_SummonSlot[slot].Clear();
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new Summon<HydraAI>("dc_wizard_hydra");
        new Summons();
    }
} // namespace DC::Combat::Wizard::Hydra

/*
 * Sacrifice and its five runes. The cast is the engine's ground cast (a spell record and the sheet's numbers: the
 * radius, each rune's school; no cost and no cooldown); here: it needs a Zombie Dog, which it banishes (all of them for
 * For the Master) and which explodes at the point aimed at, and each rune's part: Provoke the Pack's damage done, Black
 * Blood's stun, Pride's Mana, Next of Kin's returning dog.
 */

#include "dc_witch_doctor_sacrifice.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "dc_witch_doctor_mana.h"
#include "dc_witch_doctor_pets.h"
#include "../dc_classes.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_minions.h"
#include "../../combat/dc_spell_numbers.h"
#include "GameTime.h"
#include "Player.h"
#include "Position.h"
#include "Random.h"
#include "Unit.h"

#include <chrono>
#include <mutex>
#include <unordered_map>
#include <vector>

namespace DC::Combat::WitchDoctor::Sacrifice
{
    namespace
    {
        constexpr std::string_view Skill = "Sacrifice";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // Provoke the Pack: the damage done a Witch Doctor has and until when.
        struct Bonus
        {
            std::uint64_t until = 0;
            double pct = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Bonus> bonuses;

        // The explosions: every dog banished explodes on the enemies within the radius of the point, and Black Blood's
        // ichor stuns them.
        void Explode(Player* player, std::uint32_t spellId, Position const& center, unsigned dogs)
        {
            auto const enemies = Combat::Enemies(player, spellId, center, Numbers::Num(spellId, "radius_yards"));
            // For the Master states each dog's damage as its own; the others' is the skill's.
            double const pct = Numbers::Num(spellId, "damage_pct");
            for (Unit* enemy : enemies)
                for (unsigned dog = 0; dog < dogs; ++dog)
                    Combat::Strike(player, enemy, spellId, pct);
            if (RuneAt(spellId) == Rune::BlackBlood)
                for (Unit* enemy : enemies)
                    Stun(player, enemy,
                         Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Ground(Player* player, std::uint32_t spellId, Position const& center)
    {
        if (!player || !Is(spellId))
            return;
        Rune const rune = RuneAt(spellId);
        // "needs an active Zombie Dog, which it consumes": the oldest, or every one.
        std::vector<Position> banished;
        for (unsigned want = Sacrificed(rune, Minions::Alive(player, "dog")); want > 0; --want)
            if (auto const at = Pets::SacrificeDog(player))
                banished.push_back(*at);
        if (banished.empty())
            return;
        unsigned const dogs = unsigned(banished.size());
        player->m_Events.AddEventAtOffset(
            [player, spellId, center, dogs]
            {
                if (player->IsAlive() && player->IsInWorld())
                    Explode(player, spellId, center, dogs);
            },
            std::chrono::milliseconds(std::uint32_t(Tune("sacrifice_explode_delay_seconds") * 1000.0 + 0.5)));
        switch (rune)
        {
            case Rune::ProvokeThePack:
            {
                std::lock_guard<std::mutex> guard(mutex);
                bonuses[player->GetGUID().GetRawValue()] = {
                    BonusUntil(Now(), Numbers::Num(spellId, "duration_seconds")),
                    Numbers::Num(spellId, "damage_bonus_pct")};
                break;
            }
            case Rune::Pride:
                Gain(player, Classes::ClassIdOf(player), spellId,
                     PrideMana(Numbers::Num(spellId, "gain_resource"), dogs), 1);
                break;
            case Rune::NextOfKin:
                for (Position const& at : banished)
                    if (Resurrects(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct")))
                        Minions::Raise(player, "zombie_dog", at);
                break;
            default:
                break;
        }
    }

    void Multipliers(Player* player, DC::Combat::Factors& out)
    {
        if (!player)
            return;
        Bonus bonus;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto const found = bonuses.find(player->GetGUID().GetRawValue());
            if (found == bonuses.end())
                return;
            bonus = found->second;
        }
        // "Gain {damage_bonus_pct} increased damage done": one multiplier of its own on every hit.
        if (BonusOn(Now(), bonus.until) && bonus.pct > 0)
            AddFactor(out, "Provoke the Pack", bonus.pct);
    }
} // namespace DC::Combat::WitchDoctor::Sacrifice

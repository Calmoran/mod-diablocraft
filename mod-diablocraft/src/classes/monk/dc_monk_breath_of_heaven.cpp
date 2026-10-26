/*
 * Breath of Heaven and its five runes. The shape is Power/Monk_BreathOfHeaven.pow: a heal on the Monk and
 * the allies within SF_4 12 yards, and the rune's own change.
 */

#include "dc_monk_breath_of_heaven_cast.h"
#include "dc_monk_common.h"
#include "dc_monk_breath_of_heaven.h"
#include "dc_monk_spirit.h"
#include "../dc_level_heal.h"
#include "SpellAuraEffects.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Util.h"

namespace DC::Combat::Monk::Breath
{
    namespace
    {
        constexpr std::string_view Skill = "Breath of Heaven";
        // Stock "Speed" (14530): one MOD_INCREASE_SPEED effect on the target itself; Zephyr's speed, set to the sheet's
        // percentage and seconds.
        constexpr std::uint32_t Hasted = 14530;

        Shells::Ability const* Row(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        bool IsRune(std::uint32_t spellId, std::string_view rune)
        {
            auto const* row = Row(spellId);
            return row && rune == row->rune;
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // Infused with Light, per Monk: the rune's spell and when its window ends.
        struct Window
        {
            std::uint32_t spellId = 0;
            std::uint64_t until = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Window> windows;

        void Heal(Player* caster, Unit* target, std::uint32_t spellId, double amount)
        {
            if (!target->IsAlive() || amount <= 0)
                return;
            if (SpellInfo const* info = sSpellMgr->GetSpellInfo(spellId))
            {
                HealInfo heal(caster, target, uint32(std::min(amount, double(UINT32_MAX))), info,
                              SPELL_SCHOOL_MASK_HOLY);
                caster->HealBySpell(heal);
            }
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !Row(spellId))
            return;
        // "heals you and all allies within {radius_yards} yards for {heal_min_life} - {heal_max_life} Life": the
        // targets the cast resolved (self_allies), each healed by its own roll. Circle of Life states both bounds
        // itself; the others inherit the skill's. The Health Globe Healing Bonus has no stat yet: 0.
        double const minLife = Classes::HealAtLevel(Numbers::Num(spellId, "heal_min_life"), player->GetLevel()),
                     maxLife = Classes::HealAtLevel(Numbers::Num(spellId, "heal_max_life"), player->GetLevel()),
                     share = Numbers::Num(spellId, "healing_bonus_share_pct");
        for (Unit* ally : targets)
            Heal(player, ally, spellId, HealAmount(minLife, maxLife, rand_norm(), share, 0.0));

        // Circle of Scorn: "also sears enemies for {damage_pct} weapon damage as Holy" - the enemies within the same
        // radius.
        if (IsRune(spellId, "Circle of Scorn"))
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"));

        // Blazing Wrath: "increases the damage of your attacks by {damage_bonus_pct} for {duration_seconds} seconds".
        if (IsRune(spellId, "Blazing Wrath"))
            Effects::Dealt(player, spellId, Numbers::Num(spellId, "damage_bonus_pct"),
                           Numbers::Num(spellId, "duration_seconds"));

        // Infused with Light: the window opens (a new cast starts it over).
        if (IsRune(spellId, "Infused with Light"))
        {
            std::lock_guard<std::mutex> guard(mutex);
            windows[player->GetGUID().GetRawValue()] = {
                spellId, Now() + std::uint64_t(Numbers::Num(spellId, "duration_seconds") * 1000)};
        }

        // Zephyr: "Allies healed by Breath of Heaven have their movement speed increased by {movement_speed_pct} for
        // {duration_seconds} seconds": everyone the heal reached.
        if (IsRune(spellId, "Zephyr"))
        {
            double const seconds = Numbers::Num(spellId, "duration_seconds");
            for (Unit* ally : targets)
            {
                if (!ally->IsAlive() || seconds <= 0)
                    continue;
                ally->RemoveAurasDueToSpell(Hasted);
                if (Aura* haste = ally->AddAura(Hasted, ally))
                {
                    if (AuraEffect* effect = haste->GetEffect(EFFECT_0))
                        effect->ChangeAmount(SpeedAmount(Numbers::Num(spellId, "movement_speed_pct")));
                    haste->SetMaxDuration(int32(seconds * 1000));
                    haste->SetDuration(int32(seconds * 1000));
                }
            }
        }
    }

    void Attack(Player* player, bool generates)
    {
        if (!player || !generates)
            return;
        std::uint32_t spellId = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = windows.find(player->GetGUID().GetRawValue());
            if (found == windows.end())
                return;
            if (!InWindow(Now(), found->second.until))
            {
                windows.erase(found);
                return;
            }
            spellId = found->second.spellId;
        }
        // "Gain {gain_resource} additional Spirit from Spirit generating attacks": once per attack.
        Generate(player, Classes::ClassIdOf(player), spellId,
                 ExtraSpirit(true, generates, Numbers::Num(spellId, "gain_resource")));
    }
} // namespace DC::Combat::Monk::Breath

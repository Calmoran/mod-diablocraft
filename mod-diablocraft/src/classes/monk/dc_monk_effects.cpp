/*
 * The Monk's timed effects (dc_monk_effects.h).
 */

#include "dc_monk_common.h"
#include "dc_monk_effects.h"
#include "../../combat/dc_enemy_effects.h"

namespace DC::Combat::Monk
{
    namespace
    {
        std::mutex mutex;
        Ledger dealt;    // by Monk guid
        Ledger taken;    // by enemy guid
        Ledger weakened; // by enemy guid

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::uint64_t Millis(double seconds)
        {
            return std::uint64_t(seconds * 1000.0 + 0.5);
        }
    } // namespace

    namespace Effects
    {
        void Dealt(Player* player, std::uint32_t key, double pct, double seconds, unsigned maxStacks)
        {
            if (!player || seconds <= 0)
                return;
            std::lock_guard<std::mutex> guard(mutex);
            auto const now = Now();
            dealt.Of(player->GetGUID().GetRawValue(), now).Apply(key, pct, now, Millis(seconds), maxStacks);
        }

        void Taken(Unit* enemy, std::uint32_t key, double pct, double seconds, unsigned maxStacks)
        {
            if (!enemy || seconds <= 0)
                return;
            std::lock_guard<std::mutex> guard(mutex);
            auto const now = Now();
            taken.Of(enemy->GetGUID().GetRawValue(), now).Apply(key, pct, now, Millis(seconds), maxStacks);
        }

        void Weaken(Unit* enemy, std::uint32_t key, double pct, double seconds, unsigned maxStacks)
        {
            if (!enemy || seconds <= 0)
                return;
            std::lock_guard<std::mutex> guard(mutex);
            auto const now = Now();
            weakened.Of(enemy->GetGUID().GetRawValue(), now).Apply(key, pct, now, Millis(seconds), maxStacks);
        }

        void Remove(Unit* enemy, std::uint32_t key)
        {
            if (!enemy)
                return;
            std::lock_guard<std::mutex> guard(mutex);
            if (Book* book = taken.Peek(enemy->GetGUID().GetRawValue()))
                book->Remove(key);
            if (Book* book = weakened.Peek(enemy->GetGUID().GetRawValue()))
                book->Remove(key);
        }

        unsigned DealtStacks(Player* player, std::uint32_t key)
        {
            if (!player)
                return 0;
            std::lock_guard<std::mutex> guard(mutex);
            Book* book = dealt.Peek(player->GetGUID().GetRawValue());
            return book ? book->Stacks(key, Now()) : 0;
        }
    } // namespace Effects

    double DamageBonus(Player* player, Unit* /*target*/, std::uint32_t /*spellId*/)
    {
        if (!player)
            return 0;
        double const ally = MysticAlly::DamageBonus(player); // Fire Ally's Passive, the same bucket
        std::lock_guard<std::mutex> guard(mutex);
        Book* book = dealt.Peek(player->GetGUID().GetRawValue());
        return ally + (book ? book->Total(Now()) : 0);
    }

    double TargetBonus(Player* /*player*/, Unit* target)
    {
        if (!target)
            return 0;
        std::lock_guard<std::mutex> guard(mutex);
        Book* book = taken.Peek(target->GetGUID().GetRawValue());
        return book ? book->Total(Now()) : 0;
    }

    double IncomingFactor(Unit* attacker)
    {
        if (!attacker)
            return 1.0;
        std::lock_guard<std::mutex> guard(mutex);
        Book* book = weakened.Peek(attacker->GetGUID().GetRawValue());
        return book ? book->LessFactor(Now()) : 1.0;
    }
} // namespace DC::Combat::Monk

namespace DC::Combat::EnemyEffects
{
    void Taken(Unit* enemy, std::uint32_t key, double pct, double seconds, unsigned maxStacks)
    {
        Monk::Effects::Taken(enemy, key, pct, seconds, maxStacks);
    }

    void Weaken(Unit* enemy, std::uint32_t key, double pct, double seconds, unsigned maxStacks)
    {
        Monk::Effects::Weaken(enemy, key, pct, seconds, maxStacks);
    }

    void Remove(Unit* enemy, std::uint32_t key)
    {
        Monk::Effects::Remove(enemy, key);
    }
} // namespace DC::Combat::EnemyEffects

#pragma once
// The Necromancer's passives that need code: Life from Death, Fueled by Death, Stand Alone, Bone Prison, Swift
// Harvesting, Commander of the Risen Dead; Extended Servitude, Rigor Mortis, Overwhelming Essence, Dark Reaping,
// Spreading Malediction, Eternal Torment, Final Service. The rules that need no core type are
// dc_necromancer_passives_math.h; the numbers are necromancer_passive_values.csv (skill = the passive's name) and the
// power files, read through each passive's record.
#include "../../combat/dc_damage_buckets.h"

#include <cstdint>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::Necromancer::Passive
{
    // A hit of `spellId` landed on `target`: Bone Prison's stun, Rigor Mortis' slow.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The attacks per second `base` of `spellId` after Swift Harvesting.
    double AttackSpeed(Player* player, std::uint32_t spellId, double base);
    // The hit of `spellId` on `target` being computed: Spreading Malediction's and Serration's bonus.
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);
    // A cast of `spellId` began (before the cost): Rathma's Shield opens.
    void Casting(Player* player, std::uint32_t spellId);
    // Whether the Necromancer cannot lose Life now (Rathma's Shield).
    bool LifeLocked(Player* player);
    // A Life cost is about to be paid: true when Blood for Blood's stack pays it.
    bool WaivesLifeCost(Player* player);
    // `amount` of Life was lost (a blow, a cost): Blood Is Power counts it.
    void LifeLost(Player* player, double amount);
    // The Necromancer picked up a health globe (Blood for Blood's stack); the globes call it when they land.
    void GlobePicked(Player* player);
    // The damage `victim` takes after the passives (Rathma's Shield, Final Service's sustain).
    double Reduce(Unit* victim, double damage);
    // What the time of the minions of the skill `skill` is multiplied by (Extended Servitude).
    double DurationFactor(Player* player, std::string_view skill);
    // The seconds a curse of `seconds` stands (Eternal Torment: it lasts forever).
    double CurseSeconds(Player* player, double seconds);
    // The corpse listeners, the update script and the cast hook; at startup.
    void Register();
} // namespace DC::Combat::Necromancer::Passive

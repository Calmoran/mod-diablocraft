#pragma once
// The Necromancer's curses (Decrepify, Leech, Frailty): an enemy bears one curse of a Necromancer at a time, and the newest
// replaces it (all three stand together while the Necromancer's curses are allowed to). This file keeps which curse is on which enemy and ends the old curse's effects when another takes its place; each
// curse's skill says how its effects end (Define) and puts them on (Put). The shape of the Threatening Shout precedent, for three
// skills of one category.
#include <cstdint>
#include <string_view>
#include <utility>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Necromancer::Curses
{
    // How a curse skill takes its effects off `enemy` before their time (`spellId` is the record that put them).
    using Lift = void (*)(Player* player, Unit* enemy, std::uint32_t spellId);

    // The skill's way of lifting its curse; once at startup.
    void Define(std::string_view skill, Lift lift);

    // `spellId`'s curse is put on `enemy` for `seconds`. A curse of the Necromancer's already on the enemy, of another record, is lifted:
    // the newest replaces it.
    void Put(Player* player, Unit* enemy, std::uint32_t spellId, double seconds);

    // Whether `player`'s curses stand together on an enemy instead of replacing each other; once at startup.
    using Together = bool (*)(Player* player);
    void StandTogether(Together together);

    // The record of the curse the Necromancer has on `enemy` now, 0 when none; of the `skill`'s curse when it is given.
    std::uint32_t On(Player* player, Unit const* enemy, std::string_view skill = {});

    // How many living enemies the Necromancer has cursed now.
    unsigned Cursed(Player* player);

    // The living enemies the Necromancer has cursed now, with the record of each curse (an enemy twice when it bears two).
    std::vector<std::pair<Unit*, std::uint32_t>> CursedBy(Player* player);

    // The seconds the curse on `enemy` has left, 0 when none; of the `skill`'s curse when it is given.
    double Left(Player* player, Unit const* enemy, std::string_view skill = {});

    // Every Necromancer with a curse on `enemy` now, with the record of it (a cursed enemy that dies is theirs to answer).
    std::vector<std::pair<Player*, std::uint32_t>> Cursers(Unit const* enemy);

    // A number that follows how many enemies are cursed (Opportunist's speed, Osmosis' regeneration): `apply` is called with the
    // count at once and every second while any enemy stays cursed, and with 0 when the last is gone. One follower to a `group`
    // (a skill) for each Necromancer; a new one of another record takes the old one's number off first.
    using Apply = void (*)(Player* player, std::uint32_t spellId, unsigned cursed);
    void Follow(Player* player, std::string_view group, std::uint32_t spellId, Apply apply);
    // Takes the group's follower off with its number.
    void Unfollow(Player* player, std::string_view group);
} // namespace DC::Combat::Necromancer::Curses

/*
 * World of DiabloCraft - hardcore (11-hardcore §2-§4).
 *
 * Public surface of the hardcore folder. Other folders include only this header.
 *
 * This is the header 10-paragon P3 reads for its pool: paragon calls IsHardcore
 * and picks the hardcore pool for a hardcore character. The hardcore folder
 * never reaches into paragon, stash or currency - they ask, it answers.
 */

#ifndef DC_HARDCORE_H
#define DC_HARDCORE_H

#include <cstdint>
#include <string>

class Player;

namespace DC::Hardcore
{
// 11 §2. A character has no mode until its first login writes one; Unchosen is
// what every character is between creation and that login, and the 08 §5
// starter kit is handed out in the same call that writes the row.
enum class Mode { Unchosen, Normal, Hardcore };

Mode ModeOf(std::uint32_t guid);
Mode ModeOf(Player const* player);

// H2/P3. The one question the other folders ask. An unchosen character is not
// hardcore, so anything that reads it before the prompt is answered gets the
// normal pool - which is also what a character that never answers keeps.
bool IsHardcore(Player const* player);

// 11 H4: Normal and Hardcore are separate realms, so the mode
// is a property of the realm and not a question put to the player. This is what
// Diablocraft.Hardcore.Enable says this realm is - Hardcore when 1.
Mode RealmMode();

// 08 §5 gate, and the writer on the ordinary path. Writes this character's
// dc_character_mode row from RealmMode() if it has none, and answers whether a
// row exists afterwards, which is what the starter kit waits for. The row is
// still written once and never rewritten: a character that already has one is
// left exactly as it is.
//
// It is not the only INSERT of that row - `.dc mode choose` is the second, a
// GM repair for a character that has none - but the two are the same statement
// and neither can overwrite an existing row.
bool EnsureMode(Player* player);

// A8 (stash). The death the core has killed but not yet written: OnPlayerJustDied
// records it and the next player update writes the lock, so between those two
// moments IsLocked is still false. Anything that must refuse a dead hardcore
// character - the account stash above all - asks this as well as IsLocked.
bool DeathPending(Player const* player);

// H1. True when this character is a dead hardcore one; the login guard and the
// GM command both read it.
bool IsLocked(std::uint32_t guid);

void RegisterScripts();
}

#endif // DC_HARDCORE_H

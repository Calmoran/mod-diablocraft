/*
 * World of DiabloCraft - `.dc lineup [family]`. Summons a family's picked monsters
 * (dc_monster_family, generate_monster_models.py) in a row in front of the GM for LINEUP_SECONDS; with no
 * family it lists the families that have any. Temporary summons: nothing is saved and no rift knows them.
 */

#include "dc_family_lineup.h"

#include "Chat.h"
#include "ChatCommand.h"
#include "DatabaseEnv.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "WorldSession.h"

#include <string>
#include <vector>

namespace DC::Rifts
{
    namespace
    {
        class FamilyLineupCommand final : public CommandScript
        {
        public:
            FamilyLineupCommand()
                : CommandScript("dc_family_lineup_command")
            {
            }
            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable dc = {{"lineup", HandleLineup, SEC_GAMEMASTER, Console::No}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }

            static bool HandleLineup(ChatHandler* handler, Optional<std::string> family)
            {
                Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!player)
                    return false;
                if (!family)
                {
                    QueryResult families = WorldDatabase.Query("SELECT family, COUNT(*) FROM dc_monster_family GROUP BY family ORDER BY family");
                    if (!families)
                    {
                        handler->SendSysMessage("No family monsters are in the database yet (monsters_0001_family_models.sql).");
                        return true;
                    }
                    do
                        handler->PSendSysMessage("{}: {} monsters", (*families)[0].Get<std::string>(), (*families)[1].Get<uint64>());
                    while (families->NextRow());
                    return true;
                }
                std::string escaped = *family;
                WorldDatabase.EscapeString(escaped);
                QueryResult rows = WorldDatabase.Query("SELECT entry, monster FROM dc_monster_family WHERE family='{}' ORDER BY entry LIMIT {}",
                                                       escaped, LINEUP_MAX);
                if (!rows)
                {
                    handler->PSendSysMessage("No family called '{}'. `.dc lineup` lists them.", *family);
                    return false;
                }
                std::vector<std::pair<uint32, std::string>> monsters;
                do
                    monsters.emplace_back((*rows)[0].Get<uint32>(), (*rows)[1].Get<std::string>());
                while (rows->NextRow());
                for (unsigned index = 0; index < monsters.size(); ++index)
                {
                    LineupSpot const spot = LineupAt(index, monsters.size(), player->GetPositionX(), player->GetPositionY(),
                                                     player->GetOrientation());
                    float z = player->GetPositionZ();
                    player->UpdateGroundPositionZ(spot.x, spot.y, z);
                    if (player->SummonCreature(monsters[index].first, spot.x, spot.y, z, spot.facing,
                                               TEMPSUMMON_TIMED_DESPAWN, LINEUP_SECONDS * 1000))
                        handler->PSendSysMessage("{}: {} ({})", index + 1, monsters[index].second, monsters[index].first);
                    else
                        handler->PSendSysMessage("{} ({}) could not be summoned.", monsters[index].second, monsters[index].first);
                }
                return true;
            }
        };
    } // namespace

    void RegisterFamilyLineupScripts()
    {
        new FamilyLineupCommand();
    }
} // namespace DC::Rifts

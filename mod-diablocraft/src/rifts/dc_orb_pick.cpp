// `.dc orbrow`, the stock orb pick round's command (rules and the candidate list in dc_orb_pick.h).
#include "dc_orb_pick.h"
#include "Chat.h"
#include "CommandScript.h"
#include "GameObject.h"
#include "Map.h"
#include "Player.h"
#include "ScriptMgr.h"
#include <mutex>
#include <unordered_map>
#include <vector>

namespace DC::OrbPick
{
    namespace
    {
        std::mutex rowsMutex;
        std::unordered_map<ObjectGuid, std::vector<ObjectGuid>> rows; // per GM: the row standing, if any

        // What Map::SummonGameObject does for a temporary object, except that the copy's display and scale are set
        // before AddToMap: the 3.3.5 client reads a gameobject's display from the create packet only (it has no handler
        // for a later GAMEOBJECT_DISPLAYID change), so a SetDisplayId after the add is right on the server and every
        // copy would draw the template's look.
        GameObject* Spawn(Map* map, Candidate const& candidate, Spot spot, float z, float orientation)
        {
            GameObject* object = new GameObject();
            if (!object->Create(map->GenerateLowGuid<HighGuid::GameObject>(), CandidateObject, map, PHASEMASK_NORMAL,
                                spot.x, spot.y, z, orientation, G3D::Quat(0, 0, 0, 0), 100, GO_STATE_READY))
            {
                delete object;
                return nullptr;
            }
            object->SetDisplayId(candidate.display);
            object->SetObjectScale(candidate.scale);
            object->SetRespawnTime(0);
            object->SetSpawnedByDefault(false);
            map->AddToMap(object);
            // Unchanged, so no packet; UpdateModel returns early before the add and this rebuilds the collision model.
            object->SetDisplayId(candidate.display);
            return object;
        }

        class Command final : public CommandScript
        {
        public:
            Command()
                : CommandScript("dc_orb_pick_command")
            {
            }

            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                static ChatCommandTable dc = {{"orbrow", Row, SEC_GAMEMASTER, Console::No}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }

            // .dc orbrow: the row in front of the GM; again: the row goes.
            static bool Row(ChatHandler* handler)
            {
                Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!player)
                    return false;
                Map* map = player->GetMap();
                std::vector<ObjectGuid> standing;
                {
                    std::lock_guard<std::mutex> guard(rowsMutex);
                    if (auto found = rows.find(player->GetGUID()); found != rows.end())
                    {
                        standing = found->second;
                        rows.erase(found);
                    }
                }
                if (!standing.empty())
                {
                    for (ObjectGuid const& guid : standing)
                        if (GameObject* object = map->GetGameObject(guid))
                            object->DespawnOrUnsummon();
                    handler->PSendSysMessage("Orb row removed.");
                    return true;
                }
                float const o = player->GetOrientation();
                std::vector<ObjectGuid> spawned;
                std::string labels;
                for (std::size_t i = 0; i < Candidates.size(); ++i)
                {
                    Candidate const& candidate = Candidates[i];
                    Spot const spot = Place(player->GetPositionX(), player->GetPositionY(), o, i, Candidates.size());
                    float const z =
                        map->GetHeight(player->GetPhaseMask(), spot.x, spot.y, player->GetPositionZ() + 2.0f);
                    GameObject* object =
                        Spawn(map, candidate, spot, (z > INVALID_HEIGHT ? z : player->GetPositionZ()) + candidate.lift,
                              o + float(M_PI));
                    if (!object)
                    {
                        handler->PSendSysMessage(
                            "No orb row: gameobject {} is missing (apply world_0052_world_objects.sql).",
                            CandidateObject);
                        for (ObjectGuid const& guid : spawned)
                            if (GameObject* made = map->GetGameObject(guid))
                                made->DespawnOrUnsummon();
                        return true;
                    }
                    object->DespawnOrUnsummon(std::chrono::seconds(LifetimeSeconds));
                    spawned.push_back(object->GetGUID());
                    labels += Acore::StringFormat("\n{}) {} {}{}", i + 1, candidate.display, candidate.label,
                                                  candidate.needsPatch ? " [needs the Nightly patch]" : "");
                }
                {
                    std::lock_guard<std::mutex> guard(rowsMutex);
                    rows[player->GetGUID()] = spawned;
                }
                handler->PSendSysMessage(
                    "Orb row, left to right (display id, look):{}\n.dc orbrow again removes it; it goes by "
                    "itself in {} minutes.",
                    labels, LifetimeSeconds / 60);
                return true;
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new Command();
    }
} // namespace DC::OrbPick

// NPC outfits: the table loader, the creature flag and the mirror-image answer. The bytes and the
// choice of who answers are in dc_world_outfits.h. No core patch: the answer is given from
// ServerScript::CanPacketReceive, which sees CMSG_GET_MIRRORIMAGE_DATA before the core's handler,
// and the core's handler still answers everything this file does not.
#include "dc_world_outfits.h"
#include "DatabaseEnv.h"
#include "DBCStores.h"
#include "Log.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Opcodes.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "WorldPacket.h"
#include "WorldSession.h"
#include <unordered_map>

namespace DC::Outfits
{
    namespace
    {
        // Filled once at startup and only read afterwards (map threads and the session thread both read).
        // `display` is the race's own player model, which the client needs under the dressed-up body.
        struct Row
        {
            Outfit outfit;
            uint32 display;
        };
        std::unordered_map<uint32, Row> outfits;

        uint32 NativeDisplay(Outfit const& outfit)
        {
            ChrRacesEntry const* race = sChrRacesStore.LookupEntry(outfit.race);
            if (!race)
                return 0;
            return outfit.gender == GENDER_FEMALE ? race->model_f : race->model_m;
        }

        class OutfitWorld final : public WorldScript
        {
        public:
            OutfitWorld()
                : WorldScript("dc_npc_outfit_world", {WORLDHOOK_ON_STARTUP})
            {
            }

            void OnStartup() override
            {
                outfits.clear();
                QueryResult rows = WorldDatabase.Query(
                    "SELECT entry, race, gender, skin, face, hair, hair_color, facial_hair, "
                    "head, shoulders, shirt, chest, waist, legs, feet, wrists, hands, back, tabard FROM dc_npc_outfit");
                if (!rows)
                    return;
                do
                {
                    Field* f = rows->Fetch();
                    uint32 const entry = f[0].Get<uint32>();
                    Outfit outfit;
                    outfit.race = f[1].Get<uint8>();
                    outfit.gender = f[2].Get<uint8>();
                    outfit.skin = f[3].Get<uint8>();
                    outfit.face = f[4].Get<uint8>();
                    outfit.hair = f[5].Get<uint8>();
                    outfit.hairColor = f[6].Get<uint8>();
                    outfit.facialHair = f[7].Get<uint8>();
                    for (unsigned slot = 0; slot < SLOT_COUNT; ++slot)
                        outfit.items[slot] = f[8 + slot].Get<uint32>();

                    if (!sObjectMgr->GetCreatureTemplate(entry))
                    {
                        LOG_ERROR("server.loading",
                                  "[DC outfits] dc_npc_outfit entry {} is not a creature_template; row skipped", entry);
                        continue;
                    }
                    uint32 const display = NativeDisplay(outfit);
                    if (!display || outfit.gender > GENDER_FEMALE)
                    {
                        LOG_ERROR("server.loading",
                                  "[DC outfits] entry {}: race {} gender {} has no player model; row skipped", entry,
                                  outfit.race, outfit.gender);
                        continue;
                    }
                    for (unsigned slot = 0; slot < SLOT_COUNT; ++slot)
                    {
                        if (outfit.items[slot] && !sObjectMgr->GetItemTemplate(outfit.items[slot]))
                        {
                            LOG_ERROR("server.loading",
                                      "[DC outfits] entry {} slot {}: item {} does not exist; slot left bare", entry,
                                      slot, outfit.items[slot]);
                            outfit.items[slot] = 0;
                        }
                    }
                    outfits[entry] = {outfit, display};
                } while (rows->NextRow());
                LOG_INFO("server.loading", "[DC outfits] {} NPC outfits loaded", outfits.size());
            }
        };

        // Marks an outfitted creature as a mirror image so the client asks for its data, and gives it the
        // race's player model so nothing shows the template's own model while the answer is in flight.
        class OutfitCreature final : public AllCreatureScript
        {
        public:
            OutfitCreature()
                : AllCreatureScript("dc_npc_outfit_creature")
            {
            }

            void OnCreatureAddWorld(Creature* creature) override
            {
                auto found = outfits.find(creature->GetEntry());
                if (found == outfits.end())
                    return;
                creature->SetUnitFlag2(UNIT_FLAG2_MIRROR_IMAGE);
                creature->SetDisplayId(found->second.display);
                creature->SetNativeDisplayId(found->second.display);
            }
        };

        class OutfitPackets final : public ServerScript
        {
        public:
            OutfitPackets()
                : ServerScript("dc_npc_outfit_packets", {SERVERHOOK_CAN_PACKET_RECEIVE})
            {
            }

            bool CanPacketReceive(WorldSession* session, WorldPacket const& packet) override
            {
                if (packet.GetOpcode() != CMSG_GET_MIRRORIMAGE_DATA || !session || !session->GetPlayer())
                    return true;

                WorldPacket request(packet);
                ObjectGuid guid;
                request >> guid;
                Unit* unit = ObjectAccessor::GetUnit(*session->GetPlayer(), guid);
                if (!unit)
                    return true;
                auto found = outfits.find(unit->GetEntry());
                if (ChooseAnswer(unit->HasCloneCasterAura(), unit->IsCreature() && found != outfits.end()) ==
                    Answer::Stock)
                    return true;

                Outfit const& outfit = found->second.outfit;
                uint32 slotDisplays[SLOT_COUNT] = {};
                for (unsigned slot = 0; slot < SLOT_COUNT; ++slot)
                    if (ItemTemplate const* item = sObjectMgr->GetItemTemplate(outfit.items[slot]))
                        slotDisplays[slot] = item->DisplayInfoID;

                WorldPacket data(SMSG_MIRRORIMAGE_DATA, 68);
                WriteAnswer(data, guid, found->second.display, unit->getClass(), outfit, slotDisplays);
                session->SendPacket(&data);
                return false;
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new OutfitWorld();
        new OutfitCreature();
        new OutfitPackets();
    }
} // namespace DC::Outfits

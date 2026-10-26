/*
 * World of DiabloCraft - `.dc shatter`, the obelisk destruction preview.
 *
 * docs/research/obelisk-shatter.md is the design; this is its harness and
 * nothing else. A GM plays the sequence a few yards in front of the caster, swaps
 * the explosion spell, the rubble, the portal and the distance by eye, and
 * decides. Nothing here is reachable from the rift open path, and nothing here
 * writes to the world database: every object is summoned, tracked and removed
 * again.
 *
 * What it does READ from the rift path is the entrance portal
 * pool, so a preview can only show a look a real rift can roll. The two also now
 * play the same clock: see LeadMs(). The rift path's own copy of the sequence is
 * in dc_rifts.cpp (09-rifts 7.9.8); this file is still not called from it.
 *
 * Why a stand-in obelisk rather than the hub's 910011: the real sequence HIDES
 * the hub obelisk, which only works standing in the hub with a rift to open. A
 * summoned copy plays anywhere, including an empty test zone, and leaves the
 * hub's questgiver untouched - its type must never change (the obelisk is GO type 2).
 *
 * Why the timers ride the player's own update rather than a world timer: the
 * work touches that player's map, so it has to run on that map's thread. Same
 * rule that put the rift quest writes on a per-player queue.
 */

#include "dc_shatter.h"

#include "dc_rifts.h"
#include "../common/dc_tunables.h"

#include "Chat.h"
#include "Creature.h"
#include "DBCStores.h"
#include "GameObject.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "TemporarySummon.h"

#include <cmath>
#include <mutex>
#include <random>
#include <string>
#include <unordered_map>
#include <vector>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (33671, 52429, 54195, 55818, 210343, 190023, 211064, 194461, 192911, 188157): the spell and rubble looks .dc shatter list offers; Identifiers, with sizes quoted in their labels.

namespace DC::Rifts::Shatter
{
    namespace
    {
        // --- what the research settled on -----------------------------------------
        //
        // Every number here is from docs/research/obelisk-shatter.md; none is invented
        // and none is a CSV row, because none of it is game data yet. Since phase 2
        // the timings and distances are rows in dc_tunables (category `rifts`)
        // rather than literals; the lifetime is a tunable for THIS COMMAND
        // only - a preview that leaves objects standing in the world is a preview
        // that needs a cleaner.
        //
        // The defaults are picks from a first session, not the research's
        // any more: spell 55759 over 33671, rubble 190386,
        // timings 200/800, and a portal rolled from the entrance pool exactly as a
        // real rift rolls one.
        constexpr std::uint32_t DEFAULT_SPELL = 55759;   // Earth Revenant Entrance, a radial dust nova
        constexpr std::uint32_t DEFAULT_RUBBLE = 190386; // Rock Rubble, the obelisk's own footprint
        constexpr std::uint32_t OBELISK_ENTRY = 910011;  // the hub's Rift Obelisk template
        constexpr std::uint32_t TRIGGER_ENTRY = 12999;   // World Invisible Trigger
        constexpr std::uint32_t TRIGGER_DISPLAY = 11686; // the invisible model on that entry
        // creature_template 12999 ships with faction 114, a hostile monster faction.
        // That is what let spell 50811 damage a player: an enemy-targeting area effect
        // cast by a hostile creature picks up every player in radius. 35 is friendly
        // to everyone, so such an effect has no target here.
        constexpr std::uint32_t TRIGGER_FACTION = 35;
        // tunables:rifts - named a tunable in the code and still
        // compiled in. `.dc shatter` only.
        inline std::uint32_t LifetimeMs()
        {
            return static_cast<std::uint32_t>(DC::Tunables::Get("rifts", "shatter_preview_lifetime_ms"));
        }

        // How far in front of the caster the sequence plays, and a tunable in
        // the same way the rest are. It is NOT from the research: the research
        // shatters an obelisk that is already standing somewhere. Played on the
        // caster it puts the dust cloud and then a portal inside his camera, and he
        // has to walk out and turn around to see what he asked for. Eight yards is
        // far enough that the whole sequence is in frame at a normal camera
        // distance, and near enough to still read as happening at his feet.
        // tunables:rifts.
        inline float DefaultDistance()
        {
            return static_cast<float>(DC::Tunables::Get("rifts", "shatter_preview_distance_yards"));
        }
        // Past this it is behind a wall or off a cliff.
        inline float MaxDistance()
        {
            return static_cast<float>(DC::Tunables::Get("rifts", "shatter_preview_max_distance_yards"));
        }

        // §6's table, re-based so the preview and the real rift path play the same
        // clock. On the real path the obelisk is already standing when
        // the quest is accepted, and the dust and the obelisk leaving are ONE step;
        // t = 0 is that step, and 200/800 are measured from it.
        //
        // A preview has to put an obelisk there first, so it gets a LeadMs() beat of
        // just the obelisk standing. The clock below then starts at the end of that
        // beat, which is why shatter_preview_lead_ms is not one of the four
        // settings: it is the preview's own "here is the obelisk" and has no
        // counterpart in a rift.
        // tunables:rifts.
        inline std::uint32_t LeadMs()
        {
            return static_cast<std::uint32_t>(DC::Tunables::Get("rifts", "shatter_preview_lead_ms"));
        }
        // Audit rows 101 and 102 are the rift path's own two rows, read here
        // rather than copied: `open_rubble_ms` and `open_portal_ms` are the same
        // two numbers dc_rifts.cpp uses, so the preview cannot drift from the
        // real sequence the way two literals could.
        inline std::uint32_t RubbleMs()
        {
            return static_cast<std::uint32_t>(DC::Tunables::Get("rifts", "open_rubble_ms"));
        }
        inline std::uint32_t PortalMs()
        {
            return static_cast<std::uint32_t>(DC::Tunables::Get("rifts", "open_portal_ms"));
        }
        // How long the trigger and the caster's immunity outlive t = 0.
        // tunables:rifts.
        inline std::uint32_t ClearMs()
        {
            return static_cast<std::uint32_t>(DC::Tunables::Get("rifts", "shatter_preview_clear_ms"));
        }

        struct Candidate
        {
            std::uint32_t id;
            char const* note;
        };

        // §5, verified present in the server's own Spell.dbc.
        //
        // 50811 is GONE: it damaged a player. The research paired it with 33671 as if the
        // two were the same spell because they share SpellVisual 8097, but a shared
        // visual says nothing about a spell's effects, and 50811's are real. It is not
        // offered again even though the caster is now immune for the duration - an
        // offer that only works because of a safety net is a trap.
        constexpr Candidate SPELLS[] = {
            {55759, "Earth Revenant Entrance - a radial ground dust ring, no chunks (default)"},
            {33671, "Shatter - flying stone chunks and a thick dust cloud"},
            {52429, "Shatter variant - same burst, longer-lingering dust"},
            {54195, "Earth's Wrath - a heavy buried detonation"},
            {55818, "Hurl Boulder - a solid rock impact shatter"},
        };

        // §4. All seven verified present in gameobject_template.
        constexpr Candidate RUBBLE[] = {
            {190386, "Rock Rubble - flat 2.6m stone pile, the obelisk's footprint (default)"},
            {210343, "Sand Worm Rock Base - a crater rim the portal nests in"},
            {190023, "Platform - a sheared-off pillar stump"},
            {211064, "Rockwall Fence - a small cluster of loose fieldstone"},
            {194461, "Stone Block - a heavy cracked Titan slab, 6.6m across"},
            {192911, "Ancient Elven Masonry - a carved ruin block"},
            {188157, "Twilight Crystal Base - WARNING 12.7m x 11.0m x 16.1m, far larger than the obelisk"},
        };

        // The portal candidates are no longer a list in this file. They are the live
        // entrance pool from rift_portals.csv, read through DC::Rifts::PortalPool(),
        // so the preview can only show a look a real rift can actually roll -
        // which is the whole point of previewing. The hard-coded eighteen went with
        // the retired 910014; 298 was never a portal model at all (AuraBlueTall.mdx)
        // and is not in the pool.

        // One look from the pool, or the pool row that was pinned. A zero entry means the
        // pool did not load, which the caller reports rather than papering over.
        PortalLook PickPortal(std::uint32_t pinned)
        {
            std::vector<PortalLook> const pool = PortalPool();
            if (pool.empty())
                return {};
            if (pinned)
                for (PortalLook const& look : pool)
                    if (look.entry == pinned)
                        return look;
            static thread_local std::mt19937 engine{std::random_device{}()};
            return pool[std::uniform_int_distribution<std::size_t>(0, pool.size() - 1)(engine)];
        }

        // `.dc shatter portal <n>`: the user types either a pool entry (9100xx) or the
        // display read off `list` (four digits). Both resolve to the
        // one pool row, because a display that is not in the pool is a look a rift
        // cannot roll and pinning it would make the preview lie.
        std::uint32_t ResolvePortal(std::uint32_t value)
        {
            for (PortalLook const& look : PortalPool())
                if (look.entry == value || look.display == value)
                    return look.entry;
            return 0;
        }

        // One thing this command put in the world, and when it comes out again.
        struct Spawn
        {
            ObjectGuid guid;
            bool creature = false;
            std::uint32_t mapId = 0;
            std::uint32_t leftMs = LifetimeMs();
        };

        struct Session
        {
            // Set once with a subcommand, replayed by a bare `.dc shatter`. Cleared on
            // logout with the rest of the session.
            std::uint32_t spell = DEFAULT_SPELL;
            std::uint32_t rubble = DEFAULT_RUBBLE;
            // A pool ENTRY, not a display any more. 0 means "roll one per play", which
            // is what a real rift does and is the default.
            std::uint32_t portalEntry = 0;
            std::uint32_t rubbleMs = RubbleMs();
            std::uint32_t portalMs = PortalMs();
            float distance = DefaultDistance();

            // The sequence in flight.
            bool playing = false;
            std::uint32_t elapsed = 0;
            float x = 0, y = 0, z = 0, o = 0;
            std::uint32_t phase = 1;
            ObjectGuid standIn;
            bool firedSpell = false, firedRubble = false, firedPortal = false, firedClear = false;
            // Whether the caster is currently carrying the preview's immunity, so it
            // comes off exactly once however the sequence ends.
            bool immune = false;

            std::vector<Spawn> spawns;
        };

        std::mutex mutex;
        std::unordered_map<ObjectGuid, Session> sessions;

        // Removes one tracked object. The map lookup can miss - a GM may have deleted
        // it by hand, or the map may have unloaded - and a miss is not an error.
        void Remove(Map* map, Spawn const& spawn)
        {
            if (!map)
                return;
            if (spawn.creature)
            {
                if (Creature* creature = map->GetCreature(spawn.guid))
                    creature->DespawnOrUnsummon();
                return;
            }
            if (GameObject* object = map->GetGameObject(spawn.guid))
                object->Delete();
        }

        // The preview's guarantee that nothing it plays can touch the player.
        //
        // Said plainly: a cast of an arbitrary
        // spell id CANNOT be made visual-only server-side. `CastSpell` runs whatever
        // effects that spell's DBC row carries, and there is no stock flag that keeps
        // the visual and drops the effects. Two things are done instead. The trigger is
        // made faction 35 before it casts, which is the actual reason 50811 hurt him -
        // creature 12999 ships hostile - and removes every enemy-targeting effect's
        // only target. And on top of that the caster is made immune for the sequence,
        // which covers a spell that targets units regardless of hostility.
        //
        // IMMUNITY_SCHOOL over IMMUNITY_DAMAGE on purpose: damage immunity stops the
        // damage and still lets a stun or a slow land, and "must never damage or
        // affect the player" is the requirement.
        void SetPreviewImmunity(Player* player, Session& session, bool on)
        {
            if (!player || session.immune == on)
                return;
            player->ApplySpellImmune(0, IMMUNITY_SCHOOL, SPELL_SCHOOL_MASK_ALL, on);
            session.immune = on;
        }

        unsigned Clean(Player* player, Session& session)
        {
            unsigned removed = 0;
            for (Spawn const& spawn : session.spawns)
            {
                Remove(player ? player->GetMap() : nullptr, spawn);
                ++removed;
            }
            session.spawns.clear();
            session.playing = false;
            session.standIn.Clear();
            SetPreviewImmunity(player, session, false);
            return removed;
        }

        // Where the sequence plays: `distance` yards in front of the caster, facing
        // him. GetClosePoint walks the ground for us, so the spot sits on the floor
        // and pulls up short of a wall rather than landing through it. The
        // orientation is taken from where it actually landed rather than from where
        // it was asked for, so a shortened spot still faces the right way.
        void Spot(Player* player, Session& session)
        {
            float x = player->GetPositionX();
            float y = player->GetPositionY();
            float z = player->GetPositionZ();
            if (session.distance > 0.0f)
                player->GetClosePoint(x, y, z, player->GetObjectSize(), session.distance);
            session.x = x;
            session.y = y;
            session.z = z;
            float const dx = player->GetPositionX() - x;
            float const dy = player->GetPositionY() - y;
            // At zero distance there is no direction to face, so keep the caster's own.
            session.o = (dx == 0.0f && dy == 0.0f) ? player->GetOrientation() : std::atan2(dy, dx);
        }

        // Summons a gameobject at the sequence's spot and tracks it. `display` of 0
        // leaves the template's own model alone.
        //
        // Why this builds the object rather than calling Map::SummonGameObject, which
        // is what the rest of the rifts folder uses: that helper runs
        // GameObject::Create - which sets the display from gameobject_template - and
        // THEN AddToMap, and AddToMap is what sends the create packet. Setting the
        // display after it returns is correct on the server (GetDisplayId reads the
        // new value, and a values update goes out carrying GAMEOBJECT_DISPLAYID,
        // which nothing filters) but the 3.3.5 client caches a gameobject's model at
        // spawn, so every client already holding the object keeps the model it was
        // created with. That was `.dc shatter portal 8111` drawing 4713: the server
        // said 8111 and the client drew the template's own. Setting it between Create
        // and AddToMap puts the right display in the create packet itself.
        //
        // The second SetDisplayId after the map add costs no packet - SetUInt32Value
        // is a no-op when the value is unchanged - and is there only for
        // UpdateModel(), which early-returns while the object is not yet in the world
        // and so would otherwise leave the collision model built from the old display.
        GameObject* Place(Player* player, Session& session, std::uint32_t entry, float zOffset, std::uint32_t display)
        {
            Map* map = player->GetMap();
            if (!map || !sObjectMgr->GetGameObjectTemplate(entry))
                return nullptr;

            // 7.9.8: claimed for the caster and nobody else, across Create AND the map
            // add. A preview everybody can see is not a preview of something private,
            // and the claim has to be live during Create because that is when the core
            // builds the AI that answers CanBeSeen, and live during AddToMap because
            // that is when the create packet goes out.
            HubObjectClaim claim(player);
            GameObject* object = new GameObject();
            if (!object->Create(map->GenerateLowGuid<HighGuid::GameObject>(), entry, map, session.phase, session.x,
                                session.y, session.z + zOffset, session.o,
                                G3D::Quat(0, 0, std::sin(session.o / 2), std::cos(session.o / 2)), 100, GO_STATE_READY))
            {
                delete object;
                return nullptr;
            }
            if (display)
                object->SetDisplayId(display);
            // What Map::SummonGameObject does for a temporary object, and for the same
            // reason: this one is not a spawn, so it must never respawn itself.
            object->SetRespawnTime(0);
            object->SetSpawnedByDefault(false);
            map->AddToMap(object);
            if (display)
                object->SetDisplayId(display);
            session.spawns.push_back({object->GetGUID(), false, map->GetId(), LifetimeMs()});
            return object;
        }

        // The one step that is not a gameobject: an invisible stalker that exists only
        // to be the thing the client plays the explosion on. §5.2 - the 3.3.5a client
        // will not draw a particle effect at bare coordinates.
        void Detonate(Player* player, Session& session)
        {
            // Claimed for the caster, which is also what makes the EXPLOSION his alone:
            // SMSG_SPELL_GO is delivered only to players who already hold the caster,
            // so a stalker only he can see casts a spell only he can see.
            Creature* trigger = nullptr;
            {
                HubObjectClaim claim(player);
                trigger = player->SummonCreature(TRIGGER_ENTRY, session.x, session.y, session.z, session.o,
                                                 TEMPSUMMON_TIMED_DESPAWN, ClearMs());
            }
            if (!trigger)
            {
                ChatHandler(player->GetSession())
                    .SendSysMessage("The shatter trigger could not be summoned; no explosion this time.");
                return;
            }
            trigger->SetDisplayId(TRIGGER_DISPLAY);
            trigger->SetObjectScale(0.01f);
            // Friendly and untouchable BEFORE the cast, never after: the target list is
            // built when the spell goes off.
            trigger->SetFaction(TRIGGER_FACTION);
            trigger->SetImmuneToAll(true);
            SetPreviewImmunity(player, session, true);
            trigger->CastSpell(trigger, session.spell, true);
            if (Map* map = player->GetMap())
                session.spawns.push_back({trigger->GetGUID(), true, map->GetId(), ClearMs()});
        }

        // Runs on the player's own update, so everything below touches only that
        // player's map from that map's thread.
        void Advance(Player* player, std::uint32_t diff)
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto found = sessions.find(player->GetGUID());
            if (found == sessions.end())
                return;
            Session& session = found->second;

            // The 60-second cleaner, which runs whether or not a sequence is playing.
            for (std::size_t i = 0; i < session.spawns.size();)
            {
                Spawn& spawn = session.spawns[i];
                if (spawn.leftMs > diff)
                {
                    spawn.leftMs -= diff;
                    ++i;
                    continue;
                }
                Remove(player->GetMap(), spawn);
                session.spawns.erase(session.spawns.begin() + i);
            }

            if (!session.playing)
                return;
            session.elapsed += diff;

            // The clock's zero is the end of the lead-in beat, so the 200 and 800 are
            // the same 200 and 800 a real rift plays.
            if (session.elapsed < LeadMs())
                return;
            std::uint32_t const since = session.elapsed - LeadMs();

            // t = 0, one step: the dust, and the stand-in leaving under it. The real
            // path hides the hub obelisk on this same tick, which is the closest a
            // summoned stand-in can get to it.
            if (!session.firedSpell)
            {
                session.firedSpell = true;
                Detonate(player, session);
                if (session.standIn)
                {
                    for (std::size_t i = 0; i < session.spawns.size(); ++i)
                        if (session.spawns[i].guid == session.standIn)
                        {
                            Remove(player->GetMap(), session.spawns[i]);
                            session.spawns.erase(session.spawns.begin() + i);
                            break;
                        }
                    session.standIn.Clear();
                }
            }
            if (!session.firedRubble && since >= session.rubbleMs)
            {
                session.firedRubble = true;
                if (!Place(player, session, session.rubble, 0.0f, 0))
                    ChatHandler(player->GetSession()).SendSysMessage("The rubble could not be placed.");
            }
            if (!session.firedPortal && since >= session.portalMs)
            {
                session.firedPortal = true;
                PortalLook const look = PickPortal(session.portalEntry);
                if (!look.entry)
                    ChatHandler(player->GetSession())
                        .SendSysMessage("The entrance portal pool is not loaded, so there is no portal to show; "
                                        "see the startup log.");
                // +0.1m is the research's own offset so the portal's ground ring sits
                // on top of the rubble rather than inside it. No display override any
                // more: each pool row is its own template wearing its own display and
                // scale, which is exactly what a real rift summons, and that is also
                // why the create-packet trap no longer applies here.
                else if (!Place(player, session, look.entry, 0.1f, 0))
                    ChatHandler(player->GetSession()).SendSysMessage("The portal could not be placed.");
                else
                    ChatHandler(player->GetSession())
                        .PSendSysMessage("Portal: {} (entry {}, display {}, scale {}).", look.name, look.entry,
                                         look.display, look.scale);
            }
            if (!session.firedClear && since >= ClearMs())
            {
                session.firedClear = true;
                SetPreviewImmunity(player, session, false);
                session.playing = false;
            }
        }

        std::string Milliseconds(std::uint32_t ms)
        {
            return std::to_string(ms) + " ms";
        }

        // One decimal, so 8 reads as 8.0 and 7.5 is not rounded away.
        std::string Yards(float yards)
        {
            std::string text = std::to_string(yards);
            std::size_t const point = text.find('.');
            if (point != std::string::npos && point + 2 < text.size())
                text.erase(point + 2);
            return text;
        }

        class ShatterPlayer final : public PlayerScript
        {
        public:
            ShatterPlayer()
                : PlayerScript("dc_shatter_player", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                if (player)
                    Advance(player, diff);
            }

            // Defaults reset on logout, and nothing this command spawned outlives the
            // session that asked for it.
            void OnPlayerLogout(Player* player) override
            {
                if (!player)
                    return;
                std::lock_guard<std::mutex> lock(mutex);
                auto found = sessions.find(player->GetGUID());
                if (found == sessions.end())
                    return;
                Clean(player, found->second);
                sessions.erase(found);
            }
        };

        class ShatterCommand final : public CommandScript
        {
        public:
            ShatterCommand()
                : CommandScript("dc_shatter_command")
            {
            }

            Acore::ChatCommands::ChatCommandTable GetCommands() const override
            {
                using namespace Acore::ChatCommands;
                // GM-only throughout: it summons objects in the open world, and it is a
                // preview tool, not a player feature.
                static ChatCommandTable shatter = {
                    {"", HandlePlay, SEC_ADMINISTRATOR, Console::No},
                    {"spell", HandleSpell, SEC_ADMINISTRATOR, Console::No},
                    {"rubble", HandleRubble, SEC_ADMINISTRATOR, Console::No},
                    {"portal", HandlePortal, SEC_ADMINISTRATOR, Console::No},
                    {"timing", HandleTiming, SEC_ADMINISTRATOR, Console::No},
                    {"dist", HandleDist, SEC_ADMINISTRATOR, Console::No},
                    {"clean", HandleClean, SEC_ADMINISTRATOR, Console::No},
                    {"list", HandleList, SEC_GAMEMASTER, Console::No},
                };
                static ChatCommandTable dc = {{"shatter", shatter}};
                static ChatCommandTable root = {{"dc", dc}};
                return root;
            }

        private:
            static Player* Caster(ChatHandler* handler)
            {
                Player* player = handler->GetSession() ? handler->GetSession()->GetPlayer() : nullptr;
                if (!player || !player->GetMap())
                {
                    handler->SendSysMessage("`.dc shatter` has to be typed by a character in the world.");
                    return nullptr;
                }
                return player;
            }

            static bool HandlePlay(ChatHandler* handler)
            {
                Player* player = Caster(handler);
                if (!player)
                    return true;

                std::lock_guard<std::mutex> lock(mutex);
                Session& session = sessions[player->GetGUID()];
                session.playing = true;
                session.elapsed = 0;
                session.firedSpell = session.firedRubble = session.firedPortal = session.firedClear = false;
                Spot(player, session);
                session.phase = player->GetPhaseMask();

                // The lead-in beat: the obelisk stands on its own for a second so the
                // explosion has something to take away and the viewer sees what it took.
                GameObject* standIn = Place(player, session, OBELISK_ENTRY, 0.0f, 0);
                if (!standIn)
                {
                    session.playing = false;
                    handler->SendSysMessage("The stand-in obelisk could not be summoned; nothing was played.");
                    return true;
                }
                session.standIn = standIn->GetGUID();

                handler->PSendSysMessage(
                    "Shatter {} yards ahead: spell {}, rubble {}, portal {}, rubble at {}, portal at {}.",
                    Yards(session.distance), session.spell, session.rubble,
                    session.portalEntry ? std::to_string(session.portalEntry) : std::string("rolled from the pool"),
                    Milliseconds(session.rubbleMs), Milliseconds(session.portalMs));
                handler->PSendSysMessage(
                    "The obelisk stands for {} first, then goes on the same tick as the explosion, as a real "
                    "rift's does. You are immune while it plays.",
                    Milliseconds(LeadMs()));
                handler->SendSysMessage(
                    "Everything it spawns clears itself after 60 seconds, or at once with `.dc shatter clean`.");
                return true;
            }

            static bool HandleSpell(ChatHandler* handler, uint32 spellId)
            {
                Player* player = Caster(handler);
                if (!player)
                    return true;
                if (!sSpellMgr->GetSpellInfo(spellId))
                {
                    handler->PSendSysMessage("Spell {} is not in this server's Spell.dbc; nothing changed.", spellId);
                    return true;
                }
                std::lock_guard<std::mutex> lock(mutex);
                sessions[player->GetGUID()].spell = spellId;
                handler->PSendSysMessage("Shatter spell set to {}. `.dc shatter` to play it.", spellId);
                return true;
            }

            static bool HandleRubble(ChatHandler* handler, uint32 entry)
            {
                Player* player = Caster(handler);
                if (!player)
                    return true;
                GameObjectTemplate const* go = sObjectMgr->GetGameObjectTemplate(entry);
                if (!go)
                {
                    handler->PSendSysMessage("Gameobject {} is not in gameobject_template; nothing changed.", entry);
                    return true;
                }
                std::lock_guard<std::mutex> lock(mutex);
                sessions[player->GetGUID()].rubble = entry;
                handler->PSendSysMessage("Shatter rubble set to {} ({}, GO type {}). `.dc shatter` to play it.", entry,
                                         go->name, uint32(go->type));
                return true;
            }

            // A pool entry or one of the pool's displays; 0 goes back to rolling one per
            // play, which is what a real rift does. A display that is not in the pool is
            // refused rather than shown: the whole point of the preview is that what
            // the viewer sees is something a rift can actually roll.
            static bool HandlePortal(ChatHandler* handler, uint32 value)
            {
                Player* player = Caster(handler);
                if (!player)
                    return true;
                std::uint32_t entry = 0;
                if (value)
                {
                    entry = ResolvePortal(value);
                    if (!entry)
                    {
                        handler->PSendSysMessage("{} is not an entrance pool entry or display; `.dc shatter list` "
                                                 "shows the pool. Nothing changed.",
                                                 value);
                        return true;
                    }
                }
                std::lock_guard<std::mutex> lock(mutex);
                sessions[player->GetGUID()].portalEntry = entry;
                if (entry)
                    handler->PSendSysMessage("Portal pinned to entry {}. `.dc shatter` to see it.", entry);
                else
                    handler->SendSysMessage("Portal is rolled from the pool again, one per play, as a rift does.");
                return true;
            }

            static bool HandleTiming(ChatHandler* handler, uint32 rubbleMs, uint32 portalMs)
            {
                Player* player = Caster(handler);
                if (!player)
                    return true;
                std::lock_guard<std::mutex> lock(mutex);
                Session& session = sessions[player->GetGUID()];
                session.rubbleMs = rubbleMs;
                session.portalMs = portalMs;
                handler->PSendSysMessage("Rubble at {}, portal at {}, both measured from the explosion, which is "
                                         "also when the obelisk goes. Same clock as a real rift.",
                                         Milliseconds(rubbleMs), Milliseconds(portalMs));
                return true;
            }

            static bool HandleDist(ChatHandler* handler, float yards)
            {
                Player* player = Caster(handler);
                if (!player)
                    return true;
                if (yards < 0.0f || yards > MaxDistance())
                {
                    handler->PSendSysMessage("Distance has to be between 0 and {} yards; nothing changed.",
                                             Yards(MaxDistance()));
                    return true;
                }
                std::lock_guard<std::mutex> lock(mutex);
                sessions[player->GetGUID()].distance = yards;
                if (yards == 0.0f)
                    handler->SendSysMessage(
                        "The sequence now plays ON you. Expect the dust and the portal to fill your camera.");
                else
                    handler->PSendSysMessage("The sequence now plays {} yards in front of you, facing you.",
                                             Yards(yards));
                return true;
            }

            static bool HandleClean(ChatHandler* handler)
            {
                Player* player = Caster(handler);
                if (!player)
                    return true;
                std::lock_guard<std::mutex> lock(mutex);
                auto found = sessions.find(player->GetGUID());
                if (found == sessions.end())
                {
                    handler->SendSysMessage("Nothing of yours is standing.");
                    return true;
                }
                unsigned const removed = Clean(player, found->second);
                handler->PSendSysMessage("Removed {} object(s). Your spell, rubble, portal and timing are unchanged.",
                                         removed);
                return true;
            }

            static bool HandleList(ChatHandler* handler)
            {
                Player* player = Caster(handler);
                if (!player)
                    return true;
                Session session;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto found = sessions.find(player->GetGUID());
                    if (found != sessions.end())
                        session = found->second;
                }

                handler->SendSysMessage("Explosion spells - `.dc shatter spell <id>`:");
                for (Candidate const& candidate : SPELLS)
                    handler->PSendSysMessage("  {}{} - {}", candidate.id,
                                             candidate.id == session.spell ? " (in use)" : "", candidate.note);

                handler->SendSysMessage("Rubble - `.dc shatter rubble <entry>`:");
                for (Candidate const& candidate : RUBBLE)
                    handler->PSendSysMessage("  {}{} - {}", candidate.id,
                                             candidate.id == session.rubble ? " (in use)" : "", candidate.note);

                std::vector<PortalLook> const pool = PortalPool();
                if (pool.empty())
                    handler->SendSysMessage(
                        "Entrance portal pool: EMPTY. dc_rift_portal did not load; see the startup log.");
                else
                {
                    handler->PSendSysMessage("Entrance portal pool, {} looks - `.dc shatter portal <entry|display>`, "
                                             "or 0 to roll one per play as a rift does:",
                                             pool.size());
                    for (PortalLook const& look : pool)
                        handler->PSendSysMessage("  {} display {} scale {}{} - {}", look.entry, look.display,
                                                 look.scale, look.entry == session.portalEntry ? " (pinned)" : "",
                                                 look.name);
                }

                handler->PSendSysMessage("Timing - `.dc shatter timing <rubbleMs> <portalMs>`; now {} and {}, both "
                                         "from the explosion. The obelisk stands for {} first.",
                                         Milliseconds(session.rubbleMs), Milliseconds(session.portalMs),
                                         Milliseconds(LeadMs()));
                handler->PSendSysMessage("Distance - `.dc shatter dist <yards>`; now {} yards in front of you.",
                                         Yards(session.distance));
                return true;
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new ShatterPlayer();
        new ShatterCommand();
    }
} // namespace DC::Rifts::Shatter

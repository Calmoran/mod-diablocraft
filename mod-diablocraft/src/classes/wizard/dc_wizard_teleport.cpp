#include "dc_wizard_teleport.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_spell_values.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "SpellMgr.h"
#include <algorithm>

namespace DC::Combat::Wizard::Teleport
{
    using namespace Shared;

    bool Travels(uint32 id)
    {
        return IsSkill(id, "Teleport") || id == ArchonAbilityId("Teleport");
    }

    namespace
    {
        // --- Teleport faces the way it travelled --------------------------------
        // Without this, Teleport turns the Wizard to face north on every cast. Spell::EffectLeap
        // lands the caster with the ORIENTATION OF ITS DESTINATION (SpellEffects.cpp, NearTeleportTo(..., dstpos.GetOrientation())),
        // and the cursor destination the client sends carries a position only, so the orientation is 0. It is the leap's
        // landing, not the record's client data. The module cannot change the destination before the leap (that is a
        // SpellScript hook on the record, and the shells' only script is dc_combat's), so it overrides the leap's pending
        // destination once the leap has been issued, with the same point and the way it travelled.
        //
        // A player's near teleport does not move the server position at once: Player::TeleportTo stores the destination
        // (GetTeleportDest), sends the packets and puts the player back where it stood, and HandleMoveTeleportAck moves it
        // when the client acknowledges. So in AfterCast GetPosition() is still the START and the landing is
        // GetTeleportDest() while IsBeingTeleportedNear(). A second near teleport in that window only replaces the stored
        // destination and sends the client the new packet, so the final position is the new point.
        // Where the Wizard is, or is about to be.
        Position Where(Player* player)
        {
            return player->IsBeingTeleportedNear() ? Position(player->GetTeleportDest()) : player->GetPosition();
        }

        // From the start toward the landing; a cast that went nowhere keeps the facing it had.
        float TravelAngle(Position const& from, Position const& to)
        {
            return from.GetExactDist2d(&to) > 0.1f ? from.GetAbsoluteAngle(&to) : from.GetOrientation();
        }

        void TeleportBegin(Player* player, State& state, uint32 spellId)
        {
            if (Travels(spellId))
                state.travelFrom = Where(player);
        }
    } // namespace

    // The recast of Reversal returns the Wizard itself (ReversalCast), with its own facing. casting = true is the
    // leap's own flag: this runs inside the cast and must not interrupt it.
    void FaceTravel(Player* player, uint32 id)
    {
        Position from;
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            State& state = StateOf(player);
            if (state.reversalRecast && IsRune(id, "Reversal"))
                return;
            from = state.travelFrom;
        }
        // No pending near teleport: the leap went nowhere or failed, and there is nothing to turn.
        if (!player->IsBeingTeleportedNear())
            return;
        Position const landing = player->GetTeleportDest();
        player->NearTeleportTo(landing.GetPositionX(), landing.GetPositionY(), landing.GetPositionZ(),
                               TravelAngle(from, landing), true);
    }

    namespace
    {
        // --- Teleport - Reversal (GitHub #94) --------------------------------
        // "Casting Teleport again within {duration_seconds} seconds will
        // instantly return you to your original location and set the
        // remaining cooldown to {cooldown_seconds} second." The first cast
        // teleports, saves where the Wizard stood and opens the window with
        // no cooldown showing (the core installed the record's before
        // AfterCast, so it is taken off, as Wormhole's is). A recast inside
        // the window returns the Wizard and sets the cooldown to the sheet's
        // one second. A window that ends unused - the time runs out, the
        // Wizard dies, changes map, logs out or becomes an Archon - leaves the
        // cooldown the first cast would have left by now: the full cooldown
        // after reductions, less the time the window was open, never below 0.
        // There is no return across maps.

        // The rune family shares one cooldown; the swirl has to go off the
        // buttons as well as the server.
        void ReversalClearCooldown(Player* player, uint32 id)
        {
            SendSkillCooldown(player, id, 0);
            if (SpellInfo const* info = sSpellMgr->GetSpellInfo(id); info && info->GetCategory())
                player->RemoveCategoryCooldown(info->GetCategory());
        }

        // Before the leap (Begin runs in OnCast): a cast inside an open
        // window is the recast; any other is a first cast and its start is
        // the place to return to.
        void ReversalBegin(Player* player, State& state, uint32 spellId)
        {
            if (!IsRune(spellId, "Reversal"))
                return;
            state.reversalRecast = state.reversalUntil > Now() && state.reversalSpell == spellId &&
                                   state.reversalMap == player->GetMapId() &&
                                   state.reversalInstance == player->GetInstanceId();
            if (!state.reversalRecast)
            {
                state.reversalFrom = Where(player);
                state.reversalMap = player->GetMapId();
                state.reversalInstance = player->GetInstanceId();
            }
        }
    } // namespace

    // The window is over without a return: put on what is left of the
    // cooldown. Safe to call with no window open.
    void ReversalEnd(Player* player)
    {
        uint32 id;
        uint64 open;
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            State& state = StateOf(player);
            if (!state.reversalUntil)
                return;
            id = state.reversalSpell;
            open = std::min(Now() - state.reversalSince, state.reversalUntil - state.reversalSince);
            state.reversalUntil = 0;
            ++state.reversalWindow;
        }
        uint32 const full = SkillCooldownMilliseconds(player, id);
        SendSkillCooldown(player, id, full > open ? full - uint32(open) : 0);
    }

    // The cast itself, after the leap has moved the Wizard.
    void ReversalCast(Player* player, uint32 id)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        if (state.reversalRecast)
        {
            state.reversalRecast = false;
            state.reversalUntil = 0;
            ++state.reversalWindow;
            Position const from = state.reversalFrom;
            // It faces the way it travels back, not the way it stood at the start.
            float const facing = TravelAngle(state.travelFrom, from);
            // The core installed the record's cooldown for this cast too.
            ReversalClearCooldown(player, id);
            SendSkillCooldown(player, id, uint32(Numbers::Own(id, "cooldown_seconds").value_or(0) * 1000));
            // Now, inside the cast, over the recast's own pending leap: the final destination is the start.
            player->NearTeleportTo(from.GetPositionX(), from.GetPositionY(), from.GetPositionZ(), facing, true);
            return;
        }
        double const seconds = Num(id, "duration_seconds");
        unsigned const window = ++state.reversalWindow;
        state.reversalSpell = id;
        state.reversalSince = Now();
        state.reversalUntil = state.reversalSince + uint64(seconds * 1000);
        ReversalClearCooldown(player, id);
        After(player, seconds,
              [window](Player* p)
              {
                  {
                      std::lock_guard<std::recursive_mutex> guard(mutex);
                      if (StateOf(p).reversalWindow != window)
                          return;
                  }
                  ReversalEnd(p);
              });
    }

    namespace
    {
        // The Wormhole row whose numbers a Teleport cast reads: the cast's own row when Wormhole is chosen, else the rune's row when a power gives
        // the rune without choosing it (kind `rune`, Cosmic Strand), else 0. Chosen and given, it counts once.
        uint32 WormholeOf(Player* player, uint32 id)
        {
            if (IsRune(id, "Wormhole"))
                return id;
            if (!ItemPowers::GrantsRune(player, "Teleport", "Wormhole"))
                return 0;
            for (Row const& row : Shells::Abilities)
                if (std::string_view("Teleport") == row.skill && std::string_view("Wormhole") == row.rune)
                    return row.id;
            return 0;
        }
    } // namespace

    void Begin(Player* player, State& state, uint32 spellId)
    {
        ReversalBegin(player, state, spellId);
        TeleportBegin(player, state, spellId);
    }

    void Cast(Player* player, uint32 id)
    {
        // The LEAP has already moved the Wizard; the arrival effects
        // wait for the next update so they see where they arrived.
        if (IsRune(id, "Calamity"))
            After(player, 0,
                  [id](Player* p) { Combat::StrikeArea(p, id, p->GetPosition(), Num(id, "radius_yards")); });
        if (IsRune(id, "Safe Passage"))
        {
            std::lock_guard<std::recursive_mutex> guard(mutex);
            StateOf(player).safePassage = Now() + uint64(Num(id, "duration_seconds") * 1000);
        }
        // Wormhole: "After casting Teleport, there is a {duration_seconds}
        // second delay before the cooldown begins, allowing you to cast
        // it again {cast_count} time". d3planner's grace [180, 1]
        // (wizard.js:485-486): the first cast opens the window and starts
        // no cooldown; the last recast in it starts the cooldown, and so
        // does the window closing unused (cast.js:241-254, onGrace
        // :193-202). The core installed the record's cooldown before
        // AfterCast, so opening the window takes it off again.
        if (uint32 const wormhole = WormholeOf(player, id))
        {
            auto reopen = [player, id]
            {
                SendSkillCooldown(player, id, 0);
                if (SpellInfo const* info = sSpellMgr->GetSpellInfo(id); info && info->GetCategory())
                    player->RemoveCategoryCooldown(info->GetCategory());
            };
            std::lock_guard<std::recursive_mutex> guard(mutex);
            State& state = StateOf(player);
            uint64 const now = Now();
            if (state.wormholeLeft && state.wormholeUntil > now)
            {
                // A recast inside the window: the core's cooldown stays
                // once no recast is left.
                if (--state.wormholeLeft == 0)
                    state.wormholeUntil = 0;
                else
                    reopen();
            }
            else
            {
                double const seconds = Num(wormhole, "duration_seconds");
                unsigned const window = ++state.wormholeWindow;
                state.wormholeUntil = now + uint64(seconds * 1000);
                state.wormholeLeft = unsigned(Num(wormhole, "cast_count"));
                reopen();
                After(player, seconds,
                      [id, window](Player* p)
                      {
                          {
                              std::lock_guard<std::recursive_mutex> guard(mutex);
                              State& state = StateOf(p);
                              if (state.wormholeWindow != window || !state.wormholeLeft)
                                  return;
                              state.wormholeLeft = 0;
                              state.wormholeUntil = 0;
                          }
                          SendSkillCooldown(p, id, SkillCooldownMilliseconds(p, id));
                      });
            }
        }
    }
} // namespace DC::Combat::Wizard::Teleport

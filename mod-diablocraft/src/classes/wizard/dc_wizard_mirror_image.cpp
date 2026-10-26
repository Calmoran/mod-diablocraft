#include "dc_wizard_mirror_image.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_item_power_math.h"
#include "ScriptedCreature.h"
#include "TemporarySummon.h"
#include <cmath>
#include <numbers>

namespace DC::Combat::Wizard::MirrorImage
{
    using namespace Shared;

    namespace
    {
        // wizard_summons.csv: the creature template generate_wizard_summon_templates() writes for the Image.
        constexpr uint32 MIRROR_IMAGE_ENTRY = 900110;

        // Clone Me!, the stock Mirror Image's copy of its caster's look
        // (spell_dbc 45204, cast by the owner on the image).
        constexpr uint32 CLONE_ME = 45204;
    } // namespace

    // One Mirror Image of cast `id` at `at` for `ms` milliseconds with `life` Life, copying its owner's look and taunting as the cast
    // does. SummonImages makes the cast's and MultiplyImage (Archmage's Vicalyke) the copy of a killed one; the caller keeps the guid.
    TempSummon* SummonImage(Player* player, uint32 id, Position const& at, uint32 ms, double life)
    {
        TempSummon* image = player->SummonCreature(MIRROR_IMAGE_ENTRY, at, TEMPSUMMON_TIMED_DESPAWN, ms);
        if (!image)
            return nullptr;
        image->SetOwnerGUID(player->GetGUID());
        image->SetCreatorGUID(player->GetGUID());
        image->SetFaction(player->GetFaction());
        image->SetLevel(player->GetLevel());
        image->SetMaxHealth(uint32(life));
        image->SetHealth(image->GetMaxHealth());
        image->SetReactState(REACT_PASSIVE);
        player->CastSpell(image, CLONE_ME, true);
        // "taunt nearby enemies for {duration_seconds:taunt} second":
        // "nearby" has no sourced radius (mirror_image_taunt_radius_
        // yards is a placeholder), so no one is taunted until it is.
        double const taunt = Tune("mirror_image_taunt_radius_yards");
        if (taunt > 0)
            for (Unit* enemy : Combat::Enemies(player, id, image->GetPosition(), taunt))
                Apply(player, enemy, "Wizard - Taunted", Num(id, "duration_seconds", "taunt"), image);
        return image;
    }

    void SummonImages(Player* player, uint32 id)
    {
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        for (ObjectGuid guid : state.images)
            Despawn(player, guid);
        state.images.clear();
        unsigned const count = unsigned(Num(id, "pet_count"));
        double const seconds = Num(id, "duration_seconds", "image");
        double const life = player->GetMaxHealth() * Num(id, "pet_life_pct") / 100;
        if (!count || seconds <= 0 || life <= 0)
            return;
        state.imageCast = id;
        for (unsigned i = 0; i < count; ++i)
        {
            Position at = player->GetNearPosition(PET_FOLLOW_DIST, float(2 * std::numbers::pi * i / count));
            if (TempSummon* image = SummonImage(player, id, at, uint32(seconds * 1000), life))
                state.images.push_back(image->GetGUID());
        }
    }

    namespace
    {
        // Follows its Wizard and never attacks: its only work is the taunt
        // SummonImages gives it. Mirror Mimics' spells are not built.
        class ImageAI final : public ScriptedAI
        {
        public:
            explicit ImageAI(Creature* creature)
                : ScriptedAI(creature)
            {
            }

            void IsSummonedBy(WorldObject* summoner) override
            {
                if (Unit* unit = summoner ? summoner->ToUnit() : nullptr)
                    me->GetMotionMaster()->MoveFollow(unit, PET_FOLLOW_DIST, PET_FOLLOW_ANGLE);
            }

            void UpdateAI(uint32) override
            {
                Player* owner = OwnerOf(me);
                if (!owner || !owner->IsAlive() || !owner->IsInMap(me))
                    if (TempSummon* summon = me->ToTempSummon())
                        summon->UnSummon();
            }

            // Killed by an enemy of its owner (Archmage's Vicalyke's event). Running out of time, the owner leaving and ClearSummons
            // unsummon the Image: it is never killed, so none of them gets here.
            void JustDied(Unit* killer) override
            {
                Player* owner = OwnerOf(me);
                if (owner && ItemPower::ImageDeathCounts(killer != nullptr, killer && killer->IsHostileTo(owner)))
                    ItemPowers::ImageDied(owner, me);
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new Summon<ImageAI>("dc_wizard_image");
    }
} // namespace DC::Combat::Wizard::MirrorImage

namespace DC::Combat::Wizard
{
    using namespace Shared;

    bool MultiplyImage(Player* player, Unit* dead)
    {
        if (!player || !dead)
            return false;
        std::lock_guard<std::recursive_mutex> guard(mutex);
        State& state = StateOf(player);
        auto mine = std::find(state.images.begin(), state.images.end(), dead->GetGUID());
        TempSummon* summon = dead->ToTempSummon();
        uint32 const ms = ItemPower::ImageCopyMs(mine != state.images.end() && summon, summon ? summon->GetTimer() : 0);
        double const life = player->GetMaxHealth() * Num(state.imageCast, "pet_life_pct") / 100;
        if (!ms || !state.imageCast || life <= 0)
            return false;
        TempSummon* copy = MirrorImage::SummonImage(player, state.imageCast, dead->GetPosition(), ms, life);
        if (!copy)
            return false;
        *mine = copy->GetGUID();
        return true;
    }
} // namespace DC::Combat::Wizard

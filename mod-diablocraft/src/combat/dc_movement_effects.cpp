// The forced movement of an enemy that any class's skill may give (dc_movement_effects.h).
#include "dc_movement_effects.h"
#include "DatabaseEnv.h"
#include "Log.h"
#include "MotionMaster.h"
#include "Player.h"
#include "ScriptMgr.h"
#include <atomic>
#include <cmath>
#include <string>

namespace DC::Combat::Abilities
{
    namespace
    {
        // The two knockback speeds, in yards per second, from dc_ability_tuning; 0 until the table is read, and the
        // movement does nothing while either is 0.
        std::atomic<double> speedXY{0};
        std::atomic<double> speedZ{0};

        class Speeds final : public WorldScript
        {
        public:
            Speeds()
                : WorldScript("dc_movement_speeds", {WORLDHOOK_ON_STARTUP, WORLDHOOK_ON_AFTER_CONFIG_LOAD})
            {
            }
            void OnAfterConfigLoad(bool reload) override
            {
                if (reload)
                    OnStartup();
            }
            void OnStartup() override
            {
                if (auto rows = WorldDatabase.Query("SELECT name,tuned_value FROM dc_ability_tuning"))
                    do
                    {
                        auto f = rows->Fetch();
                        std::string const name = f[0].Get<std::string>();
                        if (name == "ability_knockback_speed_xy")
                            speedXY = f[1].Get<double>();
                        else if (name == "ability_knockback_speed_z")
                            speedZ = f[1].Get<double>();
                    } while (rows->NextRow());
                else
                    LOG_ERROR("server", "Missing dc_ability_tuning; knockbacks and pulls do nothing");
            }
        };
    } // namespace

    void Knock(Player* p, Unit* u, double yards)
    {
        double xy = speedXY, z = speedZ;
        if (yards <= 0 || xy <= 0 || z <= 0 || u->HasUnitState(UNIT_STATE_ROOT))
            return;
        Position dest = u->GetPosition();
        double angle = p->GetAngle(u);
        dest.Relocate(dest.GetPositionX() + std::cos(angle) * yards, dest.GetPositionY() + std::sin(angle) * yards,
                      dest.GetPositionZ());
        if (u->IsWithinLOS(dest.GetPositionX(), dest.GetPositionY(), dest.GetPositionZ()))
            u->GetMotionMaster()->MoveJump(dest, float(xy), float(z));
    }

    void Pull(Unit* u, Position const& point)
    {
        double xy = speedXY, z = speedZ;
        if (xy <= 0 || z <= 0 || u->HasUnitState(UNIT_STATE_ROOT))
            return;
        if (u->IsWithinLOS(point.GetPositionX(), point.GetPositionY(), point.GetPositionZ()))
            u->GetMotionMaster()->MoveJump(point, float(xy), float(z));
    }

    void Knockback(Player* p, Unit* u, double yards)
    {
        Knock(p, u, yards);
    }

    void PullToward(Player* p, Unit* u, double yards)
    {
        if (!p || !u || yards < 0)
            return;
        Position point = p->GetPosition();
        double const angle = p->GetOrientation();
        point.Relocate(point.GetPositionX() + std::cos(angle) * yards, point.GetPositionY() + std::sin(angle) * yards,
                       point.GetPositionZ());
        Pull(u, point);
    }

    void RegisterMovementScripts()
    {
        new Speeds();
    }
} // namespace DC::Combat::Abilities

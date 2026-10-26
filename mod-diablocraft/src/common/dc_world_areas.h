#ifndef DC_WORLD_AREAS_H
#define DC_WORLD_AREAS_H
#include <cstdint>
class WorldObject;
namespace DC::Areas
{
void RegisterScripts();
bool Ready();
bool IsOpen(std::uint32_t map, std::uint32_t area, std::uint32_t phase);
std::uint32_t SpawnPhase(WorldObject const* object, std::uint32_t requested);
// While one lives on this thread, the spawn filter lets an object through in any area: a module object the
// player opens where he stands on purpose (the Town Portal, which works in the open world, 09-rifts.md section 2).
class OwnPlacement
{
public:
    OwnPlacement();
    ~OwnPlacement();
    OwnPlacement(OwnPlacement const&) = delete;
    OwnPlacement& operator=(OwnPlacement const&) = delete;
};
}
#endif

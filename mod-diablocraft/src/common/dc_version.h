#ifndef DC_VERSION_H
#define DC_VERSION_H
#include <string>
namespace DC::Version
{
    int Schema();
    int ClientPatch();
    std::string Module();
    // The game version players see ("0.1.1", "0.1.1a"): VERSION module plus launcher_letter.
    std::string GameVersion();
    void RegisterScripts();
} // namespace DC::Version
#endif

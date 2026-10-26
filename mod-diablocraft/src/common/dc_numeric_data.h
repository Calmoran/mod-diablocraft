#ifndef DC_NUMERIC_DATA_H
#define DC_NUMERIC_DATA_H

namespace DC
{
struct BlockTuning;
namespace NumericData
{
// Startup/lazy immutable reference snapshots; missing source rows are errors.
double Rule(char const* name);
unsigned MaximumLevel();
double BaseFury(unsigned level);
BlockTuning Block();
}
}
#endif

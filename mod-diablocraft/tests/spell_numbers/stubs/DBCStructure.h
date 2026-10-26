/* Test double for the core's DBC structures (step 3 harness only). */
#ifndef DC_TEST_DBCSTRUCTURE_H
#define DC_TEST_DBCSTRUCTURE_H

struct SpellRadiusEntry
{
    unsigned int ID = 0;
    float RadiusMin = 0.0f;
    float RadiusPerLevel = 0.0f;
    float RadiusMax = 0.0f;
};

#endif

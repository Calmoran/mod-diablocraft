/* Test double for one queried column (step 3 harness only). */
#ifndef DC_TEST_FIELD_H
#define DC_TEST_FIELD_H

#include <cstdint>
#include <string>

class Field
{
public:
    std::string Value;

    template <typename T>
    T Get() const;
};

template <>
inline std::uint32_t Field::Get<std::uint32_t>() const { return std::uint32_t(std::stoul(Value)); }

template <>
inline double Field::Get<double>() const { return std::stod(Value); }

template <>
inline std::string Field::Get<std::string>() const { return Value; }

#endif

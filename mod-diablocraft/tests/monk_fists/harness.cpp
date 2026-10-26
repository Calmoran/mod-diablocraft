// diablocraft-1tiy2 (Monk 2.3.01): the real dc_monk_fists.h. Every number comes from argv (the tunables
// sheet's and monk_skill_values.csv's, read by test_monk_fists.py); nothing is typed in here.
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/monk/dc_monk_fists.h"

#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk;

static int failures = 0, cases = 0;

static void expect(bool ok, char const* what, double a = 0, double b = 0)
{
    ++cases;
    if (!ok)
    {
        std::printf("FAIL %s (%g vs %g)\n", what, a, b);
        ++failures;
    }
}

int main(int argc, char** argv)
{
    // argv: window frames, frames per second, first hit %, third hit %
    if (argc < 5)
        return 2;
    double const frames = std::atof(argv[1]), fps = std::atof(argv[2]), hit = std::atof(argv[3]), third = std::atof(argv[4]);

    // The window: 72 frames at 60 a second is 1.2 s at one attack a second; ceil rounds the frames up (1.5 aps -> 48).
    expect(ComboWindowMs(frames, fps, 1.0) == 1200, "1.2 s at 1.0 aps", double(ComboWindowMs(frames, fps, 1.0)), 1200);
    expect(ComboWindowMs(frames, fps, 1.5) == 800, "0.8 s at 1.5 aps", double(ComboWindowMs(frames, fps, 1.5)), 800);
    expect(ComboWindowMs(frames, fps, 1.4) == 867, "ceil(72/1.4)=52 frames", double(ComboWindowMs(frames, fps, 1.4)), 867);
    expect(ComboWindowMs(0, fps, 1.0) == 0 && ComboWindowMs(frames, 0, 1.0) == 0 && ComboWindowMs(frames, fps, 0) == 0,
           "an open input gives no window");

    // The combo: 1, 2, 3, then 1 again.
    Combo combo;
    std::uint64_t const window = ComboWindowMs(frames, fps, 1.0);
    expect(combo.Advance(1000, window) == 1, "first punch is stage 1");
    expect(combo.Advance(1500, window) == 2, "second punch inside the window is stage 2");
    expect(combo.Advance(2000, window) == 3, "third punch is stage 3");
    expect(combo.Advance(2500, window) == 1, "the fourth starts the combo again");
    // each punch refreshes the window: 1.0 s apart is fine at a 1.2 s window, however long the combo has run
    Combo steady;
    unsigned expected[] = {1, 2, 3, 1, 2, 3};
    bool steadyOk = true;
    for (int i = 0; i < 6; ++i)
        steadyOk &= steady.Advance(1000 + i * 1000, window) == expected[i];
    expect(steadyOk, "a punch a second keeps counting 1 2 3 1 2 3");
    // a pause longer than the window starts again at stage 1, at stage 2's place too
    Combo slow;
    slow.Advance(1000, window);
    expect(slow.Advance(1000 + window + 1, window) == 1, "a pause past the window restarts after one punch");
    Combo slower;
    slower.Advance(1000, window);
    slower.Advance(1500, window);
    expect(slower.Advance(1500 + window + 1, window) == 1, "a pause past the window restarts after two punches");
    expect(slower.Advance(1500 + window + 400, window) == 2, "and the restarted combo goes on to stage 2");
    // the window's last millisecond still counts
    Combo edge;
    edge.Advance(1000, window);
    expect(edge.Advance(1000 + window, window) == 2, "a punch exactly at the end of the window counts");

    // The split: the third hit's total is shared; one enemy takes all of it.
    expect(SplitPct(third, 1) == third, "one enemy takes the whole third hit", SplitPct(third, 1), third);
    expect(SplitPct(third, 4) == third / 4, "four share it", SplitPct(third, 4), third / 4);
    expect(SplitPct(third, 0) == 0, "no enemy, no damage");
    expect(third > hit, "the third hit is the big one", third, hit);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}

#include "../../../src/paragon/dc_paragon_math.h"
#include "../../../src/common/dc_common.h"
#include <fstream>
#include <map>
#include <iostream>
#include <sstream>
#include <cmath>
// The same isolated fixtures stat_tests.cpp uses: production
// dc_numeric_data.cpp is deliberately not linked into these pure math tests,
// and dc_common.cpp needs these four. Without them this executable does not
// link at all, which is how it stood before #55's tests were added here.
namespace DC::NumericData
{
std::map<std::string, double> rules{
    {"crit_chance_pct", 5}, {"crit_damage_pct", 50}, {"attack_speed_cap", 5},
    {"movement_cap_pct", 25}, {"magic_find_cap_pct", 300}, {"gold_find_cap_pct", 300},
    {"xp_penalty_level", 70}, {"xp_divisor", 10}, {"all_res_per_int", 0.1},
    {"class_dr_pct", 30}, {"armor_level_coefficient", 50}, {"resistance_level_coefficient", 5}};
double Rule(char const* name) { return rules.at(name); }
unsigned MaximumLevel() { return 70; }
double BaseFury(unsigned) { return 100; }
BlockTuning Block() { return {75, 100, 1}; }
}

using namespace DC::Paragon;
void Check(bool ok, char const* why = "Paragon assertion failed") { if (!ok) throw std::runtime_error(why); }
template<class F> void Reject(F f) { bool rejected=false; try {f();} catch(std::runtime_error const&) {rejected=true;} Check(rejected); }
int main(int argc,char** argv)
{
    try
    {
        Check(argc==2); std::ifstream file(argv[1]); Check(bool(file)); std::string row; std::getline(file,row);
        std::vector<XP> table; XP cumulative=0, at198=0;
        while(std::getline(file,row))
        {
            XP value=std::stoull(row.substr(row.find(',')+1)); table.push_back(value);
            cumulative+=value; if(table.size()==198) at198=cumulative;
        }
        Check(table.size()==800);
        auto state=Grant({},7199999,table); Check(state.level==0 && state.xp==7199999);
        state=Grant(state,1,table); Check(state.level==1 && state.xp==0);
        // The harness has no dc_tunables behind it, so it pins D3's published
        // value for paragon/core_only_after_level (data/d3/character_rules.csv,
        // audit row 62) the way the server reads it at runtime.
        unsigned const coreOnlyAfter = 800;
        Check(Earned(1, coreOnlyAfter)==std::array<unsigned,4>{1,0,0,0});
        Check(Earned(2, coreOnlyAfter)==std::array<unsigned,4>{1,1,0,0});
        Check(Earned(3, coreOnlyAfter)==std::array<unsigned,4>{1,1,1,0});
        Check(Earned(4, coreOnlyAfter)==std::array<unsigned,4>{1,1,1,1});
        Check(Earned(198, coreOnlyAfter)==std::array<unsigned,4>{50,50,49,49});
        Check(Earned(800, coreOnlyAfter)==std::array<unsigned,4>{200,200,200,200});
        Check(Earned(801, coreOnlyAfter)==std::array<unsigned,4>{201,200,200,200});
        Check(Earned(1000, coreOnlyAfter)==std::array<unsigned,4>{400,200,200,200});
        state=Grant({},cumulative,table);Check(state.level==800 && state.xp==0);
        Check(NextXP(799,table)==23272320000ULL);
        Check(NextXP(800,table)==23394720000ULL);
        state=Grant(state,NextXP(800,table)+1,table);Check(state.level==801 && state.xp==1);
        Check(Grant({},at198,table).level==198);
        Check(KillXP(72000,0,1,1000,3000)==72000);
        Check(KillXP(72000,160000,1,1000,3000)==1224000);
        Check(KillXP(72000,160000,4,1000,3000)==1591200);
        Check(KillXP(72000,0,2,1000,3000)==79200);
        Check(KillXP(72000,0,3,1000,3000)==86400);
        Check(KillXP(72000,0,40,1000,3000)==93600);
        Check(KillXP(1,7500,2,1000,3000)==1); // One final floor, no float/truncation.
        Reject([&]{Grant({0,1},UINT64_MAX,table);});
        Reject([&]{KillXP(UINT64_MAX,160000,4,1000,3000);});
        // Stock XP bar (decisions.md 2026-09-14): the same power-of-two divisor on
        // both numbers, and shift 0 while the threshold still fits a uint32 field.
        Check(table[583]<=0xFFFFFFFFULL && table[584]>0xFFFFFFFFULL); // P585 is the first over
        auto shown=Display(3600000,table[0]);
        Check(shown.xp==3600000 && shown.next==7200000);               // P1: exact digits
        shown=Display(table[583]-1,table[583]);
        Check(shown.next==std::uint32_t(table[583]) && shown.xp==std::uint32_t(table[583]-1));
        shown=Display(table[584]/2,table[584]);                        // P585: one halving
        Check(shown.next==std::uint32_t(table[584]/2) && shown.xp==std::uint32_t(table[584]/4));
        shown=Display(NextXP(799,table)/2,NextXP(799,table));           // P800: 23.27e9 needs /8
        Check(shown.next==std::uint32_t(23272320000ULL/8) && shown.xp==shown.next/2);
        for(std::size_t i=0;i<table.size();++i)
        {
            auto pair=Display(table[i]-1,table[i]);
            Check(pair.next>0 && pair.xp<=pair.next);                   // fits and stays ordered
        }
        shown=Display(table[0],table[0]);
        Check(shown.xp==shown.next);                                    // clamped, never thrown
        Reject([&]{Display(0,0);});
        unsigned points=0;
        for(unsigned i=0;i<5;++i)points=Change(points,10,true,50-points,50);
        Check(points==50);Reject([&]{Change(points,1,true,100,50);});
        Reject([&]{Change(0,100,true,200,50);});
        Reject([&]{Change(0,10,true,9,50);});
        Reject([&]{Change(0,1,false,0,50);});
        Reject([&]{Change(0,50,true,50,50);});
        Check(Change(50,10,false,0,50)==40);
        Check(Change(1000,100,true,100,0)==1100);
        Check(Change(100,100,false,0,0)==0);
        // #55: what the stat sheet's Experience Bonus does to one award, on
        // both award paths - the levelling hook below the cap and the Paragon
        // kill at it run the same two functions.
        Check(AwardXP(1000,0,0)==1000);                         // no sheet, no change
        Check(AwardXP(1000,Hundredths(50.0),0)==1500);
        Check(AwardXP(1000,Hundredths(5.0),0)==1050);
        Check(AwardXP(1000,0,7)==1007);                         // flat XP per kill
        Check(AwardXP(1000,Hundredths(5.0),7)==1057);           // percent FIRST, then flat
        // A +50% Ruby in the helm is +5% effective at level 70 (stats.csv), and
        // the sheet has already divided by xp_divisor before this sees it.
        Check(AwardXP(72000,Hundredths(5.0),0)==75600);
        Check(AwardXP(0,Hundredths(100.0),5)==5);
        // The two roundings, both bounded. The percentage rounds to the nearest
        // hundredth of a percent...
        Check(Hundredths(0.004)==0);
        Check(Hundredths(0.005)==1);
        Check(Hundredths(-3.0)==0);
        // ...and the product floors, which costs at most one XP per award.
        Check(AwardXP(1,Hundredths(99.99),0)==1);
        Check(AwardXP(19999,Hundredths(0.0),0)==19999);
        Reject([&]{AwardXP(UINT64_MAX,Hundredths(1.0),0);});
        // Printed here rather than with the final PASS line: the brief asks for
        // the worst case in the test, and the serialisation fixture further
        // down has been failing since before this executable could link.
        std::cout<<"PASS: #55 XP bonus on both award paths.\n";
        std::cout<<"#55 worst-case rounding: the percentage is rounded to the nearest 0.01% (at most 0.005% "
                   "of an award) and the product is floored (at most 1 XP per award); flat XP is whole XP and "
                   "is not rounded. A 72000 XP kill at +5% pays "<<AwardXP(72000,Hundredths(5.0),0)
                 <<", exact 75600, error 0.\n";
        // Exercise source 4 through the real stat engine, including one CDR
        // factor per stat (50 points must be 10%, not 50 separate factors).
        using namespace DC;
        BaseStats base; base.level=70;base.baseLife=1;
        auto naked=Calculate(base,{});
        std::vector<Contribution> c={{Source::Paragon,Stat::CritChance,7,50*0.2},
            {Source::Paragon,Stat::CooldownReduction,6,50*0.2},
            {Source::Paragon,Stat::GoldPickupRange,16,50*0.1}};
        auto sheet=Calculate(base,c);
        Check(std::abs(sheet[Stat::CritChance]-naked[Stat::CritChance]-10)<1e-9);
        Check(std::abs(sheet[Stat::CooldownReduction]-10)<1e-9);
        Check(sheet[Stat::GoldPickupRange]==5);
        Check(DeserializeSheet(Serialize(sheet))[Stat::GoldPickupRange]==5);
        Check(Calculate(base,{})[Stat::CritChance]==naked[Stat::CritChance]);
        // A version-2 record still loads, and comes back as a current one.
        //
        // This fixture was stale and failing: it was written when the header was
        // eight tokens and version 2 was one stat value short of the newest, and
        // it built its "v2" by deleting a single token. The record has grown
        // twice since (the offhand's own attacks per second in version 5, that
        // weapon's own IAS in version 6, and appended stats with each), so what
        // it produced was not a version-2 record at all and DeserializeSheet was
        // right to refuse it.
        //
        // The layout is not guessed here: DeserializeSheet itself is the frozen
        // evidence for every version, and a version-2 record is exactly
        //   2 level maxLife armorDR classDR weaponIAS attacksPerSecond flatXP
        //   <Index(Stat::GoldPickupRange) stat values>
        //   <elementalDamage, resistance, resistanceDR, damageTaken>
        // - no offhand pair, no stat from GoldPickupRange onward, and no
        // elementReduction array (version 7). So the
        // fixture drops exactly those, and nothing else, from a current record.
        //
        // Production is untouched: this builds an old record and reads it with
        // the shipped deserializer.
        std::istringstream serialized(Serialize(naked)); std::vector<std::string> tokens; std::string token;
        while(serialized>>token)tokens.push_back(token);
        unsigned const headerTokens=10;     // version + the nine scalars versions 6 and 7 write
        unsigned const legacyHeader=8;      // version + the seven version 2 wrote
        Check(tokens.size()==headerTokens+StatCount+5*ElementCount,"the sheet's token layout moved");
        tokens[0]="2";
        // The element reductions version 7 appended after the four arrays.
        tokens.resize(tokens.size()-ElementCount);
        // The stats version 2 never had, from the back so the indices hold.
        tokens.erase(tokens.begin()+headerTokens+Index(Stat::GoldPickupRange),
                     tokens.begin()+headerTokens+StatCount);
        // ...and the offhand pair version 5 and 6 added to the header.
        tokens.erase(tokens.begin()+legacyHeader,tokens.begin()+headerTokens);
        Check(tokens.size()==legacyHeader+Index(Stat::GoldPickupRange)+4*ElementCount,
              "the version-2 fixture is not a version-2 record");
        std::ostringstream legacy;for(auto const& t:tokens)legacy<<t<<' ';
        auto upgraded=DeserializeSheet(legacy.str());
        // The upgrade assertion, unchanged in meaning: an old record re-reads as
        // the current one, because everything version 2 did not carry is zero on
        // a sheet with no contributions.
        Check(Serialize(upgraded)==Serialize(naked),"a version-2 record did not upgrade to the current one");
        Check(upgraded.offhandAttacksPerSecond==0 && upgraded.offhandWeaponIAS==0,"the offhand pair was invented");
        Check(upgraded[Stat::GoldPickupRange]==0,"a stat version 2 never had came back non-zero");
        std::cout<<"PASS: XP thresholds, 800+ step, category budgets, tier/party bonuses, overflow, stock-bar scaling, caps/bulk, CHC/CDR, respec, v2/v3 persistence, #55 XP bonus.\n";
        std::cout<<"Fresh pool XP to P198="<<at198<<"; additional XP after P1="<<at198-table[0]<<"\n";
    }
    catch(std::exception const& e){std::cerr<<e.what()<<'\n';return 1;}
}

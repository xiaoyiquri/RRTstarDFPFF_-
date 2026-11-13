#!/usr/bin/env python3
"""Safely add original/paper rewiring-radius switch to RRTstarDFPFF_Tstar_1103.

Usage: python3 apply_rewire_switch.py /path/to/project

The script edits four tracked files and writes .bak_rewire_switch backups.
It fails before writing any file if expected source locations are missing.
"""
from pathlib import Path
import re
import shutil
import sys


def replace_once(s, needle, replacement, label):
    count = s.count(needle)
    if count != 1:
        raise ValueError(f"{label}: expected exactly 1 match, got {count}")
    return s.replace(needle, replacement, 1)


def regex_once(s, pattern, replacement, label):
    out, count = re.subn(pattern, replacement, s, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"{label}: cannot find expected code; local revision differs")
    return out


def patch_config(s):
    s = replace_once(s, '#include <cmath>\n', '#include <algorithm>\n#include <cmath>\n', 'config include')
    s = replace_once(
        s,
        'namespace rrtpff {\n',
        'namespace rrtpff {\n'
        'enum class RewireRadiusMode { Original, PaperCapped };\n',
        'config namespace',
    )
    s = replace_once(
        s,
        '    Real goal_tolerance{Real(.05)};\n',
        '    Real goal_tolerance{Real(.05)};\n'
        '    RewireRadiusMode rewire_radius_mode{RewireRadiusMode::Original};\n'
        '    Real paper_rewire_gamma{Real(12)};\n'
        '    Real paper_rewire_radius_cap{Real(1)};\n',
        'config fields',
    )
    s = replace_once(
        s,
        '    void validate() const {\n',
        '    Real rewiringRadius(std::size_t tree_nodes, int flat_dim) const {\n'
        '        if (tree_nodes == 0 || flat_dim <= 0)\n'
        '            throw std::invalid_argument("Invalid rewire radius dimensions");\n'
        '        const Real exponent = Real(1) / Real(flat_dim);\n'
        '        if (rewire_radius_mode == RewireRadiusMode::PaperCapped) {\n'
        '            const Real n = static_cast<Real>(tree_nodes);\n'
        '            return std::min(paper_rewire_radius_cap,\n'
        '                paper_rewire_gamma * std::pow(std::log(n + Real(1)) / n, exponent));\n'
        '        }\n'
        '        const Real n = static_cast<Real>(tree_nodes + 1);\n'
        '        return rewire_factor * range *\n'
        '            std::pow(std::log(n) / n, exponent);\n'
        '    }\n'
        '    void validate() const {\n',
        'config radius method',
    )
    s = replace_once(
        s,
        '            collision_samples > 1000000)\n',
        '            collision_samples > 1000000 ||\n'
        '             (rewire_radius_mode == RewireRadiusMode::PaperCapped &&\n'
        '              (!std::isfinite(paper_rewire_gamma) || paper_rewire_gamma <= Real(0) ||\n'
        '               !std::isfinite(paper_rewire_radius_cap) || paper_rewire_radius_cap <= Real(0))))\n',
        'config validation',
    )
    return s


def patch_rrt(s):
    pattern = (
        r'            const Real n = static_cast<Real>\(tree_\.size\(\) \+ 1\);\s*'
        r'const Real radius = config_\.rewire_factor \* config_\.range \*\s*'
        r'std::pow\(std::log\(n\) / n, Real\(1\) / Real\(Model::FlatDim\)\);'
    )
    return regex_once(
        s, pattern,
        '            const Real radius = config_.rewiringRadius(tree_.size(), Model::FlatDim);',
        'rrt radius formula',
    )


def patch_runner(s):
    s = replace_once(s, '#include <fstream>\n', '#include <cstdlib>\n#include <fstream>\n', 'runner include')
    s = replace_once(
        s,
        '    c.range=n["range"].as<float>();c.rewire_factor=n["rewire_factor"].as<float>();\n',
        '    c.range=n["range"].as<float>();c.rewire_factor=n["rewire_factor"].as<float>();\n'
        '    c.paper_rewire_gamma=n["rewire_gamma"].as<float>(12.f);\n'
        '    c.paper_rewire_radius_cap=n["rewire_radius_cap"].as<float>(1.f);\n'
        '    std::string rewire_mode=n["rewire_radius_mode"].as<std::string>("original");\n'
        '    if (const char* v=std::getenv("RRT_REWIRE_MODE")) rewire_mode=v;\n'
        '    if (const char* v=std::getenv("RRT_REWIRE_GAMMA")) c.paper_rewire_gamma=std::stof(v);\n'
        '    if (const char* v=std::getenv("RRT_REWIRE_RADIUS_CAP")) c.paper_rewire_radius_cap=std::stof(v);\n'
        '    if (rewire_mode=="original") c.rewire_radius_mode=RewireRadiusMode::Original;\n'
        '    else if (rewire_mode=="paper") c.rewire_radius_mode=RewireRadiusMode::PaperCapped;\n'
        '    else throw std::invalid_argument("rewire_radius_mode must be original or paper");\n',
        'runner settings reader',
    )
    s = replace_once(
        s,
        '    Model model(adapter,y);auto config=floatPlanner(y["planner"]);\n',
        '    Model model(adapter,y);auto config=floatPlanner(y["planner"]);\n'
        '    std::cout << "rewire_mode="\n'
        '              << (config.rewire_radius_mode==RewireRadiusMode::PaperCapped ? "paper" : "original")\n'
        '              << " range=" << config.range\n'
        '              << " rewire_factor=" << config.rewire_factor\n'
        '              << " gamma=" << config.paper_rewire_gamma\n'
        '              << " radius_cap=" << config.paper_rewire_radius_cap << std::endl;\n',
        'runner log',
    )
    return s


def patch_sh(s):
    s = replace_once(
        s,
        'PFF_ARGS=()\n',
        'PFF_ARGS=()\n'
        '# Rewiring radius: original (existing formula) or paper (capped radius).\n'
        'REWIRE_MODE="original"\n'
        'REWIRE_GAMMA=12.0\n'
        'REWIRE_RADIUS_CAP=1.0\n',
        'sh options',
    )
    s = replace_once(
        s,
        '    echo "========== Build benchmark =========="\n',
        '    case "$REWIRE_MODE" in\n'
        '        original|paper) ;;\n'
        '        *) echo "ERROR: REWIRE_MODE must be original or paper" >&2; return 1 ;;\n'
        '    esac\n'
        '    export RRT_REWIRE_MODE="$REWIRE_MODE"\n'
        '    export RRT_REWIRE_GAMMA="$REWIRE_GAMMA"\n'
        '    export RRT_REWIRE_RADIUS_CAP="$REWIRE_RADIUS_CAP"\n'
        '    echo "Rewire: mode=$REWIRE_MODE gamma=$REWIRE_GAMMA radius_cap=$REWIRE_RADIUS_CAP"\n'
        '    echo "========== Build benchmark =========="\n',
        'sh export',
    )
    s = replace_once(
        s,
        '    exp_dir="$project_dir/results/${CASE}_$(date +%Y%m%d_%H%M%S_%N)"\n',
        '    exp_dir="$project_dir/results/${CASE}_$(date +%Y%m%d_%H%M%S_%N)"\n'
        '    mkdir -p "$exp_dir"\n'
        '    printf "mode: %s\\ngamma: %s\\nradius_cap: %s\\n" \\\n'
        '        "$REWIRE_MODE" "$REWIRE_GAMMA" "$REWIRE_RADIUS_CAP" \\\n'
        '        > "$exp_dir/rewire_settings.txt"\n',
        'sh experiment provenance',
    )
    return s


def main(root):
    patches = {
        'common/planner_config.h': patch_config,
        'core/rrtstar.h': patch_rrt,
        'benchmark/production_runner.cpp': patch_runner,
        'run_one_case.sh': patch_sh,
    }
    outputs = {}
    for relative, patch in patches.items():
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        original = path.read_text(encoding='utf-8')
        if 'enum class RewireRadiusMode' in original or (
            relative == 'run_one_case.sh' and 'REWIRE_MODE=' in original
        ):
            raise ValueError(f"{relative}: appears already patched; no changes made")
        outputs[path] = patch(original)
    for path, updated in outputs.items():
        backup = path.with_name(path.name + '.bak_rewire_switch')
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(updated, encoding='utf-8')
        print(f'Updated {path} (backup: {backup})')
    print('Next: bash -n run_one_case.sh; cmake --build build --target benchmark -j 4')
    print('Then set REWIRE_MODE=original or paper in run_one_case.sh.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 apply_rewire_switch.py /path/to/project')
    main(Path(sys.argv[1]).expanduser().resolve())

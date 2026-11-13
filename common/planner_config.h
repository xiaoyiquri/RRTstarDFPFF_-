#pragma once
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <stdexcept>
namespace rrtpff {
enum class RewireRadiusMode { Original, PaperCapped };
template<class Real = double> struct PlannerConfigT {
    double timeout{10};
    Real goal_bias{Real(.1)}, range{4}, rewire_factor{3};
    Real goal_tolerance{Real(.05)};
    RewireRadiusMode rewire_radius_mode{RewireRadiusMode::Original};
    Real paper_rewire_gamma{Real(12)};
    Real paper_rewire_radius_cap{Real(1)};
    Real goal_connect_radius{Real(1)}; // Flat-output distance; not success tolerance
    std::size_t max_iterations{10000}, max_nodes{4001};
    std::size_t hard_safety_node_cap{1000000};
    unsigned seed{40};
    bool simd_enabled{false};
    bool simd_pff{true}, simd_nn{true}, simd_screen{true};
    bool interleaved_samples{true};
    std::size_t collision_samples{33};
    bool prune{false}, stop_at_first_solution{false};
    bool rewire_before_first_solution{true};
    bool enable_rewire{true};
    bool explicit_goal_connection{false};
    // Optional test/baseline prechecks. Robot models expose one SIMD validator.
    bool candidate_precheck{false}, cache_goal_connections{false};
    bool model_time_hints{false};
    std::size_t minimum_parent_candidates{0};
    Real rewiringRadius(std::size_t tree_nodes, int flat_dim) const {
        if (tree_nodes == 0 || flat_dim <= 0)
            throw std::invalid_argument("Invalid rewire radius dimensions");
        const Real exponent = Real(1) / Real(flat_dim);
        if (rewire_radius_mode == RewireRadiusMode::PaperCapped) {
            const Real n = static_cast<Real>(tree_nodes);
            return std::min(paper_rewire_radius_cap,
                paper_rewire_gamma * std::pow(std::log(n + Real(1)) / n, exponent));
        }
        const Real n = static_cast<Real>(tree_nodes + 1);
        return rewire_factor * range *
            std::pow(std::log(n) / n, exponent);
    }
    void validate() const {
        if (!std::isfinite(timeout) || timeout <= 0 || !std::isfinite(range) || range <= 0 ||
            !std::isfinite(goal_bias) || goal_bias < 0 || goal_bias > 1 ||
            !std::isfinite(rewire_factor) || rewire_factor <= 0 || !std::isfinite(goal_tolerance) ||
            goal_tolerance < 0 || (max_nodes && max_nodes < 2) || !std::isfinite(goal_connect_radius) || goal_connect_radius <= Real(0) ||
            (hard_safety_node_cap && hard_safety_node_cap < 2) ||
            minimum_parent_candidates > 1000000 || collision_samples < 2 ||
            collision_samples > 1000000 ||
             (rewire_radius_mode == RewireRadiusMode::PaperCapped &&
              (!std::isfinite(paper_rewire_gamma) || paper_rewire_gamma <= Real(0) ||
               !std::isfinite(paper_rewire_radius_cap) || paper_rewire_radius_cap <= Real(0))))
            throw std::invalid_argument("Invalid planner configuration");
    }
};
using PlannerConfig = PlannerConfigT<double>;
} // namespace rrtpff

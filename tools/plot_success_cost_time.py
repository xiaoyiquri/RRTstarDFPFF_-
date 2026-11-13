#!/usr/bin/env python3
"""Draw THREE complementary figures from an RRT* anytime benchmark.

Source files:
  <experiment>/<case>/results.csv
  <experiment>/<case>/anytime_<run>.csv

Figures:
  (1) success_cost_time : cumulative success + conditional best-so-far mean.
      Its mean MAY rise when new runs become solved (changing cohort).
  (2) cost_time_fixed_cohort : fixed-cohort mean at ABSOLUTE search time.
      Starts after every included run has found its first solution.
  (3) cost_time_aligned_normalized : fixed-cohort normalized mean, with
      each run's FIRST solution as time zero, over the common observed horizon.

Both fixed-cohort curves are non-increasing by construction from genuine
zero-order-held per-run best-so-far events. No artificial interpolation,
smoothing, or global running minimum of the fluctuating ensemble mean.
"""
import argparse
import csv
import math
import warnings
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def as_float(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else float('nan')
    except (TypeError, ValueError):
        return float('nan')


def locate_folder(root, case):
    root = root.resolve()
    if (root / 'results.csv').is_file():
        return root
    if case:
        folder = root / case
        if (folder / 'results.csv').is_file():
            return folder
        raise SystemExit(f'Cannot find {folder / "results.csv"}')
    candidates = sorted(p.parent for p in root.glob('*/results.csv'))
    if len(candidates) != 1:
        raise SystemExit('Cannot infer case: supply --case uni_bugtrap (etc.).')
    return candidates[0]


def read_experiment(folder):
    with (folder / 'results.csv').open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit('Empty results.csv')

    result = []
    for row in rows:
        run_id = int(row['run'])
        seed = str(row.get('seed', str(run_id)))
        solved = str(row.get('success', '0')).strip().lower() in ('1', 'true')
        first = as_float(row.get('first_solution_time')) if solved else float('inf')
        budget = as_float(row.get('search_time'))
        if not math.isfinite(budget) or budget <= 0:
            budget = as_float(row.get('planning_time'))
        if not math.isfinite(budget) or budget <= 0:
            budget = float('nan')

        event_path = folder / f'anytime_{run_id}.csv'
        events = []
        if event_path.is_file():
            with event_path.open(newline='', encoding='utf-8') as f:
                for event in csv.DictReader(f):
                    t = as_float(event.get('search_time'))
                    j = as_float(event.get('cost'))
                    if math.isfinite(t) and t >= 0 and math.isfinite(j):
                        events.append((t, j))
        events.sort(key=lambda pair: pair[0])

        if solved and events:
            # Keep the actual best-so-far value at every event, not the
            # instantaneous (possibly greater) candidate cost.
            best = math.inf
            monotone = []
            for t, cost in events:
                best = min(best, cost)
                monotone.append((t, best))
            events = monotone
            if not math.isfinite(first):
                first = events[0][0]
            # A run cannot contribute to cost until both its recorded first
            # solution and its first available anytime event exist.
            cost_start = max(first, events[0][0])
        else:
            cost_start = float('inf')
            if solved:
                warnings.warn(f'run {run_id}: solved but missing valid {event_path.name}; '
                              'included in success but not the cost curves')
        result.append({'run': run_id, 'seed': seed, 'solved': solved,
                       'first': first, 'budget': budget, 'events': events,
                       'cost_start': cost_start})
    return result


def get_budget(run, fallback):
    return run['budget'] if math.isfinite(run['budget']) else fallback


def run_cost_at_times(run, times, xmax):
    out = np.full(times.shape, np.nan, dtype=float)
    if not run['solved'] or not run['events']:
        return out
    t_event, c_event = (np.asarray(x, dtype=float) for x in zip(*run['events']))
    idx = np.searchsorted(t_event, times, side='right') - 1
    valid = (idx >= 0) & (times >= run['cost_start']) & (times <= get_budget(run, xmax) + 1e-8)
    out[valid] = c_event[idx[valid]]
    return out


def summary(matrix):
    n = np.sum(np.isfinite(matrix), axis=0)
    mean = np.divide(np.nansum(matrix, axis=0), n,
                     out=np.full(matrix.shape[1], np.nan), where=n > 0)
    median = np.full(matrix.shape[1], np.nan)
    p25, p75 = median.copy(), median.copy()
    for k in np.flatnonzero(n):
        values = matrix[:, k]
        values = values[np.isfinite(values)]
        p25[k], median[k], p75[k] = np.percentile(values, [25, 50, 75])
    return n, mean, median, p25, p75


def save_csv(path, headers, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([f'{float(v):.12g}' if math.isfinite(float(v)) else '' for v in row])
    print('Wrote', path)


def save_figure(fig, directory, stem):
    for ext in ('png', 'pdf'):
        path = directory / f'{stem}.{ext}'
        fig.savefig(path, dpi=210, bbox_inches='tight')
        print('Wrote', path)
    plt.close(fig)


def draw_band_and_lines(ax, x, mean, median, p25, p75, ylabel,
                        label_mean='Mean best-so-far cost', logx=False):
    plotted, = ax.plot(x, mean, lw=2, label=label_mean)
    ax.fill_between(x, p25, p75, color=plotted.get_color(), alpha=.18,
                    label='25th–75th percentile')
    ax.plot(x, median, ls='--', lw=1.35, label='Median')
    ax.set_ylabel(ylabel)
    if logx:
        ax.set_xscale('log')
    ax.grid(True, which='major', alpha=.3)
    ax.grid(True, which='minor', alpha=.12)
    ax.legend(fontsize=8.5, loc='best')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', type=Path, required=True)
    p.add_argument('--case', default='')
    p.add_argument('--xmin', type=float, default=1e-4)
    p.add_argument('--xmax', type=float, default=None)
    p.add_argument('--points', type=int, default=1600)
    p.add_argument('--output', type=Path, default=None)
    args = p.parse_args()

    folder = locate_folder(args.experiment, args.case)
    runs = read_experiment(folder)
    n = len(runs)
    known_budgets = [r['budget'] for r in runs if math.isfinite(r['budget'])]
    xmax = args.xmax if args.xmax is not None else (min(known_budgets) if known_budgets else 10.)
    if args.xmin <= 0 or xmax <= args.xmin:
        raise SystemExit('--xmin must be > 0 and --xmax must exceed --xmin')
    if args.points < 20:
        raise SystemExit('--points must be >= 20')
    if known_budgets and xmax > min(known_budgets) + 1e-4:
        warnings.warn('xmax exceeds the shortest observed budget: ended runs are excluded '
                      'rather than carried forward')
    output = args.output if args.output is not None else folder.parent / 'success_cost_time_figures'
    output.mkdir(parents=True, exist_ok=True)

    count_unique_seeds = len({r['seed'] for r in runs})
    if count_unique_seeds < n:
        warnings.warn(f'{n} runs but only {count_unique_seeds} distinct seed(s): '
                      'repeated seeds are not independent random sampling trials')
    cohort = [r for r in runs if r['solved'] and r['events']]

    # Figure 1: ORIGINAL cumulative success and changing-cohort conditional cost.
    grid = np.geomspace(args.xmin, xmax, args.points)
    firsts = np.array([r['first'] for r in runs])
    success_count = np.count_nonzero(firsts[:, None] <= grid[None, :], axis=0)
    success_rate = 100. * success_count / n
    matrix = np.vstack([run_cost_at_times(r, grid, xmax) for r in runs])
    contributing, mean, med, p25, p75 = summary(matrix)
    save_csv(output / 'success_cost_time_data.csv',
             ['time_s', 'success_percent', 'solved_runs', 'cost_contributing_runs',
              'mean_cost_solved_only', 'median_cost_solved_only', 'q25_cost', 'q75_cost'],
             zip(grid, success_rate, success_count, contributing, mean, med, p25, p75))

    fig, (a, b) = plt.subplots(2, 1, sharex=True, figsize=(9.4, 7),
                              gridspec_kw={'height_ratios': [1, 1.18], 'hspace': .10})
    a.step(grid, success_rate, where='post', lw=2,
           label=f'{n} runs; {count_unique_seeds} unique seeds')
    a.set_ylabel('Success [%]')
    a.set_ylim(-2, 102)
    a.grid(True, which='major', alpha=.3)
    a.grid(True, which='minor', alpha=.12)
    a.legend(loc='lower right', fontsize=9)
    if np.isfinite(mean).any():
        draw_band_and_lines(b, grid, mean, med, p25, p75, 'Best-so-far cost',
                            'Conditional mean (solved runs)')
    else:
        b.text(.5, .5, 'No valid anytime cost events', transform=b.transAxes,
               ha='center', va='center')
    b.set_xlabel('Computation time [s] (log scale)')
    b.set_xscale('log')
    b.set_xlim(args.xmin, xmax)
    fig.suptitle(f'{folder.name}: Success + conditional cost (N={n})', fontsize=12)
    fig.subplots_adjust(left=.10, right=.97, top=.93, bottom=.10)
    save_figure(fig, output, 'success_cost_time')

    # Figures 2 and 3: same FIXED cohort of successful, recorded runs.
    if not cohort:
        print('No run has a valid solution plus anytime data; figures 2 and 3 skipped.')
        return
    cohort_n = len(cohort)
    cohort_start = max(r['cost_start'] for r in cohort)
    cohort_end = min([xmax] + [get_budget(r, xmax) for r in cohort])
    if cohort_start >= cohort_end:
        print('No common absolute-time window for fixed cohort; figures 2 and 3 skipped.')
        return

    # Include the exact cohort start, log-distribute points to expose early progress.
    t_fixed = np.geomspace(max(cohort_start, args.xmin), cohort_end, args.points)
    fixed_cost = np.vstack([run_cost_at_times(r, t_fixed, xmax) for r in cohort])
    cnt_fixed, mean_fixed, med_fixed, q25_fixed, q75_fixed = summary(fixed_cost)
    if not np.all(cnt_fixed == cohort_n):
        raise RuntimeError('Internal error: fixed cohort is not fully observed at all grid times')
    # The checks below guard against upstream data inconsistencies, NOT a correction.
    if np.any(np.diff(mean_fixed) > 2e-10):
        raise RuntimeError('Fixed-cohort mean increased: check source events/budgets')
    save_csv(output / 'cost_time_fixed_cohort.csv',
             ['absolute_time_s', 'cohort_count', 'mean_cost', 'median_cost', 'q25_cost', 'q75_cost'],
             zip(t_fixed, cnt_fixed, mean_fixed, med_fixed, q25_fixed, q75_fixed))
    fig, ax = plt.subplots(figsize=(9.4, 4.8))
    draw_band_and_lines(ax, t_fixed, mean_fixed, med_fixed, q25_fixed, q75_fixed,
                        'Best-so-far cost', 'Fixed-cohort mean', logx=True)
    ax.set_xlim(t_fixed[0], cohort_end)
    ax.set_xlabel('Absolute computation time [s] (log scale)')
    ax.set_title(f'{folder.name}: Fixed-cohort cost (N={cohort_n}/{n})')
    ax.text(.99, .97, f'All included runs solved by t = {cohort_start:.4g} s',
            transform=ax.transAxes, fontsize=8.5, ha='right', va='top')
    fig.tight_layout()
    save_figure(fig, output, 'cost_time_fixed_cohort')

    # Aligned time tau: start at own first cost record; restrict to the time
    # horizon that is observed for EVERY member of the fixed cohort.
    common_horizon = min(min(xmax, get_budget(r, xmax)) - r['cost_start'] for r in cohort)
    if common_horizon <= 0:
        print('No common post-first-solution horizon; figure 3 skipped.')
        return
    tau = np.linspace(0., common_horizon, args.points)
    ratio_matrix = np.empty((cohort_n, len(tau)), dtype=float)
    for i, run in enumerate(cohort):
        absolute_times = run['cost_start'] + tau
        values = run_cost_at_times(run, absolute_times, xmax)
        initial = values[0]
        if not math.isfinite(initial) or initial <= 0:
            raise RuntimeError(f'Invalid first cost in run {run["run"]}: {initial}')
        ratio_matrix[i] = values / initial
    cnt_align, mean_align, med_align, q25_align, q75_align = summary(ratio_matrix)
    if not np.all(cnt_align == cohort_n) or np.any(np.diff(mean_align) > 2e-10):
        raise RuntimeError('Aligned normalized curve is inconsistent with fixed-cohort data')
    save_csv(output / 'cost_time_aligned_normalized.csv',
             ['seconds_after_first_solution', 'cohort_count', 'mean_J_over_Jfirst',
              'median_J_over_Jfirst', 'q25_ratio', 'q75_ratio', 'mean_improvement_percent'],
             zip(tau, cnt_align, mean_align, med_align, q25_align, q75_align,
                 100. * (1. - mean_align)))
    fig, ax = plt.subplots(figsize=(9.4, 4.8))
    draw_band_and_lines(ax, tau, mean_align, med_align, q25_align, q75_align,
                        'Normalized cost: J / J_first', 'Mean normalized cost')
    ax.set_xlim(0., common_horizon)
    ax.set_xlabel('Time since each run first solved [s] (linear scale)')
    ax.set_title(f'{folder.name}: Anytime cost after first solution (N={cohort_n}/{n})')
    ax.text(.99, .96, f'Mean improvement at end: {100.*(1.-mean_align[-1]):.2f}%',
            transform=ax.transAxes, ha='right', va='top', fontsize=9)
    fig.tight_layout()
    save_figure(fig, output, 'cost_time_aligned_normalized')

    print(f'Runs: {n} ({count_unique_seeds} distinct seeds); '
          f'successes by {xmax:.3g}s: {int(success_count[-1])}/{n}')
    print(f'Fixed cohort: {cohort_n} runs, absolute window [{cohort_start:.6g}, '
          f'{cohort_end:.6g}] s; aligned common horizon {common_horizon:.6g} s')
    print('Figure 1 conditional mean may rise when newly solved runs join.')
    print('Figures 2 and 3 use a fixed successful cohort and are non-increasing.')


if __name__ == '__main__':
    main()


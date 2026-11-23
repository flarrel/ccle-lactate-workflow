"""Simulate an illustrative lactate pool under constant supply and clearance."""
import csv
import json
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp


def simulate(supply, clearance, initial=1.0):
    if supply < 0 or clearance <= 0 or initial < 0:
        raise ValueError("Expected nonnegative supply and initial pool and positive clearance")
    times = np.linspace(0, 24, 49)
    result = solve_ivp(
        lambda _time, pool: supply - clearance * pool,
        (times[0], times[-1]),
        [initial],
        rtol=1e-9,
        atol=1e-10,
        t_eval=times,
    )
    if not result.success:
        raise RuntimeError(result.message)
    steady = supply / clearance
    expected = steady + (initial - steady) * np.exp(-clearance * times)
    np.testing.assert_allclose(result.y[0], expected, rtol=1e-7, atol=1e-8)
    return times, result.y[0], steady


def main():
    scenarios = {"reference": (2, 0.5), "higher_supply": (3, 0.5), "slower_clearance": (2, 0.25)}
    summaries = {}
    with Path("pathway.csv").open("w", newline="") as stream:
        output = csv.writer(stream)
        output.writerow(["scenario", "simulation_time", "relative_lactate_pool"])
        for name, (supply, clearance) in scenarios.items():
            times, levels, steady = simulate(supply, clearance)
            for time, level in zip(times, levels):
                output.writerow([name, f"{time:.3f}", f"{level:.9f}"])
            summaries[name] = {"supply": supply, "clearance": clearance, "steady_state": steady}
    Path("pathway.json").write_text(
        json.dumps(
            {
                "status": "illustrative simulation with assumed parameters",
                "equation": "dL/dt = supply - clearance * L",
                "scenarios": summaries,
            },
            indent=2,
        ) + "\n"
    )


if __name__ == "__main__":
    main()

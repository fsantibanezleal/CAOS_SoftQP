"""Generate publication figures from the complete checked experimental exports."""

import json
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / "figures"
OUT.mkdir(exist_ok=True)
campaign = json.loads((ROOT / "data/derived/experiments/campaign.json").read_bytes())
stream = json.loads((ROOT / "data/derived/experiments/stream.json").read_bytes())
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "pdf.fonttype": 42, "figure.dpi": 130})
names = dict(lifted="Native lift", asymmetric="Asymmetric projection", daqp="DAQP")


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight", metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight")
    plt.close(fig)


fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.8), sharex=True)
for ax, condition in zip(axes, (1, 1000)):
    for method, label in names.items():
        cells = sorted((r for r in campaign["cells"] if r["split"] == "heldout"
                        and r["family"] == "asymmetric-elastic" and r["density"] == 0.05
                        and r["condition"] == condition and r["method"] == method), key=lambda r: r["n"])
        xs = [r["n"] for r in cells]
        ax.plot(xs, [r["median_seconds"] * 1000 for r in cells], marker="o", markersize=3, label=label)
        ax.fill_between(xs, [r["quantile_25_seconds"] * 1000 for r in cells],
                        [r["quantile_75_seconds"] * 1000 for r in cells], alpha=0.12)
    ax.set(yscale="log", xlabel="Original variables", title=f"Diagonal condition {condition}")
    ax.set_xticks([32, 64, 128, 256])
axes[0].set_ylabel("Cold end-to-end time (ms)")
axes[1].legend(fontsize=7)
save(fig, "cold-times")

endpoint = campaign["primary_endpoint"]
fig, ax = plt.subplots(figsize=(6.8, 1.9))
low, high = np.asarray(endpoint["confidence_interval_95"]) * 100
estimate = endpoint["median_relative_reduction"] * 100
ax.plot([low, high], [0, 0], linewidth=3)
ax.scatter([estimate], [0], s=50, zorder=3)
ax.axvline(0, color="gray", linestyle=":", label="No reduction")
ax.axvline(10, color="C1", linestyle="--", label="Preregistered practical target")
ax.set(xlabel="Relative cold end-to-end reduction (%)", yticks=[], ylim=(-0.6, 0.6))
ax.legend(fontsize=7, loc="upper right")
save(fig, "primary-effect")

fig, ax = plt.subplots(figsize=(6.8, 2.7))
for method, label in names.items():
    cells = sorted((r for r in campaign["cells"] if r["split"] == "robustness" and r["method"] == method),
                   key=lambda r: r["condition"])
    ax.plot([r["condition"] for r in cells], [r["max_normalized_gap"] for r in cells], marker="o", label=label)
ax.set(xscale="log", xlabel="Diagonal Hessian condition", ylabel="Maximum normalized objective gap")
ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
ax.legend(fontsize=7)
save(fig, "conditioning")

times = np.array([frame["time_seconds"] for frame in stream["frames"]])
states = np.array([frame["state"] for frame in stream["frames"]])
controls = np.array([frame["applied_control"] for frame in stream["frames"]])
fig, axes = plt.subplots(3, 1, figsize=(6.8, 4.6), sharex=True)
for ax, values, unit, limits in zip(axes, [states[:, 0], states[:, 1], controls],
                                  ["Position (m)", "Velocity (m/s)", "Acceleration (m/s²)"],
                                  [(-0.4, 0.4), (-1.5, 1.5), (-1, 1)]):
    ax.plot(times, values, marker="o", markersize=2.5)
    for bound in limits:
        ax.axhline(bound, color="gray", linestyle=":", linewidth=0.8)
    ax.set_ylabel(unit)
    for impulse in (1.6, 4.0):
        ax.axvline(impulse, color="C1", linestyle="--", linewidth=0.8)
axes[0].set_title("Common oracle-driven trajectory; state limits soft, actuator limits hard")
axes[-1].set_xlabel("Elapsed time (s)")
save(fig, "control-stream")

fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.9), sharey=True)
for ax, zone in zip(axes, (0, 1)):
    for ident, label, method in [("C13", "Published mixed costs", "generalized"),
                                 ("C14", "Separable upper/lower ratio 3", "asymmetric"),
                                 ("C15", "Separable upper/lower ratio 1.5", "asymmetric")]:
        case = json.loads((ROOT / f"data/derived/softqp/{ident}.json").read_bytes())
        result = next(r["result"] for r in case["runs"] if r["method"] == method)
        thermal = np.array(result["x"][:291]).reshape((97, 3))
        ax.plot(np.arange(97) / 4, thermal[:, zone], label=label, linewidth=1)
    ax.fill_between([8, 20], [21, 21], [24, 24], color="gray", alpha=0.13)
    ax.set(xlabel="Time (h)", title=f"Thermal zone {zone + 1}", xlim=(0, 24))
axes[0].set_ylabel("Temperature (°C)")
axes[1].legend(fontsize=6.5, loc="best")
save(fig, "energy-policies")

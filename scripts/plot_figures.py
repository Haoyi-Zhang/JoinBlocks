#!/usr/bin/env python3
"""Reproduce the mathematical hedge example as a vector PDF; no experiment."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]

def configure_fonts(font_dir: Path | None = None) -> str:
    """Use the bundled, unmodified OFL Libertine TTFs; never a silent fallback."""
    from matplotlib import font_manager
    directory = font_dir or ROOT / "fonts"
    regular = directory / "LinLibertine_Rah.ttf"
    italic = directory / "LinLibertine_RIah.ttf"
    if regular.is_file() and italic.is_file():
        for path in (regular, italic):
            font_manager.fontManager.addfont(str(path))
        family = font_manager.FontProperties(fname=str(regular)).get_name()
    else:
        family = "Linux Libertine"
        for style in ("normal", "italic"):
            font_manager.findfont(
                font_manager.FontProperties(family=family, style=style),
                fallback_to_default=False,
            )
    matplotlib.rcParams.update({
        "font.family": family, "font.size": 8.5,
        "pdf.fonttype": 42, "ps.fonttype": 42, "pdf.use14corefonts": False,
        "text.usetex": False, "mathtext.fontset": "custom",
        "mathtext.rm": family, "mathtext.it": family + ":italic",
        "mathtext.bf": family, "mathtext.sf": family, "mathtext.tt": family,
        "mathtext.cal": family, "mathtext.fallback": None,
        "axes.unicode_minus": True, "axes.linewidth": 0.55,
        "xtick.major.width": 0.45, "ytick.major.width": 0.45,
        "xtick.major.size": 3, "ytick.major.size": 3,
    })
    resolved = font_manager.findfont(
        font_manager.FontProperties(family=family), fallback_to_default=False)
    print("FIGURE_FONT", resolved)
    return family


def hedge_cost(profile: tuple[int, int], t: float) -> float:
    """The declared relaxed world is w=(t, 1-t), with t in [0, 1]."""
    return profile[0] * t + profile[1] * (1 - t)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path)
    args = parser.parse_args()
    configure_fonts(args.font_dir)
    output = ROOT / "figures"
    paper = ROOT.parent / "paper/figures"
    output.mkdir(parents=True, exist_ok=True)
    if paper.parent.is_dir():
        paper.mkdir(parents=True, exist_ok=True)
    # Retain the original short, wide 349.51 x 94.07 bp plotting rectangle.
    fig = plt.figure(figsize=(386 / 72, 140 / 72))
    ax = fig.add_axes([34 / 386, 27 / 140, 349.51 / 386, 94.07 / 140])
    for profile, dash, width in [
        ((6, 14), "-", 0.6), ((10, 10), "--", 0.8), ((14, 6), ":", 0.8),
    ]:
        y = [hedge_cost(profile, t) for t in (0, 1)]
        ax.plot([0, 1], y, color="black", linestyle=dash,
                linewidth=width, label=f"({profile[0]}, {profile[1]})")
        # Only these endpoints are admissible integer database worlds.
        ax.plot([0, 1], y, "o", color="black", markersize=3.6, clip_on=False)
    ax.set(xlim=(0, 1), ylim=(5, 15))
    ax.set_xticks([0, 0.5, 1], ["0", "0.5", "1"])
    ax.set_yticks([6, 10, 14])
    ax.tick_params(direction="in", top=True, right=True, labelsize=8.97, pad=3)
    ax.set_xlabel(r"$t$ in $w=(t,1-t)$", fontsize=8.97, labelpad=4)
    ax.set_ylabel("Abstract cost", fontsize=8.97, labelpad=4)
    ax.legend(ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.014),
              frameon=False, borderaxespad=0, fontsize=8.97,
              handletextpad=0.3, columnspacing=0.7, handlelength=1.8)
    path = output / "hedge.pdf"
    fig.savefig(path, metadata={"Creator": None, "Producer": None,
                                "CreationDate": None, "ModDate": None})
    plt.close(fig)
    if paper.is_dir():
        shutil.copyfile(path, paper / path.name)
    print("FIGURE_OK", path)


if __name__ == "__main__":
    main()

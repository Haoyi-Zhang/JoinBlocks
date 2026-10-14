"""Optional artifact renderer mechanically copied from the current paper renderer.

Reads retained measurements only. --output-dir (required) must be outside the
project. Derived DATs and PDFs are written only there. PDF drawing requires ReportLab;
validation and tests use only the standard library. Drawing requires
--font-root pointing to external TeX fonts; no font binaries are vendored.
No native measurements or full paper-table generation are run.

Geometry is constructed in Python with ReportLab. Labels use the installed
Linux Libertine 5.3 regular Type 1 font, embedded in full. Its ASCII advances
are retained beside this source. This is the native pdfLaTeX face and the
Type 1 counterpart of the XeLaTeX manuscript's OpenType Libertine face.
Font files are not vendored or relicensed.

Run from any directory with --font-root <TeX distribution fonts directory>.
--column-width-pt sets the asset box (legacy default 241.1475 TeX pt).
--display-width-pt sets its declared inclusion width (default 430.00462 TeX pt);
only label sizes are compensated so they display at 8 TeX pt. Setting both
widths equal reproduces the uncompensated asset. TeX pt -> PDF bp is 72/72.27.
Figure heights follow the original plotting declarations.
"""
import argparse
import csv
import math
import re
from decimal import Decimal
from pathlib import Path

pdfmetrics = None
canvas = None


def load_drawing_dependency():
    global pdfmetrics, canvas
    try:
        from reportlab.pdfbase import pdfmetrics as metrics
        from reportlab.pdfgen import canvas as pdf_canvas
    except ImportError as exc:
        raise RuntimeError("Optional PDF drawing requires ReportLab; install it in the selected drawing environment") from exc
    pdfmetrics, canvas = metrics, pdf_canvas

HERE = Path(__file__).resolve().parent
ARTIFACT = HERE.parent
DISPLAY_WIDTH_TEX_PT = 430.00462
FONT = "ManuscriptRoman"
PT = 72 / 72.27
CM = 72 / 2.54


def register_font(root):
    pfb = Path(root) / "type1/public/libertine/LinLibertineT.pfb"
    face = pdfmetrics.EmbeddedType1Face(
        str(HERE / "libertine-labels.afm"), str(pfb))
    pdfmetrics.registerTypeFace(face)
    font = pdfmetrics.Font(FONT, face.name, "WinAnsiEncoding")
    font.substitutionFonts = []  # Missing labels must not introduce Helvetica.
    pdfmetrics.registerFont(font)


def new_pdf(name, width, height, output_dir):
    return canvas.Canvas(str(output_dir / name), pagesize=(width, height),
                         initialFontName=FONT, initialFontSize=8,
                         pageCompression=1, invariant=1)


def text(c, x, y, label, size=8, align="center"):
    # The reviewed labels use ASCII; never silently substitute a font.
    if any(ord(ch) < 32 or ord(ch) > 126 for ch in label):
        raise ValueError("Label requires explicit native glyph support")
    c.setFont(FONT, size)
    c.setFillColorRGB(0, 0, 0)
    if align == "left":
        c.drawString(x, y, label)
    elif align == "right":
        c.drawRightString(x, y, label)
    else:
        c.drawCentredString(x, y, label)


def axes(c, box, xrange, yrange, xticks, yticks, xlabel, ylabel,
         logx=False, logy=False, grid=True, ticksize=8, labelsize=9):
    left, bottom, width, height = box
    transform_x = math.log10 if logx else float
    transform_y = math.log10 if logy else float
    xa, xb = map(transform_x, xrange)
    ya, yb = map(transform_y, yrange)

    def xy(x, y):
        return (left + width * (transform_x(x) - xa) / (xb - xa),
                bottom + height * (transform_y(y) - ya) / (yb - ya))

    c.setLineWidth(.35)
    if grid:
        c.setStrokeColorRGB(.86, .86, .86)
        for value, _ in xticks:
            x, _ = xy(value, yrange[0])
            c.line(x, bottom, x, bottom + height)
        for value, _ in yticks:
            _, y = xy(xrange[0], value)
            c.line(left, y, left + width, y)
    c.setStrokeColorRGB(.28, .28, .28)
    c.rect(left, bottom, width, height, fill=0, stroke=1)
    for value, label in xticks:
        x, _ = xy(value, yrange[0])
        c.line(x, bottom, x, bottom - 3)
        text(c, x, bottom - 13, label, ticksize)
    for value, label in yticks:
        _, y = xy(xrange[0], value)
        c.line(left - 3, y, left, y)
        text(c, left - 6, y - 2.4, label, ticksize, "right")
    text(c, left + width / 2, bottom - 22, xlabel, labelsize)
    if ylabel:
        c.saveState()
        c.translate(left - 26, bottom + height / 2)
        c.rotate(90)
        text(c, 0, 0, ylabel, labelsize)
        c.restoreState()
    return xy


def legend(c, items, width, y, size=8):
    # Compact one-row native-font legend; no in-figure title or footer.
    lengths = [14 + pdfmetrics.stringWidth(name, FONT, size)
               for name, _ in items]
    total = sum(lengths) + 14 * (len(items) - 1)
    if total > width - 8:
        raise ValueError("Legend would exceed the figure width")
    x = (width - total) / 2
    c.setLineWidth(.5)
    for (name, colour), length in zip(items, lengths):
        c.setStrokeColorRGB(0, 0, 0)
        c.setFillColorRGB(*colour)
        c.rect(x, y, 8, 5, fill=1, stroke=1)
        text(c, x + 12, y - .1, name, size, "left")
        x += length + 14


def line_points(c, points, shape="circle", radius=1.8, connect=True):
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(.6)
    if connect:
        p = c.beginPath()
        p.moveTo(*points[0])
        for point in points[1:]:
            p.lineTo(*point)
        c.drawPath(p)
    c.setFillColorRGB(1, 1, 1)
    for x, y in points:
        if shape == "square":
            c.rect(x - radius, y - radius, 2 * radius, 2 * radius,
                   fill=1, stroke=1)
        elif shape == "triangle":
            p = c.beginPath()
            p.moveTo(x, y + radius)
            p.lineTo(x - radius, y - radius)
            p.lineTo(x + radius, y - radius)
            p.close()
            c.drawPath(p, fill=1, stroke=1)
        else:
            c.circle(x, y, radius, fill=1, stroke=1)


def bars(c, xy, categories, series, colours, barwidth):
    for i, category in enumerate(categories):
        centre, baseline = xy(i, 0)
        for j, values in enumerate(series):
            top = xy(i, float(values[i]))[1]
            x = centre + (j - (len(series) - 1) / 2) * barwidth
            c.setFillColorRGB(*colours[j])
            c.setStrokeColorRGB(0, 0, 0)
            c.setLineWidth(.5)
            # Zero-height bars remain at baseline, never given invented height.
            c.rect(x - barwidth / 2, baseline, barwidth, top - baseline,
                   stroke=1, fill=1)


def table(path, delimiter=None):
    with path.open(newline="", encoding="utf-8") as stream:
        if delimiter:
            return list(csv.DictReader(stream, delimiter=delimiter))
        names = stream.readline().split()
        return [dict(zip(names, line.split())) for line in stream
                if line.strip()]



def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare_output_dir(path):
    path = Path(path).resolve()
    if path.is_relative_to(ARTIFACT.parent.resolve()):
        raise ValueError("--output-dir must be outside the project")
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError("--output-dir must be a fresh or empty directory")
    path.mkdir(parents=True, exist_ok=True)
    return path


def dat_text(rows, columns):
    return " ".join(columns) + "\n" + "".join(
        " ".join(row[column] for column in columns) + "\n" for row in rows)


FIELDNAMES = tuple(
    "case family regime n k integer_worlds vertices plans unique_profiles regret "
    "point_regret worst_cost_regret box_regret local_regret box_claim support_calls "
    "expansions root_frontier max_frontier states component_frontier component_expansions "
    "certificate_bytes checker_records sql_profile_checks sql_plan_world_checks "
    "producer_cpu_s checker_cpu_s oracle_cpu_s baseline_cpu_s sql_cpu_s case_cpu_s "
    "case_wall_s maxrss_kib oracle_match checker_accepted".split())
TEXT_FIELDS = {"case", "family", "regime", "oracle_match", "checker_accepted"}
EXPECTED_CASES = {
    f"{family}-{n}-{k}-{regime}-{seed}": (family, regime, n, k)
    for family in ("branch", "path", "star") for n in (4, 5, 6, 7)
    for k in (4, 6) for regime in ("balanced", "skewed") for seed in (101, 202)}
EXPECTED_CASES.update({
    f"commerce-{seed}-{filtered}":
        ("commerce", "filtered" if filtered else "unfiltered", 7, 4)
    for seed in (303, 404, 505) for filtered in (0, 1)})


def validate_rows(raw):
    """Validate the complete frozen plot denominator; never filter a bad row."""
    require(len(raw) == 102, "Expected all 102 retained observations")
    require(all(set(row) == set(FIELDNAMES) and
                all(isinstance(v, str) and v.strip() for v in row.values())
                for row in raw), "Malformed CSV row/columns")
    require(len({row["case"] for row in raw}) == 102 and
            {row["case"] for row in raw} == set(EXPECTED_CASES),
            "Missing, duplicated or unknown frozen case")
    rows = []
    for original in raw:
        row = dict(original)
        for key in FIELDNAMES:
            if key in TEXT_FIELDS:
                continue
            if key.endswith("_s"):
                try:
                    value = float(row[key])
                except ValueError as exc:
                    raise ValueError("Invalid time: " + key) from exc
                require(math.isfinite(value) and value > 0, "Nonpositive/nonfinite time: " + key)
            else:
                require(re.fullmatch(r"0|[1-9][0-9]*", row[key]) is not None,
                        "Nonintegral/negative count: " + key)
                value = int(row[key])
            row[key] = value
        require((row["family"], row["regime"], row["n"], row["k"]) ==
                EXPECTED_CASES[row["case"]], "Case metadata disagree")
        require(row["oracle_match"] == row["checker_accepted"] == "True",
                "Failed retained case")
        require(0 < row["root_frontier"] <= row["component_frontier"] <= 40,
                "Invalid frontier or point outside retained axes")
        require(all(row[key] >= row["regret"] for key in
                    ("point_regret", "worst_cost_regret", "box_regret", "local_regret"))
                and row["box_claim"] >= row["box_regret"], "Retained regret inconsistency")
        require(all(.5 <= 1000 * row[key] <= 120
                    for key in ("producer_cpu_s", "checker_cpu_s")),
                "Timing point outside retained logarithmic axes")
        rows.append(row)
    return rows


def load_observations(folder):
    with (Path(folder) / "cases.csv").open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        require(tuple(reader.fieldnames or ()) == FIELDNAMES, "Unexpected/duplicate CSV header")
        rows = validate_rows(list(reader))
    # Exactly summarize.py's seconds -> milliseconds and nine-decimal formatting.
    # Row order and coincident points remain intact. No certificate/benchmark execution.
    frontiers = [{"contract": str(r["root_frontier"]), "component": str(r["component_frontier"]),
                  "n": str(r["n"]), "k": str(r["k"])} for r in rows]
    timings = [{"producer": f'{1000*r["producer_cpu_s"]:.9f}',
                "checker": f'{1000*r["checker_cpu_s"]:.9f}',
                "n": str(r["n"]), "k": str(r["k"])} for r in rows]
    return {"frontiers.dat": frontiers, "timings.dat": timings}


def main_args(default_width):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--input-dir", type=Path, default=ARTIFACT / "results/campaign",
                        help="Retained 102-case campaign directory; read-only")
    parser.add_argument("--column-width-pt", default=default_width, type=float)
    parser.add_argument("--display-width-pt", default=DISPLAY_WIDTH_TEX_PT, type=float,
                        help="Declared inclusion width; labels display at 8 TeX pt. Set equal to asset width for legacy fidelity.")
    args = parser.parse_args()
    require(math.isfinite(args.column_width_pt) and args.column_width_pt * PT > 90,
            "Invalid column width")
    require(math.isfinite(args.display_width_pt) and args.display_width_pt > 0,
            "Invalid declared display width")
    return args


def draw(width, tables, output_dir, display_width_pt=DISPLAY_WIDTH_TEX_PT):
    require(math.isfinite(display_width_pt) and display_width_pt > 0,
            "Invalid declared display width")
    label_scale = width / (display_width_pt * PT)
    specs = [
        ("frontiers.dat", "frontiers.pdf", "component", "contract",
         4.9 * CM - 14.6, (0, 40), [0, 10, 20, 30, 40],
         "Componentwise root frontier", "Contract-aware root frontier", False),
        ("timings.dat", "timings.pdf", "producer", "checker",
         5 * CM - 14.6, (.5, 120), [1, 10, 100],
         "Producer CPU (ms)", "Checker CPU (ms)", True)]
    for source, output, xkey, ykey, height, limits, ticks, xlabel, ylabel, log in specs:
        rows = tables[source]
        require(len(rows) == 102, "Retain every primary observation, including overlaps")
        c = new_pdf(output, width, height, output_dir)
        # Match the retained PGFPlots' actual ~195 x 94/97 bp plotting areas.
        # Keep 8-TeX-pt labels at the declared inclusion width. Scaling the
        # narrow asset to the manuscript column must not enlarge the text.
        xy = axes(c, (35, 25, width - 45, height - 30),
                  limits, limits, [(n, str(n)) for n in ticks],
                  [(n, str(n)) for n in ticks], xlabel, ylabel,
                  logx=log, logy=log, grid=False,
                  ticksize=8 * PT * label_scale, labelsize=8 * PT * label_scale)
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(.6)
        c.setDash(3, 2)
        c.line(*xy(limits[0], limits[0]), *xy(limits[1], limits[1]))
        c.setDash()
        points = [xy(Decimal(row[xkey]), Decimal(row[ykey])) for row in rows]
        # No jitter, deduplication, aggregation, or observation deletion.
        line_points(c, points, radius=1.5 * PT, connect=False)
        c.save()


if __name__ == "__main__":
    args = main_args((506.295 - 24) / 2)
    tables = load_observations(args.input_dir)
    load_drawing_dependency()
    register_font(args.font_root)
    output_dir = prepare_output_dir(args.output_dir)
    for name, rows in tables.items():
        columns = ("contract", "component", "n", "k") if name == "frontiers.dat" else ("producer", "checker", "n", "k")
        (output_dir / name).write_text(dat_text(rows, columns), encoding="utf-8", newline="\n")
    draw(args.column_width_pt * PT, tables, output_dir, args.display_width_pt)

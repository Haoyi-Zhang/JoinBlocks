"""Render the two-obligation certificate protocol directly as a vector PDF."""
from pathlib import Path
import argparse

NODES = {
    'contract': (5.4, 7.1, 5.0, 0.85, 'Tree, literal templates,\ncount intervals and total'),
    'snapshot': (2.7, 5.65, 4.5, 0.85, 'Join-key snapshot\nand untrusted mapper'),
    'search': (8.1, 5.65, 4.5, 0.85, 'Untrusted plan search\nand pruning'),
    'membership': (2.7, 4.3, 4.5, 0.85, 'Row partition and\ntemplate types'),
    'plancert': (8.1, 4.3, 4.5, 0.85, 'Plans, coverage,\nthresholds, witnesses'),
    'mcheck': (2.7, 2.9, 4.5, 1.05, 'Membership checker:\ncover, renaming, isolation'),
    'pcheck': (8.1, 2.9, 4.5, 1.05, 'Plan checker:\nprofiles and inequalities'),
    'result': (5.4, 1.0, 8.9, 1.15, 'Accepted snapshot belongs to the family;\nselected plan is family-minimax\nand snapshot regret is bounded'),
}
EDGES = [('contract', 'snapshot'), ('contract', 'search'),
         ('snapshot', 'membership'), ('membership', 'mcheck'),
         ('search', 'plancert'), ('plancert', 'pcheck'),
         ('mcheck', 'result'), ('pcheck', 'result')]


def render(output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Rectangle, FancyArrowPatch
    fonts = Path(__file__).resolve().parents[1] / 'fonts'
    for name in ('LinLibertine_Rah.ttf', 'LinLibertine_RIah.ttf'):
        font_manager.fontManager.addfont(str(fonts / name))
    family = font_manager.FontProperties(fname=str(fonts / 'LinLibertine_Rah.ttf')).get_name()
    plt.rcParams.update({'font.family': family, 'font.size': 8.5,
                         'pdf.fonttype': 42, 'ps.fonttype': 42, 'text.usetex': False})
    fig = plt.figure(figsize=(10.8 / 2.54, 7.8 / 2.54))
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, 10.8), ylim=(0, 7.8))
    ax.set_aspect('equal'); ax.axis('off')
    labels = []
    for name, (x, y, w, h, text) in NODES.items():
        ax.add_patch(Rectangle((x-w/2, y-h/2), w, h, linewidth=.55,
                               edgecolor='black', facecolor='white', zorder=2))
        labels.append((ax.text(x, y, text, ha='center', va='center',
                               linespacing=1.12, zorder=3), (x-w/2,y-h/2,x+w/2,y+h/2)))
    for source, target in EDGES:
        x,y,w,h,_ = NODES[source]; tx,ty,tw,th,_ = NODES[target]
        if target == 'result': tx += -2.2 if x < tx else 2.2
        ax.add_patch(FancyArrowPatch((x,y-h/2), (tx,ty+th/2),
                                     arrowstyle='-|>', mutation_scale=7.5,
                                     linewidth=.55, color='black', zorder=1))
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for artist, bounds in labels:
        b = artist.get_window_extent(renderer).transformed(ax.transData.inverted())
        if b.x0 < bounds[0] or b.x1 > bounds[2] or b.y0 < bounds[1] or b.y1 > bounds[3]:
            raise ValueError('label exceeds node: ' + artist.get_text())
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(output/'certificate.pdf', metadata={'Creator':'Python Matplotlib',
                  'Producer':None, 'CreationDate':None, 'ModDate':None})
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    render(parser.parse_args().output_dir)

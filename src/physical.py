"""Bounded in-memory hash joins executing an explicit tree on actual bag rows.

No SQL optimizer chooses the order. Result tuples contain snapshot row identities;
this prototype has no indexes, disk I/O, payload columns, parallelism, or spills.
"""
from collections import Counter


class HashPlan:
    def __init__(self, contract, plan):
        self.n = contract['n']
        self.edges = tuple(tuple(e) for e in contract['edges'])

        def compile_node(node):
            if type(node) is int:
                if not 0 <= node < self.n:
                    raise ValueError('invalid leaf')
                return (1 << node, node)
            if type(node) not in (tuple, list) or len(node) != 2:
                raise ValueError('invalid node')
            left, right = compile_node(node[0]), compile_node(node[1])
            lm, rm = left[0], right[0]
            if lm & rm:
                raise ValueError('repeated alias')
            bridges = [(str(e), a, b) if lm >> a & 1 else (str(e), b, a)
                       for e, (a, b) in enumerate(self.edges)
                       if (lm >> a & 1 and rm >> b & 1)
                       or (lm >> b & 1 and rm >> a & 1)]
            if len(bridges) != 1:
                raise ValueError('not a connected tree split')
            return (lm | rm, left, right, bridges[0], tuple(bool(lm >> i & 1)
                                                          for i in range(self.n)))
        self.tree = compile_node(plan)
        if self.tree[0] != (1 << self.n) - 1:
            raise ValueError('incomplete plan')

    def execute(self, snapshot):
        tables = snapshot['tables']
        emitted, inputs, counts = 0, 0, {}

        def run(node):
            nonlocal emitted, inputs
            state = node[0]
            if len(node) == 2:
                alias = node[1]
                return [tuple(row if i == alias else -1 for i in range(self.n))
                        for row in range(len(tables[alias]))]
            left, right = run(node[1]), run(node[2])
            inputs += len(left) + len(right)
            if inputs > 1_000_000:
                raise ValueError('hash-input budget')
            edge, a, b = node[3]
            index = {}
            for row in right:
                index.setdefault(tables[b][row[b]][edge], []).append(row)
            out = []
            for x in left:
                for y in index.get(tables[a][x[a]][edge], ()):
                    if emitted >= 200_000:
                        raise ValueError('materialized-output budget')
                    out.append(tuple(x[i] if take_left else y[i]
                                     for i, take_left in enumerate(node[4])))
                    emitted += 1
            counts[state] = len(out)
            return out
        rows = run(self.tree)
        return rows, {'intermediate_rows': emitted, 'hash_input_rows': inputs,
                      'internal_counts': counts, 'output_rows': len(rows)}


def sqlite_bag(contract, snapshot):
    """Untimed independent SQL bag reference, including duplicate row identities."""
    import sqlite3
    db = sqlite3.connect(':memory:')
    try:
        for i, rows in enumerate(snapshot['tables']):
            attrs = [str(e) for e, (a, b) in enumerate(contract['edges']) if i in (a, b)]
            db.execute(f'CREATE TABLE r{i} (tid INTEGER,' +
                       ','.join(f'e{e} TEXT COLLATE BINARY' for e in attrs) + ')')
            db.executemany(f'INSERT INTO r{i} VALUES (' +
                           ','.join('?' for _ in range(len(attrs) + 1)) + ')',
                           [(row_id, *(str(row[e]) for e in attrs))
                            for row_id, row in enumerate(rows)])
        sql = 'SELECT ' + ','.join(f'r{i}.tid' for i in range(contract['n']))
        sql += ' FROM ' + ','.join(f'r{i}' for i in range(contract['n']))
        sql += ' WHERE ' + ' AND '.join(f'r{a}.e{e}=r{b}.e{e}'
                                      for e, (a, b) in enumerate(contract['edges']))
        return Counter(db.execute(sql))
    finally:
        db.close()

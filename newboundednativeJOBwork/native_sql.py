"""Native, bounded SQL materializations of the checked logical tree.

Original MIT-licensed JoinBlocks extension. Each internal node is a separate CTAS,
so SQLite cannot flatten/reorder across logical nodes. SQLite still chooses
physical scans/indexes within each binary join. Cardinality is not latency.
"""
from collections import Counter
from copy import deepcopy
import sqlite3

import attest


class SqlTree:
    def __init__(self, contract, plan):
        self.n = contract['n']
        self.edges = tuple(tuple(e) for e in contract['edges'])
        self.plan = deepcopy(plan)
        self.nodes = []

        def columns(mask):
            out = []
            for i in range(self.n):
                if mask >> i & 1:
                    out.append(f'tid{i}')
                    out.extend(f'key{i}_{e}' for e, pair in enumerate(self.edges) if i in pair)
            return out

        def compile_node(p):
            if type(p) is int:
                if not 0 <= p < self.n:
                    raise ValueError('invalid SQL leaf')
                return 1 << p, f'r{p}'
            if type(p) not in (list, tuple) or len(p) != 2:
                raise ValueError('invalid SQL node')
            lm, lt = compile_node(p[0])
            rm, rt = compile_node(p[1])
            if lm & rm:
                raise ValueError('repeated SQL alias')
            crossing = [(e, a, b) if lm >> a & 1 else (e, b, a)
                        for e, (a, b) in enumerate(self.edges)
                        if (lm >> a & 1 and rm >> b & 1) or (lm >> b & 1 and rm >> a & 1)]
            if len(crossing) != 1:
                raise ValueError('SQL tree contains Cartesian/disconnected split')
            e, a, b = crossing[0]
            mask = lm | rm
            projection = [f'{"L" if lm >> i & 1 else "R"}.{c}'
                          for i in range(self.n) if mask >> i & 1
                          for c in columns(1 << i)]
            select = (f'SELECT {",".join(projection)} FROM {lt} AS L JOIN {rt} AS R '
                      f'ON L.key{a}_{e} = R.key{b}_{e} COLLATE BINARY')
            self.nodes.append((mask, f'p{mask}', select))
            return mask, f'p{mask}'

        mask, self.root = compile_node(plan)
        if mask != (1 << self.n) - 1:
            raise ValueError('incomplete SQL plan')


class SqlWindow:
    """Own the actual engine input; attest SQL readback, not an unrelated copy.

    A private in-memory connection, no external transactional capture. A failed
    refresh revokes execution. Base writes are denied after installation as a
    local API guard, not as a hostile-caller security boundary.
    """
    def __init__(self, contract, max_rows=200_000):
        if type(max_rows) is not int or not 0 <= max_rows <= 200_000:
            raise ValueError('invalid SQL row budget')
        self.contract = deepcopy(contract)
        self.max_rows = max_rows
        self._db = sqlite3.connect(':memory:', isolation_level=None, cached_statements=0)
        self._db.execute('PRAGMA automatic_index=ON')
        self._db.execute('PRAGMA temp_store=MEMORY')
        self._db.set_progress_handler(self._progress, 1000)
        self._ticks = 0
        self._active = False
        self._last_window = -1
        self._writing = True
        self.attrs = [[str(e) for e, pair in enumerate(contract['edges']) if i in pair]
                      for i in range(contract['n'])]
        for i, attrs in enumerate(self.attrs):
            definitions = [f'tid{i} INTEGER PRIMARY KEY'] + [
                f'key{i}_{e} TEXT NOT NULL COLLATE BINARY' for e in attrs]
            self._db.execute(f'CREATE TABLE r{i} ({",".join(definitions)})')
        self._writing = False
        self._db.set_authorizer(self._authorize)

    def _progress(self):
        self._ticks += 1
        return int(self._ticks > 200_000)  # 200 million VM instructions per call

    def _authorize(self, action, arg1, arg2, database, trigger):
        if not self._writing and database == 'main' and action in (
                sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
                sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_ALTER_TABLE):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def open_window(self, window, contract, snapshot, mapping):
        self._active = False
        if type(window) is not int or window <= self._last_window:
            raise ValueError('SQL window must advance')
        self._last_window = window
        if contract != self.contract:
            raise ValueError('changed SQL contract')
        owned = deepcopy(snapshot)
        packet = deepcopy(mapping)
        # Validate schema and bounds before loading potentially malformed input.
        attest.verify(self.contract, owned, packet)
        self._ticks = 0
        self._writing = True
        try:
            self._db.execute('BEGIN')
            for i, rows in enumerate(owned['tables']):
                self._db.execute(f'DELETE FROM r{i}')
                self._db.executemany(f'INSERT INTO r{i} VALUES (' +
                    ','.join('?' for _ in range(len(self.attrs[i]) + 1)) + ')',
                    [(tid, *(str(row[e]) for e in self.attrs[i])) for tid, row in enumerate(rows)])
            self._db.execute('COMMIT')
        except Exception:
            if self._db.in_transaction:
                self._db.execute('ROLLBACK')
            raise
        finally:
            self._writing = False
        tables = []
        for i, attrs in enumerate(self.attrs):
            rows = self._db.execute(f'SELECT * FROM r{i} ORDER BY tid{i}').fetchall()
            if [row[0] for row in rows] != list(range(len(rows))):
                raise ValueError('SQL row-identity readback mismatch')
            tables.append([{e: int(value) for e, value in zip(attrs, row[1:])} for row in rows])
        loaded = {'instance': owned['instance'], 'tables': tables}
        if loaded != owned:
            raise ValueError('SQL snapshot readback mismatch')
        verdict = attest.verify(self.contract, loaded, packet)
        self._active = True
        return tuple(verdict['world']), {'loaded_rows': verdict['rows'],
                                         'membership_checks': 2}

    def _require_active(self):
        if not self._active:
            raise ValueError('no accepted SQL window')
        self._ticks = 0

    def execute(self, tree, explain=False):
        self._require_active()
        if tree.n != self.contract['n'] or tree.edges != tuple(map(tuple, self.contract['edges'])):
            raise ValueError('SQL tree/query mismatch')
        counts, plans, created = {}, [], []
        try:
            for mask, table, select in tree.nodes:
                # At most one overflow-sentinel row beyond the remaining total
                # budget is materialized. A truncated node is always rejected,
                # never presented as the exact bag or exact cardinality.
                bounded_select = select + f' LIMIT {self.max_rows - sum(counts.values()) + 1}'
                if explain:
                    plans.append({'mask': mask, 'sql': bounded_select,
                                  'eqp': self._db.execute('EXPLAIN QUERY PLAN ' + bounded_select).fetchall()})
                self._db.execute(f'CREATE TEMP TABLE {table} AS {bounded_select}')
                created.append(table)
                count = self._db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                counts[mask] = count
                if sum(counts.values()) > self.max_rows:
                    raise ValueError('SQL materialized-output budget')
            rows = self._db.execute('SELECT ' + ','.join(f'tid{i}' for i in range(tree.n)) +
                                    f' FROM {tree.root}').fetchall()
            return rows, {'internal_counts': counts, 'intermediate_rows': sum(counts.values()),
                          'output_rows': len(rows), 'explain': plans}
        finally:
            self._ticks = 0
            for table in reversed(created):
                self._db.execute(f'DROP TABLE {table}')

    def natural_sql(self):
        n = self.contract['n']
        sql = 'SELECT ' + ','.join(f'r{i}.tid{i}' for i in range(n))
        sql += ' FROM ' + ','.join(f'r{i}' for i in range(n))
        sql += ' WHERE ' + ' AND '.join(f'r{a}.key{a}_{e}=r{b}.key{b}_{e} COLLATE BINARY'
                                      for e, (a, b) in enumerate(self.contract['edges']))
        sql += f' LIMIT {self.max_rows + 1}'
        return sql

    def natural(self, explain=False):
        self._require_active()
        sql = self.natural_sql()
        eqp = self._db.execute('EXPLAIN QUERY PLAN ' + sql).fetchall() if explain else []
        cursor = self._db.execute(sql)
        rows = cursor.fetchmany(self.max_rows + 1)
        if len(rows) > self.max_rows:
            raise ValueError('SQL final-output budget')
        return rows, {'output_rows': len(rows), 'sql': sql, 'eqp': eqp}

    def close(self):
        self._active = False
        self._db.close()


def bag(rows):
    return Counter(rows)

"""A query-semantic bridge on original authored rows, not IMDb data.

Official SQL is supplied at runtime from the author's CWI archive. No upstream
SQL is redistributed/relicensed by these original MIT-licensed adapters.
"""
from collections import Counter
from copy import deepcopy
import sqlite3

from src.optimizer import optimize
from src.reuse import ReuseSession, known_world_plan
from native_sql import SqlTree, SqlWindow, bag

ALIASES = ('k', 'mi', 'mk', 't')
EDGES = [[0, 2], [2, 3], [3, 1]]


def project(template):
    # Local filters occur before joining. The MIN payload is outside the theorem.
    return [
        [{'0': row[0]} for row in template['keyword'] if 'sequel' in row[1].lower()],
        [{'2': row[1]} for row in template['movie_info'] if row[2] == 'Bulgaria'],
        [{'0': row[2], '1': row[1]} for row in template['movie_keyword']],
        [{'1': row[0], '2': row[0]} for row in template['title'] if row[2] > 2010],
    ]


def contract(fixture):
    return {'name': 'job3b-authored-filtered-contract', 'n': 4, 'edges': deepcopy(EDGES),
            'lower': fixture['lower'], 'upper': fixture['upper'], 'total': fixture['total'],
            'blocks': [project(t) for t in fixture['templates']], 'aliases': list(ALIASES),
            'provenance': fixture['provenance']}


def instantiate(fixture, world):
    inst = contract(fixture)
    tables = {name: [] for name in ('keyword', 'movie_info', 'movie_keyword', 'title')}
    projected = [[] for _ in ALIASES]
    packet = {'instance': inst['name'], 'copies': []}
    copy_id = 0
    for j, copies in enumerate(world):
        for _ in range(copies):
            offset = 1000 * (copy_id + 1)
            template = fixture['templates'][j]
            for name, rows in template.items():
                for row in rows:
                    if name == 'keyword':
                        actual = [offset + row[0], row[1]]
                    elif name == 'title':
                        actual = [offset + row[0], row[1], row[2]]
                    elif name == 'movie_info':
                        actual = [offset + row[0], offset + row[1], row[2]]
                    else:
                        actual = [offset + row[0], offset + row[1], offset + row[2]]
                    tables[name].append(actual)
            filtered = project({name: tables[name][-len(template[name]):]
                                for name in template})
            assignment = []
            for i, rows in enumerate(filtered):
                assignment.append(list(range(len(projected[i]), len(projected[i]) + len(rows))))
                projected[i].extend(rows)
            packet['copies'].append({'type': j, 'rows': assignment})
            copy_id += 1
    return inst, tables, {'instance': inst['name'], 'tables': projected}, packet


def original_query(db, sql):
    # Offline reviewed SELECT, with a read-only authorizer; never executes scripts.
    def authorize(action, arg1, arg2, database, trigger):
        return sqlite3.SQLITE_OK if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ,
                                               sqlite3.SQLITE_FUNCTION) else sqlite3.SQLITE_DENY
    db.set_authorizer(authorize)
    try:
        return db.execute(sql).fetchall()
    finally:
        db.set_authorizer(None)


def run_fixture(fixture, official_sql, source_identity):
    inst = contract(fixture)
    cert, _, h = optimize(inst)
    session = ReuseSession(inst, cert)
    initial = [fixture['total'], 0]
    fixed = known_world_plan(inst, h, initial)
    results = []
    # Plan commitment occurs before constructing the later world.
    for number, world in enumerate((initial, [0, fixture['total']])):
        _, tables, snapshot, packet = instantiate(fixture, world)
        frozen, revealed = session.open_window(number, inst, snapshot, packet)
        adaptive = known_world_plan(inst, h, revealed)
        db = sqlite3.connect(':memory:')
        try:
            # Consumed columns and PKs agree with the official schema. Other
            # columns are unused here; this is not a full-schema loading exercise.
            definitions = {
                'keyword': 'id INTEGER PRIMARY KEY, keyword TEXT NOT NULL',
                'movie_info': 'id INTEGER PRIMARY KEY, movie_id INTEGER NOT NULL, info TEXT NOT NULL',
                'movie_keyword': 'id INTEGER PRIMARY KEY, movie_id INTEGER NOT NULL, keyword_id INTEGER NOT NULL',
                'title': 'id INTEGER PRIMARY KEY, title TEXT NOT NULL, production_year INTEGER',
            }
            for name, definition in definitions.items():
                db.execute(f'CREATE TABLE {name} ({definition})')
                db.executemany(f'INSERT INTO {name} VALUES (' +
                               ','.join('?' for _ in tables[name][0]) + ')', tables[name])
            expected = original_query(db, official_sql)
            engine = SqlWindow(inst)
            try:
                engine.open_window(number, inst, snapshot, packet)
                reference, _ = engine.natural()
                title_payload = [row[1] for row in tables['title'] if row[2] > 2010]
                policies = {}
                for policy, plan in (('robust', session.plan), ('known_fixed', fixed),
                                     ('adaptive', adaptive)):
                    rows, metrics = engine.execute(SqlTree(inst, plan), explain=True)
                    if bag(rows) != bag(reference):
                        raise AssertionError('JOB3b filtered preaggregation bag mismatch')
                    aggregate = [(min((title_payload[row[3]] for row in rows), default=None),)]
                    if aggregate != expected:
                        raise AssertionError('JOB3b MIN result differs from exact official SQL')
                    policies[policy] = {'plan': plan, 'result': aggregate, **metrics}
                results.append({'world': world, 'official_result': expected,
                                'preaggregation_rows': len(reference), 'policies': policies})
            finally:
                engine.close()
        finally:
            db.close()
    return {'scope': 'Exact official JOB3b SELECT on original authored miniature rows; not JOB data or full JOB validation.',
            'official_source': source_identity, 'fixture_provenance': fixture['provenance'],
            'certified_regret': cert['regret'], 'template_profiles': h,
            'contract': inst, 'certificate': cert, 'windows': results}

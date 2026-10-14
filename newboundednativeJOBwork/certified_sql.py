"""Bind the checked minimax selection to the native SQL execution API.

Original MIT-licensed adapter. This local caller-facing API does not expose a
tree-selection argument at execution. It is not authentication or hostile-caller
isolation. The experiment measures its constituent operations, not this adapter.
"""
from copy import deepcopy

from src.reuse import ReuseSession
from native_sql import SqlTree, SqlWindow


class CertifiedSqlSession:
    def __init__(self, contract, certificate):
        self._contract = deepcopy(contract)
        checked = ReuseSession(self._contract, certificate)
        self._tree = SqlTree(self._contract, checked.plan)
        self._sql = SqlWindow(self._contract)
        self.regret = checked.regret
        self.plan_checks = checked.plan_checks
        self.accepted_windows = 0

    @property
    def plan(self):
        return deepcopy(self._tree.plan)

    def open_window(self, window, contract, snapshot, mapping):
        # SQL readback membership checks and refresh revocation are performed
        # by the actual engine-owning SqlWindow, under this committed contract.
        result = self._sql.open_window(window, contract, snapshot, mapping)
        self.accepted_windows += 1
        return result

    def execute(self, explain=False):
        return self._sql.execute(self._tree, explain=explain)

    def close(self):
        self._sql.close()

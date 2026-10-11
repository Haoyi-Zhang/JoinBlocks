"""Commit one checked plan before future windows; recheck membership, not plans.

This is a local lifecycle interface, not an authenticated snapshot-capture service.
The consumer must supply the same contract and a complete snapshot each window.
"""
from copy import deepcopy
from types import MappingProxyType

import attest
import checker


def checked_window(contract, snapshot, mapping):
    """Check owned bytes, then expose immutable row bags for this window."""
    owned = deepcopy(snapshot)
    verdict = attest.verify(contract, owned, deepcopy(mapping))
    frozen = MappingProxyType({'instance': owned['instance'],
                              'tables': tuple(tuple(MappingProxyType(row) for row in rows)
                                              for rows in owned['tables'])})
    return frozen, tuple(verdict['world'])


class ReuseSession:
    def __init__(self, contract, certificate):
        self._contract = deepcopy(contract)
        packet = deepcopy(certificate)
        verdict = checker.verify(self._contract, packet)
        root = str((1 << self._contract['n']) - 1)
        self._plan = deepcopy(packet['states'][root]['plans'][packet['selected']])
        self.regret = verdict['regret']
        self.plan_checks = 1
        self.membership_checks = 0
        self._last_window = -1
        self._active = False

    @property
    def plan(self):
        return deepcopy(self._plan)

    def open_window(self, window, contract, snapshot, mapping):
        # A failed refresh cannot leave the preceding window authorized.
        self._active = False
        if type(window) is not int or window <= self._last_window:
            raise ValueError('window must advance')
        self._last_window = window
        if contract != self._contract:
            raise ValueError('changed contract requires a new plan session')
        self.membership_checks += 1
        frozen, world = checked_window(self._contract, snapshot, mapping)
        self._active = True
        return frozen, world

    def require_active(self):
        if not self._active:
            raise ValueError('no accepted current window')


def known_world_plan(contract, profiles, world):
    """Ordinary scalar-cost connected-subset DP; no regret/support computation."""
    from .model import cuts, dot, key, subsets
    best = {}
    for state in subsets(contract['n'], contract['edges']):
        if state & (state - 1) == 0:
            best[state] = (0, state.bit_length() - 1)
            continue
        options = []
        for left, right in cuts(state, contract['edges']):
            lc, lp = best[left]
            rc, rp = best[right]
            plan = (lp, rp)
            options.append((lc + rc + dot(profiles[state], world), key(plan), plan))
        cost, _, plan = min(options)
        best[state] = (cost, plan)
    return best[(1 << contract['n']) - 1][1]

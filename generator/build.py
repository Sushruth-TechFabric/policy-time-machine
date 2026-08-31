"""The synthetic dataset builder.

Produces the seven source tables of spec 01 section 3, plus a scenario
assignment table so validation and the query contracts can find the planted
populations by name.

Two rules govern every line below (spec 01 sections 5 and 10, ADR-0006):

* **Identity comes from the seed alone.** Policy, customer, claim, vehicle,
  agent and endorsement identifiers, scenario membership and every categorical
  draw are functions of the seed. `P-18492` is the same policy with the same
  story at any anchor.
* **Time comes from the anchor plus an offset.** Everything internal is a day
  index on ``[0, HISTORY_DAYS]`` where ``HISTORY_DAYS`` is the anchor. Dates are
  materialised once, at emit. No absolute date literal appears in this package
  apart from the SCD2 open-ended attribute sentinel.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import calibration, constants as K, pools
from .ids import mint

DAY_ANCHOR = K.HISTORY_DAYS


def _stream_seed(name: str) -> int:
    return zlib.crc32(name.encode("utf-8"))


@dataclass
class Change:
    policy: int
    day: int
    category: str
    line: str | None = None
    forced_new: float | None = None
    direction: str | None = None


def _proportional_split(total: int, capacity: np.ndarray) -> np.ndarray:
    """Split ``total`` across buckets in proportion to capacity, exactly.

    Largest remainder, then a spill pass for any bucket asked for more than it
    holds. The total is always preserved: the caller relies on it, because the
    per-state totals are what the calibration solved for.
    """
    if capacity.sum() <= 0:
        raise RuntimeError("no eligible policy-days in a state that was allocated claims")
    share = total * capacity / capacity.sum()
    take = calibration.largest_remainder(share)
    take = np.minimum(take, capacity)
    shortfall = total - int(take.sum())
    while shortfall > 0:
        room = capacity - take
        if room.sum() <= 0:
            raise RuntimeError("more background claims allocated than eligible policy-days")
        order = np.argsort(-room, kind="stable")
        for index in order:
            if shortfall == 0:
                break
            if room[index] > 0:
                take[index] += 1
                shortfall -= 1
    return take


def _assert_direction(change: "Change", old: float, new: float, policy_id: str) -> None:
    """A planted change must move the way the scenario says it moved.

    A scenario that declares an increase and emits a decrease would still look
    like a plausible policy history, and the cohort it was planted for would
    quietly come back one short.
    """
    if change.direction == "increase" and new <= old:
        raise AssertionError(f"{policy_id}: planted increase on {change.line} did not increase")
    if change.direction == "decrease" and new >= old:
        raise AssertionError(f"{policy_id}: planted decrease on {change.line} did not decrease")


@dataclass
class PlantedClaim:
    policy: int
    loss_day: int
    report_day: int
    line: str
    amount: float
    scenario: str


@dataclass
class Builder:
    seed: int
    anchor_date: object  # datetime.date

    changes: list[Change] = field(default_factory=list)
    planted_claims: list[PlantedClaim] = field(default_factory=list)

    # ------------------------------------------------------------------ setup
    def rng(self, name: str) -> np.random.Generator:
        return np.random.default_rng([self.seed, _stream_seed(name)])

    @property
    def anchor_epoch_day(self) -> int:
        return int(np.datetime64(self.anchor_date).astype("datetime64[D]").astype(np.int64))

    def to_dates(self, day_index) -> np.ndarray:
        """Turn internal day indices into dates. The only place time is absolute."""
        epoch0 = self.anchor_epoch_day - DAY_ANCHOR
        values = np.asarray(day_index, dtype=np.float64)
        out = np.full(values.shape, np.datetime64("NaT", "s"), dtype="datetime64[s]")
        known = ~np.isnan(values)
        days = (epoch0 + values[known]).astype(np.int64).astype("datetime64[D]")
        out[known] = days.astype("datetime64[s]")
        return out

    # ------------------------------------------------------------------- run
    def run(self) -> dict[str, pd.DataFrame]:
        self._build_entities()
        self._assign_scenarios()
        self._constructed_status_population()
        self._plant_scenarios()
        self._layout_policy_days()
        self._background_endorsements()
        self._agent_reassignments()
        self._finalise_changes()
        # Policy state is evolved before claims are placed, because the
        # direction a coverage or deductible change actually took is only known
        # once it has been applied, and exposure is tracked per direction.
        self._evolve_policies()
        self._allocate_background_claims()
        self._build_claims()
        return self._frames()

    # -------------------------------------------------------------- entities
    def _build_entities(self) -> None:
        rng = self.rng("agents")
        self.agent_ids = mint("agent", K.N_AGENTS, rng)
        self.agent_regions = rng.choice(pools.AGENT_REGIONS, size=K.N_AGENTS)
        first = rng.choice(pools.FIRST_NAMES, size=K.N_AGENTS)
        last = rng.choice(pools.LAST_NAMES, size=K.N_AGENTS)
        self.agent_names = np.array([f"{f} {l}" for f, l in zip(first, last)], dtype=object)

        rng = self.rng("customers")
        self.customer_ids = mint("customer", K.N_CUSTOMERS, rng)
        self.customer_first = rng.choice(pools.FIRST_NAMES, size=K.N_CUSTOMERS)
        self.customer_last = rng.choice(pools.LAST_NAMES, size=K.N_CUSTOMERS)
        self.customer_location = rng.integers(0, len(pools.LOCATIONS), size=K.N_CUSTOMERS)
        self.customer_birth_year = self.anchor_date.year - rng.integers(19, 79, size=K.N_CUSTOMERS)

        rng = self.rng("policies")
        n = K.N_POLICIES
        self.policy_ids = mint("policy", n, rng)
        owners = np.arange(n) % K.N_CUSTOMERS
        extra = n - K.N_CUSTOMERS
        if extra > 0:
            owners[K.N_CUSTOMERS:] = rng.choice(K.N_CUSTOMERS, size=extra, replace=False)
        self.policy_customer = owners
        self.policy_agent = rng.integers(0, K.N_AGENTS, size=n)
        self.policy_location = self.customer_location[owners].copy()

        full_window = rng.random(n) < K.FULL_WINDOW_SHARE
        start_offset = rng.integers(K.MIN_START_OFFSET_DAYS, K.HISTORY_DAYS, size=n)
        start_offset[full_window] = K.HISTORY_DAYS
        self.start_day = (DAY_ANCHOR - start_offset).astype(np.int64)
        self.end_day = np.full(n, DAY_ANCHOR, dtype=np.int64)

        # Customer tenure predates the policy; an attribute, not an event.
        earliest = pd.Series(self.start_day).groupby(owners).min()
        since = np.full(K.N_CUSTOMERS, DAY_ANCHOR, dtype=np.int64)
        since[earliest.index.to_numpy()] = earliest.to_numpy()
        self.customer_since_day = since - rng.integers(0, 900, size=K.N_CUSTOMERS)

        # Coverage, deductibles, premium and the first vehicle.
        rng = self.rng("coverage-initial")
        self.limits = {
            "BI": rng.choice(K.BI_LIMITS, size=n),
            "PD": rng.choice(K.PD_LIMITS, size=n),
            "COLL": rng.choice(K.PHYSICAL_DAMAGE_LIMITS, size=n),
            "COMP": rng.choice(K.PHYSICAL_DAMAGE_LIMITS, size=n),
            "UMUIM": rng.choice(K.UMUIM_LIMITS, size=n),
        }
        self.deductibles = {
            "COLL": rng.choice(K.DEDUCTIBLES, size=n),
            "COMP": rng.choice(K.DEDUCTIBLES, size=n),
        }
        lo, hi = K.PREMIUM_BASE_RANGE
        self.base_premium = np.round(rng.uniform(lo, hi, size=n), 2)
        self.policy_status0 = np.full(n, "active", dtype=object)

        rng = self.rng("propensity")
        shape = K.ENDORSEMENT_PROPENSITY_SHAPE
        self.propensity = rng.gamma(shape, 1.0 / shape, size=n)

        # Per-policy blocking windows, filled in as scenarios are planted.
        self.blocked_change_windows: list[list[tuple[int, int]]] = [[] for _ in range(n)]
        self.blocked_claim_windows: list[list[tuple[int, int]]] = [[] for _ in range(n)]
        self.no_claims_at_all = np.zeros(n, dtype=bool)
        self.endorsement_boost = np.ones(n, dtype=float)

    # ------------------------------------------------------------- scenarios
    def _assign_scenarios(self) -> None:
        rng = self.rng("scenario-assignment")
        eligible = np.flatnonzero(self.start_day <= DAY_ANCHOR - 400)
        order = rng.permutation(eligible)
        needed = sum(K.SCENARIO_SIZES.values())
        if len(order) < needed + K.N_LAPSE_REINSTATE_POLICIES + K.N_TERMINATING_POLICIES:
            raise RuntimeError("not enough long-history policies for the constructed populations")

        self.scenario_members: dict[str, np.ndarray] = {}
        cursor = 0
        for scenario in K.SCENARIO_ORDER:
            size = K.SCENARIO_SIZES[scenario]
            members = np.sort(order[cursor : cursor + size])
            cursor += size
            self.scenario_members[scenario] = members
        self._spare_pool = order[cursor:]

        scenario_policies = np.concatenate(list(self.scenario_members.values()))
        self.is_scenario = np.zeros(K.N_POLICIES, dtype=bool)
        self.is_scenario[scenario_policies] = True

        # The demo anchor policy is the S1 exemplar (spec 01 section 9). Picking
        # the lexically smallest identifier makes it stable and quotable.
        s1 = self.scenario_members["S1"]
        self.demo_policy = int(s1[np.argmin(self.policy_ids[s1])])

    def _constructed_status_population(self) -> None:
        """Lapse/reinstate and termination sequences.

        Spec 01 section 6 rule 3: status sequences are deliberate constructions,
        never random noise. They are placed here as named populations rather
        than emitted from the ordinary endorsement process, and they land in
        both the noteworthy and the control halves of the dataset because the
        pool they are drawn from is disjoint from the scenario catalogue.
        """
        rng = self.rng("status-population")
        pool = rng.permutation(self._spare_pool)
        n_lapse = K.N_LAPSE_REINSTATE_POLICIES
        n_term = K.N_TERMINATING_POLICIES
        self.lapse_policies = np.sort(pool[:n_lapse])
        self.terminating_policies = np.sort(pool[n_lapse : n_lapse + n_term])
        self._spare_pool = pool[n_lapse + n_term :]

        for policy in self.lapse_policies:
            start, end = int(self.start_day[policy]), int(self.end_day[policy])
            cursor = start + 90
            for _ in range(int(rng.integers(1, K.LAPSE_CYCLES_MAX + 1))):
                latest = min(cursor + 200, end - 210)
                if latest <= cursor:
                    break
                lapse_day = int(rng.integers(cursor, latest))
                reinstate_day = lapse_day + int(rng.integers(*K.LAPSE_REINSTATE_GAP_RANGE))
                self.changes.append(Change(int(policy), lapse_day, "status", direction="switch"))
                self.changes.append(Change(int(policy), reinstate_day, "status", direction="switch"))
                cursor = reinstate_day + 100

        terminal_kind = rng.choice(("cancelled", "non_renewed"), size=n_term)
        self.terminal_status = {}
        for policy, kind in zip(self.terminating_policies, terminal_kind):
            start, end = int(self.start_day[policy]), int(self.end_day[policy])
            earliest = start + 200
            latest = end - 30
            if latest <= earliest:
                continue
            day = int(rng.integers(earliest, latest))
            self.changes.append(Change(int(policy), day, "status", direction="switch"))
            self.terminal_status[int(policy)] = (day, str(kind))
            # Exposure ends when the policy leaves the books.
            self.end_day[policy] = day

    def _plant_scenarios(self) -> None:
        rng = self.rng("scenario-construction")
        block_change = self._block_change
        block_claim = self._block_claim

        # --- S1: coverage raised, same line claimed -------------------------
        for policy in self.scenario_members["S1"]:
            policy = int(policy)
            raise_day = DAY_ANCHOR - K.S1_COVERAGE_RAISE_OFFSET
            loss_day = DAY_ANCHOR - K.S1_LOSS_OFFSET
            if policy == self.demo_policy:
                new_limit = K.DEMO_COLL_LIMIT_AFTER
                self.limits["COLL"][policy] = K.DEMO_COLL_LIMIT_BEFORE
                # The demo's legible spine: address, then coverage, then
                # vehicle, then the collision claim - all inside the 60 days
                # before the loss (spec 01 section 9).
                self.changes.append(
                    Change(policy, DAY_ANCHOR - K.S1_EXEMPLAR_ADDRESS_OFFSET, "address")
                )
                self.changes.append(
                    Change(policy, DAY_ANCHOR - K.S1_EXEMPLAR_VEHICLE_OFFSET, "vehicle")
                )
            else:
                new_limit = float(rng.choice((15_000.0, 20_000.0, 25_000.0, 35_000.0, 50_000.0)))
                self.limits["COLL"][policy] = float(
                    rng.choice([v for v in K.PHYSICAL_DAMAGE_LIMITS if v < new_limit])
                )
            self.changes.append(
                Change(policy, raise_day, "coverage", line="COLL", forced_new=new_limit, direction="increase")
            )
            amount = round(new_limit * K.DEMO_LIMIT_UTILISATION, 2)
            report_day = loss_day + self._lag(rng, K.S1_LOSS_OFFSET)
            self.planted_claims.append(
                PlantedClaim(policy, loss_day, report_day, "COLL", amount, "S1")
            )
            # The planted limit increase has to be the only thing that moved
            # this line, or an ordinary endorsement could raise the limit past
            # the planted value first and turn the story into a decrease.
            block_change(policy, 0, DAY_ANCHOR)
            block_claim(policy, 0, DAY_ANCHOR)

        # --- S2: deductible lowered before claim ----------------------------
        for policy in self.scenario_members["S2"]:
            policy = int(policy)
            cut_day = DAY_ANCHOR - K.S2_DEDUCTIBLE_CUT_OFFSET
            loss_day = DAY_ANCHOR - K.S2_LOSS_OFFSET
            self.deductibles["COMP"][policy] = 1_000.0
            self.limits["COMP"][policy] = float(rng.choice((10_000.0, 15_000.0, 20_000.0, 25_000.0)))
            self.changes.append(
                Change(policy, cut_day, "deductible", line="COMP", forced_new=250.0, direction="decrease")
            )
            amount = round(float(rng.uniform(2_800.0, 9_400.0)), 2)
            report_day = loss_day + self._lag(rng, K.S2_LOSS_OFFSET)
            self.planted_claims.append(
                PlantedClaim(policy, loss_day, report_day, "COMP", amount, "S2")
            )
            block_change(policy, 0, DAY_ANCHOR)
            block_claim(policy, 0, DAY_ANCHOR)

        # --- S3: change inside the loss-to-report gap -----------------------
        for policy in self.scenario_members["S3"]:
            policy = int(policy)
            loss_day = DAY_ANCHOR - K.S3_LOSS_OFFSET
            report_day = DAY_ANCHOR - K.S3_REPORT_OFFSET
            change_day = DAY_ANCHOR - K.S3_ADDRESS_CHANGE_OFFSET
            self.changes.append(Change(policy, change_day, "address"))
            line = str(rng.choice(("COLL", "COMP", "PD")))
            amount = round(float(rng.uniform(3_200.0, 24_000.0)), 2)
            self.planted_claims.append(
                PlantedClaim(policy, loss_day, report_day, line, amount, "S3")
            )
            # The gap itself is kept clear too: an ordinary endorsement landing
            # inside it would make the planted change one of several, and the
            # scenario is about a single change in a single gap.
            block_change(policy, loss_day - 130, DAY_ANCHOR)
            block_claim(policy, loss_day - 130, DAY_ANCHOR)

        # --- S4: rapid change cluster before a high-severity claim ----------
        for policy in self.scenario_members["S4"]:
            policy = int(policy)
            loss_day = DAY_ANCHOR - K.S4_LOSS_OFFSET
            # Room to move in the declared direction, whatever the draw gave.
            for line in K.DEDUCTIBLE_LINES:
                self.limits[line][policy] = K.S4_INITIAL_LIMIT
                self.deductibles[line][policy] = K.S4_INITIAL_DEDUCTIBLE
            for offset, (category, line, direction) in zip(
                K.S4_CLUSTER_OFFSETS, K.S4_CLUSTER_CHANGES
            ):
                self.changes.append(
                    Change(policy, DAY_ANCHOR - offset, category, line=line, direction=direction)
                )
            amount = round(float(rng.uniform(11_000.0, 46_000.0)), 2)
            line = str(rng.choice(("COLL", "PD", "BI")))
            report_day = loss_day + self._lag(rng, K.S4_LOSS_OFFSET)
            self.planted_claims.append(
                PlantedClaim(policy, loss_day, report_day, line, amount, "S4")
            )
            # The cluster is the whole story, and its directions are declared,
            # so no ordinary endorsement may move these lines first.
            block_change(policy, 0, DAY_ANCHOR)
            block_claim(policy, 0, DAY_ANCHOR)

        # --- S5: vehicle and address together, no planted claim -------------
        for policy in self.scenario_members["S5"]:
            policy = int(policy)
            self.changes.append(Change(policy, DAY_ANCHOR - K.S5_VEHICLE_OFFSET, "vehicle"))
            self.changes.append(Change(policy, DAY_ANCHOR - K.S5_ADDRESS_OFFSET, "address"))
            block_change(policy, DAY_ANCHOR - 140, DAY_ANCHOR)

        # --- S6: claim near a newly raised limit ----------------------------
        for policy in self.scenario_members["S6"]:
            policy = int(policy)
            raise_day = DAY_ANCHOR - K.S6_COVERAGE_RAISE_OFFSET
            loss_day = DAY_ANCHOR - K.S6_LOSS_OFFSET
            new_limit = float(rng.choice((8_000.0, 10_000.0)))
            self.limits["COLL"][policy] = 5_000.0
            self.changes.append(
                Change(policy, raise_day, "coverage", line="COLL", forced_new=new_limit, direction="increase")
            )
            amount = round(new_limit * K.S6_LIMIT_UTILISATION, 2)
            report_day = loss_day + self._lag(rng, K.S6_LOSS_OFFSET)
            self.planted_claims.append(
                PlantedClaim(policy, loss_day, report_day, "COLL", amount, "S6")
            )
            block_change(policy, 0, DAY_ANCHOR)
            block_claim(policy, 0, DAY_ANCHOR)

        # --- C1: high-value claim, nothing before it ------------------------
        lo, hi = K.C1_LOSS_OFFSET_RANGE
        for policy in self.scenario_members["C1"]:
            policy = int(policy)
            loss_day = DAY_ANCHOR - int(rng.integers(lo, hi))
            band = "severe" if rng.random() < 0.72 else "catastrophic"
            amount = self._amount_in_band(rng, band)
            line = self._line_for_band(rng, band)
            report_day = loss_day + self._lag(rng, DAY_ANCHOR - loss_day)
            self.planted_claims.append(
                PlantedClaim(policy, loss_day, report_day, line, amount, "C1")
            )
            block_change(policy, loss_day - K.C1_QUIET_WINDOW_DAYS, loss_day)
            self.no_claims_at_all[policy] = True

        # --- C2: frequently changed, never claimed --------------------------
        for policy in self.scenario_members["C2"]:
            policy = int(policy)
            self.endorsement_boost[policy] = 4.0
            self.no_claims_at_all[policy] = True

        # --- C3: benign address change during the gap on a small claim ------
        lo, hi = K.C3_LOSS_OFFSET_RANGE
        for policy in self.scenario_members["C3"]:
            policy = int(policy)
            loss_day = DAY_ANCHOR - int(rng.integers(lo, hi))
            lag = int(rng.integers(*K.C3_REPORT_LAG_RANGE))
            report_day = min(loss_day + lag, DAY_ANCHOR)
            change_day = loss_day + max(1, (report_day - loss_day) // 2)
            self.changes.append(Change(policy, change_day, "address"))
            amount = self._amount_in_band(rng, "minor")
            self.planted_claims.append(
                PlantedClaim(policy, loss_day, report_day, "COMP", amount, "C3")
            )
            block_change(policy, loss_day - 130, loss_day)
            self.no_claims_at_all[policy] = True

        # --- C4: near-limit claim, nothing before it ------------------------
        lo, hi = K.C4_LOSS_OFFSET_RANGE
        self._c4_plan = {}
        for policy in self.scenario_members["C4"]:
            policy = int(policy)
            loss_day = DAY_ANCHOR - int(rng.integers(lo, hi))
            line = str(rng.choice(("COLL", "COMP")))
            utilisation = float(rng.uniform(0.90, 1.25))
            report_day = loss_day + self._lag(rng, DAY_ANCHOR - loss_day)
            self._c4_plan[policy] = (loss_day, report_day, line, utilisation)
            block_change(policy, loss_day - K.C1_QUIET_WINDOW_DAYS, loss_day)
            self.no_claims_at_all[policy] = True

        # --- C5: benign pattern match, no claim near the cluster ------------
        lo, hi = K.C5_CLUSTER_END_OFFSET_RANGE
        for policy in self.scenario_members["C5"]:
            policy = int(policy)
            end_offset = int(rng.integers(lo, hi))
            end_day = DAY_ANCHOR - end_offset
            span = K.C5_CLUSTER_SPAN_DAYS
            days = sorted({end_day - span, end_day - (2 * span) // 3, end_day - span // 3, end_day})
            # A mundane explanation: moved house, changed car, adjusted cover.
            # No claim follows, which is the whole point of the control.
            for day, category in zip(days, ("address", "vehicle", "coverage", "deductible")):
                line = "COMP" if category in ("coverage", "deductible") else None
                self.changes.append(Change(policy, day, category, line=line))
            block_change(policy, days[0] - 120, end_day + 120)
            block_claim(policy, days[0] - 30, end_day + 120)

    def _block_change(self, policy: int, lo: int, hi: int) -> None:
        self.blocked_change_windows[policy].append((lo, hi))

    def _block_claim(self, policy: int, lo: int, hi: int) -> None:
        self.blocked_claim_windows[policy].append((lo, hi))

    # ------------------------------------------------------------- day layout
    def _layout_policy_days(self) -> None:
        lengths = (self.end_day - self.start_day + 1).astype(np.int64)
        self.day_offset = np.concatenate(([0], np.cumsum(lengths)[:-1]))
        self.total_days = int(lengths.sum())
        self.policy_lengths = lengths

        # Flat index of the first day of each policy, used to translate a
        # (policy, day) pair to a position in the exposure arrays.
        self.change_blocked = np.zeros(self.total_days, dtype=bool)
        self.claim_blocked = np.zeros(self.total_days, dtype=bool)
        for policy in range(K.N_POLICIES):
            for lo, hi in self.blocked_change_windows[policy]:
                a, b = self._flat_span(policy, lo, hi)
                if b > a:
                    self.change_blocked[a:b] = True
            for lo, hi in self.blocked_claim_windows[policy]:
                a, b = self._flat_span(policy, lo, hi)
                if b > a:
                    self.claim_blocked[a:b] = True
        blocked_policies = np.flatnonzero(self.no_claims_at_all)
        for policy in blocked_policies:
            a, b = self._flat_span(int(policy), int(self.start_day[policy]), int(self.end_day[policy]))
            self.claim_blocked[a:b] = True

    def _flat_span(self, policy: int, lo: int, hi: int) -> tuple[int, int]:
        start = int(self.start_day[policy])
        end = int(self.end_day[policy])
        lo = max(lo, start)
        hi = min(hi, end)
        base = int(self.day_offset[policy])
        return base + (lo - start), base + (hi - start) + 1

    def _flat_index(self, policy, day):
        return self.day_offset[policy] + (np.asarray(day) - self.start_day[policy])

    # ------------------------------------------------- background endorsements
    def _background_endorsements(self) -> None:
        rng = self.rng("background-endorsements")
        categories = list(K.ENDORSEMENT_CATEGORY_WEIGHTS)
        weights = np.array([K.ENDORSEMENT_CATEGORY_WEIGHTS[c] for c in categories])
        weights = weights / weights.sum()

        years = self.policy_lengths / calibration.DAYS_PER_YEAR
        expected = K.ENDORSEMENT_RATE_PER_YEAR * self.propensity * self.endorsement_boost * years
        counts = rng.poisson(expected)

        for policy in range(K.N_POLICIES):
            n = int(counts[policy])
            if n == 0:
                continue
            start = int(self.start_day[policy])
            end = int(self.end_day[policy])
            if end - start < 40:
                continue
            days = rng.integers(start + 20, end + 1, size=n)
            base = int(self.day_offset[policy])
            keep = ~self.change_blocked[base + (days - start)]
            days = np.unique(days[keep])
            if days.size == 0:
                continue
            picked = rng.choice(len(categories), size=days.size, p=weights)
            second = rng.random(days.size) < K.MULTI_CHANGE_ENDORSEMENT_SHARE
            for day, cat_idx, add_second in zip(days, picked, second):
                self._append_background_change(rng, policy, int(day), categories[cat_idx])
                if add_second:
                    other = categories[int(rng.choice(len(categories), p=weights))]
                    if other != categories[cat_idx]:
                        self._append_background_change(rng, policy, int(day), other)

    def _append_background_change(self, rng, policy: int, day: int, category: str) -> None:
        if category == "coverage":
            line = str(rng.choice(K.COVERAGE_LINES))
            self.changes.append(Change(policy, day, "coverage", line=line))
        elif category == "deductible":
            line = str(rng.choice(K.DEDUCTIBLE_LINES))
            self.changes.append(Change(policy, day, "deductible", line=line))
        else:
            self.changes.append(Change(policy, day, category))

    def _agent_reassignments(self) -> None:
        rng = self.rng("agent-changes")
        pool = self._spare_pool
        chosen = rng.choice(pool, size=min(K.N_AGENT_CHANGE_POLICIES, len(pool)), replace=False)
        for policy in chosen:
            policy = int(policy)
            start, end = int(self.start_day[policy]), int(self.end_day[policy])
            if end - start < 120:
                continue
            day = int(rng.integers(start + 60, end - 30))
            self.changes.append(Change(policy, day, "agent"))

    def _finalise_changes(self) -> None:
        # Deduplicate: one change per (policy, day, category, line).
        seen = set()
        unique: list[Change] = []
        for change in self.changes:
            key = (change.policy, change.day, change.category, change.line)
            if key in seen:
                continue
            seen.add(key)
            unique.append(change)
        unique.sort(key=lambda c: (c.policy, c.day, c.category, c.line or ""))
        self.changes = unique

        self.material_changes = [c for c in unique if c.category in K.MATERIAL_CATEGORIES]
        self.material_policy = np.array([c.policy for c in self.material_changes], dtype=np.int64)
        self.material_day = np.array([c.day for c in self.material_changes], dtype=np.int64)

    # ----------------------------------------------------- exposure and claims
    def _window_flags(self, mask: np.ndarray, window: int) -> np.ndarray:
        diff = np.zeros(self.total_days + 1, dtype=np.int32)
        policy = self.material_policy[mask]
        day = self.material_day[mask]
        if policy.size == 0:
            return np.zeros(self.total_days, dtype=bool)
        start = self.start_day[policy]
        end = self.end_day[policy]
        base = self.day_offset[policy]
        a = base + (day - start)
        b = base + (np.minimum(day + window - 1, end) - start) + 1
        np.add.at(diff, a, 1)
        np.add.at(diff, b, -1)
        return np.cumsum(diff[:-1]) > 0

    def _allocate_background_claims(self) -> None:
        material_key = np.array(
            [K.exposure_key(c.category, c.direction) for c in self.material_changes], dtype=object
        )
        recent90 = self._window_flags(np.ones(len(self.material_changes), dtype=bool), K.HEADLINE_WINDOW_DAYS)
        within60 = {
            key: self._window_flags(material_key == key, K.CATEGORY_WINDOW_DAYS)
            for key in K.EXPOSURE_KEYS
        }
        self.exposure_state = calibration.state_code(recent90, within60)

        planted_flat = np.array(
            [self._flat_index(c.policy, c.loss_day) for c in self.planted_claims]
            + [self._flat_index(p, plan[0]) for p, plan in self._c4_plan.items()],
            dtype=np.int64,
        )

        # The final day cannot carry a loss: the report would have to fall on or
        # after the anchor, and a zero-day report lag is not permitted.
        eligible = ~self.claim_blocked
        last_days = self.day_offset + self.policy_lengths - 1
        eligible[last_days] = False

        exposure_by_state = np.bincount(self.exposure_state, minlength=calibration.N_STATES)
        eligible_by_state = np.bincount(
            self.exposure_state[eligible], minlength=calibration.N_STATES
        )
        planted_by_state = np.bincount(
            self.exposure_state[planted_flat], minlength=calibration.N_STATES
        )
        self.hazard = calibration.solve(
            exposure_by_state.astype(float),
            eligible_by_state.astype(float),
            planted_by_state.astype(float),
        )

        # The calibration fixes how many claims each sixty-day state carries, but
        # not where inside that state they land - and the portfolio chart is also
        # read at thirty days. Splitting each state's allocation across its
        # thirty-day sub-states in proportion to their eligible days leaves every
        # state total untouched, so nothing the calibration solved for moves,
        # while the thirty-day counts stop being a binomial draw.
        category = np.array([c.category for c in self.material_changes], dtype=object)
        substate = np.zeros(self.total_days, dtype=np.int64)
        for index, name in enumerate(K.MATERIAL_CATEGORIES):
            substate += self._window_flags(category == name, K.SHORT_WINDOW_DAYS) << index
        n_sub = 1 << len(K.MATERIAL_CATEGORIES)

        rng = self.rng("background-claim-placement")
        chosen: list[np.ndarray] = []
        eligible_index = np.flatnonzero(eligible)
        key = self.exposure_state[eligible_index].astype(np.int64) * n_sub + substate[eligible_index]
        order = np.argsort(key, kind="stable")
        eligible_index = eligible_index[order]
        key = key[order]
        groups, starts = np.unique(key, return_index=True)
        ends = np.append(starts[1:], key.size)
        parents = groups // n_sub
        for state, count in enumerate(self.hazard.counts_by_state):
            count = int(count)
            if count <= 0:
                continue
            lo, hi = np.searchsorted(parents, (state, state + 1))
            capacity = (ends[lo:hi] - starts[lo:hi]).astype(np.int64)
            take = _proportional_split(count, capacity)
            for offset, amount in enumerate(take):
                if amount <= 0:
                    continue
                slot = lo + offset
                candidates = eligible_index[starts[slot] : ends[slot]]
                chosen.append(rng.choice(candidates, size=int(amount), replace=False))
        flat = np.sort(np.concatenate(chosen)) if chosen else np.empty(0, dtype=np.int64)

        policy = np.searchsorted(self.day_offset, flat, side="right") - 1
        day = flat - self.day_offset[policy] + self.start_day[policy]
        self.background_claim_policy = policy
        self.background_claim_day = day
        self.background_claim_state = self.exposure_state[flat]
        self.background_claim_stratum = self._severity_strata()[flat]

    def _severity_strata(self) -> np.ndarray:
        """Per policy-day, how close it sits to the chart's fragile categories.

        For each of vehicle, status and address a day is at level 0 (no such
        change in the prior ninety days), 1, 2 or 3 (within ninety, sixty or
        thirty). Those levels are exactly the memberships the portfolio chart
        counts at its three windows, so holding the severity mix constant within
        a level holds the chart's bottom three bars steady.
        """
        category = np.array([c.category for c in self.material_changes], dtype=object)
        stratum = np.zeros(self.total_days, dtype=np.int32)
        for index, name in enumerate(K.SEVERITY_STRATA_CATEGORIES):
            mask = category == name
            level = np.zeros(self.total_days, dtype=np.int32)
            for window in (90, K.CATEGORY_WINDOW_DAYS, 30):
                level += self._window_flags(mask, window)
            stratum += level * (4**index)
        return stratum

    # -------------------------------------------------- policy state evolution
    def _evolve_policies(self) -> None:
        rng = self.rng("state-evolution")
        by_policy: dict[int, list[Change]] = {}
        for change in self.changes:
            by_policy.setdefault(change.policy, []).append(change)

        endorsement_keys = sorted({(c.policy, c.day) for c in self.changes})
        endorsement_ids = mint("endorsement", len(endorsement_keys), self.rng("endorsement-ids"))
        endorsement_lookup = dict(zip(endorsement_keys, endorsement_ids))
        self.endorsement_lookup = endorsement_lookup

        vehicle_slots = K.N_POLICIES + sum(1 for c in self.changes if c.category == "vehicle")
        vehicle_ids = mint("vehicle", vehicle_slots, self.rng("vehicle-ids"))
        vehicle_cursor = 0

        makes = list(pools.VEHICLES)
        history_rows: list[tuple] = []
        coverage_rows: list[tuple] = []
        vehicle_rows: list[tuple] = []
        coverage_track: dict[tuple[int, str], list[tuple[int, float, float | None]]] = {}

        for policy in range(K.N_POLICIES):
            start = int(self.start_day[policy])
            end = int(self.end_day[policy])
            changes = by_policy.get(policy, [])
            renewals = [d for d in range(start + K.TERM_LENGTH_DAYS, end + 1, K.TERM_LENGTH_DAYS)]
            change_days = sorted({c.day for c in changes})
            boundaries = sorted(set([start] + change_days + renewals))

            state = {
                "status": "active",
                "agent": int(self.policy_agent[policy]),
                "location": int(self.policy_location[policy]),
                "premium": float(self.base_premium[policy]),
                "term_start": start,
            }
            limits = {line: float(self.limits[line][policy]) for line in K.COVERAGE_LINES}
            deductibles = {
                line: float(self.deductibles[line][policy]) for line in K.DEDUCTIBLE_LINES
            }

            make = makes[int(rng.integers(0, len(makes)))]
            model = pools.VEHICLES[make][int(rng.integers(0, 3))]
            current_vehicle = vehicle_ids[vehicle_cursor]
            vehicle_cursor += 1
            vehicle_rows.append(
                (
                    current_vehicle,
                    self.policy_ids[policy],
                    make,
                    model,
                    self.anchor_date.year - int(rng.integers(0, 15)),
                    str(rng.choice(pools.BODY_STYLES)),
                    start,
                    None,
                )
            )
            state["vehicle"] = current_vehicle
            current_vehicle_row = len(vehicle_rows) - 1

            for line in K.COVERAGE_LINES:
                coverage_track.setdefault((policy, line), []).append(
                    (start, limits[line], deductibles.get(line))
                )

            def record_coverage(line: str, day: int, policy: int = policy) -> None:
                """One coverage version per line per day, even if a limit and a
                deductible moved together in the same endorsement."""
                entries = coverage_track[(policy, line)]
                row = (day, limits[line], deductibles.get(line))
                if entries and entries[-1][0] == day:
                    entries[-1] = row
                else:
                    entries.append(row)

            changes_by_day: dict[int, list[Change]] = {}
            for change in changes:
                changes_by_day.setdefault(change.day, []).append(change)

            reinstate_pending = False
            for version_no, day in enumerate(boundaries, start=1):
                if day in renewals:
                    state["term_start"] = day
                    # A renewal is a Timeline Event, never a Policy Change
                    # (ADR-0003). It may move the premium; it never moves the
                    # status, which is the premium-echo problem in disguise.
                    state["premium"] = round(state["premium"] * float(rng.uniform(1.0, 1.07)), 2)

                today = changes_by_day.get(day, [])
                premium_factor = 1.0
                for change in today:
                    category = change.category
                    if category == "address":
                        options = [i for i in range(len(pools.LOCATIONS)) if i != state["location"]]
                        state["location"] = int(rng.choice(options))
                        premium_factor *= float(rng.uniform(0.93, 1.10))
                    elif category == "vehicle":
                        row = list(vehicle_rows[current_vehicle_row])
                        row[7] = day
                        vehicle_rows[current_vehicle_row] = tuple(row)
                        make = makes[int(rng.integers(0, len(makes)))]
                        model = pools.VEHICLES[make][int(rng.integers(0, 3))]
                        new_vehicle = vehicle_ids[vehicle_cursor]
                        vehicle_cursor += 1
                        vehicle_rows.append(
                            (
                                new_vehicle,
                                self.policy_ids[policy],
                                make,
                                model,
                                self.anchor_date.year - int(rng.integers(0, 15)),
                                str(rng.choice(pools.BODY_STYLES)),
                                day,
                                None,
                            )
                        )
                        state["vehicle"] = new_vehicle
                        current_vehicle_row = len(vehicle_rows) - 1
                        premium_factor *= float(rng.uniform(0.90, 1.16))
                    elif category == "status":
                        terminal = self.terminal_status.get(policy)
                        if terminal is not None and terminal[0] == day:
                            state["status"] = terminal[1]
                        elif reinstate_pending:
                            state["status"] = "reinstated"
                            reinstate_pending = False
                        else:
                            state["status"] = "lapsed"
                            reinstate_pending = True
                    elif category == "agent":
                        options = [i for i in range(K.N_AGENTS) if i != state["agent"]]
                        state["agent"] = int(rng.choice(options))
                    elif category == "coverage":
                        line = change.line
                        old = limits[line]
                        new = change.forced_new
                        if new is None:
                            new = self._new_limit(rng, line, old, change.direction)
                        _assert_direction(change, old, float(new), self.policy_ids[policy])
                        change.direction = "increase" if new > old else "decrease"
                        limits[line] = float(new)
                        record_coverage(line, day)
                        premium_factor *= 1.0 + 0.09 * np.sign(limits[line] - old) * float(
                            rng.uniform(0.4, 1.6)
                        )
                    elif category == "deductible":
                        line = change.line
                        old = deductibles[line]
                        new = change.forced_new
                        if new is None:
                            new = self._new_deductible(rng, old, change.direction)
                        _assert_direction(change, old, float(new), self.policy_ids[policy])
                        change.direction = "increase" if new > old else "decrease"
                        deductibles[line] = float(new)
                        record_coverage(line, day)
                        premium_factor *= 1.0 - 0.07 * np.sign(deductibles[line] - old) * float(
                            rng.uniform(0.4, 1.6)
                        )

                if today:
                    state["premium"] = round(
                        min(max(state["premium"] * premium_factor, 320.0), 9_000.0), 2
                    )

                endorsement = endorsement_lookup.get((policy, day)) if today else None
                location = pools.LOCATIONS[state["location"]]
                history_rows.append(
                    (
                        self.policy_ids[policy],
                        version_no,
                        self.customer_ids[self.policy_customer[policy]],
                        day,
                        state["status"],
                        self.agent_ids[state["agent"]],
                        location[0],
                        location[1],
                        f"{location[2] + (policy % 90):05d}",
                        state["vehicle"],
                        state["term_start"],
                        state["term_start"] + K.TERM_LENGTH_DAYS,
                        state["premium"],
                        endorsement,
                    )
                )

        self._history_rows = history_rows
        self._vehicle_rows = vehicle_rows
        self.coverage_track = coverage_track
        for (policy, line), entries in coverage_track.items():
            for index, (day, limit, deductible) in enumerate(entries, start=1):
                coverage_rows.append(
                    (
                        self.policy_ids[policy],
                        line,
                        index,
                        day,
                        limit,
                        deductible,
                        self.endorsement_lookup.get((policy, day)) if index > 1 else None,
                    )
                )
        self._coverage_rows = coverage_rows

    def _new_limit(self, rng, line: str, old: float, direction: str | None) -> float:
        ladder = {
            "BI": K.BI_LIMITS,
            "PD": K.PD_LIMITS,
            "UMUIM": K.UMUIM_LIMITS,
            "COLL": K.PHYSICAL_DAMAGE_LIMITS,
            "COMP": K.PHYSICAL_DAMAGE_LIMITS,
        }[line]
        if direction is None:
            direction = "increase" if rng.random() < K.COVERAGE_INCREASE_SHARE else "decrease"
        options = [v for v in ladder if (v > old if direction == "increase" else v < old)]
        if not options:
            options = [v for v in ladder if v != old]
        return float(rng.choice(options))

    def _new_deductible(self, rng, old: float, direction: str | None) -> float:
        if direction is None:
            direction = "decrease" if rng.random() < K.DEDUCTIBLE_DECREASE_SHARE else "increase"
        options = [v for v in K.DEDUCTIBLES if (v < old if direction == "decrease" else v > old)]
        if not options:
            options = [v for v in K.DEDUCTIBLES if v != old]
        return float(rng.choice(options))

    def limit_at(self, policy: int, line: str, day: int) -> tuple[float, float | None]:
        entries = self.coverage_track[(policy, line)]
        limit, deductible = entries[0][1], entries[0][2]
        for entry_day, entry_limit, entry_deductible in entries:
            if entry_day <= day:
                limit, deductible = entry_limit, entry_deductible
            else:
                break
        return limit, deductible

    # ------------------------------------------------------------------ claims
    def _lag(self, rng, max_days: int) -> int:
        max_days = max(int(max_days), K.REPORT_LAG_MIN_DAYS)
        mu = np.log(K.REPORT_LAG_MEDIAN_DAYS)
        sigma = (np.log(K.REPORT_LAG_P90_DAYS) - mu) / 1.2815515655446004
        for _ in range(12):
            value = int(round(float(rng.lognormal(mu, sigma))))
            value = min(max(value, K.REPORT_LAG_MIN_DAYS), K.REPORT_LAG_CAP_DAYS)
            if value <= max_days:
                return value
        return int(rng.integers(K.REPORT_LAG_MIN_DAYS, max_days + 1))

    def _lags(self, rng, max_days: np.ndarray) -> np.ndarray:
        mu = np.log(K.REPORT_LAG_MEDIAN_DAYS)
        sigma = (np.log(K.REPORT_LAG_P90_DAYS) - mu) / 1.2815515655446004
        n = max_days.size
        value = np.rint(rng.lognormal(mu, sigma, size=n)).astype(np.int64)
        value = np.clip(value, K.REPORT_LAG_MIN_DAYS, K.REPORT_LAG_CAP_DAYS)
        for _ in range(12):
            bad = value > max_days
            if not bad.any():
                break
            redraw = np.rint(rng.lognormal(mu, sigma, size=int(bad.sum()))).astype(np.int64)
            value[bad] = np.clip(redraw, K.REPORT_LAG_MIN_DAYS, K.REPORT_LAG_CAP_DAYS)
        bad = value > max_days
        if bad.any():
            value[bad] = rng.integers(K.REPORT_LAG_MIN_DAYS, np.maximum(max_days[bad], 1) + 1)
        return value

    @staticmethod
    def _stratified_bands(strata: np.ndarray) -> np.ndarray:
        """Assign severity bands so every stratum gets the declared mix.

        Drawing bands independently leaves each category's high-severity count
        binomially noisy, and the bottom of the portfolio chart carries only a
        few dozen claims - enough noise to reorder vehicle, status and address
        from one regeneration to the next, which is what a count-ranking
        contract would fail on. Sorting the claims by stratum and walking a
        low-discrepancy sequence gives every contiguous run the declared mix to
        within a fraction of a claim, while the global mix stays exact.
        """
        bands = list(K.SEVERITY_MIX)
        weights = np.array([K.SEVERITY_MIX[band] for band in bands], dtype=float)
        cuts = np.cumsum(weights / weights.sum())
        order = np.argsort(strata, kind="stable")
        golden = 0.6180339887498949
        positions = (np.arange(strata.size) * golden + 0.5 * golden) % 1.0
        assigned = np.searchsorted(cuts, positions, side="right").clip(0, len(bands) - 1)
        out = np.empty(strata.size, dtype=object)
        out[order] = np.array(bands, dtype=object)[assigned]
        return out

    def _amount_in_band(self, rng, band: str) -> float:
        if band == "catastrophic":
            value = 50_000.0 * float(np.exp(rng.exponential(0.62)))
            return round(min(value, 780_000.0), 2)
        lo, hi = {b: (l, h) for b, l, h in K.SEVERITY_BANDS}[band]
        lo = max(lo, 140.0)
        value = float(np.exp(rng.uniform(np.log(lo), np.log(hi - 1.0))))
        return round(value, 2)

    def _line_for_band(self, rng, band: str) -> str:
        weights = K.CLAIM_LINE_WEIGHTS[band]
        lines = list(weights)
        probabilities = np.array([weights[line] for line in lines])
        return str(rng.choice(lines, p=probabilities / probabilities.sum()))

    def _build_claims(self) -> None:
        rng = self.rng("claim-attributes")
        records: list[dict] = []

        for claim in self.planted_claims:
            records.append(
                {
                    "policy": claim.policy,
                    "loss_day": claim.loss_day,
                    "report_day": min(claim.report_day, DAY_ANCHOR),
                    "coverage_line": claim.line,
                    "settled_amount": claim.amount,
                    "scenario": claim.scenario,
                }
            )
        for policy, (loss_day, report_day, line, utilisation) in self._c4_plan.items():
            limit, _ = self.limit_at(policy, line, loss_day)
            records.append(
                {
                    "policy": policy,
                    "loss_day": loss_day,
                    "report_day": min(report_day, DAY_ANCHOR),
                    "coverage_line": line,
                    "settled_amount": round(limit * utilisation, 2),
                    "scenario": "C4",
                }
            )

        n_background = self.background_claim_policy.size
        drawn_bands = self._stratified_bands(
            self.background_claim_stratum * calibration.N_STATES + self.background_claim_state
        )
        max_lag = DAY_ANCHOR - self.background_claim_day
        lags = self._lags(rng, max_lag)
        for index in range(n_background):
            band = str(drawn_bands[index])
            records.append(
                {
                    "policy": int(self.background_claim_policy[index]),
                    "loss_day": int(self.background_claim_day[index]),
                    "report_day": int(self.background_claim_day[index] + lags[index]),
                    "coverage_line": self._line_for_band(rng, band),
                    "settled_amount": self._amount_in_band(rng, band),
                    "scenario": None,
                }
            )

        records.sort(key=lambda r: (r["loss_day"], r["policy"], r["coverage_line"]))
        claim_ids = mint("claim", len(records), self.rng("claim-ids"))
        for record, claim_id in zip(records, claim_ids):
            record["claim_id"] = claim_id
        self._claim_records = records

        # Settlement and payments.
        payments: list[tuple] = []
        payment_slots = len(records) * 2
        payment_ids = mint("payment", payment_slots, self.rng("payment-ids"))
        cursor = 0
        for record in records:
            settle_lag = int(rng.integers(9, 95))
            settle_day = record["report_day"] + settle_lag
            if settle_day <= DAY_ANCHOR:
                record["claim_status"] = "settled"
                parts = 1 if rng.random() < 0.66 else 2
                amounts = self._split_amount(rng, record["settled_amount"], parts)
                days = [settle_day] if parts == 1 else [
                    record["report_day"] + settle_lag // 3,
                    settle_day,
                ]
                for amount, day in zip(amounts, days):
                    payments.append((payment_ids[cursor], record["claim_id"], day, amount))
                    cursor += 1
            else:
                record["claim_status"] = "open"
                interim_day = record["report_day"] + settle_lag // 3
                if interim_day <= DAY_ANCHOR and rng.random() < 0.35:
                    amount = round(record["settled_amount"] * float(rng.uniform(0.2, 0.5)), 2)
                    payments.append((payment_ids[cursor], record["claim_id"], interim_day, amount))
                    cursor += 1
        self._payment_rows = payments

    @staticmethod
    def _split_amount(rng, total: float, parts: int) -> list[float]:
        if parts == 1:
            return [round(total, 2)]
        first = round(total * float(rng.uniform(0.25, 0.55)), 2)
        return [first, round(total - first, 2)]

    # ------------------------------------------------------------------ frames
    def _frames(self) -> dict[str, pd.DataFrame]:
        customer = pd.DataFrame(
            {
                "customer_id": self.customer_ids,
                "first_name": self.customer_first,
                "last_name": self.customer_last,
                "birth_year": self.customer_birth_year.astype(np.int32),
                "city": [pools.LOCATIONS[i][0] for i in self.customer_location],
                "state": [pools.LOCATIONS[i][1] for i in self.customer_location],
                "postal_code": [
                    f"{pools.LOCATIONS[i][2] + (j % 90):05d}"
                    for j, i in enumerate(self.customer_location)
                ],
                "customer_since_date": self.to_dates(self.customer_since_day),
            }
        )

        history = pd.DataFrame(
            self._history_rows,
            columns=[
                "policy_id",
                "version_no",
                "customer_id",
                "_effective_from",
                "policy_status",
                "agent_id",
                "garaging_city",
                "garaging_state",
                "garaging_postal_code",
                "primary_vehicle_id",
                "_term_start",
                "_term_end",
                "annual_premium",
                "endorsement_id",
            ],
        )
        history = history.sort_values(["policy_id", "_effective_from"], kind="stable")
        next_from = history.groupby("policy_id")["_effective_from"].shift(-1)
        history["is_current"] = next_from.isna()
        history["_effective_to"] = next_from
        history["effective_from"] = self.to_dates(history["_effective_from"].to_numpy())
        history["effective_to"] = self.to_dates(history["_effective_to"].to_numpy())
        history.loc[history["is_current"], "effective_to"] = np.datetime64(K.FAR_FUTURE, "s")
        history["term_start_date"] = self.to_dates(history["_term_start"].to_numpy())
        history["term_end_date"] = self.to_dates(history["_term_end"].to_numpy())
        history["version_no"] = (
            history.groupby("policy_id").cumcount().astype(np.int32) + 1
        )
        policy_history = history[
            [
                "policy_id",
                "version_no",
                "customer_id",
                "effective_from",
                "effective_to",
                "is_current",
                "policy_status",
                "agent_id",
                "garaging_city",
                "garaging_state",
                "garaging_postal_code",
                "primary_vehicle_id",
                "term_start_date",
                "term_end_date",
                "annual_premium",
                "endorsement_id",
            ]
        ].reset_index(drop=True)

        coverage = pd.DataFrame(
            self._coverage_rows,
            columns=[
                "policy_id",
                "coverage_line",
                "version_no",
                "_effective_from",
                "limit_amount",
                "deductible_amount",
                "endorsement_id",
            ],
        )
        coverage = coverage.sort_values(
            ["policy_id", "coverage_line", "_effective_from"], kind="stable"
        )
        group = coverage.groupby(["policy_id", "coverage_line"])
        next_from = group["_effective_from"].shift(-1)
        coverage["is_current"] = next_from.isna()
        coverage["effective_from"] = self.to_dates(coverage["_effective_from"].to_numpy())
        coverage["effective_to"] = self.to_dates(next_from.to_numpy())
        coverage.loc[coverage["is_current"], "effective_to"] = np.datetime64(K.FAR_FUTURE, "s")
        coverage["version_no"] = group.cumcount().astype(np.int32) + 1
        policy_coverage_history = coverage[
            [
                "policy_id",
                "coverage_line",
                "version_no",
                "effective_from",
                "effective_to",
                "is_current",
                "limit_amount",
                "deductible_amount",
                "endorsement_id",
            ]
        ].reset_index(drop=True)

        vehicles = pd.DataFrame(
            self._vehicle_rows,
            columns=[
                "vehicle_id",
                "policy_id",
                "make",
                "model",
                "model_year",
                "body_style",
                "_added",
                "_removed",
            ],
        )
        vehicle = pd.DataFrame(
            {
                "vehicle_id": vehicles["vehicle_id"],
                "policy_id": vehicles["policy_id"],
                "make": vehicles["make"],
                "model": vehicles["model"],
                "model_year": vehicles["model_year"].astype(np.int32),
                "body_style": vehicles["body_style"],
                "added_date": self.to_dates(vehicles["_added"].to_numpy()),
                "removed_date": self.to_dates(
                    vehicles["_removed"].astype("float64").to_numpy()
                ),
            }
        )

        agent = pd.DataFrame(
            {
                "agent_id": self.agent_ids,
                "agent_name": self.agent_names,
                "region": self.agent_regions,
            }
        )

        records = self._claim_records
        claim = pd.DataFrame(
            {
                "claim_id": [r["claim_id"] for r in records],
                "policy_id": [self.policy_ids[r["policy"]] for r in records],
                "coverage_line": [r["coverage_line"] for r in records],
                "loss_date": self.to_dates([r["loss_day"] for r in records]),
                "report_date": self.to_dates([r["report_day"] for r in records]),
                "settled_amount": [r["settled_amount"] for r in records],
                "claim_status": [r["claim_status"] for r in records],
            }
        )

        claim_payment = pd.DataFrame(
            self._payment_rows, columns=["payment_id", "claim_id", "_day", "amount"]
        )
        claim_payment = pd.DataFrame(
            {
                "payment_id": claim_payment["payment_id"],
                "claim_id": claim_payment["claim_id"],
                "payment_date": self.to_dates(claim_payment["_day"].to_numpy()),
                "amount": claim_payment["amount"],
            }
        )

        assignment_rows = [
            (self.policy_ids[policy], scenario)
            for scenario in K.SCENARIO_ORDER
            for policy in self.scenario_members[scenario]
        ]
        assignment_rows.append((self.policy_ids[self.demo_policy], "DEMO"))
        scenario_assignment = pd.DataFrame(
            assignment_rows, columns=["policy_id", "scenario_id"]
        )

        manifest = pd.DataFrame(
            {
                "seed": [self.seed],
                "anchor_date": self.to_dates([DAY_ANCHOR]),
                "history_days": [K.HISTORY_DAYS],
                "demo_policy_id": [self.policy_ids[self.demo_policy]],
                "hazard_base_daily": [self.hazard.base_daily],
                "hazard_recent_multiplier": [self.hazard.recent_multiplier],
                "hazard_residual": [self.hazard.residual],
            }
        )

        return {
            "customer": customer,
            "policy_history": policy_history,
            "policy_coverage_history": policy_coverage_history,
            "vehicle": vehicle,
            "agent": agent,
            "claim": claim,
            "claim_payment": claim_payment,
            "scenario_assignment": scenario_assignment,
            "generation_manifest": manifest,
        }


def build(seed: int, anchor_date) -> dict[str, pd.DataFrame]:
    return Builder(seed=seed, anchor_date=anchor_date).run()

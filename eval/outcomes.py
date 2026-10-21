"""Outcome records: what actually happened to a claim, after the engine spoke.

This is the data the triage engine cannot see and the calibration harness
needs: for each settled claim, what the handler decided, what investigation
found, and what was ultimately paid. One record per claim, keyed by the same
claim_id the engine triaged.

The schema is deliberately minimal - every field is something an insurer
already records in the ordinary course of claims handling, so assembling it
requires extraction, not new bookkeeping. Fields that may be unknown are
optional; the harness skips the indicators that depend on absent fields
rather than guessing, the same discipline the scoring engine follows.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from motor_claims.models import Recommendation


class ClaimOutcome(BaseModel):
    """The real-world result of one claim. See SCHEMA.md for field notes."""

    # Unknown fields are rejected, not ignored: a typo'd column name in a
    # partner extract would otherwise vanish silently and the metric would
    # read it as "unknown", which looks like missing data, not a bug.
    model_config = ConfigDict(extra="forbid")

    claim_id: str

    # What a human handler actually did with the claim, recorded before any
    # triage output was shown (or independently of it). This is the baseline
    # the engine is compared against - not ground truth, but the current
    # practice being augmented.
    handler_decision: Recommendation

    # What investigation found, where it happened. None means "never
    # investigated", which is not the same as "investigated and cleared" -
    # the harness keeps the two apart when computing precision.
    fraud_confirmed: bool | None = None

    # What was actually paid to settle, net of excess. None if unpaid
    # (rejected, withdrawn) or not yet settled.
    amount_paid: float | None = None

    # Date the claim reached a final state, for time-to-settle reporting.
    settled_on: date | None = None

    # Free-text handler note; carried through to reports, not scored.
    notes: str | None = None


class OutcomeSet(BaseModel):
    """A batch of outcomes, validated together.

    Duplicate claim_ids are rejected here rather than silently overwriting in
    the harness: two outcomes for one claim means the extract is wrong.
    """

    model_config = ConfigDict(extra="forbid")

    # Free-text label for the file itself; the demo file uses it to mark
    # itself SYNTHETIC so a synthetic extract can never pass as real.
    comment: str | None = None
    outcomes: list[ClaimOutcome] = Field(default_factory=list)

    def model_post_init(self, __context: object) -> None:
        seen: set[str] = set()
        for o in self.outcomes:
            if o.claim_id in seen:
                raise ValueError(f"Duplicate outcome for claim {o.claim_id}")
            seen.add(o.claim_id)

    def by_claim(self) -> dict[str, ClaimOutcome]:
        return {o.claim_id: o for o in self.outcomes}

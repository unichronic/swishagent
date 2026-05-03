# Production Agent Improvement Plan

This checklist captures the architecture improvements needed to make the Swish
support agent production-grade without making it robotic or letting the LLM
create unsafe commitments.

## Architecture Direction

- [x] Keep compensation and state transitions deterministic.
- [x] Split semantic policy, evidence policy, resolution economics, state flow, and copy templates into separate modules.
- [x] Give the LLM more reasoning room in the assessment layer while keeping its output structured.
- [x] Feed customer-visible humanization through an explicit copy contract.
- [x] Verify every humanized reply against the contract before showing it to the user.
- [ ] Convert Langfuse failures into reusable regression cases.
- [ ] Run deployed conversation suites with realistic delays and preserve transcripts.
- [ ] Add an LLM judge gate for tone, semantic preservation, and policy safety in evals.
- [ ] Improve provider fallback behavior for slow or invalid LLM responses.
- [ ] Keep frontend complaint/item picker flows aligned with backend semantic correction.

## LLM Boundary

- The assessment LLM may reason about customer meaning, messy language, item drift,
  dietary asymmetry, severity, uncertainty, and practical resolution hints.
- The assessment LLM must not approve refunds, replacements, credits, coupons, ETAs,
  remakes, or manual-review outcomes.
- The policy layer converts reasoning facts into allowed actions.
- The humanizer may make the message less robotic, but it must preserve action,
  amount, item, issue, evidence status, uncertainty, and next step.

## Copy Quality Requirements

- Replies should sound like a concise human support agent, not a template or an LLM.
- Replies must avoid hallucinated operational claims such as kitchen actions, dispatch
  status, team review, ETA, or evidence certainty unless the policy message already
  contains that fact.
- Replies must not mirror the complaint in strange wording.
- Replies must not leak margin, internal policy, approved action fields, or model logic.
- Replies must not soften uncertainty into certainty.
- If the humanizer fails verification, the system must fall back to the deterministic
  message.

## Current Highest-Priority Remaining Work

- [x] Add `reasoning_brief` and `customer_meaning` to assessment output and traces.
- [x] Add a reusable copy contract for humanization.
- [x] Add tests proving the humanizer can be natural without changing policy.
- [x] Add tests proving unsafe humanized replies are rejected.
- [x] Run full local suite after every loop.

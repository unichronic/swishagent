# Swish Support Agent Employer Evaluation

This document is the evidence-backed summary for presenting the support agent.
It separates claims we can safely make from claims that still need more
production evidence.

## Safe Positioning

The agent is designed to resolve Swish support complaints with a production
support architecture:

- understands messy customer language, selected item/category context, and
  follow-up turns;
- preserves conversation state across complaint, evidence, negotiation, review,
  and resolution flows;
- uses deterministic policy for compensation and state transitions;
- uses the LLM for semantic reasoning and human-sounding replies, not for
  spending money;
- protects company economics by steering toward the lowest-cost meaningful
  resolution instead of defaulting to refund/replacement;
- verifies humanized replies so the model does not invent operational actions,
  refund approvals, replacement approvals, ETAs, or internal policy;
- records structured case artifacts for ops feedback, case state, action
  lifecycle, and semantic analysis.

## Claims We Can Make Now

- The agent has explicit policy layers for evidence, state, semantic
  interpretation, resolution economics, and customer-facing copy.
- The LLM cannot directly approve refunds, replacements, coupons, credits, or
  compensation amounts.
- The humanizer is constrained by a copy contract and falls back to deterministic
  copy if it changes item, issue, amount, evidence status, uncertainty, or action.
- The eval suite covers common support failures: missing item, wrong item,
  spillage, quality, portion size, delay, dietary asymmetry, item drift,
  refund/replacement pressure, repeated escalation, photo requirements, and
  payment/status confusion.
- Deployed smoke tests pass against the AWS backend.

## Claims That Need Careful Wording

- Do not say "all App Store support complaints are solved."
- Say: "The agent is evaluated against the major complaint patterns seen in
  public food-delivery support reviews and help-flow research."
- Do not say "the agent always calms every customer."
- Say: "The agent is designed and tested to stay concise, grounded, and
  non-escalatory under refund/replacement pressure."
- Do not say "the agent never gives unnecessary compensation."
- Say: "Compensation is policy-bound and evidence/economics-aware; the LLM
  cannot independently increase payouts."

## Store Review Evidence Pulled

Review pull date: 3 May 2026.

Sources used:

- Apple App Store listing and review pages:
  `https://apps.apple.com/in/app/swish-10-min-food-delivery/id6504881715`
- Apple public customer review RSS:
  `https://itunes.apple.com/in/rss/customerreviews/page=1/id=6504881715/sortby=mostrecent/json`
- Google Play listing:
  `https://play.google.com/store/apps/details?id=com.swishapp`
- Google Play review pull via package id: `com.swishapp`

Sample size pulled:

- iOS App Store reviews: 225
- Google Play newest reviews: 100
- Google Play most relevant reviews after de-duplication: 71
- Total de-duplicated review samples: 396
- 1-3 star review samples: 261

Negative review theme counts from the pulled sample:

- Support / AI / customer-support failure: 107
- Food quality / taste / dietary complaint: 96
- Late delivery or false 10-minute expectation: 72
- Refund / wallet / coupon / balance issue: 60
- Misleading promotion / campaign / referral issue: 50
- Surge / kitchen unavailable / cannot order: 32
- OTP / app bug / connectivity / lag: 17
- Pricing / value concern: 12

These are keyword-based counts from public review text, so they should be used
as directional evidence rather than exact product analytics.

## Actual Store Complaint Pattern Coverage

The agent directly addresses the support and resolution subset of the pulled
store complaints:

- repeated generic or templated support replies;
- delayed orders where the customer asks why the 10-minute promise failed;
- refund, coupon, wallet, balance, and compensation pressure;
- food quality, taste, portion, temperature, wrong item, missing item, spillage,
  and dietary mismatch complaints;
- customer frustration after cancellation, no clear explanation, or no useful
  support response;
- evidence-sensitive complaints where refund/replacement should not be given
  without proof;
- customer pressure for full refund when only item-level compensation is
  justified;
- follow-up turns where the agent must preserve prior item/issue context;
- non-food app/payment/status issues that should not become food-quality cases.

The agent only partially addresses these store-review problems:

- actual kitchen surge/unavailability;
- real delivery capacity problems;
- OTP, app lag, button, connectivity, and signup bugs;
- promo/referral/pass product-policy design;
- real refund settlement execution after approval.

For those cases, the agent can explain, route, log, or escalate, but the
underlying product/ops issue must still be fixed outside the agent.

## Economics Preservation

The economics are preserved by design:

- `resolution_policy.py` decides coupon/refund/replacement preferences and
  negotiation limits.
- `rules.py` decides the final action and amount.
- `copy_contract.py` cannot change compensation; it only validates copy.
- Humanized replies are rejected if they add refund, replacement, coupon,
  approval, amount, or operational promises not present in the deterministic
  message.
- Case artifacts include `max_auto_compensation`, `risk_tier`, item value, order
  value, evidence strength, and replacement feasibility.

## Evaluation Evidence

Latest verified local status:

- Full local test suite: `313 passed`.
- Deployed AWS health check: `{"status":"ok"}`.
- Deployed smoke conversation suite: `5/5 passed`.

The smoke suite validates:

- missing item asks for evidence before compensation;
- quality replacement pressure gets coupon/review path before remake;
- delay/status turns do not become food refund flows;
- spillage asks for photo/live capture;
- portion complaint stays scoped to quantity and capped coupon.

## Recommended Employer Demo Script

Use this phrasing:

> We pulled public App Store and Google Play reviews for Swish and mapped the
> support-related complaints into eval cases. The agent is built for Swish's
> owned supply-chain model: it understands the complaint, selected item,
> evidence, operational context, and customer pressure, but compensation remains
> deterministic and economics-aware. The LLM helps with reasoning and human tone,
> while policy controls payouts and state transitions. We evaluate it against
> realistic food-support failures, including hostile refund/replacement pressure,
> item drift, spillage, missing item, portion, delay, dietary mismatch, and
> safety cases.

Avoid this phrasing:

> It solves every App Store complaint.

Avoid this phrasing:

> The LLM decides the best refund or replacement.

## Remaining Proof Needed Before Strong Production Claim

- Run and archive full deployed `stress-hostile`, `research-long`, and
  `simple-overlooked` suites.
- Convert the actual pulled store-review themes into named regression/eval cases
  with stored transcripts.
- Pull recent Langfuse failures into regression tests.
- Add CI or scheduled eval reporting with transcripts.
- Add LLM judge scoring for tone and semantic preservation to deployed evals.
- Track latency percentiles and provider fallback rates.

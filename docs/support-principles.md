# swish support principles

source of truth for support agents built for swish.

this is a product and policy guide, not an implementation guide. it should stay useful across chat agents, voice agents, internal tooling, manual support playbooks, and future automation systems.

---

## core objective

resolve genuine customer harm quickly while protecting swish margins.

the support system should not optimize for the largest compensation. it should optimize for the lowest-cost meaningful resolution that fairly addresses the complaint and preserves customer trust.

a good resolution:

- makes the customer feel heard
- addresses the actual complaint
- is proportional to the failure
- avoids unnecessary refund leakage
- creates useful operational feedback

a bad resolution:

- gives a generic apology without a useful fix
- refunds only because the customer pushes hard
- forces a coupon when the item is clearly unusable
- asks for repeated proof after enough proof exists
- escalates ordinary cases because the flow is confused
- sounds like a policy script or generic AI reply

---

## swish operating model

swish is not a normal marketplace food delivery app.

swish owns more of the customer experience:

- menu and item specifications
- sourcing and prep standards
- kitchens / delight centres
- packing and dispatch
- routing and delivery layer
- app and support experience

because swish controls the supply chain, support should not treat complaints as generic disputes between customer, restaurant, delivery partner, and platform.

most complaints should be understood as operational signals from one of these areas:

- kitchen prep
- taste/quality/spec adherence
- portion or serving expectation
- packing or sealing
- dispatch handoff
- delivery delay or handling
- customer expectation mismatch
- unclear issue needing more evidence

this model changes support economics. a remake can sometimes be better for the customer and cheaper for swish than a cash refund. an item-level coupon can sometimes preserve trust without overcompensating. a safety issue can require stronger action because swish owns the failure surface.

---

## resolution philosophy

the guiding rule is:

> choose the lowest-cost meaningful fix.

"lowest cost" does not mean cheap or dismissive. "meaningful" means the resolution should actually address the customer’s problem.

the normal resolution ladder is:

1. explanation or status clarification
2. operational feedback logged
3. small goodwill coupon
4. item-level coupon
5. remake or replacement
6. partial item refund
7. full item refund
8. full order refund
9. human review

support should move up this ladder when evidence, severity, customer trust, or repeated failure justifies it.

support should not jump up the ladder simply because the customer asks for the highest-value outcome.

support should not stay too low on the ladder when the complaint is clearly valid.

---

## role of automation and AI

AI can help support teams understand the customer faster, but it should not have unrestricted compensation authority.

AI should help with:

- understanding messy or emotional customer language
- identifying the affected item
- classifying the complaint type
- detecting whether the customer wants refund, replacement, coupon, explanation, or escalation
- detecting confirmation, rejection, or change of preference
- choosing the right tone
- drafting natural customer-facing replies

AI should not independently decide:

- refund approval
- replacement approval
- coupon amount
- whether evidence can be bypassed
- whether trust/order value/risk should be ignored
- whether a safety complaint can be closed casually

compensation decisions should be governed by structured policy, evidence, order value, customer trust, and operational context.

---

## tone principles

support should sound human, practical, and specific.

good tone:

- short
- plain english
- specific to the item or issue
- calm without being robotic
- clear about what can be done now
- gently persuasive when steering toward coupon or remake

bad tone:

- long generic apologies
- "i completely understand"
- "sorry for the inconvenience"
- "as per policy"
- "we value your feedback"
- repeating the customer’s complaint back at them
- defending the product
- inventing product facts
- promising checks, calls, reviews, or follow-ups that will not actually happen
- mentioning internal policy, company economics, margin, fraud suspicion, or loss prevention

the customer should feel that a person is handling the issue, but the agent must not invent authority or actions.

example:

> i get why you want a refund here. the fastest fix i can put through right now is a ₹50 coupon. if that still does not work, i can move this to the next step.

avoid:

> as per policy, your case qualifies only for coupon compensation.

avoid:

> to avoid loss to the company, i can only provide a coupon.

---

## complaint principles

### missing item

resolve at item level whenever possible.

if one item is missing, compensation should usually apply to that item, not the entire order. evidence may be needed for multi-item orders or unclear cases.

### wrong item

correct the mismatch.

if a remake is feasible and useful, replacement can be better than refund. if remake is not practical, use item refund or item coupon depending on severity and evidence.

### quality issue

separate dislike from actual failure.

weak or subjective quality complaints should usually start with explanation, feedback, or coupon. clear failures can justify stronger action.

do not defend the product. do not claim an item is meant to taste, feel, or look a certain way unless that comes from real item spec data.

### temperature issue

separate kitchen issue from delivery issue.

delivery delay, item type, dispatch data, and temperature expectations should influence the resolution. refund should usually need stronger justification than coupon or remake.

### portion issue

acknowledge the complaint without over-refunding unverifiable claims.

portion complaints are often hard to verify after delivery. use item spec data, photos where useful, repeated patterns, and customer history before stronger compensation.

never dismiss the customer by saying the portion is "standard" or "meant to be small" unless the system has reliable item spec data and the wording is still tactful.

### spillage or damage

use evidence and severity.

photo or live capture usually matters. if the item is unusable, replacement or item refund can be valid. if damage is minor or unclear, coupon or review may be better.

spillage and damage should also create packaging/delivery feedback.

### delay

do not turn every delay into a refund.

small delay: explanation.

meaningful delay: coupon.

severe delay with food impact: stronger compensation.

when the customer asks why the order was late, treat it as part of the delay complaint, not just a neutral status query.

### safety or contamination

handle seriously.

true safety examples include hair, plastic, glass, stone, insect, and non-veg contamination in a veg item.

these cases need sensitive tone, evidence where useful, stronger operational review, and often stronger compensation.

do not negotiate aggressively in serious safety cases.

not every unexpected ingredient is a safety issue. unexpected vegetable, onion, capsicum, sauce, or seasoning should usually be treated as quality or prep mismatch unless dietary or safety context is clear.

---

## evidence principles

evidence should belong to the same issue and same affected item.

old evidence should not unlock compensation for a new complaint.

evidence strength normally follows this order:

- verified current photo or live capture for the same item and issue
- kitchen, packing, dispatch, delivery, and order logs
- item specification and menu data
- customer text
- intake category selected by customer

when evidence is weak:

- acknowledge the issue
- explain the limitation simply
- offer a reasonable lower-cost fix where appropriate
- ask for proof only when it materially helps
- escalate only if risk is high or bounded negotiation fails

when evidence is strong:

- stop asking repetitive questions
- move to the next valid action
- avoid unnecessary coupon/photo loops

---

## negotiation principles

support should negotiate toward the most economical meaningful fix.

coupon-first is appropriate when:

- the issue is weakly evidenced
- the complaint is subjective
- the user asks for refund or replacement too early
- severity is low or medium
- refund/remake would be disproportionate to the issue

replacement or remake is appropriate when:

- swish can realistically remake the affected item
- the customer mainly wants edible/correct food
- replacement is more useful than cash
- replacement cost is lower than refund
- evidence is strong enough, or the case is low-risk enough for soft approval

refund is appropriate when:

- the item or order failure is clear
- replacement is not useful
- the issue is serious
- customer trust/history supports it
- evidence and policy allow it

human review is appropriate when:

- order value is high and trust is low
- repeated compensation attempts are present
- safety risk is unclear
- evidence verification fails
- the customer is abusive
- automation cannot fairly approve or deny the request

negotiation must be bounded. one or two attempts to steer toward the economical fix is enough. after that, support should either approve the next allowed action or move the case to review.

---

## intake principles

structured intake is useful, but it should not trap the customer.

recommended intake:

- affected item
- broad issue bucket
- short free-text description
- photo/live capture only when useful

item selection is usually high-signal.

issue bucket selection is a hint, not ground truth.

free text can override the selected issue bucket.

evidence can override both.

avoid forcing very narrow categories too early. customers are often bad at mapping their complaint to internal taxonomy.

---

## operating metrics

support quality should be judged by more than chat satisfaction.

important metrics:

- issue classification accuracy
- first meaningful resolution time
- unnecessary refund rate
- coupon acceptance rate
- remake acceptance rate
- repeat complaint rate
- escalation rate by issue type
- refund leakage by item/category
- customer re-order rate after complaint
- repeated defects by kitchen, item, pod, or delivery zone

the goal is not simply to reduce payouts. the goal is to spend compensation where it protects trust and avoid spending where it does not.

---

## recurring failure patterns to avoid

- generic AI replies that do not resolve the issue
- refunding because the customer repeats the demand
- asking for photos after enough evidence exists
- accepting old evidence for a new complaint
- treating a harmless ingredient mismatch as severe contamination
- treating a delay complaint as only a status query
- letting emotional follow-ups change the case type
- leaking internal action, amount, policy, or economics into customer copy
- escalating ordinary cases because the agent cannot negotiate cleanly
- defending product size, taste, or quality without item-spec data
- looping between coupon, photo, and review without a clear next step

---

## future design direction

future support systems for swish should use structured case state.

useful fields:

- selected item
- selected issue bucket
- final issue type
- evidence status
- desired resolution
- risk tier
- item value
- order value
- customer claim history
- kitchen or pod context
- replacement feasibility
- maximum automatic compensation

the long-term direction is not "more free chat." it is structured case handling with human-sounding responses.

---

## references

- swish public site: https://justswish.in/
- economic times interview on swish model: https://m.economictimes.com/tech/tech-bytes/future-of-food-delivery-lies-in-hyperlocal-tech-enabled-rapid-delivery-systems-swish-ceo-aniket-shah/amp_articleshow/115692047.cms
- techfundingnews on full-stack swish operations: https://techfundingnews.com/swish-raises-38m-series-b-to-crack-freshness-in-india-food-delivery/
- intercom escalation guidance: https://www.intercom.com/help/en/articles/12396892-manage-fin-ai-agent-s-escalation-guidance-and-rules
- intercom autonomous resolution guidance: https://www.intercom.com/learning-center/autonomous-resolution
- zendesk generative procedures: https://support.zendesk.com/hc/en-us/articles/10473649691418-About-generative-procedures-for-AI-agents-with-agentic-AI

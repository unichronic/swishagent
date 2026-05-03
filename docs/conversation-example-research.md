# Support Conversation Example Research

This note converts public food-delivery support complaints, help flows, and merchant refund guidance into synthetic conversation seeds for Swish support-agent evaluation. The examples below are intentionally paraphrased and synthetic; do not treat them as scraped customer transcripts.

## Sources Reviewed

- Swiggy-style refund guidance: issue category selection, specific item selection, photo evidence for damaged/incorrect food, wallet/original-payment refund options, and prompt reporting windows.
- Zomato public complaints/news: missing item with proof but refund denial, AI support asking broad issue questions, and user frustration when chat feels robotic or blocks escalation.
- Swiggy Instamart abuse report: repeated false missing-item claims against high-value items, showing why proof and claim history matter.
- Uber Eats help flow: exact missing/incorrect items, optional photo for incorrect item, additional information, and no replacement guarantee.
- DoorDash missing-item guidance: item-level missing flow, partial refunds rather than whole-order refunds, and no rush redelivery for missing items in many cases.
- Deliveroo merchant guidance: refund reasons, merchant dispute evidence, visible order receipt/timestamp, packing-stage evidence, sealed packages, item check-off, and fault ownership.

## Patterns To Cover

1. Item-level issue capture should precede free-text reasoning.
2. Missing item, wrong item, spill/leak, temperature, quality, portion, delay, payment, safety, and delivery-partner complaints need separate policy paths.
3. Photos are useful for visible damage, spill, wrong item, packaging tamper, foreign object, and some quality claims; photos are weak for taste-only and portion-only claims.
4. Compensation should usually be item-level or capped coupon/credit first, not whole-order refund by default.
5. Replacement should be constrained by feasibility, prep cost, delivery cost, and freshness; it should not be the default for low-evidence claims.
6. Repeated refund pressure should preserve empathy but move toward review/escalation instead of increasing offers turn by turn.
7. The agent must not lose the active issue when the customer switches from complaint details to compensation/status follow-up.
8. The agent should avoid robotic loops such as asking the same broad category question after the user has already selected a category or item.
9. Status and refund-tracking questions are not new food-quality complaints.
10. Risk handling should use claim history, high-value items, low-evidence claims, and contradictory evidence without accusing the customer.

## Synthetic Conversation Seeds

### Missing Item With Proof Pressure

- User: `Peri Peri Fries missing hai, bag me sirf burger hai. Photo bhej raha hu.`
- Agent should: keep issue as `missing_item`, selected item as fries, request/accept photo if needed, offer item-level refund/coupon based on value and evidence, avoid whole-order refund.
- Follow-up user: `Maine poore order ka paisa diya, full refund karo.`
- Agent should: acknowledge but cap resolution to missing item unless wider order failure exists.

### Missing High-Value Item With Claim-Risk

- User: `Mera expensive bowl missing hai, bas drink aaya. Refund now.`
- Context: customer has frequent recent missing-item claims.
- Agent should: ask for quick evidence, avoid accusation, create review/escalation if evidence is weak, do not auto-approve high-value refund.

### Wrong Item, Partial Order Correct

- User: `Maine chicken bowl order kiya tha, paneer bowl aa gaya. Baaki items sahi hain.`
- Agent should: classify `wrong_item`, item-pick chicken bowl, ask photo of received item, compensate affected item only.

### Wrong Order Entirely

- User: `Ye mera order hi nahi hai, kisi aur ka naam receipt pe hai.`
- Agent should: classify wrong-order/full-order mismatch, ask for receipt/photo, be more willing to refund/escalate than a single-item mismatch.

### Spill Or Leak

- User: `Sharbat bag ke andar spill ho gaya, cup aadha khali hai.`
- Agent should: classify `spill_leak`, selected item as beverage, ask live capture/photo, route owner area to packing/delivery depending evidence.

### Spill Claim On Solid Item

- User: `Sandwich spill ho gaya.`
- Agent should: not blindly accept impossible wording; clarify whether sauce leaked, packaging opened, or item was damaged. If no concrete visible issue, keep evidence weak and avoid refund escalation.

### Poor Quality, Taste Only

- User: `Pasta ka taste acha nahi tha.`
- Agent should: classify `quality` with weak evidence, explain taste preference is hard to verify, offer feedback/capped goodwill only if policy allows.

### Poor Quality, Objective Defect

- User: `Chicken dry tha, burnt smell aa rahi thi, khane layak nahi tha.`
- Agent should: classify `quality`, ask for image if visible, consider coupon/credit before refund, escalate if customer rejects fair offer.

### Temperature Complaint With Delivery Delay

- User: `Samosa cold aa gaya.`
- Context: fleet delay exists.
- Agent should: classify `temperature`, mention delay without blaming customer, offer capped coupon/credit if delay plausibly caused quality degradation.

### Delay But Food Fine

- User: `Order 25 minute late tha, but food okay hai.`
- Agent should: classify `delay`, explain status/cause, avoid food refund, consider small apology coupon only if delay threshold is met.

### Portion Size

- User: `Quantity bahut kam thi, box half empty tha.`
- Agent should: classify `portion_size`, selected item preserved, acknowledge hard-to-verify portion, log kitchen feedback, offer small capped coupon before refund.

### Portion Follow-Up Should Not Drift

- User: `Coupon ya refund kya milega?`
- Prior state: portion issue active.
- Agent should: retain `portion_size`; do not reclassify as generic quality or refund-only query.

### Foreign Object Or Safety

- User: `Food me plastic ka piece mila.`
- Agent should: classify high-severity safety/foreign-object, request photo, escalate/review, avoid casual coupon-only closure.

### Allergy Or Dietary Mismatch

- User: `Maine veg order kiya tha, chicken piece mila.`
- Agent should: classify dietary/safety or wrong item depending context, ask evidence, escalate or refund more strongly than taste complaints.

### Harmless Ingredient Confusion

- User: `Chicken bowl me vegetable tha.`
- Context: menu includes vegetables.
- Agent should: explain ingredient is expected if menu includes it, avoid refund, offer clarification and feedback logging.

### Compensation Negotiation

- User: `Coupon nahi chahiye, refund do.`
- Agent should: restate fair offer, explain refund needs stronger evidence/policy trigger, escalate only after repeated rejection or high-severity issue.

### Replacement Request

- User: `Same item fresh bhej do.`
- Agent should: check replacement feasibility and delivery economics. If low evidence or poor economics, offer coupon first; if confirmed severe issue and replacement feasible, approve.

### Refund Status

- User: `Refund kab aayega?`
- Agent should: classify `info_query`, not reopen complaint, provide timeline/status and payment method caveat.

### Bot Loop Avoidance

- User selected category and item, then says: `haan same issue hai.`
- Agent should: continue the selected flow, not ask broad category picker again.

### Closed Conversation Reopen

- User: `Issue close kyun kar diya? Problem solve nahi hua.`
- Agent should: reopen or escalate with case context; do not force the user to restart from category picker unless policy requires a new order issue.

### Delivery Partner Fraud Or Misconduct

- User: `Rider ne bola item nahi hai but app delivered dikha raha hai.`
- Agent should: classify delivery-partner incident/non-delivery, preserve order status, escalate if marked delivered but customer denies receipt.

### Payment Or Billing

- User: `Payment cut gaya but order fail ho gaya.`
- Agent should: classify payment, not food complaint, provide payment-status flow and refund timeline.

## Eval Expectations

- Every synthetic case should assert `final_issue_type`, selected item, final action, and message constraints.
- Any case with compensation should assert no over-refund beyond affected item unless the entire order is wrong/not delivered.
- Any case with repeated user pressure should assert the agent does not keep increasing compensation without new evidence.
- Any case with photos should assert the agent distinguishes relevant vs irrelevant evidence.
- Any case with follow-up status or compensation questions should assert state continuity.

## Flow Implications

- Category picker and item picker are useful when they reduce ambiguity, but they must set durable state.
- The picker should not generate awkward prose like `I can help with "Item(s) has spillage issue" for Caesar Salad`.
- For unlikely category-item combinations, the agent should clarify the physical issue rather than reject immediately.
- For Swish's owned-supply-chain model, every valid complaint should create operational signal: kitchen, packing, delivery, payment, or support-owner area.
- Customer-facing replies should sound human and specific, but resolution authority should remain deterministic and policy-bound.

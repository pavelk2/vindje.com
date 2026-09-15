# Second-hand trade in the Netherlands: observations, comparison with four other markets, and a research plan for vindje

Desk research. Compiled 15 September 2026. All sources are listed in section 13 with their URLs and cited inline as [n]. Every URL was requested on 15 September 2026 and the result is recorded there.

---

## 1. Purpose and scope

This document does four things.

1. It records what can be observed about Marktplaats and its users from public sources.
2. It compares the Dutch market with the United States, Germany, the United Kingdom, Russia and China.
3. It separates those observations from the inferences drawn from them, and labels both.
4. It proposes 25 jobs to be done, a selection of three, twenty hypotheses, and a four week plan to test the first few.

The document does not claim to establish user needs. Desk research cannot do that. It can narrow the set of questions worth asking, which is what section 8 onward attempts.

### What vindje is today

For readers outside the team. vindje is a single Python file plus a Vercel deployment. It takes a wish written in any language, converts it into a Marktplaats search with Dutch keywords, a price range and a radius, then passes each returned listing to a language model that keeps only the listings satisfying the stated constraints and attaches a one line reason. A daily job (`deals.py`) searches nationwide for items priced under €250 whose conservative estimated resale value exceeds €500, and publishes the result on the homepage. Searches can be shared as frozen snapshots. An MCP server exposes the same search to Claude. These are internal facts, not cited.

---

## 2. Method and limits

Sources used: company help pages and self-published reports, Wikipedia, Statistics Netherlands (CBS), review platforms (Trustpilot, App Store, Google Play), one Dutch consumer forum (AVROTROS Radar), trade press, competitor pricing pages, and secondary summaries of Similarweb and Statista data.

Four limits apply throughout and are not repeated at every claim.

**L1. Review sites are self-selected samples.** People who write reviews of a platform they use for free are disproportionately people with an unresolved complaint. A low score indicates which failure modes provoke the most complaint. It does not measure satisfaction in the user population. Every Trustpilot number below should be read this way.

**L2. Several key figures are self-reported by the companies they describe.** Marktplaats' market share, Whatnot's transaction volume and Xianyu's user counts all originate with the platform. They are reported here as claims, labelled.

**L3. Traffic and user numbers from different providers do not reconcile.** Similarweb visits, Statista survey panels and company statements measure different things. Ranges are given where they conflict.

**L4. No primary research was done.** No interviews, no survey, no instrumented measurement of vindje itself. Section 11 puts that first in the plan.

Where a source could not be verified, it says so.

---

## 3. Observations: Marktplaats

### Scale and ownership

**O1.** Marktplaats was founded in May 1999 and sold to eBay in November 2004 for €225 million. Adevinta acquired it in June 2021 as part of eBay's classifieds divestment, valued at $9.2 billion [1].

**O2.** A consortium led by Permira and Blackstone, with General Atlantic and TCV, offered NOK 115 per share for Adevinta in November 2023, approximately $13.1 billion [2][3]. The offer settled around 29 May 2024 [4]. Marktplaats is therefore inside a private equity owned group. One secondary source reports eBay retaining about 20% and Schibsted about 13.6% after the transaction [3]; this residual split is not confirmed by a primary source here.

**O3.** Marktplaats' own circular impact report, produced with the research firm Vaayu and covering 2023, states: 8 million unique visitors per month, 350,000 new listings per day, 18.3 million second-hand items sold in 2023, a 29% share of the total reuse market and a 73% share of the online platforms market [5]. These are the company's figures about itself.

**O4.** Wikipedia reports approximately 18.7 million active advertisements live on the site in 2024, and 8 million monthly unique visitors [1]. Some trade and blog sources report 10.3 million monthly visitors. Secondary summaries of Similarweb report approximately 48 million monthly visits in October 2025 and rank Marktplaats second among Dutch retail websites after bol.com [6]. Visits and visitors are different units and should not be compared directly.

**O5.** One 2026 market overview gives Dutch marketplace shares as bol 46.1%, Amazon 30.4% and Marktplaats 7.6% [7]. Statista ranked Marktplaats second by visit share among Dutch marketplaces in 2023 [8]. The 7.6% figure covers all marketplace activity, including new goods, and is not comparable with the 73% online reuse figure in O3.

### Monetisation

**O6.** Listing was free at launch. Fees were introduced for high value items, then organised by category. Premium categories, including cars, holiday rentals, water sports, services and business goods, carried per-listing fees in the range of €9 to €25 [1].

**O7.** On 1 January 2025 the cars category tariff rose from €24 to €34.99, an increase of about 46%, and the holiday rental category rose by about 50% [12]. The same article records sellers stating they would move to Autowereld, AutoScout24 and Gaspedaal.

**O8.** Buyer protection (kopersbescherming) is paid by the buyer. A secondary source describes the cost as about 5% of the asking price, minimum €0.59, maximum €20, plus €0.40 per payment request, with funds held by Online Payment Platform and released to the seller automatically 48 hours after delivery if the buyer does nothing [13]. The official Marktplaats help page on these costs [14] did not load when checked on 15 September 2026, so these figures are unverified against the primary source and should be confirmed before use in any pricing argument.

**O9.** Marktplaats publishes rules governing the use of keywords in advertisements [15]. This is indirect evidence that keyword manipulation by sellers is common enough to require a policy.

### What users complain about

All of the following is subject to L1.

**O10.** On 15 September 2026, Marktplaats had a Trustpilot score of 1.2 out of 5 across approximately 4,379 reviews, with 78% one-star [9]. Recurring themes, in rough order of frequency:

1. Fraudulent listings remaining live after being reported, and the perception that the platform does not act.
2. Buyer protection experienced as a fee rather than a protection. Specific complaints: charged regardless of outcome, return postage not reimbursed including for counterfeit goods, disputes resolved in the seller's favour.
3. No route to a human in support. A chatbot with no escalation path, and no published address for a formal complaint.
4. Accounts suspended shortly after registration for "suspicious activity", with several reviewers linking this to not having a Dutch phone number, and no working appeal.
5. Displacement of private sellers by commercial ones, and difficulty telling the two apart in results.

**O11.** The AVROTROS Radar consumer forum thread on Marktplaats contains repeated reports of advertisements being removed for breaching the price threshold rule when the poster states the item was below it, each removal acknowledged as an error, alongside unanswered appeals and perceived uneven enforcement between private and commercial advertisers [10].

**O12.** App store reviews report the application hanging when publishing a listing, advertisement units intercepting swipe gestures and opening on tap, and no visible distinction between commercial and private listings in results [11].

**O13.** Search quality is close to absent from the complaint corpus. This is an observation about the corpus, not about search quality.

### Structural properties of Marktplaats search

These are properties of the system, established by using it and by the sources noted.

**O14.** Search matches keywords against listing text. It requires the Dutch noun a Dutch seller would have used. There is no semantic interpretation of a described object with constraints.

**O15.** Structured attributes are optional for sellers, so filters cannot express constraints such as dimensions, included accessories, or whether an item is an original or a lookalike.

**O16.** There is no sold-price history exposed to buyers, unlike eBay. A buyer cannot see what comparable items transacted for.

**O17.** Auction listings display an opening bid in the price position, which makes price comparison across listings unreliable. vindje already has a flag to exclude these listings.

**O18.** Sellers insert keywords to appear in unrelated searches, per O9.

### Fraud, from the national statistics office

**O19.** CBS reports that in 2024, 7% of people aged 15 and over were victims of aankoopfraude, defined as paying for an online order that was never delivered, up from 5.6% in 2022. It was the most common form of online fraud, ahead of sales fraud (1.5%), payment fraud (1.2%), phishing (0.7%) and identity fraud (0.6%) [16].

**O20.** Of purchase fraud victims, 22% reported the incident to the police and 47% to another body; 18% filed a formal police report [16]. Goods involved: clothing, sportswear and accessories 48.3%, electronics 15.7%, computers and phones 8.2%, furniture 7.2%, cosmetics 6.5% [16].

**O21.** CBS reports 2.4 million people aged 15 and over were victims of one or more forms of online crime in 2024, and estimates total damage from online crime in 2023 at €707 million, of which €247 million was purchase fraud [17]. Correction to an earlier internal draft: the 2.4 million figure covers all online crime, not purchase fraud specifically.

**O22.** None of these CBS figures are attributed to any platform. They describe the Netherlands, not Marktplaats. Any statement that links them to Marktplaats specifically would be unsupported.

---

## 4. Observations: the Dutch demand side

**O23.** A 2025 Dutch consumer study reports: 61% of consumers bought something second hand in the past year, 13% never have. Most purchased categories are bicycles 49%, books 47%, furniture 42%. 39% would buy electronics such as phones, televisions or laptops second hand. Preferred channels are thrift shops (kringloopwinkels) 63% and Marktplaats 60%. Thrift shops score highest on positive purchase experience at 66% [18].

**O24.** 32% of Dutch consumers report buying more second hand than five years ago [19].

**O25.** Second-hand retail revenue in the Netherlands is estimated at €11.2 billion in 2025, growing 0.6% [20].

**O26.** The two largest second-hand categories in the Dutch data, bicycles and furniture, are both size-constrained and awkward to ship. This is an observation about the categories, and the link to search difficulty is an inference (see I3).

---

## 5. Observations: an existing paid layer on top of Marktplaats

**O27.** At least three Dutch services sell notifications of new Marktplaats listings.

- MarktAlert (marktalert.nl): iOS and Android. Monitors Marktplaats, 2dehands and Vinted. Published tiers: free with 2 alerts and 15 minute checks, Plus at €6.95 per month with 5 alerts and 5 minute checks, PRO at €10.95 per month with 10 or more alerts and 3 minute checks. Email, Telegram and push [21].
- MPAlerts (mpalerts.nl): described as monitoring Marktplaats, 2dehands, Vinted and Facebook Marketplace in one dashboard, with an AI that reads each listing and filters irrelevant results. The site returned HTTP 403 when fetched on 15 September 2026, so this description comes from a competitor's comparison page and search listings, not from the vendor's own page [21][22].
- Marktplaats Scanner (mpscanner.nl, marktplaatsscanner.nl): new listing and price drop alerts via push, Telegram, Discord, Slack or email [23].

**O28.** MarktAlert's own comparison page claims the native Marktplaats saved search notification is at most a once daily summary [21]. This is a competitor's characterisation of a rival's product and should be verified directly before it is repeated.

**O29.** Brenger transports large second-hand items in the Netherlands and Belgium, and is integrated with Vinted and Whoppah. Stated limits: maximum 400 x 180 x 160 cm per item, insurance to €250 included, extra cover to €1,500 available at booking, typical delivery in 3 to 7 working days [24].

---

## 6. Observations: four other markets

### United States

**O30.** Facebook Marketplace operates without seller vetting and with low-cost account creation. Security vendors and consumer press document non-delivery, counterfeit goods, overpayment scams and fake payment confirmations as the common patterns, and cite the FTC ranking shopping scams as the most reported category of social media fraud [43]. Vendor blogs are an interested source; the FTC categorisation is the part worth relying on.

**O31.** OfferUp offers identity verification (TruYou), profile ratings, in-app messaging, suggested public meetup locations, and a listing flow described as under a minute. Mercari offers in-app payment, platform shipping labels and visible ratings. A comparison source ranks Mercari first and OfferUp second on buyer protection among US platforms [44]. This source is a commercial blog and the ranking is an opinion.

**O32.** Whatnot, a live auction platform, reports global GMV above $8 billion in 2025, more than doubling year over year, and over 20 million new accounts in the year [33]. A separate analysis gives above $6 billion for the same year [34]. Both figures originate with the company. The discrepancy is unresolved. Whatnot raised $225 million at an $11.5 billion valuation in October 2025 [35].

**O33.** Reported conversion rates for live shopping of 9% to 30%, against 2% to 3% for standard e-commerce, and returns of about 10% against 30% to 35% for standard fashion e-commerce, come from industry and platform sources [34]. No independent verification was found. Treat as claims, not measurements.

**O34.** Craigslist requires no account to browse, has no ranking algorithm and no seller profile system. Reports of large traffic decline exist but the sources located were low quality and are not cited.

### Germany

**O35.** Kleinanzeigen is described by a portal profile as having around 35 million monthly users, more than 55 million live listings, 110 million monthly sessions and over 480,000 registered commercial sellers with at least one active listing as of Q3 2024. The same source estimates annual revenue at approximately €300 million [31]. The revenue figure is an estimate by a third party. Kleinanzeigen won a UX Design Award in 2025 [32].

**O36.** Kleinanzeigen's Trustpilot complaint themes overlap with Marktplaats' and add one distinct theme: users describe being pushed onto the platform's own shipping after alternatives were removed, and describe buyer protection as paying more for little in return. Account blocks shortly after registration, including for accounts without a German phone number, also appear [30]. L1 applies.

### United Kingdom

**O37.** Reporting on the UK Competition and Markets Authority's analysis puts Vinted at an estimated 50% to 60% of UK consumer-to-consumer online apparel GMV in 2025, against 5% to 10% in 2021. Over the same period eBay is put at 30% to 40% falling to 10% to 20%, and Depop at 10% to 20% falling to 0% to 5% [25].

**O38.** In October 2025 Vinted recorded 30.3 million UK monthly visits against Gumtree's 16.9 million, making it the most visited horizontal marketplace in the UK [26].

**O39.** Vinted reports 2025 group GMV of €10.8 billion, up 47%, revenue of €1.1 billion and net profit of €62 million [27]. Company-reported.

**O40.** Vinted charges no seller fees; buyers pay a protection fee. eBay removed private seller fees in the UK in October 2024 [28].

**O41.** Gumtree has no platform-managed postage. Buyers arrange collection or delivery with the seller, which suits large or heavy items [26].

### Russia

**O42.** Avito operates an escrow-like "Safe Deal": the buyer's funds are held until the item is received and confirmed, with free returns including return postage if the item is unsuitable. Avito Delivery, launched 2018, provides couriers, parcel lockers and pickup points with tracking [36]. The stated intent was to bring in users unwilling to do in-person handovers.

**O43.** Trade reporting states an AI assistant named Avi is to be made available to every Avito user in 2026, and that Avito Services is testing a "neighbours recommend" ranking that surfaces providers rated well by residents of nearby buildings [38]. This rests on a single trade source in Russian. Low confidence.

### China

**O44.** Xianyu (Idle Fish), owned by Alibaba, is reported to have over 600 million registered users and 209 million monthly active users as of March 2025 (QuestMobile), with 43% of users born after 1995 [39][40].

**O45.** Xianyu's structure is community-first: interest and location based groups called fishponds, numbering 1.3 million by 2019, with volunteer moderators and a peer dispute process ("Xianyu Small Court"). Additional layers include hobby circles, hashtag-driven event conversations, location based discovery, celebrity listings, livestreams and auctions [39].

**O46.** Xianyu's trust mechanisms are Alipay escrow, credit ratings, and third party inspection and authentication for high value goods with free mail-in or pickup collection [39].

**O47.** Xianyu launched a services and side-hustle marketplace in 2024; reporting states 9.5 million users earned an average of RMB 3,660 in 2024 [39]. Company-derived.

**O48.** Zhuanzhuan operates a C2B2C model: it takes the item into custody and inspects it. Company material describes three inspection centres (Shenzhen, Chengdu, Qingdao), over 2,000 inspectors and a 66 step standardised inspection with a report, plus warranties [42]. That entry is company-derived and its host was unreachable when checked, so the specific counts are unconfirmed. The model itself is corroborated by trade reporting [37].

**O49.** Zhuanzhuan ended its consumer-to-consumer trading service on 29 September 2025, announced in an open letter dated 22 September 2025. The stated reasons were difficulty resolving transaction disputes and thin margins. C2C was less than 3% of its gross merchandise volume, and the company first reached profitability in 2022 on the inspected C2B2C model [47]. This is a dated, verifiable data point on the cost of running unmediated C2C trade at scale.

**O50.** Aihuishou provides trade-in and cash-for-device services with data wiping and warranty [41]. Both Xianyu and Zhuanzhuan opened physical inspection and recycling shops in 2024 and 2025 [41].

### Dutch channel data, for section 10

**O51.** Reported reach among Dutch internet users: WhatsApp 88.8%, Facebook 69.1%, LinkedIn 76.2%, Instagram approximately 45%, TikTok 5.62 million users aged 18 and over in early 2025 [45]. These come from different instruments within the same compilation and the LinkedIn and Instagram figures are not measured the same way.

**O52.** Expat-facing guides to selling in the Netherlands name the Dutch language and hard bargaining as the main obstacles, and note that items often need reposting before they sell [46]. Secondary and anecdotal.

---

## 7. Interpretation

Clearly separated from the observations. Each inference names what it rests on and what would undermine it.

**I1. Supply is not contestable; sentiment is weak.** Marktplaats' own reported 73% share of online reuse (O3) plus 18.7 million live listings (O4) means no new Dutch marketplace can assemble comparable supply. At the same time the complaint corpus (O10 to O12) is unusually hostile. A product that sits on top of the existing supply is therefore a better bet than one that tries to replace it. Undermined if the 73% figure is materially overstated, which is possible because it is self-reported.

**I2. The industry invests in sellers, not buyers.** eBay's Magical Listing now builds listings from images alone [29]. Vinted, Kleinanzeigen and Marktplaats monetise sellers and payment rails (O6 to O8, O36, O40). Buyer-side tooling is limited to keyword search and sponsored placement. The demand side is therefore comparatively under-served. This is the single inference the whole vindje thesis depends on, and it is not directly measured anywhere in this document.

**I3. Buyer-side search failure is structural, not a quality problem.** O14 to O18 describe properties of the system, not defects that a better ranking model inside Marktplaats would fix. The two largest Dutch second-hand categories are size-constrained (O26), which is where the absence of expressible constraints costs the most. Undermined if buyers mostly search for named products rather than described objects, which has not been measured.

**I4. The absence of search complaints is weak evidence of anything.** O13 is compatible with two explanations: search works well enough, or users abandon the item instead of complaining. Nothing here distinguishes them. This is a question for interviews, not for desk research.

**I5. Willingness to pay for notification speed exists, and the differentiating claim is already taken.** Three services charge for it (O27), one at €6.95 to €10.95 per month. One of them already advertises AI filtering, although that claim could not be read on the vendor's own site (O27). Novelty is therefore unavailable as a differentiator, and measured match quality is what remains.

**I6. Price confidence is an unserved question with a possible data path.** There is no sold-price history (O16) and auction listings corrupt the price signal (O17). Nobody in this market publishes comparables. vindje's daily job already estimates resale values, and listings that disappear from the index are a weak proxy for sales. The proxy is weak: listings are also removed when they expire, are withdrawn, or are relisted. Any valuation built on it must report its own confidence.

**I7. The language barrier is plausible as a segment, and unquantified.** Search requires Dutch keywords (O14), several reviewers report bans on accounts without a Dutch phone number (O10), and expat guides name language as the main obstacle (O52). There is no population estimate, no conversion data, and no evidence that this group will pay. Treat as the weakest of the three focus areas and test cheaply.

**I8. The competitive window is finite but its length is a guess.** Avito is reported to be giving every user an assistant in 2026 (O43, low confidence), and it sits in the same industry as Marktplaats. It is reasonable to expect Marktplaats to ship similar features. No announcement, roadmap or date is available. Any specific figure such as "12 to 18 months" is invented and is removed from this version.

**I9. Custody and logistics solve trust, and both need capital.** Avito holds funds and moves goods (O42). Xianyu authenticates and Zhuanzhuan inspects (O46, O48). These are operational businesses. Zhuanzhuan's decision to close unmediated C2C trade entirely, citing disputes and margins (O49), is the clearest available evidence that the mediated model is what pays. A team of three cannot replicate it, so the trust work available to vindje is limited to signalling risk, not underwriting it.

**I10. Community is the mechanism behind the largest engagement numbers.** Xianyu's 209 million monthly actives sit on 1.3 million interest groups rather than on a search box (O44, O45). Whatnot's reported growth comes from live auctions (O32). Both suggest that for one-of-a-kind goods, discovery formats beat query formats. This is suggestive, not transferable: both operate at a scale and in a culture unlike the Dutch market, and their figures are self-reported.

---

## 8. Twenty five jobs to be done

Stated from the buyer's or seller's position, in the third person. These are candidate jobs derived from the observations above. None has been validated with users.

**Finding an item**

1. A buyer who needs an object with physical constraints (height 1.5 to 2 metres, solid oak, with drawers) wants to state those constraints and see only listings that meet them, instead of opening sixty listings to reject fifty eight.
2. A buyer who does not know the Dutch word for the object wants to search in their own language.
3. A buyer scanning results wants one line per listing stating why it matches and what does not, instead of reading every description.
4. A buyer looking at a listing that omits relevant facts (dimensions, model year, included accessories) wants those facts extracted, or flagged as missing.
5. A buyer looking at an asking price wants to know how it compares with prices for comparable items.
6. A buyer browsing without a specific target wants a feed of relevant items nearby.
7. A buyer waiting for a particular kind of item wants to hear about a match within minutes rather than the next day.
8. A buyer who will want an object for several weeks wants the search to continue without repeating it.
9. A buyer who wants a category rather than a specific listing wants a short ranked shortlist instead of 400 results.
10. A buyer holding four candidates wants them compared on the attributes that decide the purchase.

**Assessing risk**

11. A buyer considering a listing wants an indication of fraud risk based on observable signals.
12. A buyer who receives a payment link, or a request for a one cent verification payment, wants a warning at that moment, since this is the most reported fraud pattern nationally (O19).
13. A buyer arranging a handover with a stranger wants a safer procedure: a public location, what to inspect, what to ask.
14. A buyer of used electronics wants a short model-specific inspection checklist that can be run at the door.
15. A buyer of branded goods wants an assessment of whether the photographs show an original.

**Completing the transaction**

16. A buyer contacting a seller wants a first message in natural Dutch, since response rates matter and the buyer may be competing with local buyers.
17. A buyer negotiating wants an opening offer and a walk-away price grounded in comparable listings.
18. A buyer whose item is 40 km away wants transport options with real prices (O29 shows the options exist).
19. A buyer comparing a near listing with a better distant one wants total cost including transport and time.
20. A buyer who has agreed terms wants the agreed price, time, address and stated condition recorded.

**Selling**

21. A seller clearing out a room wants to know which items are worth listing and which are not.
22. A seller listing an item wants a photograph turned into a Dutch title, description, category, attributes and price.
23. A seller pricing an item wants two numbers: one that sells within a week, one that sells within a month.
24. A seller receiving repetitive questions wants those answered without typing.
25. A seller whose listing has had no contact for ten days wants to know whether to lower the price, replace the photographs or rewrite the title.

**Adjacent, already partly served by `deals.py`**

A resale buyer wants a daily list of underpriced live listings with estimated resale value, margin and confidence.

---

## 9. The three jobs proposed for focus

### Selection

**Jobs 1, 2, 3 and 9: constrained search with a stated reason.** Rests on I3. It is the only candidate where the incumbent's limitation is structural rather than a matter of investment, and it is what the product already does. The immediate work is measurement, not features, because vindje's precision and recall are unknown.

**Jobs 7 and 8: a standing search.** Rests on I5. It is the only candidate with external evidence of willingness to pay in this specific market.

**Job 5, with 17: price comparison.** Rests on I6. It answers a question nothing in the market answers, it reuses existing valuation code, and it produces a data asset that improves with time. It carries the highest risk of being confidently wrong, so it needs an explicit "insufficient data" state.

### Why not the others

Selling tools (21 to 25) are the most invested-in area of the industry (I2) and eBay already ships the core of it [29]. Custody, escrow, inspection and logistics are operational businesses (I9). Community and live formats are associated with the largest engagement numbers observed (I10) but the evidence does not transfer to a market of this size, and they require an existing audience.

### What would change this selection

- If interviews show users mostly search for named products rather than described objects, focus 1 weakens and price comparison becomes the lead.
- If measured precision on constrained searches is low and cannot be raised quickly, the standing search has nothing worth notifying about and the whole selection is premature.
- If the comparables proxy (I6) turns out too noisy to produce a defensible verdict, focus 3 should be dropped rather than shipped with a disclaimer.

---

## 10. Hypotheses

Each hypothesis states a prediction, the measurement, and the result that would falsify it. Thresholds are set to be decidable within weeks at vindje's current traffic, not derived from any benchmark. They are judgement calls and should be read as such.

### 10.1 Product

**H1. Constraint richness predicts engagement.** Searches containing two or more explicit constraints produce more listing views per search than keyword-style searches.
Measure: listing click-through per search, split by constraint count parsed. Falsified if the difference is not positive at a reasonable sample.

**H2. The stated reason increases listing views.** Showing the one line explanation of why a listing matches increases click-through relative to hiding it.
Measure: A/B on the results page. Falsified if the difference is not positive.

**H3. Disclosing the rejected set does not reduce trust.** Showing "43 listings hidden" with grouped reasons does not lower return rate, and may raise it.
Measure: 7 day return rate by arm. Falsified if the disclosure arm returns less.

**H4. A saved search converts one-time users into repeat users.** Users offered a standing search after results create one at a usable rate, and return more often than one-time searchers.
Measure: creation rate at the offer point; 7 day return by cohort. Falsified if creation is rare, set here at under 10%.

**H5. Some users will pay for a standing search.** A minority of active standing-search users will pay a monthly fee in the range already charged in this market (O27).
Measure: paid conversion among users with at least one active search. Falsified if conversion is under 2%.

**H6. A price comparison changes buyer behaviour.** Showing a verdict with the number of comparables changes the rate at which users contact sellers.
Measure: contact clicks by arm, plus one direct question to users who saw it. Note the direction is genuinely uncertain: a well calibrated verdict should also stop some purchases. Falsified as useful only if it moves neither contacts nor stated decisions.

**H7. Non-Dutch language input identifies a distinct, better-retained segment.** Rests on I7, which is the weakest inference here.
Measure: listings viewed per session and 30 day retention, split by input language. Falsified if the two groups behave the same, in which case the expat-first marketing plan is dropped.

**H8. A generated Dutch opening message increases seller contact.** Measure: contact rate by arm. Falsified if not positive.

**H9. Risk signalling can be made accurate enough to show.** A combination of rules and model inspection can flag listings users independently judge suspicious, without flagging clean listings often.
Measure: recall against a user-reported suspicious set, false positive rate against a hand-labelled clean set. Falsified if false positives exceed 20%, at which point the badge should not ship.

**H10. The daily deal list attracts new users who then use the product.** Measure: share of new visitors landing on a finds page, and their standing-search creation rate. Falsified if arriving visitors do not create searches, at which point the page is content, not acquisition.

### 10.2 Marketing in the Netherlands

Context: channel reach in O49, category data in O23, the existing paid competitors in O27, and payment method conventions which are not verified in this document and should be checked before build (iDEAL and Mollie are the assumption, not a finding).

**M1. Dutch long-tail pages built from live listings attract search traffic.** Pages of the form "tweedehands [object] [constraint] in [city]".
Measure: organic sessions and search-to-standing-search conversion from 200 pages at day 90. Falsified below roughly 1,000 sessions per month.

**M2. Valuation queries are a high-intent entry point.** Pages of the form "wat is een [model] waard".
Measure: ranking and conversion for 25 model pages. Falsified if conversion is below the site average, which would mean the traffic is curiosity, not intent.

**M3. International residents are reachable at low cost in English-language communities.** Expat forums, subreddits, community groups and expat media (O50).
Measure: signups and cost per signup. Paired with H7: if H7 is falsified, M3 stops regardless of its own cost per signup.

**M4. WhatsApp outperforms email for delivery of standing search results.** Grounded in reach (O51).
Measure: open and click rate by channel. Falsified if WhatsApp does not exceed email materially. Note WhatsApp Business API template approval takes time and has cost per message, which changes the economics of frequent alerts.

**M5. Category-intent paid search can acquire users below the target cost.** Bidding on category and object queries, not on the incumbent's brand.
Measure: cost per created standing search on a fixed €500 budget. Falsified above €3 per created search.

**M6. Hobby communities convert better than broad social channels.** Cycling, audio, photography, and similar forums and marketplaces.
Measure: signups and 30 day retention by source. Falsified if retention is no better than paid traffic.

**M7. Short video built from the daily finds is a viable acquisition channel.** The material is produced daily already.
Measure: cost per signup at 20 clips. Falsified if no clip in 20 exceeds a modest view threshold, which would indicate the format does not work for this product rather than that the content is wrong.

**M8. Second-hand demand is seasonal in ways that can be planned for.** Near term candidates are the December gifting period and the winter months for indoor goods; April brings King's Day, which the sources describe as a nationwide open-air market [46].
Measure: signups in campaign weeks against baseline. This is the weakest hypothesis in the set, because vindje has no seasonal data of its own and the claim rests on one secondary source.

**M9. Shared search snapshots produce new visitors.** The share link already exists.
Measure: new visitors per shared search, and their conversion. Falsified if shares bring under 0.1 new visitors each.

**M10. Trade press coverage produces retained users, not just traffic.** Measure: 30 day retention of the cohort arriving from any press pickup, compared with organic. Falsified if retention is at or near zero, which would indicate that press outreach is not worth further time.

---

## 11. Four week plan

**Team:** one designer, one engineer, one marketer, plus Pavel on prioritisation.

**Primary metric:** weekly retained users with a standing search, defined as users with at least one active standing search who opened a result in the last 7 days.

**Targets.** These are planning numbers chosen to be large enough to distinguish a signal from noise and small enough to be reachable. They are not forecasts.

| Quantity | Target at day 30 |
|---|---|
| Weekly retained users with a standing search | 250 |
| Standing searches created | 1,000 |
| Paying users | 40 |
| Precision on the internal evaluation set | 85% |
| Recall on the internal evaluation set | 80% |
| Median delay from listing publication to alert | under 8 minutes |

Forty paying users at a €7 monthly price is €280 per month. That is not a business result. It is the smallest sample that makes H5 decidable.

**Standing rules.** Every feature ships with instrumentation or it does not ship. Five user interviews per week, recorded, at least one watched by everyone. One demo per week using real data.

### Week 1. Measurement before building

The plan's premise is that match quality is adequate. That has never been measured (L4), so it is measured first.

*Engineer.* Define and implement the event schema in PostHog: search started, wish parsed (with constraint count and input language), results rendered (matched and hidden counts), listing opened, reason expanded, share copied, standing search created. Build an evaluation set: 50 wishes across bicycles, furniture, electronics, baby goods and clothing, each with hand-labelled expected matches against a frozen listing snapshot, and a command that reports precision, recall and cost per search. Then fix what the evaluation exposes, starting with constraints dropped during parsing and listings rejected for missing data rather than for failing a constraint.

*Designer.* Five buyer interviews, at least two with non-Dutch speakers, testing I3 and I4 directly. Rebuild the result row so the reason line is the primary element, mobile first. Design the hidden-listings disclosure for H3, and the empty state for a search with no genuine matches.

*Marketer.* Build the Dutch keyword map for the three focus jobs with volumes, producing a ranked list of 200 page targets for M1 and 25 for M2. Set up analytics and Search Console. Recruit interview participants. Open the expat and hobby community conversations by hand for M3 and M6.

*Gate.* Baseline precision and recall known. If precision is below 70%, week 2 becomes quality work and the standing search moves to week 3. That trade-off is stated openly rather than absorbed.

### Week 2. Standing searches

*Engineer.* Storage for a standing search: wish, parsed query, constraints, radius, postcode, channel, cadence, seen listing ids, reusing the existing de-duplication for relisted items. A runner at 5 to 15 minute intervals with caching, jitter, rate limiting and back-off, applying the model filter only to new listings so cost per search stays near zero. Web push and email delivery. WhatsApp behind a flag, with the Business API approval started on day one because of the lead time noted in M4. A per-search cost and latency dashboard.

*Designer.* Creation in one step from a finished search. The notification itself, which is the product surface for this job and has to be readable at a glance. A management list with last result, hidden count, pause and delete.

*Marketer.* First 60 pages for M1 and 10 for M2. First 10 short videos for M7. Community posts for M3 and M6.

*Gate.* 100 standing searches created by real users, median delay under 15 minutes, H4 measurable.

### Week 3. Price comparison and payment

*Engineer.* Persist observed listings from the daily job with price, category, attributes, first seen and last seen dates, which starts the comparables corpus described in I6. A valuation endpoint reusing the `deals.py` prompt, returning a verdict, a range, a comparable count and a confidence level, and refusing to answer when the comparable set is thin. Payment for a paid tier, with free limited to 2 standing searches at 15 minutes.

*Designer.* The price verdict component in the result row and the detail view, with comparables visible on demand. The paywall, stating the price plainly. One pass over the shared snapshot page for M9.

*Marketer.* 25 valuation pages live for M2. First organic reading for M1. The €500 paid test for M5, measured on created searches. Draft the seasonal campaign for M8 and the press list for M10 without sending.

*Gate.* H6 running. First paying user. Valuation returns "insufficient data" on a known-thin category, verified by hand.

### Week 4. Reliability, risk signalling, and a second source

*Engineer.* Alerting on failed runs, model fallbacks and empty result streaks, because a standing search that silently stops is worse than none. Risk signalling for H9, shipped quietly and measured for false positives before it becomes visible. 2dehands as a second source behind a flag, to test whether coverage changes perceived usefulness, since all three competitors are multi-source (O27).

*Designer.* Fix the two largest drop-offs the funnel shows. Landing page using a real search as the main image. Record the design tokens in the repository.

*Marketer.* Press outreach for M10, measured on 30 day retention. Referral on the shared snapshot for M9. One page month review: cost per signup and retention by channel, with a recommendation.

*Gate.* The six numbers in the target table, reported as measured, including misses.

---

## 12. Risks and open questions

**R1. Platform dependency.** vindje reads an undocumented Marktplaats search endpoint, and standing searches multiply request volume. Mitigation: conservative polling, caching, jitter, a non-abusive request profile, the existing degradation to plain search, and a second source so a single block is not fatal. Open question: what request rate is acceptable. Public sources do not answer this, so the only available course is to stay conservative.

**R2. Terms of service.** Whether vindje's use is compatible with Marktplaats' terms has not been assessed in this document. It should be, by someone qualified, before the standing search runs at scale.

**R3. Incumbent feature risk.** I8, with the explicit note that no date is known.

**R4. Unit economics.** Frequent checks on many searches are a recurring model cost. Filter only new listings, cache, and keep cost per search per month visible from week 2.

**R5. Confidently wrong output.** A miscalibrated price verdict or a jumpy risk badge costs more than silence, because both claim authority. Both need an explicit refusal state, and H9's falsification threshold exists for this reason.

**R6. Data protection.** Stored searches, notifications and any WhatsApp messaging require a lawful basis, consent where applicable, and retention limits under the AVG. Not analysed here.

**R7. Unverified figures carried into decisions.** Specifically O8 (buyer protection cost, primary page unavailable), O28 (competitor's claim about a rival's notification speed), O43 (single-source assistant claim), and the iDEAL and Mollie assumption in section 10.2. Each should be checked before it appears in anything external.

---

## 13. Sources

Every URL below was requested on 15 September 2026. Of 47 URLs, 40 returned HTTP 200. Six return a bot challenge or 403 to an automated request and open normally in a browser, and one host was unreachable from this network. Each is annotated. Quality labels: **[company]** self-published by the subject, **[official]** government or regulator, **[press]** trade or general press, **[secondary]** aggregator, blog or vendor comparison, **[review]** self-selected user reviews.

1. Marktplaats.nl, Wikipedia. [secondary] https://en.wikipedia.org/wiki/Marktplaats.nl
2. Permira and Blackstone announce voluntary offer for Adevinta shares, Adevinta press release. [company] https://adevinta.com/press-releases/permira-and-blackstone-announce-voluntary-offer-for-all-outstanding-ordinary-class-a-shares-in-adevinta-at-nok-115-per-share/
3. Blackstone and Permira lead $13 billion bid for Adevinta, Reuters via Yahoo Finance. [press] https://ca.finance.yahoo.com/news/blackstone-permira-buy-adevinta-13-165440995.html
4. Adevinta takeover to complete by June 2024, Online Marketplaces. [press] https://www.onlinemarketplaces.com/articles/adevinta-takeover-to-complete-by-june-2024/
5. The Marktplaats Effect, Marktplaats with Vaayu, 2023 data. [company] https://www.marktplaats.nl/m/the-marktplaats-effect/
6. marktplaats.nl traffic analytics, Similarweb. [secondary] Bot challenge on automated request; opens in a browser. https://www.similarweb.com/website/marktplaats.nl/
7. Top online marketplaces in the Netherlands 2026, WMTips. [secondary] Returns 403 to automated requests; opens in a browser. https://www.wmtips.com/technologies/marketplaces/country/nl/
8. Netherlands leading online marketplaces by visit share 2023, Statista. [secondary] https://www.statista.com/statistics/1256594/netherlands-leading-online-marketplaces-visits/
9. Marktplaats reviews, Trustpilot, accessed 15 September 2026. [review] Returns 403 to automated requests; opens in a browser. https://www.trustpilot.com/review/www.marktplaats.nl
10. Problemen met marktplaats.nl, AVROTROS Radar forum. [review] https://radar-forum.avrotros.nl/webwinkels-f69/problemen-met-marktplaats-nl-t17863.html
11. Marktplaats app listings and reviews, Google Play and App Store. [review] https://play.google.com/store/apps/details?id=nl.marktplaats.android
12. Marktplaats.nl verhoogt prijzen in zakelijke rubrieken, Emerce. [press] https://www.emerce.nl/nieuws/marktplaats-nl-verhoogt-prijzen-zakelijke-rubrieken
13. Marktplaats kopersbescherming, hoe werkt het en wat kost het, MarktAlert blog. [secondary, and a competitor] https://marktalert.nl/blog/marktplaats-kopersbescherming-hoe-werkt-het
14. Kosten kopersbescherming, Marktplaats help. [company] The URL responds, but the page content did not render when fetched on 15 September 2026, which is why O8 is marked unverified. https://help.marktplaats.nl/s/article/kosten-kopersbescherming
15. Regels over het gebruik van zoekwoorden in advertenties, Marktplaats help. [company] https://help.marktplaats.nl/s/article/regels-over-het-gebruik-van-zoekwoorden-in-advertenties
16. Online oplichting en fraude, in Online veiligheid en criminaliteit 2024, CBS. [official] https://www.cbs.nl/nl-nl/longread/rapportages/2025/online-veiligheid-en-criminaliteit-2024/4-online-oplichting-en-fraude
17. Meer mensen slachtoffer van online criminaliteit in 2024, CBS. [official] https://www.cbs.nl/nl-nl/nieuws/2025/16/meer-mensen-slachtoffer-van-online-criminaliteit-in-2024
18. Wat vinden consumenten van tweedehands spullen, Circulair Ambachtscentrum, reporting Consumentenonderzoek Potentie Tweedehands Spullen 2025. [secondary] https://circulairambachtscentrum.nl/nieuws/2025/vinden-consumenten-tweedehands-spullen/
19. 32% van de Nederlandse consumenten koopt nu meer tweedehands producten, Duurzaam Ondernemen. [secondary] https://www.duurzaam-ondernemen.nl/32-van-de-nederlandse-consumenten-koopt-nu-meer-tweedehands-producten-dan-5-jaar-geleden/
20. Second-hand goods retailing in the Netherlands, IBISWorld 2025. [secondary] https://www.ibisworld.com/netherlands/industry/second-hand-goods-retailing/200596/
21. MarktAlert, pricing and tool comparison. [company, and a competitor] https://marktalert.nl/ and https://marktalert.nl/vergelijking
22. MPAlerts. [company] Returned HTTP 403 on 15 September 2026. https://mpalerts.nl/
23. Marktplaats Scanner. [company] https://www.marktplaatsscanner.com/
24. Delivery service for large Vinted purchases, and support articles, Brenger. [company] https://www.brenger.nl/en-nl/vinted/
25. CMA puts Vinted at 50 to 60% of UK C2C apparel GMV, Value Added Resource. [press, reporting a regulator] https://www.valueaddedresource.net/cma-vinted-leads-uk-apparel-gmv/
26. Vinted overtakes Gumtree to become the UK's most visited secondhand marketplace, AIM Group. [press] Bot challenge on automated request; opens in a browser. https://aimgroup.com/2025/11/26/vinted-overtakes-gumtree-to-become-the-u-k-s-largest-secondhand-marketplace/
27. Financial results 2025, Vinted. [company] https://company.vinted.com/newsroom/financial-results-2025
28. eBay removes UK seller fees, TechCrunch. [press] https://techcrunch.com/2024/10/01/ebay-removes-uk-seller-fees-to-counter-new-wave-of-marketplace-startups
29. Magical Listing revisited, has eBay closed the AI gap, Value Added Resource. [press] https://www.valueaddedresource.net/ebay-ai-magical-listing-revisited/
30. Kleinanzeigen reviews, Trustpilot. [review] Returns 403 to automated requests; opens in a browser. https://www.trustpilot.com/review/kleinanzeigen.de
31. Kleinanzeigen portal profile, Coraly GPPI 2026. [secondary, revenue is an estimate] https://coraly.ai/gppi/portals/kleinanzeigen-de
32. Kleinanzeigen, UX Design Awards 2025. [secondary] https://ux-design-awards.com/winners/2025-2-kleinanzeigen
33. Whatnot's global GMV doubles year over year to reach $8 billion in 2025, Ebrun. [press, reporting company figures] https://english.ebrun.com/20260211/640428.shtml
34. Whatnot, live shopping finally works, Ringing the Bell. [secondary, gives $6bn and the conversion figures] https://ringingthebell.substack.com/p/whatnot-live-shopping-finally-works
35. Whatnot secures $11.5 billion valuation, Business of Fashion. [press] Returns 403 to automated requests; opens in a browser. https://www.businessoffashion.com/news/retail/whatnot-secures-115-billion-valuation/
36. Avito delivery and order tracking, Ship24, and Avito Delivery product page, TAdviser. [secondary] https://www.ship24.com/shops/avito-tracking and https://tadviser.com/index.php/Product:Avito_Delivery
37. Second time a charm for used gadgets, China Daily. [press] https://www.chinadaily.com.cn/a/202210/13/WS63474d16a310fd2b29e7c1f3.html
38. Avito Services introduces neighbour recommendations, www1.ru. [press, single source, low confidence] https://www1.ru/en/news/2026/06/22/sarafannoe-radio-vyxodit-v-onlain-avito-uslugi-nasli-novyi-sposob-iskat-masterov.html
39. Alibaba's Xianyu, more than just a second-hand marketplace, ChinaTalk. [secondary] https://www.chinatalk.nl/alibabas-xianyu-more-than-just-a-second-hand-marketplace/
40. Alibaba's Xianyu swims a different course, TechBuzz China. [secondary] https://techbuzzchina.substack.com/p/alibabas-xianyu-idle-fsh-swims-a
41. Young consumers drive second-hand e-commerce in China, Daxue Consulting. [secondary] https://daxueconsulting.com/secondhand-market-in-china/
42. Zhuanzhuan, Baidu Baike. [company-derived] Host unreachable from this network on 15 September 2026, so the inspection counts in O48 are unconfirmed. https://baike.baidu.com/en/item/Zhuanzhuan/60216
43. Facebook Marketplace scams, NordPass, citing FTC data on social media fraud reports. [secondary, vendor] https://nordpass.com/blog/facebook-marketplace-scams/
44. Mercari vs OfferUp, IdeaUsher. [secondary, vendor blog] https://ideausher.com/blog/mercari-vs-offerup-which-marketplace-model-is-better/
45. Digital 2025 Netherlands, DataReportal. [secondary] https://datareportal.com/reports/digital-2025-netherlands
46. Where to sell your stuff in the Netherlands, DutchReview. [secondary] https://dutchreview.com/expat/selling-your-stuff-in-the-netherlands/
47. Chinese used goods site Zhuanzhuan to close C2C market due to disputes, profit margin, Yicai Global. [press] https://www.yicaiglobal.com/news/chinese-used-goods-site-zhuanzhuan-to-close-c2c-market-due-to-disputes-profit-margin

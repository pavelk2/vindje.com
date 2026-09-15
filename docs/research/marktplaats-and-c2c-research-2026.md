# Buying second hand in the Netherlands: what is broken, what wins elsewhere, and what vindje should build next

Research and plan, September 2026. Written for the vindje team (product, design, engineering, marketing).

---

## 0. What this document is

A deep read on Marktplaats (how people actually use it and what they hate about it), a scan of the best buy and sell experiences in the USA, Germany, UK, Russia and China, and then the part that matters: 25 jobs to be done, the three we should own, 20 hypotheses, and a concrete one month plan for a designer, an engineer and a marketer.

vindje today is one Python file that does three things: it turns a wish written in any language into a real Marktplaats search, it reads every returned listing with an LLM and keeps only the ones that satisfy the stated constraints (with a one line reason each), and every morning it hunts nationwide for underpriced items and puts them on the homepage. There is also a share link per search, a search history, an ideas board, and an MCP server so Claude can do the same thing inside a chat.

That is a sharper starting position than it looks, for a reason the research makes obvious: everyone in this market is investing in sellers, and nobody is selling buyers a better way to find.

---

## 1. Method and confidence

Desk research, September 2026: Marktplaats' own help pages and product pages, Trustpilot and App Store review bodies, the AVROTROS Radar consumer forum, Dutch consumer research on second hand behaviour, Similarweb and Statista traffic and share data, the UK CMA's read on C2C apparel, Vinted's 2025 financials, Adevinta and Kleinanzeigen material, Avito product coverage, and Chinese platform coverage for Xianyu, Zhuanzhuan and Aihuishou.

Confidence notes, stated up front so nobody over-trusts a number:

- Review sites are selection biased. A 1.2 Trustpilot score for a platform with tens of millions of monthly visits does not mean 78% of users are furious. It means the people motivated to write are furious, and it tells you which failure modes generate the most emotion. That is still useful; treat it as a map of pain, not a satisfaction measurement.
- Traffic and user figures come from different methodologies (Similarweb visits, Statista survey panels, company statements) and do not reconcile cleanly. Ranges are given where they differ.
- Nothing here substitutes for 20 user interviews. Week one of the plan below puts that in the calendar.

---

## 2. Marktplaats: the incumbent

### 2.1 Scale and position

- Founded May 1999 by René van Mullem. Sold to eBay in November 2004 for €225 million, and moved to Adevinta in June 2021 as part of eBay's $9.2 billion classifieds divestment. Adevinta was itself taken private by a Permira and Blackstone led consortium, so Marktplaats now sits inside a private equity owned portfolio. That ownership matters for predicting behaviour: PE owned classifieds monetise harder, and they do it on the seller and the payment rails.
- Roughly 8 to 10.3 million monthly active users or unique visitors depending on the source, around 48 million monthly visits (October 2025), approximately 350,000 new listings per day, and about 18.7 million live advertisements at any moment.
- 7.6% share of all Dutch marketplace activity (bol 46.1%, Amazon 30.4%), but 73% of the online reuse market and about 29% of the total reuse market including physical thrift. In second hand, Marktplaats is not a competitor, it is the substrate.
- Second in Dutch retail web traffic after bol.com.

Read that as: supply is not contestable. 18.7 million live ads is a moat nobody in the Netherlands is going to rebuild. Any Dutch second hand product decision that starts with "we will build a marketplace" is starting with a fundraising problem, not a product.

### 2.2 How Marktplaats makes money

- Listing fees by category. Free in most consumer categories, paid in premium ones (cars, holiday rentals, water sports, services, business goods), historically €9 to €25 per listing. On 1 January 2025 the cars tariff went from €24 to €34.99, a 46% rise, and holiday rentals rose about 50%.
- Admarkt and Marktplaats Pro: paid placement and visibility for commercial sellers.
- Kopersbescherming (buyer protection): the buyer pays roughly 5% of the asking price, minimum €0.59, maximum €20, plus €0.40 service cost per payment request. Money sits with Online Payment Platform, and there is a 48 hour inspection window after delivery before the seller is paid automatically.
- Direct Kopen (buy now) as the managed checkout path.

Two things follow. First, the fee incidence in the Netherlands is on the buyer, not the seller, which is the opposite of what you would guess and the same direction Vinted took. Second, Marktplaats' incentives are to push volume into the managed payment and shipping rails, because that is where the take rate lives. Search relevance does not earn them anything. Sponsored placement does.

### 2.3 What users complain about

From Trustpilot (1.2 out of 5 across roughly 4,379 reviews, 78% one star), App Store and Play reviews, the Radar consumer forum, and Dutch consumer coverage. Grouped and ranked by how often and how loudly it shows up:

1. **Fraud volume and the feeling that nobody is stopping it.** Purchase fraud is the most reported form of online fraud in the Netherlands. Published figures put damage from purchase fraud at around €247 million in 2023 with only about a tenth reimbursed, and Dutch victim support organisations run dedicated Marktplaats fraud pages. The dominant mechanic is the fake payment link: "pay me one cent to verify", which is a phishing page. Reviewers report scam listings staying live after reporting.
2. **Buyer protection that does not feel like protection.** Mandatory fee whether or not the transaction goes well, return shipping not reimbursed even on counterfeit goods, and disputes decided in the seller's favour. The recurring phrasing is that the platform earns either way.
3. **No human support.** A chatbot with no path to a person, no published address for a formal complaint, appeals that go unanswered.
4. **Account bans out of nowhere.** Suspensions on day one for "suspicious activity", frequently for accounts without a Dutch phone number, with no working recovery path. This one hits expats hardest.
5. **Moderation inconsistency.** The same listing removed repeatedly over the €200 threshold rule, each time acknowledged as a mistake. Users perceive uneven enforcement between private and commercial advertisers.
6. **Commercialisation of the feed.** Private sellers say they are crowded out by professional ones, that you cannot tell a business listing from a private one at a glance, and that sponsored slots and ad units interrupt browsing. One review reads: no longer a treasure trove, now a soulless e-commerce wasteland. Play Store reviews complain that ad units swallow swipes and open on tap.
7. **App quality.** Hangs when publishing a listing, buggy and inconsistent, coasting on market position.
8. **Fees rising.** The 2025 category increases produced public defections in cars, where sellers listed the free alternatives they moved to by name.

### 2.4 What almost nobody complains about, and why that is the finding

Search quality barely appears in review sites, and that is not because it is good. It is because users do not report a bad search, they just give up on the item. The structural facts:

- Search is keyword based and Dutch. You need the Dutch noun a Dutch seller would have typed. There is no semantic understanding of "wooden closet, 1.5 to 2 metres, with drawers and a hanging rail".
- Sellers stuff keywords deliberately. Marktplaats publishes rules about keyword use in listings, which tells you how much of it there is.
- Structured attributes are optional and unreliable, so filters cannot express the constraints that actually decide a purchase: dimensions, whether the charger is included, whether it is the real thing or a "stijl van" lookalike, whether it fits in a Fiat 500.
- There is no sold price history, unlike eBay. Nothing on the page answers "is €180 a good price for this bike".
- Bidding listings show an opening bid as if it were a price, which poisons price comparison. vindje already has an exclude-bids flag, which was the right instinct.
- The good listings are gone in hours, and the platform's own saved search notification is, per the third party comparisons, as slow as a once daily digest.

That is the whole vindje thesis, stated in the incumbent's own constraints.

---

## 3. The Dutch demand side

From the 2025 Consumentenonderzoek Potentie Tweedehands Spullen and adjacent data:

- 61% of Dutch consumers bought something second hand in the past year. Only 13% never have.
- Top categories: bicycles 49%, books 47%, furniture 42%. 39% would buy phones, TVs or laptops second hand.
- Preferred channels: kringloopwinkels 63%, Marktplaats 60%. Thrift shops score highest on positive experience at 66%, which is a quiet indictment of the online experience.
- 32% buy more second hand than five years ago. Second hand retail revenue is around €11.2 billion in 2025, growing slowly.

Two implications. Bicycles and furniture are the two biggest Dutch second hand categories and both are physically constrained purchases (size, frame height, does it fit through the door, can I transport it), which is exactly where keyword search fails hardest and where vindje's constraint parsing is worth the most. And the fact that a dusty warehouse outscores the online channel on experience means the ceiling here is not "slightly better search", it is "make buying second hand feel good".

---

## 4. There is already a paid layer on top of Marktplaats

This is the single most commercially useful thing in the research, and it was not in anyone's slide deck.

A small Dutch market exists for "tell me about the listing before anyone else":

- **MarktAlert** (marktalert.nl), iOS and Android. Monitors Marktplaats, 2dehands and Vinted. Free tier: 2 alerts, 15 minute checks. Plus: €6.95 per month, 5 alerts, 5 minute checks. PRO: €10.95 per month, 10 or more alerts, 3 minute checks. Email, Telegram and push.
- **MPAlerts** (mpalerts.nl). Marktplaats, 2dehands, Vinted and Facebook Marketplace in one dashboard, and it already advertises an AI that reads each listing and filters out irrelevant results.
- **Marktplaats Scanner** (mpscanner.nl / marktplaatsscanner.nl). New listing and price drop alerts via push, Telegram, Discord, Slack or email.

What this tells us:

1. Dutch consumers will pay €7 to €11 a month for speed on a free platform. The willingness to pay question is answered.
2. The AI filtering wedge is already being claimed. vindje is not early to the idea, it is early to doing it well. The differentiator has to be match quality and the explanation, not the existence of AI.
3. All of them sell to the same person: the hobbyist and the flipper, who runs many searches. None of them serve the one time buyer who needs a specific wardrobe this month, which is a far larger population and the one that generates word of mouth.
4. Multi source (Marktplaats plus 2dehands plus Vinted plus Facebook Marketplace) is table stakes in this category, and vindje is single source today.

---

## 5. Global scan: what the best buy and sell experiences actually built

### 5.1 USA: distribution, verification, and turning discovery into entertainment

- **Facebook Marketplace** won on distribution alone. No new account, a real identity attached, and every listing one degree from a social graph. Its weakness is the same thing: no vetting, trivial fake profiles, and shopping scams are the most reported social media fraud category. Buyers deal with it because the supply is there.
- **OfferUp** made trust a product: TruYou identity verification, profile ratings, in-app messaging, suggested safe public meetup spots, and a list-in-under-a-minute photo flow.
- **Mercari** made the transaction managed end to end: in-app payments, shipping labels from day one, ratings visible before you buy. Buyer protection is the best in the US set.
- **Craigslist** is instructive in the opposite direction. No account needed to browse, no algorithm, no feed, no seller brand to build. Post, wait, answer, meet, done. People who stay are staying for the absence of product. Traffic has fallen roughly 85% from its peak, so this is not a strategy, but the lesson stands: every mechanic you add has to earn its friction.
- **Whatnot** is the most interesting data point in the whole scan. Live auction commerce, GMV doubling year over year to roughly $8 billion in 2025, the number one shopping app in the US and UK that year. Live shopping converts at 9% to 30% against 2% to 3% for standard e-commerce, and fashion returns run 10% against 30% to 35%. 42% of US shoppers say they do it because it is fun. Second hand supply is one of a kind, so urgency and a human voice work better on it than a grid of thumbnails does.

**Takeaway.** Trust can be manufactured with verification and managed payments. Discovery can be made enjoyable instead of merely efficient. Both are being monetised. Neither is being done in the Netherlands.

### 5.2 Germany: the rails play, and its cost

- **Kleinanzeigen** is Germany's dominant generalist: around 35 million monthly users, 55 million live listings, 110 million monthly sessions, 480,000+ commercial sellers, roughly €300 million annual revenue, and a 2025 UX Design Award. It is what Marktplaats would look like with more design investment.
- Its user complaints are the same family as Marktplaats' and sharper on one point: users describe being forced onto the platform's own shipping (DHL only after alternatives were removed) and its own payment with buyer protection, and they experience protection as "you just pay more". Plus instant bans on accounts without a German phone number, and no complaint tracking.

**Takeaway.** Owning the shipping and payment rails is the standard classifieds monetisation endgame, it works financially, and it reliably burns goodwill. Marktplaats is walking the same path. That goodwill is the opening for a third party that is unambiguously on the buyer's side.

### 5.3 UK: the fee incidence lesson and the vertical lesson

- **Vinted** took an estimated 50% to 60% of UK C2C apparel GMV in 2025, up from 5% to 10% in 2021. Over the same period eBay fell from 30% to 40% down to 10% to 20%, and Depop from 10% to 20% down to 0% to 5%. In October 2025 Vinted did 30.3 million UK monthly visits against Gumtree's 16.9 million, making it the most visited horizontal marketplace in the country. Group wide, 2025 GMV was €10.8 billion (up 47%), revenue €1.1 billion, net profit €62 million.
- The mechanism: no seller fees, buyer pays a protection fee, and a social, scrollable, single category experience where every visitor is already in second hand clothing mode. eBay responded by removing UK private seller fees in October 2024, which is what a defensive move looks like.
- **Gumtree** kept exactly one structural advantage: large, heavy, awkward items that cannot be posted. Local collection is not a legacy feature, it is a defensible niche.

**Takeaway.** Free to sell, buyer pays, plus a focused category, beat a horizontal generalist with better brand recognition in four years. And the one place a local classifieds site cannot be displaced is bulky goods, which in the Netherlands means furniture and bicycles.

### 5.4 Russia: escrow plus logistics, then an AI assistant

- **Avito** built Safe Deal: the buyer's money is reserved on their card and held in an escrow account until they have the item and confirm it, with free returns including return shipping if it is not right. Avito Delivery (from 2018) added couriers, parcel lockers and pickup points with real time tracking, which is what let strangers in different cities trade at all.
- The stated purpose was to bring in people who would never do a doorstep handover with a stranger. That population is large everywhere.
- Now: an AI assistant, Avi, rolling out to every Avito user in 2026, and a "neighbours recommend" mechanic in services that ranks providers already rated well by people in nearby buildings.

**Takeaway.** Two things. Escrow plus logistics converts the scared majority, which is the biggest untapped segment in any C2C market. And the incumbents are shipping AI assistants now. Marktplaats will do this. The window to own the association between "AI helps me buy well" and a Dutch brand is measured in quarters, not years.

### 5.5 China: take custody of the item, and make the market a place

- **Xianyu (Idle Fish)**, Alibaba: 600 million registered users, 209 million MAU as of March 2025, and 43% of users born after 1995. Trust comes from Alipay escrow, credit ratings, third party inspection and authentication on high value goods with free mail-in or pickup, and a peer dispute mechanism called the Xianyu Small Court.
- The engagement engine is not search. It is 1.3 million "fishponds": interest and neighbourhood communities where people trade, talk, and post. Layered on top: hobby circles, hashtag driven event conversations, location based discovery, celebrity closets, livestreams and auctions. Plus a side hustle services marketplace where 9.5 million users earned an average of RMB 3,660 in 2024. Registered to active ratio shows a large population that shows up for the community without transacting.
- **Zhuanzhuan** (Tencent backed) answered information asymmetry with C2B2C: it takes the phone or laptop into custody, runs a 66 step standardised inspection through three inspection centres and more than 2,000 inspectors, issues a report, and offers a warranty. Xianyu and Zhuanzhuan both opened physical recycle and inspection shops in 2024 and 2025.
- **Aihuishou** does the other half: instant trade-in and cash for used electronics, with data wiping and warranty attached.

**Takeaway.** China concluded that in second hand, trust is not a UI problem, it is an operations problem, and the answer is to touch the item. That is capital intensive and not ours to build. The second conclusion is free and we are ignoring it: people come back for a place and a community, not for a search box. Xianyu has 209 million monthly actives on a product where the transaction is almost a side effect.

---

## 6. Key learnings

1. **Supply is settled, affection is not.** Marktplaats holds 73% of Dutch online reuse and a 1.2 Trustpilot score. An unloved monopoly with unmatchable supply is the perfect host for a layer that sits on top of it. Do not build a marketplace.
2. **Everyone is building for sellers.** eBay's Magical Listing now builds listings autonomously from photos. Vinted, Kleinanzeigen and Marktplaats all monetise sellers and payment rails. Buyers get a keyword box and sponsored slots. The demand side is the underserved side of this entire industry.
3. **The three winning mechanics elsewhere are custody, logistics and entertainment.** Escrow and inspection (Avito, Xianyu, Zhuanzhuan), delivery for C2C including bulky items (Avito, Vinted Go, Brenger), and discovery as something you enjoy (Xianyu ponds, Whatnot live). Two of the three are capital intensive. The third is software.
4. **Speed already sells in the Netherlands for €7 to €11 a month.** MarktAlert, MPAlerts and Marktplaats Scanner have validated the price point and the buyer. One of them already claims AI filtering. Our edge is quality and explanation, not novelty.
5. **Price confidence is an open hole.** No sold price history on Marktplaats, and bidding ads show opening bids as prices. "Is this a good price" is the most common unanswered question in second hand buying, and vindje's deal hunt already contains the valuation machinery to answer it.
6. **Language is a real wedge, not a nice-to-have.** Search requires the Dutch noun. Expat guides name the language barrier and hard Dutch bargaining as the two main obstacles, and bans hit accounts without a Dutch phone number. vindje works in any language on day one, and internationals cluster in exactly the four cities where supply density is highest.
7. **Fee incidence and category focus beat brand.** Vinted went from 5% to 60% of UK C2C apparel in four years on free-to-sell plus one category. Horizontal generalists lose to focused experiences.
8. **Trust is the loudest complaint and the cheapest partial win.** We cannot run escrow. We can flag the payment link scam pattern, stock photos, too-cheap outliers and fresh accounts, in the moment, for free.
9. **Bulky goods are structurally local, and that is where the money and the pain are.** Furniture (42%) and bicycles (49%) top Dutch second hand purchasing. Brenger already moves Vinted and Whoppah items in the Netherlands, insured to €250 by default and €1,500 on request. Landed cost, not sticker price, is what buyers actually decide on, and nobody shows it.
10. **The window is 12 to 18 months.** Avito ships an assistant to every user in 2026. Marktplaats will follow. After that the question stops being "who has the better AI" and becomes "who has distribution", which we lose. Build the habit and the brand association now.

---

## 7. 25 jobs to be done

Grouped. Written from the buyer's or seller's side, not ours.

**Finding**

1. When I need something with physical constraints (fits this alcove, 1.5 to 2 metres, solid oak, with drawers), I want to describe it the way I would to a friend and see only listings that actually meet them, so I stop opening sixty tabs to reject fifty eight.
2. When I do not know the Dutch word for the thing I want, I want to search in my own language, so 18 million listings are not closed to me.
3. When I scan results, I want one line per listing telling me why it matches and what is off about it, so I do not have to read every description.
4. When a listing is vague, I want the missing facts (dimensions, model year, whether the charger is included) pulled out or asked for, so I do not message five sellers to eliminate four.
5. When I see a price, I want to know whether it is fair against what comparable items actually sold for, so I neither overpay nor scroll past a steal.
6. When I am not looking for anything specific, I want a feed of genuinely interesting things near me, so I find things I would never have searched for.
7. When the right listing appears, I want to know within minutes, so I am not the twelfth message.
8. When I am going to want this thing for weeks, I want the search to keep running without me reopening anything.
9. When I want a category rather than a listing (a road bike, 56cm frame, under €400), I want the best three live options right now, ranked, not 400 results.
10. When I have shortlisted four listings, I want them side by side on the attributes that decide it, so I can choose in two minutes.

**Trust and risk**

11. When I consider a listing, I want a read on scam risk (stock photos, price far below the market, fresh account, payment link language), so I do not lose money.
12. When the seller sends me a payment link or asks for one cent to "verify", I want to be warned right then, in the conversation.
13. When I am about to meet a stranger, I want a safer handover plan: a public place, what to check, what to say, so the meetup is not the risky part.
14. When I buy electronics, I want a two minute doorstep checklist for that exact model (battery health, IMEI, cycle count, accessories), so I can verify before I pay.
15. When I buy something branded, I want a replica read from the photos, so I do not pay for a "stijl van" lookalike.

**Doing the deal**

16. When I am about to message a seller, I want a first message in natural Dutch that actually gets a reply, so I do not lose the item to a faster or more local buyer.
17. When I negotiate, I want an opening number and a walk away number grounded in comparables, so I am not guessing against someone who does this weekly.
18. When the item is 40 kilometres away, I want pickup or transport solved with a real price (van, Brenger, a courier), so distance stops being an automatic no.
19. When I compare a listing 5 km away with a better one 45 km away, I want the true landed cost including fuel, time and transport, so I compare like with like.
20. When we agree, I want the agreement recorded (price, time, address, stated condition), so doorstep price hikes and no-shows become rare.

**Selling**

21. When I clear out a room, I want to know what is worth listing, what should go to the kringloop and what to throw away, so I do not waste an evening on items worth €4.
22. When I list, I want a photo to become a Dutch title, description, category, attributes and price, so listing takes one minute instead of fifteen.
23. When I price, I want two numbers: the one that sells this week, and the one that sells this month.
24. When buyers message, I want the repetitive part answered for me, so I am not typing "ja, nog beschikbaar" fourteen times.
25. When my listing has been dead for ten days, I want to know whether to drop the price, reshoot the photos or rewrite the title, and by how much.

**Flipping (adjacent, already half built)**

Bonus, because deals.py already serves it: when I buy to resell, I want a daily list of underpriced live items with an estimated resale value, a margin and a confidence level, so I work from a list instead of scrolling.

---

## 8. The three jobs to focus on

### Focus 1. Constraint-true search with a stated reason (jobs 1, 2, 3, 9)

*See only what actually matches, and know why in one line.*

This is the only job where the incumbent is structurally unable to compete without rebuilding its core, it is what vindje already does, and it is the reason anyone tries the product once. The work now is not the feature, it is the quality: a measurable match rate, a reason line people trust, and honest handling of the rejected pile ("we hid 43, here is why") so the filtering reads as competence rather than as a black box.

### Focus 2. The standing hunt (jobs 7, 8)

*Tell me first, and only when it really matches.*

This is the retention and revenue job. A one-off search is a tool, a standing hunt is a habit. The Dutch market has already priced it at €7 to €11 a month, and our version is better on the only axis that matters to a buyer: relevance, so the notification is worth opening. Without this, vindje is a clever demo people visit twice.

### Focus 3. Price confidence (jobs 5, 17)

*Is this a good price, yes or no, and here is what it is based on.*

It makes a match actionable, it turns a match into a decision, it is the most searched unanswered question in second hand, we already have the valuation prompt from the deal hunt, and it produces the content engine for organic acquisition (a price page per model). It also compounds: every day of listings we observe makes the comparable set better, which is the closest thing to a data moat available in this business.

### What we are explicitly not doing this quarter

- Selling tools (photo to listing, auto replies, pricing for sellers). Crowded, eBay and Vinted are ahead, Marktplaats will ship it. Revisit in 2027.
- Escrow, payments, inspection, authentication. Capital and operations, not our fight.
- Logistics. Partner with Brenger when it becomes a blocker, do not build it.
- Live commerce and community feeds. The Xianyu and Whatnot lesson is real and comes after we have a retained audience, not before.
- Our own marketplace. Ever.

---

## 9. Ten product hypotheses

Each with the metric that settles it and the number that kills it. Order is roughly the order to run them.

**H1. Constraint richness predicts value.** Users whose wish contains two or more explicit constraints click through to listings at a materially higher rate than keyword-style users.
Measure: listing click-through per search, split by constraint count. Target: 35%+ for constraint-rich searches. Kill below 15%.

**H2. The reason line is the product, not decoration.** Showing the one line "why this matches" increases listing clicks versus hiding it.
Measure: A/B on results page. Target: +25% clicks. Kill if flat.

**H3. Showing the rejected pile builds trust rather than doubt.** "We hid 43 listings, here is why" increases repeat use.
Measure: D7 return rate, A/B. Target: +10 percentage points. Kill if negative, which would mean we are advertising our own uncertainty.

**H4. Hunts convert searchers into users.** Offered a saved hunt right after results, a quarter of searchers create one, and hunt creators return within 7 days at three times the rate of one-off searchers.
Measure: hunt creation rate, D7 return by cohort. Target: 25% creation, 3x return. Kill below 10% creation.

**H5. Speed and relevance sell at €7.** At least 5% of active hunt users pay €7 a month for unlimited hunts and faster checks, and alerts get opened and clicked within 15 minutes at least 40% of the time.
Measure: paid conversion of hunt users, alert click latency. Target: 5% and 40%. Kill below 2% conversion.

**H6. A price verdict changes decisions.** Adding "good deal / fair / steep, based on N comparables" raises seller-contact intent and users say it changed what they did.
Measure: contact clicks A/B, plus a one question survey on the verdict. Target: +20% contact clicks, 50%+ say it changed their decision. Kill if contact clicks drop, which would mean we are talking people out of purchases.

**H7. Internationals are the beachhead.** Non-Dutch language searches show higher engagement per session and higher referral than Dutch ones.
Measure: listings opened per session and referral rate by input language. Target: 1.5x engagement, 2x referral. If false, drop the expat-first marketing thesis immediately and go mainstream Dutch.

**H8. The first message is a real job.** Offering a generated Dutch opening message raises the rate at which users actually contact a seller.
Measure: contact rate A/B. Target: +30%. Secondary: is this a better paywall trigger than hunt limits.

**H9. Scam flags are worth the false positives.** A rules plus LLM risk badge catches most listings users independently consider suspicious without crying wolf on clean ones.
Measure: recall against user-reported suspicious listings, false positive rate on a hand labelled clean set. Target: 60% recall, under 10% false positives. Kill above 20% false positives, because a jumpy badge destroys the trust it is meant to build.

**H10. The daily deal hunt is an acquisition engine, not a homepage decoration.** Public per-category daily finds pages bring in new visitors and convert them into hunts.
Measure: share of new visitors landing on a finds page, and their hunt creation rate. Target: 30% of new visitors within 8 weeks, 15% hunt creation. Kill if hunt creation from that traffic is under 5%, which would mean we are attracting spectators.

---

## 10. Ten marketing hypotheses for the Netherlands

All tied to the three focus jobs. Dutch context: WhatsApp reaches 88.8% of Dutch internet users, Facebook 69.1%, LinkedIn 76.2%, Instagram around 45%, TikTok 5.6 million adults. iDEAL is how the Netherlands pays, so Mollie, not a card-only checkout.

**M1. Programmatic Dutch long-tail SEO on constraint queries.** Pages like "tweedehands eettafel massief hout 180 cm Amsterdam" built from live listings plus a price range, 200 pages to start.
Target: 5,000 organic sessions a month within 90 days, 3% to hunt creation. Kill if under 1,000 sessions at day 90.

**M2. Price pages capture the highest intent query in the category.** "Wat is een [model] waard in 2026", fed by our own observed comparables.
Target: top 10 Dutch ranking for 25 model queries in 8 weeks, 8% of that traffic creating a hunt.

**M3. Internationals first, in English, in their own rooms.** r/Netherlands, r/Amsterdam, expat Facebook groups, IamExpat, DutchReview, university housing channels. The pitch is "search Marktplaats in English and get only what fits".
Target: 1,000 signups in 4 weeks at under €2 blended CAC. Paired with H7.

**M4. WhatsApp is the notification channel, not email.** Hunt results delivered to WhatsApp beat email badly on a channel where nine in ten Dutch people already live.
Target: 70%+ open on WhatsApp against 35% or less on email, and higher paid conversion for WhatsApp users.

**M5. Category-intent Google Ads, never brand-adjacent terms.** Bid on "tweedehands bakfiets kopen", not on "marktplaats". In-house competence exists, so the test is cheap.
Target: CPC at or under €0.40, cost per registered hunt at or under €3, on a €500 test.

**M6. Niche forums and hobby communities convert better than broad social.** Tweakers V&A, bakfiets and vintage bicycle forums, HiFi, photography, horse gear, model trains. Offer a free standing hunt for that niche.
Target: 500 signups across five niches, and higher D30 retention than paid traffic.

**M7. The deal hunt is short-form video content that writes itself.** A Dutch language series: a €120 find, valued at €600, with the reasoning. We already generate the material every morning at 08:00.
Target: one clip in twenty over 100k views, CAC under €0.50 at scale, 20 clips in the month.

**M8. Seasonality is worth planning for.** Near term: Sinterklaas and Christmas second hand gifting, Black Friday counter-positioning ("the anti Black Friday: buy it used"), and the dark months when people buy furniture indoors. April: King's Day, when the country turns into one open air market and "what is this worth" gets asked a million times.
Target: a built and dated campaign calendar, and a 3x signup week on the Sinterklaas push.

**M9. The share link is an under-used growth loop.** Every finished search already produces a frozen shareable snapshot at /s/. Today it is a receipt. Make it a landing page with its own hunt call to action.
Target: 0.3 new visitors per shared search, 10% of them creating a hunt.

**M10. One national press moment, measured honestly.** "The AI that reads all 18.7 million Marktplaats ads for you" to Tweakers, Bright, Emerce, NU.nl tech, De Ondernemer, plus Dutch startup podcasts.
Target: one national pickup, 20,000 sessions in 48 hours, and the real test: D30 retention of that cohort at 8% or better. If retention is 2%, we learned that PR is vanity here and we stop spending time on it.

---

## 11. One month plan

**Team.** One designer, one engineer, one marketer, Pavel on product and priority calls.

**Month goal.** Prove the habit, not the revenue. North star: weekly retained hunters, defined as users with at least one active hunt who opened a hunt result in the last 7 days.

| End of month target | Number |
|---|---|
| Weekly retained hunters | 250 |
| Hunts created | 1,000 |
| Paying subscribers at €7 | 40 |
| Match quality on the golden set | 85% precision, 80% recall |
| Median alert latency | under 8 minutes |

Forty paying subscribers is €280 a month, which is not a business. It is the only honest proof that the standing hunt is worth money, and it is enough to decide whether month two is growth or a rethink.

**Non-negotiables all month.** Friday demo with real data on screen, not slides. Every feature ships instrumented in PostHog or it does not ship. Five user interviews a week, every week, everyone watches at least one.

---

### Week 1. Measure the core, then sharpen it

The premise of the whole plan is that vindje's match quality is good. Nobody has measured it. That happens first.

**Engineer**
- PostHog event schema and implementation: search started, wish parsed (with constraint count and input language), results rendered (matched and rejected counts), listing opened, listing rejected-reason expanded, share link copied, hunt created. This is the backbone for H1, H2, H3.
- Build the evaluation harness: 50 golden wishes covering bicycles, furniture, electronics, baby gear and clothing, each with hand-labelled expected matches from a frozen listing snapshot. One command prints precision, recall and cost per search. Nothing else built this month matters as much.
- Fix whatever the harness exposes, in this order: constraints silently dropped in parsing, listings rejected for missing data rather than for failing a constraint, radius and postcode handling.

**Designer**
- Interview five buyers who used Marktplaats in the last month, at least two non-Dutch speakers. Recorded, watched by everyone.
- Redesign the results row as a typographic row system in the house style: image, price with tabular numerals, title, distance, and the reason line as the thing the eye lands on. Mobile first, because this gets used standing in a kitchen.
- Design the rejected pile: "43 hidden" expanding to grouped reasons, and the empty state for a search that legitimately has nothing.

**Marketer**
- Dutch keyword map for the three focus jobs, with volumes: constraint queries, "wat is X waard" valuation queries, and city plus category queries. Output a ranked list of 200 page targets for M1 and 25 model targets for M2.
- Set up analytics, Search Console, and one page of positioning copy in the house voice that we can actually test.
- Recruit for interviews, and open the five niche forum and expat community conversations for M3 and M6 by hand, no automation.

**Gate.** Harness runs, baseline numbers known. If precision is below 70%, week 2 is quality work and hunts slip. State that trade-off out loud on Friday.

---

### Week 2. Ship the standing hunt

**Engineer**
- Hunt storage in Upstash: wish, parsed search, constraints, radius, postcode, delivery channel, cadence, last-seen listing ids (reuse the existing dedupe logic, which already handles relisted items).
- Hunt runner cron at 5 to 15 minutes depending on tier. Be gentle with the Marktplaats endpoint: caching, jitter, rate limiting, back off on errors. Run the LLM filter only on genuinely new listings, which keeps cost per hunt near zero.
- Delivery: web push and email in week 2, WhatsApp behind a flag for M4 (WhatsApp Business API, template approval takes days, so start the paperwork on Monday).
- Cost and latency dashboard per hunt.

**Designer**
- Hunt creation flow: one tap from a finished search, with cadence and channel chosen without a settings page.
- The notification itself, which is the actual product surface for this job: one listing, the price, the reason it matches, one tap to the listing. It has to be legible in a lock screen glance.
- Hunt management: a row per hunt, last found, how many hidden, pause and delete.

**Marketer**
- Ship the first 60 programmatic SEO pages (M1) and the first 10 price pages (M2).
- Start the video series (M7): 10 clips from the daily finds, Dutch, shot on a phone, no production values.
- Post in the five niches and the expat channels with a real offer, not a link drop.

**Gate.** 100 hunts created by real users, median latency under 15 minutes, and at least one hunt result that a user tells us they bought.

---

### Week 3. Price confidence, and ask for money

**Engineer**
- Start the comparables corpus. We already pull listings daily for the deal hunt. Persist observed listings with price, category, attributes and first and last seen dates. Disappearance is a weak but real signal of a sale, and it is the only sold-price data available in this market.
- Valuation endpoint reusing and hardening the deals.py prompt: a verdict (good deal, fair, steep), a range, the number of comparables, and a confidence level. Refuse to guess when the comparable set is thin. A wrong confident number here costs more trust than a missing one.
- Mollie with iDEAL for the €7 tier. Free: 2 hunts at 15 minutes. Paid: 10 hunts at 5 minutes, WhatsApp delivery, price verdicts.

**Designer**
- The price verdict component, in both the results row and the listing detail, with the comparables visible on tap. Restraint matters: this is a number and a word, not a chart.
- The paywall, which states the price in the button and what the free tier keeps. Dutch and English.
- One pass over the share page (/s/) to turn it from a receipt into a landing page for M9.

**Marketer**
- Price pages live at 25 models (M2), first SEO traffic read.
- Launch the €500 Google Ads test (M5) against hunt creation, not clicks.
- Write and schedule the Sinterklaas and Black Friday counter-positioning campaign (M8). Prepare the press angle and the target list for M10 but do not send yet.

**Gate.** First paying subscriber, price verdict live on every result, and an A/B running on H6.

---

### Week 4. Make it hold, then push

**Engineer**
- Reliability: hunt runs must not silently die. Alerting on failed runs, on LLM fallbacks, and on empty result streaks. A hunt that stops firing is worse than no hunt.
- Scam risk badge (H9) as rules plus LLM: stock photo detection, price far below the comparable range, fresh account, payment-link language in the description. Ship it quiet and measure the false positive rate before making it loud.
- Second source behind a flag: 2dehands, since it is the same operator and the same listing shapes, to test whether multi-source changes perceived coverage (the alert tools all do this already).

**Designer**
- Close the loop on the month's data: fix the two worst drop-offs the funnel shows, whatever they are.
- The house-style landing page, with a real screenshot of a real search as the hero. Not an illustration of AI.
- A design.md in the repo recording the accent, type scale and row system, so this does not drift.

**Marketer**
- Press push (M10) with the landing page live, and measure the cohort's D30, not the session count.
- Referral on the share link (M9).
- Month review: CAC and retention by channel, on one page, with a clear recommendation of the two channels to kill and the one to double.

**Gate.** The five month-goal numbers in the table, honestly reported, including the ones we miss.

---

## 12. Risks worth naming now

1. **Platform dependency.** vindje reads Marktplaats' own website search endpoint. It is undocumented and can be rate limited, changed or blocked at any time, and hunts multiply the request volume. Mitigations: conservative polling, caching, jitter, a clearly non-abusive profile, and a second source (2dehands, Vinted, Facebook Marketplace) so a single block is not fatal. Keep a plain-search fallback that degrades instead of failing, which the app already does for LLM outages.
2. **The incumbent ships the feature.** Avito gives every user an AI assistant in 2026 and Marktplaats will do the same. Our defence is not the model, it is being multi-source, buyer-aligned, and habit-forming before they arrive.
3. **The AI filtering wedge is already claimed.** MPAlerts advertises it today. Differentiate on measured match quality and the explanation, and say the number out loud once we have it.
4. **Unit economics.** Every hunt that runs every five minutes is LLM spend. Filter only new listings, cache aggressively, and keep cost per hunt per month visible from week 2 so the €7 price does not quietly go underwater.
5. **Trust runs the other way too.** A confident wrong price verdict or a jumpy scam badge damages us more than silence would. Ship both with an explicit "not enough data" state.
6. **AVG and consent.** Notifications, WhatsApp and stored searches all need proper consent and retention rules. Cheap to do now, expensive to retrofit.

---

## 13. Sources

Marktplaats and the Netherlands
- [Marktplaats.nl, Wikipedia](https://en.wikipedia.org/wiki/Marktplaats.nl)
- [Marktplaats reviews, Trustpilot](https://www.trustpilot.com/review/www.marktplaats.nl)
- [Problemen met marktplaats.nl, Radar forum, AVROTROS](https://radar-forum.avrotros.nl/webwinkels-f69/problemen-met-marktplaats-nl-t17863.html)
- [Kosten Kopersbescherming, Marktplaats help](https://help.marktplaats.nl/s/article/kosten-kopersbescherming)
- [Marktplaats kopersbescherming, hoe werkt het en wat kost het, MarktAlert](https://marktalert.nl/blog/marktplaats-kopersbescherming-hoe-werkt-het)
- [Marktplaats.nl verhoogt prijzen in zakelijke rubrieken, Emerce](https://www.emerce.nl/nieuws/marktplaats-nl-verhoogt-prijzen-zakelijke-rubrieken)
- [Marktplaats, Adevinta](https://adevinta.com/brand/marktplaats/)
- [marktplaats.nl traffic analytics, Similarweb](https://www.similarweb.com/website/marktplaats.nl/)
- [Netherlands leading online marketplaces by visit share, Statista](https://www.statista.com/statistics/1256594/netherlands-leading-online-marketplaces-visits/)
- [Wat vinden consumenten van tweedehands spullen, Circulair Ambachtscentrum](https://circulairambachtscentrum.nl/nieuws/2025/vinden-consumenten-tweedehands-spullen/)
- [32% van de Nederlandse consumenten koopt nu meer tweedehands, Duurzaam Ondernemen](https://www.duurzaam-ondernemen.nl/32-van-de-nederlandse-consumenten-koopt-nu-meer-tweedehands-producten-dan-5-jaar-geleden/)
- [Second-hand goods retailing in the Netherlands, IBISWorld](https://www.ibisworld.com/netherlands/industry/second-hand-goods-retailing/200596/)
- [Aankoop via een online platform, Consumentenbond](https://www.consumentenbond.nl/online-kopen/opgelicht-marktplaats)
- [Opgelicht via Marktplaats, Slachtofferwijzer](https://slachtofferwijzer.nl/artikelen/opgelicht-marktplaats-fraude-melden)
- [Where to sell your stuff in the Netherlands, DutchReview](https://dutchreview.com/expat/selling-your-stuff-in-the-netherlands/)
- [Digital 2025 Netherlands, DataReportal](https://datareportal.com/reports/digital-2025-netherlands)

The existing alert layer
- [MarktAlert](https://marktalert.nl/) and [its tool comparison](https://marktalert.nl/vergelijking)
- [MPAlerts](https://mpalerts.nl/)
- [Marktplaats Scanner](https://www.marktplaatsscanner.com/)
- [Delivery service for large Vinted purchases, Brenger](https://www.brenger.nl/en-nl/vinted/)

Global
- [CMA puts Vinted at 50 to 60% of UK C2C apparel GMV, Value Added Resource](https://www.valueaddedresource.net/cma-vinted-leads-uk-apparel-gmv/)
- [Vinted overtakes Gumtree as the UK's most visited secondhand marketplace, AIM Group](https://aimgroup.com/2025/11/26/vinted-overtakes-gumtree-to-become-the-u-k-s-largest-secondhand-marketplace/)
- [Vinted 2025 financial results](https://company.vinted.com/newsroom/financial-results-2025)
- [eBay removes UK seller fees, TechCrunch](https://techcrunch.com/2024/10/01/ebay-removes-uk-seller-fees-to-counter-new-wave-of-marketplace-startups)
- [Magical Listing revisited, has eBay closed the AI gap, Value Added Resource](https://www.valueaddedresource.net/ebay-ai-magical-listing-revisited/)
- [Kleinanzeigen reviews, Trustpilot](https://www.trustpilot.com/review/kleinanzeigen.de)
- [Kleinanzeigen, UX Design Awards 2025](https://ux-design-awards.com/winners/2025-2-kleinanzeigen)
- [Whatnot global GMV doubles to $8 billion in 2025, Ebrun](https://english.ebrun.com/20260211/640428.shtml)
- [Whatnot, live shopping finally works, Ringing the Bell](https://ringingthebell.substack.com/p/whatnot-live-shopping-finally-works)
- [Mercari vs OfferUp, which marketplace model is better, IdeaUsher](https://ideausher.com/blog/mercari-vs-offerup-which-marketplace-model-is-better/)
- [Top Facebook Marketplace scams, NordPass](https://nordpass.com/blog/facebook-marketplace-scams/)
- [Avito delivery and order tracking, Ship24](https://www.ship24.com/shops/avito-tracking)
- [Avito.ru overview](https://grokipedia.com/page/Avito.ru)
- [Avito Services, neighbours recommend](https://www1.ru/en/news/2026/06/22/sarafannoe-radio-vyxodit-v-onlain-avito-uslugi-nasli-novyi-sposob-iskat-masterov.html)
- [Alibaba's Xianyu, more than just a second-hand marketplace, ChinaTalk](https://www.chinatalk.nl/alibabas-xianyu-more-than-just-a-second-hand-marketplace/)
- [Alibaba's Xianyu swims a different course, TechBuzz China](https://techbuzzchina.substack.com/p/alibabas-xianyu-idle-fsh-swims-a)
- [Young consumers drive second-hand e-commerce in China, Daxue Consulting](https://daxueconsulting.com/secondhand-market-in-china/)
- [Why Craigslist still looks the same after 25 years, Slashdot](https://tech.slashdot.org/story/22/09/16/2123239/why-craigslist-still-looks-the-same-after-25-years)

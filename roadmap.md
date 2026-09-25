# Roadmap: 19 September to 16 October

Four weeks. One month objective, three outcomes, taken from the quarter plan:

1. **Team.** Does this team work well together, and who wants to continue after
   16 October.
2. **Paid users.** 5 customers paying EUR 100+ per month, and a written answer
   to "who exactly are they".
3. **Free users.** 100+ people a day using the free product, and a written
   answer to "what do they use it for".

Everything below exists to move one of those three. If a task does not, it is
not on this list.

## Who does what

| Person | Owns |
|---|---|
| **Julia** | Engineering. Scheduled searches, accounts, second platform, filter-quality eval. |
| **Nadja** | Product and design. What the paid product actually is, the onboarding surface, grants. |
| **Jesse** | Marketing. Where the 100 daily users come from, and the story that makes them stay. |
| **Pavel** | Customer conversations, pricing, access, unblocking, the 16 October decision. |

Each outcome has one name against it. Team: Pavel. Paid: Pavel. Free: Jesse.
Shared ownership means nobody owns it.

## The bet

Flippers and resellers doing EUR 1,000 to 10,000 a month pay for a daily list
of things worth buying in their category. They do not want a better search box.
They want to open one email in the morning, see ten items, and decide on each.

That is the bet. The whole month is built to prove or kill it.

The quarter plan says EUR 250 per month. The B2B notes say EUR 50 to 150. The
objective says EUR 100+. Quote EUR 249 in the first conversations. You can come
down from a high number, you cannot go up from a low one, and the gap between
what people say and what they pay is the thing we are actually measuring.

Free users are the top of the same funnel, not a separate product. Someone who
searches for a vintage racing bike three times in a week is a flipper who has
not told us yet.

## Where the product is today

Worth being precise, because the plan depends on it.

Working now: single-file Python app on Vercel, LLM parse of a wish into a Dutch
Marktplaats search, LLM filter over the results with a reason per listing,
share links (`/s/<id>`), a global `/history`, an `/ideas` board, an MCP server,
and a daily deal hunt (`deals.py`) over four categories that renders on the
homepage.

Not there at all: accounts, saved searches, any notification, any email, any
second platform, any way to take money, and any product analytics beyond a GTM
container. We currently cannot count "100 users a day" in a way anyone would
defend in a meeting.

So the month is: turn the daily deal hunt into a product a flipper pays for,
and build the measurement that tells us whether any of it worked.

## Week 1: 19 to 25 September

Goal: know who the customer is, and have the machine that mails them results.

**Pavel: 20+ conversations with flippers.** Bikes, sneakers, Lego, designer
furniture, designer clothing. Start with the boat flipper from FRClub. Every
conversation ends with one question asked out loud: "if this landed in your
inbox every morning at seven, would you pay EUR 249 a month for it." Write the
answer down verbatim, including the no's. Output by Thursday: a one-page ICP
with categories, monthly turnover, current tooling, and what they said about
price.

**Julia: scheduled searches.** A saved search stored in Upstash, run on a
GitHub Actions cron, results delivered by email. `deals.py` already does the
hunt-and-value half; this generalises it from four hard-coded categories to a
per-user query. Email goes out through an HTTP API called with `urllib`, no new
Python dependency (see `AGENTS.md`, hard limit 1). Deduplicate against what was
already sent, so nobody gets the same listing twice.

**Julia: answer "what does one search cost".** Log tokens and euros per search
and per digest run. If a daily digest costs EUR 2 a day to produce, EUR 249 a
month is a thin business and we need to know that in week 1, not week 4.

**Julia: measure filter quality.** Pick 5 real wishes, take the ~100 listings
they return, have Nadja and Pavel hand-label each keep or drop, and write a
script that prints precision and recall against those labels. "The filtering
feels good" is not a number. This eval is what lets us change the prompt later
without guessing.

**Julia: second platform spike.** Vinted first: it has the clothing and
sneaker volume that flippers live on. Time-boxed to two days and the output is
a written verdict, not a feature: can we read it, at what rate, under what
terms, and what does it cost. Build lands in week 2 only if the verdict is yes.

**Jesse: the funnel we can count.** Get product analytics in (PostHog next to
GTM) with four events: search started, results returned, alert created, alert
opened. Then pick three acquisition channels and say why. Suggestions worth
arguing about: Dutch flipper and second-hand Facebook groups, Reddit
(r/marktplaats, r/thenetherlands), and the Claude connector directory, which we
are already eligible for and nobody else in this space is using.

**Nadja: what is the paid product.** One page and one screen. What a paying
flipper sees on day one, what lands in their inbox on day two, and what makes
them open it on day thirty. Not a spec, a decision.

**Pavel: access.** GitHub and Vercel for Julia, Jesse and Nadja. Day one, not
day five.

## Week 2: 26 September to 2 October

Goal: something we can charge for, in the hands of the first pilots.

**Julia: accounts.** Email and a magic link. No passwords, no OAuth, no user
table nobody asked for. This is also how the email list gets built, which the
B2B notes correctly put first.

**Julia: saved searches in the UI.** Create one from a search you just ran,
because that is the moment somebody wants it. Daily digest by email, on by
default.

**Julia: second platform live**, if week 1 said yes. One search across both,
one result list.

**Nadja: onboarding.** First-run examples that show what the AI can do, since
an empty search box explains nothing. The competitor review is right: they
demonstrate, they do not list features.

**Nadja: grants for sustainability.** The reuse numbers are strong (a garment
kept nine months longer cuts its footprint by up to 30%) and Dutch and EU
circular-economy funding exists. Time-boxed to one day. Output: three named
programmes with deadlines, or a written "not worth it this quarter".

**Pavel: a way to take money.** A Stripe payment link and a pricing page. Do
not build billing. The first five customers get onboarded by hand and that is
correct at this stage.

**Jesse: launch the channels.** Publish, post, and put a number against each
channel so we can tell in week 4 which one worked.

**Everyone: first pilots live.** Target five flippers using scheduled searches
by 2 October, paid or in a paid trial.

## Week 3: 3 to 9 October

Goal: find out whether they come back.

**Pavel and Nadja: concierge buy lists.** For each pilot, hand-curate the daily
list for a week. Yes, by hand. It tells us what a good list looks like before
we automate the wrong thing, and it is how the first five customers stay
customers.

**Julia: fix what the pilots complain about.** Nothing else. Week 3 is not for
new surface area.

**Jesse: read the funnel.** Where do people drop between landing and first
search, and between first search and second visit. Say it in numbers and name
the one fix worth making.

**Julia: SEO on what we already have.** The daily finds are real content
produced every morning and thrown away. A public, indexed archive page is close
to free traffic, and it is the one acquisition lever that compounds without
anyone posting anything.

**Pavel: convert.** Trials to paid. Ask for the card.

## Week 4: 10 to 16 October

Goal: decide, with evidence.

- **Paid.** How many are actually paying, at what price, and what they said
  when asked why. Five is the target. Two with strong reasons beats five who
  signed up to be polite.
- **Free.** Daily users over the last seven days, and the top ten search wishes
  people typed. That list is the answer to "what do they use Vindje for".
- **Team.** One retro, one honest conversation each. Who wants to continue,
  at what commitment, doing what.
- **Tech direction.** The product-ideas deck proposes moving to a
  TypeScript-first stack. Decide it now, with four weeks of evidence behind it,
  not before. See the non-goals below.
- **Next month.** One page, written on 16 October, while it is fresh.

## What we are deliberately not doing

- **No rewrite to TypeScript this month.** It may well be the right call later.
  A rewrite in the middle of a four-week revenue sprint trades the only thing
  we are short of (time to talk to customers and ship for them) for something
  we cannot yet prove we need. Revisit on 16 October with the month's evidence.
- **No consumer cross-platform search, no browser extension.** Both are good
  ideas from the brainstorm. Neither gets us to five paying flippers by
  16 October. They go on the list for next month.
- **No listing-writing tools, no commission model, no price-data product.**
  Real revenue lines, all of them downstream of having customers at all.
- **No splitting `app.py`.** One file is a choice. See `AGENTS.md`.

## Numbers we report every Monday

| Metric | Now | Target 16 Oct |
|---|---|---|
| Paying customers | 0 | 5 |
| Revenue per month | EUR 0 | EUR 500+ |
| Daily active users | not measured | 100 |
| Saved searches running | 0 | 50 |
| Digest open rate | n/a | 40% |
| Filter precision on the eval set | not measured | 90% |
| Cost per search | not measured | known, and under EUR 0.05 |

Half of these read "not measured" today. Fixing that is week 1's real job.

## Risks

**Marktplaats.** Scheduled searches multiply our request volume by the number
of saved searches, every day. That is exactly where "be gentle" stops being a
guideline and starts being an outage. Cap it: one request per saved search per
run, batched, nightly, no retry storms.

**LLM cost per digest.** Fifty daily digests through two LLM passes adds up
fast. Measure in week 1 and cache aggressively. Same listing, same verdict, no
second call.

**Five customers is a small number with a large variance.** Twenty
conversations in week 1 is what makes five plausible. If week 1 produces eight
conversations instead of twenty, the month is already off track and we should
say so on 26 September rather than on 16 October.

**We are four people with day jobs' worth of scope here.** If something has to
go, it goes in this order: grants, SEO archive, second platform. Scheduled
searches and the customer conversations do not go.

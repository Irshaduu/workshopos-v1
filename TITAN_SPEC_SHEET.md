# Titan Spec Sheet

**WorkshopOS "Titan"** — every file, line, model and rule, counted from the
repository rather than estimated. **This is the final revision**: the system was
frozen on 9 October 2026, never went live, and is kept as the reference
specification for its rebuild in a separate repository.

| | |
|---|---|
| **Measured** | 9 October 2026, branch `main`, including this document |
| **Stack** | Django 5.2 monolith, PostgreSQL in development and production |
| **Apps** | 2 — `workshop` (core business logic), `inventory` (stock + supplier shops) |
| **History** | 294 commits, 11 January – 9 October 2026, before the commit carrying this revision |

| Files | Lines | Tests | Models | Routes | Screens | Dependencies |
|---:|---:|---:|---:|---:|---:|---:|
| **510** | **169,231** | **3,185** | **49** | **324** | **140** | **9** |

> Every figure below was re-measured from the working tree. Nothing is carried
> over from documentation.

---

## 01 — Totals: files and lines

**510** files are tracked in version control, and every one of them is
counted below. The four categories do not overlap and add up exactly to the
total. Line counts exclude binary files (fonts, images, PDFs, the database file),
which are measured by size instead.

| Category | Files | Lines | Size | Share of lines |
|---|---:|---:|---:|---:|
| **Back end** | **298** | **87,170** | 3,982 KB | 51.5% |
| &nbsp;&nbsp;Application code | 101 | 35,896 | 1,630 KB | 21.2% |
| &nbsp;&nbsp;Test suite | 92 | 48,146 | 2,227 KB | 28.4% |
| &nbsp;&nbsp;Database migrations | 105 | 3,128 | 125 KB | 1.8% |
| **Front end** | **153** | **57,754** | 2,689 KB | 34.1% |
| &nbsp;&nbsp;Django templates (screens) | 137 | 50,032 | 2,388 KB | 29.6% |
| &nbsp;&nbsp;Shared JavaScript | 10 | 3,747 | 167 KB | 2.2% |
| &nbsp;&nbsp;Shared stylesheets | 2 | 2,899 | 92 KB | 1.7% |
| &nbsp;&nbsp;JavaScript test suite | 4 | 1,076 | 42 KB | 0.6% |
| **Documentation** | **14** | **20,133** | 2,037 KB | 11.9% |
| &nbsp;&nbsp;Markdown documents | 10 | 18,607 | 1,182 KB | 11.0% |
| &nbsp;&nbsp;System map (2 HTML + 2 PDF) | 4 | 1,526 | 855 KB | 0.9% |
| **Other** | **45** | **4,174** | 8,310 KB | 2.5% |
| &nbsp;&nbsp;Vendored libraries (Bootstrap, icons, Chart.js) | 5 | 2,250 | 609 KB | 1.3% |
| &nbsp;&nbsp;Build tooling (icon, system-map, vendoring scripts) | 5 | 1,566 | 76 KB | 0.9% |
| &nbsp;&nbsp;Config (Procfile, manifest, requirements, robots, service worker, error pages) | 11 | 358 | 14 KB | 0.2% |
| &nbsp;&nbsp;Self-hosted fonts | 16 | — | 550 KB | — |
| &nbsp;&nbsp;App icons & letterhead artwork | 7 | — | 322 KB | — |
| &nbsp;&nbsp;Development database (SQLite, dummy data) | 1 | — | 6,740 KB | — |
| **TOTAL** | **510** | **169,231** | **16.62 MB** | **100%** |

Two rows carry files that hold no tests or no migration: the test suite's 92
files include one empty package initialiser, so **91 files actually carry
tests**, and the 105 migration files are 103 numbered migrations plus the two
package initialisers. Both are counted where they live so the table adds up.

The three shared error pages (403 / 404 / 500) sit in the config row rather than
with the screens: they extend no layout and load nothing at all, so that an
error page cannot break for the reason it is being shown. Counting them as
screens gives the **140** in the headline.

⚠ **The development database is committed again.** The September revision
recorded the 6.6 MB SQLite file as deleted with the throwaway demo deploy. It was
re-added on 29 September "temporarily for a live check", and on 9 October the
developer decided to keep it. It holds dummy data only — production never reads
SQLite — and it is counted here as one binary file.

**Working files outside version control** are deliberately not counted: the
environment secrets file, the local technical-debt register (225
lines, 2,103 words), the error log, and a generated single-file dump
of the repository.

---

## 02 — Language usage

Measured across 146,490 lines of code written for this project. Third-party
libraries and documentation are excluded. Crucially, the CSS and JavaScript
written *inside* template files is counted as CSS and JavaScript, not as HTML —
which is why these percentages differ from a naive file-extension count.

| Language | Lines | Share |
|---|---:|---:|
| **Python** — business logic, data model, tests | 88,736 | **60.6%** |
| **HTML / Django templates** — markup only | 23,069 | **15.7%** |
| **CSS** — incl. 20,006 lines written inside templates | 22,905 | **15.6%** |
| **JavaScript** — incl. 6,957 lines written inside templates | 11,780 | **8.0%** |
| **TOTAL OWN CODE** | **146,490** | **100%** |

Inline styling and scripting inside templates accounts for **787 KB of
CSS across 74 templates** and **318 KB of JavaScript across
52 templates**.

### Python, broken down

| Purpose | Lines | Share of Python |
|---|---:|---:|
| Test suite | 48,146 | 54.3% |
| Application code | 35,896 | 40.5% |
| Database migrations | 3,128 | 3.5% |
| Build tooling | 1,566 | 1.8% |
| **TOTAL PYTHON** | **88,736** | **100%** |

> **1.34 lines of test for every line of application code.** The test suite is
> larger than the software it tests. That ratio is the single number that best
> describes how this system was built, and it rose every time it was measured:
> 1.22 : 1 in August, 1.29 : 1 in September, 1.34 : 1 at the freeze — the
> last three weeks added Change History, shop discounts, parts transport and
> Warranty, and 493 more tests.

---

## 03 — Back end, by layer

101 files of application code, excluding tests and migrations. Every row adds up
to the total; nothing is double-counted.

| Layer | Files | Lines |
|---|---:|---:|
| Views — `workshop/views/` package | 25 | 10,714 |
| **Rule modules** — each owns exactly one question | 21 | 7,771 |
| Models, forms, costing & signals | 5 | 5,947 |
| Management commands | 18 | 3,767 |
| Views — flat modules (auth, analysis, cashbook, admin, cleanup) | 5 | 3,450 |
| Views — inventory app | 2 | 1,522 |
| Platform — notifications, push, mail, middleware, access control | 5 | 1,067 |
| Routing, admin, template tags & context processor | 6 | 995 |
| Settings, URL root, WSGI/ASGI, entry point | 8 | 621 |
| App registry & package initialisers | 6 | 42 |
| **TOTAL** | **101** | **35,896** |

### The twenty-one rule modules — the structural idea of this codebase

| Module | The one question it answers | Lines |
|---|---|---:|
| `analysis_engine.py` | What is the profit, and the cash movement, for this date window? | 1,969 |
| `warranty.py` | Which part of which earlier bill may be claimed, and where does its warranty clock start? | 968 |
| `service_history.py` | Every figure and every name on the service-history sheet | 845 |
| `rent.py` | How much should we hand the rent collector today? | 614 |
| `invoice.py` | What does the customer see? (owns every bill, the estimate and the warranty slip) | 559 |
| `master_data.py` | What does renaming or merging a name actually do? | 395 |
| `photos.py` | Where do the bytes go, and how is the URL signed? | 392 |
| `old_bills.py` | Is this pre-system bill's number, date and money acceptable? | 342 |
| `settlement.py` | What is still unfilled before this bill is settled? | 318 |
| `old_bill_pdf.py` | What does this bill's own saved PDF say, box by box? | 263 |
| `mileage.py` | Can this hand-typed odometer reading be believed? | 165 |
| `money_dates.py` | Which day did this money move, and how far back may it be filed? | 158 |
| `vehicle_ids.py` | Is this a chassis code and a VIN, and what did this car last have? | 150 |
| `known_car.py` | What does the workshop already know about this number plate? | 119 |
| `delete_window.py` | Has this record been in the books too long for Office to change? | 116 |
| `spare_dates.py` | Is this ordered / received date pair the right way round — and how is it printed short? | 97 |
| `money.py` | Is this typed rupee amount acceptable for its column? | 70 |
| `pricing.py` | What markup is suggested, and is this typed markup usable? | 69 |
| `client_ip.py` | Which address is the visitor's, behind the host's own proxy? | 59 |
| `discounts.py` | May this shop discount be written? | 55 |
| `return_to.py` | Where does this page send you when you leave it? | 48 |
| **21 MODULES** | | **7,771** |

> Three of these arrived after the September measurement, each for the reason the
> first eighteen did: a rule was about to need a second home. `client_ip.py`
> exists because the sign-in lockout counted Railway's own proxy as the visitor —
> every visitor arriving through it shared one counter — while the session list
> read the forwarded header unchecked. `discounts.py` holds the one
> set of rules for a discount from either kind of shop. `warranty.py` is the
> largest newcomer, and nearly all of it is about *which* part a claim may be
> made on and from what date its age is measured.
>
> **`pricing.py` is the one that is defined by what it does *not* contain.**
> It holds the three markup numbers and the parser for a typed markup, and
> deliberately no price function: the suggested customer price is worked out in
> the browser and reaches a bill only when a person presses Save. A price the
> server computed would have billed parts the floor added with no price,
> silenced the settle check, repriced an unlocked settled card, and moved old
> bills every time a late supplier bill re-costed the shelf.

### Ten largest single files

| File | Lines |
|---|---:|
| `workshop/models.py` | 3,323 |
| `workshop/analysis_engine.py` | 1,969 |
| `workshop/forms.py` | 1,686 |
| `workshop/views/spare_shop.py` | 1,352 |
| `workshop/views/jobcard.py` | 1,314 |
| `inventory/views_suppliers.py` | 1,240 |
| `workshop/analysis_views.py` | 1,094 |
| `workshop/views/salary_advance.py` | 1,017 |
| `workshop/warranty.py` | 968 |
| `workshop/auth_views.py` | 957 |

---

## 04 — Front end, by section

137 templates under the two apps — every screen in the system, plus the partials
they include. Each carries its own page-specific styling and scripting inline,
which is why the line counts run high: a template is a complete screen, not a
fragment.

### Workshop app — 117 templates, 46,305 lines

| Section | Files | Lines |
|---|---:|---:|
| Job Card — *the central record* | 16 | 11,714 |
| Car Profiles — *incl. the two customer documents a profile hands over* | 6 | 4,914 |
| Shared includes | 18 | 3,428 |
| Shared shell — *base layout, home, About* | 3 | 3,192 |
| Spare Shops | 5 | 2,845 |
| Analysis & Reports | 11 | 2,668 |
| Estimates | 5 | 2,294 |
| Cashbook | 4 | 2,019 |
| Warranty — *a failed part, claimed on its own card* | 9 | 1,857 |
| Salary & Advance | 5 | 1,791 |
| Dashboard | 2 | 1,551 |
| Invoice — *one file, the printed bill* | 1 | 1,344 |
| Control Hub — *accounts, staff, security, data cleanup* | 4 | 1,127 |
| Old Bills — *the Excel years, typed in for history* | 3 | 1,010 |
| Owner Withdrawals | 1 | 873 |
| Deposit & Rent | 1 | 841 |
| Completed | 2 | 811 |
| Sign-in & password recovery | 5 | 667 |
| Legacy Data — *the go-live starting position* | 4 | 553 |
| Master Lists | 7 | 372 |
| Change History — *deleted, edited, back-dated* | 2 | 249 |
| Notifications | 3 | 185 |
| **SUBTOTAL** | **117** | **46,305** |

> **One whole section appeared since the September measurement — Warranty.** A
> customer comes back with a part that failed, and the claim opens a card of its
> own: nine templates, laid out as the job card so the floor learns nothing new.
> **Shared includes nearly doubled, from 10 to 18**, which is the "one
> declaration" rule at work rather than growth — the date chip, the shop-discount
> symbol, dialog and history, the expected-days box, the print-name copy and the
> warranty slip are each one file included wherever they appear. **Master Lists
> shrank from 11 to 7**: its spare and concern screens were retired, because
> Data Cleanup already did the same job and two front doors for one job is how
> drift starts.

### Inventory app — 20 templates, 3,727 lines

| Section | Files | Lines |
|---|---:|---:|
| Supplies Shops — *restock bills, catalog, payments, discounts* | 13 | 2,491 |
| Stock — *list, low stock, history, categories* | 7 | 1,236 |
| **SUBTOTAL** | **20** | **3,727** |

### Shared front-end assets

| File | Role | Lines |
|---|---|---:|
| `static/css/style.css` | Global styling — the payment card, the back control, the question card, the shop-discount dialog | 1,511 |
| `workshop/static/css/analysis.css` | Owner analysis styling | 1,388 |
| `workshop/static/js/script.js` | Form rows, autocomplete, shared behaviour | 661 |
| `workshop/static/js/photos.js` | Camera capture & upload queue | 550 |
| `workshop/static/js/confirm.js` | The shared question card, and one-press-one-post | 497 |
| `static/js/notifications.js` | Alert panel & push subscription | 331 |
| `workshop/static/js/pricing-core.js` | Markup arithmetic in whole paise — **unit-tested** | 319 |
| `workshop/static/js/spare_autofill.js` | Spare status & date derivation | 296 |
| `workshop/static/js/old-bill-core.js` | Reading a typed date and amount — **unit-tested** | 295 |
| `workshop/static/js/sound.js` | Five synthesised outcome tones | 288 |
| `workshop/static/js/photos-core.js` | Pure logic, DOM-free — **unit-tested** | 276 |
| `workshop/static/js/estimate.js` | Estimate line editing | 234 |
| `workshop/templates/workshop/sw.js` | Service worker — push delivery, offline notice | 125 |
| **13 SHARED FILES** | | **6,771** |

> **No build step, no npm, no bundler.** Server-rendered Django templates with
> page-scoped inline styling and scripting. Thirteen shared JavaScript and CSS
> files exist, and the rule for admission is simply "used on more than one
> page". This is a settled architectural decision, documented with its
> reasoning, not an unaddressed backlog item.
>
> **Three of the JavaScript files are marked unit-tested, and that is a
> different rule from the other ten.** They are not shared because two pages
> need them — `pricing-core.js` and `old-bill-core.js` are each used by one
> screen. They are separate files because they are *provable*: pure functions,
> no browser, no network, so Node's built-in runner can execute them. Each was
> extracted before it was written, because each computes something that can be
> wrong without looking wrong — a price rounded by floating point, a comma read
> as a decimal point.
>
> `style.css` grew from 847 lines to 1,511, mostly by *absorbing* duplication
> rather than adding features: the payment card that had been four
> near-copies, the back control that had been seventeen controls in seven
> treatments, the question card that replaced twenty-one browser dialogs — and,
> since September, the car card's ⋮ menu that had been two copies on two
> screens, and the shop-discount symbol and dialog drawn on both kinds of shop.

---

## 05 — Test suite

3,185 tests, counted by asking Django's own test runner to build the suite — not
by counting function names, which misses tests inherited from shared base
classes.

| Tests | Test classes | Test files | Lines | Test : app code |
|---:|---:|---:|---:|---:|
| **3,185** | **569** | **91** | **48,146** | **1.34 : 1** |

Every run executes against SQLite, in memory. That is not a convenience: the
runner creates and drops an entire database, and there is deliberately no flag
that would let it be pointed at real data by accident. Run serially it has taken
anything from 20 minutes to two and a half hours, and the spread is machine load
rather than a signal. Run on four workers it takes under an hour: the final full
run, on 9 October 2026, passed all 3,185 tests in 49.6 minutes.

### Twelve largest test files

| File | What it guards | Lines |
|---|---|---:|
| `test_analysis.py` | The profit engine, cash tracking and every insight | 2,946 |
| `test_master_salary_hub_integrity.py` | Salary months, settlement locking, advances | 2,495 |
| `test_warranty.py` | Claims, the warranty card, and what claims cost | 2,187 |
| `test_jobcard_form_ux.py` | The job card form — the busiest screen | 1,953 |
| `test_rent.py` | The rent ledger, and how far back money may be filed | 1,758 |
| `test_invoice.py` | The printed bill handed to a customer | 1,644 |
| `test_service_history_view.py` | The printed service record, set from the bill | 1,536 |
| `test_fleet_cashbook_integrity.py` | Fleet account balances & the cashbook | 1,298 |
| `test_photos.py` | Evidence photos, signing, retention | 1,258 |
| `test_estimate.py` | Quotations | 1,112 |
| `tests_suppliers.py` *(inventory)* | Supplies shops & restock bills | 1,111 |
| `test_old_bills.py` | The Excel years, and one JB number sequence across both | 1,052 |

**There is also a second, separate test runner for JavaScript** — Node's
built-in one, with no npm, no package file and no dependencies. It covers three
modules — `photos-core.js`, `pricing-core.js` and `old-bill-core.js` — because
each was deliberately written to be coverable: pure functions, no browser, no
network. 71 tests, and the markup-arithmetic expectations in
`pricing-core.test.js` were each produced by Python first, so the browser and
the server can never round a customer's price differently.

⚠ **Nothing in the Django suite executes a line of CSS or JavaScript.** That is
why several test files assert on *markup and source* rather than behaviour: a
dialog that opens behind another element, a card with no colour, a form that
quietly lost its question, and a page that pasted its own bespoke back link all
leave every functional test green. Those assertions are the only thing that
notices.

---

## 06 — System structure

The moving parts, counted by loading the application and asking it directly
rather than by reading source.

| What | Count | Detail |
|---|---:|---|
| Data models | 49 | 39 in the workshop app, 10 in inventory |
| Model fields | 360 | 296 workshop, 64 inventory — concrete columns only |
| URL routes | 324 | Every reachable address, Django admin included; 187 are the app's own |
| View-module functions | 320 | 199 public screens, 121 private helpers |
| Database migrations | 103 | 90 workshop, 13 inventory |
| Form classes | 12 | Excludes 8 formset classes |
| Access-control decorators applied | 191 | 38 Owner-only, 123 Office, 30 all staff |
| Database signal handlers | 16 | 13 for stock & costing; sign-out, the photo sweep queue and the role cache |
| Atomic transaction blocks | 72 | 53 `with` blocks and 19 decorators — every money movement is all-or-nothing |
| Row locks (`select_for_update`) | 12 | Fleet cascades, shop payments and discounts, the number series, the photo limit and warranty claims |
| Notification events | 20 | 15 critical (push to phone), 5 informational |
| Notification call sites | 29 | Across 11 modules, one catalogue |
| Permanently-deletable record types | 16 | Each writes a snapshot before deletion |
| Management commands | 15 | Backup, seeding, purge, owner identity, roles, photo sweep, legacy unlock |
| Template filters | 16 | Custom, shared across screens; one is also registered under a second name |
| Runtime dependencies | 9 | Django, Pillow, psycopg2, WhiteNoise, gunicorn, decouple, pywebpush, coverage, pypdf |
| Commits | 294 | 11 January – 9 October 2026 |

⚠ **Every count here is across *application code only*** — tests, migrations and
build scripts are excluded. That matters most on the transaction and row-lock
rows: the test suite opens its own transactions and takes its own locks in order
to prove the real ones hold, and counting those as system transactions flatters
the number while describing nothing.

⚠ **Three rows are corrected rather than grown** — see the Method. The September
sheet's 14 forms counted a widget, a field and a choice iterator; its 15 record
types counted the list of record types as one of them; and its 10 row locks
counted every mention, comments included.

---

## 07 — Documentation

196,784 words across ten documents, plus a generated one-page system map in
light and dark themes, committed as both HTML and print-exact PDF. Each document
owns a defined set of facts; none restates another's.

| Document | Owns | Lines | Words |
|---|---|---:|---:|
| `CLAUDE.md` | Day-to-day working rules and every deliberate decision | 11,852 | 122,852 |
| `MASTER_BLUEPRINT.md` | The numbers — models, routes, templates, settings | 1,153 | 22,306 |
| `OPERATIONAL_BLUEPRINT.md` | Workflow narrative — who does what, screen by screen | 1,935 | 17,899 |
| `TITAN_SPEC_SHEET.md` | This document — every figure, counted from the repository | 950 | 9,867 |
| `TITAN_MASTER_HANDOVER.md` | Mission, roadmap, and what is deliberately out of scope | 505 | 9,022 |
| `GO_LIVE_RUNBOOK.md` | The one-time go-live procedure and rollback | 728 | 5,650 |
| `RAILWAY_OPERATIONS.md` | Ongoing platform reference — deploys, backups, cost | 763 | 5,380 |
| `README.md` | Outward-facing summary — features, stack, install | 256 | 1,938 |
| `master_data_export.md` | The workshop's own brand / model / spare list | 315 | 1,065 |
| `WorkshopOS_Complete_Structure.md` | The section tree, as the owner describes it | 150 | 805 |
| **10 DOCUMENTS** | | **18,607** | **196,784** |

`TECH_DEBT.md` (225 lines, 2,103 words) is deliberately
untracked: it lists what is known to be wrong and not yet scheduled, which is
working state rather than a published fact. At the freeze it lists nothing open
at any severity — only two suggestions, and the findings that were decided
rather than fixed, so that nobody raises them again.

**`CLAUDE.md` is the unusual one.** 56 major sections carrying
**801 stated rules**, **526 flagged hazards** and **236
pointers to the test that guards each rule**. It records not just what the system
does but which apparent bugs are deliberate business decisions — so the next
person to touch the code cannot "fix" the business by accident. Every one of
those hazard entries was written after a real failure, and the count never
stopped rising: 326 in early September, 427 on 20 September, 526 at the
freeze.

**The system map is drawn, not written.** One build script emits both the light
and dark versions from a single set of coordinates, and a third copy as a Django
partial that the in-app About page includes, so no two can disagree. A checker
then verifies six things the eye cannot catch at that density: connectors
cutting through unrelated cards, connectors missing their target, anything
off-canvas, overlaps, long same-colour lines running too close, and every tap
landing on the bus it feeds. At the freeze it reports all six clear across 45
connectors, and re-running the build changes no committed file.

⚠ **The checker is geometric and reads no words.** A card's caption goes stale
exactly the way a count does, and nothing catches it — found in an earlier pass,
on the one card that had grown two whole documents since its caption was
written.

---

## 08 — Specifications & what makes it unusual

Not a feature list — those are in the README. These are the engineering
decisions that distinguish this system from a generic business application, each
one traceable to a real failure it prevents.

### Architecture

**One rule, one implementation.** Twenty-one modules contain no screens at all.
Each owns exactly one question — the profit maths, the printed document, the
service record, the rent calculation, the settlement checklist, the rename rule,
rupee validation, which day money moved, date-pair validation, the change
window, odometer parsing, photo signing, what this car already told us, whether
a VIN is a VIN, what markup to suggest, whether a pre-system bill is acceptable,
what that bill's own PDF says, where a page sends you when you leave it, which
address is the visitor's, whether a shop discount may be written, and which part
a warranty claim may be made on. Nothing else in 169,231 lines is
permitted to answer those questions a second time. The reason is specific: the
cost of a spare part was once calculated in five different places, giving a
shop's own page and the profit page two different answers for the same debt.
*21 modules · 7,771 lines*

**A warranty card is a job card underneath.** A part that failed after the car
left is claimed on a card of its own — free to the customer, never settled, with
its own number series — and it is an ordinary job card with one field set.
Mechanic, concerns, parts, stock draws, photos, the shop ledger and the profit
page's parts cost all work on it unchanged, so there is no second copy of any
money code. What makes it free is held in the model on every save, never trusted
to a screen. **The system never decides whether a part is covered**: it shows
the part's age to the day, measured from the first bill it was fitted on — a
claim never restarts the clock — and the owner decides.
*One claim is one part, linked to the exact part it replaces.*

### Money and stock integrity

**A part is paid for exactly once.** A spare reaches a car by one of two routes —
bought from a spare shop for that job, or drawn from warehouse stock already paid
for by a supplier bill. Charging both would overstate expenses by roughly ₹9.8M
against the test data. The route is **stored**, never inferred. It used to be
guessed from a name match, and the guess was made differently in two places, so
the shelf count drifted downward until a restock bill covered it up.
*Guarded by a dedicated test class.*

**Profit and cash are never added together.** They differ by five things at once
— stock bought but unused, stock used but bought earlier, bills unpaid, bills
paid from an earlier period, customer bills unpaid — so subtracting one from the
other produces a number that is not anything. Both appear on the same page and
are drawn as different kinds of object so they cannot be confused. Money taken
out by the owners is the sharpest case: it is real cash leaving the drawer and
**not an expense**, because profit is what is available to take and taking it
cannot make it smaller. Recorded as an expense, the error compounds — the page
reports less left to distribute, over money already distributed, and the next
distribution is decided from the smaller figure.
*It reaches exactly one figure in the whole engine: cash out.*

**What a month COST and how it got PAID are two different numbers.** The
workshop rents its premises for a fixed monthly sum and pays it in daily cash
instalments to a collector who keeps his own book. The rent is a fixed expense;
the deposits are cash movement. Collapse them and a month where the office had a
good week reports a *higher rent* than a month where it did not, so monthly
profit swings on a cash-flow decision rather than on what the month cost — and
the owners read monthly profit to decide distribution. It is the fourth time the
system has drawn this line, not a new idea: wages are dated by the salary month
and not the day the cash left, a supplier payment never touches profit while the
stock draw does, and a spare-shop payment never touches profit while the part
fitted does.
*Nothing is stored but the rate and the deposits; every other figure is derived.*

**A discount from a shop is a payment with no cash.** A shop owed ₹22,150 says
"just pay ₹22,000": that is a ₹22,000 payment and a ₹150 discount, and the shop
is settled. The discount is its own record — it settles the debt exactly as a
payment does, it is profit on the day it is given, and it never touches an
item's cost or the cash figures. It replaced a discount carried on the supplier
bill and shared into every line, which made a part's cost match no paper bill,
dropped the suggested customer price with it, and re-priced parts already fitted
when a discount was keyed late.
*A fleet discount was built the same way and removed the same day, on the owners' call.*

**Stock is allowed to go negative.** A job card records a part the mechanic has
already physically taken. Refusing that record does not put the part back on the
shelf — it only stops a mechanic mid-shift and makes the system disagree with
reality. The old clamp at zero never prevented an overdraw; it destroyed the
evidence of one, and silently invented three units of stock when the missing bill
arrived. A negative balance is self-healing and is the signal that a supplier
bill has not been keyed.
*Reported separately from "low stock" — the two counts are disjoint.*

**Cost is a full replay, never an increment.** Warehouse cost is a weighted
average, recomputed date-ordered from every receipt each time one changes. There
is deliberately no fast incremental path, because a moving average is
path-dependent and cannot be un-averaged — a fast version and a correcting
version would be two answers to one number. It matches how the workshop actually
operates: a supplier delivers, keeps their own book, and the bill is keyed weeks
later when the collector comes.
*Per-batch cost is still retained, so true FIFO remains reconstructable.*

**Every typed rupee passes one gate.** A figure too large for its column is
silently accepted by SQLite and rejected by PostgreSQL with a server error.
`Infinity` passes a naive "greater than zero" check and poisons every total that
touches the column. `NaN` makes that same check raise, crashing the page. One
corrupts, one crashes. A single module refuses all three before either can
happen, and reads the acceptable bound from the database column itself rather
than restating it. The gate is deliberately not allowed to round a figure up
into validity — that would be the system saving a number nobody typed — so each
screen makes the final call itself, in one line.
*Wired into every screen where money is typed.*

**Money is dated at both ends.** Nothing that moves money can be dated ahead of
today — a job card mistyped into next year lifts a whole job out of the month
that earned it and then *hides* it, because the year-to-date window ends on a
calendar boundary the card now sits past. The other end is quieter and needed
its own rule: a figure dated three years back rewrites the running position of
every month since, on rows nobody scrolls to, and reports nothing. Office may
date money at most **three days** back — enough for yesterday's receipt typed
this morning and a Saturday found on Monday, and short enough that nobody can
quietly move an entry into a month the owners have already read. Anything older
is an owner's to record, and the other owner is told on their phone.
*One implementation, ten screens, and every back-dated entry is announced — the bell inside the three days, the other owner's phone past them.*

**The system installs into a workshop that is already running, and says so in
the schema.** Parts are on the shelf and money is owed to every shop on the day
it starts, and neither can arrive through a daily screen — stock only moves
through a supplies bill, and a shop's balance is built from purchases recorded
against it. Two go-live screens take the starting position once. The opening
shelf count is **always the first event in the costing replay**, whatever day it
was typed, so a part drawn before the count was finished is still costed from
it; and its cost is **required**, because without one every part used before
that product's next bill would be charged ₹0 on the profit page permanently — a
later-dated bill never reaches back. An opening balance is the oldest debt a
shop has, so all three payment waterfalls clear it first.
*The shelf and the balances are typed separately: on day one they have no connection, and inventing one would be a guess.*

**And then that door is bolted from the inside.** Once the figures match the
count and the shops' books, an owner locks both screens behind three
confirmations that get louder. Afterwards they still *show* their figures and
refuse every change from everyone, owners included, enforced in the view rather
than by hiding the form. Nothing in the application can undo it — only a command
run on the server by whoever holds the deployment. **The lock is a database row
rather than a hosting setting**, and that was the owner's own correction to the
first design: a setting lives on the hosting account, so a backup restored
somewhere else, or the whole system moved to another host, would come back
silently open.
*The figures a business is measured from should not stay editable because nobody got round to closing them.*

**The server never works out a price.** A customer price is suggested at a
markup — 40% on a bought-in part plus its transport at cost, the product's own
figure off the shelf — and that arithmetic lives in the browser, in whole paise,
written into ordinary boxes that reach a bill only when a person presses Save.
Computing it on save was the obvious build and would have moved money four ways
nobody decided: it would price the parts the floor records with no price,
silence the settle check's "no customer price", reprice an unlocked settled
card, and move old bills every time a late supplier bill re-costed the shelf. A
test asserts the server prices nothing; if it fails, the arithmetic has moved
back.
*`700 × 1.1` is `770.0000000000001` in JavaScript, which is why the maths is integers and why it has its own unit tests.*

**A settled month cannot be walked backwards.** Salary months have three states:
open, locked, and closed. Closure is a **stored one-way flag**, not a computed
"is this the latest?". The computed version looked tidier and was a ratchet that
turned both ways — deleting the newest settlement handed the frontier back to the
month before it, so an entire history could be unwound one delete at a time. It
was observed doing exactly that: thirteen settled months down to ten.
*Enforced in the view, not only the template.*

### Security

**Two lockouts, in different units.** Five failed attempts lock a single account
for fifteen minutes. Twenty failures from one visitor's address is the backstop.
The network threshold was deliberately *raised* from five, because the unit was
wrong for this business: the laptop, the tablet and both owners' phones leave
through one connection, so five fumbled attempts on the shop-floor tablet locked
the owners out of their own devices. **Which address is the visitor's is one
rule in one module**: behind the host's proxy the address the server sees is the
proxy's own, so every visitor shared one counter and every alert named the
proxy. The forwarded header is now trusted only when the connection came from
inside the host's own network, and ignored from anywhere else, so it still
cannot be spoofed.
*Per-account lockout is what stops guessing; the network gate catches a spray.*

**Owners are nameable only by email.** Sign-in accepts a username, an email or a
mobile number — except for owner accounts. The workshop's published phone number
was a valid owner identifier, and five wrong guesses locks an account, so anyone
who could name an owner could lock that owner out on demand. The refusal is
enforced at the authentication call itself, not merely hidden at the form —
otherwise a refused identifier would still have been handed straight to the login
backend.
*Password recovery is deliberately left generous — different threat, different rule.*

**Getting in always reaches a phone.** Every sign-in raises a critical alert to
the *other* owner. An owner's own sign-in was informational until August, on the
reasoning that it is routine — until the obvious question was asked and had a bad
answer: **a sign-in on an owner account with a stolen password reached no phone
at all.** The reset flow was alarmed; simply knowing the password was not. It is
safe at critical for a measured reason rather than a hopeful one: the session
cookie lasts forty days, so a signed-in phone stays signed in and this fires on a
genuinely new device — one or two a month across two owners.
*The actor is always excluded, so what arrives is always "somebody else signed in".*

**A six-digit code, not a reset link.** Django's built-in emailed reset link is
less code and better tested, and it was the original plan. It was rejected for
one reason: on iOS an installed home-screen app has its own cookie jar, so a link
tapped in the mail app completes the reset in Safari and returns the owner to the
app still signed out. The code is placed in the email *subject* line, so it is
readable from the phone's notification banner without opening the mail app. The
owners read these on iPhones.
*Throttled, single-use, expiring — and it clears the account lockout.*

**Signed-in pages are never stored.** Logging out flushes the session, so the next
request is bounced — but the browser Back button never makes a request. It
restores the page from cache, fully rendered: the dashboard, a customer's bill,
the profit page, on a laptop now in someone else's hands. Nothing server-side can
undo that after the page has been sent, so authenticated responses are marked
never-store.
*Accepted cost: Back re-fetches instead of restoring instantly. Owner accounts
also cannot enter the Django admin at all, deliberately.*

### Records and evidence

**Two verbs for removal, never one.** Accounts that other records point at —
shops, fleet accounts, staff — are archived, never deleted, because deleting one
would cascade away its entire financial ledger. Transactions are permanently
deleted, but every deletion first writes a snapshot to an owner-only, read-only
history. There is deliberately no restore: reviving stale financial data corrupts
running balances.
*16 record types · one shared entry point · every delete notifies both owners.*

**The years before the system are typed in, and joined to nothing.** About eight
hundred bills were written in Excel before this existed, and they are entered so
that a car's profile, its printed service history and its all-bills PDF reach
back to its first visit rather than starting on the day the workshop switched
over. They touch **no** profit figure, no cash figure, no stock and no shop
balance: those months happened outside the system, and counting them now would
rewrite periods nobody can check. A test holds an allow-list of the only files
permitted to mention the model at all and fails the moment another one does —
adding a file to that list is a decision, not a fix for a red test. The bills
also shared the system's own numbering, so one sequence now spans both: a live
job card skips any number an old bill holds, and an old bill cannot take a
number that belongs to the live series.
*Where the bill was saved as a PDF, the PDF fills the form — and saves nothing until a person has looked at it.*

**A correction and an anomaly are different acts.** Office can change or delete
a money record within 24 hours of entering it; anything older is an owner's to
change, and a change made past that reaches the other owner's phone. One window
covers both doors, because an edit that retypes ₹50,000 as ₹500 is a delete by
another name. It is measured from when the row was *entered*, never from the
date the money carries — because back-dating is normal here, and on the money
date Office would be refused permission to fix their own typo thirty seconds
after making it. The refusal names the rule, the age of the row and who to ask,
and a list row too old to change says so in its own menu.
*An escalation, not a wall — no approval queue, no second sign-off.*

**Where prevention stops, detection starts — and the trace is kept.** Every guard
in the system escalates to an owner, and nothing can refuse an owner — so at
that boundary the model changes rather than the rule getting stricter. An owner
who dates money past the three days sends a critical alert to the *other* owner
within seconds. A notification is a feed that forgets, so what was changed is
also **kept**: one Change History page, in three tabs — what was deleted, what
was edited (each money figure before and after), and what was typed in on a
later day than the money moved. A same-day correction in the Cashbook or the
rent log is the one thing left out: there it is the day's work, not a change. The back-dated tab stores nothing of its own; it
reads the two dates every money row already keeps, so it cannot disagree with
them.
*An approval queue in a two-owner workshop is machinery nobody would use.*

**Photographs never touch the server.** The browser uploads straight to object
storage on a signed URL, so an upload on poor workshop wifi never occupies a web
worker. The signing is written against the standard library and pinned to
Amazon's own published test vector — the only way to verify it without a live
bucket. Signing and recording are separate steps, in that order. The obvious
design records first, which leaves a row pointing at a photo that does not exist.
This way **a row always means a real photograph**, and the cost is an
unreferenced file that a sweep collects.
*Photos are frozen when the bill is settled — money and evidence stop moving together.*

### Customer-facing documents

**The printed bill loads nothing.** No external stylesheet, no external script,
no icon font. Everything inline, including the letterhead as embedded artwork at
600 DPI. A framework update shipping upstream could otherwise move a column on a
customer's bill, and a workshop printing on a dropped connection would get an
unstyled page. The bill, the estimate and the warranty slip are produced by
**one module**, so where they agree they agree exactly — and the bill and the
estimate diverge in precisely two columns, for a stated reason: a bill records
work that happened, an estimate describes work that has not.
*Screen controls live outside the printed sheet entirely, not merely hidden.*

**Every bill for one car is the same bill, not a copy that looks like one.** The
tempting build for "send me all my invoices" is a second template laying a bill
out the same way. It would look right on the day and drift on some later one — a
column width, a rounding, a label — and the *customer* would find it, holding
both documents at once. So the markup was extracted the way the arithmetic
already had been, and a test renders one job card through both routes and asserts
the two sheets match **character for character**.

**A document is set from another document, not by eye.** The service-history
sheet wore the bill's letterhead and still read as generic. Every size and every
colour on it was legal against the stated rule, audited and true. Measuring the
two *rendered* documents element by element — rather than reading either
stylesheet — found what neither audit could: **the sheet was set in bold and the
bill is not**, 166 bold elements against the bill's five, with eleven-point
regular painted not once. Green went with it, because green means *money* in this
system and this document carries no payment state at all.
*The rule now has three clauses: no size, no colour, and no weight the bill does not already use.*

**A saved bill is named for the car.** The page title is the file name, so a PDF
saved from any document reads make, model, plate and number — searchable in a
folder of hundreds. It is letters, digits, spaces and dashes only: brackets are
legal on every file system, and still made two AI tools refuse the file as
empty. iOS ignores the title outright, so pressing Print also copies the name
for the owner to paste — and if that copy fails, Print says so *before* the
print box opens, because a paste would otherwise name this bill after the
previous car.
*Windows' own "Microsoft Print to PDF" always opens with a blank name; the browser's "Save as PDF" does not.*

### Interface

**Three devices, three roles, one interface.** Office works on a laptop, the
floor on a tablet, the owners on phones. Every hover effect is gated to devices
that actually have a pointer; touch targets are sized by input method rather than
screen width, because the shop-floor tablet is wider than many laptops. The
navigation bar moves to the bottom of the screen on phones — the same element,
repositioned, because the top edge is the hardest place on a phone for a thumb.
*One navigation menu in the whole app, deliberately.*

**A control drawn on four screens is one control.** The card that records a
payment appears on the spare shop, the Supplies Shop, the fleet account and the
owner withdrawals page. It was four near-copies kept in step by hand, and they
had already drifted three different ways — one of them 397 px of content in a
343 px box. It is now one declaration in the shared stylesheet; a variant sets
two colour values and nothing else.
*Red moves money out, green takes money in — the same rule the profit page uses.*

**Every page carries its own way out.** The installed app has no address bar and
no browser Back button, and a laptop has no system back gesture either. There
were seventeen back controls in seven visual treatments across two placements —
including four that called browser history, which does nothing at all on the
first page of a session, and one page that rendered no way out whatsoever. They
are now one control, on 33 templates, that **names its destination**. A global
back button in the navigation bar was asked for and deliberately not built:
measured at 375 px the bar is five equal columns with no free slot, a sixth tab
costs every existing tab 17% of its width, and roughly twenty pages would then
carry two back affordances.
*The measurement is the argument — the request was reasonable and the numbers refused it.*

**The app asks its own questions.** Twenty-one browser dialogs were replaced by
one card. They opened with "127.0.0.1:8000 says", which is the browser talking
rather than the app, and rendered the question, the reason and the way out as one
flat grey block that can carry no icon, no colour and no field. The replacement
found a real defect on the way in: a card inherits the visibility rules of the
screen it opens on, and the card then asked by Mark Completed — pressed mostly
from the shop-floor tablet — was explaining what would happen to *the bill*, to
somebody shown no money anywhere in the system. The same card now carries a
single short box when a question needs a number, such as how many days a shop
said an ordered part would take.
*Two native dialogs survive, both deliberate fallbacks for a page whose script never arrived.*

**One press is one post.** Reported from the shop: on a slow connection the same
Confirm was tapped again and again, and every tap was another submission — a
payment deleted twice, an advance deleted twice. The app-wide guard listens for a
submit *event*, and nine dialogs post by calling the form directly, which fires
none — so the screens where a second press costs the most had no guard at all.
The fix wraps the browser's own form-submit method once, rather than restating
the rule in nine templates.
*Painted with pointer-events, never `disabled` — a disabled control is dropped from the payload.*

**Five tones, wired to nothing.** Success, error, warning, question and shutter
each have a synthesised tone, and the first four are carried by an attribute on
the message banner. Because the app already tags every outcome, one attribute
covers every action in the system — and anything added later. Per-button sounds
were rejected: roughly 230 places to attach the wrong tone, each firing at click
time, announcing "done" before the server had done anything.
*Informational messages are silent — a tone for everything trains people to hear nothing.*

### Alerts

**One catalogue, one entry point.** Twenty events, defined in a single file,
raised from twenty-nine places. Severity is a delivery tier rather than decoration:
fifteen push to the owners' phones, five land only in the in-app feed. For money
the tier is decided by the record, never the person: anything Office is allowed
to do reaches the bell, anything only an owner can do reaches the other owner's
phone. A notification's address is permanent, so the rule is that a bad one is
fixed by making that address work — never by repointing the next alert, which
does nothing for every alert already sent.
*Push runs off the request path entirely — a dead push service cannot slow a payment.*

**A row is three strings, and each answers a different question.** What happened,
what category it belongs to, and the context read second. The loud line carries
what *differs* between rows — it used to carry the category, so nine consecutive
alerts opened with "Record deleted" in bold and the ₹1,00,000 sat in smaller,
greyer type underneath. The same fault reached the lock screen, where a push had
been sending the category as its bold line.
*A push carries no replace-key: it once carried a constant one, so each alert deleted the one before it.*

### Discipline

**Traps are written down.** 526 hazards are documented, each one a
failure that produced no exception, no console error and a green test suite — a
running CSS transition outranking an important rule; a cached deletion list in a
form set; a date built in UTC reporting yesterday for an entire Indian morning;
a framework that centres a dialog only above a certain screen width. They are
recorded so the next person does not have to rediscover them, and 236
rules carry a pointer to the exact test that guards them.

**A number written down is a number going stale.** Every count in these documents
is re-derived rather than trusted, because they have drifted repeatedly and
always the same way: a feature lands and the tables are not recounted. The pass
that produced this revision found a go-live step promising a warning that had
been removed three weeks earlier, two pointers to issues that no longer exist,
an owner's question listed as still open eighteen days after it was answered,
and one document contradicting itself on how long the test suite takes.
*The lesson is written into the documents themselves: re-derive before quoting.*

**Built for its actual load.** About thirty cars a month, six or seven staff, two
owners. That is why access control needs only three tiers, why the cashbook is
weighted for a ledger that is 98% expenses, and why performance is judged
against realistic load rather than generic assumptions. Scope deliberately left
out — customer-facing messaging, attendance, multi-mechanic assignment, general
file attachments — is written down as excluded, so proposing one is understood
as proposing scope, not reporting a defect.
*Same database engine in development and production, so differences surface while cheap.*

---

## 09 — Headline figures

| | |
|---:|---|
| **169,231** | lines of code across 510 files, in a single deployable system |
| **3,185** | automated tests — 1.34 lines of test for every line of application code |
| **49** | data models holding 360 fields, reachable through 324 addresses |
| **140** | screens, each built to work on a laptop, a tablet and a phone |
| **21** | rule modules, each the only place in the system that answers its question |
| **191** | access checks across three roles — owner, office, floor |
| **72** | all-or-nothing transaction blocks guarding every movement of money |
| **196,784** | words of documentation across ten documents and a drawn system map |
| **9** | runtime dependencies — no build step, no package manager, no bundler |
| **294** | commits over nine months, by one developer |

> **The one-line version:** a 169,000-line Django system running a
> premium automotive workshop end to end — job cards, inventory, supplier and
> spare-shop ledgers, fleet billing, payroll, rent, estimates, warranty claims,
> evidence photography, printed service records, owner withdrawals and owner
> analytics — with a test suite larger than the application it tests, and every
> deliberate business decision written down with the failure it prevents.
>
> It was built to be switched on in a workshop already running — the years
> billed in a spreadsheet typed in as history, the shelf and the shop debts that
> existed on day one entered once and then locked. It never was: it is frozen
> here as the specification its rebuild is measured against.

---

## Method

Counted from the working tree on 9 October 2026, on branch `main` at `3f82f77`
plus the documentation changes that accompany this revision, including this
document.

- File counts cover every file tracked in version control. That now includes the
  committed development database, counted as one binary file. Working files
  outside version control are named in section 01 and excluded.
- Line counts exclude binary files, which are reported by size. A line is
  `len(text.splitlines())`. Word counts split on whitespace.
- **The counter was checked against the September revision before it was
  trusted.** Run on that revision's own commit (`ef390e2`) it reproduces the
  published total exactly — 464 files, 152,392 lines — so the file, line and
  test figures here compare like with like.
- Vendored third-party libraries are counted as files but excluded from language
  percentages.
- CSS and JavaScript written inside template files is attributed to those
  languages, not to HTML. ⚠ **The inline counter is new in this revision**: it
  takes the content between a `<style>` or `<script>` tag pair, and counts the
  tag lines themselves, empty blocks and `src=` scripts as HTML. The September
  sheet's counter was not kept; run on the September commit the new one reads
  19,189 CSS and 6,441 JavaScript lines where the published sheet said 19,301
  and 6,495, so section 02's figures are not comparable with that revision's.
- The test count comes from Django's own suite builder; model, route, field,
  form, event and record-type counts come from loading the application and
  querying it. Decorator, transaction and row-lock counts exclude test files.
- **Three counts are corrected, not grown**, each by the rule that a figure must
  describe what its label says:
  - *Form classes:* the September 14 included a widget, a field and a choice
    iterator. Counting only form classes it was 11; it is 12 now.
  - *Deletable record types:* the September 15 counted the list of record types
    as a type. It was 14; it is 16 now, with the two shop discounts.
  - *Row locks:* the September 10 counted every mention, comments included. In
    code it was 7; it is 12 now.
- **Corrections made at source by this run**, in the documents that own each
  fact rather than only here:
  - `GO_LIVE_RUNBOOK.md` — the go-live step for the last Excel bill number told
    the reader to watch for an amber "not set yet" warning that was removed on
    17 September, so a missing variable would have looked like a set one. It now
    says the one line on the page is the only check. The same file pointed at a
    technical-debt entry that no longer exists, listed the purge without the
    shop discounts or opening stock, and gained two smoke tests: saving a PDF on
    a real iPhone — the one part of the print-name copy never checked on one —
    and a warranty claim.
  - `TITAN_MASTER_HANDOVER.md` — marked final; the module counts (21 view
    modules and 15 rule modules, against 24 and 21); an owner question listed as
    still owed that was answered on 21 September; a second pointer to a deleted
    technical-debt entry; the late deliveries missing from the roadmap — shop
    discounts, parts transport, the rest of Warranty and the owners' last
    requests.
  - `CLAUDE.md` — marked final; the back control's template count (23, now 33),
    the dialog counts (18 of 37, now 22 of 38), the inline CSS and JavaScript
    sizes, and a contradiction about the test suite's duration — "the slowest
    measured run took 82 minutes" in one section, a recorded 2 h 30 m run in
    another. `MASTER_BLUEPRINT.md`, `README.md`, `RAILWAY_OPERATIONS.md` and
    `OPERATIONAL_BLUEPRINT.md` carried the same counts and got the same fixes.
  - `WorkshopOS_Complete_Structure.md` — the Warranty section, shop discounts,
    parts transport, the expected-days question and the warranty lines on the
    Profit page, the Live Report and Deep Analysis.
  - **This document** had five statements gone false since September, beyond
    its numbers: the network lockout described as ignoring forwarded headers,
    which stopped being true on 21 September; a rent-screen row mark and a
    "recently added" view that were replaced by Change History on 24 September;
    back-dating guarded on "seven screens", which is ten; "roughly fifty cars a
    month", which is thirty; and tax handling listed as deliberately left out,
    which came back into scope on 13 September.

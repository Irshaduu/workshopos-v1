"""
Warranty — free work on a car because of an EARLIER bill (2026-10-02, the
owners' design).

⚠ ONE CLAIM IS ONE PART (the owners' rule, 2026-10-07). A claim is a warranty
card for ONE failed part from ONE earlier bill. Its part is copied from that
bill and remembers the EXACT part it replaces
(`JobCardSpareItem.replaces` / `replaces_line`). That link is what makes a
part's history readable:

* a part with an OPEN claim says "Being claimed" and cannot be claimed again;
* a part whose claim is FINISHED says "Replaced": the new part is the one on
  the car now, so a second failure is claimed on THAT part, under the warranty
  card that fitted it — never on the old bill again. The new card then says
  "2nd claim".

Anything the repair needs that was NOT on the earlier bill goes on an ordinary
job card and is billed — the owners' rule — so a claim card carries its one
part and nothing else.

⚠ THE WARRANTY CLOCK RUNS FROM THE FIRST BILL, AND A CLAIM NEVER RESTARTS IT
(the owners, 2026-10-08). A part fitted on JB-26-005 that failed and was
replaced on WR-26-018 is still under JB-26-005's warranty: the replacement
carries what is left of it, not a new one. So every age and every "km since"
a claim is judged by is measured from `first_bill` — the bill the part's chain
started on — never from the warranty card that fitted the replacement, whose
own date would make a part fitted 8 months ago look 3 months old. (A SHOP's
own warranty on the replacement is a different clock; its dates are on the
part's own line.)

⚠ THERE IS NO CLAIM FOR THE WORK ALONE (the owners, 2026-10-08). A fix with no
part — a clamp re-tightened, an alignment redone — is done without a card:
nothing is ordered, nothing waits, nothing costs. A part is what makes a claim
worth tracking.

THE ONE ANSWER to these questions:

* which cars can a claim be made for? — `claimable_cars`, the New claim
  screen's car list;
* which bills of this car are there, which of their parts can be claimed, and
  which already are? — `bills_for`;
* open a claim for this part — `open_claim`;
* which warranty cards were opened against these bills? — `claims_for`, read
  wherever an earlier bill names its claims (a shield and "WR-26-003");
* which part does this card claim, and which claim of it is this? —
  `claimed_part`, `claim_round`;
* which bill does the warranty clock run from? — `first_bill`;
* may a finished claim be put back on the floor? — `reopen_conflict`.

and two about a card already open: how far the car has run since the bill its
warranty clock runs from (`km_since`, given `first_bill`), and whether a claim opened by mistake may still be
cancelled (`cancel_refusal`, `cancel_warranty`).

and the Warranty page's figures: which parts are still waiting for a shop price,
and what warranty work cost.

A warranty card is a `JobCard` with `kind=WARRANTY` and its own WR-YY-NNN
number. `JobCard.save()` and `update_totals()` hold its money rules (the
customer pays nothing, it is never settled); this module holds how one comes
into being. The link to the earlier bill is `warranty_for` — the earlier
bill's NUMBER — and the link to the part is on the claimed part; both are
written once, here, and never by a form.

⚠ THE EARLIER BILL MAY BE AN EXCEL-ERA OLD BILL, and that is the one place
anything outside the Old Bills screens reads that table for a job card. It is
safe for the reason the number is enough: a JB number exists ONCE across job
cards and old bills, so `warranty_for` names either exactly, and nothing is
written to the old bill. Old bills still move no money and are pointed at by
nothing. This file is on `OldBillsAreConnectedToNothingTests.ALLOWED` for that
reason, by decision.

⚠ THE SYSTEM NEVER DECIDES WHETHER A PART IS STILL UNDER WARRANTY. There is no
expiry date anywhere. The start page shows how old each bill is, and the owner
decides — a rule this system enforced would be a rule nobody at the workshop
agreed.
"""
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from django.db import transaction
from django.db.models import Count, Max, Prefetch, Q, Sum
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

from .analysis_engine import MONEY, PART_COST, ZERO
from .known_car import known_car
from .mileage import parse_km
from .models import JobCard, JobCardSpareItem, OldBill, OldBillPartLine, live_cards


class WarrantyRefused(Exception):
    """Raised by `open_claim` with the sentence to show the person."""


@dataclass
class EarlierBill:
    """One bill a warranty card can be opened against, ready to print."""
    number: str
    date: date                       # the DATE printed on that bill
    registration: str
    brand: str
    model: str
    customer_name: str
    customer_contact: str
    is_old_bill: bool                # an Excel-era bill, typed into Old Bills
    is_warranty: bool                # itself a warranty card (a repeat claim)
    is_done: bool                    # the car has left (always, for an old bill)
    mileage: str                     # the odometer reading on that bill, as typed
    # The parts a claim can be about, for the claim screen — each a `_part`
    # dict (`key`, `name`, `meta`, `status`, `claim`, `newer`, `round` …). A
    # job card's spare-shop parts are `shop_parts` and its warehouse draws
    # `stock_parts` (the screen folds those away: a stock part is rarely
    # claimed). An old bill's lines are all `shop_parts` — the paper never split
    # the two. `key` is what a part's Claim button posts ("c12" a card's part,
    # "o7" an old bill's line) and `rows` maps it back to that record, which is
    # what `open_claim` copies onto the new card. `status`, `claim` and `newer`
    # are filled by `bills_for` — see there.
    shop_parts: List[dict] = field(default_factory=list)
    stock_parts: List[dict] = field(default_factory=list)
    rows: dict = field(default_factory=dict, repr=False)
    pk: Optional[int] = None
    # The bill's own page (Office/Owner): a job card's read-only page, an old
    # bill's reprint, a warranty card's claim card — so "For WR-26-001" opens
    # the 1st claim itself.
    url: str = ''
    warranty_for: str = ''           # a warranty card's earlier bill — the chain's link
    # The bill the warranty clock runs from (`first_bill`): itself, unless this
    # is a warranty card. Filled by `bills_for`.
    first: Optional['EarlierBill'] = field(default=None, repr=False)
    round_label: str = ''            # a warranty card's own claim, a repeat only: '2nd claim' …


def tidy_number(text):
    """'jb-26-007 ' → 'JB-26-007', the way both tables store a number."""
    return ''.join((text or '').split()).upper()


def age_phrase(then, today=None):
    """
    How long ago a bill was, to the DAY: 'today', '3 days', '1 month 3 days',
    '1 year 2 months 5 days'. To the day because a warranty is decided at its
    edge — "5 months 28 days" and "6 months 2 days" are the whole question
    (the owners, 2026-10-08). No "ago": it is always printed after the date it
    is measured from — "JB-26-005 · 1 Sep 2026 · 1 month 7 days" — which says
    it already.

    Calendar months, not 30-day blocks: a bill from the 12th of March is "7
    months" old on the 12th of October, and the days are what is left after
    the last whole month (a month landing on a shorter month's end stops at
    that end — 31 Jan + 1 month is 28 Feb). A part left at zero is not said.

    Nothing for a date in the future — that is a typo upstream, and the page
    prints the date alone rather than an age that cannot be true.
    """
    today = today or timezone.localdate()
    if then is None or then > today:
        return ''
    if then == today:
        return 'today'
    months = (today.year - then.year) * 12 + (today.month - then.month)
    if today.day < then.day:
        months -= 1
    year, month = divmod(then.month - 1 + months, 12)
    year, month = then.year + year, month + 1
    last_whole_month = date(year, month, min(then.day, monthrange(year, month)[1]))
    days = (today - last_whole_month).days
    years, months = divmod(months, 12)
    words = []
    for count, one, many in ((years, 'year', 'years'), (months, 'month', 'months'),
                             (days, 'day', 'days')):
        if count:
            words.append(f'1 {one}' if count == 1 else f'{count} {many}')
    return ' '.join(words)


def _qty(value):
    """A quantity the app's one way — 1.00 → "1" — or '' for none."""
    from .templatetags.custom_filters import clean_qty
    return str(clean_qty(value)) if value is not None else ''


def _spares():
    """A card's parts with everything the claim screen prints, in the order
    they were entered — so building a bill costs no query per part."""
    return Prefetch('spares', queryset=JobCardSpareItem.objects
                    .select_related('shop', 'item__category').order_by('pk'))


def _lines():
    return Prefetch('part_lines', queryset=OldBillPartLine.objects.order_by('pk'))


def _part(key, name, shop, kind, qty, meta):
    """One part as the claim screen prints it. `meta` is the pieces of the
    line under its name (`_meta`). `status`, `claim` and `newer` start empty and are filled by
    `bills_for`."""
    return {'key': key, 'name': name, 'shop': shop, 'kind': kind, 'qty': qty, 'meta': meta,
            'status': '', 'claim': None, 'newer': '', 'round': 1, 'round_label': ''}


def _meta(*bits):
    """
    The line under a part's name — "× 2 · Biljo · 01/01 – 10/01 · ₹14,500":
    the facts an owner matches against that shop's own ledger, so the part is
    found there in seconds. Returned as its PIECES, missing ones dropped, so a
    missing fact takes its separator with it and a phone breaks the line
    between pieces, never inside a date or a price.

    The dates are the read-only job card's own (`spare_dates.date_pair`, the
    year dropped when it is the bill's), and the figure is the SHOP PRICE —
    what the shop billed, the ledger's own figure — never the customer price.
    A stock part has no shop, dates or ledger line, so it says its category; an
    Excel bill's line has none of them either (its amount is what the
    CUSTOMER paid, a different figure), so it says only how many.
    """
    return [b for b in bits if b]


def _times(qty):
    """'× 2' — only above one, the workshop's own habit."""
    return f'× {qty}' if qty and qty != '1' else ''


def _from_card(card):
    from .spare_dates import date_pair
    from .templatetags.custom_filters import inr_amount
    year = card.admitted_date.year if card.admitted_date else None
    shop_parts, stock_parts, rows = [], [], {}
    for spare in card.spares.all():
        key = f'c{spare.pk}'
        qty = _qty(spare.quantity)
        if spare.source == spare.SOURCE_INVENTORY:
            item = spare.item
            name = item.name if item else (spare.spare_part_name or '')
            if not name:
                continue
            kind = item.category.name if item else ''
            stock_parts.append(_part(key, name, '', kind, qty, _meta(kind, _times(qty))))
        else:
            if not spare.spare_part_name:
                continue
            shop = spare.shop.name if spare.shop_id else ''
            price = f'₹{inr_amount(spare.unit_price)}' if spare.unit_price is not None else ''
            shop_parts.append(_part(key, spare.spare_part_name, shop, '', qty, _meta(
                _times(qty), shop, date_pair(spare.ordered_date, spare.received_date, year),
                price)))
        rows[key] = spare
    return EarlierBill(
        number=card.bill_number,
        date=card.admitted_date,
        registration=card.registration_number,
        brand=card.brand_name or '',
        model=card.model_name or '',
        customer_name=card.customer_name or '',
        customer_contact=card.customer_contact or '',
        is_old_bill=False,
        is_warranty=card.is_warranty,
        is_done=card.completed,
        mileage=card.mileage or '',
        shop_parts=shop_parts,
        stock_parts=stock_parts,
        rows=rows,
        pk=card.pk,
        url=reverse('warranty_card' if card.is_warranty else 'jobcard_detail', args=[card.pk]),
        warranty_for=card.warranty_for or '',
    )


def _from_old_bill(bill):
    shop_parts, rows = [], {}
    for line in bill.part_lines.all():
        if not line.name:
            continue
        key = f'o{line.pk}'
        qty = _qty(line.quantity)
        shop_parts.append(_part(key, line.name, '', '', qty, _meta(_times(qty))))
        rows[key] = line
    return EarlierBill(
        number=bill.bill_number,
        date=bill.bill_date,
        registration=bill.registration_number,
        brand=bill.brand_name or '',
        model=bill.model_name or '',
        customer_name=bill.customer_name or '',
        customer_contact='',   # an Excel bill never carried a number
        is_old_bill=True,
        is_warranty=False,
        is_done=True,
        mileage=bill.mileage or '',
        shop_parts=shop_parts,
        rows=rows,
        pk=bill.pk,
        url=reverse('old_bill_invoice', args=[bill.pk]),
    )


def find(number):
    """
    The bill with this number — a live job card (JB or WR) or an old bill — or
    None. A job card is looked for first; the two cannot share a number.
    """
    tidy = tidy_number(number)
    if not tidy:
        return None
    card = (JobCard.objects.filter(live_cards(), bill_number=tidy)
            .prefetch_related(_spares()).first())
    if card:
        return _from_card(card)
    bill = OldBill.objects.filter(bill_number=tidy).prefetch_related(_lines()).first()
    if bill:
        return _from_old_bill(bill)
    return None


def _first_of(bill, lookup):
    """Walk a warranty card back through `warranty_for` to the bill its chain
    started on — a job card or an Excel bill — with `lookup` turning a number
    into a bill. A link that cannot be followed stops the walk where it is; a
    cap stops a loop (none can exist — every link points at an older bill)."""
    hops = 0
    while bill is not None and bill.is_warranty and hops < 50:
        earlier = lookup(bill.warranty_for)
        if earlier is None:
            break
        bill, hops = earlier, hops + 1
    return bill


def first_bill(number):
    """
    The bill the warranty clock runs from, for a claim against this bill: the
    bill itself, or — when it is a warranty card — the bill its part was FIRST
    fitted on. See "THE WARRANTY CLOCK" above. None when the number is unknown.
    """
    return _first_of(find(number), find)


def _name_key(name):
    """A part's name compared the forgiving way: case and spacing ignored."""
    return ' '.join((name or '').split()).lower()


def bills_for(registration):
    """
    Every bill of this car, NEWEST FIRST — its finished job cards, warranty
    cards included (a replacement fitted under warranty can fail too), and its
    Excel-era old bills — with every part's place in the warranty story:

    * `status` 'claiming' + `claim` — an OPEN claim is on it; it cannot be
      claimed again until that one is finished or cancelled;
    * `status` 'replaced' + `claim` — a claim on it is FINISHED: the new part,
      on that warranty card, is the one on the car now, and a failure is
      claimed there;
    * `newer` — the number of a NEWER bill carrying a part of the same name
      (`_name_key`): the same part was fitted again later, so this one may not
      be on the car any more. A quiet note, never a block: the owner decides,
      and the claim link above is the only thing the system KNOWS.

    * `round` + `round_label` — which claim of this part a claim made NOW
      would be (or the open one is): 1 for a part from a job card or an old
      bill, 2 for a part a claim fitted ("2nd claim"), and so on — so the
      screen says "2nd claim" BEFORE it is pressed, not only after.

    And each bill's `first`: the bill its warranty clock runs from — itself,
    or for a warranty card the bill its part was first fitted on
    (`first_bill`'s rule, walked over the bills already loaded).

    A card still on the floor is left out: a part that fails before the car
    leaves is fixed on that same card, never under warranty.

    The same few queries whatever the car's history — cards, their parts, old
    bills, their lines, the claims on those parts — never one per bill.
    """
    plate = (registration or '').strip().upper()
    if not plate:
        return []
    cards = (JobCard.objects
             .filter(live_cards(), registration_number=plate, completed=True)
             .prefetch_related(_spares()))
    old_bills = (OldBill.objects.filter(registration_number=plate)
                 .prefetch_related(_lines()))
    bills = [_from_card(c) for c in cards] + [_from_old_bill(b) for b in old_bills]

    # Newest first, by the bill's own date. On a shared day the job card comes
    # before the old bill (old bills are older by definition), then the newer
    # record — so the order never depends on what the database returns. Sorted
    # BEFORE the "newer" pass below, which reads it top to bottom.
    bills.sort(key=lambda b: (b.date, not b.is_old_bill, b.pk or 0), reverse=True)

    claims = _claims_on(
        [row.pk for b in bills if not b.is_old_bill for row in b.rows.values()],
        [row.pk for b in bills if b.is_old_bill for row in b.rows.values()])

    # Which claim a part's NEXT claim is: 1 + the claims already in its chain,
    # walked through the parts loaded above (the chain is this car's own
    # bills), so it costs no query.
    on_warranty = {row.pk: row for b in bills if b.is_warranty for row in b.rows.values()}

    def claims_before(row, depth=0):
        if row is None or row.pk not in on_warranty or depth > 50:
            return 0
        earlier = on_warranty.get(row.replaces_id) if row.replaces_id else None
        if earlier is None and row.replaces_id:
            # The part it replaced is on a job card (or a warranty card this
            # list does not hold): this claim was the first.
            return 1
        return 1 + claims_before(earlier, depth + 1) if earlier else 1

    by_number = {b.number: b for b in bills}
    newest_with = {}   # a part's name → the newest bill it is on
    for bill in bills:
        bill.first = _first_of(bill, by_number.get)
        here = set()
        for part in bill.shop_parts + bill.stock_parts:
            row = bill.rows.get(part['key'])
            if bill.is_warranty and not bill.is_old_bill:
                # This card's own claim, and the one a press on its part makes.
                done = claims_before(row)
                bill.round_label = round_label(done)
                part['round'] = done + 1
                part['round_label'] = round_label(part['round'])
            claim = claims.get(part['key'])
            name = _name_key(part['name'])
            here.add(name)
            if claim:
                part['claim'] = claim
                part['status'] = 'claiming' if claim['open'] else 'replaced'
            else:
                part['newer'] = newest_with.get(name, '')
        for name in here:
            newest_with.setdefault(name, bill.number)
    return bills


def claimable_cars(query=''):
    """
    Every car a claim can be made for — every car with a FINISHED bill, a
    job card or an Excel-era old bill — newest bill first, as
    `{'plate', 'last', 'bills', 'car'}`. The New claim screen's list.

    The words typed find a car when ANY of its bills matches (plate, make,
    model, customer, bill number) — and the car is then counted over ALL its
    bills, never only the matching ones: filtering the grouped query itself
    is how the Car Profiles list once reported "2 visits" for a car of six.

    `car` (make and model) is filled for the cars a page shows, by
    `name_cars`, so a long list costs two grouped queries, not one per car.
    """
    cards = JobCard.objects.filter(live_cards(), completed=True)
    olds = OldBill.objects.all()
    words = (query or '').split()
    if words:
        card_hits, old_hits = cards, olds
        for word in words:
            card_hits = card_hits.filter(
                Q(registration_number__icontains=word) | Q(brand_name__icontains=word) |
                Q(model_name__icontains=word) | Q(customer_name__icontains=word) |
                Q(bill_number__icontains=word))
            old_hits = old_hits.filter(
                Q(registration_number__icontains=word) | Q(brand_name__icontains=word) |
                Q(model_name__icontains=word) | Q(customer_name__icontains=word) |
                Q(bill_number__icontains=word))
        plates = (set(card_hits.values_list('registration_number', flat=True))
                  | set(old_hits.values_list('registration_number', flat=True)))
        cards = cards.filter(registration_number__in=plates)
        olds = olds.filter(registration_number__in=plates)

    # `.order_by()` is load-bearing: an ordering field on a values().annotate()
    # joins the GROUP BY and counts every bill as one car.
    found = {}
    for plate, last, bills in (cards.order_by().values('registration_number')
                               .annotate(last=Max('admitted_date'), n=Count('id'))
                               .values_list('registration_number', 'last', 'n')):
        found[plate] = {'plate': plate, 'last': last, 'bills': bills, 'car': ''}
    for plate, last, bills in (olds.order_by().values('registration_number')
                               .annotate(last=Max('bill_date'), n=Count('id'))
                               .values_list('registration_number', 'last', 'n')):
        row = found.setdefault(plate, {'plate': plate, 'last': last, 'bills': 0, 'car': ''})
        row['bills'] += bills
        row['last'] = max(row['last'], last)
    return sorted(found.values(), key=lambda r: (r['last'], r['plate']), reverse=True)


def name_cars(rows):
    """Fill each row's `car` — the make and model of its newest job card, or of
    its newest old bill when it has no job card (old bills are older by
    definition). Two queries for the whole page."""
    plates = [row['plate'] for row in rows]
    names = {}
    for model in (OldBill, JobCard):          # the job card, read last, wins
        date_field = 'bill_date' if model is OldBill else 'admitted_date'
        query = model.objects.filter(registration_number__in=plates)
        if model is JobCard:
            query = query.filter(live_cards())
        for plate, brand, name in (query.order_by(date_field, 'pk')
                                   .values_list('registration_number', 'brand_name', 'model_name')):
            car = ' '.join(p for p in (brand, name) if p)
            if car:
                names[plate] = car
    for row in rows:
        row['car'] = names.get(row['plate'], '')
    return rows


def _claims_on(part_ids=(), line_ids=()):
    """
    The claims made on these parts (`JobCardSpareItem` pks) and old bill lines
    (`OldBillPartLine` pks), as `{key: {'number', 'pk', 'open'}}` with the
    claim screen's keys ("c12", "o7"). An OPEN claim outranks a finished one —
    there should never be both, but the open one is what has to be said. One
    query; nothing when there is nothing to ask about.
    """
    part_ids, line_ids = list(part_ids), list(line_ids)
    found = {}
    if not part_ids and not line_ids:
        return found
    rows = (JobCardSpareItem.objects
            .filter(live_cards('job_card__'), job_card__kind=JobCard.KIND_WARRANTY)
            .filter(Q(replaces_id__in=part_ids) | Q(replaces_line_id__in=line_ids))
            .order_by('job_card_id')
            .values_list('replaces_id', 'replaces_line_id', 'job_card__bill_number',
                         'job_card_id', 'job_card__completed'))
    for part_id, line_id, number, pk, done in rows:
        key = f'c{part_id}' if part_id else f'o{line_id}'
        if key in found and found[key]['open']:
            continue
        found[key] = {'number': number, 'pk': pk, 'open': not done}
    return found


_LINKED = Q(replaces__isnull=False) | Q(replaces_line__isnull=False)


def claimed_part(card):
    """The part this warranty card claims — its row linked to the part it
    replaces."""
    return (card.spares.filter(_LINKED)
            .select_related('replaces__job_card', 'item__category').order_by('pk').first())


def claimed_names(card_ids):
    """What each of these warranty cards claims, by name — `{pk: name}`,
    `claimed_part`'s rule. One query, for a list of cards."""
    names = {}
    for card_id, name in (JobCardSpareItem.objects.filter(_LINKED, job_card_id__in=list(card_ids))
                          .order_by('job_card_id', 'pk')
                          .values_list('job_card_id', 'spare_part_name')):
        names.setdefault(card_id, name or '')
    return names


def claim_round(part):
    """
    Which claim of this part this is: 1 for a part from a job card or an old
    bill, 2 when the part it replaces was itself fitted under warranty, and so
    on down the chain. None without a part. Capped, so a chain can never loop
    a request forever (it cannot by construction — every link points at an
    older part — but a cap costs nothing).
    """
    if part is None:
        return None
    count, earlier = 1, part.replaces
    while earlier is not None and count < 50:
        card = earlier.job_card
        if card is None or not card.is_warranty:
            break
        count += 1
        earlier = earlier.replaces
    return count


def round_label(count):
    """'2nd claim', '3rd claim', '11th claim' — said only for a REPEAT claim.
    The first is the ordinary case and needs no word (the owners, 2026-10-08):
    its button says "Claim", its card says nothing."""
    if not count or count < 2:
        return ''
    suffix = 'th' if 10 <= count % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(count % 10, 'th')
    return f'{count}{suffix} claim'


def reopen_conflict(card):
    """
    The card that stops this FINISHED warranty card going back on the floor
    (Undo Completion) — or None: another live claim on the same part — the
    open one that took its place — or a claim already made on THIS card's
    part, which only exists because this card's replacement was fitted.
    """
    part = claimed_part(card)
    if part is None:
        return None
    claims = JobCardSpareItem.objects.filter(
        live_cards('job_card__'), job_card__kind=JobCard.KIND_WARRANTY)
    later = claims.filter(replaces=part).select_related('job_card').first()
    if later:
        return later.job_card
    if part.replaces_id:
        twin = claims.filter(replaces_id=part.replaces_id)
    elif part.replaces_line_id:
        twin = claims.filter(replaces_line_id=part.replaces_line_id)
    else:
        return None
    twin = twin.exclude(job_card=card).filter(job_card__completed=False).select_related('job_card').first()
    return twin.job_card if twin else None


def old_bill_claims(bill):
    """
    The warranty claims made on this Excel-era old bill's lines, oldest first,
    as `[{'spare', 'name', 'number'}]` — the claimed part's pk, the line's name,
    and the claim's WR number. One query. Read by the Old Bills screens, which
    must not break a claim's link (`old_bill_edit_problems`,
    `repoint_old_bill_claims`) and must not delete a claimed bill.
    """
    rows = (JobCardSpareItem.objects.filter(replaces_line__old_bill=bill)
            .order_by('pk')
            .values_list('pk', 'replaces_line__name', 'job_card__bill_number'))
    return [{'spare': pk, 'name': name, 'number': number} for pk, name, number in rows]


def old_bill_edit_problems(claims, parts):
    """
    Why this edit of an old bill may NOT be saved — a sentence per claimed line
    it would remove or rename. `claims` is `old_bill_claims`; `parts` the
    edit's `(name, quantity, amount)` rows. A claimed line's quantity and
    amount may still be corrected; its NAME is what the claim copied.
    """
    kept = {_name_key(name) for name, _qty, _amount in parts}
    problems, said = [], set()
    for claim in claims:
        key = _name_key(claim['name'])
        if key not in kept and key not in said:
            said.add(key)
            problems.append(f"{claim['name']} is claimed under warranty on {claim['number']} — "
                            f"it can't be removed or renamed on this bill.")
    return problems


def repoint_old_bill_claims(claims, bill):
    """
    After an old bill's lines are written again (the Old Bills edit replaces
    them), point each claim back at the line of the same name — so the edit
    keeps the bill's printed order AND the claim keeps its part. Inside the
    caller's transaction; `old_bill_edit_problems` has already made sure every
    claimed name is still there.
    """
    if not claims:
        return
    by_name = {}
    for line in OldBillPartLine.objects.filter(old_bill=bill).order_by('pk'):
        by_name.setdefault(_name_key(line.name), line)
    for claim in claims:
        line = by_name.get(_name_key(claim['name']))
        if line is not None:
            JobCardSpareItem.objects.filter(pk=claim['spare']).update(replaces_line=line)


def claims_for(numbers):
    """
    The warranty cards opened against each of these bills, as
    `{bill number: [{'number', 'pk'}, ...]}`, oldest claim first. One query,
    however many numbers.

    THE EARLIER BILL STORES NOTHING. This lookup on `warranty_for` IS the link
    back, so the two ends can never disagree — there is no second copy of the
    link to fall out of step. Plain dicts, not cards: every reader prints the
    number and links by pk, and nothing else.
    """
    wanted = [n for n in numbers if n]
    found = {}
    if not wanted:
        return found
    rows = (JobCard.objects
            .filter(live_cards(), kind=JobCard.KIND_WARRANTY, warranty_for__in=wanted)
            .order_by('pk')
            .values_list('warranty_for', 'bill_number', 'pk'))
    for earlier, number, pk in rows:
        found.setdefault(earlier, []).append({'number': number, 'pk': pk})
    return found


def waiting_on_shop():
    """
    Every warranty part still waiting for the shop's answer, OLDEST FIRST —
    the top of the Warranty page, never filtered by date or search.

    THE SHOP'S ANSWER IS THE SHOP PRICE BOX: blank is waiting, ₹0 is free, an
    amount is what the shop charged. So "waiting" is exactly a spare-shop part
    on a warranty card with no Shop Price — on an open card or a finished one,
    because a shop often answers after the car has gone. A warehouse draw is
    never waiting: it came off our own shelf at a known cost.
    """
    return list(
        JobCardSpareItem.objects
        .filter(live_cards('job_card__'), job_card__kind=JobCard.KIND_WARRANTY,
                source=JobCardSpareItem.SOURCE_SHOP, unit_price__isnull=True)
        .select_related('job_card', 'shop')
        .order_by('job_card__admitted_date', 'job_card__pk', 'pk')
    )


def free_from_shop(card_ids):
    """
    Which of these warranty cards the shop REPLACED FREE — `{pk}`: a spare-shop
    part whose Shop Price is ₹0, the shop's own answer (2026-10-09).

    ⚠ THE SHOP'S ANSWER, NEVER WHAT THE CARD COST US. The list used to say Free
    only when the card's whole cost was ₹0, so a part the shop gave free with
    ₹55 of transport paid read as charged, while Deep Analysis counted it as
    replaced free. The cost stays beside it as its own figure. A warehouse draw
    is never free from a shop — it came off our own shelf — even when its cost
    is still unknown. One query.
    """
    answers = {}
    for card_id, price in (JobCardSpareItem.objects
                           .filter(job_card_id__in=list(card_ids),
                                   source=JobCardSpareItem.SOURCE_SHOP)
                           .values_list('job_card_id', 'unit_price')):
        # Every shop part on the card answered ₹0; a blank (None) is waiting.
        answers[card_id] = answers.get(card_id, True) and price == 0
    return {card_id for card_id, free in answers.items() if free}


def cost_by_card(card_ids):
    """
    What each of these warranty cards cost the workshop, `{pk: ₹}` — its parts
    at cost plus their transport, the same `PART_COST` the Profit page and a
    car's gross figure read, so the three can never quote one warranty two
    ways. One query.
    """
    return dict(
        JobCardSpareItem.objects.filter(job_card_id__in=list(card_ids))
        .values('job_card_id')
        .annotate(cost=Coalesce(Sum(PART_COST, output_field=MONEY), ZERO, output_field=MONEY))
        .values_list('job_card_id', 'cost')
    )


def total_cost(cards):
    """The warranty cost of a set of cards — the Warranty page's heading."""
    return JobCardSpareItem.objects.filter(job_card__in=cards).aggregate(
        cost=Coalesce(Sum(PART_COST, output_field=MONEY), ZERO, output_field=MONEY))['cost']


def km_since(card, earlier):
    """
    How far the car has run since `earlier` — today's reading less that
    bill's — or None. The warranty card passes `first_bill`, so a 2nd claim
    counts from where the part was first fitted, like its age does.

    Warranties are usually "so many months OR so many km", and the claim
    screen shows only how long ago. Both readings go through `parse_km`, the
    service history's own reader, so a hand-typed odometer is read one way
    everywhere; either one unreadable, or a difference below zero (a reading
    typed wrong somewhere), gives None and the card says nothing.
    """
    if earlier is None:
        return None
    now, then = parse_km(card.mileage), parse_km(earlier.mileage)
    if now is None or then is None or now < then:
        return None
    return now - then


def cancel_refusal(card):
    """
    Why this warranty card may NOT be cancelled — or None when it may.

    CANCEL CLAIM undoes a claim opened by mistake: wrong bill, wrong car,
    pressed twice. It is allowed only while nothing real has happened —

    * the card is still OPEN: a completed card is a visit that took place;
    * no shop has CHARGED for a part: that is a debt on the shop's ledger;
    * no TRANSPORT was paid on a part: that money has left the drawer.

    A shop that answered Free, a part still Waiting, and a part taken off the
    shelf do not stop it — the stock goes back on the shelf with the card.
    """
    if card.completed:
        return "It is completed — undo the completion first."
    parts = card.spares.filter(source=JobCardSpareItem.SOURCE_SHOP)
    if parts.filter(unit_price__gt=0).exists():
        return "A shop has charged for a part on it."
    if parts.filter(transport_cost__gt=0).exists():
        return "Transport was paid on a part on it."
    return None


def cancel_warranty(card):
    """
    Remove a warranty card opened by mistake, with everything on it, and
    return its number — or raise `WarrantyRefused` with `cancel_refusal`'s
    sentence.

    Its parts are removed through the models, so a part taken off the shelf
    goes back on it (the stock signals), and every shop a part named has its
    totals refreshed. Photos are queued for the bucket sweep by their own
    signal. NO DeletionLog row, the owners' decision — like deleting an
    estimate: no customer money was ever on it and nothing it moved survives
    it, so it is housekeeping, not a record to keep. Its WR number may be
    taken by the next claim, as a deleted job card's JB number may.
    """
    from .models import SpareShop

    with transaction.atomic():
        card = JobCard.objects.select_for_update().get(pk=card.pk)
        stop = cancel_refusal(card)
        if stop:
            raise WarrantyRefused(stop)
        number = card.bill_number
        shops = set(card.spares.exclude(shop_id=None).values_list('shop_id', flat=True))
        for part in card.spares.all():
            part.delete()
        card.delete()
        for shop in SpareShop.objects.filter(pk__in=shops):
            shop.update_totals()
    return number


def refusal(bill, registration):
    """
    Why a warranty card may NOT be opened against this bill for this car — or
    None when it may. The sentence names what to do instead.
    """
    if bill is None:
        return "That bill was not found."
    if bill.registration != (registration or '').strip().upper():
        return f"{bill.number} is not a bill of this car."
    if not bill.is_done:
        return (f"{bill.number} is still on the floor — fix the part on that "
                f"card. A warranty card is for work after the car has left.")
    return None


def _lock_part(key):
    """The part this key names, locked for the rest of the transaction — a
    card's part ("c12") or an old bill's line ("o7") — or None. Locked so two
    presses at once cannot open two claims for one part (effective on
    PostgreSQL; the page's one-press latch covers the rest). No select_related:
    a part's card is a nullable join, and PostgreSQL refuses FOR UPDATE across
    the nullable side of one."""
    kind, rest = (key or '')[:1], (key or '')[1:]
    if kind not in ('c', 'o') or not rest.isdigit():
        return None
    if kind == 'c':
        return (JobCardSpareItem.objects.select_for_update()
                .filter(pk=int(rest), job_card__isnull=False).first())
    return OldBillPartLine.objects.select_for_update().filter(pk=int(rest)).first()


def part_refusal(name, claim):
    """Why a part may NOT be claimed, from its claim (`bills_for`'s `claim`) —
    or None. The sentence says where to go instead."""
    if not claim:
        return None
    if claim['open']:
        return f"{name} is already being claimed on {claim['number']}."
    return f"{name} was replaced on {claim['number']} — claim the new one there."


def open_claim(registration, part):
    """
    Open ONE claim and return its new warranty card — for ONE part (`part`, a
    key from `bills_for`: "c12" a card's part, "o7" an old bill's line).
    Raises `WarrantyRefused` with the sentence to show.

    REFUSED, and nothing is opened, when:

    * no part is named — there is no claim for the work alone;
    * the part or bill is not found, is not this car's, or the car has not
      left (`refusal`);
    * the part already has an open claim, or a finished one — then the part
      on the car is the replacement, claimed under the warranty card that
      fitted it (`part_refusal`).

    THE PART goes onto the card, linked to the part it replaces:

    * a SPARE-SHOP part — same name, shop and quantity, the shop's answer
      Waiting (no Shop Price) and ordered on the claim day, because claiming
      is asking the shop;
    * a WAREHOUSE draw — the same product and quantity as a new draw, so the
      replacement comes off the shelf NOW, at the shelf's cost, as any part
      added to a card does;
    * an OLD BILL's line — a spare-shop part with no shop chosen: the paper
      never said where it came from, so Office picks it on the card.

    WHAT THE NEW CARD TAKES:

    * WHICH CAR — plate, make and model — from the EARLIER BILL, because that
      is the car the claim is about. An old bill may carry no make or model,
      and a job card needs both, so those fall back to the car as the workshop
      knows it now.
    * THE CUSTOMER from the EARLIER BILL too — the person who holds the bill
      being claimed against. Never from the car's newest visit: cars change
      hands, which is why the job card only ever OFFERS a past customer, and
      this card has no customer box for anybody to notice a wrong one in. Name
      and number come from that one bill together (an old bill has no number).
    * The colour, chassis code and VIN from `known_car` — facts about the car,
      as it is known now.
    * Nothing else. Today's mileage, the mechanic and the work are this visit's.
    """
    if not part:
        raise WarrantyRefused("Pick the part that failed.")
    with transaction.atomic():
        row = _lock_part(part)
        if row is None:
            raise WarrantyRefused("That part was not found.")
        number = (row.old_bill.bill_number if isinstance(row, OldBillPartLine)
                  else row.job_card.bill_number)

        bill = find(number)
        stop = refusal(bill, registration)
        if stop:
            raise WarrantyRefused(stop)

        names = {p['key']: p['name'] for p in bill.shop_parts + bill.stock_parts}
        if part not in names:      # a nameless row is not a part to claim
            raise WarrantyRefused("That part was not found.")
        claims = (_claims_on(line_ids=[row.pk]) if bill.is_old_bill
                  else _claims_on(part_ids=[row.pk]))
        stop = part_refusal(names[part], claims.get(part))
        if stop:
            raise WarrantyRefused(stop)

        known = known_car(bill.registration)
        card = JobCard.objects.create(
            kind=JobCard.KIND_WARRANTY,
            warranty_for=bill.number,
            admitted_date=timezone.localdate(),
            registration_number=bill.registration,
            brand_name=bill.brand or known['brand_name'],
            model_name=bill.model or known['model_name'],
            car_color=known['car_color'] or None,
            car_color_other=known['car_color_other'] or None,
            chassis_code=known['chassis_code'] or None,
            vin=known['vin'] or None,
            customer_name=bill.customer_name or None,
            customer_contact=bill.customer_contact or None,
        )
        _claim_part(card, bill.rows[part])
        return card


def _claim_part(card, row):
    """Copy the claimed part of the earlier bill onto the new warranty card,
    linked to it — see `open_claim` for what each kind becomes. Through the
    model, so the stock signals, the shop ledger and the card's ₹0 rule all
    run."""
    claim_day = card.admitted_date
    if isinstance(row, OldBillPartLine):
        JobCardSpareItem.objects.create(
            job_card=card, source=JobCardSpareItem.SOURCE_SHOP, replaces_line=row,
            spare_part_name=row.name, quantity=row.quantity,
            ordered_date=claim_day, status='ORDERED')
    elif row.source == JobCardSpareItem.SOURCE_INVENTORY and row.item_id:
        JobCardSpareItem.objects.create(
            job_card=card, source=JobCardSpareItem.SOURCE_INVENTORY, replaces=row,
            item_id=row.item_id, spare_part_name=row.spare_part_name,
            quantity=row.quantity or 1)
    else:
        JobCardSpareItem.objects.create(
            job_card=card, source=JobCardSpareItem.SOURCE_SHOP, replaces=row,
            spare_part_name=row.spare_part_name, quantity=row.quantity,
            shop=row.shop, shop_name=row.shop.name if row.shop_id else '',
            ordered_date=claim_day, status='ORDERED')

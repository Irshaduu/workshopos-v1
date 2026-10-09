"""
Warranty — opening a warranty card, working on one, and its paper.

Opening a warranty card — NEW CLAIM (2026-10-05).

Warranty page → New claim → pick the car → tick the part that failed → Claim.
The Car Profile's Warranty button is a shortcut into the same parts screen,
the car already chosen. One screen for every kind of earlier bill — a job
card, an earlier warranty card (a part that failed again) and an Excel-era
old bill alike. Every rule is `workshop/warranty.py`; these views only ask it
and answer.

OFFICE AND OWNER ONLY. Whether a part is covered is a commercial decision, and
the card it opens carries the shop's price. Floor works on the card once it is
open, like any job card.

The WARRANTY CARD — the page a claim is worked on (2026-10-05) — is here, and
so is the warranty SLIP, the paper handed over with the car.
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .. import warranty
from ..decorators import is_office_or_owner, office_required, staff_required
from ..forms import (
    JobCardConcernFormSet, JobCardLabourFormSet, WarrantyCardForm,
    WarrantyPartFormSet, WarrantyStockFormSet,
)
from ..invoice import build_warranty_slip
from ..models import JobCard, JobCardLabourItem, JobCardSpareItem, live_cards
from ..return_to import safe_return
# The job card's own save machinery, shared rather than copied: the Floor lock
# on prices, the after-save block that keeps the shop ledgers honest, the
# refusal summary, the shop list and the photo box.
from .jobcard import (
    _after_parts_saved, _floor_locked_data, _photo_context, _problems_for,
    _shop_options,
)


#: The two windows the Warranty page offers — the Estimates list's own pair.
#: A warranty is opened a handful of times a month, so Today or This Week
#: would be an empty page most of the time, which reads as a broken screen.
WARRANTY_FILTERS = (('this_year', 'This Year'), ('all', 'All Time'))


@office_required
def warranty_list(request):
    """
    THE WARRANTY PAGE — every warranty card, and what is still waiting.

    Two parts, top to bottom:

    * **Waiting on the shop** — every warranty part whose Shop Price is still
      blank, oldest first, NEVER filtered: a claim the shop has not answered
      must not drop out of sight because somebody narrowed the list below.
      Each row opens the card's form, where the answer is typed.
    * **Every warranty card**, newest first, narrowed by a search and by This
      Year (the default) or All Time. The heading counts them and totals what
      they cost, over exactly the cards listed.

    Office and Owner, like the cards themselves. Plain links and a plain GET
    form — nothing here needs a script.
    """
    q = request.GET.get('q', '').strip()
    filter_type = request.GET.get('filter', 'this_year')
    if filter_type not in dict(WARRANTY_FILTERS):
        filter_type = 'this_year'

    cards = JobCard.objects.filter(live_cards(), kind=JobCard.KIND_WARRANTY)
    if filter_type == 'this_year':
        cards = cards.filter(admitted_date__year=timezone.localdate().year)
    for word in q.split():
        cards = cards.filter(
            Q(bill_number__icontains=word) | Q(warranty_for__icontains=word) |
            Q(registration_number__icontains=word) | Q(brand_name__icontains=word) |
            Q(model_name__icontains=word) | Q(customer_name__icontains=word) |
            Q(spares__spare_part_name__icontains=word))
    if q:
        # The part's name joins one card to its row; `distinct` keeps a card
        # from being counted once per matching row.
        cards = cards.distinct()

    count = cards.count()
    cost = warranty.total_cost(cards)

    page_obj = Paginator(cards.order_by('-admitted_date', '-pk'), 45).get_page(
        request.GET.get('page'))
    rows = list(page_obj.object_list)
    costs = warranty.cost_by_card(r.pk for r in rows)
    names = warranty.claimed_names(r.pk for r in rows)
    waiting = warranty.waiting_on_shop()
    waiting_cards = {spare.job_card_id for spare in waiting}
    for row in rows:
        row.cost = costs.get(row.pk)
        row.claimed_name = names.get(row.pk, '')
        row.waiting = row.pk in waiting_cards
    for spare in waiting:
        spare.age = warranty.age_phrase(spare.job_card.admitted_date)

    # The live search asks for the list alone; a page load gets the whole page.
    template = ('workshop/warranty/_warranty_cards.html'
                if request.headers.get('x-requested-with') == 'XMLHttpRequest'
                else 'workshop/warranty/warranty_list.html')
    return render(request, template, {
        'waiting': waiting,
        'cards': rows,
        'page_obj': page_obj,
        'count': count,
        'cost': cost,
        'q': q,
        'filter_type': filter_type,
        'filters': WARRANTY_FILTERS,
        'filter_label': dict(WARRANTY_FILTERS)[filter_type],
    })


@office_required
def warranty_slip(request, pk):
    """
    The warranty slip — the paper handed over with a warranty card's car.

    Drawn by the All Invoices page with one sheet, as a single old bill is, so
    there is no second toolbar, scaler or PDF-naming script to keep in step.
    Office and Owner, like the invoice it stands in for. A job card has no slip
    and 404s here; its paper is the invoice.
    """
    card = get_object_or_404(
        JobCard.objects.filter(kind=JobCard.KIND_WARRANTY).prefetch_related(
            Prefetch('labours', queryset=JobCardLabourItem.objects.order_by('pk')),
            Prefetch('spares', queryset=JobCardSpareItem.objects
                     .select_related('item__category').order_by('pk')),
        ),
        pk=pk,
    )
    earlier = warranty.find(card.warranty_for)
    doc = build_warranty_slip(card, for_number=card.warranty_for,
                              for_date=earlier.date if earlier else None)
    return render(request, 'workshop/car_profiles/all_invoices_print.html', {
        'sheets': [{'doc': doc, 'jobcard': card, 'warranty': True}],
        'count': 1,
        'chip_label': 'Warranty',
        'edit_url': reverse('warranty_card', args=[card.pk]),
        'registration': card.registration_number,
        'document_title': doc['document_title'],
        'back_url': safe_return(request) or reverse(
            'car_profile_detail', args=[card.registration_number]),
    })


@office_required
def warranty_new(request):
    """
    NEW CLAIM, step one: which car?

    Every car with a finished bill, newest bill first, 45 to a page, narrowed
    by plate, make, model, customer or bill number (`warranty.claimable_cars`).
    A car opens the parts screen; the search rides along as `?back=`, so its
    Back lands on the same narrowed list.
    """
    q = request.GET.get('q', '').strip()
    cars = warranty.claimable_cars(q)
    page_obj = Paginator(cars, 45).get_page(request.GET.get('page'))
    rows = warranty.name_cars(list(page_obj.object_list))
    template = ('workshop/warranty/_claim_cars.html'
                if request.headers.get('x-requested-with') == 'XMLHttpRequest'
                else 'workshop/warranty/warranty_new.html')
    return render(request, template, {
        'cars': rows,
        'page_obj': page_obj,
        'count': len(cars),
        'q': q,
    })


@office_required
def warranty_start(request, registration):
    """
    THE CAR'S WARRANTY PAGE — which part failed? (Reached from New claim's car
    list, and from the Car Profile's Warranty button.)

    GET: this car's bills, newest first, each with its date and how long ago,
    an Open link to the bill, and its parts — spare-shop parts in the open, the
    rarely claimed stock parts folded under "Stock items". Each part carries
    its OWN Claim button, or says it is already being claimed, or was replaced
    (the claim link is `warranty.bills_for`). There is no claim for the work
    alone: a fix with no part is done without a card (the owners, 2026-10-08).

    POST `part` (one part's key): ONE claim is opened, and its card shown.
    `warranty.open_claim` re-checks everything —
    the part is on a bill of this car, the car has left, the part is not
    already claimed — so a crafted POST is refused, not obeyed. A refusal comes
    back to this screen with its message.
    """
    plate = (registration or '').strip().upper()
    back = safe_return(request)
    back_url, back_label = (back, 'Back') if back else (
        reverse('car_profile_detail', args=[plate]), plate)

    if request.method == 'POST':
        if len(request.POST.getlist('part')) > 1:
            messages.error(request, "One claim is one part — claim each part on its own.")
            return redirect(request.get_full_path())
        try:
            card = warranty.open_claim(plate, request.POST.get('part', '').strip() or None)
        except warranty.WarrantyRefused as refused:
            messages.error(request, str(refused))
            return redirect(request.get_full_path())
        messages.success(
            request, f"{card.bill_number} opened — "
                     f"{warranty.claimed_part(card).spare_part_name} from {card.warranty_for}.")
        return redirect('warranty_card', pk=card.pk)

    bills = warranty.bills_for(plate)
    today = timezone.localdate()
    for bill in bills:
        # Measured from where the warranty clock runs — a warranty card's
        # first bill, never its own claim day (`warranty.first_bill`).
        bill.age = warranty.age_phrase(bill.first.date, today)

    # The car's name for the heading: the newest bill's make and model, the
    # plate alone when none was recorded.
    newest = bills[0] if bills else None
    car_name = ' '.join(p for p in (newest.brand, newest.model) if p) if newest else ''

    return render(request, 'workshop/warranty/warranty_start.html', {
        'registration': plate,
        'car_name': car_name,
        'bills': bills,
        'back_url': back_url,
        'back_label': back_label,
        # A card still on the floor is not offered — a part that fails before
        # the car leaves is fixed on that card — so the page says why it is
        # missing rather than leaving somebody looking for it.
        'on_floor': JobCard.get_active_conflict(plate),
    })

#: The warranty card's four row sections, as the page names them — the refusal
#: summary uses the same words (`_problems_for`).
WARRANTY_SECTIONS = ('Customer concern', 'Job', 'Claimed part', 'Claimed part')


def _card_way_back(request, office):
    """
    Where the warranty card's back control goes, and what it says. Named
    destinations, never `history.back()` (CLAUDE.md, "Going back"): the Live
    Report when the card was opened from it, the Warranty page for Office and
    an owner, and the board for Floor, who cannot open the Warranty page.
    """
    if request.GET.get('next') == 'mini':
        return reverse('live_report'), 'Live'
    if office:
        return reverse('warranty_list'), 'Warranty'
    return reverse('home'), 'Floor'


@staff_required
def warranty_card(request, pk):
    """
    THE WARRANTY CARD — the page a claim is worked on (2026-10-05).

    It is the JOB CARD'S PAGE (2026-10-09, the owners' call — the template
    extends `jobcard_form.html`), in the job card's order: this visit's date,
    mileage and mechanic; the note and photos; the concerns; the jobs; and,
    where Spare Parts sits, the ONE part claimed — fixed from the bill, with
    the SHOP'S ANSWER. Nothing else is added here: anything not from the
    earlier bill goes on a job card and is billed. No customer box, no
    customer price, no labour charge — the customer pays nothing — and the car
    and the bill it is for are fixed. Every link that opens a warranty card
    arrives here, through `jobcard_edit`'s redirect.

    The data is a job card's, so the job card's own save is used — the Floor
    price lock and `_after_parts_saved` — and stock, the shop ledgers, the
    Live Report and the Profit page behave exactly as on a job card.

    Floor works on it like any card; the shop, the Shop Price (the shop's
    answer) and transport are Office's and an owner's — not drawn for Floor,
    who posts them back from a hidden cell as on a job card, the two prices
    pinned on the server by `_floor_locked_data`.

    The claimed part is the Job Card's own spare row (2026-10-08). Its rare
    "Took it from Unassigned Spares" fills that one row from a Hub row and
    posts `imported_unassigned_ids`, so `_after_parts_saved` removes the Hub
    row exactly as a job card's import does — Office and Owner only.
    """
    card = get_object_or_404(JobCard, pk=pk, kind=JobCard.KIND_WARRANTY)
    office = is_office_or_owner(request.user)

    if request.method == 'POST':
        data = _floor_locked_data(request, card)
        form = WarrantyCardForm(data, instance=card)
        concern_formset = JobCardConcernFormSet(request.POST, instance=card, prefix='concerns')
        part_formset = WarrantyPartFormSet(
            data, instance=card, prefix='spares')
        stock_formset = WarrantyStockFormSet(data, instance=card, prefix='inventory')
        labour_formset = JobCardLabourFormSet(request.POST, instance=card, prefix='labours')

        # Every one is validated — a list, never `all()` over a generator,
        # which would stop at the first refusal and hide the rest.
        checks = [f.is_valid() for f in (form, concern_formset, part_formset,
                                         stock_formset, labour_formset)]
        if all(checks):
            with transaction.atomic():
                form.save()
                saved_concerns = concern_formset.save()
                saved_parts = part_formset.save()
                stock_formset.save()
                labour_formset.save()
                _after_parts_saved(request, card, saved_concerns, saved_parts)
            messages.success(request, f'{card.bill_number} saved.')
            if request.GET.get('next') == 'mini':
                return redirect('live_report')
            return redirect('warranty_card', pk=card.pk)
    else:
        form = WarrantyCardForm(instance=card)
        concern_formset = JobCardConcernFormSet(instance=card, prefix='concerns')
        part_formset = WarrantyPartFormSet(instance=card, prefix='spares')
        stock_formset = WarrantyStockFormSet(instance=card, prefix='inventory')
        labour_formset = JobCardLabourFormSet(instance=card, prefix='labours')

    problems = []
    if request.method == 'POST':
        problems = _problems_for(
            request, form, concern_formset, labour_formset, stock_formset,
            part_formset, subject=card.bill_number, sections=WARRANTY_SECTIONS)

    earlier = warranty.find(card.warranty_for)
    # Where the warranty clock runs from: `earlier` itself, or for a repeat
    # claim the bill the part was first fitted on — its age and km are what
    # the claim is judged by.
    first = warranty.first_bill(card.warranty_for)
    claimed = warranty.claimed_part(card)
    back_url, back_label = _card_way_back(request, office)
    return render(request, 'workshop/warranty/warranty_card.html', {
        'card': card,
        'form': form,
        'concern_formset': concern_formset,
        'part_formset': part_formset,
        'stock_formset': stock_formset,
        'labour_formset': labour_formset,
        'is_office': office,
        'earlier': earlier,
        'first': first,
        'first_age': warranty.age_phrase(first.date) if first else '',
        # What this claim is for — its one part — and which claim of that
        # part it is (2 when the part it replaces was itself
        # fitted under warranty).
        'claimed': claimed,
        'claim_label': warranty.round_label(warranty.claim_round(claimed)),
        # "7,000 km since JB-26-007" under Mileage, worked out from the SAVED
        # reading — `card` is the form's instance, so after a refused save it
        # holds what was typed, which is still the reading being looked at.
        'km_since': warranty.km_since(card, first),
        # Why the ⋮'s Cancel claim is greyed out, or None when it may be used.
        'cancel_refusal': warranty.cancel_refusal(card) if office else None,
        # The make and model boxes, only while the earlier bill left them
        # blank — see `WarrantyCardForm`.
        'ask_car': 'brand_name' in form.fields or 'model_name' in form.fields,
        'spare_shops': _shop_options(card),
        # The rare "the replacement came from Unassigned Spares" — Office and
        # Owner only, and not even fetched for Floor (the list carries every
        # Hub row's price; the job card's own rule, AUD-0109). Only while the
        # claim has a shop part to fill.
        'unassigned_spares': (
            list(JobCardSpareItem.objects.filter(job_card__isnull=True)
                 .exclude(shop=None).select_related('shop').order_by('-ordered_date', '-pk'))
            if office and part_formset.forms else None),
        'problems': problems,
        'next_url': 'mini' if request.GET.get('next') == 'mini' else '',
        'back_url': back_url,
        'back_label': back_label,
        **_photo_context(card),
    })


@office_required
def warranty_cancel(request, pk):
    """
    CANCEL CLAIM — remove a warranty card opened by mistake, from its ⋮.

    POST only, Office and Owner. Allowed while the card is open and nothing
    real has happened on it (`warranty.cancel_refusal`); refused otherwise,
    with the reason, back on the card. The confirmation card asks first.
    """
    card = get_object_or_404(JobCard, pk=pk, kind=JobCard.KIND_WARRANTY)
    if request.method != 'POST':
        return redirect('warranty_card', pk=card.pk)
    try:
        number = warranty.cancel_warranty(card)
    except warranty.WarrantyRefused as refused:
        messages.error(request, f"{card.bill_number} can't be cancelled. {refused}")
        return redirect('warranty_card', pk=card.pk)
    messages.success(request, f"Claim {number} cancelled.")
    return redirect('warranty_list')

"""
What a valid ordered/received pair looks like — one module, no views.

A spare part is ordered from a shop and then arrives. Those are two dates on one
row, and there is exactly one mistake the pair can express that neither date can
express alone: **arriving before it was ordered.** Nothing in the schema stops
it, both boxes are independent `<input type="date">`, and the result is a row
that reads as time travel on the shop's ledger and on the printed history.

The rule lived only in `views/spare_shop._clean_spare_dates`, which guards the
Unassigned Spares hub — so an unassigned purchase was checked and the *same two
boxes on a job card* were not. That is where most spares are actually entered.
Extracting it here rather than copying it into the job-card form is the point:
two implementations of "is this pair the right way round" would be two answers
free to disagree, and they would disagree on the ledger.

Pure functions over dates. `_clean_spare_dates` parses raw POST text and then
calls this; the job-card form gets real `date` objects from its own DateFields
and calls it directly.
"""

from django.utils import timezone


def pair_problem(ordered, received):
    """
    What is wrong with this ordered/received pair, or None if nothing is.

    Either may be None — a part ordered and not yet arrived is the normal
    mid-workflow state, and a row with neither date is simply unfilled. Only a
    pair where BOTH are present can be the wrong way round.

    A FUTURE date is refused as well, and the two callers need that for slightly
    different reasons: an unassigned row is created already RECEIVED, so it
    cannot have arrived on a day that has not come; a job-card spare could in
    principle be pre-ordered, but a date after today is far more often a typed
    year — 2027 for 2026 — than a plan, and the workshop has no forward-ordering
    workflow to protect. Same reasoning as `_parse_money`'s future-advance
    refusal.

    **The wording is SHORT, on the owner's instruction (2026-08-17.)** The first
    version explained the rule — "Received date cannot be before the ordered
    date — this part would have arrived before it was ordered" — and the job
    card prints it after a field label, so a mistyped year filled two lines with
    "Received date: Received date cannot be…". A sentence that repeats the box
    it is attached to and then argues its case is a sentence nobody finishes.
    Say what is wrong and what to do: "Arrived before it was ordered — fix the
    date." The job card also checks the pair AS IT IS TYPED now
    (`jobcard_form.html`), so in the ordinary case this message is the backstop
    rather than the thing anybody reads.
    """
    today = timezone.localdate()

    if ordered and ordered > today:
        return "Ordered date is in the future."
    if received and received > today:
        return "Received date is in the future."
    if ordered and received and received < ordered:
        return "Arrived before it was ordered — fix the date."
    return None


def short_date(value, card_year):
    """
    A part's date, with the YEAR dropped when it is the card's own.

    Not a formatting preference — a width fix with a measurement behind it. The
    full pair plus a shop name ("16/07/2026 – 17/07/2026 · Spare club") is 38
    characters and wrapped to two lines on a 375px phone, so rows in the same
    list came out different heights and the list read as broken. Dropping a
    year that is already stated twice in the card above takes it to 30 and it
    fits.

    The year is KEPT the moment it differs, because then it is the whole point:
    a part ordered in December for a car admitted in January is the one case
    where the reader must not have to assume. Both halves are compared
    separately, so a pair that straddles New Year prints one short and one long
    rather than hiding the crossing.

    An em dash for the half not in yet: a spare is finished when it has been
    ordered AND received, so half-filled is still incomplete — the rule the job
    card's own date chip follows.
    """
    if value is None:
        return '—'
    if card_year is not None and value.year == card_year:
        return value.strftime('%d/%m')
    return value.strftime('%d/%m/%Y')


def date_pair(ordered, received, card_year):
    """A part's two dates as ONE item — "16/07 – 17/07" — or '' when it has
    neither. Read by the read-only job card and the car's warranty page, so a
    part's dates read the same on both."""
    if not ordered and not received:
        return ''
    return f'{short_date(ordered, card_year)} – {short_date(received, card_year)}'

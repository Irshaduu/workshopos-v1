"""
Parts transport — what it cost to bring a spare-shop part in, paid to anyone but
the shop (2026-10-01, the owners' request).

The owners' first plan was to add it into Shop Price (₹22,000 + ₹900 =
₹22,900). That would have put ₹900 on the shop's ledger that nobody owes the
shop, so it is its own box on the spare row, and these tests pin down where the
money goes and — just as important — where it must NOT go:

  * NEVER the shop's balance, and never the customer's bill as a line.
  * The Profit page: its own expense line, dated by the job like the part.
  * The spare-parts margin and every gross profit: counted AFTER transport.
  * Cash Tracking: on the day the part arrived.
  * The suggested price (rule B): the markup on the part, transport at cost —
    that arithmetic is `pricing-core.js` and is tested in
    `workshop/tests/js/pricing-core.test.js`; the server never prices a part.

Plus the saved-₹0 fix found while building it: a part's ₹0 survives a save.
"""
import re
from datetime import date, timedelta
from decimal import Decimal as D

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from workshop import analysis_engine as engine
from workshop.models import JobCard, JobCardSpareItem, Mechanic, SpareShop

FORM_TEMPLATE = 'workshop/templates/workshop/jobcard/jobcard_form.html'


class TransportBase(TestCase):
    def setUp(self):
        for name in ('Owner', 'Office', 'Floor'):
            Group.objects.get_or_create(name=name)
        self.owner = User.objects.create_user(username='tr_owner', password='pw')
        self.owner.groups.add(Group.objects.get(name='Owner'))
        self.office = User.objects.create_user(username='tr_office', password='pw')
        self.office.groups.add(Group.objects.get(name='Office'))
        self.floor = User.objects.create_user(username='tr_floor', password='pw')
        self.floor.groups.add(Group.objects.get(name='Floor'))

        self.today = timezone.localdate()
        self.mech = Mechanic.objects.create(name='Ravi')
        self.shop = SpareShop.objects.create(name='Alpha Spares')

    def client_for(self, user):
        c = Client()
        c.force_login(user)
        return c

    def make_card(self, when=None, completed=False, **kw):
        kw.setdefault('registration_number', 'KL 01 AB %04d' % JobCard.objects.count())
        return JobCard.objects.create(
            admitted_date=when or self.today, brand_name='Toyota', model_name='Innova',
            lead_mechanic=self.mech, completed=completed,
            completed_date=(when or self.today) if completed else None, **kw)

    def make_spare(self, card, shop_price='1000', transport='500', price='1900',
                   received=None, **kw):
        return JobCardSpareItem.objects.create(
            job_card=card, source=JobCardSpareItem.SOURCE_SHOP,
            spare_part_name=kw.pop('name', 'Alternator'), shop=kw.pop('shop', self.shop),
            unit_price=D(shop_price) if shop_price is not None else None,
            transport_cost=D(transport) if transport is not None else None,
            total_price=D(price) if price is not None else None,
            received_date=received, **kw)

    def month(self):
        start = self.today.replace(day=1)
        return start, engine._month_end(start)


# =============================================================================
# NEVER THE SHOP'S DEBT
# =============================================================================
class TransportIsNeverTheShopsDebtTests(TransportBase):

    def test_the_shops_balance_is_the_shop_price_and_nothing_else(self):
        """₹1,000 bought, ₹500 paid to a bus parcel office: the shop is owed
        ₹1,000. The ₹500 on its ledger is the mistake this box exists to stop."""
        self.make_spare(self.make_card())
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.total_purchased_amount, D('1000'))
        self.assertEqual(self.shop.get_pending_balance, D('1000'))

    def test_the_bill_does_not_carry_it_as_a_line(self):
        """It reaches the customer only inside the part's price — the bill is
        the customer prices plus labour, exactly as before."""
        card = self.make_card()
        self.make_spare(card, transport='500', price='1900')
        card.refresh_from_db()
        self.assertEqual(card.total_bill_amount, D('1900'))

    def test_the_profit_pages_spare_shops_line_is_still_what_the_shops_charged(self):
        """`Spare Shops` must keep matching the Shops section's spend — the
        transport is its own line, never folded in."""
        self.make_spare(self.make_card())
        start, end = self.month()
        self.assertEqual(engine.spare_shop_expense(start, end), D('1000'))


# =============================================================================
# PROFIT
# =============================================================================
class TransportIsAProfitExpenseTests(TransportBase):

    def setUp(self):
        super().setUp()
        card = self.make_card()
        card.total_bill_amount = D('1900')
        card.save()
        self.make_spare(card)
        self.start, self.end = self.month()

    def test_it_is_its_own_expense_line_and_inside_the_total(self):
        r = engine.build_profit_report(self.start, self.end)
        lines = {l['key']: l['amount'] for l in r['expense_lines']}
        self.assertEqual(lines.get('transport'), D('500'))
        self.assertEqual(r['transport'], D('500'))
        self.assertEqual(sum(l['amount'] for l in r['expense_lines']), r['expense_total'])
        # ₹1,900 earned − ₹1,000 shop − ₹500 transport.
        self.assertEqual(r['profit'], D('400'))

    def test_the_line_is_absent_when_there_is_no_transport(self):
        JobCardSpareItem.objects.update(transport_cost=None)
        r = engine.build_profit_report(self.start, self.end)
        self.assertNotIn('transport', [l['key'] for l in r['expense_lines']])

    def test_the_owners_way_lands_on_the_same_profit(self):
        """The earnings card states the profit a second time. With transport
        off the spare margin and on the equation's own line, the two must
        still land on one figure with nothing in between."""
        r = engine.build_profit_report(self.start, self.end)
        self.assertEqual(r['earnings']['profit'], r['profit'])
        row = next(x for x in r['earnings']['earn'] if x['key'] == 'spare_margin')
        self.assertEqual(row['transport'], D('500'))
        self.assertEqual(row['amount'], row['charged'] - row['cost'] - row['transport'])

    def test_the_spare_margin_is_after_transport_and_the_cost_is_not(self):
        shop = engine.parts_trading(self.start, self.end)['shop']
        self.assertEqual(shop['cost'], D('1000'))        # what the shop charged
        self.assertEqual(shop['transport'], D('500'))
        self.assertEqual(shop['profit'], D('400'))

    def test_the_chart_totals_to_the_headline(self):
        r = engine.build_profit_report(self.start, self.end)
        rows = engine.monthly_series(self.start, self.end)
        self.assertEqual(sum(x['expenses'] for x in rows), r['expense_total'])
        self.assertEqual(sum(x['profit'] for x in rows), r['profit'])

    def test_it_is_dated_by_the_job_like_the_part_it_came_with(self):
        """Profit charges it in the month the CAR was admitted, even when the
        part arrived the next month — a job's revenue, parts and their
        transport stay in one month."""
        JobCardSpareItem.objects.update(received_date=self.end + timedelta(days=3))
        r = engine.build_profit_report(self.start, self.end)
        self.assertEqual(r['transport'], D('500'))


# =============================================================================
# CASH
# =============================================================================
class TransportIsCashOnTheDayThePartArrivedTests(TransportBase):

    def line(self, start, end):
        cash = engine.cash_position(start, end)
        return next((r['amount'] for r in cash['money_out'] if r['label'] == 'Parts transport'),
                    D('0'))

    def test_it_is_filed_on_the_received_date_not_the_job_date(self):
        last_month_end = self.today.replace(day=1) - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        card = self.make_card(when=last_month_end)
        self.make_spare(card, received=self.today)
        this_start, this_end = self.month()
        self.assertEqual(self.line(this_start, this_end), D('500'))
        self.assertEqual(self.line(last_month_start, last_month_end), D('0'))

    def test_with_no_received_date_it_falls_back_to_the_admitted_date(self):
        self.make_spare(self.make_card(), received=None)
        self.assertEqual(self.line(*self.month()), D('500'))

    def test_a_part_waiting_in_unassigned_spares_is_counted_too(self):
        """The cash left the drawer when the part arrived, car or no car."""
        self.make_spare(None, received=self.today)
        self.assertEqual(self.line(*self.month()), D('500'))

    def test_the_line_is_absent_when_there_is_none(self):
        self.make_spare(self.make_card(), transport=None)
        cash = engine.cash_position(*self.month())
        self.assertNotIn('Parts transport', [r['label'] for r in cash['money_out']])

    def test_all_time_reaches_a_part_that_arrived_before_any_car(self):
        """Ordered ahead for an appointment: the parcel was paid before the car
        was admitted, so All Time has to open on the parcel's day."""
        early = self.today - timedelta(days=40)
        self.make_spare(self.make_card(), received=early)
        self.assertEqual(engine.first_record_date(), early)


# =============================================================================
# ROUTE
# =============================================================================
class AWarehouseDrawNeverCarriesTransportTests(TransportBase):

    def test_a_draw_cannot_hold_one(self):
        """A draw's delivery was paid on the Supplies Shop bill that put it on
        the shelf; the engine counts transport on the shop side alone."""
        draw = JobCardSpareItem.objects.create(
            job_card=self.make_card(), source=JobCardSpareItem.SOURCE_INVENTORY,
            spare_part_name='Oil', transport_cost=D('300'))
        draw.refresh_from_db()
        self.assertIsNone(draw.transport_cost)


# =============================================================================
# THE JOB CARD FORM
# =============================================================================
class TheJobCardFormTests(TransportBase):

    def setUp(self):
        super().setUp()
        self.card = self.make_card()
        self.spare = self.make_spare(self.card, transport='500', price='1900')
        self.spare.shop_name = str(self.shop.pk)
        self.spare.save()

    def payload(self, **row):
        data = {
            'registration_number': self.card.registration_number,
            'admitted_date': str(self.card.admitted_date),
            'brand_name': 'Toyota', 'model_name': 'Innova', 'mileage': '10000',
            'lead_mechanic': self.mech.id, 'car_color': 'Red',
            'concerns-TOTAL_FORMS': '0', 'concerns-INITIAL_FORMS': '0',
            'inventory-TOTAL_FORMS': '0', 'inventory-INITIAL_FORMS': '0',
            'labours-TOTAL_FORMS': '0', 'labours-INITIAL_FORMS': '0',
            'spares-TOTAL_FORMS': '1', 'spares-INITIAL_FORMS': '1',
            'spares-0-id': str(self.spare.pk),
            'spares-0-spare_part_name': 'Alternator',
            'spares-0-quantity': '',
            'spares-0-shop_name': str(self.shop.pk),
            'spares-0-status': 'PENDING',
            'spares-0-unit_price': '1000',
            'spares-0-transport_cost': '500',
            'spares-0-total_price': '1900',
            'spares-0-ordered_date': '', 'spares-0-received_date': '',
        }
        for key, value in row.items():
            if value is None:
                data.pop('spares-0-' + key, None)
            else:
                data['spares-0-' + key] = value
        return data

    def post(self, user, **row):
        return self.client_for(user).post(
            reverse('jobcard_edit', args=[self.card.pk]), self.payload(**row))

    def test_office_saves_a_transport_and_the_bill_does_not_move(self):
        resp = self.post(self.office, transport_cost='650')
        self.assertRedirects(resp, reverse('jobcard_edit', args=[self.card.pk]))
        self.spare.refresh_from_db()
        self.card.refresh_from_db()
        self.assertEqual(self.spare.transport_cost, D('650'))
        self.assertEqual(self.card.total_bill_amount, D('1900'))

    def test_a_negative_transport_is_refused_not_clamped(self):
        resp = self.post(self.office, transport_cost='-50')
        self.assertEqual(resp.status_code, 200)
        self.spare.refresh_from_db()
        self.assertEqual(self.spare.transport_cost, D('500'))

    def test_floor_cannot_set_a_transport(self):
        """Floor is shown no cost anywhere. A crafted post carrying one is
        pinned back to what is stored."""
        self.post(self.floor, transport_cost='9999')
        self.spare.refresh_from_db()
        self.assertEqual(self.spare.transport_cost, D('500'))

    def test_floor_cannot_ERASE_one_by_leaving_the_box_out(self):
        """⚠ The lock used to pin a price only `if key in data`, so a payload
        that simply OMITTED it was saved as blank — erasing Office's figure.
        Now pinned whether posted or not; the customer price beside it too."""
        self.post(self.floor, transport_cost=None, total_price=None, unit_price=None)
        self.spare.refresh_from_db()
        self.assertEqual(self.spare.transport_cost, D('500'))
        self.assertEqual(self.spare.total_price, D('1900'))
        self.assertEqual(self.spare.unit_price, D('1000'))

    def test_the_server_never_prices_a_part_from_its_transport(self):
        """A shop price and a transport with no customer price saves NO price:
        the suggestion is the browser's, and only a person's Save puts it on
        a bill (`workshop/pricing.py`)."""
        self.post(self.office, total_price='')
        self.spare.refresh_from_db()
        self.assertIsNone(self.spare.total_price)

    def test_a_row_holding_only_a_transport_is_refused_not_dropped(self):
        resp = self.client_for(self.office).post(
            reverse('jobcard_edit', args=[self.card.pk]),
            dict(self.payload(), **{
                'spares-TOTAL_FORMS': '2',
                'spares-1-id': '', 'spares-1-spare_part_name': '',
                'spares-1-quantity': '', 'spares-1-shop_name': '',
                'spares-1-status': 'PENDING', 'spares-1-unit_price': '',
                'spares-1-transport_cost': '300', 'spares-1-total_price': '',
                'spares-1-ordered_date': '', 'spares-1-received_date': '',
            }))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(JobCardSpareItem.objects.filter(job_card=self.card).count(), 1)

    def test_office_sees_the_column_between_the_two_prices(self):
        html = self.client_for(self.office).get(
            reverse('jobcard_edit', args=[self.card.pk])).content.decode()
        head = html.split('<tbody id="spare-list">', 1)[0].rsplit('<thead', 1)[1]
        headings = [t.strip() for t in re.findall(r'<th[^>]*>([^<]*)</th>', head)]
        self.assertEqual(headings[-3:], ['Shop Price (₹)', 'Transport (₹)', 'Customer Price (₹)'])

    def test_floor_still_posts_it_but_cannot_see_it(self):
        """Rendered inside the hidden cell, like the prices — an absent formset
        field saves as blank — and no Transport heading on Floor's page."""
        html = self.client_for(self.floor).get(
            reverse('jobcard_edit', args=[self.card.pk])).content.decode()
        tbody = html.split('<tbody id="spare-list">', 1)[1].split('</tbody>', 1)[0]
        hidden = tbody.split('<td class="d-none">', 1)[1].split('</td>', 1)[0]
        self.assertIn('spares-0-transport_cost', hidden)
        head = html.split('<tbody id="spare-list">', 1)[0].rsplit('<thead', 1)[1]
        self.assertNotIn('Transport (₹)', head)

    def test_the_added_row_template_carries_the_box_in_the_same_place(self):
        with open(FORM_TEMPLATE, encoding='utf-8') as fh:
            source = fh.read()

        def order(chunk):
            names = ('unit_price', 'transport_cost', 'total_price')
            return [n for _, n in sorted((chunk.find(n), n) for n in names if chunk.find(n) != -1)]

        live = source.split('<tbody id="spare-list">', 1)[1].split('</tbody>', 1)[0]
        clone = source.split('<tbody id="empty-spare-form">', 1)[1].split('</tbody>', 1)[0]
        self.assertEqual(order(live), ['unit_price', 'transport_cost', 'total_price'])
        self.assertEqual(order(clone), order(live))


class APartsZeroSurvivesASaveTests(TransportBase):
    """
    ⚠ Found while building transport, measured before it was fixed: a part saved
    at ₹0 came back NULL after one ordinary save, because the page blanked every
    zero box on load and the blank posted. ₹0 (given away, a free warranty part)
    and blank (nobody priced it) are different facts. Nothing in this suite runs
    the script, so the contract it relies on is pinned.
    """

    def test_the_zero_clearing_script_leaves_a_parts_money_boxes_alone(self):
        with open(FORM_TEMPLATE, encoding='utf-8') as fh:
            source = fh.read()
        body = source.split('function clearZeroInputs()', 1)[1].split('\n        }', 1)[0]
        self.assertIn('PART_MONEY.test', body)
        rule = source.split('const PART_MONEY = ', 1)[1].split(';', 1)[0]
        for field in ('unit_price', 'transport_cost', 'total_price', 'customer_rate'):
            self.assertIn(field, rule)
        self.assertIn('spares', rule)
        self.assertIn('inventory', rule)

    def test_a_posted_zero_is_stored_as_zero(self):
        card = self.make_card()
        spare = self.make_spare(card, transport=None, price='0')
        self.assertEqual(JobCardSpareItem.objects.get(pk=spare.pk).total_price, D('0'))


# =============================================================================
# THE SCREENS THAT REPORT IT
# =============================================================================
class TheScreensSayItTests(TransportBase):

    def test_the_read_only_card_puts_it_on_the_cost_line(self):
        card = self.make_card()
        self.make_spare(card, shop_price='900', transport='500', price='1900')
        html = self.client_for(self.office).get(
            reverse('jobcard_detail', args=[card.pk])).content.decode()
        # The ELEMENT, not the first mention — the page's own stylesheet
        # declares `.dv-cost-col` above it.
        cost = html.split('class="dv-cost-col">', 1)[1].split('</div>', 1)[0]
        self.assertIn('₹900 + ₹500 transport', cost)

    def test_the_bill_never_prints_it(self):
        card = self.make_card()
        self.make_spare(card, shop_price='900', transport='437', price='1900')
        html = self.client_for(self.office).get(
            reverse('invoice_view', args=[card.pk])).content.decode()
        self.assertNotIn('437', html)
        self.assertNotIn('ransport', html)

    def test_the_car_profiles_gross_profit_is_after_transport(self):
        card = self.make_card(completed=True)
        card.total_bill_amount = D('1900')
        card.save()
        self.make_spare(card)
        resp = self.client_for(self.owner).get(
            reverse('car_profile_detail', args=[card.registration_number]))
        self.assertEqual(resp.context['car_info']['gross_profit'], D('400'))

    def test_the_spare_parts_section_shows_it_only_when_there_is_some(self):
        card = self.make_card()
        spare = self.make_spare(card)
        owner = self.client_for(self.owner)
        url = reverse('analysis_insight_section', args=['spare_parts'])
        html = owner.get(url).content.decode()
        self.assertIn('<th class="num">Transport</th>', html)
        spare.transport_cost = None
        spare.save()
        html = owner.get(url).content.decode()
        self.assertNotIn('<th class="num">Transport</th>', html)


# =============================================================================
# UNASSIGNED SPARES
# =============================================================================
class TheHubCarriesTransportTests(TransportBase):

    def add(self, user, **extra):
        data = {'shop': str(self.shop.pk), 'spare_part_name': 'Starter Motor',
                'quantity': '1', 'unit_price': '3000', 'transport_cost': '400',
                'ordered_date': str(self.today), 'received_date': str(self.today)}
        data.update(extra)
        return self.client_for(user).post(reverse('unassigned_spare_add'), data)

    def test_office_records_it_on_arrival(self):
        self.add(self.office)
        item = JobCardSpareItem.objects.get(spare_part_name='Starter Motor')
        self.assertEqual(item.transport_cost, D('400'))
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.total_purchased_amount, D('3000'))

    def test_floor_cannot_write_one(self):
        self.add(self.floor)
        item = JobCardSpareItem.objects.get(spare_part_name='Starter Motor')
        self.assertIsNone(item.transport_cost)
        self.assertIsNone(item.unit_price)

    def test_a_negative_one_is_refused(self):
        self.add(self.office, transport_cost='-10')
        self.assertFalse(JobCardSpareItem.objects.filter(spare_part_name='Starter Motor').exists())

    def edit(self, item, **extra):
        data = {'shop': str(self.shop.pk), 'spare_part_name': item.spare_part_name,
                'quantity': '1', 'unit_price': '3000',
                'ordered_date': str(self.today), 'received_date': str(self.today)}
        data.update(extra)
        data = {k: v for k, v in data.items() if v is not None}
        return self.client_for(self.office).post(
            reverse('unassigned_spare_edit', args=[item.pk]), data)

    def test_an_edit_from_a_page_without_the_box_keeps_it(self):
        self.add(self.office)
        item = JobCardSpareItem.objects.get(spare_part_name='Starter Motor')
        self.edit(item)          # no transport_cost key at all
        item.refresh_from_db()
        self.assertEqual(item.transport_cost, D('400'))

    def test_clearing_the_box_clears_it(self):
        self.add(self.office)
        item = JobCardSpareItem.objects.get(spare_part_name='Starter Motor')
        self.edit(item, transport_cost='')
        item.refresh_from_db()
        self.assertIsNone(item.transport_cost)

    def test_the_hub_table_keeps_its_hidden_label_inside_the_scroller(self):
        """
        ⚠ Found while checking this page on a phone (2026-10-01): the Actions
        heading is a `visually-hidden` label — `position: absolute` — and with
        no positioned cell around it, it escaped the table's sideways scroller
        and widened the whole page to 712px at 375. Nothing in this suite runs
        CSS, so the declaration is pinned.
        """
        with open('workshop/templates/workshop/spare_shops/unassigned_hub.html',
                  encoding='utf-8') as fh:
            style = fh.read().split('<style>', 1)[1].split('</style>', 1)[0]
        rule = style.split('.ua-table th {', 1)[1].split('}', 1)[0]
        self.assertIn('position: relative', rule)

    def test_a_transport_with_no_received_date_is_refused(self):
        """Its cash is filed on the Received date; with none it would be in
        no period of Cash Tracking at all."""
        self.add(self.office)
        item = JobCardSpareItem.objects.get(spare_part_name='Starter Motor')
        self.edit(item, transport_cost='400', received_date='')
        item.refresh_from_db()
        self.assertEqual(item.received_date, self.today)

    def test_a_zero_transport_needs_no_received_date(self):
        """Blank and ₹0 both mean no transport — there is no cash to file, so
        clearing the Received date is not refused over it."""
        self.add(self.office)
        item = JobCardSpareItem.objects.get(spare_part_name='Starter Motor')
        self.edit(item, transport_cost='0', received_date='')
        item.refresh_from_db()
        self.assertIsNone(item.received_date)


# =============================================================================
# THE CASHBOOK ASKS
# =============================================================================
class TheCashbookAsksAboutPartTransportTests(TransportBase):

    def matched(self, text):
        from workshop.cashbook_views import _steers
        for row in _steers():
            for word in row['words']:
                if re.search(r'\b' + re.escape(word) + r'\b', text, re.I):
                    return row
        return None

    def test_transport_typed_there_is_asked_about(self):
        row = self.matched('Transport for alternator')
        self.assertIsNotNone(row)
        self.assertEqual(row['ask'], 'Is this transport for a part?')
        self.assertIn('twice', row['why'])
        self.assertIsNotNone(self.matched('Parcel charge'))

    def test_courier_charges_stay_quiet(self):
        """An ordinary ledger row the existing word-boundary rule keeps silent."""
        self.assertIsNone(self.matched('Courier Charges'))

"""
Warranty cards — free work on a car because of an EARLIER bill (2026-10-02, the
owners' design). Step 1: the core.

A warranty card is a `JobCard` with `kind=WARRANTY`, so everything a job card
does it does too. These tests pin down the few things that differ, and the
safety rules that hold them:

  1. A warranty card's total is always ₹0 — whatever was posted.
  2. A warranty card is never settled, and never goes to a Fleet Account.
  3. It has its own number series, WR-YY-NNN; the JB series does not move.
  4. ONE CLAIM IS ONE PART (2026-10-07): a claim is a warranty card for one
     part of one earlier bill, linked to the exact part it replaces — never
     for the work alone (2026-10-08). One open claim per part; a finished
     claim makes the replacement the part to claim next ("2nd claim"). A
     warranty card never blocks a job card, nor a job card it.
  5. The link is picked from the car's own bills, never typed: another car's
     bill, a card still on the floor or an unknown number is refused.

Its COST is untouched, and the last class proves it still reaches the Profit
page exactly as a job card's parts do — that is the warranty's real cost.
"""
from datetime import date, timedelta
from decimal import Decimal as D

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from workshop import analysis_engine as engine
from workshop import warranty
from inventory.models import Category, Item
from workshop.models import (
    BulkPayer, DeletionLog, JobCard, JobCardConcern, JobCardLabourItem,
    JobCardSpareItem, Mechanic, OldBill, OldBillPartLine, SpareShop, bill_cards,
)


class WarrantyBase(TestCase):
    def setUp(self):
        for name in ('Owner', 'Office', 'Floor'):
            Group.objects.get_or_create(name=name)
        self.office = User.objects.create_user(username='wr_office', password='pw')
        self.office.groups.add(Group.objects.get(name='Office'))
        self.floor = User.objects.create_user(username='wr_floor', password='pw')
        self.floor.groups.add(Group.objects.get(name='Floor'))

        self.today = timezone.localdate()
        self.mech = Mechanic.objects.create(name='Ravi')
        self.shop = SpareShop.objects.create(name='Spare club')
        self.plate = 'KL 10 AA 1000'

    def client_for(self, user):
        c = Client()
        c.force_login(user)
        return c

    def sold(self, when=None, plate=None, completed=True, **kw):
        """A finished job card: the bill a warranty is claimed against."""
        when = when or (self.today - timedelta(days=60))
        card = JobCard.objects.create(
            admitted_date=when, brand_name='Audi', model_name='A4',
            registration_number=plate or self.plate, lead_mechanic=self.mech,
            customer_name='Anwar', customer_contact='9207217978',
            car_color='Red', completed=completed,
            completed_date=when if completed else None, **kw)
        JobCardSpareItem.objects.create(
            job_card=card, source=JobCardSpareItem.SOURCE_SHOP,
            spare_part_name='Starter Motor', shop=self.shop,
            unit_price=D('6000'), total_price=D('8400'))
        card.refresh_from_db()
        return card

    def open_for(self, card_or_number, plate=None):
        """A claim for the FIRST part of this bill — the plainest warranty
        card. A bill with no part names none, and is refused as one."""
        number = getattr(card_or_number, 'bill_number', card_or_number)
        bill = warranty.find(number)
        key = next(iter(bill.rows), None) if bill else None
        return warranty.open_claim(plate or self.plate, key or 'c0')

    def claimed(self, card):
        """The part a warranty card claims."""
        return warranty.claimed_part(card)

    def answer(self, card, price, **kw):
        """The shop's answer to a claim — its Shop Price (and transport)."""
        JobCardSpareItem.objects.filter(pk=self.claimed(card).pk).update(unit_price=price, **kw)

    def claim(self, part, plate=None):
        """A claim for ONE part — a card's part or an old bill's line."""
        key = ('o' if isinstance(part, OldBillPartLine) else 'c') + str(part.pk)
        return warranty.open_claim(plate or self.plate, part=key)


# =============================================================================
# 1. ALWAYS ₹0
# =============================================================================
class AWarrantyCardChargesNothingTests(WarrantyBase):

    def setUp(self):
        super().setUp()
        self.wr = self.open_for(self.sold())

    def test_a_refit_part_is_free_to_the_customer_and_keeps_its_cost(self):
        """The customer price is pinned to ₹0; the shop price and transport —
        the warranty's real cost — are kept exactly as typed."""
        part = JobCardSpareItem.objects.create(
            job_card=self.wr, source=JobCardSpareItem.SOURCE_SHOP,
            spare_part_name='Starter Motor', shop=self.shop,
            unit_price=D('2500'), transport_cost=D('400'),
            total_price=D('9999'), customer_rate=D('100'), quantity=D('1'))
        part.refresh_from_db()
        self.wr.refresh_from_db()
        self.assertEqual(part.total_price, D('0'))
        self.assertIsNone(part.customer_rate)
        self.assertEqual(part.unit_price, D('2500'))
        self.assertEqual(part.transport_cost, D('400'))
        self.assertEqual(self.wr.total_bill_amount, D('0'))

    def test_labour_cannot_be_charged(self):
        self.wr.labour_amount = D('3000')
        self.wr.save()
        self.wr.update_totals()
        self.wr.refresh_from_db()
        self.assertEqual(self.wr.labour_amount, D('0'))
        self.assertEqual(self.wr.total_bill_amount, D('0'))

    def test_a_price_written_past_save_still_bills_nothing(self):
        """`update_totals` never sums a warranty card's rows, so a figure that
        reached a row by a bulk `.update()` cannot put a charge on it."""
        part = JobCardSpareItem.objects.create(
            job_card=self.wr, source=JobCardSpareItem.SOURCE_SHOP,
            spare_part_name='Relay', unit_price=D('300'))
        JobCardSpareItem.objects.filter(pk=part.pk).update(total_price=D('500'))
        self.wr.update_totals()
        self.wr.refresh_from_db()
        self.assertEqual(self.wr.total_bill_amount, D('0'))

    def test_the_shop_is_owed_what_it_charged(self):
        """The shop's ledger works unchanged: a shop that charged for the
        replacement is owed it."""
        self.shop.refresh_from_db()
        before = self.shop.get_pending_balance
        JobCardSpareItem.objects.create(
            job_card=self.wr, source=JobCardSpareItem.SOURCE_SHOP,
            spare_part_name='Starter Motor', shop=self.shop, unit_price=D('2500'))
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.get_pending_balance, before + D('2500'))


# =============================================================================
# 2. NEVER SETTLED
# =============================================================================
class AWarrantyCardIsNeverSettledTests(WarrantyBase):

    def setUp(self):
        super().setUp()
        self.wr = self.open_for(self.sold())

    def test_save_undoes_any_payment_state(self):
        fleet = BulkPayer.objects.create(customer_name='Acme Fleet')
        self.wr.payment_status = 'PAID'
        self.wr.received_amount = D('500')
        self.wr.discount_amount = D('100')
        self.wr.payment_method = 'CASH'
        self.wr.paid_date = timezone.now()
        self.wr.bulk_payer = fleet
        self.wr.save()
        self.wr.refresh_from_db()
        self.assertEqual(self.wr.payment_status, 'PENDING')
        self.assertEqual(self.wr.received_amount, D('0'))
        self.assertEqual(self.wr.discount_amount, D('0'))
        self.assertIsNone(self.wr.payment_method)
        self.assertIsNone(self.wr.paid_date)
        self.assertIsNone(self.wr.bulk_payer_id)

    def test_the_settle_screen_refuses_it(self):
        resp = self.client_for(self.office).post(
            reverse('update_bill_status', args=[self.wr.pk]),
            {'received_amount': '500', 'payment_method': 'CASH'})
        self.assertRedirects(resp, reverse('jobcard_edit', args=[self.wr.pk]),
                             fetch_redirect_response=False)
        self.wr.refresh_from_db()
        self.assertEqual(self.wr.payment_status, 'PENDING')
        self.assertEqual(self.wr.received_amount, D('0'))

    def test_it_cannot_go_to_a_fleet_account(self):
        """`job_cards.add()` writes with `.update()`, which never runs save(),
        so this refusal is the only thing that stops it."""
        fleet = BulkPayer.objects.create(customer_name='Acme Fleet')
        self.client_for(self.office).post(
            reverse('move_jobcard_to_bulk'),
            {'job_card_id': str(self.wr.pk), 'bulk_payer_id': str(fleet.pk)})
        self.wr.refresh_from_db()
        self.assertIsNone(self.wr.bulk_payer_id)


# =============================================================================
# 3. ITS OWN NUMBER SERIES
# =============================================================================
class TheWarrantyNumberSeriesTests(WarrantyBase):

    def test_warranty_cards_count_their_own_series_from_001(self):
        year = str(self.today.year)[2:]
        first = self.open_for(self.sold())
        second = self.open_for(self.sold(plate='KL 10 AA 2000'), plate='KL 10 AA 2000')
        self.assertEqual(first.bill_number, f'WR-{year}-001')
        self.assertEqual(second.bill_number, f'WR-{year}-002')

    def test_the_JB_series_does_not_move(self):
        """A warranty card takes no JB number, so the next job card is the
        next JB in line exactly as if no warranty card existed."""
        sold = self.sold()
        jb_before = int(sold.bill_number.rsplit('-', 1)[1])
        self.open_for(sold)
        nxt = JobCard.objects.create(
            admitted_date=self.today, brand_name='Honda', model_name='City',
            registration_number='KL 07 ZZ 1')
        self.assertTrue(nxt.bill_number.startswith('JB-'))
        self.assertEqual(int(nxt.bill_number.rsplit('-', 1)[1]), jb_before + 1)

    def test_the_series_restarts_each_year(self):
        """Numbered by the card's own admitted year, like JB."""
        sold = self.sold()
        JobCard.objects.create(
            kind=JobCard.KIND_WARRANTY, warranty_for=sold.bill_number,
            admitted_date=date(2025, 12, 30), brand_name='Audi', model_name='A4',
            registration_number=self.plate, completed=True, completed_date=date(2025, 12, 31))
        this_year = self.open_for(sold)
        self.assertEqual(this_year.bill_number, f'WR-{str(self.today.year)[2:]}-001')


# =============================================================================
# 4. ONE CLAIM IS ONE PART — AND NEVER AGAINST A JOB CARD
# =============================================================================
class OneClaimIsOnePartTests(WarrantyBase):

    def test_a_claim_carries_its_one_part_linked_to_the_part_it_replaces(self):
        sold = self.sold()
        original = sold.spares.get()
        wr = self.claim(original)
        part = wr.spares.get()
        self.assertEqual(part.replaces_id, original.pk)
        self.assertEqual(warranty.claimed_part(wr).pk, part.pk)
        self.assertEqual(warranty.claim_round(part), 1)

    def test_a_part_with_an_open_claim_cannot_be_claimed_again(self):
        sold = self.sold()
        first = self.claim(sold.spares.get())
        with self.assertRaises(warranty.WarrantyRefused) as caught:
            self.claim(sold.spares.get())
        self.assertEqual(str(caught.exception),
                         f'Starter Motor is already being claimed on {first.bill_number}.')
        self.assertEqual(JobCard.objects.filter(kind=JobCard.KIND_WARRANTY).count(), 1)

    def test_a_finished_claim_sends_the_next_failure_to_the_replacement(self):
        """The second claim is made on the part the first claim fitted — never
        on the old bill again — and says it is the 2nd."""
        sold = self.sold()
        first = self.claim(sold.spares.get())
        first.mark_completed()
        with self.assertRaises(warranty.WarrantyRefused) as caught:
            self.claim(sold.spares.get())
        self.assertEqual(str(caught.exception),
                         f'Starter Motor was replaced on {first.bill_number} — claim the new one there.')
        second = self.claim(first.spares.get())
        self.assertEqual(second.warranty_for, first.bill_number)
        replacement = warranty.claimed_part(second)
        self.assertEqual(replacement.replaces_id, first.spares.get().pk)
        self.assertEqual(warranty.claim_round(replacement), 2)
        self.assertEqual(warranty.round_label(2), '2nd claim')
        self.assertEqual(warranty.round_label(3), '3rd claim')
        self.assertEqual(warranty.round_label(11), '11th claim')
        self.assertEqual(warranty.round_label(1), '')       # the first needs no word

    def test_each_part_of_one_bill_is_its_own_claim(self):
        sold = self.sold()
        relay = JobCardSpareItem.objects.create(
            job_card=sold, source=JobCardSpareItem.SOURCE_SHOP,
            spare_part_name='Starter Relay', shop=self.shop, unit_price=D('300'))
        a = self.claim(sold.spares.get(spare_part_name='Starter Motor'))
        b = self.claim(relay)
        self.assertNotEqual(a.pk, b.pk)
        self.assertEqual([p.spare_part_name for p in a.spares.all()], ['Starter Motor'])
        self.assertEqual([p.spare_part_name for p in b.spares.all()], ['Starter Relay'])

    def test_a_cancelled_claim_frees_the_part(self):
        sold = self.sold()
        wr = self.claim(sold.spares.get())
        warranty.cancel_warranty(wr)
        again = self.claim(sold.spares.get())
        self.assertTrue(again.is_warranty)

    def test_there_is_no_claim_for_the_work_alone(self):
        """A fix with no part is done without a card (the owners,
        2026-10-08), so a claim that names no part opens nothing."""
        self.sold()
        for nothing in (None, ''):
            with self.assertRaises(warranty.WarrantyRefused) as caught:
                warranty.open_claim(self.plate, nothing)
            self.assertEqual(str(caught.exception), 'Pick the part that failed.')
        self.assertFalse(JobCard.objects.filter(kind=JobCard.KIND_WARRANTY).exists())

    def test_a_warranty_card_never_blocks_a_job_card(self):
        self.open_for(self.sold())
        self.assertIsNone(JobCard.get_active_conflict(self.plate))
        resp = self.client_for(self.office).post(reverse('jobcard_create'), {
            'registration_number': self.plate, 'admitted_date': str(self.today),
            'brand_name': 'Audi', 'model_name': 'A4', 'lead_mechanic': self.mech.id,
            'concerns-TOTAL_FORMS': '0', 'concerns-INITIAL_FORMS': '0',
            'inventory-TOTAL_FORMS': '0', 'inventory-INITIAL_FORMS': '0',
            'labours-TOTAL_FORMS': '0', 'labours-INITIAL_FORMS': '0',
            'spares-TOTAL_FORMS': '0', 'spares-INITIAL_FORMS': '0',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            JobCard.objects.filter(kind=JobCard.KIND_JOB, completed=False,
                                   registration_number=self.plate).count(), 1)

    def test_a_job_card_never_blocks_a_warranty_card(self):
        sold = self.sold()
        JobCard.objects.create(
            admitted_date=self.today, brand_name='Audi', model_name='A4',
            registration_number=self.plate)          # paid work, on the floor
        wr = self.claim(sold.spares.get())
        self.assertTrue(wr.is_warranty)

    def test_undo_completion_answers_the_claims_own_rule(self):
        """An open JOB card does not stop a claim going back on the floor; a
        claim already made on its replacement does."""
        sold = self.sold()
        wr = self.claim(sold.spares.get())
        wr.mark_completed()
        JobCard.objects.create(admitted_date=self.today, brand_name='Audi',
                               model_name='A4', registration_number=self.plate)
        self.client_for(self.office).post(reverse('undo_completed', args=[wr.pk]))
        wr.refresh_from_db()
        self.assertFalse(wr.completed)

        wr.mark_completed()
        again = self.claim(wr.spares.get())          # its replacement failed too
        resp = self.client_for(self.office).post(reverse('undo_completed', args=[wr.pk]), follow=True)
        wr.refresh_from_db()
        self.assertTrue(wr.completed)
        self.assertContains(resp, f'{again.bill_number} has claimed the same part since.')

    def test_a_part_with_a_claim_stays_on_its_bill(self):
        """Deleting it from the job card, or moving it to Unassigned Spares,
        would cut the claim's link — both are refused, and say why."""
        from workshop.forms import JobCardSpareFormSet
        sold = self.sold()
        part = sold.spares.get()
        wr = self.claim(part)
        formset = JobCardSpareFormSet({
            'spares-TOTAL_FORMS': '1', 'spares-INITIAL_FORMS': '1',
            'spares-0-id': str(part.pk), 'spares-0-spare_part_name': 'Starter Motor',
            'spares-0-status': 'RECEIVED', 'spares-0-DELETE': 'on',
        }, instance=sold, prefix='spares')
        self.assertFalse(formset.is_valid())
        self.assertIn(f'claimed under warranty on {wr.bill_number}', str(formset.non_form_errors()))
        self.client_for(self.office).post(reverse('spare_shop_unassign_item', args=[part.pk]))
        part.refresh_from_db()
        self.assertEqual(part.job_card_id, sold.pk)


# =============================================================================
# 5. THE LINK — PICKED, NEVER TYPED
# =============================================================================
class TheLinkToTheEarlierBillTests(WarrantyBase):

    def test_the_new_card_takes_the_car_and_customer_from_the_claimed_bill(self):
        sold = self.sold()
        wr = self.open_for(sold)
        self.assertEqual(wr.kind, JobCard.KIND_WARRANTY)
        self.assertEqual(wr.warranty_for, sold.bill_number)
        self.assertEqual((wr.registration_number, wr.brand_name, wr.model_name),
                         (self.plate, 'Audi', 'A4'))
        self.assertEqual((wr.customer_name, wr.customer_contact), ('Anwar', '9207217978'))
        self.assertEqual(wr.car_color, 'Red')
        self.assertEqual(wr.admitted_date, self.today)
        self.assertFalse(wr.completed)
        self.assertIsNone(wr.lead_mechanic_id)       # this visit's to choose

    def test_a_card_still_on_the_floor_is_refused(self):
        """A part that fails before the car leaves is fixed on that card."""
        open_card = self.sold(completed=False)
        with self.assertRaises(warranty.WarrantyRefused) as caught:
            self.open_for(open_card)
        self.assertIn('still on the floor', str(caught.exception))

    def test_another_cars_bill_is_refused(self):
        other = self.sold(plate='KL 99 XX 9999')
        with self.assertRaises(warranty.WarrantyRefused):
            self.open_for(other, plate=self.plate)
        self.assertFalse(JobCard.objects.filter(kind=JobCard.KIND_WARRANTY).exists())

    def test_an_unknown_number_is_refused(self):
        with self.assertRaises(warranty.WarrantyRefused):
            self.open_for('JB-26-999')

    def test_a_repeat_claim_is_opened_against_the_warranty_card(self):
        """The same part failing again: the claim points at the warranty card
        where the failing part was fitted, so the chain is JB → WR → WR."""
        sold = self.sold()
        first = self.open_for(sold)
        first.mark_completed()
        second = self.open_for(first)
        self.assertEqual(second.warranty_for, first.bill_number)

    def test_an_excel_era_bill_can_be_claimed_against(self):
        old = OldBill.objects.create(
            bill_number='JB-25-097', bill_date=date(2025, 11, 3),
            registration_number='KL 05 OB 1', brand_name='', model_name='',
            customer_name='Shibu')
        OldBillPartLine.objects.create(old_bill=old, name='Alternator')
        # The car is known from a later job card, which supplies the make and
        # model the Excel bill left blank.
        JobCard.objects.create(
            admitted_date=self.today - timedelta(days=5), brand_name='Honda',
            model_name='City', registration_number='KL 05 OB 1',
            completed=True, completed_date=self.today - timedelta(days=5))
        wr = self.open_for('JB-25-097', plate='KL 05 OB 1')
        self.assertEqual(wr.warranty_for, 'JB-25-097')
        self.assertEqual((wr.brand_name, wr.model_name), ('Honda', 'City'))
        self.assertEqual(wr.customer_name, 'Shibu')
        self.assertIsNone(wr.customer_contact)
        old.refresh_from_db()
        self.assertEqual(old.total_amount, D('0'))   # nothing written to it

    def test_bills_for_lists_finished_bills_newest_first_with_each_parts_claim(self):
        old = OldBill.objects.create(
            bill_number='JB-25-090', bill_date=date(2025, 6, 1),
            registration_number=self.plate, brand_name='Audi', model_name='A4')
        older = self.sold(when=self.today - timedelta(days=300))
        newer = self.sold(when=self.today - timedelta(days=30))
        self.sold(completed=False, when=self.today)   # on the floor: not offered
        wr = self.claim(older.spares.get())
        bills = warranty.bills_for(self.plate)
        self.assertEqual([b.number for b in bills],
                         [newer.bill_number, older.bill_number, old.bill_number])
        claimed = bills[1].shop_parts[0]
        self.assertEqual((claimed['status'], claimed['claim']['pk']), ('claiming', wr.pk))
        self.assertEqual(bills[0].shop_parts[0]['status'], '')
        self.assertTrue(bills[2].is_old_bill)

        wr.mark_completed()
        replaced = {b.number: b for b in warranty.bills_for(self.plate)}
        self.assertEqual(replaced[older.bill_number].shop_parts[0]['status'], 'replaced')
        # The finished warranty card is a bill too, carrying the replacement.
        self.assertEqual(replaced[wr.bill_number].shop_parts[0]['status'], '')

    def test_a_part_fitted_again_on_a_newer_bill_says_so_quietly(self):
        """Every sold() bill carries a Starter Motor: the older one is told a
        newer one exists — a note, never a block."""
        older = self.sold(when=self.today - timedelta(days=300))
        newer = self.sold(when=self.today - timedelta(days=30))
        bills = warranty.bills_for(self.plate)
        self.assertEqual(bills[0].shop_parts[0]['newer'], '')
        self.assertEqual(bills[1].shop_parts[0]['newer'], newer.bill_number)
        self.assertTrue(self.claim(older.spares.get()).is_warranty)

    def test_age_phrase(self):
        today = date(2026, 10, 12)
        cases = {
            date(2026, 10, 12): 'today',
            date(2026, 10, 11): '1 day',
            date(2026, 9, 20): '22 days',
            date(2026, 9, 12): '1 month',
            date(2026, 9, 9): '1 month 3 days',
            date(2026, 3, 12): '7 months',
            date(2026, 3, 13): '6 months 29 days',   # the edge a warranty is decided at
            date(2026, 8, 31): '1 month 12 days',    # 31 Aug + 1 month stops at 30 Sep
            date(2025, 10, 12): '1 year',
            date(2025, 8, 12): '1 year 2 months',
            date(2025, 8, 7): '1 year 2 months 5 days',
            date(2023, 9, 12): '3 years 1 month',
            date(2026, 10, 13): '',                # the future: no age
        }
        for then, words in cases.items():
            self.assertEqual(warranty.age_phrase(then, today), words, then)


# =============================================================================
# THE DOOR — Car Profile → Warranty → pick the bill → Open
# =============================================================================
class TheWarrantyDoorTests(WarrantyBase):

    def setUp(self):
        super().setUp()
        self.sold_card = self.sold()
        self.url = reverse('warranty_start', args=[self.plate])

    def test_the_car_profile_offers_the_door(self):
        resp = self.client_for(self.office).get(
            reverse('car_profile_detail', args=[self.plate]))
        self.assertContains(resp, f'href="{self.url}"')

    def test_the_page_lists_the_bill_with_its_age(self):
        resp = self.client_for(self.office).get(self.url)
        self.assertContains(resp, self.sold_card.bill_number)
        self.assertContains(resp, warranty.age_phrase(self.sold_card.admitted_date))
        self.assertContains(resp, 'Starter Motor')

    def test_floor_cannot_open_the_page(self):
        resp = self.client_for(self.floor).get(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_each_part_says_what_its_shops_ledger_says(self):
        """Shop, dates and SHOP price — the facts an owner matches against the
        shop's ledger — never the customer price. An Excel line's amount is
        what the customer paid, so it prints none."""
        sold = self.sold(when=date(2026, 3, 10), plate='KL 03 C 3')
        JobCardSpareItem.objects.filter(job_card=sold).update(
            ordered_date=date(2026, 3, 1), received_date=date(2026, 3, 5))
        old = OldBill.objects.create(bill_number='JB-25-050', bill_date=date(2025, 4, 1),
                                     registration_number='KL 03 C 3')
        OldBillPartLine.objects.create(old_bill=old, name='Alternator', amount=D('3000'))
        html = self.client_for(self.office).get(
            reverse('warranty_start', args=['KL 03 C 3'])).content.decode()
        # Each piece whole, so a phone breaks the line between them.
        self.assertIn('<span class="wn-part-meta"><span class="wn-bit">Spare club ·</span> '
                      '<span class="wn-bit">01/03 – 05/03 ·</span> <span class="wn-bit">₹6,000</span></span>', html)
        self.assertNotIn('8,400', html)
        self.assertNotIn('3,000', html)

    def test_opening_lands_on_the_new_card(self):
        spare = self.sold_card.spares.get()
        resp = self.client_for(self.office).post(self.url, {'part': f'c{spare.pk}'})
        wr = JobCard.objects.get(kind=JobCard.KIND_WARRANTY)
        self.assertRedirects(resp, reverse('warranty_card', args=[wr.pk]),
                             fetch_redirect_response=False)

    def test_a_post_naming_no_part_opens_nothing(self):
        """Including a page opened before the work-only claim went, which
        still posts `work_only`."""
        for data in ({}, {'work_only': self.sold_card.bill_number}):
            resp = self.client_for(self.office).post(self.url, data, follow=True)
            self.assertEqual(resp.redirect_chain[-1][0], self.url)
            self.assertContains(resp, 'Pick the part that failed.')
        self.assertFalse(JobCard.objects.filter(kind=JobCard.KIND_WARRANTY).exists())

    def test_a_claimed_part_is_linked_not_offered_again(self):
        spare = self.sold_card.spares.get()
        wr = self.claim(spare)
        html = self.client_for(self.office).get(self.url).content.decode()
        self.assertIn(f'href="{reverse("warranty_card", args=[wr.pk])}">Being claimed · {wr.bill_number}</a>', html)
        self.assertNotIn(f'name="part" value="c{spare.pk}"', html)
        wr.mark_completed()
        html = self.client_for(self.office).get(self.url).content.decode()
        self.assertIn(f'>Replaced · {wr.bill_number}</a>', html)
        # The replacement, on the finished warranty card, is the part to claim.
        self.assertIn(f'name="part" value="c{wr.spares.get().pk}"', html)

    def test_the_work_alone_is_never_offered(self):
        html = self.client_for(self.office).get(self.url).content.decode()
        for gone in ('Claim work only', 'name="work_only"', 'Claim the work only?', 'Work claim open'):
            self.assertNotIn(gone, html, gone)

    def test_a_repeat_claim_says_its_number_before_it_is_pressed(self):
        """A part a claim fitted: its button reads "2nd claim", its open claim
        "2nd claim open", and after that one is fitted, "3rd claim"."""
        first = self.claim(self.sold_card.spares.get())
        first.mark_completed()
        html = self.client_for(self.office).get(self.url).content.decode()
        self.assertIn('aria-label="Claim Starter Motor">2nd claim</button>', html)
        self.assertIn('data-confirm-title="Make the 2nd claim?"', html)
        second = self.claim(first.spares.get())
        html = self.client_for(self.office).get(self.url).content.decode()
        self.assertIn(f'>2nd claim open · {second.bill_number}</a>', html)
        second.mark_completed()
        html = self.client_for(self.office).get(self.url).content.decode()
        self.assertIn('aria-label="Claim Starter Motor">3rd claim</button>', html)
        third = self.claim(second.spares.get())
        self.assertEqual(warranty.claim_round(warranty.claimed_part(third)), 3)

    def test_a_repeat_claim_is_aged_from_the_bill_the_part_was_first_fitted_on(self):
        """A claim never restarts the warranty clock. The warranty card that
        fitted the replacement is tinted; under its number is ITS OWN date and
        what it is for (one date rule for every block), and the clock — the
        FIRST bill and the age since — sits on the part it fitted, beside the
        button, and in the claim question."""
        first = self.claim(self.sold_card.spares.get())
        first.mark_completed()
        html = self.client_for(self.office).get(self.url).content.decode()
        block = html.split(f'data-bill="{first.bill_number}"', 1)[1].split('</section>', 1)[0]
        self.assertIn('class="wn-bill wn-bill-wr"', html)
        sold, when = self.sold_card.bill_number, self.sold_card.admitted_date
        day, age = f'{when.day} {when:%b %Y}', warranty.age_phrase(when)
        self.assertIn(f'<span class="wn-bit">{self.today.day} {self.today:%b %Y} ·</span> '
                      f'<span class="wn-bit">for <a class="wn-jump" href="#bill-{sold}">{sold}</a></span>', block)
        self.assertNotIn('1st claim', block)                     # the first needs no word
        self.assertIn(f'First fitted <a class="wn-jump" href="#bill-{sold}">{sold}</a> ·</span> '
                      f'<b class="wn-bit">{age}</b>', block)
        self.assertNotIn(day, block.split('<div class="wn-part"', 1)[0])   # one date in the header
        self.assertIn(f'Starter Motor, first fitted on {sold} · {day} · {age}.', block)
        # A job card's own block is its own first bill, and is not tinted.
        own = html.split(f'data-bill="{self.sold_card.bill_number}"', 1)[0].rsplit('<section', 1)[1]
        self.assertNotIn('wn-bill-wr', own)

    def test_the_page_costs_the_same_however_long_the_history(self):
        """Built for years of bills: the page's database work does not grow
        with bills, parts, claims or Excel bills. Asserted as the invariant —
        a short history and a long one cost the same — never a magic number."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        # Both histories hold an Excel bill: with none at all, Django skips
        # the query for their lines — one query cheaper, not a growth.
        excel = OldBill.objects.create(bill_number='JB-25-050', bill_date=date(2025, 5, 1),
                                       registration_number=self.plate)
        OldBillPartLine.objects.create(old_bill=excel, name='Wiper Blades')
        client = self.client_for(self.office)
        client.get(self.url)                                   # the session settles first
        with CaptureQueriesContext(connection) as short:
            client.get(self.url)
        for n in range(6):
            card = self.sold(when=self.today - timedelta(days=100 + n))
            JobCardSpareItem.objects.create(job_card=card, source=JobCardSpareItem.SOURCE_SHOP,
                                            spare_part_name=f'Part {n}', shop=self.shop)
        first = self.claim(self.sold_card.spares.get())
        first.mark_completed()
        self.claim(first.spares.get()).mark_completed()
        old = OldBill.objects.create(bill_number='JB-25-060', bill_date=date(2025, 6, 1),
                                     registration_number=self.plate)
        for name in ('Alternator', 'Drive Belt', 'Horn'):
            OldBillPartLine.objects.create(old_bill=old, name=name)
        with CaptureQueriesContext(connection) as long:
            html = client.get(self.url).content.decode()
        self.assertEqual(html.count('id="bill-'), 11)            # 7 job cards, 2 claims, 2 Excel bills
        self.assertEqual(len(long), len(short),
                         [q['sql'][:90] for q in long.captured_queries])

    def test_a_claims_chain_links_itself_across_the_page(self):
        """Other bills come between a claim's links, so each number with a
        block here jumps to it: the clock's first bill, the claim a repeat is
        "for", and "Replaced · WR-…". An open claim has no block, so it opens
        its card."""
        first = self.claim(self.sold_card.spares.get())
        first.mark_completed()
        second = self.claim(first.spares.get())
        second.mark_completed()
        third = self.claim(second.spares.get())                 # open: no block
        html = self.client_for(self.office).get(self.url).content.decode()
        for number in (self.sold_card.bill_number, first.bill_number, second.bill_number):
            self.assertIn(f'id="bill-{number}"', html)
        self.assertNotIn(f'id="bill-{third.bill_number}"', html)
        block = html.split(f'data-bill="{second.bill_number}"', 1)[1].split('</section>', 1)[0]
        self.assertIn('2nd claim ·</span> <span class="wn-bit">for '
                      f'<a class="wn-jump" href="#bill-{first.bill_number}">{first.bill_number}</a>', block)
        self.assertIn(f'href="#bill-{second.bill_number}">Replaced · {second.bill_number}</a>', html)
        self.assertIn(f'href="{reverse("warranty_card", args=[third.pk])}">3rd claim open', html)
        # A 1st claim is for the bill the part came from, and says no "1st".
        block = html.split(f'data-bill="{first.bill_number}"', 1)[1].split('</section>', 1)[0]
        self.assertIn(f'for <a class="wn-jump" href="#bill-{self.sold_card.bill_number}">', block)
        self.assertNotIn('1st claim', block)
        # A replaced part is history: no clock under it.
        self.assertNotIn('First fitted', block)

    def test_every_part_has_its_own_claim_button_that_asks_first(self):
        html = self.client_for(self.office).get(self.url).content.decode()
        self.assertIn('data-confirm-title="Claim this part?"', html)
        self.assertIn('aria-label="Claim Starter Motor">Claim</button>', html)
        for gone in ('type="checkbox"', 'id="wnClaim"', 'One claim is for one bill'):
            self.assertNotIn(gone, html)


# =============================================================================
# NEW CLAIM — PICK THE CAR, TICK THE PART (2026-10-05)
# =============================================================================
class TheNewClaimTests(WarrantyBase):
    """
    Warranty page → New claim → the car → tick the part that failed → Claim.
    The ticked parts land on the new card: a shop part Waiting and ordered on
    the claim day, a stock part as a new draw off the shelf, an Excel bill's
    line with no shop chosen. One claim answers to one bill.
    """

    def setUp(self):
        super().setUp()
        self.sold_card = self.sold()
        self.shop_part = self.sold_card.spares.get()
        JobCardSpareItem.objects.filter(pk=self.shop_part.pk).update(quantity=D('2'))
        self.item = Item.objects.create(
            category=Category.objects.create(name='Battery'), name='Amaron 65Ah',
            average_stock=D('4'), current_stock=D('5'), avg_cost=D('5000'))
        self.stock_part = JobCardSpareItem.objects.create(
            job_card=self.sold_card, source=JobCardSpareItem.SOURCE_INVENTORY,
            item=self.item, quantity=D('1'), total_price=D('7000'))
        self.url = reverse('warranty_start', args=[self.plate])

    def claim(self, **data):
        return self.client_for(self.office).post(self.url, data)

    def test_the_warranty_page_offers_new_claim_and_floor_cannot_open_it(self):
        new = reverse('warranty_new')
        page = self.client_for(self.office).get(reverse('warranty_list')).content.decode()
        self.assertIn(f'href="{new}"', page)
        self.assertEqual(self.client_for(self.floor).get(new).status_code, 403)

    def test_the_car_list_holds_cars_with_a_finished_bill(self):
        self.sold(plate='KL 22 BB 2222', completed=False)          # only on the floor
        res = self.client_for(self.office).get(reverse('warranty_new'))
        plates = [car['plate'] for car in res.context['cars']]
        self.assertEqual(plates, [self.plate])
        self.assertEqual(res.context['cars'][0]['car'], 'Audi A4')
        self.assertContains(res, f'{reverse("warranty_start", args=[self.plate])}?back=')

    def test_the_search_finds_the_car_and_counts_all_its_bills(self):
        other = self.sold(when=self.today - timedelta(days=20))
        JobCard.objects.filter(pk=other.pk).update(customer_name='Someone else')
        res = self.client_for(self.office).get(reverse('warranty_new'), {'q': 'someone'})
        self.assertEqual([(c['plate'], c['bills']) for c in res.context['cars']], [(self.plate, 2)])
        res = self.client_for(self.office).get(reverse('warranty_new'), {'q': self.sold_card.bill_number})
        self.assertEqual(len(res.context['cars']), 1)
        res = self.client_for(self.office).get(reverse('warranty_new'), {'q': 'nothing like it'})
        self.assertEqual(res.context['cars'], [])

    def test_the_parts_page_folds_the_stock_parts(self):
        html = self.client_for(self.office).get(self.url).content.decode()
        self.assertIn(f'name="part" value="c{self.shop_part.pk}"', html)
        fold = html.split('<details class="wn-stock">', 1)[1].split('</details>', 1)[0]
        self.assertIn('Stock items · 1', fold)
        self.assertIn(f'value="c{self.stock_part.pk}"', fold)
        self.assertIn('Amaron 65Ah', fold)

    def test_a_claimed_shop_part_lands_waiting_and_ordered_on_the_claim_day(self):
        resp = self.claim(part=f'c{self.shop_part.pk}')
        wr = JobCard.objects.get(kind=JobCard.KIND_WARRANTY)
        self.assertRedirects(resp, reverse('warranty_card', args=[wr.pk]),
                             fetch_redirect_response=False)
        part = wr.spares.get()
        self.assertEqual((part.source, part.spare_part_name, part.shop_id, part.quantity),
                         (JobCardSpareItem.SOURCE_SHOP, 'Starter Motor', self.shop.pk, D('2')))
        self.assertIsNone(part.unit_price)                      # Waiting
        self.assertEqual((part.ordered_date, part.status), (wr.admitted_date, 'ORDERED'))
        self.assertEqual(part.replaces_id, self.shop_part.pk)
        self.assertIn(part, warranty.waiting_on_shop())

    def test_a_claimed_stock_part_comes_off_the_shelf_at_no_charge(self):
        self.item.refresh_from_db()
        before = self.item.current_stock         # the earlier bill already drew one
        self.claim(part=f'c{self.stock_part.pk}')
        wr = JobCard.objects.get(kind=JobCard.KIND_WARRANTY)
        draw = wr.spares.get()
        self.assertEqual((draw.source, draw.item_id, draw.quantity, draw.total_price),
                         (JobCardSpareItem.SOURCE_INVENTORY, self.item.pk, D('1'), D('0')))
        self.assertEqual(draw.replaces_id, self.stock_part.pk)
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_stock, before - 1)

    def test_a_claimed_stock_part_is_drawn_as_the_job_cards_inventory_row(self):
        """The job card's Inventory Items row: the product fixed in a disabled
        box, the quantity, and its cost for Office — no customer price."""
        self.claim(part=f'c{self.stock_part.pk}')
        wr = JobCard.objects.get(kind=JobCard.KIND_WARRANTY)
        url = reverse('warranty_card', args=[wr.pk])
        html = self.client_for(self.office).get(url).content.decode()
        row = html.split('<tbody id="inventory-list">', 1)[1].split('</tbody>', 1)[0]
        self.assertIn('class="inventory-row border-bottom', row)
        self.assertIn('value="Amaron 65Ah" disabled', row)
        self.assertIn('name="inventory-0-quantity"', row)
        self.assertIn('>Cost / Unit (₹)</th>', html)
        for gone in ('Unit Price (₹)', 'Total Price (₹)', 'inventory-0-item"', '-total_price"'):
            self.assertNotIn(gone, html, gone)
        floor = self.client_for(self.floor).get(url).content.decode()
        self.assertIn('value="Amaron 65Ah" disabled', floor)
        self.assertNotIn('Cost / Unit', floor.split('<tbody id="inventory-list">', 1)[0].rsplit('<table', 1)[1])

    def test_an_excel_bills_line_lands_with_no_shop(self):
        old = OldBill.objects.create(
            bill_number='JB-25-010', bill_date=date(2025, 5, 20),
            registration_number=self.plate, brand_name='Audi', model_name='A4')
        line = OldBillPartLine.objects.create(old_bill=old, name='Alternator', quantity=D('1'))
        self.claim(part=f'o{line.pk}')
        wr = JobCard.objects.get(kind=JobCard.KIND_WARRANTY, warranty_for='JB-25-010')
        part = wr.spares.get()
        self.assertEqual((part.spare_part_name, part.shop_id, part.status),
                         ('Alternator', None, 'ORDERED'))
        self.assertEqual(part.replaces_line_id, line.pk)

    def test_one_claim_is_one_part(self):
        resp = self.client_for(self.office).post(
            self.url, {'part': [f'c{self.shop_part.pk}', f'c{self.stock_part.pk}']},
            follow=True)
        self.assertEqual(resp.redirect_chain[-1][0], self.url)
        self.assertContains(resp, 'One claim is one part — claim each part on its own.')
        self.assertFalse(JobCard.objects.filter(kind=JobCard.KIND_WARRANTY).exists())

    def test_a_part_of_another_cars_bill_opens_nothing(self):
        other = self.sold(plate='KL 99 XX 9999')
        self.claim(part=f'c{other.spares.get().pk}')
        self.assertFalse(JobCard.objects.filter(kind=JobCard.KIND_WARRANTY).exists())

    def test_a_part_claimed_twice_is_refused_on_this_screen(self):
        first = self.claim(part=f'c{self.shop_part.pk}')
        resp = self.claim(part=f'c{self.shop_part.pk}')
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)
        self.assertEqual(JobCard.objects.filter(kind=JobCard.KIND_WARRANTY).count(), 1)
        self.assertEqual(first.status_code, 302)

    def test_the_way_back_follows_where_the_screen_was_opened_from(self):
        html = self.client_for(self.office).get(self.url).content.decode()
        self.assertIn(f'href="{reverse("car_profile_detail", args=[self.plate])}" class="pg-back"', html)
        came = reverse('warranty_new') + '?q=audi'
        html = self.client_for(self.office).get(self.url, {'back': came}).content.decode()
        self.assertIn('class="pg-back">', html)
        self.assertIn('<span>Back</span>', html)


# =============================================================================
# THE EDIT PAGE CANNOT MOVE THE CAR OR CHARGE ANYTHING
# =============================================================================
class SavingAWarrantyCardTests(WarrantyBase):
    """
    The warranty card's own page saves only what a claim needs. The shop's
    answer is stored in the Shop Price box (blank waiting, ₹0 free, an amount
    charged); a claimed part's ordered date is the claim day and its status
    follows its dates; and nothing a job card carries beyond that — the car,
    the customer, any price to the customer, the labour — can be posted.
    """

    def setUp(self):
        super().setUp()
        self.sold_card = self.sold()
        self.original = self.sold_card.spares.get()
        self.wr = self.claim(self.original)
        self.part = self.wr.spares.get()
        self.url = reverse('warranty_card', args=[self.wr.pk])

    def post(self, user=None, url=None, **over):
        data = {
            'admitted_date': str(self.today), 'mileage': '61000',
            'lead_mechanic': self.mech.id, 'notes': '',
            'concerns-TOTAL_FORMS': '0', 'concerns-INITIAL_FORMS': '0',
            'inventory-TOTAL_FORMS': '0', 'inventory-INITIAL_FORMS': '0',
            'labours-TOTAL_FORMS': '0', 'labours-INITIAL_FORMS': '0',
            'spares-TOTAL_FORMS': '1', 'spares-INITIAL_FORMS': '1',
            'spares-0-id': str(self.part.pk),
            'spares-0-spare_part_name': 'Starter Motor',
            'spares-0-quantity': '',
            'spares-0-status': 'ORDERED',
            'spares-0-shop_name': str(self.shop.pk),
            'spares-0-ordered_date': str(self.wr.admitted_date),
            'spares-0-received_date': '',
            'spares-0-unit_price': '',
            'spares-0-transport_cost': '',
        }
        data.update(over)
        return self.client_for(user or self.office).post(url or self.url, data)

    def test_the_shops_answer_is_the_shop_price(self):
        """Blank while the shop has not answered, 0 when free, an amount paid."""
        self.post(**{'spares-0-unit_price': '0'})
        self.part.refresh_from_db()
        self.assertEqual(self.part.unit_price, D('0'))

        self.post(**{'spares-0-unit_price': '2500'})
        self.part.refresh_from_db()
        self.assertEqual(self.part.unit_price, D('2500'))
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.total_purchased_amount, D('6000') + D('2500'))

        self.post(**{'spares-0-unit_price': ''})
        self.part.refresh_from_db()
        self.assertIsNone(self.part.unit_price)

    def test_a_free_answer_survives_the_next_save(self):
        """The page shows a stored ₹0 as 0 — never blank, which would read as
        "waiting" and be saved back as that."""
        JobCardSpareItem.objects.filter(pk=self.part.pk).update(unit_price=D('0'))
        html = self.client_for(self.office).get(self.url).content.decode()
        self.assertIn('name="spares-0-unit_price" value="0"', html)
        self.post(**{'spares-0-unit_price': '0', 'mileage': '62000'})
        self.part.refresh_from_db()
        self.assertEqual(self.part.unit_price, D('0'))

    def test_the_ordered_date_is_the_claim_day_and_the_status_follows(self):
        """Claiming is asking the shop, so the part is ordered on the claim day.
        The status follows the dates by the job card's one rule — on the server
        too, whatever the Status box posted."""
        self.assertEqual((self.part.ordered_date, self.part.status),
                         (self.wr.admitted_date, 'ORDERED'))
        self.post(**{'spares-0-received_date': str(self.today), 'spares-0-status': 'ORDERED'})
        self.part.refresh_from_db()
        self.assertEqual((self.part.ordered_date, self.part.received_date, self.part.status),
                         (self.wr.admitted_date, self.today, 'RECEIVED'))

    def test_a_part_cannot_arrive_before_it_was_claimed(self):
        resp = self.post(**{'spares-0-received_date': str(self.today - timedelta(days=3))})
        self.assertEqual(resp.status_code, 200)
        self.part.refresh_from_db()
        self.assertIsNone(self.part.received_date)

    def test_the_car_the_customer_and_every_charge_stay_put(self):
        resp = self.post(**{
            'registration_number': 'KL 99 ZZ 0001', 'brand_name': 'Tata', 'model_name': 'Nano',
            'customer_name': 'Someone else', 'customer_contact': '9000000000',
            'labour_amount': '5000', 'spares-0-total_price': '8400',
            'spares-0-customer_rate': '100', 'chassis_code': 'X1', 'vin': 'Y',
        })
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)
        self.wr.refresh_from_db()
        self.part.refresh_from_db()
        self.assertEqual((self.wr.registration_number, self.wr.brand_name, self.wr.model_name),
                         (self.plate, 'Audi', 'A4'))
        self.assertEqual(self.wr.customer_name, 'Anwar')
        self.assertEqual((self.wr.labour_amount, self.wr.total_bill_amount), (D('0'), D('0')))
        self.assertEqual(self.part.total_price, D('0'))
        self.assertIsNone(self.wr.chassis_code)
        self.assertEqual(self.wr.mileage, '61000')       # this visit's own fact saves

    def test_floor_cannot_answer_for_the_shop(self):
        JobCardSpareItem.objects.filter(pk=self.part.pk).update(
            unit_price=D('2500'), transport_cost=D('300'))
        self.post(self.floor, **{'spares-0-unit_price': '0', 'spares-0-transport_cost': ''})
        self.part.refresh_from_db()
        self.assertEqual((self.part.unit_price, self.part.transport_cost), (D('2500'), D('300')))

    def test_nothing_can_be_added_to_a_claim(self):
        """Anything not from the earlier bill goes on a job card and is
        billed — so a post adding a part, or a part from stock, adds nothing."""
        item = Item.objects.create(
            category=Category.objects.create(name='Battery'), name='Amaron 65Ah',
            average_stock=D('4'), current_stock=D('5'), avg_cost=D('5000'))
        resp = self.post(**{
            'spares-TOTAL_FORMS': '2', 'spares-1-spare_part_name': 'Starter Relay',
            'spares-1-shop_name': str(self.shop.pk), 'spares-1-answer': 'waiting',
            'inventory-TOTAL_FORMS': '1', 'inventory-0-item': str(item.pk),
            'inventory-0-quantity': '1',
        })
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)
        self.assertEqual(list(self.wr.spares.values_list('pk', flat=True)), [self.part.pk])
        item.refresh_from_db()
        self.assertEqual(item.current_stock, D('5'))

    def test_the_name_is_the_bills_and_the_shop_starts_as_the_bills(self):
        html = self.client_for(self.office).get(self.url).content.decode()
        # The job card's Part Name box, shown with the bill's name — DISABLED,
        # so it reads as fixed and a post of it is ignored (below).
        box = html.split('name="spares-0-spare_part_name"', 1)[1].split('>', 1)[0]
        self.assertIn('disabled', box)
        self.assertIn('value="Starter Motor"', box)
        self.assertIn(f'<option value="{self.shop.pk}" selected>', html)
        self.post(**{'spares-0-spare_part_name': 'Something else'})
        self.part.refresh_from_db()
        self.assertEqual((self.part.spare_part_name, self.part.shop_id),
                         ('Starter Motor', self.shop.pk))

    def test_a_replacement_bought_elsewhere_says_where_the_part_first_came_from(self):
        """Rare: the replacement came from another shop. The claim goes to that
        shop's ledger, and the row says where the part was first fitted from."""
        other = SpareShop.objects.create(name='Biljo')
        self.post(**{'spares-0-shop_name': str(other.pk), 'spares-0-unit_price': '1800'})
        self.part.refresh_from_db()
        self.assertEqual((self.part.shop_id, self.part.unit_price), (other.pk, D('1800')))
        html = self.client_for(self.office).get(self.url).content.decode()
        self.assertIn('First fitted from Spare club', html)

    def test_a_replacement_from_unassigned_spares_leaves_the_hub(self):
        """Rarer still: the replacement came off the Unassigned Spares shelf.
        The pick fills the row; saving removes the Hub row, so the part is on
        its shop's ledger once."""
        other = SpareShop.objects.create(name='Biljo')
        hub = JobCardSpareItem.objects.create(
            source=JobCardSpareItem.SOURCE_SHOP, spare_part_name='Starter motor',
            shop=other, unit_price=D('1800'), ordered_date=self.today, received_date=self.today)
        html = self.client_for(self.office).get(self.url).content.decode()
        self.assertIn(f'data-hub-use="{hub.pk}"', html)
        self.assertIn('Took the replacement from Unassigned Spares?', html)
        self.post(**{'spares-0-shop_name': str(other.pk), 'spares-0-unit_price': '1800',
                     'spares-0-received_date': str(self.today),
                     'imported_unassigned_ids': str(hub.pk)})
        self.assertFalse(JobCardSpareItem.objects.filter(pk=hub.pk).exists())
        self.part.refresh_from_db()
        self.assertEqual((self.part.shop_id, self.part.unit_price, self.part.status),
                         (other.pk, D('1800'), 'RECEIVED'))
        self.assertEqual(self.part.spare_part_name, 'Starter Motor')   # the claim's own name
        floor = self.client_for(self.floor).get(self.url).content.decode()
        self.assertNotIn('id="wcHubModal"', floor)          # no Hub list, no prices, for Floor
        self.assertNotIn(f'data-hub-use="{hub.pk}"', floor)

    def test_the_row_is_the_job_cards_without_a_customer_price(self):
        html = self.client_for(self.office).get(self.url).content.decode()
        for heading in ('Part Name', 'Qty', 'Status', 'Shop', 'Dates', 'Shop Price (₹)', 'Transport (₹)'):
            self.assertIn(f'>{heading}</th>', html, heading)
        # The column, not the words: the job card's stylesheet, inherited, names
        # Customer Price in its own comments.
        self.assertNotIn('Customer Price (₹)</th>', html)
        self.assertNotIn('-total_price"', html)
        self.assertIn('<tbody id="spare-list">', html)
        self.assertIn('class="jc-date-chip"', html)
        self.assertIn('name="spares-0-status"', html)
        self.assertIn('js/spare_autofill.', html)
        self.assertIn('window.refreshDateChips = refreshChips;', html)

    def test_the_quantity_may_go_down_never_above_the_bills(self):
        JobCardSpareItem.objects.filter(pk=self.original.pk).update(quantity=D('4'))
        self.post(**{'spares-0-quantity': '1'})
        self.part.refresh_from_db()
        self.assertEqual(self.part.quantity, D('1'))
        resp = self.post(**{'spares-0-quantity': '5'})
        self.assertContains(resp, 'The bill had 4 — a claim can&#x27;t be for more.')
        self.part.refresh_from_db()
        self.assertEqual(self.part.quantity, D('1'))

    def test_complaint_and_work_save_like_a_job_cards(self):
        self.post(**{
            'concerns-TOTAL_FORMS': '1', 'concerns-0-concern_text': 'Not starting',
            'concerns-0-status': 'WORKING',
            'labours-TOTAL_FORMS': '1', 'labours-0-job_description': 'Starter Motor replaced',
        })
        self.assertTrue(JobCardConcern.objects.filter(
            job_card=self.wr, concern_text='Not starting', status='WORKING').exists())
        self.assertTrue(JobCardLabourItem.objects.filter(
            job_card=self.wr, job_description='Starter Motor replaced').exists())

    def test_a_make_and_model_that_arrived_blank_can_be_filled_once(self):
        """A car known only from an Excel bill may have no make or model, and
        both are required — so the boxes appear for that car, once."""
        JobCard.objects.filter(pk=self.wr.pk).update(brand_name='', model_name='')
        html = self.client_for(self.office).get(self.url).content.decode()
        self.assertIn('name="brand_name"', html)
        self.post(brand_name='Honda', model_name='City')
        self.wr.refresh_from_db()
        self.assertEqual((self.wr.brand_name, self.wr.model_name), ('Honda', 'City'))
        html = self.client_for(self.office).get(self.url).content.decode()
        self.assertNotIn('name="brand_name"', html)
        self.post(brand_name='Tata', model_name='Nano')
        self.wr.refresh_from_db()
        self.assertEqual((self.wr.brand_name, self.wr.model_name), ('Honda', 'City'))

    def test_from_the_live_report_it_goes_back_there(self):
        resp = self.post(url=f'{self.url}?next=mini')
        self.assertRedirects(resp, reverse('live_report'), fetch_redirect_response=False)


# =============================================================================
# THE COST REACHES THE PROFIT PAGE — AND NO REVENUE DOES
# =============================================================================
class TheWarrantyCostReachesProfitTests(WarrantyBase):

    def test_its_parts_cost_counts_and_its_bill_adds_no_turnover(self):
        sold = self.sold(when=self.today - timedelta(days=400))
        start = self.today.replace(day=1)
        end = engine._month_end(start)
        before = engine.build_profit_report(start, end)

        wr = self.open_for(sold)
        self.answer(wr, D('2500'), transport_cost=D('400'))

        after =engine.build_profit_report(start, end)
        self.assertEqual(after['turnover'], before['turnover'])
        self.assertEqual(engine.spare_shop_expense(start, end), D('2500'))
        self.assertEqual(engine.parts_transport(start, end), D('400'))
        self.assertEqual(after['profit'], before['profit'] - D('2900'))


# =============================================================================
# THE WARRANTY CARD — ITS OWN PAGE (2026-10-05)
# =============================================================================
class TheWarrantyCardPageTests(WarrantyBase):
    """
    A warranty card has its own page carrying only what a claim needs, and
    every door that opens a card brings a warranty card to it. A job card is
    never sent there, and its own form carries nothing of the warranty.
    """

    def setUp(self):
        super().setUp()
        self.sold_card = self.sold()
        self.wr = self.open_for(self.sold_card)
        self.url = reverse('warranty_card', args=[self.wr.pk])

    def page(self, user):
        return self.client_for(user).get(self.url).content.decode()

    def test_every_door_to_a_warranty_card_lands_here(self):
        edit = reverse('jobcard_edit', args=[self.wr.pk])
        c = self.client_for(self.office)
        self.assertRedirects(c.get(edit), self.url, fetch_redirect_response=False)
        self.assertRedirects(c.get(edit, {'next': 'mini'}), f'{self.url}?next=mini',
                             fetch_redirect_response=False)
        # A post to the job card's form saves nothing on a warranty card.
        resp = c.post(edit, {'mileage': '99999'})
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)
        self.wr.refresh_from_db()
        self.assertNotEqual(self.wr.mileage, '99999')

    def test_a_job_card_is_never_sent_here_and_keeps_its_own_form(self):
        c = self.client_for(self.office)
        self.assertEqual(
            c.get(reverse('warranty_card', args=[self.sold_card.pk])).status_code, 404)
        html = c.get(reverse('jobcard_edit', args=[self.sold_card.pk])).content.decode()
        self.assertIn('<span class="jc-submit-label">Update Job Card</span>', html)
        for gone in ('jc-wr-band', 'jcWrPick', 'Warranty:'):
            self.assertNotIn(gone, html)

    def test_the_header_names_the_card_the_car_and_the_bill(self):
        html = self.page(self.office)
        self.assertIn(self.wr.bill_number, html)
        self.assertIn('Audi A4', html)
        detail = reverse('jobcard_detail', args=[self.sold_card.pk])
        self.assertIn(f'<a href="{detail}?back=', html)
        self.assertIn(warranty.age_phrase(self.sold_card.admitted_date), html)
        self.assertIn(f'href="{reverse("warranty_slip", args=[self.wr.pk])}?back=', html)

    def test_only_what_a_claim_needs(self):
        html = self.page(self.office)
        for name in ('customer_name', 'customer_contact', 'labour_amount',
                     'registration_number', 'chassis_code', 'vin', 'car_color',
                     'brand_name', 'model_name'):
            self.assertNotIn(f'name="{name}"', html, name)
        self.assertNotIn('-total_price"', html)
        self.assertNotIn('-customer_rate"', html)
        for heading in ('Vehicle Details', 'Customer Concerns', 'Job Performed', 'Claimed Part'):
            self.assertIn(heading, html)
        for gone in ('Parts claimed', 'Stock used'):
            self.assertNotIn(gone, html)

    def test_it_is_the_job_cards_page_in_the_job_cards_order(self):
        """
        The owners' call (2026-10-09): staff already know the job card, so the
        warranty card is the job card's page — its stylesheet inherited, never
        copied, and its sections in the job card's order, with the claimed part
        where Spare Parts sits. Only the section headings differ (teal).
        """
        res = self.client_for(self.office).get(self.url)
        self.assertTemplateUsed(res, 'workshop/jobcard/jobcard_form.html')
        html = res.content.decode()
        names = ['>Vehicle Details</h6>', '>Workshop Note', '>Customer Concerns</h6>',
                 '>Job Performed</h6>', '>Claimed Part</h6>']
        at = [html.find(name) for name in names]
        self.assertNotIn(-1, at, names)
        self.assertEqual(at, sorted(at), names)
        self.assertEqual(html.count('class="card-header jc-sec-head'), 5)
        self.assertIn('.wc-page .jc-sec-head { background: var(--wr-tint);', html)
        self.assertIn('<span class="jc-submit-label">Update Warranty Card</span>', html)

    def test_the_shops_answer_reads_back(self):
        box = self.page(self.office).split('name="spares-0-unit_price"', 1)[1].split('>', 1)[0]
        self.assertIn('placeholder="Waiting"', box)
        self.assertNotIn('value=', box)
        self.answer(self.wr, D('0'))
        self.assertIn('name="spares-0-unit_price" value="0"', self.page(self.office))
        self.answer(self.wr, D('2500'))
        self.assertIn('name="spares-0-unit_price" value="2500"', self.page(self.office))

    def test_floor_works_the_card_but_sees_no_money_and_no_slip(self):
        self.answer(self.wr, D('2500'))
        html = self.page(self.floor)
        self.assertIn(self.sold_card.bill_number, html)
        self.assertNotIn(reverse('jobcard_detail', args=[self.sold_card.pk]), html)
        self.assertNotIn(reverse('warranty_slip', args=[self.wr.pk]), html)
        self.assertNotIn('-answer"', html)
        self.assertNotIn('data-wc-remove aria-label="Remove this part"', html)
        # The figures still post from a hidden cell, so a save cannot blank them.
        hidden = html.split('<td class="d-none">', 1)[1].split('</td>', 1)[0]
        self.assertIn('name="spares-0-unit_price"', hidden)
        self.assertIn('name="spares-0-shop_name"', hidden)
        self.assertNotIn('>Shop Price (₹)</th>', html)

    def test_a_claimed_part_cannot_be_added_to_or_removed(self):
        html = self.page(self.office)
        for gone in ('id="add-spare-btn"', 'id="add-inventory-btn"', 'id="empty-spare-form"',
                     'id="empty-inventory-form"', 'data-wc-remove', 'name="spares-0-DELETE"'):
            self.assertNotIn(gone, html, gone)
        self.assertIn('<p class="wc-claim">Starter Motor</p>', html)       # a first claim says no "1st"

    def test_the_header_says_a_repeat_claim(self):
        first = self.wr
        first.mark_completed()
        second = self.claim(first.spares.get())
        html = self.client_for(self.office).get(reverse('warranty_card', args=[second.pk])).content.decode()
        self.assertIn('Starter Motor<span class="wc-round">2nd claim</span>', html)
        # It is for the first claim; its clock — the line under — is the first
        # bill's, beside that bill's own number.
        lines = [p.split('</p>', 1)[0] for p in html.split('<p class="wc-for">')[1:]]
        self.assertTrue(lines[0].endswith(f'>{first.bill_number}</a>'), lines[0])
        # "For WR-…" opens the 1st claim's own card.
        self.assertIn(f'href="{reverse("warranty_card", args=[first.pk])}?back=', lines[0])
        self.assertTrue(lines[1].startswith('First fitted <a '), lines[1])
        self.assertTrue(lines[1].endswith(
            f'>{self.sold_card.bill_number}</a> · {warranty.age_phrase(self.sold_card.admitted_date)}'),
            lines[1])


# =============================================================================
# STEP 3 — WHEREVER THE CAR IS SHOWN
# =============================================================================
class TheWarrantyIsShownWhereverTheCarIsTests(WarrantyBase):
    """
    A warranty card is a job card, so it already appears on every screen a job
    card does. These pin down how it reads there: a WARRANTY label, "No charge"
    where a bill says its amount, and the link between it and the earlier bill
    read from both ends — the earlier bill storing nothing.
    """

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username='wr_owner', password='pw')
        self.owner.groups.add(Group.objects.get(name='Owner'))
        self.sold_card = self.sold()
        self.wr = self.open_for(self.sold_card)

    def get(self, user, name, *args, ajax=False, **params):
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'} if ajax else {}
        return self.client_for(user).get(reverse(name, args=args), params, **headers)

    def profile(self, user):
        return self.get(user, 'car_profile_detail', self.plate).content.decode()

    # ---- the board -----------------------------------------------------------
    def test_the_board_labels_the_warranty_card_and_counts_both(self):
        """Warranty plus paid work: two cards, two in the count, one label."""
        JobCard.objects.create(admitted_date=self.today, registration_number=self.plate,
                               brand_name='Audi', model_name='A4')
        res = self.get(self.floor, 'home')
        self.assertEqual(res.context['floor_count'], 2)
        html = res.content.decode()
        self.assertEqual(html.count('class="wr-badge pit-wr">Warranty</span>'), 1)
        self.assertIn('<div class="pit-wr-part">Starter Motor</div>', html)   # what it claims

    def test_the_board_has_a_warranty_chip_while_a_warranty_card_is_live(self):
        JobCard.objects.create(admitted_date=self.today, registration_number='KL 01 Z 9',
                               brand_name='Audi', model_name='A4')
        res = self.get(self.floor, 'home')
        self.assertEqual(res.context['warranty_chip']['count'], 1)
        self.assertIn('class="pit-crew-chip is-warranty"', res.content.decode())
        narrowed = self.get(self.floor, 'home', mechanic='warranty')
        self.assertEqual(list(narrowed.context['active_jobcards']), [])
        self.assertEqual([c.pk for c in narrowed.context['warranty_cards']], [self.wr.pk])
        self.assertTrue(narrowed.context['warranty_chip']['active'])
        self.wr.mark_completed()
        res = self.get(self.floor, 'home', mechanic='warranty')
        self.assertIsNone(res.context['warranty_chip'])
        self.assertEqual(res.context['mechanic_key'], '')   # a stale link falls back to All

    def test_the_live_report_labels_a_warranty_part(self):
        html = self.get(self.office, 'live_report').content.decode()   # claimed: ordered
        on_the_way = html.split('On the way', 1)[1].split('</section>', 1)[0]
        self.assertIn('Starter Motor', on_the_way)
        self.assertIn('class="wr-badge lr-wr">Warranty</span>', on_the_way)

    def test_the_warranty_cards_are_a_group_of_their_own_under_the_job_cards(self):
        job = JobCard.objects.create(admitted_date=self.today, registration_number=self.plate,
                                     brand_name='Audi', model_name='A4')
        res = self.get(self.floor, 'home')
        self.assertEqual([c.pk for c in res.context['active_jobcards']], [job.pk])
        self.assertEqual([c.pk for c in res.context['warranty_cards']], [self.wr.pk])
        html = res.content.decode()
        heading = html.index('id="pitWarranty"')
        self.assertLess(html.index(f'data-card-id="{job.pk}"'), heading)
        self.assertGreater(html.index(f'data-card-id="{self.wr.pk}"'), heading)
        self.assertIn('Warranty <span class="n">1</span></h2>', html)

    def test_no_warranty_card_no_group_and_a_warranty_card_alone_is_not_an_empty_workshop(self):
        self.wr.mark_completed()
        html = self.get(self.floor, 'home').content.decode()
        self.assertNotIn('id="pitWarranty"', html)
        JobCard.objects.filter(pk=self.wr.pk).update(completed=False, completed_date=None)
        html = self.get(self.floor, 'home').content.decode()
        self.assertIn('id="pitWarranty"', html)
        self.assertNotIn('Workshop is empty', html)

    def test_the_mechanic_chip_narrows_the_warranty_group_too(self):
        other = Mechanic.objects.create(name='Zayan')
        JobCard.objects.create(admitted_date=self.today, registration_number='KL 01 Z 1',
                               brand_name='Audi', model_name='A4', lead_mechanic=other)
        res = self.get(self.floor, 'home', mechanic=str(other.pk))
        self.assertEqual(res.context['warranty_cards'], [])
        JobCard.objects.filter(pk=self.wr.pk).update(lead_mechanic=other)
        res = self.get(self.floor, 'home', mechanic=str(other.pk))
        self.assertEqual([c.pk for c in res.context['warranty_cards']], [self.wr.pk])

    def test_the_warranty_group_is_on_the_first_page_only(self):
        for n in range(46):
            JobCard.objects.create(admitted_date=self.today, registration_number=f'KL 01 P {n}',
                                   brand_name='Audi', model_name='A4')
        self.assertEqual(len(self.get(self.floor, 'home').context['warranty_cards']), 1)
        self.assertEqual(self.get(self.floor, 'home', page='2').context['warranty_cards'], [])

    def test_the_live_report_and_both_lists_label_it(self):
        self.assertIn('class="wr-badge">Warranty</span>',
                      self.get(self.office, 'live_report').content.decode())
        self.assertIn('class="wr-badge">Warranty</span>',
                      self.get(self.office, 'jobcard_list').content.decode())
        self.wr.mark_completed()
        html = self.get(self.office, 'completed_list').content.decode()
        card = html.split(f'{self.wr.registration_number}</span>', 1)[1].split('</div>', 1)[0]
        self.assertIn('class="wr-badge">Warranty</span>', card)
        self.assertNotIn('Pending', card)          # it is never settled

    # ---- the Car Profile ------------------------------------------------------
    def test_the_profile_row_says_no_charge_and_names_both_ends(self):
        html = self.profile(self.office)
        self.assertIn('class="cd-amount cd-amount-wr">No charge</div>', html)
        self.assertIn(f'{self.wr.bill_number} · for {self.sold_card.bill_number}', html)
        self.assertIn(f'{self.sold_card.bill_number} · <span class="cd-wr" title="Warranty">', html)
        self.assertIn(f'<span class="visually-hidden">Warranty </span>{self.wr.bill_number}</span>', html)
        state = html.split('class="cd-amount cd-amount-wr">No charge</div>', 1)[1][:80]
        self.assertIn('<span class="wr-badge">Warranty</span>', state)

    def test_the_owner_sees_what_it_cost_not_a_gross_loss(self):
        self.answer(self.wr, D('1000'))
        html = self.profile(self.owner)
        self.assertIn('₹1,000<span class="cd-gp-word"> cost</span>', html)
        self.assertNotIn('Gross loss', html)

    def test_an_open_warranty_card_alone_shows_no_money_tile(self):
        """The car is in the workshop, but there is no bill being built."""
        res = self.get(self.office, 'car_profile_detail', self.plate)
        self.assertTrue(res.context['car_info']['on_floor'])
        self.assertFalse(res.context['car_info']['on_floor_bill'])
        self.assertNotIn('class="cd-stat cd-stat-floor"', res.content.decode())

    def test_the_car_is_on_the_floor_while_ANY_card_is_open(self):
        """The newest card finished no longer means the car has left — an
        older warranty card can still be open on it."""
        newer = JobCard.objects.create(
            admitted_date=self.today, registration_number=self.plate,
            brand_name='Audi', model_name='A4')
        newer.mark_completed()
        res = self.get(self.office, 'car_profile_list')
        car = next(c for c in res.context['car_profiles'] if c['registration'] == self.plate)
        self.assertTrue(car['on_floor'])
        detail = self.get(self.office, 'car_profile_detail', self.plate)
        self.assertTrue(detail.context['car_info']['on_floor'])

    def test_an_old_bill_names_its_warranty_card(self):
        old = OldBill.objects.create(
            bill_number='JB-25-097', bill_date=date(2025, 11, 3),
            registration_number=self.plate, brand_name='Audi', model_name='A4')
        OldBillPartLine.objects.create(old_bill=old, name='Alternator')
        wr = self.open_for('JB-25-097')
        html = self.profile(self.office)
        self.assertIn('JB-25-097 · <span class="cd-wr" title="Warranty">', html)
        self.assertIn(f'<span class="visually-hidden">Warranty </span>{wr.bill_number}</span>', html)

    # ---- the read-only card ---------------------------------------------------
    def test_the_warranty_card_page_says_no_charge_and_links_its_bill(self):
        self.answer(self.wr, D('1000'))
        html =self.get(self.office, 'jobcard_detail', self.wr.pk).content.decode()
        earlier = reverse('jobcard_detail', args=[self.sold_card.pk])
        self.assertIn('class="dv-bill dv-bill-wr">No charge</span>', html)
        self.assertIn(f'<a href="{earlier}?back=', html)
        self.assertNotIn('class="dv-pay', html)       # no payment state at all
        self.assertNotIn('class="dv-money-col"', html)  # no customer price per part
        self.assertIn('₹1,000', html)                 # its cost line stays
        self.assertNotIn('>Settled<', html)           # never settled, so no column

    def test_the_earlier_bill_page_links_its_warranty_cards(self):
        html = self.get(self.office, 'jobcard_detail', self.sold_card.pk).content.decode()
        claim = reverse('jobcard_detail', args=[self.wr.pk])
        self.assertIn(f'<a href="{claim}?back=', html)
        self.assertIn(f'>{self.wr.bill_number}</a>', html)
        self.assertIn('>Settled<', html)              # a job card keeps all three

    # ---- searches -------------------------------------------------------------
    def test_a_warranty_number_finds_its_card_and_its_car(self):
        number = self.wr.bill_number
        jobs = self.get(self.office, 'jobcard_list', ajax=True, q=number)
        self.assertEqual([j.pk for j in jobs.context['jobcards']], [self.wr.pk])
        cars = self.get(self.office, 'car_profile_list', q=number)
        self.assertEqual([c['registration'] for c in cars.context['car_profiles']],
                         [self.plate])
        self.wr.mark_completed()
        done = self.get(self.office, 'completed_list', q=number, filter='all')
        self.assertEqual([j.pk for j in done.context['completed_jobcards']], [self.wr.pk])

    def test_the_earlier_bills_number_lists_the_bill_and_its_claims(self):
        jobs = self.get(self.office, 'jobcard_list', ajax=True,
                        q=self.sold_card.bill_number)
        self.assertEqual({j.pk for j in jobs.context['jobcards']},
                         {self.sold_card.pk, self.wr.pk})



# =============================================================================
# STEP 4 — THE WARRANTY SLIP
# =============================================================================
class TheWarrantySlipTests(WarrantyBase):
    """
    The paper handed over with a warranty card's car. Its own sheet in the
    invoice's style: titled WARRANTY, naming the bill it is for, closing on
    "WARRANTY" alone — and carrying no price of any kind.
    """

    def setUp(self):
        super().setUp()
        self.sold_card = self.sold()
        self.wr = self.open_for(self.sold_card)
        JobCardLabourItem.objects.create(job_card=self.wr,
                                         job_description='Starter motor replaced')
        self.answer(self.wr, D('6000'))
        self.url = reverse('warranty_slip', args=[self.wr.pk])

    def sheet(self, user=None):
        html = self.client_for(user or self.office).get(self.url).content.decode()
        return html, html.split('<div class="sheet">', 1)[1]

    def test_every_invoice_door_leads_to_the_slip(self):
        res = self.client_for(self.office).get(
            reverse('invoice_view', args=[self.wr.pk]), {'back': '/completed/'})
        self.assertRedirects(res, f'{self.url}?back=%2Fcompleted%2F',
                             fetch_redirect_response=False)

    def test_it_names_itself_and_the_bill_it_is_for(self):
        html, sheet = self.sheet()
        self.assertIn('<div class="inv-title">WARRANTY</div>', sheet)
        self.assertIn(f'#: {self.wr.bill_number}', sheet)
        when = self.sold_card.admitted_date
        self.assertIn(f'FOR:&nbsp; {self.sold_card.bill_number} · '
                      f'{when.day}-{when:%b-%Y}', sheet)
        self.assertIn('<td colspan="3" class="grand-label c">WARRANTY</td>', sheet)
        self.assertNotIn('NO CHARGE', sheet)                 # the owners' call, 2026-10-09
        self.assertIn('Starter motor replaced', sheet)
        self.assertIn('<td colspan="3">Starter Motor</td>', sheet)
        self.assertIn('<td class="c">1</td>', sheet)      # a blank qty prints as one
        self.assertIn(f' {self.wr.bill_number}</title>', html)  # the saved PDF's name

    def test_no_price_of_any_kind_is_on_the_sheet(self):
        _html, sheet = self.sheet()
        for word in ('₹', 'AMOUNT', 'UNIT PRICE', 'SUBTOTAL', '>TOTAL<', '6,000', '6000'):
            self.assertNotIn(word, sheet, word)

    def test_a_job_card_has_no_slip(self):
        res = self.client_for(self.office).get(
            reverse('warranty_slip', args=[self.sold_card.pk]))
        self.assertEqual(res.status_code, 404)

    def test_floor_cannot_open_it(self):
        self.assertEqual(self.client_for(self.floor).get(self.url).status_code, 403)

    def test_the_menus_name_the_slip_not_an_invoice(self):
        detail = self.client_for(self.office).get(
            reverse('jobcard_detail', args=[self.wr.pk])).content.decode()
        self.assertIn(f'href="{self.url}?back=', detail)
        self.assertIn('Warranty slip', detail)
        self.assertNotIn(reverse('invoice_view', args=[self.wr.pk]), detail)
        card = self.client_for(self.office).get(
            reverse('warranty_card', args=[self.wr.pk])).content.decode()
        self.assertIn(f'href="{self.url}?back=', card)
        jobs = self.client_for(self.office).get(reverse('jobcard_list')).content.decode()
        self.assertIn(f'href="{self.url}?back=', jobs)
        self.assertNotIn(reverse('invoice_view', args=[self.wr.pk]), jobs)



# =============================================================================
# STEP 5 — THE WARRANTY PAGE
# =============================================================================
class TheWarrantyPageTests(WarrantyBase):
    """
    The drawer's Warranty page: what is still waiting on a shop — never
    filtered — and every warranty card, with a search, This Year / All Time,
    and a heading that counts and costs exactly the cards listed.
    """

    def setUp(self):
        super().setUp()
        self.url = reverse('warranty_list')
        self.wr = self.open_for(self.sold())

    def page(self, **params):
        return self.client_for(self.office).get(self.url, params)

    def last_year(self, plate):
        card = self.open_for(self.sold(plate=plate), plate=plate)
        JobCard.objects.filter(pk=card.pk).update(
            admitted_date=self.today.replace(year=self.today.year - 1, month=6, day=1))
        return card

    def waiting(self, res=None):
        return [s.job_card_id for s in (res or self.page()).context['waiting']]

    def test_waiting_is_a_blank_shop_price_oldest_first(self):
        older = self.last_year('KL 01 B 2')
        self.assertEqual(self.waiting(), [older.pk, self.wr.pk])
        self.answer(self.wr, D('0'))                       # the shop said free
        self.assertEqual(self.waiting(), [older.pk])

    def test_waiting_ignores_the_search_and_the_period(self):
        older = self.last_year('KL 01 B 2')
        self.answer(self.wr, D('0'))
        res = self.page(q='nothing-matches-this')
        self.assertEqual(self.waiting(res), [older.pk])
        self.assertEqual(res.context['count'], 0)

    def test_the_heading_counts_and_costs_the_cards_listed(self):
        self.answer(self.wr, D('1000'), transport_cost=D('200'))
        res = self.page()
        self.assertEqual(res.context['count'], 1)
        self.assertEqual(res.context['cost'], D('1200'))
        self.assertIn('₹1,200 warranty cost · This Year', res.content.decode())

    def test_this_year_by_default_and_all_time_on_request(self):
        older = self.last_year('KL 01 B 2')
        self.assertEqual([c.pk for c in self.page().context['cards']], [self.wr.pk])
        self.assertEqual([c.pk for c in self.page(filter='all').context['cards']],
                         [self.wr.pk, older.pk])                     # newest first
        self.assertEqual(self.page(filter='nonsense').context['filter_type'], 'this_year')

    def test_the_earlier_bills_number_finds_its_warranty_card(self):
        other = self.open_for(self.sold(plate='KL 01 B 2'), plate='KL 01 B 2')
        res = self.page(q=other.warranty_for)
        self.assertEqual([c.pk for c in res.context['cards']], [other.pk])

    def test_each_row_says_what_the_shop_answered(self):
        html = self.page().content.decode()
        self.assertIn('class="wl-chip wl-chip-wait">Waiting</span>', html)
        self.answer(self.wr, D('0'))
        html = self.page().content.decode()
        self.assertIn('class="wl-chip wl-chip-free">Free</span>', html)

    def test_each_card_names_its_part_and_the_search_finds_it(self):
        other = self.sold(plate='KL 01 B 2')
        alternator = JobCardSpareItem.objects.create(
            job_card=other, source=JobCardSpareItem.SOURCE_SHOP,
            spare_part_name='Alternator', shop=self.shop)
        claimed = self.claim(alternator, plate='KL 01 B 2')
        html = self.page().content.decode()
        self.assertIn('<b class="wl-part">Starter Motor</b>', html)
        self.assertIn('<b class="wl-part">Alternator</b>', html)
        res = self.page(q='alternator')
        self.assertEqual([c.pk for c in res.context['cards']], [claimed.pk])

    def test_a_waiting_row_opens_the_form_where_the_answer_is_typed(self):
        self.assertIn(f'href="{reverse("warranty_card", args=[self.wr.pk])}"',
                      self.page().content.decode())

    def test_it_is_office_and_owner_only_and_in_their_drawer(self):
        self.assertEqual(self.client_for(self.floor).get(self.url).status_code, 403)
        office_home = self.client_for(self.office).get(reverse('home')).content.decode()
        self.assertIn(f'href="{self.url}"', office_home)
        floor_home = self.client_for(self.floor).get(reverse('home')).content.decode()
        self.assertNotIn(f'href="{self.url}"', floor_home)



# =============================================================================
# STEP 6 — BILLS ARE JOB CARDS; THE HISTORY MARKS A WARRANTY VISIT
# =============================================================================
class BillScreensReadJobCardsOnlyTests(WarrantyBase):
    """
    Safety rule 6. Every screen that lists or counts BILLS reads
    `models.bill_cards()` — one rule, one place. A warranty card is ₹0 and
    never settled, so counted as a bill it would dilute every average and sit
    "unsettled" for ever. Its cost still reaches profit through its parts.
    """

    def setUp(self):
        super().setUp()
        self.sold_card = self.sold(when=self.today)
        self.wr = self.open_for(self.sold_card)
        self.wr.mark_completed()

    def test_the_rule_and_its_card_twin_agree(self):
        bills = set(JobCard.objects.filter(bill_cards()).values_list('pk', flat=True))
        self.assertEqual(bills, {self.sold_card.pk})
        self.assertTrue(self.sold_card.is_bill)
        self.assertFalse(self.wr.is_bill)

    def test_pending_bills_never_lists_a_warranty_card(self):
        res = self.client_for(self.office).get(reverse('pending_payments_list'),
                                               HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual([j.pk for j in res.context['pending_jobs']], [self.sold_card.pk])

    def test_all_invoices_prints_bills_only(self):
        res = self.client_for(self.office).get(
            reverse('car_all_invoices', args=[self.plate]))
        self.assertEqual([s['jobcard'].pk for s in res.context['sheets']], [self.sold_card.pk])

    def test_analysis_counts_bills_only(self):
        """Deep Analysis and the Profit page build every count and average on
        `live_jobcards()` — a warranty card is not a job there."""
        self.assertEqual(list(engine.live_jobcards().values_list('pk', flat=True)),
                         [self.sold_card.pk])
        turnover = engine.car_bill_turnover(self.today, self.today)
        self.assertEqual(turnover['cards'], 1)


class TheServiceHistoryMarksAWarrantyVisitTests(WarrantyBase):
    """
    A warranty visit is a visit: it counts in VISITS and its parts join PART
    LIFE (a refit is a fitting). It says what it is in its band and closes on
    "WARRANTY · NO CHARGE" where a bill prints its AMOUNT. TOTAL BILLED is
    untouched — it bills ₹0.
    """

    def setUp(self):
        super().setUp()
        self.sold_card = self.sold()
        self.wr = self.open_for(self.sold_card)
        self.answer(self.wr, D('0'))
        self.wr.mark_completed()

    def sheet(self):
        return self.client_for(self.office).get(
            reverse('car_service_history_sheet', args=[self.plate]), {'amount': '1'})

    def test_the_visit_says_warranty_and_no_charge(self):
        html = self.sheet().content.decode()
        self.assertIn(f'{self.wr.bill_number}&nbsp; ·&nbsp; WARRANTY FOR '
                      f'{self.sold_card.bill_number}', html)
        self.assertIn('class="sub-label sh-nocharge">WARRANTY · NO CHARGE</td>', html)

    def test_it_counts_as_a_visit_its_refit_joins_part_life_and_the_total_is_unchanged(self):
        res = self.sheet()
        self.assertEqual(res.context['summary'].visits, 2)
        self.assertEqual(res.context['summary'].total_billed, D('8400'))
        chain = next(c for c in res.context['chains'] if c.key == 'starter motor')
        self.assertEqual(len(chain.instances), 2)


# =============================================================================
# STEP 4 — CANCEL CLAIM, AND HOW FAR THE CAR HAS RUN
# =============================================================================
class CancellingAClaimTests(WarrantyBase):
    """
    A claim opened by mistake can be cancelled from its ⋮ — while the card is
    open and nothing real has happened on it: no shop has charged, no
    transport was paid. A part taken off the shelf goes back on it. No
    DeletionLog row — housekeeping, like deleting an estimate.
    """

    def setUp(self):
        super().setUp()
        self.wr = self.open_for(self.sold())
        self.part = self.claimed(self.wr)
        self.url = reverse('warranty_cancel', args=[self.wr.pk])

    def cancel(self, user=None):
        return self.client_for(user or self.office).post(self.url)

    def test_a_mistaken_claim_goes_and_its_stock_comes_back(self):
        item = Item.objects.create(
            category=Category.objects.create(name='Battery'), name='Amaron 65Ah',
            average_stock=D('4'), current_stock=D('5'), avg_cost=D('5000'))
        JobCardSpareItem.objects.create(job_card=self.wr, source=JobCardSpareItem.SOURCE_INVENTORY,
                                        item=item, quantity=D('1'))
        item.refresh_from_db()
        self.assertEqual(item.current_stock, D('4'))
        logs = DeletionLog.objects.count()
        resp = self.cancel()
        self.assertRedirects(resp, reverse('warranty_list'), fetch_redirect_response=False)
        self.assertFalse(JobCard.objects.filter(pk=self.wr.pk).exists())
        item.refresh_from_db()
        self.assertEqual(item.current_stock, D('5'))
        self.assertEqual(DeletionLog.objects.count(), logs)

    def test_a_free_answer_does_not_stop_it(self):
        JobCardSpareItem.objects.filter(pk=self.part.pk).update(unit_price=D('0'))
        self.cancel()
        self.assertFalse(JobCard.objects.filter(pk=self.wr.pk).exists())

    def test_a_charge_transport_or_completion_stops_it_and_says_why(self):
        cases = (
            ({'unit_price': D('2500')}, 'A shop has charged for a part on it.'),
            ({'transport_cost': D('300')}, 'Transport was paid on a part on it.'),
        )
        for change, reason in cases:
            with self.subTest(reason=reason):
                JobCardSpareItem.objects.filter(pk=self.part.pk).update(
                    **{'unit_price': None, 'transport_cost': None, **change})
                self.cancel()
                self.assertTrue(JobCard.objects.filter(pk=self.wr.pk).exists())
                html = self.client_for(self.office).get(
                    reverse('warranty_card', args=[self.wr.pk])).content.decode()
                self.assertIn(f'<small>{reason}</small>', html)
                self.assertNotIn('id="wcCancel"', html)
        JobCardSpareItem.objects.filter(pk=self.part.pk).update(unit_price=None, transport_cost=None)
        self.wr.mark_completed()
        self.cancel()
        self.assertTrue(JobCard.objects.filter(pk=self.wr.pk).exists())
        self.assertEqual(warranty.cancel_refusal(self.wr), 'It is completed — undo the completion first.')

    def test_it_asks_first_and_floor_has_no_door(self):
        html = self.client_for(self.office).get(reverse('warranty_card', args=[self.wr.pk])).content.decode()
        self.assertIn('data-confirm-title="Cancel this claim?"', html)
        # Not "Cancel" beside "Cancel claim": the way back out says what it does.
        self.assertIn('data-confirm-no="Keep it"', html)
        self.assertIn('form="wcCancel"', html)
        self.assertEqual(self.cancel(self.floor).status_code, 403)
        floor_html = self.client_for(self.floor).get(reverse('warranty_card', args=[self.wr.pk])).content.decode()
        self.assertNotIn('Cancel claim', floor_html)
        self.assertTrue(JobCard.objects.filter(pk=self.wr.pk).exists())

    def test_a_get_cancels_nothing(self):
        self.client_for(self.office).get(self.url)
        self.assertTrue(JobCard.objects.filter(pk=self.wr.pk).exists())


class HowFarTheCarHasRunTests(WarrantyBase):
    """Under Mileage: how far the car has run since the bill it claims
    against, read by the service history's own odometer reader."""

    def setUp(self):
        super().setUp()
        self.sold_card = self.sold()
        JobCard.objects.filter(pk=self.sold_card.pk).update(mileage='45,000')
        self.wr = self.open_for(self.sold_card)
        self.url = reverse('warranty_card', args=[self.wr.pk])

    def test_it_says_how_far_since_the_bill(self):
        JobCard.objects.filter(pk=self.wr.pk).update(mileage='52000')
        html = self.client_for(self.floor).get(self.url).content.decode()
        self.assertIn(f'7,000 km since {self.sold_card.bill_number}', html)

    def test_a_repeat_claim_counts_from_where_the_part_was_first_fitted(self):
        JobCard.objects.filter(pk=self.wr.pk).update(mileage='50,000')
        self.wr.refresh_from_db()
        self.wr.mark_completed()
        second = self.claim(self.wr.spares.get())
        JobCard.objects.filter(pk=second.pk).update(mileage='53,000')
        html = self.client_for(self.floor).get(reverse('warranty_card', args=[second.pk])).content.decode()
        self.assertIn(f'8,000 km since {self.sold_card.bill_number}', html)

    def test_nothing_when_it_cannot_be_worked_out(self):
        for reading in ('', 'cluster dead', '40000'):           # blank, unreadable, lower
            with self.subTest(reading=reading):
                JobCard.objects.filter(pk=self.wr.pk).update(mileage=reading)
                self.assertNotIn('km since', self.client_for(self.office).get(self.url).content.decode())

    def test_an_excel_bills_reading_counts_too(self):
        old = OldBill.objects.create(bill_number='JB-25-011', bill_date=date(2025, 5, 20),
                                     registration_number=self.plate, mileage='30000')
        card = JobCard(mileage='31,500')
        self.assertEqual(warranty.km_since(card, warranty.find(old.bill_number)), 1500)


# =============================================================================
# ONE SEARCH BOX — THE WARRANTY SCREENS SEARCH LIKE THE REST OF THE APP
# =============================================================================
class TheWarrantySearchesAreTheAppsOwnTests(WarrantyBase):
    """
    The Warranty page, New claim's car list and its parts screen each carry the
    app's own search box — Completed's values, copied — and the two lists
    update as you type, answering the live search with the list alone.
    """

    def css(self, name):
        from pathlib import Path
        from django.conf import settings
        return (Path(settings.BASE_DIR) / 'workshop' / 'templates' / 'workshop' / name).read_text(encoding='utf-8')

    def test_all_three_boxes_declare_completeds_shape(self):
        from workshop.tests.test_car_profiles import TheSearchLooksLikeCompletedsTests
        completed = self.css('completed/completed_list.html')
        for name in ('warranty/warranty_list.html', 'warranty/warranty_new.html',
                     'warranty/warranty_start.html'):
            source = self.css(name)
            for declaration in TheSearchLooksLikeCompletedsTests.SHARED:
                with self.subTest(template=name, declaration=declaration):
                    self.assertIn(declaration, completed)
                    self.assertIn(declaration, source)

    def test_the_warranty_page_answers_the_live_search_with_its_list(self):
        wr = self.open_for(self.sold())
        other = self.open_for(self.sold(plate='KL 99 XX 9999'), plate='KL 99 XX 9999')
        res = self.client_for(self.office).get(reverse('warranty_list'), {'q': 'XX 9999'},
                                               HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        html = res.content.decode()
        self.assertNotIn('<html', html)
        self.assertIn('id="wlTotals" hidden data-count="1"', html)
        self.assertIn(other.bill_number, html)
        self.assertNotIn(wr.bill_number, html)
        page = self.client_for(self.office).get(reverse('warranty_list')).content.decode()
        self.assertIn('id="wlSearch"', page)
        self.assertIn('id="wlResults"', page)

    def test_the_car_list_answers_the_live_search_with_its_cards(self):
        self.sold()
        self.sold(plate='KL 99 XX 9999')
        res = self.client_for(self.office).get(reverse('warranty_new'), {'q': 'XX 9999'},
                                               HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        html = res.content.decode()
        self.assertNotIn('<html', html)
        self.assertIn('KL 99 XX 9999', html)
        self.assertNotIn(self.plate, html)


# =============================================================================
# AN EXCEL BILL'S CLAIMED LINE KEEPS ITS CLAIM
# =============================================================================
class AnOldBillsClaimedLineIsKeptTests(WarrantyBase):
    """
    The Old Bills edit writes a bill's lines afresh. A claim points at a line,
    so the edit points it back at the line of the same name — and refuses to
    remove or rename a claimed line, or to delete a claimed bill.
    """

    def setUp(self):
        super().setUp()
        from workshop.tests.test_old_bills import _the_sample_bill
        self.bill = _the_sample_bill()
        self.line = self.bill.part_lines.get(name='Coolant')
        self.wr = self.claim(self.line, plate=self.bill.registration_number)
        self.client = self.client_for(self.office)

    def edit(self, **changes):
        from workshop.tests.test_old_bills import _sample_post
        return self.client.post(reverse('old_bill_edit', args=[self.bill.pk]), _sample_post(**changes))

    def test_an_edit_keeps_the_claim_on_its_line(self):
        resp = self.edit(part_amount=['', '3,000.00', '75.00', '11,880.00', ''])
        self.assertEqual(resp.status_code, 302)
        part = self.wr.spares.get()
        self.assertIsNotNone(part.replaces_line_id)
        self.assertEqual(part.replaces_line.name, 'Coolant')
        self.assertEqual(part.replaces_line.old_bill_id, self.bill.pk)

    def test_a_claimed_line_cannot_be_removed_or_renamed(self):
        resp = self.edit(part_name=['Drive belt', 'Coolant (red)', 'Distilled water', 'Spark plugs', ''])
        self.assertEqual(resp.status_code, 200)
        self.assertIn(f'Coolant is claimed under warranty on {self.wr.bill_number}',
                      resp.content.decode())
        self.assertTrue(self.bill.part_lines.filter(name='Coolant').exists())

    def test_a_claimed_bill_cannot_be_deleted(self):
        self.client.post(reverse('old_bill_delete', args=[self.bill.pk]))
        self.assertTrue(OldBill.objects.filter(pk=self.bill.pk).exists())

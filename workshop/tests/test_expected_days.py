"""
"Expected in __ days" — how long the shop said a part would take.

Typed into the job card's date panel when a part is marked Ordered (the panel
opens itself there), and read by the Live Report's "On the way" box as "2d"
over "13 left" — "due today" in amber, "2 late" in red (2026-10-09, the owners'
request). Optional everywhere: blank means nobody gave a day.

One rule decides when the number means anything — the part is ON ITS WAY,
ordered and not yet received (`JobCardSpareItem.on_its_way`) — and the model,
the form and the panel all read it. Nothing in the Django suite executes
JavaScript, so the panel's behaviour is pinned here by what the server owes it
and by reading the script; it was measured by hand in the browser.
"""

import re
from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Category, Item
from workshop.forms import JobCardSpareFormSet, WarrantyPartFormSet
from workshop.models import JobCard, JobCardSpareItem, Mechanic, SpareShop
from workshop.views.dashboard import part_wait

SHOP = JobCardSpareItem.SOURCE_SHOP


class TheWordingTests(TestCase):
    """`part_wait` — the whole of what the Live Report prints, as a function."""

    def setUp(self):
        self.today = date(2026, 10, 9)

    def ago(self, days):
        return self.today - timedelta(days=days)

    def test_the_owners_example(self):
        """Fifteen days typed, ordered two days ago: 15 - 2 = 13 left."""
        self.assertEqual(part_wait(self.ago(2), 15, self.today), ('2d', '13 left', ''))

    def test_no_expected_days_prints_the_age_alone(self):
        self.assertEqual(part_wait(self.ago(2), None, self.today), ('2d', '', ''))

    def test_ordered_today_reads_new_like_every_other_age_on_the_page(self):
        self.assertEqual(part_wait(self.today, 15, self.today), ('New', '15 left', ''))

    def test_the_last_day_is_due_today(self):
        self.assertEqual(part_wait(self.ago(15), 15, self.today), ('15d', 'due today', 'today'))

    def test_past_the_day_it_is_late(self):
        self.assertEqual(part_wait(self.ago(17), 15, self.today), ('17d', '2 late', 'late'))

    def test_no_ordered_date_has_nothing_to_count_from(self):
        self.assertEqual(part_wait(None, 15, self.today), ('', '', ''))

    def test_a_forward_ordered_date_never_counts_negative(self):
        """The form refuses a future date; a row that has one anyway must not
        read "-2d" or "17 left" on a 15-day wait."""
        self.assertEqual(part_wait(self.today + timedelta(days=2), 15, self.today),
                         ('New', '15 left', ''))


class TheNumberMeansSomethingOnlyOnItsWayTests(TestCase):
    """`save()` keeps it only while the part is ordered and not received."""

    def setUp(self):
        self.card = JobCard.objects.create(
            admitted_date=date(2026, 10, 1), brand_name='Toyota',
            model_name='Corolla', registration_number='KL01EX0001')
        self.shop = SpareShop.objects.create(name='Spare club')

    def part(self, **kw):
        return JobCardSpareItem.objects.create(
            job_card=self.card, source=SHOP, spare_part_name='Brake Pads',
            shop=self.shop, **kw)

    def test_kept_while_on_its_way(self):
        spare = self.part(status='ORDERED', ordered_date=date(2026, 10, 2), expected_days=15)
        spare.refresh_from_db()
        self.assertEqual(spare.expected_days, 15)

    def test_cleared_once_received(self):
        spare = self.part(status='ORDERED', ordered_date=date(2026, 10, 2), expected_days=15)
        spare.received_date = date(2026, 10, 5)
        spare.status = 'RECEIVED'
        spare.save()
        spare.refresh_from_db()
        self.assertIsNone(spare.expected_days)

    def test_cleared_with_no_ordered_date(self):
        spare = self.part(status='PENDING', expected_days=15)
        spare.refresh_from_db()
        self.assertIsNone(spare.expected_days)

    def test_a_warehouse_draw_never_carries_one(self):
        item = Item.objects.create(category=Category.objects.create(name='Engine Oil'),
                                   name='Castrol Edge', current_stock=10)
        draw = JobCardSpareItem.objects.create(
            job_card=self.card, source=JobCardSpareItem.SOURCE_INVENTORY, item=item,
            quantity=1, ordered_date=date(2026, 10, 2), expected_days=15)
        draw.refresh_from_db()
        self.assertIsNone(draw.expected_days)


class TheJobCardSavesItTests(TestCase):
    """The box posts through the ordinary spare formset."""

    def setUp(self):
        office, _ = Group.objects.get_or_create(name='Office')
        user = User.objects.create_user(username='off', password='pw')
        user.groups.add(office)
        self.client = Client()
        self.client.force_login(user)

        self.mechanic = Mechanic.objects.create(name='Lead Tech')
        self.shop = SpareShop.objects.create(name='Ajmal Auto Parts')
        self.today = timezone.localdate()
        self.job = JobCard.objects.create(
            admitted_date=self.today, brand_name='Toyota', model_name='Corolla',
            registration_number='KL01EX0002')
        self.spare = JobCardSpareItem.objects.create(
            job_card=self.job, source=SHOP, spare_part_name='Wheel Bearing',
            shop=self.shop, status='PENDING')

    def post(self, days, ordered=None, received='', **extra):
        ordered = str(self.today) if ordered is None else ordered
        payload = {
            'registration_number': 'KL01EX0002',
            'admitted_date': str(self.today),
            'brand_name': 'Toyota', 'model_name': 'Corolla',
            'lead_mechanic': self.mechanic.id,
            'concerns-TOTAL_FORMS': '0', 'concerns-INITIAL_FORMS': '0',
            'concerns-MIN_NUM_FORMS': '0', 'concerns-MAX_NUM_FORMS': '1000',
            'inventory-TOTAL_FORMS': '0', 'inventory-INITIAL_FORMS': '0',
            'inventory-MIN_NUM_FORMS': '0', 'inventory-MAX_NUM_FORMS': '1000',
            'labours-TOTAL_FORMS': '0', 'labours-INITIAL_FORMS': '0',
            'labours-MIN_NUM_FORMS': '0', 'labours-MAX_NUM_FORMS': '1000',
            'spares-TOTAL_FORMS': '1', 'spares-INITIAL_FORMS': '1',
            'spares-MIN_NUM_FORMS': '0', 'spares-MAX_NUM_FORMS': '1000',
            'spares-0-id': str(self.spare.pk),
            'spares-0-spare_part_name': 'Wheel Bearing',
            'spares-0-status': 'RECEIVED' if received else ('ORDERED' if ordered else 'PENDING'),
            'spares-0-shop_name': str(self.shop.pk),
            'spares-0-ordered_date': ordered,
            'spares-0-received_date': received,
        }
        if days is not None:
            payload['spares-0-expected_days'] = days
        payload.update(extra)
        return self.client.post(reverse('jobcard_edit', args=[self.job.pk]), payload)

    def stored(self):
        self.spare.refresh_from_db()
        return self.spare.expected_days

    def test_typed_days_are_saved(self):
        self.assertEqual(self.post('15').status_code, 302)
        self.assertEqual(self.stored(), 15)

    def test_blank_saves_as_nobody_gave_a_day(self):
        self.assertEqual(self.post('').status_code, 302)
        self.assertIsNone(self.stored())

    def test_a_page_without_the_box_saves_nothing_wrong(self):
        """A page opened before the box existed and saved after the deploy."""
        self.assertEqual(self.post(None).status_code, 302)
        self.assertIsNone(self.stored())

    def test_an_unusable_figure_is_refused_with_its_reason(self):
        for bad in ('0', '366', 'abc', '1.5', '-3', '١٥'):
            with self.subTest(bad=bad):
                resp = self.post(bad)
                self.assertEqual(resp.status_code, 200)   # re-rendered, not saved
                body = resp.content.decode()
                self.assertIn('Wheel Bearing', body)
                self.assertIn('Expected days: Enter whole days, from 1 to 365.', body)
                self.assertIsNone(self.stored())

    def test_the_top_of_the_range_is_accepted(self):
        self.assertEqual(self.post('365').status_code, 302)
        self.assertEqual(self.stored(), 365)

    def test_a_received_part_ignores_a_stale_figure_instead_of_refusing(self):
        """The box is hidden once a part has arrived, so junk left in it must
        not refuse the save of a card nobody can see the problem on."""
        resp = self.post('abc', ordered=str(self.today - timedelta(days=3)),
                         received=str(self.today))
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(self.stored())

    def test_a_pending_part_stores_none_whatever_was_posted(self):
        self.assertEqual(self.post('15', ordered='').status_code, 302)
        self.assertIsNone(self.stored())


class ThePanelCarriesTheBoxTests(TestCase):
    """What the server owes the date panel's script, on every row shape."""

    def setUp(self):
        office, _ = Group.objects.get_or_create(name='Office')
        user = User.objects.create_user(username='off', password='pw')
        user.groups.add(office)
        self.client = Client()
        self.client.force_login(user)
        self.job = JobCard.objects.create(
            admitted_date=timezone.localdate(), brand_name='Toyota',
            model_name='Corolla', registration_number='KL01EX0003')
        JobCardSpareItem.objects.create(
            job_card=self.job, source=SHOP, spare_part_name='Clutch Plate',
            status='ORDERED', ordered_date=timezone.localdate(), expected_days=12)

    def page(self):
        return self.client.get(reverse('jobcard_edit', args=[self.job.pk])).content.decode()

    def test_a_saved_row_and_the_added_row_template_both_carry_it(self):
        page = self.page()
        self.assertRegex(page, r'name="spares-0-expected_days"[^>]*value="12"'
                               r'|value="12"[^>]*name="spares-0-expected_days"')
        self.assertIn('name="spares-__prefix__-expected_days"', page)

    def test_it_sits_inside_the_date_panel_and_ships_hidden(self):
        page = self.page()
        pop = page.split('<div class="jc-date-pop"', 1)[1].split('jc-date-done', 1)[0]
        self.assertIn('class="jc-date-field jc-date-expect" hidden', pop)
        self.assertIn('spares-0-expected_days', pop)

    def test_it_is_not_a_browser_number_box(self):
        """A number box with min/max inside a hidden panel lets the browser
        abandon the whole save silently. Text, refused by the server."""
        widget = JobCardSpareFormSet().empty_form['expected_days'].as_widget()
        self.assertIn('type="text"', widget)
        self.assertNotIn('type="number"', widget)
        self.assertNotIn(' min=', widget)
        self.assertIn('inputmode="numeric"', widget)

    def test_blank_wears_no_still_to_fill_hairline(self):
        widget = JobCardSpareFormSet().empty_form['expected_days'].as_widget()
        self.assertIn('jc-optional', widget)

    def test_the_browser_reads_the_limit_from_the_model(self):
        widget = JobCardSpareFormSet().empty_form['expected_days'].as_widget()
        self.assertIn('data-max="%d"' % JobCardSpareItem.EXPECTED_DAYS_MAX, widget)

    def test_the_warranty_card_row_carries_it_too(self):
        """An absent formset field saves as blank — so a page that shares the
        row must carry the box, or saving the warranty card would wipe it."""
        self.assertIn('expected_days', WarrantyPartFormSet.form._meta.fields)
        with open('workshop/templates/workshop/warranty/_warranty_part_row.html',
                  encoding='utf-8') as handle:
            self.assertIn('_expected_days.html" with field=p.expected_days', handle.read())


class ThePanelScriptTests(TestCase):
    """The behaviour lives in `_date_chip.html` and nothing here runs it, so
    these read the source for the three things that would break it quietly."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open('workshop/templates/workshop/includes/_date_chip.html',
                  encoding='utf-8') as handle:
            cls.source = handle.read()

    def test_only_a_change_a_person_made_opens_the_panel(self):
        """The dates→status rule re-fires the select's change in script while
        a date is typed in the panel; reacting to that would steal the cursor."""
        self.assertIn("e.isTrusted || select.value !== 'ORDERED'", self.source)

    def test_ordered_asks_in_the_apps_own_card_never_a_second_dialog(self):
        """The owners chose a centred question card. It is the app's ONE card
        (`wsConfirm`) with its short box — never a dialog of this page's own —
        and Done copies the number into the row's own box, the only copy."""
        listener = self.source.split("ORDERED ASKS", 1)[1].split('// Typing in the box', 1)[0]
        self.assertIn('window.wsConfirm({', listener)
        self.assertIn("ok: 'Done'", listener)
        self.assertIn("cancel: 'Skip'", listener)
        self.assertIn('input: {', listener)
        self.assertIn('box.value = answer.value;', listener)
        self.assertNotIn('class="modal', self.source)

    def test_the_card_reads_part_then_shop_then_one_sentence(self):
        """The owners' layout: the part as the headline, its shop under it,
        then "Expected in [ ] days" as one line."""
        listener = self.source.split("ORDERED ASKS", 1)[1].split('// Typing in the box', 1)[0]
        self.assertIn("title: name || 'Unnamed part'", listener)
        self.assertIn('html: shopLine(row)', listener)
        self.assertIn("lead: 'Expected in'", listener)
        self.assertIn("unit: 'days'", listener)

    def test_the_shop_line_is_escaped_red_when_missing_and_never_shown_to_floor(self):
        """Shop names are typed by people and the line becomes markup, so it is
        escaped. "No shop" is red. And only where the Shop column is SHOWN —
        Floor is shown no shop anywhere, so a red "No shop" it cannot fix would
        be a door it can see and not open."""
        line = self.source.split('function shopLine(row)', 1)[1].split('function expectProblem', 1)[0]
        self.assertIn("row.querySelector('select.shop-name-select')", line)
        self.assertIn("if (!shop) return '';", line)
        self.assertIn('escapeHtml(picked)', line)
        self.assertIn('<span class="wcf-missing">No shop</span>', line)
        with open('static/css/style.css', encoding='utf-8') as handle:
            self.assertIn('.wcf-missing { color: #b91c1c;', handle.read())

    def test_a_move_BACK_to_pending_never_opens_it(self):
        """Ordered → Pending is reverted by `spare_autofill.js` while its
        "Status Revert" dialog asks, so the select reads "Ordered" again by the
        time a bubbling listener runs — which re-opened the box behind the
        dialog (the owner's screenshot). The choice is read in the CAPTURE
        phase, before that file sees it, and the box waits for no dialog."""
        listener = self.source.split("ORDERED ASKS", 1)[1].split('// Typing in the box', 1)[0]
        self.assertIn('}, true);', listener)          # capture phase
        self.assertIn('setTimeout(', listener)
        self.assertIn("document.body.classList.contains('modal-open')", listener)

    def test_enter_in_the_box_is_done_not_a_save(self):
        self.assertIn("e.key === 'Enter'", self.source)
        enter = self.source.split("e.key === 'Enter'", 1)[1][:400]
        self.assertIn('e.preventDefault()', enter)

    def test_the_shared_card_puts_its_box_back_for_the_next_delete(self):
        """The card's one text box is the delete REASON box everywhere else.
        A short box shown for the days must never leak its placeholder, limit,
        unit or warning into the next delete dialog — and Enter answers only
        the short box, never a delete by reflex."""
        with open('workshop/static/js/confirm.js', encoding='utf-8') as handle:
            js = handle.read()
        ask = js.split('function ask(opts)', 1)[1].split('/* ---', 1)[0]
        for reset in ("reason.placeholder = 'Reason (optional)';",
                      'reason.maxLength = 255;',
                      "reason.removeAttribute('inputmode');",
                      "wrap.classList.remove('wcf-reason--short');",
                      "if (lead) { lead.hidden = true; lead.textContent = ''; }",
                      'check = null;'):
            self.assertIn(reset, ask)
        # The reset comes BEFORE the short box is set up.
        self.assertLess(ask.index('check = null;'), ask.index('if (input) {'))
        self.assertIn("if (e.key !== 'Enter' || !check) { return; }", js)

    def test_the_browser_warning_says_the_servers_words(self):
        self.assertIn("'Enter whole days, from 1 to ' + top + '.'", self.source)
        with open('workshop/forms.py', encoding='utf-8') as handle:
            self.assertIn('f"Enter whole days, from 1 to {top}."', handle.read())


class TheLiveReportSaysHowLongTests(TestCase):
    """The "On the way" box, and only that box."""

    def setUp(self):
        owner_group, _ = Group.objects.get_or_create(name='Owner')
        owner = User.objects.create_user(username='own', password='pw')
        owner.groups.add(owner_group)
        self.client = Client()
        self.client.force_login(owner)
        self.today = timezone.localdate()
        self.card = JobCard.objects.create(
            admitted_date=self.today - timedelta(days=20), brand_name='Audi',
            model_name='A4', registration_number='KL01EX0004')
        self.shop = SpareShop.objects.create(name='Spare club')

    def ordered(self, name, days_ago, expected=None):
        return JobCardSpareItem.objects.create(
            job_card=self.card, source=SHOP, spare_part_name=name, shop=self.shop,
            status='ORDERED', ordered_date=self.today - timedelta(days=days_ago),
            expected_days=expected)

    def box(self, colour):
        page = self.client.get(reverse('live_report')).content.decode()
        return page.split('<section class="lr-box lr-box--%s">' % colour, 1)[1].split('</section>', 1)[0]

    def row(self, box, name):
        return box.split(name, 1)[1].split('</a>', 1)[0]

    def test_age_and_days_left(self):
        self.ordered('Brake Pads', 2, expected=15)
        row = self.row(self.box('amber'), 'Brake Pads')
        self.assertIn('<span class="lr-days-age">2d</span>', row)
        self.assertIn('<span class="lr-days-due">13 left</span>', row)

    def test_late_is_red(self):
        self.ordered('Clutch Plate', 17, expected=15)
        row = self.row(self.box('amber'), 'Clutch Plate')
        self.assertIn('<span class="lr-days-due lr-days-due--late">2 late</span>', row)

    def test_due_today_is_amber(self):
        self.ordered('Drive Belt', 15, expected=15)
        row = self.row(self.box('amber'), 'Drive Belt')
        self.assertIn('<span class="lr-days-due lr-days-due--today">due today</span>', row)

    def test_no_expected_days_shows_the_age_alone(self):
        self.ordered('Wiper Blades', 4)
        row = self.row(self.box('amber'), 'Wiper Blades')
        self.assertIn('<span class="lr-days-age">4d</span>', row)
        self.assertNotIn('lr-days-due', row)

    def test_late_is_red_and_due_today_amber_in_the_stylesheet(self):
        page = re.sub(r'\s+', ' ', self.client.get(reverse('live_report')).content.decode())
        self.assertIn('.lr-days-due--late { color: var(--lr-red); }', page)
        self.assertIn('.lr-days-due--today { color: var(--lr-amber); }', page)

    def test_a_received_part_carries_no_clock(self):
        JobCardSpareItem.objects.create(
            job_card=self.card, source=SHOP, spare_part_name='Air Filter', shop=self.shop,
            status='RECEIVED', ordered_date=self.today - timedelta(days=3),
            received_date=self.today)
        self.assertNotIn('lr-spare-days', self.box('green'))

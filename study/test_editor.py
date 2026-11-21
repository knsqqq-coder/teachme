from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from .demo import DEMO_TEXT
from .models import Flashcard, Source


class FlashcardEditingWorkflowTests(TestCase):
    def setUp(self):
        self.source = Source.objects.create(
            title='Желілер',
            text=DEMO_TEXT,
            generation_mode='demo',
        )
        self.other_source = Source.objects.create(
            title='Басқа жинақ',
            text=DEMO_TEXT,
            generation_mode='demo',
        )
        self.cards = [
            Flashcard.objects.create(
                source=self.source,
                position=position,
                question=f'Сұрақ {position}',
                answer=f'Жауап {position}',
                source_quote=DEMO_TEXT.splitlines()[position - 1],
                is_verified=(position == 2),
            )
            for position in range(1, 4)
        ]
        self.other_card = Flashcard.objects.create(
            source=self.other_source,
            position=1,
            question='Басқа жинақтың сұрағы',
            answer='Басқа жауап',
            source_quote=DEMO_TEXT.splitlines()[0],
        )
        self.detail_url = reverse('source_detail', kwargs={'pk': self.source.pk})

    def edit_url(self, card=None):
        return reverse('card_edit', kwargs={'pk': (card or self.cards[0]).pk})

    def delete_url(self, card=None):
        return reverse('card_delete', kwargs={'pk': (card or self.cards[0]).pk})

    def review_url(self, card=None):
        return reverse('card_review', kwargs={'pk': (card or self.cards[0]).pk})

    def valid_edit_data(self, card=None, **overrides):
        card = card or self.cards[0]
        data = {
            'question': card.question,
            'answer': card.answer,
            'source_quote': card.source_quote,
        }
        data.update(overrides)
        return data

    @patch('study.views.generate_cards')
    def test_edit_get_does_not_write_or_generate(self, generate):
        before = list(Flashcard.objects.values_list('pk', 'question', 'answer', 'is_verified'))

        response = self.client.get(self.edit_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].instance.pk, self.cards[0].pk)
        self.assertEqual(
            list(Flashcard.objects.values_list('pk', 'question', 'answer', 'is_verified')),
            before,
        )
        generate.assert_not_called()

    @patch('study.views.generate_cards')
    def test_valid_edit_updates_only_card_and_clears_verified_state(self, generate):
        card = self.cards[1]
        updated_question = 'DNS атауы IP-мекенжаймен қалай сәйкестенеді?'
        updated_answer = 'DNS домен атауын IP-мекенжаймен сәйкестендіреді.'
        response = self.client.post(
            self.edit_url(card),
            self.valid_edit_data(
                card,
                question=updated_question,
                answer=updated_answer,
                source_quote=DEMO_TEXT.splitlines()[2],
                source=self.other_source.pk,
                position=91,
                is_verified='on',
            ),
        )

        self.assertRedirects(response, self.detail_url)
        card.refresh_from_db()
        self.assertEqual(card.question, updated_question)
        self.assertEqual(card.answer, updated_answer)
        self.assertEqual(card.source_quote, DEMO_TEXT.splitlines()[2])
        self.assertEqual(card.source_id, self.source.pk)
        self.assertEqual(card.position, 2)
        self.assertFalse(card.is_verified)
        self.assertEqual(self.source.cards.count(), 3)
        self.assertEqual(self.other_source.cards.count(), 1)
        generate.assert_not_called()

    @patch('study.views.generate_cards')
    def test_invalid_edit_values_are_shown_and_not_saved(self, generate):
        card = self.cards[0]
        original = (card.question, card.answer, card.source_quote, card.position, card.is_verified)
        invalid_cases = [
            ({'question': ''}, 'This field is required.'),
            ({'question': 'Q' * 301}, 'Ensure this value has at most 300 characters'),
            ({'source_quote': 'Конспектте жоқ сөйлем.'}, 'бастапқы конспектіден дәл табылмады'),
        ]

        for changes, message in invalid_cases:
            with self.subTest(changes=changes):
                response = self.client.post(self.edit_url(card), self.valid_edit_data(card, **changes))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                if 'question' in changes:
                    self.assertEqual(response.context['form']['question'].value(), changes['question'])
                if 'source_quote' in changes:
                    self.assertEqual(response.context['form']['source_quote'].value(), changes['source_quote'])
                card.refresh_from_db()
                self.assertEqual(
                    (card.question, card.answer, card.source_quote, card.position, card.is_verified),
                    original,
                )

        generate.assert_not_called()

    def test_edit_post_without_csrf_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        url = self.edit_url()
        client.get(url)
        card = self.cards[0]

        response = client.post(url, self.valid_edit_data(card, answer='Жаңа жауап'))

        self.assertEqual(response.status_code, 403)
        card.refresh_from_db()
        self.assertEqual(card.answer, 'Жауап 1')

    @patch('study.views.generate_cards')
    def test_delete_get_and_cancel_link_leave_records_untouched(self, generate):
        before = (Source.objects.count(), Flashcard.objects.count())

        response = self.client.get(self.delete_url(self.cards[0]))
        detail_response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Иә, өшіру')
        self.assertContains(response, reverse('source_detail', kwargs={'pk': self.source.pk}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual((Source.objects.count(), Flashcard.objects.count()), before)
        generate.assert_not_called()

    @patch('study.views.generate_cards')
    def test_delete_post_removes_one_card_and_keeps_source_and_neighbors(self, generate):
        deleted = self.cards[1]
        response = self.client.post(self.delete_url(deleted))

        self.assertRedirects(response, self.detail_url)
        self.assertTrue(Source.objects.filter(pk=self.source.pk).exists())
        self.assertFalse(Flashcard.objects.filter(pk=deleted.pk).exists())
        self.assertEqual(list(self.source.cards.values_list('pk', flat=True)), [self.cards[0].pk, self.cards[2].pk])
        self.assertTrue(Flashcard.objects.filter(pk=self.other_card.pk).exists())
        self.assertEqual(self.source.cards.count(), 2)
        generate.assert_not_called()

    def test_delete_post_without_csrf_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        url = self.delete_url(self.cards[0])
        client.get(url)

        response = client.post(url)

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Flashcard.objects.filter(pk=self.cards[0].pk).exists())

    @patch('study.views.generate_cards')
    def test_review_is_post_only_verify_reset_and_repeated_verify(self, generate):
        card = self.cards[0]
        self.assertEqual(self.client.get(self.review_url(card)).status_code, 405)

        response = self.client.post(self.review_url(card), {'action': 'verify'})
        self.assertRedirects(response, self.detail_url)
        card.refresh_from_db()
        self.assertTrue(card.is_verified)

        self.client.post(self.review_url(card), {'action': 'verify'})
        card.refresh_from_db()
        self.assertTrue(card.is_verified)

        self.client.post(self.review_url(card), {'action': 'reset'})
        card.refresh_from_db()
        self.assertFalse(card.is_verified)
        generate.assert_not_called()

    @patch('study.views.generate_cards')
    def test_unknown_review_action_does_not_write(self, generate):
        card = self.cards[0]
        response = self.client.post(self.review_url(card), {'action': 'unknown'})

        self.assertEqual(response.status_code, 400)
        card.refresh_from_db()
        self.assertFalse(card.is_verified)
        generate.assert_not_called()

    @patch('study.views.generate_cards')
    def test_filters_have_source_wide_counts_and_do_not_mix_other_sources(self, generate):
        cases = [
            ('all', ['Сұрақ 1', 'Сұрақ 2', 'Сұрақ 3'], 3),
            ('pending', ['Сұрақ 1', 'Сұрақ 3'], 2),
            ('verified', ['Сұрақ 2'], 1),
            ('unknown', ['Сұрақ 1', 'Сұрақ 2', 'Сұрақ 3'], 3),
        ]

        for status, visible_questions, visible_count in cases:
            with self.subTest(status=status):
                response = self.client.get(self.detail_url, {'status': status})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([card.question for card in response.context['cards']], visible_questions)
                self.assertEqual(response.context['total_count'], 3)
                self.assertEqual(response.context['verified_count'], 1)
                self.assertEqual(response.context['pending_count'], 2)
                self.assertEqual(len(response.context['cards']), visible_count)
                self.assertNotContains(response, self.other_card.question)

        generate.assert_not_called()

    def test_empty_filter_and_empty_source_keep_helpful_content(self):
        pending = self.client.get(self.detail_url, {'status': 'pending'})
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(list(pending.context['cards']), [self.cards[0], self.cards[2]])

        self.source.cards.update(is_verified=True)
        empty_filter = self.client.get(self.detail_url, {'status': 'pending'})
        self.assertEqual(empty_filter.status_code, 200)
        self.assertEqual(list(empty_filter.context['cards']), [])
        self.assertContains(empty_filter, 'Бұл сүзгіде карточка жоқ.')
        self.assertContains(empty_filter, '?status=all')
        self.assertContains(empty_filter, DEMO_TEXT.splitlines()[0])

        self.source.cards.all().delete()
        empty_source = self.client.get(self.detail_url, {'status': 'verified'})
        self.assertEqual(empty_source.status_code, 200)
        self.assertEqual(empty_source.context['total_count'], 0)
        self.assertContains(empty_source, 'Бұл жинақта карточка қалмады.')
        self.assertContains(empty_source, DEMO_TEXT.splitlines()[0])

    def test_missing_source_or_card_urls_return_404(self):
        missing_pk = 999999
        urls = [
            reverse('source_detail', kwargs={'pk': missing_pk}),
            reverse('card_edit', kwargs={'pk': missing_pk}),
            reverse('card_delete', kwargs={'pk': missing_pk}),
            reverse('card_review', kwargs={'pk': missing_pk}),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    @patch('study.views.generate_cards')
    def test_edit_delete_filter_and_review_never_call_generator(self, generate):
        self.client.get(self.edit_url())
        self.client.post(self.edit_url(), self.valid_edit_data(answer='Түзетілген жауап'))
        self.client.get(self.delete_url(self.cards[2]))
        self.client.get(self.detail_url, {'status': 'pending'})
        self.client.post(self.review_url(self.cards[0]), {'action': 'verify'})

        generate.assert_not_called()

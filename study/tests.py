from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse

from .demo import DEMO_CARDS, DEMO_TEXT
from .models import Flashcard, Source
from .services import GenerationError, validate_cards


class SourceAndFlashcardFlowTests(TestCase):
    def setUp(self):
        self.home_url = reverse('home')
        self.valid_data = {'title': 'Компьютерные сети', 'text': DEMO_TEXT}

    @patch('study.views.generate_cards', return_value=DEMO_CARDS)
    def test_valid_demo_post_saves_source_and_cards_then_redirects(self, generate):
        response = self.client.post(self.home_url, self.valid_data)

        self.assertRedirects(response, reverse('source_detail', kwargs={'pk': 1}))
        self.assertEqual(Source.objects.count(), 1)
        self.assertEqual(Flashcard.objects.count(), 3)
        source = Source.objects.get()
        self.assertEqual(source.generation_mode, 'demo')
        self.assertEqual(list(source.cards.values_list('position', flat=True)), [1, 2, 3])
        generate.assert_called_once_with(DEMO_TEXT)

    @patch('study.views.generate_cards')
    def test_short_text_is_rejected_before_provider_call(self, generate):
        response = self.client.post(self.home_url, {'title': 'Қысқа мәтін', 'text': 'өте қысқа'})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(generate.called)
        self.assertEqual(Source.objects.count(), 0)
        self.assertEqual(Flashcard.objects.count(), 0)
        self.assertContains(response, 'at least 80 characters')

    def test_invalid_quote_rejects_the_entire_result(self):
        invalid_cards = [dict(card) for card in DEMO_CARDS]
        invalid_cards[1]['source_quote'] = 'Бұл дәйексөз конспектте жоқ.'

        with self.assertRaises(GenerationError):
            validate_cards({'cards': invalid_cards}, DEMO_TEXT)

        self.assertEqual(Source.objects.count(), 0)
        self.assertEqual(Flashcard.objects.count(), 0)

    @patch('study.views.generate_cards', side_effect=GenerationError('Карточки не удалось подготовить.'))
    def test_generation_error_keeps_bound_form_and_creates_no_records(self, generate):
        response = self.client.post(self.home_url, self.valid_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Карточки не удалось подготовить.')
        self.assertContains(response, DEMO_TEXT.splitlines()[0])
        self.assertEqual(response.context['form']['text'].value(), DEMO_TEXT)
        self.assertEqual(Source.objects.count(), 0)
        self.assertEqual(Flashcard.objects.count(), 0)
        generate.assert_called_once_with(DEMO_TEXT)

    @patch('study.views.Flashcard.objects.bulk_create')
    def test_database_error_during_card_writes_rolls_back_source(self, bulk_create):
        def insert_first_then_fail(objects, **kwargs):
            objects[0].save(force_insert=True)
            raise DatabaseError('simulated database failure')

        bulk_create.side_effect = insert_first_then_fail
        response = self.client.post(self.home_url, self.valid_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Не удалось сохранить конспект и карточки.')
        self.assertEqual(Source.objects.count(), 0)
        self.assertEqual(Flashcard.objects.count(), 0)

    @patch('study.views.generate_cards')
    def test_detail_get_twice_reads_saved_cards_without_provider_or_writes(self, generate):
        source = Source.objects.create(title='Networks', text=DEMO_TEXT, generation_mode='demo')
        Flashcard.objects.bulk_create([
            Flashcard(source=source, position=index, **card)
            for index, card in enumerate(DEMO_CARDS, start=1)
        ])
        before = (Source.objects.count(), Flashcard.objects.count())
        url = reverse('source_detail', kwargs={'pk': source.pk})

        first = self.client.get(url)
        second = self.client.get(url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertContains(first, DEMO_CARDS[0]['question'])
        self.assertContains(second, DEMO_CARDS[0]['question'])
        self.assertEqual((Source.objects.count(), Flashcard.objects.count()), before)
        generate.assert_not_called()

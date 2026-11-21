from django.conf import settings
from django.db import DatabaseError, transaction
from django.http import HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from .demo import DEMO_TEXT, DEMO_TITLE
from .forms import FlashcardForm, SourceForm
from .models import Flashcard, Source
from .services import GenerationError, generate_cards


def home(request):
    context = {
        'mode': str(getattr(settings, 'TEACHME_MODE', 'demo')).strip().upper(),
        'sources': Source.objects.order_by('-created_at', '-id')[:20],
    }
    if request.method == 'POST':
        form = SourceForm(request.POST)
        if form.is_valid():
            text = form.cleaned_data['text']
            try:
                cards = generate_cards(text)
            except GenerationError as exc:
                form.add_error(None, str(exc))
            else:
                generation_mode = str(getattr(settings, 'TEACHME_MODE', 'demo')).strip().lower()
                try:
                    with transaction.atomic():
                        source = Source.objects.create(
                            title=form.cleaned_data['title'],
                            text=text,
                            generation_mode=generation_mode,
                        )
                        Flashcard.objects.bulk_create([
                            Flashcard(
                                source=source,
                                position=position,
                                question=card['question'],
                                answer=card['answer'],
                                source_quote=card['source_quote'],
                            )
                            for position, card in enumerate(cards, start=1)
                        ])
                except DatabaseError:
                    form.add_error(None, 'Не удалось сохранить конспект и карточки. Попробуйте ещё раз.')
                else:
                    return redirect('source_detail', pk=source.pk)
    else:
        form = SourceForm(initial={'title': DEMO_TITLE, 'text': DEMO_TEXT})
    context['form'] = form
    return render(request, 'study/home.html', context)


def source_detail(request, pk):
    source = get_object_or_404(Source, pk=pk)
    all_cards = source.cards.order_by('position', 'pk')
    total_count = all_cards.count()
    verified_count = all_cards.filter(is_verified=True).count()
    pending_count = total_count - verified_count

    status = request.GET.get('status', 'all')
    if status not in {'all', 'pending', 'verified'}:
        status = 'all'

    if status == 'pending':
        cards = all_cards.filter(is_verified=False)
    elif status == 'verified':
        cards = all_cards.filter(is_verified=True)
    else:
        cards = all_cards

    return render(
        request,
        'study/source_detail.html',
        {
            'source': source,
            'cards': cards,
            'status': status,
            'total_count': total_count,
            'verified_count': verified_count,
            'pending_count': pending_count,
        },
    )


def card_edit(request, pk):
    card = get_object_or_404(Flashcard, pk=pk)
    if request.method == 'POST':
        form = FlashcardForm(request.POST, instance=card)
        if form.is_valid():
            updated_card = form.save(commit=False)
            updated_card.is_verified = False
            updated_card.save(update_fields=['question', 'answer', 'source_quote', 'is_verified'])
            return redirect('source_detail', pk=card.source_id)
    else:
        form = FlashcardForm(instance=card)
    return render(request, 'study/card_form.html', {'form': form, 'card': card, 'source': card.source})


def card_delete(request, pk):
    card = get_object_or_404(Flashcard, pk=pk)
    source_id = card.source_id
    if request.method == 'POST':
        card.delete()
        return redirect('source_detail', pk=source_id)
    return render(request, 'study/card_confirm_delete.html', {'card': card, 'source': card.source})


def card_review(request, pk):
    card = get_object_or_404(Flashcard, pk=pk)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    action = request.POST.get('action')
    if action not in {'verify', 'reset'}:
        return HttpResponseBadRequest('Белгісіз тексеру әрекеті.')

    card.is_verified = action == 'verify'
    card.save(update_fields=['is_verified'])
    return redirect('source_detail', pk=card.source_id)

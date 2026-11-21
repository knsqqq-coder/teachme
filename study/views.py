from django.conf import settings
from django.db import DatabaseError, transaction
from django.shortcuts import get_object_or_404, redirect, render

from .demo import DEMO_TEXT, DEMO_TITLE
from .forms import SourceForm
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
    cards = source.cards.order_by('position', 'id')
    return render(request, 'study/source_detail.html', {'source': source, 'cards': cards})

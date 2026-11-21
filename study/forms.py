from django import forms

from .models import Flashcard


class SourceForm(forms.Form):
    title = forms.CharField(
        label='Тема',
        max_length=120,
        strip=True,
    )
    text = forms.CharField(
        label='Конспект',
        min_length=80,
        max_length=12000,
        strip=True,
        widget=forms.Textarea,
    )

    def clean_text(self):
        text = self.cleaned_data['text']
        return text.replace('\r\n', '\n').replace('\r', '\n')


class FlashcardForm(forms.ModelForm):
    class Meta:
        model = Flashcard
        fields = ['question', 'answer', 'source_quote']
        labels = {
            'question': 'Сұрақ',
            'answer': 'Жауап',
            'source_quote': 'Конспектідегі дәл дәйексөз',
        }
        widgets = {
            'question': forms.TextInput(),
            'answer': forms.Textarea(attrs={'rows': 5}),
            'source_quote': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_source_quote(self):
        source_quote = self.cleaned_data['source_quote']
        source_quote = source_quote.replace('\r\n', '\n').replace('\r', '\n')
        if source_quote not in self.instance.source.text:
            raise forms.ValidationError(
                'Бұл дәйексөз бастапқы конспектіден дәл табылмады. Конспектідегі сөйлемді өзгеріссіз көшіріңіз.'
            )
        return source_quote

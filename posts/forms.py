from django.forms import ModelForm, Textarea

from .models import Comment, Post


class PostForm(ModelForm):

    class Meta:
        model = Post
        fields = ('group', 'text', 'image')
        required = {
            'group': False,
        }
        labels = {
            'group': 'Сообщества',
            'text': 'Текст записи',
        }


class CommentForm(ModelForm):

    class Meta:
        model = Comment
        fields = ('text',)
        widgets = {'text': Textarea(attrs={'rows': 3}), }
        labels = {'text': 'Текст комментария'}

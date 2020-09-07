from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import cache_page

from .forms import CommentForm, PostForm
from .models import Comment, Follow, Group, Post


@cache_page(20, cache='default', key_prefix='')
def index(request):
    latest = Post.objects.select_related('group', 'author').all()
    paginator = Paginator(latest, 10)
    page_number = request.GET.get('page')
    page = paginator.get_page(page_number)
    # узнаем, подписан ли на кого-то залогиненный пользователь
    follow = Follow.objects.filter(user__username=request.user).exists()
    return render(
        request,
        'index.html',
        {
            'page': page, 'paginator': paginator,
            'follow': follow
        }
    )


def group_posts(request, slug):
    group = get_object_or_404(Group, slug=slug)
    posts = group.posts.all()
    paginator = Paginator(posts, 10)
    page_number = request.GET.get('page')
    page = paginator.get_page(page_number)
    return render(request, 'group.html', {
        'group': group,
        'page': page,
        'posts': posts,
        'paginator': paginator
    })


@login_required
def new_post(request):
    form = PostForm(request.POST or None, files=request.FILES or None)
    if not form.is_valid():
        return render(
            request,
            'posts/new_post.html',
            {'form': form}
        )
    form.instance.author = request.user
    form.save()
    return redirect('index')


@login_required
def post_edit(request, username, post_id):
    post = get_object_or_404(Post, author__username=username, id=post_id)
    if request.user != post.author:
        return redirect('post', username=post.author, post_id=post_id)
    form = PostForm(
        request.POST or None, files=request.FILES or None, instance=post
    )
    if form.is_valid():
        form.save()
        return redirect('post', username=username, post_id=post_id)
    return render(
        request,
        'posts/new_post.html',
        {'form': form, 'post': post}
    )


def profile(request, username):
    user_profile = get_object_or_404(User, username=username)
    posts = user_profile.posts.all()
    # такой вариант работает без try и if :) в index тоже
    following = Follow.objects.filter(
        author=user_profile,
        user__username=request.user).exists()
    paginator = Paginator(posts, 10)
    page_num = request.GET.get('page')
    page = paginator.get_page(page_num)
    return render(
        request,
        'posts/profile.html',
        {
            'page': page,
            'paginator': paginator,
            'author': user_profile,
            'following': following
        }
    )


def post_view(request, username, post_id):
    post = get_object_or_404(Post, author__username=username, pk=post_id)
    items = Comment.objects.filter(post_id=post_id)
    form = CommentForm(instance=None)
    return render(
        request,
        'posts/post.html',
        {
            'post': post,
            'author': post.author,
            'items': items, 'form': form
        }
    )


@login_required
def add_comment(request, username, post_id):
    post = get_object_or_404(Post, author__username=username, pk=post_id)
    form = CommentForm(request.POST or None)
    if form.is_valid():
        form.instance.author = request.user
        form.instance.post = post
        form.save()
    return redirect('post', username=username, post_id=post_id)


@login_required
def follow_index(request):
    posts = Post.objects.select_related('author', 'group').filter(
        author__following__user=request.user)
    paginator = Paginator(posts, 10)
    page_number = request.GET.get(
        'page')
    page = paginator.get_page(
        page_number)
    return render(request, 'follow.html',
                  {'page': page, 'paginator': paginator})


@login_required
def profile_follow(request, username):
    user = request.user
    author = get_object_or_404(User, username=username)
    if user != author:
        Follow.objects.get_or_create(user=user, author=author)
    return redirect('profile', username)


@login_required
def profile_unfollow(request, username):
    author = get_object_or_404(User, username=username)
    # И ведь действительно работает и так :)
    Follow.objects.filter(user=request.user, author=author).delete()
    return redirect('profile', username)


def server_error(request):
    return render(request, 'misc/500.html', status=500)


def page_not_found(request):
    return render(
        request,
        'misc/404.html',
        {'path': request.path},
        status=404
    )

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.core.cache import cache
from PIL import Image
import random
import string
import time
import os

from .models import Group, Post, User, Follow


class TestProfile(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='HaroldFinch'
        )

    def test_profile(self):
        response = self.client.get(
            reverse(
                'profile',
                kwargs={'username': self.user.username}
            )
        )
        self.assertEqual(
            response.status_code,
            200,
            msg='Профиль пользователя не найден'
        )


class TestPostCreaton(TestCase):
    def setUp(self):
        self.client = Client()
        self.client2 = Client()
        self.user = User.objects.create_user(
            username='HaroldFinch'
        )
        self.user2 = User.objects.create_user(
            username='JohnReese'
        )
        self.group = Group.objects.create(
            title='Person of Interest',
            slug='PoV'
        )
        self.group2 = Group.objects.create(
            title='Game of Thrones',
            slug='GoT'
        )
        self.post_text = 'Only the paranoid survive'
        self.post_edited_text = 'No, not your rules.'
        self.client.force_login(self.user)
        self.client2.force_login(self.user2)

    # Вынесли метод для получения объекта поста из страниц сайта
    # Достает пост из списка ссылок и передает его на дальнейшую проверку
    def check_post_from_page(self, urls, text, user, group):
        for url in urls:
            with self.subTest(url=url, msg=f'Запись не найдена'
                                           f' на странице'):
                response = self.client.get(url)
                paginator = response.context.get('paginator')
                if paginator is not None:
                    self.assertEqual(
                        paginator.count, 1,
                        msg='Несоответствие количества записей'
                            'или Paginator работает некорректно'
                    )
                    post = response.context['page'][0]
                else:
                    post = response.context['post']
                self.check_equality(post, text, user, group)

    # Отдельный метод сверки всех полей, вывода соответсвующих
    # сообщений об ошибках и получения поста на выходе
    def check_equality(self, e_posts, text, user, group):
        # Дабы сделать метод более универсальным, добавим проверку сущности
        # получаемого объекта
        if hasattr(e_posts, 'query'):
            self.assertEqual(e_posts.count(), 1,
                             msg='Количество постов не соответствует '
                                 'заданным')
            e_post = e_posts.last()
        else:
            e_post = e_posts
        self.assertEqual(e_post.text, text,
                         msg='Текст поста не соотвествует заданному или '
                             'отсутствует')
        self.assertEqual(e_post.author.username, user.username,
                         msg='Автор поста не соотвествует заданному')
        self.assertEqual(e_post.group.slug, group.slug,
                         msg='Сообщество поста не соответствует заданному')
        return e_post

    # В  следующем тесте создаем пост через HTTP и сверяем соответствие в
    # БД
    def test_new_post_auth(self):
        response = self.client.post(reverse('new_post'),
                                    {
                                        'text': self.post_text,
                                        'group': self.group.id
                                    }, follow=True)
        self.assertRedirects(response, reverse('index'))
        posts = Post.objects.all()
        self.check_equality(posts, self.post_text, self.user, self.group)

    # Создаем пост в БД и сверяем отображение через http запросы к сайту
    def test_post_display(self):
        post = Post.objects.create(text=self.post_text,
                                   group=self.group,
                                   author=self.user)
        urls = (
            reverse('index'),
            reverse('profile', args=[self.user.username]),
            reverse('group', args=[self.group.slug]),
            reverse('post', args=[self.user.username, post.pk]),
        )
        # Мы подождём :)
        time.sleep(21)
        self.check_post_from_page(urls, self.post_text, self.user,
                                  self.group)

    # Создаем пост в БД, редактируем через http и сверяем содержимое на
    # всех
    # связанных страницах
    def test_edit(self):
        post = Post.objects.create(
            text=self.post_text,
            author=self.user,
            group=self.group
        )
        response = self.client.post(
            reverse(
                'post_edit',
                kwargs={
                    'username': self.user.username,
                    'post_id': post.id
                }
            ),
            {
                'text': self.post_edited_text,
                'group': self.group2.id
            }, follow=True
        )
        self.assertEqual(response.status_code, 200,
                         msg='Сервер вернул неожиданный ответ')
        posts = Post.objects.all()
        # Проверяем соответствие объекта из БД с заданными и получаем
        # сам пост
        self.check_equality(posts, self.post_edited_text, self.user,
                            self.group2)
        # Почистим кэш, чтобы увидеть результат
        cache.clear()
        urls = (
            reverse('index'),
            reverse('profile', args=[self.user.username]),
            reverse('group', args=[self.group2.slug]),
            reverse('post', args=[self.user.username, post.pk]),
        )
        # А также на соответствующих страницах. Сверяем объектами из
        # контекста, поскольку поля объектов уже проверены выше
        self.check_post_from_page(urls, self.post_edited_text, self.user,
                                  self.group2)

    # Создаем пост через БД, далее логинимся под вторым пользователем и
    # пытаемся изменить текст и сообщество через http,
    # далее проверяем изменения в БД
    def test_wrong_user_edit(self):
        self.post = Post.objects.create(
            text=self.post_text,
            author=self.user, group=self.group
        )
        response = self.client2.post(
            reverse(
                'post_edit',
                kwargs={
                    'username': self.post.author,
                    'post_id': self.post.id
                }
            ),
            {
                'text': self.post_edited_text,
                'group': self.group2.id
            }, follow=True
        )
        target_url = reverse('post', kwargs={
            'username': self.user.username, 'post_id': self.post.id
        })
        self.assertRedirects(response, target_url,
                             msg_prefix='Редирект для неверного '
                                        'пользователя '
                                        'работает неправильно')
        posts = Post.objects.all()
        # Убедимся, что пост остался в неизменном виде и в БД не появилось
        # новых постов
        self.check_equality(posts, self.post_text, self.user, self.group)
        # И что на страницах сайта также всё в порядке
        urls = (
            reverse('index'),
            reverse('profile', args=[self.user.username]),
            reverse('group', args=[self.group.slug]),
            reverse('post', args=[self.user.username, self.post.id]),
        )
        # Проверим целостность исходных постов на страницах сайтах и не
        # пояивлось новых
        cache.clear()
        self.check_post_from_page(urls, self.post_text, self.user,
                                  self.group)
        # Убедимся, что у второго автора не появилось страницы с постом
        response = self.client.get(
            reverse('post', args=[self.user2.username, 1]))
        self.assertEqual(response.status_code, 404)


class TestUnAuthAccess(TestCase):
    def setUp(self):
        self.client = Client()
        self.post_text = 'Only the paranoid survive'
        self.group = Group.objects.create(
            title='Person of Interest',
            slug='PoV'
        )

    def test_unathorized_new_post(self):
        response = self.client.post(
            reverse('new_post'),
            {'text': self.post_text, 'group': self.group.slug}
        )
        login_url = reverse('login')
        new_post_url = reverse('new_post')
        target_url = f'{login_url}?next={new_post_url}'
        self.assertRedirects(
            response,
            target_url,
            msg_prefix='Редирект для неавторизованного пользователя '
                       'работает неправильно'
        )
        self.assertEqual(Post.objects.count(), 0,
                         msg='Сайт позволяет создавать посты'
                             ' неавторизованным пользователям')

class TestImage(TestCase):
    def setUp(self):
        pass

    def test_post_with_image(self):
        pass
#        small_img=()

class ImageTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='ImageTest',  password='1234'
        )
        self.client.force_login(self.user)
        self.group = Group.objects.create(
            title='ImageGroup', slug='img_group', description='Image Test Group')
        img = Image.new('RGB', (300, 300), color='red')
        with open(img) as infile:
            _file = SimpleUploadedFile(filename, infile.read())
            self.post = Post.objects.create(
                author=self.user,
                text='text',
                image=img
            )
        self.image = SimpleUploadedFile(name='some.jpg', content=img, content_type='image/jpg')
        # Need to be fixed!!

        self.urls = [
            reverse('index'),
            reverse('post', args=[self.user.username, self.post.id]),
            reverse('profile', args=[self.user.username]),
            reverse('group', args=[self.group.slug])
        ]

    def test_image_exists(self):
        response = self.client.get(reverse('index'))
        for url in self.urls:
            with self.subTest(url=url):
                response=self.client.get(url)
                self.assertContains(response, '<img>')

        ## Прямое сравнение картинок оставим до лучших времен
        # paginator = response.context.get('paginator')
        # if paginator is not None:
        #     post = response.context['page'][0]
        # else:
        #     post = response.context['post']
        # image = post.image
        # self.assertEqual(image, self.img)


        # self.assertContains(
        #     response, '<img', status_code=200, count=1,
        #     msg_prefix='img tag not found on the index page',
        #     html=False)
        # response = self.client.get(
        #     reverse('profile', kwargs={'username': self.user.username}))
        # self.assertContains(
        #     response, '<img', status_code=200, count=1,
        #     msg_prefix='img tag not found on the profile page',
        #     html=False)
        # response = self.client.get(
        #     reverse('group_posts', kwargs={'slug': 'img_group'}))
        # self.assertContains(
        #     response, '<img', status_code=200, count=1,
        #     msg_prefix='img tag not found on the group page',
        #     html=False)


    def test_wrong_file_type(self):
        with open('README.md', 'rb') as f_obj:
            self.client.post(
                reverse('new_post'),
                {'text': 'Тестовый пост с неправильным типом файла',
                 'image': f_obj})
        response = self.client.get(reverse('index'))
        self.assertNotContains(
            response, 'Тестовый пост с неправильным типом файла',
            status_code=200, msg_prefix='Test post with wrong img type found, but it should not', html=False)

    def tearDown(self):
        os.remove('test_red.jpg')

class TestFollow(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(
            username='HaroldFinch'
        )
        self.user2 = User.objects.create_user(
            username='JohnReese',
            email='j.reeese@contoso.com',
            password='12345678a'
        )
        self.user3 = User.objects.create_user(
            username='SamanthaGrooves',
            email='root@contoso.com',
            password='12345678a'
        )
        self.post = Post.objects.create(
            text='Followed text', author=self.user3
        )
        cache.clear()

    def test_follow_unfollow(self):
        # Подписываемся
        self.client.force_login(self.user1)
        self.client.get(reverse('profile_follow', kwargs={'username': self.user2.username}))
        response = self.client.get(reverse('profile', kwargs={'username': self.user1.username}))
        self.assertEqual(response.status_code, 200, msg='Сервер вернул неожиданный ответ')
        self.assertEqual(response.context['follower_count'], 1, msg='Несоответсвие количества подписок')
        # test = Follow.objects.filter(author__username__contains=self.user2.username)
        # Отписываемся
        self.client.get(reverse('profile_unfollow',
                                kwargs={'username': self.user2}))
        response = self.client.get(reverse('profile', kwargs={'username': self.user1}))
        self.assertEqual(response.context["follower_count"], 0)

    def test_feed(self):
        '''Проверка появления новой записи в ленте у подписсчика, но у дрегих пользователей лента
        должна оставаться пустой'''
        self.client.force_login(self.user1)
        self.client.get(reverse('profile_follow', kwargs={'username': self.user3.username}))
        response = self.client.get(reverse('follow_index'))
        print('hold')


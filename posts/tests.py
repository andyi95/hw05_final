import io

from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from PIL import Image

from .models import Comment, Follow, Group, Post, User


# Создали отдельный класс с общими методами
class Fixtures(TestCase):
    def check_post_from_page(self, urls, text, user, group):
        '''Отдельный метод для получения объекта поста из страниц сайта
            Достает пост из списка ссылок и передает его на дальнейшую
            проверку'''
        cache.clear()
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


    def check_equality(self, e_posts, text, user, group):
        '''Отдельный метод сверки всех полей, вывода соответсвующих
        сообщений об ошибках и получения поста на выходе'''
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
        self.assertEqual(e_post.author, user,
                         msg='Автор поста не соотвествует заданному')
        self.assertEqual(e_post.group, group,
                         msg='Сообщество поста не соответствует заданному')
        return e_post

    # Добавили метод для очистки всего ненужного ;)
    def tearDown(self):
        key = make_template_fragment_key('index')
        cache.delete(key)


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


class TestPostCreaton(Fixtures):
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

    def test_new_post_auth(self):
        '''В  следующем тесте создаем пост через HTTP и сверяем соответствие в
        БД'''
        response = self.client.post(reverse('new_post'),
                                    {
                                        'text': self.post_text,
                                        'group': self.group.id
                                    }, follow=True)
        self.assertRedirects(response, reverse('index'))
        posts = Post.objects.all()
        self.check_equality(posts, self.post_text, self.user, self.group)

    def test_post_display(self):
        '''Создаем пост в БД и сверяем отображение через http запросы к
        сайту'''
        post = Post.objects.create(text=self.post_text,
                                   group=self.group,
                                   author=self.user)
        urls = (
            reverse('index'),
            reverse('profile', args=[self.user.username]),
            reverse('group', args=[self.group.slug]),
            reverse('post', args=[self.user.username, post.pk]),
        )
        self.check_post_from_page(urls, self.post_text, self.user,
                                  self.group)

    def test_edit(self):
        '''Создаем пост в БД, редактируем через http и сверяем содержимое на
            всех
            связанных страницах'''
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

    def test_wrong_user_edit(self):
        '''Создаем пост через БД, далее логинимся под вторым пользователем и
            пытаемся изменить текст и сообщество через http,
            далее проверяем изменения в БД'''
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
        self.check_post_from_page(urls, self.post_text, self.user,
                                  self.group)
        # Убедимся, что у второго автора не появилось страницы с постом
        response = self.client.get(
            reverse('post', args=[self.user2.username, 1])
        )
        self.assertEqual(
            response.status_code, 404,
            msg='Страница создана, все пропало'
        )

    def test_cache(self):
        '''Проверка работы кэша - создаем пост и сразу смотрим, не появился ли
        он на главной странице'''
        # Загружаем в кэш главную страницу
        self.client.get(reverse('index'))
        self.post = Post.objects.create(
            text=self.post_text,
            author=self.user, group=self.group
        )
        response = self.client.get(reverse('index'))
        self.assertIsNone(response.context,
                          msg='Похоже, что кэширование не работает'
                          )


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


class ImageTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='HaroldFinch'
        )
        self.group = Group.objects.create(
            title='Person of Interest',
            slug='PoV'
        )
        self.post_text = 'The image test post'
        self.client.force_login(self.user)
        # Создаем картинку и сохраняем её в памяти в виде байт-кода
        img = Image.new('RGB', (300, 300), color='red')
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        self.small_img = buf.getvalue()

    def test_post_with_image(self):
        '''Проверка возможности загрузки изображений в посты и их
        отображения'''
        # Загружаем изображение и создаем пост в БД
        img = SimpleUploadedFile(
            name='small.jpeg',
            content=self.small_img,
            content_type='image/jpeg',
        )
        post = Post.objects.create(
            author=self.user,
            text=self.post_text,
            group=self.group,
            image=img,
        )
        urls = (
            reverse('index'),
            reverse('profile', args=[self.user.username]),
            reverse('group', args=[self.group.slug]),
            reverse('post', args=[self.user.username, post.pk]),
        )
        # Чистим кэш и проверяем наличие картинки на страницах сайта
        cache.clear()
        for url in urls:
            with self.subTest(url=url, msg='Изображение не найдено'
                                           ' на странице'):
                response = self.client.get(url)
                self.assertContains(
                    response,
                    '<img class="img-thumbnail"'
                )

    def test_wrong_file_type(self):
        '''Проверка возможности создания постов с загрузкой невалидных
        файлов'''
        wrong_image = SimpleUploadedFile(
            name='image.txt',
            content=b'asodjfewpjf39',
            content_type='image/jpeg',
        )
        response = self.client.post(
            reverse('new_post'),
            {
                'text': self.post_text,
                'group': self.group.id,
                'image': wrong_image
            }
        )
        self.assertContains(
            response,
            'alert',
            msg_prefix='Форма не вернула сообщение об ошибке'
        )
        posts = Post.objects.all()
        # Проверим, что сайт не позволил создать пост
        self.assertEqual(
            posts.count(), 0,
            msg='Форма создания поста позволяет загружать невалидные файлы'
        )

    # Подчищаем все ненужное
    def tearDown(self):
        key = make_template_fragment_key('index')
        cache.delete(key)


class TestFollow(TestCase):
    def setUp(self):
        self.client1 = Client()
        self.client2 = Client()
        self.client3 = Client()
        self.unauth_client = Client()
        self.user1 = User.objects.create_user(
            username='HaroldFinch'
        )
        self.client1.force_login(self.user1)
        self.user2 = User.objects.create_user(
            username='JohnReese'
        )
        self.client2.force_login(self.user2)
        self.user3 = User.objects.create_user(
            username='SamanthaGrooves'
        )
        self.client3.force_login(self.user3)

    def test_follow_auth(self):
        '''Проверка возможности авторизированному пользователю подписываться
        и отписываться от автора'''
        response = self.client1.get(
            reverse(
                'profile_follow',
                kwargs={'username': self.user2.username}
            ),
            follow=True
        )
        self.assertRedirects(
            response, reverse(
                'profile',
                args=[self.user2.username]
            )
        )
        # Проверяем, что HaroldFinch подписан на JohnJeese, а у JohnReese
        # Harold есть в подписках
        follow = Follow.objects.all()
        self.assertEqual(
            follow.count(), 1,
            'Количество подписок не соответсвует ожидаемому'
        )
        follow = follow.last()
        self.assertEqual(
            follow.author.id,
            self.user2.id,
            msg='Несоответствие автора'
        )
        self.assertEqual(
            follow.user.id,
            self.user1.id,
            msg='Несоответствие подписчика'
        )
        # Отписываемся
        self.client1.get(
            reverse('profile_unfollow', kwargs={'username': self.user2})
        )
        followers = Follow.objects.all()
        self.assertEqual(followers.count(), 0, 'Не удалось отписаться')

    def test_follow_unauth(self):
        '''Проверка поведение сервера в случае попытки неавторизованной
         подписки или отписки'''
        login_url = reverse('login')
        urls = (
            reverse(
                'profile_follow',
                kwargs={'username': self.user2.username}
            ),
            reverse(
                'profile_unfollow',
                kwargs={'username': self.user2.username}
            )
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.unauth_client.get(
                    url,
                    follow=True
                )
                target_url = f'{login_url}?next={url}'
                self.assertRedirects(
                    response,
                    target_url,
                    msg_prefix='Сервер вернул неожиданный ответ'
                )
                followers = Follow.objects.filter(author=self.user2.id)
                # Убеждаемся, что количество подписчиков не изменилось
                self.assertEqual(followers.count(), 0)

    def test_self_follow(self):
        '''Проверка невозможности подписки на самого себя'''
        self.client1.get(reverse('profile_follow', args=[self.user1.username]))
        # Убедимся, что количество подписчиков и подписок не изменилось
        followers = Follow.objects.filter(author=self.user1.id)
        self.assertEqual(
            followers.count(), 0,
            msg='Сайт позволяет подписаться на самого себя'
        )


class TestFeed(Fixtures):
    def setUp(self):
        self.client = Client()
        self.client2 = Client()
        self.client3 = Client()
        self.user1 = User.objects.create_user(
            username='HaroldFinch'
        )
        self.user2 = User.objects.create_user(
            username='JohnReese'
        )
        self.user3 = User.objects.create_user(
            username='SamanthaGrooves'
        )
        self.client.force_login(self.user1)
        self.client2.force_login(self.user2)
        self.client3.force_login(self.user3)
        self.group = Group.objects.create(
            title='Followed group',
            slug='followed_g'
        )
        self.post = Post.objects.create(
            text='Followed text', author=self.user2, group=self.group
        )

    def test_feed_followed(self):
        '''Проверка появления новой записи в ленте у подписсчика,
        но у других пользователей лента
        должна оставаться пустой'''
        self.client.get(
            reverse(
                'profile_follow',
                kwargs={'username': self.user2.username}
            )
        )
        urls = (
            reverse('follow_index'),
        )
        # Проверяем с помощью уже готового инструмента
        self.check_post_from_page(
            urls,
            self.post.text,
            self.user2,
            self.group
        )

    def test_feed_unfollowed(self):
        '''Проверка отсутсвия поста в ленте у неподписанного пользователя'''
        response = self.client3.get(reverse('follow_index'))
        paginator = response.context['paginator']
        if paginator is not None:
            self.assertEqual(
                paginator.count, 0,
                msg='Несоответствие количества записей'
                    'или Paginator работает некорректно'
            )
        else:
            self.assertIsNone(response.context['post'])


class TestComment(Fixtures):
    def setUp(self):
        # Создаем авторизованного и неавторизованного клиентов, тестовый пост
        self.client = Client()
        self.client2 = Client()
        self.user = User.objects.create_user(username='HaroldFinch')
        self.client.force_login(self.user)
        self.post = Post.objects.create(
            author=self.user,
            text='Leave your comment here'
        )
        self.comment_text = 'A test comment here'

    def test_comment_auth(self):
        '''Создание комментария через веб-морду нашего сайта и
        проверка валидности'''
        self.client.post(
            reverse('add_comment', args=[
                self.user.username,
                self.post.id
            ]), {'text': self.comment_text}
        )
        # Проверяем, появилась-ли запись в БД...
        comments = Comment.objects.filter(post_id=self.post.id)
        self.assertEqual(comments.count(), 1,
                         msg='Количество созданных комментариев не '
                             'соответсвует')
        comment = comments.last()
        self.assertEqual(comment.text, self.comment_text,
                         msg='Текст комментария в БД не найден либо сохранен '
                             'неверно')
        # Если выше все хорошо, то проверяем по полной
        # на странице поста
        response = self.client.get(
            reverse('post', args=[self.user.username, self.post.id])
        )
        comments = response.context['items']
        if hasattr(comments, 'query'):
            self.assertEqual(comments.count(), 1,
                             msg='Количество комментариев не соответствует '
                                 'заданным')
            e_post = comments.last()
        else:
            e_post = comments
        self.assertEqual(
            e_post.post, self.post,
            msg='Пост комментария не соответствует заданному'
        )
        self.assertEqual(
            e_post.text, self.comment_text,
            msg='Текст комментария не соотвествует заданному или отсутствует'
        )
        self.assertEqual(
            e_post.author, self.user,
            msg='Автор комментария не соотвествует заданному'
        )

    def test_comment_unauth(self):
        # Пытаемся написать комментарий неавторизовавшись на сайте
        self.client2.post(
            reverse(
                'add_comment', args=[self.user.username, self.post.id]
            ),
            {'text': 'This comment should not be here'}
        )
        # Проверяем, не попал-ли комментарий на сайт, проверки
        # через объект будет достаточно
        comment_count = Comment.objects.count()
        self.assertEqual(comment_count, 0,
                         msg='Сайт позволяет оставлять комментарии'
                             ' незарегистрированным пользователям')


class TestHTTPCodes(TestCase):
    def setUp(self):
        self.client = Client()

    def test_not_found(self):
        '''Проверка возвращаемых значений сервера для различных
         несуществующих страниц'''
        urls = (
            'somethingwrong',
            '256',
            'group/qwerty',
            'test/56',
            'test/56/edit'
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code, 404,
                    msg='Сервер вернул неожиданный код ответа')

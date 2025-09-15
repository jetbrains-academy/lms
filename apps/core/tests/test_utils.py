from core.utils import get_youtube_video_id, instance_memoize


def test_get_youtube_video_id():
    assert get_youtube_video_id('https://youtu.be/sxnSFdRECas') == 'sxnSFdRECas'
    assert get_youtube_video_id('https://youtu.be/sxnSFdRECas?v=42') == 'sxnSFdRECas'
    # Not a valid url btw
    assert get_youtube_video_id('https://youtu.be/sxnSFdRECas/what?') == 'sxnSFdRECas'
    assert get_youtube_video_id('youtu.be/sxnSFdRECas?') == 'sxnSFdRECas'
    assert get_youtube_video_id('https://ya.ru/watch?v=0lZJicHYJXM') is None
    assert get_youtube_video_id('https://youtube.com/watch?v=0lZJicHYJXM') == '0lZJicHYJXM'
    assert get_youtube_video_id('https://www.youtube.com/watch?v=0lZJicHYJXM') == '0lZJicHYJXM'
    assert get_youtube_video_id('youtube.com/embed/8SPq-9kS69M') == '8SPq-9kS69M'
    assert get_youtube_video_id('https://www.youtube-nocookie.com/embed/8SPq-9kS69M') == '8SPq-9kS69M'
    assert get_youtube_video_id('http://www.youtube.com/watch?v=0zM3nApSvMg#t=0m10s') == '0zM3nApSvMg'


def test_instance_memoize():
    class A:
        def __init__(self):
            self.counter = -1

        @instance_memoize
        def foo(self, i):
            self.counter += 1
            return self.counter + i

    a = A()
    assert not hasattr(a, "_instance_memoize_cache")
    assert a.foo(1) == 1
    assert len(a.__dict__["_instance_memoize_cache"]) == 1
    assert a.foo(1) == 1
    del a.__dict__["_instance_memoize_cache"]
    assert a.foo(1) == 2
    a.counter = 42
    assert a.foo(1) == 2
    del a.__dict__["_instance_memoize_cache"]
    assert a.foo(1) == 44
    assert A.foo(a, 1) == 45

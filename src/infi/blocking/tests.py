import unittest
import logging
import time
import os

from infi.blocking import make_blocking, Timeout

def hello_world():
    return 'hello world'

def fail():
    raise RuntimeError("epic fail")

def sleep(n):
    time.sleep(n)

def suicide():
    os.kill(os.getpid(), 9)

def log_exception():
    try:
        raise NotImplementedError()
    except:
        logging.getLogger(__name__).exception("what")

def nested(level, gevent_friendly):
    if level:
        return make_blocking(nested, gevent_friendly=gevent_friendly)(level-1, gevent_friendly)
    return gevent_friendly

class MyObject(object):
    def test(self):
        assert self.attribute == 'yes'


class Mixin(object):
    def test_hello_world(self):
        func = make_blocking(hello_world, gevent_friendly=self.gevent_friendly)
        result = func()
        assert result == 'hello world'

    def test_exception(self):
        func = make_blocking(fail, gevent_friendly=self.gevent_friendly)
        with self.assertRaises(RuntimeError):
            func()


    def test_timeout(self):
        func = make_blocking(sleep, timeout=0.1, gevent_friendly=self.gevent_friendly)
        with self.assertRaises(Timeout):
            func(10)

    def test_worker_died(self):
        func = make_blocking(suicide, timeout=1, gevent_friendly=self.gevent_friendly)
        with self.assertRaises(Timeout):
            func()

    def test_instancemethod(self):
        instance = MyObject()
        instance.attribute = 'yes'
        func = make_blocking(instance.test, timeout=1, gevent_friendly=self.gevent_friendly)
        func()

    def test_log_exception(self):
        make_blocking(log_exception, gevent_friendly=self.gevent_friendly)()

    def test_nested(self):
        func = make_blocking(nested, gevent_friendly=self.gevent_friendly)
        self.assertEqual(func(5, self.gevent_friendly), self.gevent_friendly)


class TestCase(unittest.TestCase, Mixin):
    gevent_friendly = False


class GeventTestCase(unittest.TestCase, Mixin):
    gevent_friendly = True

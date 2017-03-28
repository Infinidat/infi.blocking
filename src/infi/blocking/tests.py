import unittest
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

class TestCase(unittest.TestCase, Mixin):
    gevent_friendly = False


class GeventTestCase(unittest.TestCase, Mixin):
    gevent_friendly = True

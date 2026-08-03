import threading
import time

from model_lifetime import IdleModelHandle


def test_unloads_after_last_lease_becomes_idle():
    unloaded = threading.Event()
    handle = IdleModelHandle("test model", 0.02, unloaded.set)

    with handle.use():
        time.sleep(0.04)
        assert not unloaded.is_set()

    assert unloaded.wait(0.5)


def test_new_lease_cancels_pending_unload():
    unloaded = threading.Event()
    handle = IdleModelHandle("test model", 0.04, unloaded.set)

    with handle.use():
        pass
    time.sleep(0.02)
    with handle.use():
        time.sleep(0.03)
        assert not unloaded.is_set()

    assert unloaded.wait(0.5)


def test_manual_unload_refuses_while_in_use():
    unloads = []
    handle = IdleModelHandle("test model", 60, lambda: unloads.append(True))

    with handle.use():
        assert handle.unload_now() is False
    assert handle.unload_now() is True
    assert unloads == [True]

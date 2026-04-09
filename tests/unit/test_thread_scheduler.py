import src.thread_scheduler as thread_scheduler


class FakeTimer:
    instances = []

    def __init__(self, interval, func, args=None):
        self.interval = interval
        self.func = func
        self.args = tuple(args) if args is not None else ()
        self.daemon = False
        self.started = False
        self.canceled = False
        self.joined = False
        FakeTimer.instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.canceled = True

    def join(self):
        self.joined = True


def test_iterative_task_schedules_immediately(monkeypatch, mocker):
    FakeTimer.instances = []
    monkeypatch.setattr(thread_scheduler.threading, "Timer", FakeTimer)
    callback = mocker.Mock()

    task = thread_scheduler.ThreadIterativeTask(
        scheduler=thread_scheduler.ThreadScheduler(),
        interval_ms=200,
        func=callback,
    )

    timer = FakeTimer.instances[-1]
    assert task.is_running is True
    assert timer.started is True
    assert timer.daemon is True
    assert timer.interval == 0.2


def test_iterative_task_execute_runs_callback_and_reschedules(monkeypatch, mocker):
    FakeTimer.instances = []
    monkeypatch.setattr(thread_scheduler.threading, "Timer", FakeTimer)
    callback = mocker.Mock()

    task = thread_scheduler.ThreadIterativeTask(
        scheduler=thread_scheduler.ThreadScheduler(), interval_ms=150, func=callback
    )
    initial_count = len(FakeTimer.instances)

    task._execute()

    callback.assert_called_once()
    assert len(FakeTimer.instances) == initial_count + 1


def test_iterative_task_execute_logs_exception_and_reschedules(monkeypatch, mocker):
    FakeTimer.instances = []
    monkeypatch.setattr(thread_scheduler.threading, "Timer", FakeTimer)
    log_error = mocker.Mock()
    monkeypatch.setattr(thread_scheduler.logger, "error", log_error)

    def boom():
        raise RuntimeError("failure")

    task = thread_scheduler.ThreadIterativeTask(
        scheduler=thread_scheduler.ThreadScheduler(), interval_ms=100, func=boom
    )
    initial_count = len(FakeTimer.instances)

    task._execute()

    assert log_error.call_count == 1
    assert len(FakeTimer.instances) == initial_count + 1


def test_iterative_task_cancel_stops_and_joins_timer(monkeypatch, mocker):
    FakeTimer.instances = []
    monkeypatch.setattr(thread_scheduler.threading, "Timer", FakeTimer)

    task = thread_scheduler.ThreadIterativeTask(
        scheduler=thread_scheduler.ThreadScheduler(),
        interval_ms=120,
        func=mocker.Mock(),
    )
    timer = task._timer

    task.cancel(wait=True)

    assert task.is_running is False
    assert timer.canceled is True
    assert timer.joined is True
    assert task._timer is None


def test_iterative_task_set_interval_replaces_timer(monkeypatch, mocker):
    FakeTimer.instances = []
    monkeypatch.setattr(thread_scheduler.threading, "Timer", FakeTimer)

    task = thread_scheduler.ThreadIterativeTask(
        scheduler=thread_scheduler.ThreadScheduler(),
        interval_ms=100,
        func=mocker.Mock(),
    )
    first_timer = task._timer

    task.set_interval(250)

    assert first_timer.canceled is True
    assert task.get_interval() == 250
    assert task._timer is not None
    assert task._timer.started is True
    assert task._timer.interval == 0.25


def test_thread_scheduler_set_timeout_creates_and_starts_timer(monkeypatch, mocker):
    FakeTimer.instances = []
    monkeypatch.setattr(thread_scheduler.threading, "Timer", FakeTimer)
    callback = mocker.Mock()

    scheduler = thread_scheduler.ThreadScheduler()
    timer = scheduler.set_timeout(500, callback, "a", "b")

    assert timer.started is True
    assert timer.daemon is True
    assert timer.interval == 0.5
    assert timer.args == ("a", "b")

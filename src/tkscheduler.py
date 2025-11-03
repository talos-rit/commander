from tkinter import Tk


class IterativeTask:
    root: Tk
    running = True

    def __init__(self, root: Tk, ms, func, *args):
        self.root = root
        self.iterative_call(int(ms), func, *args)

    def iterative_call(self, ms, func, *args):
        self.root.after(ms, func, *args)
        if self.running:
            self.root.after(ms, self.iterative_call, ms, func, *args)

    def cancel(self):
        self.running = False


class Scheduler:
    def __init__(self, root: Tk):
        self.root = root

    def set_timeout(self, ms, func, *args):
        self.root.after(int(ms), func, *args)

    def set_interval(self, ms, func, *args):
        return IterativeTask(self.root, int(ms), func, *args)

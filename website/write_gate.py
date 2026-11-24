"""Fair in-process writer admission for the single-host SQLite deployment."""
from threading import Condition

class WriteGate:
    def __init__(self):
        self.condition=Condition()
        self.next_ticket=0
        self.serving=0

    def acquire(self):
        with self.condition:
            ticket=self.next_ticket
            self.next_ticket+=1
            self.condition.wait_for(lambda:self.serving==ticket)

    def release(self):
        with self.condition:
            self.serving+=1
            self.condition.notify_all()

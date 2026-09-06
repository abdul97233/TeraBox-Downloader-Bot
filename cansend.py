import time


class CanSend:
    def __init__(self, interval=2):
        self.interval = interval
        self.last_send_time = time.time() - 10

    def can_send(self):
        current_time = time.time()
        if current_time - self.last_send_time >= self.interval:
            self.last_send_time = current_time
            return True
        return False

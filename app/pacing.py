"""Explicit experimental cadence; zero retains the original renderer loop."""
class Pacer:
    def __init__(self,fps):
        if not isinstance(fps,(int,float)) or not (fps==0 or 1<=fps<=60):raise ValueError('fps must be 0 or 1..60')
        self.interval=1/fps if fps else 0;self.next=0
    def due(self,now):return self.interval==0 or now>=self.next
    def mark(self,now):self.next=now+self.interval
    def delay(self,now):return max(0,self.next-now)

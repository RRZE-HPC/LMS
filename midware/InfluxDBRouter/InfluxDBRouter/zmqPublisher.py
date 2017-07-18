#!/usr/bin/env python

import sys, re

zmq = None
try:
    import zmq as zeromq
    zmq = zeromq 
except ImportError:
    sys.stderr.write("Cannot load ZeroMQ.\n")

class ZMQPublisher(object):
    def __init__(self, bindhost, bindport, filter=".*", proto="tcp"):
        self.bindhost = bindhost
        if self.bindhost == "localhost":
            self.bindhost = "127.0.0.1"
        self.bindport = bindport
        self.proto = proto
        self.filter = re.compile(filter)
        self.context = None
        self.socket = None
        self.started = False
        self.url = "%s://%s:%s" % (self.proto, self.bindhost, str(self.bindport))
    def start(self):
        if zmq and not self.context:
            print("Start ZMQPublisher %s" % self.url)
            self.context = zmq.Context()
            self.socket = self.context.socket(zmq.PUB)
            try:
                self.socket.bind(self.url)
            except Exception as e:
                print("Bind to %s failed %s" % (self.url, str(e),))
                self.socket = None
                self.context = None
            self.started = True
    def pub_metric(self, m):
        if self.socket and self.started and self.filter.match(str(m)):
            self.socket.send(str(m))

    def term(self):
        print("Close ZMQPublisher %s" % self.url)
        if self.socket:
           self.socket.close()
           self.socket = None
        if self.context:
            self.context.term()
            self.context = None
    def is_alive(self):
        return self.context and self.socket


if __name__ == "__main__":
    import os
    p = ZMQPublisher("localhost", 8091)
    p.start()
    p.pub_metric("test")
    os.system("netstat -a -n | grep LISTEN")
    p.close()

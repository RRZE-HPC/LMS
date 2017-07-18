#!/usr/bin/env python

import zmq
from measurement import InfluxDBMeasurement
from ConfigParser import SafeConfigParser

def parse_interval(interval):
    if isinstance(interval, int) or isinstance(interval, float):
        return int(interval)
    if isinstance(interval, str):
        if interval[-1] == "s":
            return int(interval[:-1])
        elif interval[-1] == "m":
            return int(interval[:-1])*60
        elif interval[-1] == "h":
            return int(interval[:-1])*3600
        elif interval[-1] == "d":
            return int(interval[:-1])*86400
    return None

class JobMonitor(object):
    def __init__(self, configfile):
        self.configfile = configfile
        self.config = None

        self.filter = None
        self.stat_attr = None
        self.hostname = "localhost"
        self.port = 8091
        self.protocol = "tcp"
        self.stat_start = None
        self.stat_end = None
        self.interval = None

        self.terminate = False
        self.context = None
        self.socket = None
    def read_config(self, configfile=None):
        self.config = None
        if configfile and os.path.exists(configfile):
            self.config = SafeConfigParser()
            fp = open(configfile, "r")
            self.config.readfp(fp)
            fp.close()
        if not c and os.path.exists(self.configfile):
            self.config = SafeConfigParser()
            fp = open(self.configfile, "r")
            self.config.readfp(fp)
            fp.close()
        defs = self.config.defaults()
        if "hostname" in defs:
            self.hostname = defs["hostname"]
        if "port" in defs:
            self.port = int(defs["port"])
        if "protocol" in defs and defs["protocol"] in ("tcp", "udp"):
            self.protocol = defs["protocol"]
        if "status_attr" in defs:
            self.status_attr = defs["status_attr"]
        if "filter" in defs and len(defs["filter"]) > 0:
            self.filter = defs["filter"]
        if "create_at_status" in defs:
            self.stat_start = defs["create_at_status"]
        if "delete_at_status" in defs:
            self.stat_end = defs["delete_at_status"]
        if "update_inverval" in defs:
            i = parse_interval(defs["update_inverval"])
            if i:
                self.interval = i
    def connect(self, configfile=None):
        if not self.config:
            self.read_config(configfile=configfile)
        addr = "%s://%s:%s" % (self.protocol, self.hostname, str(self.port))
        if not self.context:
            self.context = zmq.Context()
        if not self.socket:
            self.socket = context.socket(zmq.SUB)
            self.socket.connect(addr)
            if self.filter and len(self.filter) > 0:
                self.socket.setsockopt(zmq.SUBSCRIBE, self.filter)
    def disconnect(self):
        if self.socket:
            self.socket.close()
        if self.context:
            self.context.term()
    def recv_loop(self, configfile=None):
        if not self.config:
            self.read_config(configfile=configfile)
        if not self.context:
            self.connect()
        
        interval = self.interval
        while not self.terminate:
            try:
                s = socket.recv(flags=zmq.NOBLOCK)
            except zmq.Again as e:
                time.sleep(1)
                interval -= 1
                if interval == 0:
                    self.update()
                    interval = self.interval
            except KeyboardInterrupt:
                break
            m = Measurement(s)
            stat = m.get_attr(self.stat_attr)
            if stat == self.stat_start:
                self.start()
            elif stat == self.stat_end:
                self.finish()
        self.disconnect()
    def update(self):
        pass
    def start(self):
        pass
    def stop(self):
        pass

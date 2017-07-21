#!/usr/bin/env python

import zmq, re, os, os.path, time
from influxdbmeasurement import Measurement
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

        self.filter = []
        self.stat_attr = None
        self.hostname = "localhost"
        self.port = 8091
        self.protocol = "tcp"
        self.stat_start = None
        self.stat_end = None
        self.interval = 300

        self.terminate = False
        self.context = None
        self.socket = None
    def read_def_config(self, configfile=None):
        self.config = None
        if configfile and os.path.exists(configfile):
            self.config = SafeConfigParser()
            fp = open(configfile, "r")
            self.config.readfp(fp)
            fp.close()
        if not self.config and os.path.exists(self.configfile):
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
            self.filter = re.split("\s*,\s*", str(defs["filter"]))
        if "create_at_status" in defs:
            self.stat_start = defs["create_at_status"]
        if "delete_at_status" in defs:
            self.stat_end = defs["delete_at_status"]
        if "update_interval" in defs:
            i = parse_interval(defs["update_interval"])
            if i:
                self.interval = i
    def read_config(self, configfile=None):
        self.read_def_config(configfile=configfile)
    def connect(self, configfile=None):
        if not self.config:
            self.read_config(configfile=configfile)
        addr = "%s://%s:%s" % (self.protocol, self.hostname, str(self.port))
        if not self.context:
            self.context = zmq.Context()
        if not self.socket:
            self.socket = self.context.socket(zmq.SUB)
            self.socket.connect(addr)
            if self.filter and len(self.filter) > 0:
                newfilter = []
                for f in self.filter:
                    if not f.startswith("*"):
                        self.socket.setsockopt(zmq.SUBSCRIBE, f)
                    else:
                        newfilter.append(f)
                self.filter = newfilter
            else:
                self.socket.setsockopt(zmq.SUBSCRIBE, "")
    def disconnect(self):
        if self.socket:
            self.socket.close()
        if self.context:
            self.context.term()
    def _filter(self, str_m):
        match = True
        for f in self.filter:
            if f not in str_m:
                match = False
        return match
    def recv_loop(self, configfile=None):
        if not self.config:
            self.read_config(configfile=configfile)
        if not self.context:
            self.connect()

        interval = self.interval
        while not self.terminate:
            s = None
            try:
                s = self.socket.recv(flags=zmq.NOBLOCK)
            except zmq.Again as e:
                time.sleep(1)
                interval -= 1
                if interval == 0:
                    self.update()
                    interval = self.interval
            except KeyboardInterrupt:
                break
            if s and self._filter(s):
                m = Measurement(s)
                if self.stat_attr:
                    stat = m.get_attr(self.stat_attr)
                    if stat:
                        if stat == self.stat_start:
                            self.start(m)
                        elif stat == self.stat_end:
                            self.finish(m)
                self.get(m)
        self.disconnect()
    def update(self):
        pass
    def start(self, m):
        pass
    def stop(self, m):
        pass
    def get(self, m):
        pass

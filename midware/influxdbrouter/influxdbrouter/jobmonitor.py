#!/usr/bin/env python

import zmq, re, os, os.path, time
from influxdbmeasurement import Measurement
from ConfigParser import SafeConfigParser
from optparse import OptionParser
import logging, datetime

def parse_interval(interval):
    """
    Parse string like 1m or 2h into seconds. Used when parsing the config file.
    """
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
    """
    Class that subscribes to a ZeroMQ publisher (with filtering) and calls functions
    based on a status attribute in the received InfluxDB measurement. An update
    function is called periodically. The configuration is read from file.
    """
    def __init__(self, configfile):
        """
        Create a new JobMonitor. It takes the configfile as input but it can be overwritten
        later when reading in the configuration.
        """
        self.configfile = configfile
        self.config = None

        self.filter = []
        self.status_attr = None
        self.hostname = "localhost"
        self.port = 8091
        self.protocol = "tcp"
        self.stat_start = None
        self.stat_end = None
        self.interval = 300

        self.terminate = False
        self.context = None
        self.socket = None
        self.stat_funcs = {}
    
    def add_stat_func(self, status, fptr):
        """
        Add a function that should be called at a specific value of the
        status attribute. This allows to create new callbacks. Already
        existing mappings are overwritten.
        """
        self.stat_funcs[status] = fptr
        
    def read_def_config(self, configfile=None):
        """
        Read in the basic configuration of a JobMonitor including hostname and
        port of the ZeroMQ publisher and the attribute name and values to call
        the start and stop function.
        """
        self.config = None
        loglevel = logging.ERROR
        logfile = None
        
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
        defs = dict(self.config.defaults())
        if "hostname" in defs:
            self.hostname = defs["hostname"]
        if "port" in defs:
            self.port = int(defs["port"])
        if "protocol" in defs and defs["protocol"] in ("tcp", "udp"):
            self.protocol = defs["protocol"]
        if "status_attr" in defs:
            self.status_attr = defs["status_attr"]
        if "filter" in defs and len(defs["filter"]) > 0:
            # Split up the filters. At connect the subscribtion strings
            # that are added the ZeroMQ are filtered out
            self.filter = re.split("\s*,\s*", str(defs["filter"]))
        if "start_at_status" in defs:
            self.stat_funcs[defs["start_at_status"]] = self.start
        if "stop_at_status" in defs:
            self.stat_funcs[defs["stop_at_status"]] = self.stop
        if "update_interval" in defs:
            i = parse_interval(defs["update_interval"])
            if i:
                self.interval = i
            else:
                logging.warn("Cannot read update interval from config file")
        if "loglevel" in defs:
            numeric_level = getattr(logging, defs["loglevel"].upper(), None)
            if not isinstance(numeric_level, int):
                raise ValueError('Invalid log level: %s' % defs["loglevel"])
            else:
                loglevel = numeric_level
        if "logfile" in defs:
            if os.path.exists(os.path.dirname(os.path.abspath(defs["logfile"]))):
                logfile = defs["logfile"]
        if logfile:
            logging.basicConfig(filename=logfile, level=loglevel)
    
    def connect(self, configfile=None):
        """
        Connect the ZeroMQ publisher and apply subscribtion strings filtering
        the beginning of the received string. All strings matching tags and 
        fields are tested for each string at reception.
        """
        if not self.config:
            self.read_config(configfile=configfile)
        addr = "%s://%s:%s" % (self.protocol, self.hostname, str(self.port))
        logging.info("Subscribing to %s" % addr)
        if not self.context:
            logging.debug("Open ZeroMQ context")
            self.context = zmq.Context()
        if not self.socket:
            logging.debug("Open ZeroMQ socket")
            self.socket = self.context.socket(zmq.SUB)
            self.socket.connect(addr)
            logging.debug("Subscribing to ZeroMQ")
            if self.filter and len(self.filter) > 0:
                newfilter = []
                for f in self.filter:
                    if not f.startswith("*"):
                        logging.debug("Add filter: %s" % str(f))
                        self.socket.setsockopt(zmq.SUBSCRIBE, f)
                    else:
                        newfilter.append(f.replace("*", ""))
                self.filter = newfilter
            else:
                logging.debug("Subscribe to everything")
                self.socket.setsockopt(zmq.SUBSCRIBE, "")
    def disconnect(self):
        """
        Disconnect from the ZeroMQ publisher
        """
        if self.socket:
            logging.debug("Close ZeroMQ socket")
            self.socket.close()
        if self.context:
            logging.debug("Close ZeroMQ context")
            self.context.term()
    def _filter(self, str_m):
        """
        Apply filter strings that match not the beginning of the string.
        """
        match = True
        for f in self.filter:
            if f not in str_m:
                match = False
        return match
    def recv_loop(self, configfile=None):
        """
        This is the main loop receiving data and calling functions. First it calls
        the read_config function if not done previously. Afterwards it connects the
        ZeroMQ publisher.
        The reception is non-blocking. If nothing is received, the JobMonitor sleeps
        for a second. This is no problem since ZeroMQ queues the strings.
        Each loop checks whether it is time to call the update function.
        If the filter applies, it is analyzed for the status attribute and if it exists,
        the value is checked whether a function is registered for it and finally calls it.
        """
        if not self.config:
            self.read_config(configfile=configfile)
        if not self.context:
            self.connect()

        updatetime = datetime.datetime.now() + datetime.timedelta(seconds=self.interval)
        while not self.terminate:
            s = None
            try:
                s = self.socket.recv(flags=zmq.NOBLOCK)
            except zmq.Again as e:
                time.sleep(1)
            except KeyboardInterrupt:
                self.terminate = True
                pass
            if not self.terminate:
                if datetime.datetime.now() > updatetime:
                    logging.debug("Calling update function")
                    self.update()
                    updatetime = datetime.datetime.now() + datetime.timedelta(seconds=self.interval)
                if s and self._filter(s):
                    logging.debug("Received string: %s" % s)
                    m = Measurement(s)
                    if self.status_attr:
                        logging.debug("Checking status_attr: %s" % self.status_attr)
                        stat = m.get_attr(self.status_attr)
                        if stat:
                            for key in self.stat_funcs:
                                if key == stat:
                                    logging.debug("Calling %s function" % key)
                                    self.stat_funcs[key](m)
                    self.get(m)
        self.disconnect()
    def read_config(self, configfile=None):
        """
        Read in the configuration from file. This function can be overloaded but
        the first call must be "self.read_def_config(configfile=configfile)" to
        get the default parameters.
        """
        self.read_def_config(configfile=configfile)
    def update(self):
        """
        This function is called at every time the update interval is passed.
        """
        pass
    def start(self, m):
        """
        This function is called at every time the status attribute value matches
        start_at_status config option.
        """
        pass
    def stop(self, m):
        """
        This function is called at every time the status attribute value matches
        stop_at_status config option.
        """
        pass
    def get(self, m):
        """
        This function is called for each received and filtered measurement.
        """
        pass

def main():
    parser = OptionParser()
    parser.add_option("-c", "--config", dest="configfile", help="Configuration file", default=sys.argv[0]+".conf", metavar="FILE")
    (options, args) = parser.parse_args()
    mymon = JobMonitor(configfile=options.configfile)
    try:
        mymon.recv_loop()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()

#!/usr/bin/env python


import time, sys, os, re
import xml.sax
from Queue import Queue
import threading
import urllib2

global stop
stop = False

# Read data from this host
remote_host = 'jobscheduler'
remote_port = 8649
remote_timeout = 10
read_chunks = 1000

# Write data to this database
db_host = 'testhost'
db_port = 8086
db_user = 'testuser'
db_pass = 'testpass'
db_name = "testdatabase"
db_batch = 100
db_timeout = 10

# Filter metric names
metricfilter = re.compile(".*")



# Global list required to add metrics inside XML Stream reader and use it
# in the end to send everthing remaining in list
global db_batchlist
db_batchlist = []




def db_url():
    url = "http://"
    if len(db_user) > 0:
	url += str(db_user)
	if len(db_pass) > 0:
	    url += ":"+str(db_pass)+"@"
    url += "%s:%s/write?db=%s" % (db_host, str(db_port),str(db_name),)
    return url


def send(metriclist, force=False):
    global db_batchlist
    if len(metriclist) + len(db_batchlist) < db_batch and not force:
	db_batchlist += metriclist
    elif len(metriclist) + len(db_batchlist) > 0:
        url = db_url()
        cmd = "curl -m %s -f -XPOST '%s' --data-binary '%s'" % (db_timeout, url, "\n".join(db_batchlist + metriclist),)
        ret = os.system(cmd)
	db_batchlist = []



class StreamHandler(xml.sax.handler.ContentHandler):
    def __init__(self):
        self.lastStamp = None
        self.lastHostTags = None
        self.lastMetric = None
        self.lastMetricTags = None
        self.lastValue = None
        self.lastExtras = None
        self.url = db_url()

    def cast(self, s):
        """Cast input to number or if input is a non-number string, add " around it"""
        try:
            s = int(s)
        except:
            try:
                s = float(s)
            except:
                s = "\"%s\"" % str(s)
            return s

    def startElement(self, name, attrs):
        attrnames = attrs.getNames()
        # HOST tags contains hostname, ip address and timestamp
        if name == 'HOST':
            self.lastHostTags = {}
            if 'NAME' in attrnames:
                self.lastHostTags.update({"hostname" : attrs.getValue('NAME')})
            if 'IP' in attrnames:
                self.lastHostTags.update({"ip" : attrs.getValue('IP')})
            if 'REPORTED' in attrnames:
                self.lastStamp = attrs.getValue('REPORTED')
        # METRIC tags contains metric name, metric value and partly a metric unit
        elif name == 'METRIC':
            self.lastMetricTags = {}
            if 'NAME' in attrnames:
                # InfluxDB is not happy with '.' in metric names, so replace
                # it with '_'
                self.lastMetric = attrs.getValue('NAME').replace(".","_")
            if 'VAL' in attrnames:
                self.lastValue = self.cast(attrs.getValue('VAL'))
            if 'UNITS' in attrnames:
                u = attrs.getValue('UNITS')
                # Store unit only if not empty
                if len(u.strip()) > 0:
                    self.lastMetricTags.update({"unit" : u.strip()})
        # EXTRA_ELEMENT tags contain additional data for a metric. We just take
        # the group and the spoof host (e.g. network switch address)
        elif name == 'EXTRA_ELEMENT':
            if 'NAME' in attrnames:
                if attrs.getValue('NAME') == 'GROUP':
                    self.lastMetricTags.update({"group" : attrs.getValue('VAL')})
                elif attrs.getValue('NAME') == 'SPOOF_HOST':
                    self.lastMetricTags.update({"spoof_host" : attrs.getValue('VAL')})

    def endElement(self, name):
        if name == 'HOST':
            self.lastHostTags = None
            self.lastStamp = None
        elif name == 'METRIC':
            # All data for the metric was collected, put it into queue
            s = self.lastMetric
	    if metricfilter.search(s):
                v = self.lastValue
                t = self.lastStamp
                tags = ["%s=\"%s\"" % (k,self.lastHostTags[k],) for k in self.lastHostTags ]
                tags += ["%s=\"%s\"" % (k,self.lastMetricTags[k],) for k in self.lastMetricTags ]
		send(["%s,%s value=%s %d" % (s, ",".join(tags), v, int(t)*1E9)])
        elif name == 'GANGLIA_XML':
	    send([], force=True)
            raise StopIteration

    def characters(self, content):
        pass



if __name__ == '__main__':
    parser = xml.sax.make_parser()
    parser.setContentHandler(StreamHandler())
    url = "http://%s:%s" % (remote_host, str(remote_port),)
    try:
	# Open source URL
        resp = urllib2.urlopen(url, timeout=remote_timeout)
    except Exception as e:
        print("Cannot open URL %s: %s" % (url, e,))
        sys.exit(1)
    while True:
        try:
            # Read data in chunks and feed it to the parser
            buf = resp.read(read_chunks)
            if buf:
                try:
                    parser.feed(buf)
                except StopIteration:
                    break
        except:
	    # If reading fails, check if we need to send something remain in list
	    send([], force=True)
            break

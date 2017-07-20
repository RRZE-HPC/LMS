#!/usr/bin/env python

import os, sys, os.path, socket
import time, logging, datetime
import unicodedata
import re, json, logging, copy

from optparse import OptionParser

# Class to daemonize this process
from daemon import Daemon

# Used for receiving
# ThreadingMixIn is used to create a thread per data packet
from SocketServer import ThreadingMixIn
from BaseHTTPServer import HTTPServer
from BaseHTTPServer import BaseHTTPRequestHandler
from urlparse import urlparse

# Used for sending
import urllib2
# Main data structure to hold the measurements
# The data store has a lock which is only used when adding
# of deleting a queue which represents a database connection
from Queue import Queue
from threading import Lock

# Parse config file
from ConfigParser import SafeConfigParser

# Class which represents a measurement
from influxdbmeasurement import Measurement
# Class which holds the tags
from tagstore import Tagger
# Publish data through an ZMQ publisher
from zmqPublisher import ZMQPublisher


daemon = None

def handle_signal(sig):
    """Signal handler, sends all outstanding measurements to all databases."""
    if daemon:
        if daemon.receiver:
            while daemon.receiver.store.send_required():
                daemon.receiver.store.send_all()

def cast_bool(v):
    if isinstance(v, str):
        if v.lower() in ("true", "yes", "y"):
            return True
        return False
    elif isinstance(v, int):
        if v != 0: return True
        return False
    return False

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        pass

    try:
        unicodedata.numeric(s)
        return True
    except (TypeError, ValueError):
        pass

    return False

def get_influx_values(data):
    """
    When you query the influxdb, you receive the data in a JSON object. This function
    converts it to a list of dicts mainly used to get the list of databases.
    """
    if isinstance(data, str):
        data = json.loads(data)
    out = []
    if "results" in data:
        for r in data["results"]:
            if "series" in r:
                for s in r["series"]:
                    cols = []
                    if "columns" in s:
                        for c in s["columns"]:
                            cols.append(c)
                    if "values" in s:
                        for v in s["values"]:
                            d = {}
                            for i,c in enumerate(cols):
                                d[c] = v[i]
                            out.append(d)
    return out


class MeasurementStore(object):
    """
    Storage and sender for the measurements. The measurements are stored
    per database and sends the data can be send by multiple threads
    simultaneously.
    """
    def __init__(self, config):
        """
        Read timeout and database configurations from config object
        """
        self.config = config
        self.buffer = {}
        self.addtimes = {}
        self.active_keys = []
        self.lock = Lock()


        self.timeout = 600
        if self.config.has_section("CacheConfig"):
            if self.config.has_option("CacheConfig", "timeout"):
                self.timeout = self.config.getint("CacheConfig", "timeout")

        self.oldest = None
        self.batch_ready = Queue()

        self.send_in_progress = False
        self.heads = {"Content-Type" : "application/octet-stream"}
        self.dbs = {}
        self.db_hosts = {}
        self.def_db_host = { "hostname" : "localhost",
                             "port" : 8086,
                             "username" : "testuser",
                             "password" : "testpass",
                             "maxsend" : 1000,
                             "batch" : 10,
                             "maxcache" : 2000,
                             "timeout" : 10,
                             "maxdbs" : 1000,
                             "activedbs" : [],
                             "exclude" : "",
                             "create_db" : False}

        self.read_db("AdminDB")
        if self.config.has_section("SplitConfig"):
            if self.config.has_option("SplitConfig", "dbentries"):
                l_dbentries = re.split("\s*,\s*", self.config.get("SplitConfig", "dbentries"))
                for db in l_dbentries:
                    splitdb = "SplitDB-%s" % db
                    self.read_db(splitdb)

    def select_db_host(self, dbname):
        """
        Select the host for the database. If it is already assigned, it uses the same host.
        If not, the list of databases of all hosts are read to check if it already exists.
        Finally, it tries to create the database on the host with the minimal load of databases.
        """
        # If the database is already known and registered, return database host
        # identifier
        if dbname in self.dbs:
            return self.dbs[dbname]

        # If the database is not registered, check all database hosts, whether
        # a database with the same name exists
        for h in self.db_hosts:
            data = self._get_databases(h)
            for db in data:
                if db["name"] == dbname:
                    return h

        # If it is a complete new database, check the fill state of all hosts
        # and get the minimal loaded one.
        # The database is created afterwards and the database registered for the
        # database host.
        min_host_load = 100.0
        min_host = None
        for name in self.db_hosts:
            if self.db_hosts[name]["create_db"]:
                load = float(len(self.db_hosts[name]["activedbs"]))/self.db_hosts[name]["maxdbs"]
                if load < min_host_load:
                    min_host_load = load
                    min_host = name
        if min_host_load == 100.0:
            logging.error("All database hosts filled with databases or none allows the creation of new databases")
            return None

        # Create the database
        if min_host:
            url = "http://%s:%s/query?q=create+database+%s" % (self.db_hosts[min_host]["hostname"], str(self.db_hosts[min_host]["port"]), dbname)
            req = urllib2.Request(url, headers=self.heads)
            resp = None
            try:
                resp = urllib2.urlopen(req)
            except urllib2.URLError as e:
                logging.error("Cannot retrieve list of databases from %s" % name)
            if resp:
                resp.close()
        return min_host

    def _get_databases(self, dbhost):
        url = "http://%s:%s/query?q=show+databases" % (self.db_hosts[dbhost]["hostname"], str(self.db_hosts[dbhost]["port"]))
        req = urllib2.Request(url, headers=self.heads)
        resp = None
        data = {}
        try:
            resp = urllib2.urlopen(req)
        except urllib2.URLError as e:
            logging.error("Cannot retrieve list of databases from %s" % dbhost)
        if resp:
            data = get_influx_values(resp.read())
            resp.close()
        return data

    def update_db(self, name):
        data = self._get_databases(name)
        for db in data:
            if db["name"] not in self.db_hosts[name]["exclude"] and db["name"] not in self.db_hosts[name]["activedbs"]:
                self.db_hosts[name]["activedbs"].append(db["name"])
                self.dbs[db["name"]] = name
    def read_db(self, name):
        if self.config.has_section(name):
            if name not in self.db_hosts:
                newdb = copy.deepcopy(self.def_db_host)
                for k in newdb:
                    if self.config.has_option(name, k):
                        newdb[k] = self.config.get(name, k)
                newdb["maxsend"] = int(newdb["maxsend"])
                newdb["batch"] = int(newdb["batch"])
                newdb["maxcache"] = int(newdb["maxcache"])
                newdb["timeout"] = int(newdb["timeout"])
                newdb["port"] = int(newdb["port"])
                newdb["maxdbs"] = int(newdb["maxdbs"])
                newdb["exclude"] = re.split("\s*,\s*", newdb["exclude"])
                self.db_hosts[name] = newdb
            self.update_db(name)


    def send_required(self):
        close_q = datetime.datetime.now() - datetime.timedelta(seconds=self.timeout)
        for key in self.dbs:
            if key in self.buffer and self.buffer[key].empty() and self.addtimes[key] < close_q:
                self.lock.acquire()
                dbhost = self.dbs[key]
                if key in self.active_keys:
                    self.active_keys.remove(key)
                del self.addtimes[key]
                del self.dbs[key]
                del self.buffer[key]
                self.db_hosts[dbhost]["activedbs"].remove(key)
                self.lock.release()
        if len(self.active_keys) > 0:
            for key in self.active_keys:
                if self.buffer[key].qsize() >= self.db_hosts[self.dbs[key]]["batch"]:
                    return True
                else:
                    timeout = datetime.datetime.now() - datetime.timedelta(seconds=self.db_hosts[self.dbs[key]]["timeout"])
                   # logging.info(self.addtimes[key], timeout, self.buffer[key].empty())
                    if self.addtimes[key] < timeout and not self.buffer[key].empty():
                        return True
        return False

    def add(self, m):
        key = m.get_meta("db")
        if key not in self.buffer:
            dbhost = self.select_db_host(key)
            self.lock.acquire()
            if key not in self.buffer:
                logging.info("Creating new Queue for key '%s' with max size %d" % (key, self.db_hosts[dbhost]["maxcache"],))
                self.buffer[key] = Queue(maxsize=self.db_hosts[dbhost]["maxcache"])
                self.dbs[key] = dbhost
                if key not in self.db_hosts[dbhost]["activedbs"]:
                    self.db_hosts[dbhost]["activedbs"].append(key)
                self.addtimes[key] = None
                if key not in self.active_keys:
                    self.active_keys.append(key)
            self.lock.release()
        if self.buffer[key].full():
            logging.info("Buffer for key '%s' full, trying to send some measurements" % (key,))
            self.send(key)
        if self.buffer[key].empty():
            self.addtimes[key] = datetime.datetime.now()
        self.buffer[key].put(m)
        if self.buffer[key].qsize() > self.db_hosts[self.dbs[key]]["batch"]:
            self.batch_ready.put(key)
    def send(self, key, batch=0):
        sendlist = []
        delkeys = []
        if key not in self.dbs:
            dbhost = self.select_db_host(key)
        else:
            dbhost = self.dbs[key]
        if batch == 0:
            batch = self.db_hosts[dbhost]["batch"]
        items = 0
        if key not in self.buffer:
            logging.info("No store available for key '%s'" % key)
            return
        while not self.buffer[key].empty() and items < batch:
            sendlist.append(str(self.buffer[key].get()))
            items += 1
        if items == 0:
            return
        hostname = self.db_hosts[self.dbs[key]]["hostname"]
        port = self.db_hosts[self.dbs[key]]["port"]
        url = "http://%s:%s/write?db=%s" % (hostname, str(port), key)
        req = urllib2.Request(url, "\n".join(sendlist), headers=self.heads)
        logging.info("Send %d metrics to %s" % (len(sendlist), url,))
        try:
            resp = urllib2.urlopen(req)
            resp.close()
        except urllib2.URLError as e:
            logging.info("\n".join(sendlist))
            logging.info("ERROR")
            logging.info(e)
            for si in sendlist:
                req = urllib2.Request(url, si, headers=self.heads)
                try:
                    resp = urllib2.urlopen(req)
                    resp.close
                except:
                    logging.info("Cannot send measurement to %s:\n%s" % (url,si))
                    pass
        if self.buffer[key].empty():
            self.lock.acquire()
            for key in delkeys:
                del self.buffer[key]
                del self.addtimes[key]
                self.active_keys.remove(key)
            self.lock.release()
    def send_all(self):
        while not self.batch_ready.empty():
            key = self.batch_ready.get()
            self.send(key, batch=self.db_hosts[self.dbs[key]]["batch"])
    def get_db_hosts(self):
        out = {}
        for name in self.db_hosts:
            out[name] = {}
            for entry in self.db_hosts[name]:
                if entry not in ("password", "exclude"):
                    out[name][entry] = self.db_hosts[name][entry]
        return out

class InfluxReceiver(ThreadingMixIn, HTTPServer, object):
    def __init__(self, config, server_address, RequestHandlerClass):
        self.timeout = 1
        request_queue_size = 100
        self.config = config
        self.data_queue = None
        self.filter = None
        self.drop_tags = []
        self.host_tag = None


        self.store = MeasurementStore(config)
        self.default_db = config.get("AdminDB","dbname")
        self.default_db_host = config.get("AdminDB","hostname")
        self.default_db_port = config.getint("AdminDB","port")

        self.drop_tags = config.get("Receiver", "drop_tags")
        if self.drop_tags and "," in self.drop_tags:
            self.drop_tags = re.split("\s*,\s*", self.drop_tags)
        self.sigconf = { "addstatus" : "start",
                         "delstatus" : "finish",
                         "signal_measurement" : "jobevents",
                         "status_tag" : "fields.stat",
                         "hostkey" : "fields.hosts",
                         "hostsep" : ":",
                         "do_signalling" : "False",
                         "tag_file" : None}
        self.setup_signal_config()
        self.tagconf = { "hosts_tag" : self.sigconf["hostkey"],
                         "hosts_sep" : self.sigconf["hostsep"],
                         "tag_file" :  self.sigconf["tag_file"]}
        self.tagger = Tagger(hosts_attr=self.tagconf["hosts_tag"],
                             hosts_sep=self.tagconf["hosts_sep"],
                             tag_file=self.tagconf["tag_file"])

        self.infoconf = { "do_info": False,
                          "hostname": "localhost",
                          "port": "27000",
                          "dbtype": "mongodb",
                          "collection": "jobinfo",
                          "info_measurement": "info",
                          "index": "tags.jobid"}
        self.setup_info_config()
        self.metricconf = { "hostkey": "tags.hostname",
                            "taskkey": "tags.jobid",
                            "userkey": "tags.username",
                            "mainkey": "tags.jobid",
                            "allow_tag_modification": "True"}
        self.setup_metrics_config()
        self.splitconf = { "do_split" : False,
                           "delete_format_tags" : True,
                           "split_db_format" : "[tags.username]",
                           "splitkey" : "tags.jobid",
                           "dbentries" : ""}

        self.defSplitDBconf = { "hostname" : None,
                                "port" : None,
                                "batch" : 100,
                                "maxsend" : 1000,
                                "username" : "admin",
                                "passwd" : "admin",
                                "maxdbs" : 100,
                                "curdbs" : 0,
                                "active" : []}

        self.setup_split_config()
        self.zmqPublisher = None
        super(InfluxReceiver, self).__init__(server_address, RequestHandlerClass)



    def setup_signal_config(self):
        if self.config.has_section("SignalConfig"):
            for k in self.sigconf:
                if self.config.has_option("SignalConfig", k):
                    self.sigconf[k] = self.config.get("SignalConfig", k).strip()
        self.sigconf["do_signalling"] = bool(self.sigconf["do_signalling"])
    def setup_info_config(self):
        if self.config.has_section("InfoConfig"):
            for k in self.infoconf:
                if self.config.has_option("InfoConfig", k):
                    self.infoconf[k] = self.config.get("InfoConfig", k).strip()
        self.infoconf["do_info"] = bool(self.infoconf["do_info"])
    def setup_metrics_config(self):
        if self.config.has_section("MetricsConfig"):
            for k in self.metricconf:
                if self.config.has_option("MetricsConfig", k):
                    self.metricconf[k] = self.config.get("MetricsConfig", k).strip()
        self.metricconf["allow_tag_modification"] = bool(self.metricconf["allow_tag_modification"])
    def setup_split_config(self):

        if self.config.has_section("SplitConfig"):
            for k in self.splitconf:
                if self.config.has_option("SplitConfig", k):
                    self.splitconf[k] = self.config.get("SplitConfig", k).strip()
        self.splitconf["do_split"] = cast_bool(self.splitconf["do_split"])
        self.splitconf["delete_format_tags"] = bool(self.splitconf["delete_format_tags"])
        self.splitconf["dbentries"] = re.split("\s*,\s*", self.splitconf["dbentries"])



    def publish(self, data):
        # If the ZMQ publisher is not already initialized, read the configuration
        # and start it.
        if not self.zmqPublisher:
            if self.config.has_section("ZMQPublisher"):
                host = "localhost"
                port = 8091
                filt = ".*"
                proto = "tcp"
                if self.config.has_option("ZMQPublisher", "bindhost"):
                    host = self.config.get("ZMQPublisher", "bindhost")
                if self.config.has_option("ZMQPublisher", "bindport"):
                    port = self.config.getint("ZMQPublisher", "bindport")
                if self.config.has_option("ZMQPublisher", "regex"):
                    # The regex is used for filtering
                    filt = self.config.get("ZMQPublisher", "regex")
                if self.config.has_option("ZMQPublisher", "protocol"):
                    newproto = self.config.has_option("ZMQPublisher", "protocol")
                    if newproto in ["tcp", "udp"]:
                        proto = newproto
                self.zmqPublisher = ZMQPublisher(host, port, filter=filt, proto=proto)
                self.zmqPublisher.start()
        # Publish it
        if self.zmqPublisher:
            self.zmqPublisher.pub_metric(data)

class InfluxReceiveHandler(BaseHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        self.timeout = 1

        BaseHTTPRequestHandler.__init__(self, request, client_address, server)
    def _set_headers(self, resp):
        self.send_response(resp)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()
    def log_message(self,fmt, *args):
        pass

    def do_POST(self):
        u = urlparse(self.path)
        content = self.rfile.read(int(self.headers["Content-Length"]))
        self.rfile.close()
        logging.info_once = True
        if u.path.startswith("/write"):
            db = None
            # Get the database
            m = re.search("db=([\w\d]+)", self.path)
            if m: db = m.group(1)

            # Since we can get a bunch of measurements in one request, we need
            # to analyze them separately
            contentlist = content.strip().split("\n")
            for cline in contentlist:
                # Create a measurement
                m = Measurement(cline)
                mname = m.get_metric()
                # Should we skip this measurement?
                if self.server.filter and not self.server.filter.match(mname):
                    continue

                # Add the database as a meta information to the measurement
                # If there is no database in the URL, use the default database
                if db:
                    m.add_meta("db", db)
                else:
                    m.add_meta("db", self.server.default_db)


                key = None
                # Measurements can have multiple functions, so we test all
                if self.server.sigconf["do_signalling"] and mname == self.server.sigconf["signal_measurement"]:
                    # Only tags are attached to all following measurements
                    # Stuff in fields is only meant for the database (additional
                    # information)
                    stag = self.server.sigconf["status_tag"]
                    addstatus = self.server.sigconf["addstatus"]
                    delstatus = self.server.sigconf["delstatus"]

                    if re.match(addstatus, m.get_attr(stag)):
                        if not self.server.tagger.add(m):
                            continue
                    elif m.get_attr(stag) == delstatus:
                        if not self.server.tagger.delete(m):
                            continue

                elif self.server.infoconf["do_info"] and mname == self.server.infoconf["info_measurement"]:
                        # process info measurement (currently unused)
                        newdb = self.server.config.get("InfoConfig", "infodb_db")
                        if not newdb:
                            newdb = self.server.default_db
                        m.mod_meta("db", newdb)
                else:
                    # Try to enrich the measurement if we are inside a signaled
                    # timeframe (job)
                    newtags = {}
                    hostkey = self.server.metricconf["hostkey"]
                    hostname = m.get_attr(hostkey)
                    if hostname and self.server.tagger.host_active(hostname):
                        t = self.server.tagger.get_tags_by_host(hostname)
                        newtags.update(t)
                        if len(newtags) > 0:
                            for k in newtags:
                                if self.server.metricconf["allow_tag_modification"]:
                                    m.mod_tag(k, newtags[k])
                                else:
                                    m.add_tag(k, newtags[k])
                # Sometimes the measurement contains tags that are not wanted in
                # the database. We can drop them here
                tags = m.get_all_tags()
                for k in self.server.drop_tags:
                    if k in tags:
                        m.del_tag(k)

                # Store it for admin database
                self.server.store.add(m)
                # Publish through ZeroMQ
                # The published measurements can be filtered. This is done later
                # in the zmqPublisher
                self.server.publish(str(m))

                # Should we split and is the host of the measurement
                # in a job currently?
                if self.server.splitconf["do_split"] and self.server.tagger.host_active(m.get_attr(self.server.metricconf["hostkey"])):
                    # Copy the measurement
                    newm = Measurement(m)
                    # Get the format of the new database
                    udb = self.server.splitconf["split_db_format"]
                    skip = False

                    # Try to replace variables in format with measurements entries
                    if "tags." in udb:
                        tags = newm.get_all_tags()
                        for t in tags:
                            if "[tags.%s]" % t in udb:
                                udb = udb.replace("[tags.%s]" % t, tags[t])
                                # We can delete this tag, it is already stored
                                # as database name
                                if self.server.splitconf["delete_format_tags"]:
                                    newm.del_tag(t)
                    if "field." in udb:
                        fields = newm.get_all_fields()
                        for f in fields:
                            if "[field.%s]" % f in udb:
                                udb = udb.replace("[field.%s]" % f, fields[f])
                                # We can delete this field, it is already stored
                                # as database name
                                if self.server.splitconf["delete_format_tags"]:
                                    newm.del_field(f)
                    if "meta." in udb:
                        meta = newm.get_all_meta()
                        for m in meta:
                            if "[meta.%s]" % m in udb:
                                # We can delete this meta information,
                                # it is already stored as database name
                                # But currently there is no possibility to add
                                # new meta information and meta.db points
                                # to the old database. Set in a few lines by
                                # mod_meta
                                udb = udb.replace("[meta.%s]" % m, meta[m])
                                if self.server.splitconf["delete_format_tags"]:
                                    newm.del_meta(m)
                    if "tags." in udb or "field." in udb or "meta." in udb:
                        skip = True

                    if not skip:
                        newm.mod_meta("db", udb)
                        self.server.store.add(newm)
                    else:
                        logging.info("Skip measurement: %s" % str(newm))

            self._set_headers(204)
        elif u.path.startswith("/query"):
            # forward to original database
            self._set_headers(404)
        self._set_headers(404)
    def do_GET(self):
        # forward to host of admin database
        u = urlparse(self.path)
        if u.path.startswith("/query"):
            # Imitate common query endpoint
            path = self.path
            if "db=" in path:
                m = re.search("(db=[\w\d]+)", path)
                if m:
                    path = path.replace(m.group(1), "db=%s" % str(self.server.default_db))
            # The url is changed to the one of the default database
            url = "http://%s:%s%s" % (self.server.default_db_host, str(self.server.default_db_port), path)

            heads = self.headers
            # Remove gzip from headers to get the data in plain text
            if "Accept-Encoding" in heads:
                del heads["Accept-Encoding"]
            req = urllib2.Request(url, headers=heads)
            resp = None
            try:
                resp = urllib2.urlopen(req)
            except urllib2.URLError as e:
                logging.info(e)
                self._set_headers(404)
                return
            if resp:
                out = resp.read()
                self.send_response(resp.getcode())
                self.send_header('Content-type', 'application/json')
                self.send_header('Connection', 'keep-alive')
                self.end_headers()
                self.wfile.write(out)
        elif u.path.startswith("/info"):
            # Endpoint to get current tagger data
            if "entity=" in self.path:
                m = re.search("entity=([\w\d]+)", self.path)
                if m:
                    out = None
                    if m.group(1) == "keys":
                        out = json.dumps(self.server.tagger.get_all_keys())
                    if m.group(1) == "hosts":
                        out = json.dumps(self.server.tagger.get_all_active_hosts())
                    if m.group(1) == "keydata":
                        out = json.dumps(self.server.tagger.get_all_key_data())
                    if m.group(1) == "dbhosts":
                        out = json.dumps(self.server.store.get_db_hosts())

                    if out:
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.send_header('Connection', 'keep-alive')
                        self.end_headers()
                        self.wfile.write(out)
                    else:
                        self.send_response(404)
                        self.end_headers()

    def handle_one_request(self):
        """Handle a single HTTP request.

        You normally don't need to override this method; see the class
        __doc__ string for information on how to handle specific HTTP
        commands such as GET and POST.

        """
        try:
            try:
                self.raw_requestline = self.rfile.readline(65537)
                if len(self.raw_requestline) > 65536:
                    self.requestline = ''
                    self.request_version = ''
                    self.command = ''
                    self.send_error(414)
                    return
            except:
                self.raw_requestline = None
            if not self.raw_requestline:
                self.close_connection = 1
                return
            if not self.parse_request():
                # An error code has been sent, just exit
                return
            mname = 'do_' + self.command
            if not hasattr(self, mname):
                self.send_error(501, "Unsupported method (%r)" % self.command)
                return
            method = getattr(self, mname)
            method()
            self.wfile.flush() #actually send the response if not already done.

            # now check the store whether a send is required.
            if self.server.store.send_required():
                self.server.store.send_all()
        except socket.timeout, e:
            #a read or a write timed out.  Discard this connection
            self.log_error("Request timed out: %r", e)
            self.close_connection = 1
            return




class RouterDaemon(Daemon):
    def __init__(self, configfile, pidfile):
        self.configfile = configfile
        self.receiver = None
        self.config = None
        Daemon.__init__(self, pidfile)
    def read_config(self):
        if not self.config:
            self.config = SafeConfigParser()
            if os.path.exists(self.configfile):
                fp = open(self.configfile)
                self.config.readfp(fp)
                fp.close()
            else:
                logging.error("Config file %s does not exist" % self.configfile)
                return False
        return True
    def start_receiver(self):
        h = ""
        p = 8090
        if not self.config:
            logging.error("Initialize configuration file first")
            return False
        if not self.receiver:
            if self.config.has_section("Receiver"):
                if self.config.has_option("Receiver", "bindaddress"):
                    h = self.config.get("Receiver", "bindaddress")
                if self.config.has_option("Receiver", "port"):
                    p = self.config.getint("Receiver", "port")
            self.receiver = InfluxReceiver(self.config, (h, p), InfluxReceiveHandler)
        return True
    def run(self):
        if not self.read_config():
            return
        if not self.start_receiver():
            return
        try:
            while True:
                self.receiver.handle_request()
        except KeyboardInterrupt:
            sys.exit(1)

def main():
    parser = OptionParser()
    parser.add_option("-c", "--config", dest="configfile", help="Configuration file", default="influxdb-router.conf", metavar="FILE")
    parser.add_option("-l", "--log", dest="logfile", help="Log file", default="influxdb-router.log", metavar="FILE")
    parser.add_option("-p", "--pidfile", dest="pidfile", help="File to store the PID", default="influxdb-router.pid", metavar="FILE")
    (options, args) = parser.parse_args()

    FORMAT = '%(asctime)s %(message)s'
    logging.basicConfig(filename=options.logfile, level=logging.INFO, format=FORMAT)

    daemon = RouterDaemon(options.configfile, options.pidfile)
    daemon.run()


if __name__ == "__main__":
    main()

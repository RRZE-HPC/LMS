# coding=utf-8

"""
Send metrics to a [influxdb](https://github.com/influxdb/influxdb/) using the
http interface.

v1.0 : creation
v1.1 : force influxdb driver with SSL
v1.2 : added a timer to delay influxdb writing in case of failure
       this whill avoid the 100% cpu loop when influx in not responding
       Sebastien Prune THOMAS - prune@lecentre.net

Patched by Thomas Roehl (Thomas.Roehl@fau.de) for the FEPA project to add
collector and metric tags to the json.

- Dependency:
    - influxdb client (pip install influxdb)
      you need version > 0.1.6 for HTTPS (not yet released)

- enable it in `diamond.conf` :

handlers = diamond.handler.influxdbHandler.InfluxdbHandler

- add config to `diamond.conf` :

[[InfluxdbHandler]]
hostname = localhost
port = 8086 #8084 for HTTPS
batch_size = 100 # default to 1
cache_size = 1000 # default to 20000
username = root
password = root
database = graphite
time_precision = s
tagfile = /tmp/.tags.influx.dat
"""

import time
import math
import os, os.path
import re, subprocess
import json
from diamond.handler.Handler import Handler
import urllib2

def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None

try:
    InfluxDBClient = which("curl")
except ImportError:
    InfluxDBClient = None


def loggedin_users(blacklist):
    systemusers = blacklist
    users = []
    f = open("/etc/passwd")
    finput = f.read().strip()
    f.close()
    for line in finput.split("\n"):
        if re.match("^\s*$", line): continue
        linelist = re.split(":", line)
        if linelist[1] == "x":
            if len(linelist[0]) <= 8:
                systemusers.append(linelist[0])
            else:
                systemusers.append(linelist[0])
                systemusers.append(linelist[0][:7]+"+")
        else:
            uid = None
            try:
                uid = int(linelist[2])
                if uid < 1024:
                    if len(linelist[0]) <= 8:
                        systemusers.append(linelist[0])
                    else:
                        systemusers.append(linelist[0])
                        systemusers.append(linelist[0][:7]+"+")
            except:
                pass
    cmd = ["ps -ef"]
    try:
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = p.communicate()
    except subprocess.CalledProcessError, e:
        return -1
    if p.returncode:
        return -1
    if not out:
        return -1
    if err:
        return -1
    for line in out.split('\n'):
        if line.startswith("UID"): continue
        linelist = re.split("\s+", line)
        if linelist[0] != "" and linelist[0] not in systemusers and not re.match("\d+", linelist[0]):
            users.append(linelist[0])
    return len(set(users))

class InfluxdbHandlerNative(Handler):
    """
    Sending data to Influxdb using batched format with urllib2
    """
    def __init__(self, config=None):
        """
        Create a new instance of the InfluxdbHandlerNative
        """
        # Initialize Handler
        Handler.__init__(self, config)

        if not InfluxDBClient:
            self.enabled = False
            return

        # Initialize Options
        self.url = ""
        defport = 8086
        if self.config['ssl'] == "True":
            self.ssl = True
            self.url="https://"
            defport = 8084
        else:
            self.ssl = False
            self.url="http://"
        self.hostname = "localhost"
        if self.config.has_key("hostname"):
            self.hostname = self.config['hostname']
        self.port = defport
        if self.config.has_key("port"):
            self.port = int(self.config['port'])
        self.username = None
        if self.config.has_key("username"):
            self.username = self.config['username']
        self.password = None
        if self.config.has_key("password"):
            self.password = self.config['password']
        if self.username and self.password:
            self.url += "%s:%s@" % (self.username, self.password, )
        elif self.username:
            self.url += "%s@" % (self.username, )

        self.database = self.config['database']
        self.userblacklist = []
        if self.config.has_key("userblacklist"):
            self.userblacklist = re.split("\s*,\s*", self.config['userblacklist'])
        self.batch_size = int(self.config['batch_size'])
        self.metric_max_cache = int(self.config['cache_size'])
        self.batch_count = 0
        self.time_precision = self.config['time_precision']
        self.addtags = False
        if len(self.config['tagfile']) > 0:
            self.tagfile = self.config['tagfile']
            self.addtags = True

        # Initialize Data
        self.batch = {}
        self.batch_timestamp = time.time()
        self.time_multiplier = 1

        self.url += "%s:%s/write?db=%s" % (self.hostname, self.port, self.database, )
        self.curl_cmd = "%s -i -XPOST '%s' --data-binary" % (InfluxDBClient, self.url,)


    def get_default_config_help(self):
        """
        Returns the help text for the configuration options for this handler
        """
        config = super(InfluxdbHandlerNative, self).get_default_config_help()

        config.update({
            'hostname': 'Hostname',
            'port': 'Port',
            'ssl': 'set to True to use HTTPS instead of http',
            'batch_size': 'How many metrics to store before sending to the'
            ' influxdb server',
            'cache_size': 'How many values to store in cache in case of'
            ' influxdb failure',
            'username': 'Username for connection',
            'password': 'Password for connection',
            'database': 'Database name',
            'time_precision': 'time precision in second(s), milisecond(ms) or '
            'microsecond (u)',
            'tagfile': 'Filename to get tags data from',
        })

        return config

    def get_default_config(self):
        """
        Return the default config for the handler
        """
        config = super(InfluxdbHandlerNative, self).get_default_config()

        config.update({
            'hostname': 'localhost',
            'port': 8086,
            'ssl': False,
            'username': 'root',
            'password': 'root',
            'database': 'graphite',
            'batch_size': 1,
            'cache_size': 20000,
            'time_precision': 's',
            'tagfile': ''
        })

        return config


    def read_tags(self):
        tags = {}
        if loggedin_users(self.userblacklist) == 0 and os.path.exists(self.tagfile):
            os.remove(self.tagfile)
            return tags
        if os.path.exists(self.tagfile):
            finput = None
            try:
                f = open(self.tagfile)
                finput = f.read().strip()
                f.close()
            except:
                self.log.error("Cannot open tag file %s" % (self.tagfile,))
                return tags
            for line in finput.split("\n"):
                if line.startswith("#") or not line.strip():
                    continue
                if not ":" in line:
                    continue
                linelist = [ i.strip() for i in line.split(":") ]
                if len(linelist):
                    tags.update({linelist[0] : linelist[1]})
        return tags

    def process(self, metric):
        if self.batch_count <= self.metric_max_cache:
            # Add the data to the batch
            #self.batch.setdefault(metric.path, []).append([metric.timestamp,
            #                                               metric.value])
            if not self.batch.has_key(metric.path):
                self.batch[metric.path] = []
            self.batch[metric.path].append([metric.timestamp,metric.value])
            self.batch_count += 1
        # If there are sufficient metrics, then pickle and send
        if self.batch_count >= self.batch_size and (
                time.time() - self.batch_timestamp) > 2**self.time_multiplier:
            # Log
            self.log.debug(
                "InfluxdbHandler: Sending batch sizeof : %d/%d after %fs",
                self.batch_count,
                self.batch_size,
                (time.time() - self.batch_timestamp))
            # reset the batch timer
            self.batch_timestamp = time.time()
            # Send pickled batch
            self._send()

    def _send(self):
        """
        Send data to Influxdb. Data that can not be sent will be kept in queued.
        """
        try:
            if InfluxDBClient is None:
                self.log.debug("InfluxdbHandler: Send failed.")
            else:
                # build metrics data
                metrics = []
                tags ={}
                if self.addtags:
                    tags.update(self.read_tags())
                for path in self.batch.keys():
                    pathlist = path.split(".")
                    if len(pathlist) >= 4:
                        pathlist.pop(0)
                        mname = pathlist[-1]
                        pathlist.pop()
                        host = pathlist[0]
                        pathlist.pop(0)
                        collector = pathlist[0]
                        pathlist.pop(0)
                        tags = {"hostname": host, "collector" : collector}
                        for p in pathlist:
                            if p.startswith("cpu"):
                                tags["cpu"] = p.replace("cpu","")
                                pathlist[pathlist.index(p)] = ""
                            elif p.startswith("total"):
                                mname = "sum."+mname
                                pathlist[pathlist.index(p)] = ""
                        if collector == "likwid":
                            for p in pathlist:
                                if p in ["avg","min","max","sum"]:
                                    mname = p+"."+mname
                                    pathlist[pathlist.index(p)] = ""
                        elif collector == "iostat":
                            tags["disk"] = pathlist[0]
                            pathlist[0] = ""
                    else:
                        mname = path

                    for item in self.batch[path]:
                        time = item[0]
                        value = item[1]
                        if str(value) == "nan" or math.isnan(float(value)):
                            value = 0
                        mjson = {
                            "time": time,
                            "tags": tags,
                            "measurement": mname,
                            "fields": { "value" : value }}
                        metrics.append(mjson)
            # Send data to influxdb
            self.log.debug("InfluxdbHandler: writing %d series of data", len(metrics))
            #self.influx.write_points(metrics, time_precision=self.time_precision)
            ret = self._send_native(metrics)
            if ret:
                # empty batch buffer
                self.batch = {}
                self.batch_count = 0
                self.time_multiplier = 1

        except Exception:
            if self.time_multiplier < 5:
                self.time_multiplier += 1
            self._throttle_error(
                "InfluxdbHandler: Error sending metrics, waiting for %ds.",
                2**self.time_multiplier)
            raise


    def _send_native(self, metrics):
        sent = False
        os.environ['http_proxy']=''
        os.environ['https_proxy']=''
        sendlist = []
        for m in metrics:
            tags = []
            for k in m["tags"].keys():
                tags.append("%s=%s" % (str(k),str(m["tags"][k]),))
            mstr = m["measurement"]
            if len(tags) > 0:
                mstr += ","+",".join(tags)
            mstr += " value=%s %s" % (str(m["fields"]["value"]),str(int(m["time"]*1E9)),)
            sendlist.append(mstr)
        try:
            req = urllib2.Request(self.url, "\n".join(sendlist), {"Content-Type" : "application/octet-stream"})
            resp = urllib2.urlopen(req)
            if resp.getcode() == 204:
                sent = True
        except urllib2.URLError as e:
            self._throttle_error("InfluxdbHandlerNative: Failed to send %d metrics: %s" % (len(metrics),str(e),))
        return sent

    def _send_curl(self, metrics):
        sendlist = []
        for m in metrics:
            tags = []
            for k in m["tags"].keys():
                tags.append("%s=%s" % (str(k),str(m["tags"][k]),))
            mstr = m["measurement"]
            if len(tags) > 0:
                mstr += ","+",".join(tags)
            mstr += " value=%s %s" % (str(m["fields"]["value"]),str(int(m["time"]*1E9)),)
            sendlist.append(mstr)
        sendcmd = "%s '%s' 2>/dev/null 1>/dev/null" % (self.curl_cmd, "\n".join(sendlist), )
        ret = os.system(sendcmd)
        if ret == 0:
            return True
        return False

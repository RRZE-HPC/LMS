# coding=utf-8

"""
Collect icmp round trip times
Only valid for ipv4 hosts currently

#### Dependencies

 * likwid
 * likwid-python-api

#### Configuration

Configuration is done by:

Create a file named: LikwidCollector.conf in the collectors_config_path

 * enabled = true
 * interval = 1 (second)
 * group_1 = <group name>
 * group_2 = <group name>
 * likwidmonitor = <file to watch>
 * userblacklist = hpcop

Test your configuration using the following command:

diamond-setup --print -C LikwidCollector

You should get a response back that indicates 'enabled': True and see entries
for your targets in pairs like:

'group_1': 'L3'

"""

import diamond.collector
import time
import os, os.path
import sys
import math
import re
# required for test_ps
import subprocess
try:
    import pylikwid
except:
    pylikwid = None

def test_ps(blacklist):
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
        print err
        return -1
    for line in out.split('\n'):
        if line.startswith("UID"): continue
        linelist = re.split("\s+", line)
        if linelist[0] != "" and linelist[0] not in systemusers and not re.match("\d+", linelist[0]):
            users.append(linelist[0])
    return len(set(users))

def ownsleep(secs):
    nsecs = 1
    try:
        nsecs = int(secs)
    except:
        pass
    time.sleep(nsecs)

class LikwidCollector(diamond.collector.Collector):
    def __init__(self, *args, **kwargs):
        self.cpus = []
        self.groups = {}
        self.groupnames = []
        self.userblacklist = []
        self.init = False
        self.debug = False
        self.likwidmonitor = False
        super(LikwidCollector, self).__init__(*args, **kwargs)

        if not pylikwid:
            self.log.error('pylikwid import failed. '
                               'Handler disabled')
            self.enabled = False
            return
        os.environ["LIKWID_FORCE"] = "1"
        self.mtime = int(self.config["mtime"])
        self.access = int(self.config['accessmode'])
        if len(self.config["likwidmonitor"]) > 0:
            self.monitorfile = self.config["likwidmonitor"]
            self.likwidmonitor = True
        if self.config.has_key("userblacklist"):
            self.userblacklist = re.split("\s*,\s*", self.config["userblacklist"])
        for k in self.config.keys():
            #if re.match("group_\d+", k):
            if k.startswith("group_"):
                self.groups[self.config[k]] = -1
                self.groupnames.append(self.config[k])

        if self.debug:
            self.log.debug("Set access mode for LIKWID")
        ret = pylikwid.hpmmode(self.access)
        if not ret:
            self.log.error('Failed to set access mode for LIKWID')
            self.enabled = False
            return
        if self.debug:
            self.log.debug("Initialize LIKWID's access layer")
        ret = pylikwid.hpminit()
        if not ret:
            self.log.error('Failed to initialize access layer for LIKWID')
            self.enabled = False
            return
        if self.debug:
            self.log.debug("Initialize LIKWID's topology module")
        ret = pylikwid.inittopology()
        if not ret:
            self.log.error('Failed to initialize LIKWID topology module')
            self.enabled = False
            return
        if self.debug:
            self.log.debug("Add all CPUs to monitored CPUs")
        topo = pylikwid.getcputopology()
        for t in topo["threadPool"].keys():
            self.cpus.append(topo["threadPool"][t]["apicId"])
        return None
    def get_default_config_help(self):
        config_help = super(LikwidCollector, self).get_default_config_help()
        config_help.update({
            'mtime':         'Measurement time per group',
            'accessmode':    'Method how to access the registers (0=direct, 1=accessDaemon)',
            'group_1':       'Group to measure. Additional groups can be added by incrementing the number in group_X',
            'likwidmonitor': 'File to check to skip measurements',
            'userblacklist': 'Skip users when checking the count of logged in users.',
            'debug': 'Activate debug output.'
        })
        return config_help

    def get_default_config(self):
        """
        Returns the default collector settings
        """
        config = super(LikwidCollector, self).get_default_config()
        config.update({
            'mtime':             1,
            'accessmode':        0,
            'interval':         10,
            'path':             'likwid',
            'likwidmonitor':    '',
            'userblacklist':    '',
            'debug':            False,
        })
        return config
    def __del__(self):
        if self.debug:
            self.log.debug("Finalize LIKWID")
        pylikwid.finalize()

    def collect(self):
        if self.likwidmonitor and os.path.exists(self.monitorfile):
            if test_ps(self.userblacklist) == 0:
                os.remove(self.monitorfile)
            else:
                self.log.info("Monitoring file found -> skipping LikwidCollector")
                return
        if not self.init:
            ret = pylikwid.init(self.cpus)
            if ret != 0:
                self.log.error('Failed to initialize LIKWID perfmon module')
                self.enabled = False
                return
            if self.debug:
                self.log.debug("Initialized LIKWID")
            self.init = True

        for gname in sorted(self.groupnames):
            gid = self.groups[gname]
            if gid == -1:
                if self.debug:
                    self.log.debug("Adding group %s" % (gname,))
                gid = pylikwid.addeventset(gname)
                if gid < 0:
                    self.log.error('Failed to add group %s to LIKWID perfmon module' % (gname,))
                    self.groups[gname] = -2
                    return
                self.groups[gname] = gid
            elif gid == -2:
                continue

            if pylikwid.setup(gid) != 0:
                return
            if self.debug:
                self.log.debug("Setup of group %s done" % (gname,))
            pylikwid.start()
            if self.debug:
                self.log.debug("Start of group %s done" % (gname,))
            ownsleep(self.mtime)
            pylikwid.stop()
            if self.debug:
                self.log.debug("Stop of group %s done" % (gname,))
            timestamp = time.time()
            sums = {}
            avgs = {}
            mins = {}
            maxs = {}
            nmetrics = pylikwid.getnumberofmetrics(gid)
            if self.debug:
                self.log.debug("Processing %d metrics for %d CPUs for group %s" % (nmetrics, len(self.cpus), gname,))
            for i in range(len(self.cpus)):
                for m in range(nmetrics):
                    metricname = pylikwid.getnameofmetric(gid, m)
                    v = float(pylikwid.getlastmetric(gid, m, i))
                    if math.isnan(v) or str(v) == "nan":
                        #self.log.error("Metric %s on CPU %d failed" % (metricname, self.cpus[i],))
                        v = 0.0
                    if metricname.startswith("AVG"):
                        if not avgs.has_key(metricname):
                            avgs[metricname] = v
                        else:
                            avgs[metricname] += v
                    elif metricname.startswith("SUM"):
                        if not sums.has_key(metricname):
                            sums[metricname] = v
                        else:
                            sums[metricname] += v
                    elif metricname.startswith("MIN"):
                        if not mins.has_key(metricname):
                            mins[metricname] = v
                        else:
                            if v < mins[metricname]:
                                mins[metricname] = v
                    elif metricname.startswith("MAX"):
                        if not maxs.has_key(metricname):
                            maxs[metricname] = v
                        else:
                            if v > maxs[metricname]:
                                maxs[metricname] = v
                    else:    
                        mname = "cpu%d." % (self.cpus[i])
                        mname += metricname 
                        mname = mname.replace(" ","_").replace("[","").replace("]","").replace("/","")
                        if self.debug:
                            self.log.debug("Publish %s = %.2f" % (mname,v,))
                        self.publish(mname, v, precision=2, timestamp=timestamp)
            for mname in avgs.keys():
                if self.debug:
                    self.log.debug("Publish %s = %.2f" % (mname,avgs[mname] / len(self.cpus),))
                self.publish(mname.replace("AVG ","avg.").replace(" ","_").replace("[","").replace("]","").replace("/",""), avgs[mname] / len(self.cpus), precision=2, timestamp=timestamp)
            for mname in mins.keys():
                if self.debug:
                    self.log.debug("Publish %s = %.2f" % (mname,mins[mname],))
                self.publish(mname.replace("MIN ","min.").replace(" ","_").replace("[","").replace("]","").replace("/",""), mins[mname], precision=2, timestamp=timestamp)
            for mname in maxs.keys():
                if self.debug:
                    self.log.debug("Publish %s = %.2f" % (mname,maxs[mname],))
                self.publish(mname.replace("MAX ","max.").replace(" ","_").replace("[","").replace("]","").replace("/",""), maxs[mname], precision=2, timestamp=timestamp)
            for mname in sums.keys():
                if self.debug:
                    self.log.debug("Publish %s = %.2f" % (mname,sums[mname],))
                self.publish(mname.replace("SUM ","sum.").replace(" ","_").replace("[","").replace("]","").replace("/",""), sums[mname], precision=2, timestamp=timestamp)

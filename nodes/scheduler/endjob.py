#!/usr/bin/env python

import urllib2, getopt, sys, os.path, re
import getpass, time

ROUTER_HOST = "testhost.testdomain.de"
ROUTER_PORT = 8090
SIGNAL_MEASUREMENT = "baseevents"
SIGNAL_DB = "testdatabase"

def usage():
    print "%s -j <jobid> -m <hostlist> (-M hostfile)" % (os.path.basename(sys.argv[0]),)
    print "You can add multiple tags and fields by supplying -t and -f multiple times"
    print
    print "-h/--help\tHelp message"
    print "-j/--jobid\tJob identifier"
    print "-m/--hosts\tComma-separated list of hosts"
    print "-M/--Hosts\tPath to file with hostnames (currently only PBS format)"
    print "-f/--field k=v\tKey/value pair that is added to fields"

def trycast(v):
    m = re.match("^\d+$", str(v))
    if m:
        return str(v)
    else:
        m = re.match("^\d+\.\d+$", str(v))
        if m:
            return str(v)
        else:
            v = "\""+ str(v) + "\""
            v = v.replace("\"\"", "\"")
            return v
    return str(v)


if len(sys.argv[1:]) == 0:
    usage()
    sys.exit()
jobid = None
hosts = None
addtags = []
user = getpass.getuser()
tags = {}
fields = {}
hostfile = None
try:
    opts, args = getopt.getopt(sys.argv[1:], "hj:m:M:f:", ["help", "jobid:", "hosts:", "field:"])
except getopt.GetoptError as err:
    # print help information and exit:
    print str(err)  # will print something like "option -a not recognized"
    usage()
    sys.exit(2)
for o, a in opts:
    if a.startswith("-"):
        print("Missing argument to option %s ?" % o)
        continue
    if o in ("-h", "--help"):
        usage()
        sys.exit()
    elif o in ("-j", "--jobid"):
        jobid = a
    elif o in ("-m", "--hosts"):
        hosts = a.split(",")
    elif o in ("-M", "--Hosts"):
        if os.path.exists(a):
            f = open(a)
            hosts = []
            for l in f.read().strip().split("\n"):
                if l not in hosts:
                    hosts.append(l)
            f.close()
        else:
            print("Cannot open file %s" % a)
#    elif o in ("-t", "--tag"):
#        if "=" in a:
#            alist = a.split("=")
#            tags[alist[0]] = "=".join(alist[1:])
    elif o in ("-f", "--field"):
        if "=" in a:
            alist = a.split("=")
            fields[alist[0]] = "=".join(alist[1:])
    else:
        assert False, "unhandled option"

if not jobid or not hosts:
    print "Job ID and hostlist are required to register a job"
    sys.exit()
if len(args) > 0:
    for a in args:
        if re.match(".+=.*", a):
            addtags.append(a)

tags["jobid"] = jobid
tags["username"] = user
fields["hosts"] = trycast(":".join(hosts))
fields["stat"] = trycast("finish")


registerstr = "%s" % (SIGNAL_MEASUREMENT)
for t in tags:
    registerstr += ",%s=%s" % (t, str(tags[t]))
registerstr += " "
for f in fields:
    registerstr += ",%s=%s" % (f, trycast(fields[f]))

registerstr = registerstr.replace(" ,"," ")
registerstr += " %d" % int(time.time()*1E9)

url = "http://%s:%d/write?db=%s" % (ROUTER_HOST, ROUTER_PORT, SIGNAL_DB,)
req = urllib2.Request(url, str(registerstr))
try:
    resp = urllib2.urlopen(req)
except urllib2.URLError as e:
    print "Failed to register job: %s" % e

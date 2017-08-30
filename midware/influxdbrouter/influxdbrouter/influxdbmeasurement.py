

import re, datetime
from Queue import Queue


class Measurement(object):
    def __init__(self, mstr):
        self.mstr = None
        self.meta = {}
        self.tags = {}
        self.fields = {}
        self.metric = ""
        self.timestamp = None

        self.names = ["measurement", "tags", "fields", "timestamp"]
        if isinstance(mstr, Measurement):
            self.mstr = mstr.mstr
            self.metric = mstr.metric
            self.timestamp = mstr.timestamp
            for k in mstr.meta:
                self.meta[k] = mstr.meta[k]
            for k in mstr.tags:
                self.tags[k] = mstr.tags[k]
            for k in mstr.fields:
                self.fields[k] = mstr.fields[k]

        elif isinstance(mstr, str):
            self.mstr = mstr
            instr = False
            start = 0
            no_timestamp = False
            for i, c in enumerate(mstr):
                if c == '\"' or c == '\'':
                    instr = not instr
                if c == ' ' and not instr:
                    self.metric = mstr[start:i]
                    start = i+1
                    break
                elif c == ',' and not instr:
                    self.metric = mstr[start:i]
                    start = i+1
                    hastags = True
                    break
            t = ""
            for i,c in enumerate(mstr[::-1]):
                if c == ' ':
                    break
                t = c+t
            try:
                self.timestamp = int(t.strip())
            except:
                no_timestamp = True
                self.timestamp = None
            if not no_timestamp:
                end_fields = len(mstr) - len(t)
            else:
                end_fields = len(mstr)+1
            end_tags = start
            instr = False
            for i, c in enumerate(mstr[start:]):
                if c == '\"' or c == '\'':
                    instr = not instr

                elif c == ' ' and not instr:
                    end_tags = start+i
                    break
            instr = False
            s = 0
            e = 0
            key = None
            for i,c in enumerate(mstr[start:end_tags]):
                if c == '\"' or c == '\'':
                    instr = not instr
                if c == "=" and not instr:
                    k = mstr[start:end_tags][s:i]
                    key = k
                    s = i+1
                if c == "," and not instr and key:
                    self.tags[key] = mstr[start:end_tags][s:i]
                    key = None
                    s = i+1
            if key and key not in self.tags:
                self.tags[key] = mstr[start:end_tags][s:end_tags]
            s = 0
            e = 0
            key = None
            instr = False
            while mstr[end_tags] == " ":
                end_tags += 1
            for i,c in enumerate(mstr[end_tags:end_fields]):
                if c == '\"' or c == '\'':
                    instr = not instr
                if c == "=" and not instr:
                    k = mstr[end_tags:][s:i]
                    key = k
                    s = i+1
                if (c == "," or i == (end_fields-end_tags)-1) and not instr and key:
                    self.fields[key] = mstr[end_tags:end_fields][s:i]
                    key = None
                    s = i+1
            if key and key not in self.fields:
                e = len(mstr[end_tags:])
                instr = False
                for i,c in enumerate(mstr[end_tags:][s:]):
                    if c == '\"' or c == '\'':
                        instr = not instr
                    if c == " ":
                        e = i
                        break;
                self.fields[key] = mstr[end_tags:][s:e]
            if len(self.fields) == 0 and len(self.tags) > 0:
                for t in self.tags:
                    self.fields[t] = self.tags[t]
                self.tags = {}

    def debug(self):
            print(self.mstr)
            print("Tags", self.tags)
            print("Fields", self.fields)
            print("Time", self.timestamp)
    def _get_idxs_from_str(self, key, idxs):
        if self.mstr and idxs[0] >= 0:
            kstart = self.mstr.find(key, idxs[0], idxs[1])
            if kstart >= 0:
                eq = self.mstr.find("=", kstart, idxs[1])
                if self.mstr[kstart:eq] == key:
                    instr = False
                    for i in range(eq+1, idxs[1]+1):
                        c = self.mstr[i]
                        if c == '\"' or c == '\'':
                            instr = not instr
                        elif c == ',':
                            break
                    return eq+1, i
        return -1,-1

    def get_tag(self, key):
        if key in self.tags:
            return self.tags[key]
        return None
    def get_field(self, key):
        if key in self.fields:
            return self.fields[key]
        return None
    def get_meta(self, key):
        if key in self.meta:
            return self.meta[key]
        return None
    def get_all_tags(self):
        return self.tags
    def get_all_fields(self):
        return self.fields
    def get_all_meta(self):
        return self.meta
    def has_tags(self):
        return self.idxs[1][0] > 0
    def has_fields(self):
        return self.idxs[2][0] > 0
    def _trycast(self, value):
        try:
            v = int(value)
#            if v == float(int(v)):
#                print("float but int")
#                return int(value)
            return v
        except:
            try:
                return float(value)
            except:
                pass
        if value.lower() in ("true", "false"):
            return bool(value)
        if ' ' in value:
            return '\"'+value+'\"'
#        if value[-1] == 'i':
#            try:
#                return int(value[:-1])
#            except:
#                pas
        return value

    def add_tag(self, key, value):
        if key in ("user", "host"):
            print("Bad keys for InfluxDB, used by itself as keywords")
            return False
        if key in self.tags:
            print("Tag with key %s already exists with value %s" % (key, self.tags[key]))
        else:
            self.tags[key] = value
            return True
        return False

    def mod_tag(self, key, value):
        if key in self.tags:
            self.tags[key] = value
            return True
        else:
            self.add_tag(key, value)
        return False

    def _del_sanitize(self):
        repl_len = 0
        if ",," in self.mstr:
            self.mstr = self.mstr.replace(",,", ",")
            repl_len += 1
        if " ," in self.mstr:
            self.mstr = self.mstr.replace(" ,", " ")
            repl_len += 1
        if ", " in self.mstr:
            self.mstr = self.mstr.replace(", ", " ")
            repl_len += 1
        return repl_len
    def del_tag(self, key):
        if key in self.tags:
            del self.tags[key]
    def del_field(self, key):
        if key in self.fields:
            del self.fields[key]
        if len(self.fields) == 0:
            print("Deleted last field. Current state is invalid, there must be at least one field entry")

    def add_field(self, key, value):
        if key not in self.fields:
            self.fields[key] = value
            return True
        else:
            print("Field with key %s already exists with value %s" % (key, self.mstr[s:e]))
        return False
    def set_time(self, time):
        self.timestamp = time

    def get_metric(self):
        return self.metric
    def get_time(self):
        if self.timestamp:
            return self.timestamp
        return None
    def get_datetime(self):
        if self.idxs[3][0] != -1:
            return datetime.datetime.fromtimestamp(float(self.timestamp)/1E9)
        return None
    def add_meta(self, key, value):
        if not key in self.meta:
            self.meta[key] = value
        else:
            print("Meta info with key %s already exists with value %s" % (key, self.meta[key]))
    def mod_meta(self, key, newvalue):
        if key in self.meta:
            self.meta[key] = newvalue
        else:
            print("Meta info with key %s does not exist" % key)
    def del_meta(self, key):
        if key in self.meta:
            del self.meta[key]
        else:
            print("Meta info with key %s does not exist" % key)
    def __str__(self):
        s = self.metric
        if len(self.tags) > 0:
            s += ","+",".join(["%s=%s" % (k,str(self.tags[k])) for k in self.tags])
        if len(self.fields) > 0:
            s += " "+",".join(["%s=%s" % (k,str(self.fields[k])) for k in self.fields])
        if self.timestamp:
            s += " "+str(self.timestamp)
        return s
    def __repr__(self):
        return """Measurement(\"\"\"%s\"\"\")""" % (self.mstr)
    def get_attr(self, attr):
        alist = attr.split(".")
        len_alist = len(alist)
        if len_alist >= 1 and len_alist < 3 and alist[0] in self.names:
            if alist[0] == "tags":
                v = self.get_tag(alist[1])
                if v:
                    return v.strip("\"")
            elif alist[0] == "fields":
                v = self.get_field(alist[1])
                if v:
                    return v.strip("\"")
            elif alist[0] == "measurement":
                return self.metric
            elif alist[0] == "meta":
                if alist[1] in self.meta:
                    return self.meta[alist[1]].strip("\"")
            elif alist[0] == "any":
                if alist[1] in self.meta:
                    return self.meta[alist[1]].strip("\"")
                if alist[1] in self.tags:
                    return self.tags[alist[1]].strip("\"")
                if alist[1] in self.fields:
                    return self.fields[alist[1]].strip("\"")
        else:
            print("Unknown attribute specifier, must be either tag.X, fields.Y, meta.Z or measurement")
        return None

class MeasurementBatch(object):
    def __init__(self, batchsize=100):
        self.batchsize = batchsize
        self.buffer = Queue(maxsize=self.batchsize)
        self.addtime = None
        self.timeout = 10
    def add(self, m):
        try:
            self.buffer.put(m, True, 10)
        except:
            return False
        return True
    def get_time(self):
        return self.addtime
    def clear(self):
        self.buffer = Queue(maxsize=self.batchsize)
    def len(self):
        return self.buffer.qsize()
    def __str__(self):
        tmp = []
        while not self.buffer.empty():
            try:
                x = self.buffer.get(False)
                tmp.append(x)
            except:
                break
        s = "\n".join([m.mstr for m in tmp])
        for m in tmp:
            self.add(m)
        return s

class MeasurementBatchByAttr(object):
    def __init__(self, attrkey, batchsize=100):
        self.buffer = {}
        self.batchsize = batchsize
        self.attrkey = attrkey
        self.nokey = "NOATTR"
    def _get_attr(self, m):
        return None
    def add(self, m):
        info = self._get_attr(m)
        key = self.nokey
        if info:
            key = info
        if not key in self.buffer:
            self.buffer[key] = MeasurementBatch(batchsize=self.batchsize)
        return self.buffer[key].add(m)
    def keys(self):
        return self.buffer.keys()
    def batch(self, key):
        if key in self.buffer:
            return self.buffer[key]
    def clear(self, key):
        if key in self.buffer:
            return self.buffer[key].clear()
    def len(self):
        s = 0
        if key in self.buffer:
            s = self.buffer[key].len()
        return s
    def __str__(self):
        s = ""
        for k in self.buffer:
            s += "%s=%s\n%s\n" % (self.attrkey, k, self.buffer[k])
        return s[:-1]

class MeasurementBatchByMeta(MeasurementBatchByAttr):
    def _get_attr(self, m):
        return m.get_meta(self.attrkey)

class MeasurementBatchByTag(MeasurementBatchByAttr):
    def _get_attr(self, m):
        return m.get_tag(self.attrkey)



#i = Measurement2("testmetric value=1.0")
#i.debug()
#i.add_tag("hostname", "heidi")
#i.debug()
#i = Measurement2("testmetric value=1.0 123")
#i.debug()
#i = Measurement2("""testmetric,hostname=heidi value=1.01,desc="123 as" """)
#i.debug()
#m = """testmetric,hostname=heidi,username=unrz139,jobid=12345.eadm value=1.01 1493129461000000000"""
#m = """baseevent,hostname=heidi,username=unrz139,jobid=12345.eadm title="Job started",nodes=4,ppn=40,hosts="heidi,heidi1,heidi2,heidi3",wallclock=14:00:00 1493129461000000000"""
#it = 1000
#it = 1
#import time
#x = None
#s = time.time()
#for i in range(it):
#    x = Measurement(m)
#e = time.time()
#print("Measurement", e-s)
#s = time.time()
#for i in range(it):
#    x = Measurement2(m)
#e = time.time()
#print("Measurement2", e-s)
#if not x:
#    x = Measurement2(m)
#x.debug()
#i = Measurement2("""baseevent,hostname=heidi,username=unrz139,jobid=12345.eadm title="Job started",nodes=4,ppn=40,hosts="heidi,heidi1,heidi2,heidi3",wallclock=14:00:00 1493129461002200000""")
#i.mod_tag("hostname", "adm")
#i.debug()
#print(i)
#print(i.get_datetime())
#metas = ["adm", "user"]

#b = MeasurementBatchByMeta("db", batchsize=2)
#h = MeasurementBatchByTag("hostname", batchsize=2)
#for i in range(10):
#    x = Measurement2(m)
#    x.add_meta("db", metas[i%2])
#    b.add(x)
#    x.del_tag("hostname")
#    h.add(x)
#print(b)
#print(h)
#x.debug()




class MeasurementWindow(object):
    def __init__(self, window=120, key="hostname"):
        self.window = window
        self.key = key
        self.buffer = {}
    def add_measurement(self, m):
        if not isinstance(m, Measurement):
            m = Measurement(m)
        tags = m.get_tags()
        if self.key in tags:
            if tags[self.key] in self.buffer:
                print("%s %s already in buffer, creating new" % (self.key, tags[self.key],))
                self.buffer = {}
            self.buffer[tags[self.key]] = m
            return True
        return False
    def get_window(self):
        times = []
        w = []
        for h in self.buffer:
            times.append(self.buffer[h].get_time())
        t = sorted(times)[len(times)/2]
        for h in self.buffer:
            self.buffer[h].set_time(t)
            w.append(self.buffer[h])
        return w


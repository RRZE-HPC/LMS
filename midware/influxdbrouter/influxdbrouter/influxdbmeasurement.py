

import re, datetime
from Queue import Queue


class Measurement(object):
    def __init__(self, mstr):
        self.mstr = None
        self.idxs = []
        self.meta = {}
        self.tags = {}
        self.fields = {}
        self.metric = ""
        self.timestamp = None
        for i in range(4):
            self.idxs.append([0,0])
        self.names = ["measurement", "tags", "fields", "timestamp"]
        if isinstance(mstr, Measurement):
            self.mstr = mstr.mstr
            for i in range(4):
                self.idxs[i] = [ mstr.idxs[i][0], mstr.idxs[i][1]]
            for k in mstr.meta:
                self.meta[k] = mstr.meta[k]

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
            for i,c in enumerate(mstr[end_tags:]):
                if c == '\"' or c == '\'':
                    instr = not instr
                if c == "=" and not instr:
                    k = mstr[end_tags:][s:i]
                    key = k
                    s = i+1
                if c == "," and not instr and key:
                    self.fields[key] = mstr[end_tags:][s:i]
                    key = None
                    s = i+1
            if key and key not in self.tags:
                e = len(mstr[end_tags:])
                instr = False
                for i,c in enumerate(mstr[end_tags:][s:]):
                    if c == '\"' or c == '\'':
                        instr = not instr
                    if c == " ":
                        e = i
                        break;
                self.fields[key] = mstr[end_tags:][s:e]
#            self.mstr = mstr
#            state = 1
#            instr = False
#            hastags = False

#            mstr = mstr.strip()
#            start = 0
#            for i, c in enumerate(mstr):
#                if c == '\"' or c == '\'':
#                    instr = not instr
#                if c == ' ' and not instr:
#                    self.idxs[0][1] = i
#                    self.metric = mstr[start:i]
#                    start = i+1
#                    self.idxs[1][0] = start
#                    break
#                elif c == ',' and not instr:
#                    self.idxs[0][1] = i
#                    self.metric = mstr[start:i]
#                    start = i+1
#                    self.idxs[1][0] = start
#                    hastags = True
#                    break
#            if start == 0:
#                print("String not in InfluxDB line protocol")
#            instr = False
#            for i, c in enumerate(mstr[start:]):
#                if c == '\"' or c == '\'':
#                    instr = not instr

#                elif c == ' ' and not instr:
#                    idx = start+i
#                    self.idxs[state][1] = idx
#                    state += 1
#                    self.idxs[state][0] = idx+1
#                    if state == 3:
#                        break
#            self.idxs[state][1] = len(mstr)

#            if state == 1:
#                self.idxs[2][0] = self.idxs[1][0]
#                self.idxs[2][1] = self.idxs[1][1]
#                self.idxs[1] = [-1,-1]
#                self.idxs[3] = [-1,-1]
#            elif state == 2:
#                if hastags:
#                    self.idxs[3] = [-1,-1]
#                else:
#                    self.idxs[3][0] = self.idxs[2][0]
#                    self.idxs[3][1] = self.idxs[2][1]
#                    self.idxs[2][0] = self.idxs[1][0]
#                    self.idxs[2][1] = self.idxs[1][1]
#                    self.idxs[1] = [-1,-1]
#        if self.idxs[3][0] != -1:
#            try:
#                timestamp = int(self.mstr[self.idxs[3][0]:self.idxs[3][1]])
#            except:
#                self.idxs[2][1] = self.idxs[3][1]
#                self.idxs[3] = [-1,-1]
#        self.fields = self._get_all_pairs(2)
#        self.tags = self._get_all_pairs(1)
    def debug(self):
            print(self.mstr)
            print(self.idxs)
            for i in range(4):
                print "%20s:\t\'%s\'" % (self.names[i], self.mstr[self.idxs[i][0]:self.idxs[i][1]])

            print
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
#        s, e = self._get_idxs_from_str(key, self.idxs[1])
#        if s > 0:
#            return self.mstr[s:e]
        if key in self.tags:
            return self.tags[key]
        return None
    def get_field(self, key):
#        s, e = self._get_idxs_from_str(key, self.idxs[2])
#        if s > 0:
#            return self.mstr[s:e]
        if key in self.fields:
            return self.fields[key]
        return None
    def get_meta(self, key):
        if key in self.meta:
            return self.meta[key]
        return None
    def _get_all_pairs(self, idx):
        tags = {}
        k = ""
        v = ""
        has_eq = False
        instr = False
        if not self.mstr:
            return tags
        for i in range(self.idxs[idx][0], self.idxs[idx][1]):
            c = self.mstr[i]
            if c == '\"' or c == '\'':
                instr = not instr
            elif c == '=':
                has_eq = not has_eq
                continue
            elif c == ',':
                tags[k] = self._trycast(v)
                k = ""
                v = ""
                has_eq = False
                instr = False
                continue
            if not has_eq: 
                k += c
            else:
                v += c
        tags[k] = self._trycast(v)
        return tags
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
#        if self.idxs[1][0] == -1:
#            repl = self.mstr[:self.idxs[0][1]]
#            add = ","+str(key)+"="+str(value)
#            add_len = len(add)
#            self.mstr = self.mstr.replace(repl, repl+add, 1)
#            self.idxs[1][0] = self.idxs[0][1] + 1
#            self.idxs[1][1] = self.idxs[0][1] + add_len
#            for i in range(2,4):
#                if self.idxs[i][0] >= 0:
#                    self.idxs[i][0] += add_len
#                    self.idxs[i][1] += add_len
#            self.tags[key] = value
#            return True
#        else:
#            #s, e = self._get_idxs_from_str(key, self.idxs[1])
#            if key not in self.tags:
#                repl = self.mstr[self.idxs[1][1]-5:self.idxs[1][1]]
#                add = ","+str(key)+"="+str(self._trycast(value))
#                add_len = len(add)
#                self.mstr = self.mstr.replace(repl, repl+add, 1)
#                self.idxs[1][1] += len(add)
#                for i in range(2,4):
#                    if self.idxs[i][0] >= 0:
#                        self.idxs[i][0] += add_len
#                        self.idxs[i][1] += add_len
#                self.tags[key] = value
#                return True
#            else:
#                print("Tag with key %s already exists with value %s" % (key, self.mstr[s:e]))
#        return False
    def mod_tag(self, key, value):
        if key in self.tags:
            self.tags[key] = value
        else:
            self.tags[key] = value
        if self.idxs[1][0] != -1:
            if self.get_tag(key):
                s, e = self._get_idxs_from_str(key, self.idxs[1])
                if s != -1:
                    start = self.idxs[1][0]
                    for i in range(s, self.idxs[1][0], -1):
                        c = self.mstr[i]
                        if c == ',':
                            start = i+1
                            break
                    end = e

                    repl = self.mstr[start:end]
                    add = str(key)+"="+str(self._trycast(value))
                    self.mstr = self.mstr.replace(repl, add, 1)
                    diff = len(add) - len(repl)
                    self.idxs[1][1] += diff
                    for i in range(2,4):
                        if self.idxs[i][0] >= 0:
                            self.idxs[i][0] += diff
                            self.idxs[i][1] += diff
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
#        if self.idxs[1][0] != -1:
#            s, e = self._get_idxs_from_str(key, self.idxs[1])
#            if s != -1:
#                start = self.idxs[1][0]
#                for i in range(s, self.idxs[1][0], -1):
#                    c = self.mstr[i]
#                    if c == ',':
#                        start = i+1
#                        break
#                end = e
#                repl = self.mstr[start:end]
#                repl_len = len(repl)
#                self.mstr = self.mstr.replace(repl, "", 1)
#                repl_len += self._del_sanitize()
#                self.idxs[1][1] -= repl_len
#                for i in range(2,4):
#                    if self.idxs[i][0] >= 0:
#                        self.idxs[i][0] -= repl_len
#                        self.idxs[i][1] -= repl_len
#                del self.tags[key]
    def del_field(self, key):
        if key in self.fields:
            del self.fields[key]
        
#        if self.idxs[2][0] != -1:
#            s, e = self._get_idxs_from_str(key, self.idxs[2])
#            if s != -1:
#                start = self.idxs[2][0]
#                for i in range(s, self.idxs[2][0], -1):
#                    c = self.mstr[i]
#                    if c == ',':
#                        start = i+1
#                        break
#                end = e
#                repl = self.mstr[start:end]
#                repl_len = len(repl)
#                self.mstr = self.mstr.replace(repl, "", 1)
#                repl_len += self._del_sanitize()
#                self.idxs[2][1] -= repl_len
#                if self.idxs[3][0] >= 0:
#                    self.idxs[3][0] -= repl_len
#                    self.idxs[3][1] -= repl_len
#                del self.fields[key]
#                if self.idxs[2][0] == self.idxs[2][1]:
#                    print("Deleted last field. Current state is invalid, there must be at least one field entry")
    def add_field(self, key, value):
        #s, e = self._get_idxs_from_str(key, self.idxs[2])
        if key not in self.fields:
#            repl = self.mstr[self.idxs[2][1]-5:self.idxs[2][1]]
#            add = ","+str(key)+"="+str(self._trycast(value))
#            add_len = len(add)
#            self.mstr = self.mstr.replace(repl, repl+add, 1)
#            self.idxs[2][1] += len(add)
#            if self.idxs[3][0] >= 0:
#                self.idxs[3][0] += add_len
#                self.idxs[3][1] += add_len
            self.fields[key] = value
            return True
        else:
            print("Field with key %s already exists with value %s" % (key, self.mstr[s:e]))
        return False
    def set_time(self, time):
        self.timestamp = time
#        if self.idxs[3][0] == -1:
#            repl = self.mstr[self.idxs[2][1]-5:self.idxs[2][1]]
#            add = " "+str(time)
#            self.mstr = self.mstr.replace(repl, repl+add, 1)
#            self.idxs[3][0] = self.idxs[2][1] + 1
#            self.idxs[3][1] = self.idxs[3][0] + len(str(time))
#        else:
#            repl = self.mstr[self.idxs[3][0]:self.idxs[3][1]]
#            self.mstr = self.mstr.replace(repl, str(time), 1)
#            if len(repl) != len(str(time)):
#                self.idxs[3][1] = self.idxs[3][0] + len(str(time)) + 1
#        self.timestamp = self.mstr[self.idxs[3][0]:self.idxs[3][1]]
    def get_metric(self):
        return self.mstr[self.idxs[0][0]:self.idxs[0][1]]
    def get_time(self):
        if self.timestamp:
            return self.timestamp
        return None
    def get_datetime(self):
        if self.idxs[3][0] != -1:
            return datetime.datetime.fromtimestamp(float(self.mstr[self.idxs[3][0]:self.idxs[3][1]])/1E9)
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
#                s,e = self._get_idxs_from_str(alist[1], self.idxs[1])
#                if s > 0:
#                    return self.mstr[s:e].strip("\"")
            elif alist[0] == "fields":
                v = self.get_field(alist[1])
                if v:
                    return v.strip("\"")
#                s,e = self._get_idxs_from_str(alist[1], self.idxs[2])
#                if s > 0:
#                    return self.mstr[s:e].strip("\"")
            elif alist[0] == "measurement":
                return self.metric
                #return self.mstr[self.idxs[0][0]:self.idxs[0][1]]
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
#                s,e = self._get_idxs_from_str(alist[1], self.idxs[1])
#                if s > 0:
#                    return self.mstr[s:e].strip("\"")
#                s,e = self._get_idxs_from_str(alist[1], self.idxs[2])
#                if s > 0:
#                    return self.mstr[s:e].strip("\"")
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


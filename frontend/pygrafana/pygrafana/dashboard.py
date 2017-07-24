#!/usr/bin/python

import copy
import json
import re
import sys
import datetime

grafana_version = "2.6.1"
global debug
debug = False

def set_grafana_version(version):
    if version and re.match("\d+\.\d+\.\d+", version):
        global grafana_version
        grafana_version = version

def debug_enable():
    debug = True
def debug_disable():
    debug = False
def debug_print(s):
    if debug:
        print("DEBUG: %s" % str(s))

# s (seconds), m (minutes), h (hours), d (days), w (weeks), M (months), y (years
time_limits = { "s" : 60, "m" : 60, "h" : 24, "d" : 31, "w": 52, "M" : 12, "y" : 100}
def check_timerange(t):
    """
    Checks a timerange string for validity

    Checks if string is anything like now-1h, or now-6h/h up to a date like 2016-09-17 04:31:00

    :param t: timerange string
    :return True/False
    """
    if isinstance(t, str):
        if time == "now":
            return True
        if "now" in t:
            m = re.match("now[-]([\d]+[smhdwMy])$")
            if m:
                return True
            m = re.match("now[-]([\d]+)([smhdwMy])/[smhdwMy]$")
            if m and len(m.groups) == 2:
                val, sym = m.groups()
                if int(val) > 0 and int(val) < time_limits[sym]:
                    return True
                else:
                    print "out of range"
                    return False
        m = re.match("([\d][\d][\d][\d])-([\d][\d])-([\d][\d]) ([\d][\d]):([\d][\d]):([\d][\d])", t)
        if m:
            return True
    return False

def check_color(c):
    """
    Checks a color string or tuple with numeric values

    :param c: Color string or tuple
    :return c or None
    """
    if isinstance(c, str):
        m = re.match("rgba\((\d+),\s*(\d+),\s*(\d+),\s*(0.[\d]+)\)", c)
        if m and int(m.group(1)) < 255 and int(m.group(2)) < 255 and int(m.group(3)) < 255 and float(m.group(4)) > 0 and float(m.group(4)) <= 1:
            return c
        m = re.match("rgb\((\d+),\s*(\d+),\s*(\d+)\)", c)
        if m and int(m.group(1)) < 255 and int(m.group(2)) < 255 and int(m.group(3)) < 255:
            return c
        m = re.match("#[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]$", c)
        if m:
            return c
    elif isinstance(c, tuple):
        if len(c) == 3 and int(c[0]) > 0 and int(c[0]) < 256 and \
                           int(c[1]) > 0 and int(c[1]) < 256 and \
                           int(c[2]) > 0 and int(c[2]) < 256:
            return "rgb(%d,%d,%d)" % (int(c[0]), int(c[1]), int(c[2]),)
        if len(c) == 4 and int(c[0]) > 0 and int(c[0]) < 256 and \
                           int(c[1]) > 0 and int(c[1]) < 256 and \
                           int(c[2]) > 0 and int(c[2]) < 256 and \
                           float(c[3]) > 0 and float(c[3]) < 1:
            return "rgba(%d,%d,%d, %f)" % (int(c[0]), int(c[1]), int(c[2]), float(c[3]),)
    return None

target_id = 0
def _get_next_target_refID():
    global target_id
    if target_id == 255:
        target_id = 0
    t = ord('A') + target_id
    if t > 255:
        t = ord('A')
        target_id = 0
    c = chr(t)
    target_id += 1
    return c

class Target(object):
    """
    Encapsulates an query and evaluation target used in Grafana's panels
    """
    def __init__(self, measurement, dsType="influxdb", alias="", tags=[],
                  groupBy=[], select=[[]], query="", resultFormat="time_series",
                  policy="default", rawQuery=False):
        """
        Construct a new Target object

        :param measurement: The name of the measurement
        :param dsType: String with the identifier for a supported data source
        :param alias: Alias in the panel's legend for this target
        :param tags: List of tags (Format: {{'key': DB key as string, 'value': DB value as string, 'operator': any valid operator as string, 'condition': any valid conditon as string})
        :param groupBy: List of grouping options (Format: {'type': any of ('fill', 'time', 'tag'), 'params': [parameter(s) for type, e.g. tag name]})
        :param select: Which elements in a measurement should be returned and further processed. (Format: {'type': 'field' or any valid function, 'params': [parameter(s) for type, e.g. 'value' if type == 'field' or function argument]})
        :param query: Query that is send to the data source. Not required for InfluxDB but probably the Graphite query is in here.
        :param resultFormat: Currently the only supported option is 'time_series'. There are others but not implemented yet.
        """
        self.dsType = dsType
        self.tags = tags
        self.groupBy = groupBy
        self.alias = alias
        self.select = select
        self.measurement = measurement
        self.query = query
        self.policy = policy
        self.refId = chr(ord('A'))
        self.resultFormat = resultFormat
        self.validGroupBy = ['fill', 'time', 'tag']
        self.validResultFormat = ["time_series"]
        self.grafana_version = grafana_version
        self.rawQuery = rawQuery
    def get(self):
        """
        Returns a dictionary with the Target object's configuration. Performs some sanitation like removing duplicated groupBy options
        and creates a valid query for InfluxDB based on the configuration.

        :return dict with the Target object's settings
        """
        global grafana_version
        t = None
        t = {}
        t["dsType"] = self.dsType
        t["tags"] = self.tags
        t["groupBy"] = self.groupBy
        t["alias"] = self.alias
        t["select"] = [[]]#[self.select]
        t["measurement"] = self.measurement
        t["query"] = self.query
        t["refId"] = self.refId
        t["resultFormat"] = self.resultFormat

        if grafana_version.startswith("3") or grafana_version.startswith("4"):
            t["policy"] = self.policy
            grp_has_time = None
            grp_has_fill = None
            grpBy = []
            for g in self.groupBy:
                if g["type"] == "time":
                    grp_has_time = g
                elif g["type"] == "fill":
                    grp_has_fill = g
            if not grp_has_time:
                grpBy.append({'type': 'time', 'params': ['$interval']})
            else:
                grpBy.append(grp_has_time)
            for g in self.groupBy:
                if g["type"] not in ("time", "fill"):
                    grpBy.append(g)
            if not grp_has_fill:
                grpBy.append({'type': 'fill', 'params': ['null']})
            else:
                grpBy.append(grp_has_fill)

            t["groupBy"] = grpBy
            has_field = False
            has_func = False
            newselect = []
            if len(self.select[0]) > 0:
                for s in self.select:
                    news = []
                    for elem in s:
                        if elem["type"] == "field":
                            has_field = True
                            news.append(elem)
                        if elem["type"] != "field":
                            has_func = True
                            news.append(elem)
                    if not has_field:
                        news.append({ "params": [ "value" ], "type": "field" })
                    if not has_func:
                        news.append({ "params": [], "type": "mean" })
                    newselect.append(news)
            else:
                news = []
                news.append({ "params": [ "value" ], "type": "field" })
                news.append({ "params": [], "type": "mean" })
                newselect.append(news)
            t["select"] = newselect
        else:
            grp_has_time = False
            grp_has_fill = False
            for g in self.groupBy:
                if g["type"] == "time":
                    grp_has_time = True
                elif g["type"] == "fill":
                    grp_has_fill = True
            if not grp_has_time:
                t["groupBy"].append({'type': 'time', 'params': ['$interval']})
            if not grp_has_fill:
                t["groupBy"].append({'type': 'fill', 'params': ['null']})
            has_field = False
            has_func = False
            for s in self.select[0]:
                if s["type"] == "field":
                    has_field = True
                if s["type"] != "field" and s["type"] != "fill":
                    has_func = True
            sel = [[]]
            if not has_field:
                sel[0].append({ "params": [ "value" ], "type": "field" })
            if not has_func:
                sel[0].append({ "params": [], "type": "mean" })
            for s in self.select:
                sel[0].append(s)
                #t["select"].append({ "params": [], "type": "mean" })
            #if not has_field:
                #t["select"].append({ "params": [ "value" ], "type": "field" })
                #t["select"] =  + t["select"]
            t["select"] = sel
        if len(self.query) == 0:
            field = "value"
            func = "mean"
            func_params = ""
            for s in self.select[0]:
                if s["type"] == "field":
                    field = ",".join(s["params"])
                else:
                    func = s["type"]
                    if len(s["params"]) > 0:
                        func_params = "," + ",".join(s["params"])
            t["query"] = "SELECT %s(\"%s\"%s) FROM \"%s\" WHERE $timeFilter" % (func, field, func_params, self.measurement,)
            filt = ""
            for s in t["tags"]:
                op = s["operator"]
                val = s["value"]
                key = s["key"]

                if val[0] == "$" and val[-1] != "$":
                    val += "$"

                if op in ["=~", "!~"]:
                    if val[0] != "/":
                        val = "/^"+val
                    if val[-1] != "/":
                        val += "$/"
                if s.has_key("condition"):
                    filt += "%s %s %s %s " % (s["condition"], key, op, val,)
                else:
                    filt += "%s %s %s " % (key, op, val,)

            if len(filt) > 0:
                t["query"] += " AND %s" % (filt,)
            if len(self.groupBy) > 0:
                gBy = " GROUP BY "
                gBy_items = []
                for g in t["groupBy"]:
                    if g["type"] == "time":
                        gBy_items.append("time(%s)" % g["params"][0])
                    elif g["type"] == "fill":
                        gBy_items.append("fill(%s)" % g["params"][0])
                    elif g["type"] == "tag":
                        gBy_items.append("\"%s\"" % g["params"][0])
                gBy += ", ".join(gBy_items)
                t["query"] += gBy
            #t["query"] = t["query"] + ";"
        if grafana_version.startswith("4"):
            t["policy"] = self.policy
            t["rawQuery"] = self.rawQuery
        return t
    def get_json(self):
        """
        Returns a JSON string with the Target object's configuration.

        :return JSON string with the Target object's settings
        """
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        t = self.get()
        s = "Target(%s, dsType=\"%s\", alias=\"%s\", " % (t["measurement"], t["dsType"], t["alias"],)

        s += "tags=[%s], " % (", ".join([str(a) for a in t["tags"]]),)
        s += "groupBy=[%s], " % (", ".join([str(g) for g in t["groupBy"]]),)
        s += "select=[%s], " % (", ".join([str(s) for s in t["select"]]),)
        s += "query=\"%s\", resultFormat=\"%s\"," % (t["query"], t["resultFormat"],)
        if grafana_version.startswith("4"):
            s += "policy=\"%s\", rawQuery=\"%s\"," % (t["policy"], str(t["rawQuery"]),)
        return s
    def set_dsType(self, dsType):
        """
        Set data source type.

        :param dsType: Valid identifier string for Grafana data source types. Currently no validity checks
        :return True/False
        """
        debug_print("Target: set_dsType(%s)" % str(dsType))
        if not isinstance(dsType, str):
            try:
                dsType = str(dsType)
            except ValueError:
                return False
        self.dsType = dsType
        return True
    def set_refId(self, refId):
        """
        Set reference identifier (refId).

        :param refId: Reference identifier string(!) like 'A','B'
        :return True/False
        """
        debug_print("Target: set_refId(%s)" % str(refId))
        if not isinstance(refId, str):
            try:
                refId = str(refId)
            except ValueError:
                return False
        self.refId = refId
        return True
    def set_alias(self, alias):
        """
        Set alias for this Target in panel's legend.

        TODO: Warn if alias contains [[tag_<tagname>]] but no valid entry in groupBy exists

        :param alias: Alias for this Target
        :return True/False
        """
        debug_print("Target: set_alias(%s)" % str(alias))
        if not isinstance(alias, str):
            try:
                alias = str(alias)
            except ValueError:
                return False
        self.alias = alias
        return True
    def set_resultFormat(self, fmt):
        """
        Set result format for this Target.

        TODO: Add missing valid result formats

        :param fmt: Result format. Currently only "time_series" allowed
        :return True/False
        """
        debug_print("Target: set_resultFormat(%s)" % str(fmt))
        if fmt in self.validResultFormat:
            self.resultFormat = fmt
            return True
        return False
    def add_tag(self, key, value, operator='=', condition='AND'):
        """
        Add a tag to this target.
        Performs some sanitation by adding missing trailing $ for dashboard tags or add missing / around the value if operator is a regex operator.

        :param key: DB key
        :param value: DB value
        :param operator: A valid operator like '=' or '=~'
        :param condition: A valid condition like 'AND' or 'OR'
        :return True/False
        """
        debug_print("Target: add_tag(%s, %s, %s, %s)" % (str(key),str(value),str(operator),str(condition),))
        try:
            val = value
            if val[0] == "$" and val[-1] != "$":
                val += "$"

            if operator in ["=~", "!~"]:
                if val[0] != "/":
                    val = "/"+val
                if val[-1] != "/":
                    val += "/"
            if len(self.tags) == 0:
                tag = {'key': key, 'value': val, 'operator': operator}
            else:
                tag = {'key': key, 'value': val, 'operator': operator, 'condition': condition}
            self.tags.append(tag)
            return True
        except:
            pass
        return False
    def add_select(self, sel_type, sel_params):
        """
        Add a select configuration for this Target. Duplicated additions are discarded

        :param sel_type: Type of select like 'field' or any valid function
        :param sel_params: Parameters of select like 'value' for 'field' or function arguments. If parameter is not a list, the parameter is put in one.
        :return True/False
        """
        debug_print("Target: add_select(%s, %s)" % (str(sel_type), str(sel_params),))
        if not isinstance(sel_params, list):
            sel_params = [sel_params]
        s = { "params": sel_params, "type": sel_type }
        if not s in self.select[0]:
            self.select[0].append(s)
            return True
        return False
    def add_groupBy(self, grp_type, grp_params):
        """
        Add a groupBy configuration for this Target. Duplicated additions are discarded

        :param sel_type: Type of groupBy options. Valid types are 'fill', 'time' and 'tag'.
        :param sel_params: Parameter to the groupBy type.
        :return True/False
        """
        debug_print("Target: add_groupBy(%s, %s)" % (str(grp_type), str(grp_params),))
        if grp_type not in self.validGroupBy:
            return False
        if grp_type != 'tag':
            for g in self.groupBy:
                if g["type"] == grp_type:
                    g["params"] = grp_params
                    return True
        else:
            if grp_params[0] == "$" and grp_params[-1] != "$":
                grp_params += "$"
            #grp_params = "/"+grp_params+"/"
        d = {'type': grp_type, 'params': [grp_params]}
        if d not in self.groupBy:
            self.groupBy.append(d)
            return True
        return False
    def read_json(self, j):
        """
        Configure Target object according to settings in JSON document describing a Target

        :param sel_type: Type of groupBy options. Valid types are 'fill', 'time' and 'tag'.
        :param sel_params: Parameter to the groupBy type.
        :return True/False
        """
        if isinstance(j, str):
            try:
                j = json.loads(j)
            except Exception as e:
                print("Cannot read JSON: %s" % e)
                return False
        if j.has_key("resultFormat"):
            self.set_resultFormat(j["resultFormat"])
        if j.has_key("alias"):
            self.set_alias(j["alias"])
        if j.has_key("refId"):
            self.set_refId(j["refId"])
        if j.has_key("dsType"):
            self.set_dsType(j["dsType"])
        if j.has_key("query"):
            self.query = j["query"]
        if j.has_key("policy"):
            self.policy = j["policy"]
        if j.has_key("measurement"):
            self.measurement = j["measurement"]
        if j.has_key("tags"):
            self.tags = []
            if isinstance(j["tags"], list):
                for t in j["tags"]:
                    key = None
                    value = None
                    operator = "="
                    if t.has_key("key") and t.has_key("value"):
                        key = t["key"]
                        value = t["value"]
                    else:
                        print "Invalid tag %s, Format is {'key': '', 'value': '', 'operator': '', 'condition': ''}" % str(t)
                        continue
                    if t.has_key("operator"):
                        operator = t["operator"]
                    if t.has_key("condition"):
                        self.add_tag(key, value, operator=operator, condition=t["condition"])
                    else:
                        self.add_tag(key, value, operator=operator)
        if j.has_key("groupBy"):
            self.groupBy = []
            if isinstance(j["groupBy"], list):
                for gb in j["groupBy"]:
                    t = None
                    p = None
                    if gb.has_key("type"):
                        t = gb["type"]
                    if gb.has_key("params"):
                        p = gb["params"]
                    if not isinstance(p, list):
                        print "Invalid groupBy JSON %s, Format is {'type': '', 'params': []}" % str(gb)
                        continue
                    self.add_groupBy(t, p[0])
        if j.has_key("select"):
            self.select = [[]]
            if isinstance(j["select"], list):
                for sel in j["select"][0]:
                    t = None
                    p = None
                    if sel.has_key("type"):
                        t = sel["type"]
                    if sel.has_key("params"):
                        p = sel["params"]
                    if not isinstance(p, list):
                        print "Invalid select JSON %s, Format is {'type': '', 'params': []}" % str(sel)
                        continue
                    self.add_select(t, p)
        return True


class Tooltip(object):
    """
    Encapsulates tooltip configuration used in Grafana's graph panels
    """
    def __init__(self, shared=True, value_type="cumulative", sort=0, msResolution=True):
        self.shared = shared
        self.value_type = value_type
        self.sort = 0
        self.msResolution = msResolution
        self.validValueTypes = ["cumulative", "individual"]
    def set_shared(self, s):
        if isinstance(s, bool):
            self.shared = s
    def set_value_type(self, v):
        if (isinstance(v, str) or isinstance(v, unicode)) and str(v) in self.validValueTypes:
            self.value_type = v
            return True
        return False
    def set_sort(self, sort):
        if isinstance(sort, int) and (grafana_version.startswith("3") or grafana_version.startswith("4")):
            self.sort = sort
            return True
        return False
    def set_msResolution(self, msResolution):
        if isinstance(msResolution, bool) and (grafana_version.startswith("3") or grafana_version.startswith("4")):
            self.msResolution = msResolution
            return True
        return False
    def get(self):
        if grafana_version.startswith("2"):
            return {"shared" : self.shared, "value_type" : self.value_type}
        elif grafana_version.startswith("3"):
            return {"shared" : self.shared, "value_type" : self.value_type,
                    "sort" : self.sort, "msResolution" : self.msResolution}
        elif grafana_version.startswith("4"):
            return {"shared" : self.shared, "value_type" : self.value_type,
                    "sort" : self.sort}
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        return "Tooltip(shared=%s, value_type=\"%s\", sort=%d, msResolution=%s)" % (str(self.shared), self.value_type, self.sort, str(self.msResolution),)
    def read_json(self, j):
        if isinstance(j, str):
            j = json.loads(j)
        if j.has_key("shared"):
            self.set_shared(j["shared"])
        if j.has_key("value_type"):
            self.set_value_type(j["value_type"])
        if j.has_key("sort"):
            self.set_sort(j["sort"])
        if j.has_key("msResolution"):
            self.set_msResolution(j["msResolution"])

class Legend(object):
    def __init__(self, total=False, show=True, max=False, min=False, current=False,
                       values=False, avg=False, alignAsTable=False, rightSide=False,
                       sideWidth=None, hideEmpty=False):
        self.total=False
        self.show=True
        self.max=False
        self.min=False
        self.current=False
        self.values=False
        self.avg=False
        self.alignAsTable=False
        self.rightSide=False
        self.sideWidth=None
        self.hideEmpty = False
        self.set_total(total)
        self.set_show(show)
        self.set_max(max)
        self.set_min(min)
        self.set_current(current)
        self.set_values(values)
        self.set_avg(avg)
        self.set_alignAsTable(alignAsTable)
        self.set_rightSide(rightSide)
        self.set_sideWidth(sideWidth)
        self.set_hideEmpty(hideEmpty)
    def set_total(self, t):
        if isinstance(t, bool):
            self.total = t
            return True
        return False
    def set_show(self, s):
        if isinstance(s, bool):
            self.show = s
            return True
        return False
    def set_max(self, m):
        if isinstance(m, bool):
            self.max = m
            return True
        return False
    def set_min(self, m):
        if isinstance(m, bool):
            self.min = m
            return True
        return False
    def set_current(self, m):
        if isinstance(m, bool):
            self.current = m
            return True
        return False
    def set_values(self, m):
        if isinstance(m, bool):
            self.values = m
            return True
        return False
    def set_avg(self, m):
        if isinstance(m, bool):
            self.avg = m
            return True
        return False
    def set_alignAsTable(self, m):
        if isinstance(m, bool):
            self.alignAsTable = m
            return True
        return False
    def set_rightSide(self, m):
        if isinstance(m, bool):
            self.rightSide = m
            return True
        return False
    def set_hideEmpty(self, m):
        if isinstance(m, bool):
            self.hideEmpty = m
            return True
        return False
    def set_sideWidth(self, m):
        if not m or isinstance(m, int):
            self.sideWidth = m
            return True
        return False
    def get(self):
        d = {"total" : self.total, "show" : self.show, "max" : self.max,
                "min" : self.min, "current" : self.current, "values" : self.values,
                "avg" : self.avg, "alignAsTable" : self.alignAsTable,
                "rightSide" : self.rightSide}
        if grafana_version.startswith("4"):
            d.update({"hideEmpty" : self.hideEmpty})
            if self.sideWidth:
                d.update({"sideWidth" : self.sideWidth})
        return d
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        l = "Legend(total=%s, show=%s, max=%s, " % (self.total, self.show, self.max,)
        l += "min=%s, current=%s, values=%s, avg=%s, " %(self.min, self.current, self.values, self.avg,)
        l += "alignAsTable=%s, rightSide=%s," % (str(self.alignAsTable), str(self.rightSide))
        l += "hideEmpty=%s, sideWidth=%s)" % (str(self.hideEmpty), str(sideWidth),)
        return l
    def read_json(self, j):
        if isinstance(j, str):
            j = json.loads(j)
        if j.has_key("total"):
            self.set_total(j["total"])
        if j.has_key("show"):
            self.set_show(j["show"])
        if j.has_key("max"):
            self.set_max(j["max"])
        if j.has_key("min"):
            self.set_min(j["min"])
        if j.has_key("current"):
            self.set_current(j["current"])
        if j.has_key("values"):
            self.set_values(j["values"])
        if j.has_key("avg"):
            self.set_avg(j["avg"])
        if j.has_key("alignAsTable"):
            self.set_alignAsTable(j["alignAsTable"])
        if j.has_key("rightSide"):
            self.set_rightSide(j["rightSide"])
        if j.has_key("hideEmpty"):
            self.set_hideEmpty(j["hideEmpty"])
        if j.has_key("sideWidth"):
            self.set_sideWidth(j["sideWidth"])

class Grid(object):
    def __init__(self, leftMax=None, threshold2=None, rightLogBase=1, rightMax=None, threshold1=None,
                    leftLogBase=1, threshold2Color="rgba(234, 112, 112, 0.22)",rightMin=None,
                    threshold1Color="rgba(216, 200, 27, 0.27)", leftMin=None):
        self.validLogBases = [1, 2, 10, 32, 1024]
        self.leftMax = leftMax
        self.threshold2 = threshold2
        self.rightLogBase = rightLogBase
        self.rightMax = rightMax
        self.threshold1 = threshold1
        self.leftLogBase = leftLogBase
        self.threshold2Color = check_color(threshold2Color)
        self.rightMin = rightMin
        self.threshold1Color = check_color(threshold1Color)
        self.leftMin = leftMin
    def get(self):
        if grafana_version.startswith("2"):
            return {"leftMax" : self.leftMax, "threshold2" : self.threshold2,
                    "rightLogBase" : self.rightLogBase, "rightMax" : self.rightMax,
                    "threshold1" : self.threshold1, "leftLogBase" : self.leftLogBase,
                    "threshold2Color" : self.threshold2Color, "rightMin" : self.rightMin,
                    "threshold1Color" : self.threshold1Color, "leftMin" : self.leftMin}
        elif grafana_version.startswith("3"):
            return {"threshold1" : self.threshold1, "threshold2" : self.threshold2,
                    "threshold1Color" : self.threshold1Color,
                    "threshold2Color" : self.threshold2Color}
        elif grafana_version.startswith("4"):
            return {}
    def get_attrib(self):
        return {"leftMax" : self.leftMax, "threshold2" : self.threshold2,
                "rightLogBase" : self.rightLogBase, "rightMax" : self.rightMax,
                "threshold1" : self.threshold1, "leftLogBase" : self.leftLogBase,
                "threshold2Color" : self.threshold2Color, "rightMin" : self.rightMin,
                "threshold1Color" : self.threshold1Color, "leftMin" : self.leftMin}
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        return str(self.get())
    def read_json(self, j):
        if isinstance(j, str):
            j = json.loads(j)
        if j.has_key("leftMax"):
            self.set_leftMax(j["leftMax"])
        if j.has_key("threshold2"):
            self.set_threshold2(j["threshold2"])
        if j.has_key("rightLogBase"):
            self.set_rightLogBase(j["rightLogBase"])
        if j.has_key("rightMax"):
            self.set_rightMax(j["rightMax"])
        if j.has_key("threshold1"):
            self.set_threshold1(j["threshold1"])
        if j.has_key("leftLogBase"):
            self.set_leftLogBase(j["leftLogBase"])
        if j.has_key("threshold2Color"):
            self.set_threshold2Color(j["threshold2Color"])
        if j.has_key("rightMin"):
            self.set_rightMin(j["rightMin"])
        if j.has_key("threshold1Color"):
            self.set_threshold1Color(j["threshold1Color"])
        if j.has_key("leftMin"):
            self.set_leftMin(j["leftMin"])

panel_id = 1



class Panel(object):
    def __init__(self, span=12, editable=True, title="", description=None):
        global panel_id
        self.set_id(panel_id)
        panel_id += 1
        self.span = 12
        self.editable = True
        self.title = ""
        self.description = None
        self.set_span(span)
        self.set_title(title)
        self.set_editable(editable)
        self.set_description(description)
    def set_editable(self, b):
        debug_print("Panel: set_editable(%s)" % str(b))
        if isinstance(b, bool):
            self.editable = b
            return True
        return False
    def set_title(self, title):
        debug_print("Panel: set_title(%s)" % str(title))
        if isinstance(title, str) or isinstance(title, unicode):
            self.title = title
            return True
        return False
    def set_description(self, description):
        debug_print("Panel: set_description(%s)" % str(description))
        if description == None or isinstance(description, str) or isinstance(description, unicode):
            self.description = description
            return True
        return False
    def set_span(self, span):
        debug_print("Panel: set_span(%s)" % str(span))
        if isinstance(span, int) and span in range(1,13):
            self.span = span
            return True
        return False
    def set_id(self, i):
        debug_print("Panel: set_id(%s)" % str(i))
        if isinstance(i, int):
            self.id = i
            return True
        return False
    def set_datasource(self, datasource):
        pass
    def get(self):
        return {}
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        return str(self.get())
    def read_json(self, j):
        pass


class TablePanelStyle(object):
    pass

class TablePanelHiddenStyle(TablePanelStyle):
    def __init__(self, pattern="/.*/"):
        self.pattern = "/.*/"
        self.type = "hidden"
    def set_pattern(self, p):
        if isinstance(p, str) or isinstance(p, unicode):
            self.pattern = p
            return True
        return False
    def get(self):
        d = { "type": self.type, "pattern": self.pattern}
        return d
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j.has_key("type"):
            if j["type"] != 'hidden':
                print "No TablePanelHiddenStyle"
                return False
        if j.has_key("pattern"):
            self.set_pattern(j["pattern"])
        return True


class TablePanelDateStyle(TablePanelStyle):
    def __init__(self, pattern="Time", dateFormat="YYYY-MM-DD HH:mm:ss"):
        self.pattern = "Time"
        self.dateFormat = "YYYY-MM-DD HH:mm:ss"
        self.type = "date"
    def set_pattern(self, p):
        if isinstance(p, str) or isinstance(p, unicode):
            self.pattern = p
            return True
        return False
    def set_dateFormat(self, p):
        if isinstance(p, str) or isinstance(p, unicode):
            self.dateFormat = p
            return True
        return False
    def get(self):
        d = { "type": self.type, "pattern": self.pattern, "dateFormat": self.dateFormat}
        return d
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j.has_key("type"):
            if j["type"] != 'date':
                print "No TablePanelDateStyle"
                return False
        if j.has_key("pattern"):
            self.set_pattern(j["pattern"])
        if j.has_key("dateFormat"):
            self.set_dateFormat(j["dateFormat"])
        return True

class TablePanelStringStyle(TablePanelStyle):
    def __init__(self, pattern="/.*/", sanitize=False):
        self.pattern = "/.*/"
        self.sanitize = False
        self.type = "string"
    def set_pattern(self, p):
        debug_print("TablePanelStringStyle: set_pattern(%s)" % str(p))
        if isinstance(p, str) or isinstance(p, unicode):
            self.pattern = p
            return True
        return False
    def set_sanitize(self, t):
        debug_print("TablePanelStringStyle: set_sanitize(%s)" % str(t))
        if isinstance(t, bool):
            self.sanitize = t
            return True
        return False
    def get(self):
        d = { "type": self.type, "pattern": self.pattern, "sanitize": self.sanitize}
        return d
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j.has_key("type"):
            if j["type"] != 'number':
                print "No TablePanelNumberStyle"
                return False
        if j.has_key("pattern"):
            self.set_pattern(j["pattern"])
        if j.has_key("sanitize"):
            self.set_sanitize(j["sanitize"])
        return True

class TablePanelNumberStyle(TablePanelStyle):
    def __init__(self, unit="short", decimals=2, colors=[], colorMode=None, pattern="/.*/", thresholds=[]):
        self.unit = "short"
        self.type = "number"
        self.decimals = 2
        self.colors = []
        self.colorMode = None
        self.pattern = "/.*/"
        self.thresholds = []
        self.validColorModes = [None, "cell", "value", "row"]
        self.validYFormats = ['bytes', 'kbytes', 'mbytes', 'gbytes', 'bits',
                              'bps', 'Bps', 'short', 'joule', 'watt', 'kwatt',
                              'watth', 'ev', 'amp', 'volt'
                              'none', 'percent', 'ppm', 'dB', 'ns', 'us',
                              'ms', 's', 'hertz', 'pps',
                              'celsius', 'farenheit', 'humidity',
                              'pressurembar', 'pressurehpa',
                              'velocityms', 'velocitykmh', 'velocitymph', 'velocityknot']
    def set_unit(self, u):
        if isinstance(u, str) and u in self.validYFormats:
            self.unit = u
            return True
        return False
    def set_decimals(self, d):
        if isinstance(d, int):
            self.decimals = d
            return True
        return False
    def set_colorMode(self, m):
        if m in self.validColorModes:
            self.colorMode = m
            return True
        return False
    def set_pattern(self, p):
        if isinstance(p, str) or isinstance(p, unicode):
            self.pattern = p
            return True
        return False
    def set_thresholds(self, t):
         if isinstance(t, list):
            self.thresholds = t
            return True
         return False
    def set_colors(self, colors):
        valid = False
        if isinstance(colors, list):
            valid = True
        for c in colors:
            if not check_color(c):
                valid = False
        if valid:
            self.colors = c
            return True
        return False
    def get(self):
        c = self.colors
        if len(c) == 0:
            c = ["rgba(245, 54, 54, 0.9)", "rgba(237, 129, 40, 0.89)", "rgba(50, 172, 45, 0.97)"]
        d = { "unit": self.unit, "type": self.type, "decimals": self.decimals, "colors": c,
              "colorMode": self.colorMode, "pattern": self.pattern, "thresholds": self.thresholds}
        return d
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j.has_key("type"):
            if j["type"] != 'number':
                print "No TablePanelNumberStyle"
                return False
        if j.has_key("pattern"):
            self.set_pattern(j["pattern"])
        if j.has_key("unit"):
            self.set_unit(j["unit"])
        if j.has_key("decimals"):
            self.set_decimals(j["decimals"])
        if j.has_key("colorMode"):
            self.set_colorMode(j["colorMode"])
        if j.has_key("thresholds"):
            self.set_thresholds(j["thresholds"])
        if j.has_key("colors"):
            self.set_colors(j["colors"])
        return True

class TablePanel(Panel):
    def __init__(self, title="default title", transform="timeseries_to_columns", pageSize=None,
                       styles=[], span=12, editable=True, error=False,
                       links=[], transparent=False, repeat=None, minSpan=None,
                       description=None, showHeader=True, scroll=True, fontSize="100%",
                       columns=[]):
        Panel.__init__(self, span=span, editable=editable, title=title, description=description)
        self.type = 'table'
        self.validTransform = ["timeseries_to_columns", "timeseries_to_rows", "timeseries_aggregations", "annotations", "table", "json"]
        self.validFontSizes = ['20%', '30%','50%','70%','80%','100%', '110%', '120%', '150%', '170%', '200%']
        self.pageSize = None
        self.fontSize = "100%"
        self.showHeader = True
        self.transparent = False
        self.targets = []
        self.styles = []
        self.columns = []
        self.scroll = True
        self.error = False
        self.datasource = ""

        self.set_transform(transform)
        self.set_pageSize(pageSize)
        self.set_showHeader(showHeader)
        self.set_transparent(transparent)
        self.set_scroll(scroll)
        self.set_fontSize(fontSize)
        self.set_error(error)
        self.set_datasource(datasource)
    def set_transform(self, t):
        debug_print("TablePanel: set_transform(%s)" % str(t))
        if isinstance(t, str) and t in self.validTransform:
            self.transform = t
            return True
        return False
    def set_fontSize(self, t):
        debug_print("TablePanel: set_fontSize(%s)" % str(t))
        if isinstance(t, str) and t in self.validFontSizes:
            self.fontSize = t
            return True
        return False
    def set_pageSize(self, t):
        debug_print("TablePanel: set_pageSize(%s)" % str(t))
        if not t or isinstance(t, int):
            self.pageSize = t
            return True
        return False
    def set_datasource(self, t):
        debug_print("TablePanel: set_datasource(%s)" % str(t))
        if isinstance(t, str) or isinstance(t, unicode):
            self.datasource = t
            return True
        return False
    def set_error(self, t):
        debug_print("TablePanel: set_error(%s)" % str(t))
        if isinstance(t, bool):
            self.error = t
            return True
        return False
    def set_showHeader(self, t):
        debug_print("TablePanel: set_showHeader(%s)" % str(t))
        if isinstance(t, bool):
            self.showHeader = t
            return True
        return False
    def set_scroll(self, t):
        debug_print("TablePanel: set_scroll(%s)" % str(t))
        if isinstance(t, bool):
            self.scroll = t
            return True
        return False
    def set_transparent(self, t):
        debug_print("TablePanel: set_transparent(%s)" % str(t))
        if isinstance(t, bool):
            self.transparent = t
            return True
        return False
    def add_style(self, s):
        debug_print("TablePanel: add_style(%s)" % str(s))
        if isinstance(s, TablePanelStyle):
            self.styles.append(s)
    def get(self):
        d = { "id": self.id, "title": self.title, "span": self.span, "type": self.type,
              "targets": [ t.get for t in self.targets], "transform": self.transform,
              "pageSize": self.pageSize, "showHeader": self.showHeader, "columns": self.columns,
              "scroll": self.scroll, "fontSize": self.fontSize, "sort": { "col": 0, "desc": True },
              "styles": [ s.get() for s in self.styles], "datasource" : self.datasource}
        return d
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j.has_key("type"):
            if j["type"] != 'table':
                print "No TablePanel"
                return False
        if j.has_key("title"):
            self.set_title(j["title"])
        if j.has_key("id"):
            self.set_id(j["id"])
        if j.has_key("span"):
            self.set_span(j["span"])
        if j.has_key("transform"):
            self.set_transform(j["transform"])
        if j.has_key("pageSize"):
            self.set_pageSize(j["pageSize"])
        if j.has_key("showHeader"):
            self.set_showHeader(j["showHeader"])
        if j.has_key("scroll"):
            self.set_scroll(j["scroll"])
        if j.has_key("fontSize"):
            self.set_fontSize(j["fontSize"])
        if j.has_key("datasource"):
            self.set_datasource(j["datasource"])
        if j.has_key("targets"):
            for tdict in j["targets"]:
                t = Target()
                t.read_json(tdict)
                self.targets.append(t)
        if j.has_key("columns"):
            for cdict in j["columns"]:
                self.columns.append(cdict)
        if j.has_key("styles"):
            for s in j["styles"]:
                t = None
                if s["type"] == "number":
                    t = TablePanelNumberStyle()
                elif s["type"] == "string":
                    t = TablePanelStringStyle()
                elif s["type"] == "hidden":
                    t = TablePanelHiddenStyle()
                elif s["type"] == "date":
                    t = TablePanelDateStyle()
                t.read_json(s)
                self.add_style(t)
        return True


class TextPanel(Panel):
    def __init__(self, title="default title", mode="markdown", content="",
                       style={}, span=12, editable=True, error=False,
                       links=[], transparent=False, repeat=None, minSpan=None,
                       description=None):
        Panel.__init__(self, span=span, editable=editable, title=title, description=description)
        self.set_mode(mode)
        self.set_content(content)
        self.set_style(style)
        self.set_error(error)
        self.set_repeat(repeat)
        if isinstance(links, list):
            self.links = []
            for l in links:
                if l["type"] == "absolute":
                    self.add_link(title=l["title"], typ="absolute", url=l["url"])
                elif l["type"] == "dashboard":
                    self.add_link(title=l["title"], typ="dashboard", dashboard=l["dashboard"])

        self.set_transparent(transparent)
        self.set_minSpan(minSpan)
        self.type = 'text'
    def set_mode(self, m):
        debug_print("TextPanel: set_mode(%s)" % str(m))
        if str(m) in ['html', 'markdown', 'text']:
            self.mode = str(m)
            return True
        return False
    def set_title(self, title):
        debug_print("TextPanel: set_title(%s)" % str(title))
        if isinstance(title, str) or isinstance(title, unicode):
            self.title = title
            return True
        return False
    def set_content(self, content):
        debug_print("TextPanel: set_content(%s)" % str(content))
        if isinstance(content, str) or isinstance(content, unicode):
            self.content = str(content)
            return True
        return False
    def set_error(self, error):
        debug_print("TextPanel: set_error(%s)" % str(error))
        if isinstance(error, bool):
            self.error = error
            return True
        return False
    def set_transparent(self, transparent):
        debug_print("TextPanel: set_transparent(%s)" % str(transparent))
        if isinstance(transparent, bool):
            self.transparent = transparent
            return True
        return False
    def set_minSpan(self, minSpan):
        debug_print("TextPanel: set_minSpan(%s)" % str(minSpan))
        if minSpan == None or isinstance(minSpan, int):
            self.minSpan = minSpan
            return True
        return False
    def set_repeat(self, repeat):
        debug_print("TextPanel: set_repeat(%s)" % str(repeat))
        if repeat == None or isinstance(repeat, str) or isinstance(repeat, unicode):
            self.repeat = repeat
            return True
        return False
    def set_style(self, style):
        debug_print("TextPanel: set_style(%s)" % str(style))
        if isinstance(style, dict):
            self.style = style
            return True
        return False
    def add_link(self, title="", typ="dashboard", url=None, dashboard=None):
        debug_print("TextPanel: add_link(%s, %s, %s, %s)" % (str(title), str(typ), str(url), str(dashboard),))
        if typ not in ["absolute", "dashboard"]:
            print "Invalid link type"
            return False
        if typ == "absolute" and not url:
            print "For type 'absolute' an url is required"
            return False
        elif typ == "absolute":
            self.links.append({
              "type": typ,
              "url": url,
              "title": title,

            })
        if typ == "dashboard" and not dashboard:
            print "For type 'dashboard' a dashboard name is required"
            return False
        elif typ == "dashboard":
            self.links.append({
              "type": typ,
              "dashboard": dashboard,
              "title": title,
              "dashUri" : "db/"+dashboard.lower().replace("_","-")
            })
        return True
    def get(self):
        d = {"title" : self.title, "mode" : self.mode,
                "content" : self.content, "style" : self.style,
                "span" : self.span, "editable": self.editable,
                "id": self.id, "type" : self.type, "error": self.error,
                "links" : self.links, "transparent" : self.transparent,
                "repeat" : self.repeat, "minSpan" : self.minSpan}
        return d
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        links = ""
        for l in self.links:
            if l["type"] == "absolute":
                links += "{\"type\" : \"absolute\", \"title\" : \"%s\", \"url\" : \"%s\"}" % (l["title"], l["url"],)
            elif l["type"] == "dashboard":
                links += "{\"type\" : \"dashboard\", \"title\" : \"%s\", \"dashboard\" : \"%s\"}" % (l["title"], l["dashboard"],)
        p = "Textpanel(title=\"%s\", mode=\"%s\", content=\"%s\", " % (self.title, str(self.mode), self.content,)
        p += "style=%s, span=%d, editable=%s, " % (str(self.style), int(self.span), str(self.editable),)
        p += "links=[%s], transparent=%s, " % (links, str(self.transparent), )
        if self.repeat:
            p += "repeat=\"%s\", " % str(self.repeat)
        else:
            p += "repeat=None, "
        p += "minSpan=%s)" % str(self.minSpan)
        return p
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j.has_key("type"):
            if j["type"] != 'text':
                print "No TextPanel"
                return False
        if j.has_key("title"):
            self.set_title(j["title"])
        if j.has_key("mode"):
            self.set_mode(j["mode"])
        if j.has_key("content"):
            self.set_content(j["content"])
        if j.has_key("style"):
            self.set_style(j["style"])
        if j.has_key("span"):
            self.set_span(j["span"])
        if j.has_key("editable"):
            self.set_editable(j["editable"])
        if j.has_key("transparent"):
            self.set_transparent(j["transparent"])
        if j.has_key("repeat"):
            self.set_repeat(j["repeat"])
        if j.has_key("minSpan"):
            self.set_repeat(j["minSpan"])
        if j.has_key("description"):
            self.set_description(j["description"])
        if j.has_key("links"):
            for l in j["links"]:
                if l["type"] == "absolute":
                    self.add_link(title=l["title"], typ="absolute", url=l["url"])
                elif l["type"] == "dashboard":
                    self.add_link(title=l["title"], typ="dashboard", dashboard=l["dashboard"])
        if j.has_key("id"):
            self.id = j["id"]
        return True

class PlotPanel(Panel):
    def __init__(self, targets=[], datasource="", title="", error=False,
                       editable=True, isNew=True, links=[], span=12,
                       description=None):
        Panel.__init__(self, span=span, editable=editable, title=title, description=description)
        self.links = links
        self.isNew = isNew
        self.error = error
        self.datasource = datasource
        self.targets = targets
    def set_isNew(self, b):
        debug_print("PlotPanel: set_isNew(%s)" % str(b))
        if isinstance(b, bool):
            self.isNew = b
    def set_error(self, b):
        debug_print("PlotPanel: set_error(%s)" % str(b))
        if isinstance(b, bool):
            self.error = b
    def set_datasource(self, d):
        debug_print("PlotPanel: set_datasource(%s)" % str(d))
        if isinstance(d, str) or isinstance(d, unicode):
            self.datasource = d
    def set_title(self, t):
        debug_print("PlotPanel: set_title(%s)" % str(t))
        self.title = t
    def add_link(self, l):
        debug_print("PlotPanel: add_link(%s)" % str(l))
        self.links.append(l)
    def add_target(self, t):
        debug_print("PlotPanel: add_target(%s)" % str(t))
        if isinstance(t, Target):
            x = copy.deepcopy(t)
            x.set_refId(chr(ord('A')+len(self.targets)))
            self.targets.append(x)
    def get(self):
        d = {"datasource" : self.datasource, "title" : self.title,
                "error" : self.error, "isNew" : self.isNew,
                "span" : self.span,
                "id": self.id, "targets" : [t.get() for t in self.targets ]}
        if not grafana_version.startswith("4"):
            d.update({"isNew" : self.isNew,
                      "editable": self.editable})
        return d
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        p = "PlotPanel(targets=%s, datasource=\"%s\", " % (str([t.__repr__() for t in self.targets ]), self.datasource, )
        p += "title=\"%s\", error=%s, " % (self.title, str(self.error), )
        p += "editable=%s, isNew=%s, " % (str(self.editable), str(self.isNew), )
        p += "links=%s, span=%d)"  % (str(self.links), int(self.span), )
        return p
    def read_json(self, j):
        if isinstance(j, str):
            j = json.loads(j)
        if j.has_key("datasource"):
            self.set_datasource(j["datasource"])
        if j.has_key("title"):
            self.set_title(j["title"])
        if j.has_key("error"):
            self.set_error(j["error"])
        if j.has_key("isNew"):
            self.set_isNew(j["isNew"])
        if j.has_key("links"):
            for l in j["links"]:
                self.add_link(l)
        if j.has_key("span"):
            self.set_span(j["span"])
        if j.has_key("editable"):
            self.set_editable(j["editable"])
        if j.has_key("id"):
            self.id = j["id"]
        if j.has_key("description"):
            self.set_description(j["description"])


class SeriesOverride(object):
    def __init__(self, alias):
        self.alias = alias
        self.bars = None
        self.lines = None
        self.fill = None
        self.linewidth = None
        self.fillBelowTo = None
        self.steppedLine = None
        self.points = None
        self.pointradius = None
        self.stack = None
        self.yaxis = None
        self.zindex = None
    def get(self):
        d = {"alias" : self.alias}
        if self.bars and isinstance(self.bars, bool):
            d.update({"bars" : self.bars})
        if self.lines and isinstance(self.lines, bool):
            d.update({"lines" : self.lines})
        if self.fill and isinstance(self.fill, int) and self.fill in range(11):
            d.update({"fill" : self.fill})
        if self.linewidth and isinstance(self.linewidth, int) and self.linewidth in range(11):
            d.update({"linewidth" : self.linewidth})
        if self.fillBelowTo and isinstance(self.linewidth, str):
            d.update({"fillBelowTo" : self.fillBelowTo})
        if isinstance(self.steppedLine, bool):
            d.update({"steppedLine" : self.steppedLine})
        if isinstance(self.points, bool):
            d.update({"points" : self.points})
        if self.pointradius and isinstance(self.linewidth, int) and self.pointradius in range(1,6):
            d.update({"pointradius" : self.pointradius})
        if self.stack and self.stack in [True, False, 2, 3, 4, 5]:
            d.update({"stack" : self.stack})
        if self.yaxis and self.yaxis in [1, 2]:
            d.update({"yaxis" : self.yaxis})
        if self.zindex and isinstance(self.linewidth, int) and self.linewidth in range(-3,4):
            d.update({"zindex" : self.zindex})
        return d
    def set_bars(self, b):
        debug_print("SeriesOverride: set_bars(%s)" % str(b))
        if isinstance(b, bool):
            self.bars = b
        else:
            self.bars = None
    def set_lines(self, b):
        debug_print("SeriesOverride: set_lines(%s)" % str(b))
        if isinstance(b, bool):
            self.lines = b
        else:
            self.lines = None
    def set_steppedLine(self, b):
        debug_print("SeriesOverride: set_steppedLine(%s)" % str(b))
        if isinstance(b, bool):
            self.steppedLine = b
        else:
            self.steppedLine = None
    def set_points(self, b):
        debug_print("SeriesOverride: set_points(%s)" % str(b))
        if isinstance(b, bool):
            self.points = b
        else:
            self.points = None
    def set_stack(self, b):
        debug_print("SeriesOverride: set_stack(%s)" % str(b))
        if isinstance(b, bool):
            self.stack = b
        elif isinstance(b, int) and b in range(2,6):
            self.stack = b
        else:
            self.stack = None
    def set_pointradius(self, b):
        debug_print("SeriesOverride: set_pointradius(%s)" % str(b))
        if isinstance(b, int) and b in range(1,6):
            self.pointradius = b
        else:
            self.pointradius = None
    def set_yaxis(self, b):
        debug_print("SeriesOverride: set_yaxis(%s)" % str(b))
        if isinstance(b, int) and b in [1, 2]:
            self.yaxis = b
        else:
            self.yaxis = None
    def set_zindex(self, b):
        debug_print("SeriesOverride: set_zindex(%s)" % str(b))
        if isinstance(b, int) and b in range(-3,4):
            self.zindex = b
        else:
            self.zindex = None
    def set_linewidth(self, b):
        debug_print("SeriesOverride: set_linewidth(%s)" % str(b))
        if isinstance(b, int) and b in range(11):
            self.linewidth = b
        else:
            self.linewidth = None
    def set_fill(self, b):
        debug_print("SeriesOverride: set_fill(%s)" % str(b))
        if isinstance(b, int) and b in range(11):
            self.fill = b
        else:
            self.fill = None
    def set_fillBelowTo(self, b):
        debug_print("SeriesOverride: set_fillBelowTo(%s)" % str(b))
        if isinstance(b, str):
            self.alias = b
            self.fillBelowTo = b
            self.lines = False
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        return str(self.get())
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j.has_key("fillBelowTo"):
            self.set_fillBelowTo(j["fillBelowTo"])
        if j.has_key("fill"):
            self.set_fill(j["fill"])
        if j.has_key("linewidth"):
            self.set_linewidth(j["linewidth"])
        if j.has_key("zindex"):
            self.set_zindex(j["zindex"])
        if j.has_key("yaxis"):
            self.set_yaxis(j["yaxis"])
        if j.has_key("pointradius"):
            self.set_pointradius(j["pointradius"])
        if j.has_key("stack"):
            self.set_stack(j["stack"])
        if j.has_key("points"):
            self.set_points(j["points"])
        if j.has_key("steppedLine"):
            self.set_steppedLine(j["steppedLine"])
        if j.has_key("lines"):
            self.set_lines(j["lines"])
        if j.has_key("bars"):
            self.set_bars(j["bars"])
        if j.has_key("alias"):
            self.alias = j["alias"]


class HistogramPanel(PlotPanel):
    def __init__(self, title, isNew=True, targets=[], links=[], datasource="",
                 error=False, span=12, editable=True, renderer="flot", bucketMode="size",
                 xaxis=True, tooltip=Tooltip(), grid=Grid(), stack=False,
                 nullPointMode="connected", seriesOverrides=[], aliasColors={},
                 transparent=False, hideTimeOverride=False, timeFrom=None,
                 timeShift=None, bucketSize="", minValue="", maxValue="",
                 legend=Legend(), description=None):
        PlotPanel.__init__(self, title=title, isNew=isNew, targets=targets, links=links,
                         datasource=datasource, error=error, span=span, editable=editable,
                         description=description)
        self.validRenderer = ["png", "flot"]
        self.validBucketModes = ["size", "count"]
        self.validNullPointModes = ["connected", 'null as zero', 'null']
        self.type = "mtanda-histogram-panel"

    def get(self):
        g = {
          "title": self.title,
          "error": self.error,
          "span": self.span,
          "editable": self.editable,
          "type": self.type,
          "isNew": self.isNew,
          "id": self.id,
          "targets": self.targets,
          "datasource": self.datasource,
          "renderer": self.renderer,
          "bucketMode": self.bucketMode,
          "grid": self.grid.get(),
          "lines": True,
          "fill": 1,
          "linewidth": 2,
          "points": False,
          "pointradius": 5,
          "bars": False,
          "stack": self.stack,
          "percentage": False,
          "legend": {
            "show": true,
            "values": false,
            "min": false,
            "max": false,
            "current": false,
            "total": false,
            "avg": false,
            "hideEmpty": true,
            "hideZero": true,
            "alignAsTable": true,
            "rightSide": false
          },
          "nullPointMode": self.nullPointMode,
          "steppedLine": False,
          "tooltip": self.tooltip.get(),
          "timeFrom": self.timeFrom,
          "timeShift": self.timeShift,
          "aliasColors": self.aliasColors,
          "seriesOverrides": self.seriesOverrides,
          "links": self.links,
          "bucketSize": self.bucketSize,
          "minValue": self.minValue,
          "maxValue": self.maxValue
        }
        if grafana_version.startswith("2"):
            if self.leftYAxisLabel:
                g.update({"leftYAxisLabel" : self.leftYAxisLabel})
            if self.rightYAxisLabel:
                g.update({"rightYAxisLabel" : self.rightYAxisLabel})
            yfmt = ["short","short"]
            if len(self.y_formats) > 0:
                yfmt = self.y_formats
            g.update({"y_formats" : yfmt, "x-axis" : self.xaxis, "y-axis" : self.yaxis})
        elif grafana_version.startswith("3") or grafana_version.startswith("4"):
            g.update({"xaxis" : { "show" : self.xaxis}})
            lfmt = "short"
            if len(self.y_formats) > 0:
                lfmt = self.y_formats[0]
            lefty = {"show" : self.yaxis, "logBase" : self.grid.leftLogBase,
                     "max" : self.grid.leftMax, "min" : self.grid.leftMin,
                     "format" : lfmt}
            if self.leftYAxisLabel:
                lefty.update({"label" : self.leftYAxisLabel})
            else:
                lefty.update({"label" : None})
            rfmt = "short"
            if len(self.y_formats) > 1:
                rfmt = self.y_formats[1]
            righty = {"show" : self.yaxis, "logBase" : self.grid.rightLogBase,
                     "max" : self.grid.rightMax, "min" : self.grid.rightMin,
                     "format" : rfmt}
            if self.rightYAxisLabel:
                righty.update({"label" : self.rightYAxisLabel})
            else:
                righty.update({"label" : None})
            g.update({"yaxes" : [lefty, righty]})

class GraphPanel(PlotPanel):
    def __init__(self, bars=False, links=[], isNew=True, nullPointMode="connected",
                       renderer="flot", linewidth=2, steppedLine=False, fill=1,
                       span=12, title="", tooltip=Tooltip(), targets=[],
                       seriesOverrides=[], percentage=False, xaxis=True,
                       error=False, editable=True, stack=False, yaxis=True,
                       timeShift=None, aliasColors={}, lines=True, points=False,
                       datasource="", pointradius=5, y_formats=[], legend=Legend(),
                       leftYAxisLabel=None, rightYAxisLabel=None, grid=Grid(),
                       transparent=False, hideTimeOverride=False, timeFrom=None,
                       thresholds=[], xaxisMode="time", xaxisName=None, xaxisValues=[],
                       description=None, decimals=None):
        self.validYFormats = ['bytes', 'kbytes', 'mbytes', 'gbytes', 'bits',
                              'bps', 'Bps', 'short', 'joule', 'watt', 'kwatt',
                              'watth', 'ev', 'amp', 'volt'
                              'none', 'percent', 'ppm', 'dB', 'ns', 'us',
                              'ms', 's', 'hertz', 'pps',
                              'celsius', 'farenheit', 'humidity',
                              'pressurembar', 'pressurehpa',
                              'velocityms', 'velocitykmh', 'velocitymph', 'velocityknot']
        self.validNullPointModes = ["connected", 'null as zero', 'null']
        self.validRenderer = ["png", "flot"]
        self.validXaxisModes = ["time", "series"]
        self.validThreadholdOps = ["gt", "lt"]
        self.validColorModes = ["custom", "ok", "critical", "warning"]
        PlotPanel.__init__(self, title=title, isNew=isNew, targets=targets, links=links,
                         datasource=datasource, error=error, span=span, editable=editable,
                         description=description)
        self.type = "graph"
        self.bars = False
        self.targets = []
        self.nullPointMode = "connected"
        self.renderer = "flot"
        self.linewidth = 2
        self.steppedLine = False
        self.fill = 1
        self.tooltip = Tooltip()
        self.seriesOverrides = []
        self.percentage = False
        self.xaxis = True
        self.yaxis = True
        self.stack = False
        self.timeShift = None
        self.aliasColors = {}
        self.lines = True
        self.points = False
        self.pointradius = 5
        self.decimals = None
        self.y_formats = []
        self.legend = Legend()
        self.leftYAxisLabel = None
        self.rightYAxisLabel = None
        self.grid = Grid()
        self.transparent = False
        self.hideTimeOverride = False
        self.timeFrom = None
        self.thresholds = []
        self.xaxisMode = "time"
        self.xaxisName = None
        self.xaxisValues = []
        self.set_nullPointMode(nullPointMode)
        self.set_bars(bars)
        self.set_renderer(renderer)
        self.set_linewidth(linewidth)
        self.set_steppedLine(steppedLine)
        self.set_fill(fill)
        self.seriesOverrides = seriesOverrides
        self.set_percentage(percentage)
        self.set_xaxis(xaxis)
        self.grid = grid
        self.tooltip = tooltip
        self.legend = legend
        self.set_stack(stack)
        self.set_yaxis(yaxis)
        self.aliasColors = aliasColors
        self.set_lines(lines)
        self.set_points( points)
        self.set_pointradius(pointradius)
        self.set_hideTimeOverride(hideTimeOverride)
        self.set_transparent(transparent)
        self.set_timeShift(timeShift)
        self.set_timeFrom(timeFrom)
        self.thresholds = []
        for t in thresholds:
            self.add_threshold(t)
        self.set_xaxisMode(xaxisMode)
        self.set_xaxisName(xaxisName)
        self.set_xaxisValues(xaxisValues)
        left = 'short'
        right = 'short'
        if len(y_formats) > 0:
            left = y_formats[0]
        if len(y_formats) > 1:
            right = y_formats[1]
        self.y_formats = ()
        self.set_y_formats(left, right)
        self.set_leftYAxisLabel(leftYAxisLabel)
        self.set_rightYAxisLabel(rightYAxisLabel)
    def set_nullPointMode(self, m):
        debug_print("GraphPanel: set_nullPointMode(%s)" % str(m))
        if str(m) in self.validNullPointModes:
            self.nullPointMode = m
            return True
        return False
    def add_seriesOverride(self, b):
        debug_print("GraphPanel: add_seriesOverride(%s)" % str(b))
        if isinstance(b, SeriesOverride):
            self.seriesOverrides.append(b)
            return True
        return False
    def set_bars(self, b):
        debug_print("GraphPanel: set_bars(%s)" % str(b))
        if isinstance(b, bool):
            self.bars = b
            return True
        return False
    def set_timeFrom(self, timeFrom):
        debug_print("GraphPanel: set_timeFrom(%s)" % str(timeFrom))
        if timeFrom == None or (isinstance(timeFrom, str) and timeFrom[-1] in time_limits.keys()):
            self.timeFrom = timeFrom
            return True
        return False
    def set_timeShift(self, timeShift):
        debug_print("GraphPanel: set_timeShift(%s)" % str(timeShift))
        if timeShift == None or (isinstance(timeShift, str) and timeShift[-1] in time_limits.keys()):
            self.timeShift = timeShift
            return True
        return False
    def set_hideTimeOverride(self, hideTimeOverride):
        debug_print("GraphPanel: set_hideTimeOverride(%s)" % str(hideTimeOverride))
        if isinstance(hideTimeOverride, bool):
            self.hideTimeOverride = hideTimeOverride
            return True
        return False
    def set_steppedLine(self, b):
        debug_print("GraphPanel: set_steppedLine(%s)" % str(b))
        if isinstance(b, bool):
            self.steppedLine = b
            return True
        return False
    def set_transparent(self, transparent):
        debug_print("GraphPanel: set_transparent(%s)" % str(transparent))
        if isinstance(transparent, bool):
            self.transparent = transparent
            return True
        return False
    def set_percentage(self, b):
        debug_print("GraphPanel: set_percentage(%s)" % str(b))
        if isinstance(b, bool):
            self.percentage = b
            return True
        return False
    def set_xaxis(self, b):
        debug_print("GraphPanel: set_xaxis(%s)" % str(b))
        if isinstance(b, bool):
            self.xaxis = b
            return True
        return False
    def set_yaxis(self, b):
        debug_print("GraphPanel: set_yaxis(%s)" % str(b))
        if isinstance(b, bool):
            self.yaxis = b
            return True
        return False
    def set_stack(self, b):
        debug_print("GraphPanel: set_stack(%s)" % str(b))
        if isinstance(b, bool):
            self.stack = b
            return True
        return False
    def set_lines(self, b):
        debug_print("GraphPanel: set_lines(%s)" % str(b))
        if isinstance(b, bool):
            self.lines = b
            return True
        return False
    def set_points(self, b):
        debug_print("GraphPanel: set_points(%s)" % str(b))
        if isinstance(b, bool):
            self.points = b
            return True
        return False
    def set_linewidth(self, b):
        debug_print("GraphPanel: set_linewidth(%s)" % str(b))
        if isinstance(b, int):
            self.linewidth = b
            return True
        return False
    def set_fill(self, b):
        debug_print("GraphPanel: set_fill(%s)" % str(b))
        if isinstance(b, int):
            self.fill = b
            return True
        return False
    def set_renderer(self, renderer):
        debug_print("GraphPanel: set_renderer(%s)" % str(renderer))
        if (isinstance(renderer, str) or isinstance(renderer, unicode)) and renderer in self.validRenderer:
            self.renderer = str(renderer)
            return True
        return False
    def set_y_formats(self, left, right):
        debug_print("GraphPanel: set_y_formats(%s, %s)" % (str(left), str(right),))
        retl = False
        retr = False
        newfmts = ['short', 'short']
        if left in self.validYFormats:
            newfmts[0] = left
            retl = True
        if right in self.validYFormats:
            newfmts[1] = right
            retr = True
        self.y_formats= tuple(newfmts)
        return retl and retr
    def set_pointradius(self, b):
        debug_print("GraphPanel: set_pointradius(%s)" % str(b))
        if isinstance(b, int):
            self.pointradius = b
            return True
        elif isinstance(b, str):
            try:
                self.pointradius = int(b)
                return True
            except:
                pass
        return False
    def _check_threshold(self, d):
        if not (d.has_key("op") and d.has_key("value") and d.has_key("colorMode")):
            return False
        if d["op"] not in self.validThreadholdOps:
            print("Threshold op not valid")
            return False
        if d["colorMode"] not in self.validColorModes:
            print("Color mode not valid")
            return False
        if d["colorMode"] == "custom" and d.has_key("line") and not d.has_key("lineColor"):
            print("Threshold uses custom color and line but no line color specified")
            return False
        if d["colorMode"] == "custom" and d.has_key("fill") and not d.has_key("fillColor"):
            print("Threshold uses custom color and fill but no fill color specified")
            return False
        if d.has_key("lineColor") and not check_color(d["lineColor"]):
            print("Line color not valid")
        if d.has_key("fillColor") and not check_color(d["fillColor"]):
            print("Fill color not valid")
        return True

    def add_threshold(self, d):
        debug_print("GraphPanel: add_threshold(%s)" % str(d))
        if isinstance(d, dict) and self._check_threshold(d):
            self.thresholds.append(d)
            return True
        elif isinstance(d, list):
            for i in d:
                if self._check_threshold(i):
                    self.thresholds.append(i)
            return True
        return False
    def set_grid(self, t):
        debug_print("GraphPanel: set_grid(%s)" % str(t))
        if isinstance(t, Grid):
            self.grid = t
            return True
        return False
    def set_tooltip(self, t):
        debug_print("GraphPanel: set_tooltip(%s)" % str(t))
        if isinstance(t, Tooltip):
            self.tooltip = t
            return True
        return False
    def set_legend(self, t):
        debug_print("GraphPanel: set_legend(%s)" % str(t))
        if isinstance(t, Legend):
            self.legend = t
            return True
        return False
    def set_xaxisValues(self, t):
        debug_print("GraphPanel: set_xaxisValues(%s)" % str(t))
        if isinstance(t, list):
            self.xaxisValues = t
            return True
        return False
    def set_decimals(self, t):
        debug_print("GraphPanel: set_decimals(%s)" % str(t))
        if not t or isinstance(t, int):
            self.decimals = t
            return True
        return False
    def set_xaxisMode(self, s):
        debug_print("GraphPanel: set_xaxisMode(%s)" % str(s))
        if (isinstance(s, str) or isinstance(s, unicode)) and str(s) in self.validXaxisModes:
            self.xaxisMode = s
            return True
        return False
    def set_xaxisName(self, s):
        debug_print("GraphPanel: set_xaxisName(%s)" % str(s))
        if s == None or isinstance(s, str) or isinstance(s, unicode):
            self.xaxisName = s
            return True
        return False
    def set_leftYAxisLabel(self, l):
        debug_print("GraphPanel: set_leftYAxisLabel(%s)" % str(l))
        self.leftYAxisLabel = l
    def set_rightYAxisLabel(self, l):
        debug_print("GraphPanel: set_rightYAxisLabel(%s)" % str(l))
        self.rightYAxisLabel = l
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j["type"] != "graph":
            print("No GraphPanel")
            return False
        if j.has_key("id"):
            self.id = j["id"]
        if j.has_key("title"):
            self.set_title(j["title"])
        if j.has_key("bars"):
            self.set_bars(j["bars"])
        if j.has_key("nullPointMode"):
            self.set_nullPointMode(j["nullPointMode"])
        if j.has_key("renderer"):
            self.set_renderer(j["renderer"])
        if j.has_key("linewidth"):
            self.set_linewidth(j["linewidth"])
        if j.has_key("steppedLine"):
            self.set_steppedLine(j["steppedLine"])
        if j.has_key("fill"):
            self.set_fill(j["fill"])
        if j.has_key("percentage"):
            self.set_percentage(j["percentage"])
        if j.has_key("xaxis"):
            self.set_xaxis(j["xaxis"])
        if j.has_key("stack"):
            self.set_stack(j["stack"])
        if j.has_key("yaxis"):
            self.set_yaxis(j["yaxis"])
        if j.has_key("decimals"):
            self.set_decimals(j["decimals"])
        if j.has_key("lines"):
            self.set_lines(j["lines"])
        if j.has_key("points"):
            self.set_points(j["points"])
        if j.has_key("pointradius"):
            self.set_pointradius(j["pointradius"])
        if j.has_key("hideTimeOverride"):
            self.set_hideTimeOverride(j["hideTimeOverride"])
        if j.has_key("transparent"):
            self.set_transparent(j["transparent"])
        if j.has_key("timeShift"):
            self.set_timeShift(j["timeShift"])
        if j.has_key("timeFrom"):
            self.set_timeFrom(j["timeFrom"])
        if j.has_key("xaxisMode"):
            self.set_xaxisMode(j["xaxisMode"])
        if j.has_key("xaxisName"):
            self.set_xaxisName(j["xaxisName"])
        if j.has_key("xaxisValues"):
            self.set_xaxisValues(j["xaxisValues"])
        if j.has_key("leftYAxisLabel"):
            self.set_leftYAxisLabel(j["leftYAxisLabel"])
        if j.has_key("rightYAxisLabel"):
            self.set_rightYAxisLabel(j["rightYAxisLabel"])
        if j.has_key("seriesOverrides"):
            for s in j["seriesOverrides"]:
                sc = SeriesOverride("")
                sc.read_json(s)
                self.add_seriesOverride(sc)
        if j.has_key("grid"):
            g = Grid()
            g.read_json(j["grid"])
            self.set_grid(g)
        if j.has_key("tooltip"):
            g = Tooltip()
            g. read_json(j["tooltip"])
            self.set_tooltip(g)
        if j.has_key("legend"):
            g = Legend()
            g.read_json(j["legend"])
            self.set_legend(g)
        if j.has_key("aliasColors"):
            self.aliasColors = j["aliasColors"]
        if j.has_key("thresholds"):
            for t in j["thresholds"]:
                self.add_threshold(t)
        if j.has_key("targets"):
            for t in j["targets"]:
                tar = Target("")
                tar.read_json(t)
                self.add_target(tar)
        if j.has_key("yaxes"):
            left = None
            right = None
            if j["yaxes"][0].has_key("format"):
                left = j["yaxes"][0]["format"]
            if j["yaxes"][1].has_key("format"):
                right = j["yaxes"][1]["format"]
            self.set_y_formats(left, right)
        return True
    def get(self):

        g = {"bars" : self.bars, "timeFrom" : self.timeFrom, "links" : self.links,
                "editable" : self.editable, "nullPointMode" : self.nullPointMode,
                "renderer" : self.renderer, "linewidth" : self.linewidth,
                "steppedLine" : self.steppedLine, "id" : self.id, "fill" : self.fill,
                "span" : self.span, "title" : self.title, "tooltip" : self.tooltip.get(),
                "targets" : [ t.get() for t in self.targets], "grid" : self.grid.get(),
                "seriesOverrides" : self.seriesOverrides, "percentage" : self.percentage,
                "type" : self.type, "error" : self.error,
                "legend" : self.legend.get(), "stack" : self.stack,
                "timeShift" : self.timeShift,
                "aliasColors" : self.aliasColors, "lines" : self.lines,
                "points" : self.points, "datasource" : self.datasource,
                "pointradius" : self.pointradius}
        if self.transparent:
            g.update({"transparent" : self.transparent})

        if grafana_version.startswith("2"):
            if self.leftYAxisLabel:
                g.update({"leftYAxisLabel" : self.leftYAxisLabel})
            if self.rightYAxisLabel:
                g.update({"rightYAxisLabel" : self.rightYAxisLabel})
            yfmt = ["short","short"]
            if len(self.y_formats) > 0:
                yfmt = self.y_formats
            g.update({"y_formats" : yfmt, "x-axis" : self.xaxis, "y-axis" : self.yaxis})
        elif grafana_version.startswith("3") or grafana_version.startswith("4"):
            xaxis = { "show" : self.xaxis}
            if grafana_version.startswith("4"):
                xaxis.update({"name" : self.xaxisName,
                              "mode" : self.xaxisMode,
                              "values": self.xaxisValues})
            g.update({"xaxis" : xaxis})
            lfmt = "short"
            if len(self.y_formats) > 0:
                lfmt = self.y_formats[0]
            grid = self.grid.get_attrib()
            lefty = {"show" : self.yaxis, "logBase" : grid["leftLogBase"],
                     "max" : grid["leftMax"], "min" : grid["leftMin"],
                     "format" : lfmt}
            if self.leftYAxisLabel:
                lefty.update({"label" : self.leftYAxisLabel})
            else:
                lefty.update({"label" : None})
            rfmt = "short"
            if len(self.y_formats) > 1:
                rfmt = self.y_formats[1]
            righty = {"show" : self.yaxis, "logBase" : grid["rightLogBase"],
                     "max" : grid["rightMax"], "min" : grid["rightMin"],
                     "format" : rfmt}
            if self.rightYAxisLabel:
                righty.update({"label" : self.rightYAxisLabel})
            else:
                righty.update({"label" : None})
            g.update({"yaxes" : [lefty, righty]})
        if grafana_version.startswith("4"):
            g.update({"thresholds" : self.thresholds, "decimals" : self.decimals})
        else:
            g.update({"isNew" : self.isNew})
        return g

class PiePanel(PlotPanel):
    def __init__(self, title, isNew=True, targets=[], links=[], datasource="",
                 error=False, span=12, editable=True, aliasColors={}, cacheTimeout=None,
                 fontSize="80%", format="short", interval=None, legendType="Under graph",
                 maxDataPoints=3, nullPointMode="connected", strokeWidth=1, valueName="current",
                 legend=Legend(), description=None, pieType="pie", combineLabel="", combineThreshold=0):
        self.validYFormats = ['bytes', 'kbytes', 'mbytes', 'gbytes', 'bits',
                              'bps', 'Bps', 'short', 'joule', 'watt', 'kwatt',
                              'watth', 'ev', 'amp', 'volt'
                              'none', 'percent', 'ppm', 'dB', 'ns', 'us',
                              'ms', 's', 'hertz', 'pps',
                              'celsius', 'farenheit', 'humidity',
                              'pressurembar', 'pressurehpa',
                              'velocityms', 'velocitykmh', 'velocitymph', 'velocityknot',
                              "kBs", "KBs", "MBs", "GBs"]
        self.validLegendTypes = ["Under graph", "On graph", "Right side"]
        self.validPieTypes = ["pie", "donut"]
        self.validNullPointModes = ["connected", 'null as zero', 'null']
        self.validValueNames = ["current", "min", "max", "avg", "total"]
        PlotPanel.__init__(self, title=title, isNew=isNew, targets=targets, links=links,
                         datasource=datasource, error=error, span=span, editable=editable,
                         description=description)
        self.type = "grafana-piechart-panel"
        self.targets = []
        self.pieType = "pie"
        self.aliasColors = {}
        self.cacheTimeout = None
        self.fontSize = "80%"
        self.format = "short"
        self.interval = None
        self.legendType = "Under graph"
        self.maxDataPoints = 3
        self.nullPointMode = "connected"
        self.strokeWidth = 1
        self.valueName = "current"
        self.combineLabel = ""
        self.combineThreshold = 0
        self.legend = Legend()
        self.set_aliasColors(aliasColors)
        self.set_cacheTimeout(cacheTimeout)
        self.set_fontSize(fontSize)
        self.set_format(format)
        self.set_interval(interval)
        self.set_legendType(legendType)
        self.set_maxDataPoints(maxDataPoints)
        self.set_nullPointMode(nullPointMode)
        self.set_strokeWidth(strokeWidth)
    def set_combineLabel(self, combineLabel):
        debug_print("PiePanel: set_combineLabel(%s)" % str(combineLabel))
        if isinstance(combineLabel, str) or isinstance(combineLabel, unicode):
            self.combineLabel = combineLabel
            return True
        return False
    def set_combineThreshold(self, combineThreshold):
        debug_print("PiePanel: set_combineThreshold(%s)" % str(combineThreshold))
        if isinstance(combineThreshold, int):
            self.combineThreshold = combineThreshold
            return True
        return False
    def set_pieType(self, pieType):
        debug_print("PiePanel: set_pieType(%s)" % str(pieType))
        if pieType in self.validPieTypes:
            self.pieType = pieType
            return True
        return False
    def set_aliasColors(self, aliasColors):
        debug_print("PiePanel: set_aliasColors(%s)" % str(aliasColors))
        if isinstance(aliasColors, dict):
            self.aliasColors = aliasColors
            return True
        return False
    def set_cacheTimeout(self, cacheTimeout):
        debug_print("PiePanel: set_cacheTimeout(%s)" % str(cacheTimeout))
        if cacheTimeout == None or isinstance(cacheTimeout, int):
            self.cacheTimeout = cacheTimeout
            return True
        return False
    def set_fontSize(self, fontSize):
        debug_print("PiePanel: set_fontSize(%s)" % str(fontSize))
        if re.match("\d+%", fontSize):
            self.fontSize = fontSize
            return True
        return False
    def set_format(self, fmt):
        debug_print("PiePanel: set_format(%s)" % str(fmt))
        if fmt in self.validYFormats:
            self.format = fmt
            return True
        return False
    def set_interval(self, interval):
        debug_print("PiePanel: set_interval(%s)" % str(interval))
        if interval == None or isinstance(interval, int):
            self.interval = interval
            return True
        return  False
    def set_legendType(self, legendType):
        debug_print("PiePanel: set_legendType(%s)" % str(legendType))
        if legendType in self.validLegendTypes:
            self.legendType = legendType
            return True
        return False
    def set_maxDataPoints(self, maxDataPoints):
        debug_print("PiePanel: set_maxDataPoints(%s)" % str(maxDataPoints))
        if isinstance(maxDataPoints, int):
            self.maxDataPoints = maxDataPoints
            return True
        return False
    def set_nullPointMode(self, nullPointMode):
        debug_print("PiePanel: set_nullPointMode(%s)" % str(nullPointMode))
        if nullPointMode in self.validNullPointModes:
            self.nullPointMode = nullPointMode
            return True
        return False
    def set_strokeWidth(self, strokeWidth):
        debug_print("PiePanel: set_strokeWidth(%s)" % str(strokeWidth))
        if isinstance(strokeWidth, int) and strokeWidth > 0:
            self.strokeWidth = strokeWidth
            return True
        return False
    def set_valueName(self, valueName):
        debug_print("PiePanel: set_valueName(%s)" % str(valueName))
        if isinstance(valueName, str):
            self.valueName = valueName
            return True
        return False
    def set_legend(self, legend):
        debug_print("PiePanel: set_legend(%s)" % str(legend))
        if isinstance(legend, Legend):
            self.legend = legend
            return True
        return False
    def add_target(self, target):
        debug_print("PiePanel: add_target(%s)" % str(target))
        if isinstance(target, Target):
            target.set_refId(chr(ord('A')+len(self.targets)))
            self.targets.append(target)
            return True
        return False
    def get(self):
        d = {
          "aliasColors": self.aliasColors,
          "cacheTimeout": self.cacheTimeout,
          "datasource": self.datasource,
          "error": self.error,
          "fontSize": self.fontSize,
          "format": self.format,
          "id": self.id,
          "targets" : [ t.get() for t in self.targets ],
          "interval": self.interval,
          "legend": self.legend.get(),
          "legendType": self.legendType,
          "links": self.links,
          "maxDataPoints": self.maxDataPoints,
          "nullPointMode": self.nullPointMode,
          "pieType": self.pieType,
          "span": self.span,
          "strokeWidth": self.strokeWidth,
          "targets": self.targets,
          "title": self.title,
          "type": self.type,
          "valueName": self.valueName,
          "combine" : { "label" : self.combineLabel, "threshold" : self.combineThreshold}
        }
        if not grafana_version.startswith("4"):
            d.update({"editable": self.editable,
                      "isNew": self.isNew})
        return d
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        return str(self.get())
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j["type"] != "grafana-piechart-panel":
            print("Not a PiePanel")
            return False
        if j.has_key("id"):
            self.set_id(j["id"])
        if j.has_key("aliasColors"):
            self.set_aliasColors(j["aliasColors"])
        if j.has_key("cacheTimeout"):
            self.set_cacheTimeout(j["cacheTimeout"])
        if j.has_key("datasource"):
            self.set_datasource(j["datasource"])
        if j.has_key("editable"):
            self.set_editable(j["editable"])
        if j.has_key("error"):
            self.set_error(j["error"])
        if j.has_key("fontSize"):
            self.set_fontSize(j["fontSize"])
        if j.has_key("format"):
            self.set_format(j["format"])
        if j.has_key("interval"):
            self.set_interval(j["interval"])
        if j.has_key("isNew"):
            self.set_isNew(j["isNew"])
        if j.has_key("combine") and j["combine"].has_key("label"):
            self.set_combineLabel(j["combine"]["label"])
        if j.has_key("combine") and j["combine"].has_key("threshold"):
            self.set_combineThreshold(j["combine"]["threshold"])
        if j.has_key("legend"):
            l = Legend()
            l.read_json(j["legend"])
            self.set_legend(l)
        if j.has_key("legendType"):
            self.set_legendType(j["legendType"])
        if j.has_key("maxDataPoints"):
            self.set_maxDataPoints(j["maxDataPoints"])
        if j.has_key("nullPointMode"):
            self.set_nullPointMode(j["nullPointMode"])
        if j.has_key("span"):
            self.set_span(j["span"])
        if j.has_key("strokeWidth"):
            self.set_strokeWidth(j["strokeWidth"])
        if j.has_key("title"):
            self.set_title(j["title"])
        if j.has_key("valueName"):
            self.set_valueName(j["valueName"])
        if j.has_key("links"):
            for l in j["links"]:
                self.add_link(l)
        if j.has_key("targets"):
            for t in j["targets"]:
                target = Target("")
                target.read_json(t)
                self.add_target(target)
        if j.has_key("description"):
            self.set_description(j["description"])
        return True





class Gauge(object):
    def __init__(self, maxValue=100, minValue=0, show=False, thresholdLabels=False, thresholdMarkers=True):
        self.set_maxValue(maxValue)
        self.set_minValue(minValue)
        self.set_show(show)
        self.set_thresholdLabels(thresholdLabels)
        self.set_thresholdMarkers(thresholdMarkers)

    def set_show(self, b):
        debug_print("Gauge: set_show(%s)" % str(b))
        if isinstance(b, bool):
            self.show = b
            return True
        return False
    def set_thresholdLabels(self, b):
        debug_print("Gauge: set_thresholdLabels(%s)" % str(b))
        if isinstance(b, bool):
            self.thresholdLabels = b
            return True
        return False
    def set_thresholdMarkers(self, b):
        debug_print("Gauge: set_thresholdMarkers(%s)" % str(b))
        if isinstance(b, bool):
            self.thresholdMarkers = b
            return True
        return False
    def set_maxValue(self, b):
        debug_print("Gauge: set_maxValue(%s)" % str(b))
        if not isinstance(b, int):
            try:
                b = int(b)
            except:
                print "maxValue must be an integer"
                return False
        self.maxValue = b
        return True
    def set_minValue(self, b):
        debug_print("Gauge: set_minValue(%s)" % str(b))
        if not isinstance(b, int):
            try:
                b = int(b)
            except:
                print "minValue must be an integer"
                return False
        self.minValue = b
        return True
    def get(self):
        return {"maxValue" : self.maxValue, "minValue" : self.minValue,
                "show" : self.show, "thresholdLabels" : self.thresholdLabels,
                "thresholdMarkers" : self.thresholdMarkers}
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        return str(self.get())
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j.has_key("maxValue"):
            self.set_maxValue(j["maxValue"])
        if j.has_key("minValue"):
            self.set_minValue(j["minValue"])
        if j.has_key("show"):
            self.set_show(j["show"])
        if j.has_key("thresholdLabels"):
            self.set_thresholdLabels(j["thresholdLabels"])
        if j.has_key("thresholdMarkers"):
            self.set_thresholdMarkers(j["thresholdMarkers"])

class Sparkline(object):
    def __init__(self, fillColor=None, full=False,
                       lineColor=None, show=False):
        self.default_fillColor = "rgba(31, 118, 189, 0.18)"
        self.default_lineColor = "rgb(31, 120, 193)"
        if fillColor:
            self.set_fillColor(fillColor)
        else:
            self.set_fillColor(self.default_fillColor)
        self.set_full(full)
        if lineColor:
            self.set_lineColor(lineColor)
        else:
            self.set_lineColor(self.default_lineColor)
        self.set_show(show)

    def set_full(self, b):
        debug_print("Sparkline: set_full(%s)" % str(b))
        if isinstance(b, bool):
            self.full = b
            return True
        return False
    def set_show(self, b):
        debug_print("Sparkline: set_show(%s)" % str(b))
        if isinstance(b, bool):
            self.show = b
            return True
        return False
    def set_fillColor(self, c):
        debug_print("Sparkline: set_fillColor(%s)" % str(c))
        c = check_color(c)
        if c:
            self.fillColor = c
            return True
        return False
    def set_lineColor(self, c):
        debug_print("Sparkline: set_lineColor(%s)" % str(c))
        c = check_color(c)
        if c:
            self.lineColor = c
            return True
        return False
    def get(self):

        return { "fillColor" : str(self.fillColor), "full" : self.full,
                 "lineColor" : str(self.lineColor), "show" : self.show }
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        return str(self.get())
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j.has_key("fillColor"):
            self.set_fillColor(j["fillColor"])
        if j.has_key("lineColor"):
            self.set_lineColor(j["lineColor"])
        if j.has_key("full"):
            self.set_full(j["full"])
        if j.has_key("show"):
            self.set_show(j["show"])

class SingleStat(PlotPanel):
    def __init__(self, cacheTimeout=None, colorBackground=False, colorValue=False,
                       colors=[], datasource="", editable=True, error=False,
                       format="none", gauge=Gauge(), interval=None,
                       isNew=True, links=[], maxDataPoints=100,
                       NonePointMode="connected", NoneText=None, postfix="",
                       postfixFontSize="50%", prefix="", prefixFontSize="50%",
                       span=3, sparkline=Sparkline(), targets=[], thresholds="",
                       title="", valueFontSize="80%", valueMaps=[], valueName="avg",
                       invertColors=False, description=None, decimals=None,
                       mappingType=None, mappingTypes=[], nullPointMode="connected",
                       nullText=None, rangeMaps=[]):

        PlotPanel.__init__(self, title=title, isNew=isNew, targets=targets, links=links,
                         datasource=datasource, error=error, span=span, editable=editable,
                         description=description)
        self.validValueNames = ['min','max','avg', 'current', 'total', 'name']
        self.validNonePointModes = ["connected", 'null as zero', 'null']
        self.validFontSizes = ['20%', '30%','50%','70%','80%','100%', '110%', '120%', '150%', '170%', '200%']
        self.type = "singlestat"
        self.cacheTimeout=None
        self.colorBackground=False
        self.colorValue=False
        self.colors=[]
        self.format="none"
        self.gauge=Gauge()
        self.interval=None
        self.maxDataPoints=100
        self.NonePointMode="connected"
        self.NoneText=None
        self.postfix=""
        self.postfixFontSize="50%"
        self.prefix=""
        self.prefixFontSize="50%"
        self.sparkline=Sparkline()
        self.thresholds=""
        self.valueFontSize="80%"
        self.valueMaps=[]
        self.valueName="avg"
        self.invertColors=False
        self.decimals=None
        self.mappingType=None
        self.mappingTypes=[]
        for m in mappingTypes:
            if m.has_key("name") and m.has_key("value"):
                self.add_mappingType(m["name"], m["value"])
        self.nullPointMode="connected",
        self.nullText=None
        self.rangeMaps=[]
        for r in rangeMaps:
            if r.has_key("from") and r.has_key("to") and r.has_key("text"):
                self.add_rangeMap(r["from"], r["to"], r["text"])
        self.set_cacheTimeout(cacheTimeout)
        self.set_colorBackground(colorBackground)
        self.set_colorValue(colorValue)
        self.colors = []
        for c in colors:
            self.add_color(c)
        self.targets = []
        for t in targets:
            self.add_target(t)
        self.set_format(format)
        self.set_gauge(gauge)
        self.set_interval(interval)
        self.set_maxDataPoints(maxDataPoints)
        self.set_nonePointMode(NonePointMode)
        self.set_noneText(NoneText)
        self.set_nullPointMode(nullPointMode)
        self.set_nullText(nullText)
        self.set_decimals(decimals)
        self.set_postfix(postfix)
        self.set_postfixFontSize(postfixFontSize)
        self.set_prefix(prefix)
        self.set_prefixFontSize(prefixFontSize)
        self.set_sparkline(sparkline)
        self.set_thresholds(thresholds)
        self.set_invertColors(invertColors)
        self.set_valueFontSize(valueFontSize)
        self.valueMaps = []
        for v in valueMaps:
            if v.has_key("value"):
                if v.has_key("operator"):
                    self.add_valueMap(v["value"], v["text"], operator=v["operator"])
                else:
                    self.add_valueMap(v["value"], v["text"])
            elif v.has_key("from"):
                self.add_rangeMap(v["start"], v["end"], v["text"] )
        self.set_valueName(valueName)
    def set_thresholds(self, t):
        if isinstance(t, str):
            self.thresholds = t
            return True
        return False
    def set_format(self, t):
        if isinstance(t, str):
            self.format = t
            return True
        return False
    def set_interval(self, t):
        if not t or isinstance(t, str):
            self.interval = t
            return True
        return False
    def set_postfix(self, t):
        if isinstance(t, str):
            self.postfix = t
            return True
        return False
    def set_prefix(self, t):
        if isinstance(t, str):
            self.prefix = t
            return True
        return False
    def set_maxDataPoints(self, t):
        if isinstance(t, int):
            self.maxDataPoints = t
            return True
        return False
    def set_decimals(self, t):
        if not t or isinstance(t, int):
            self.decimals = t
            return True
        return False
    def set_nonePointMode(self, t):
        if isinstance(t, str) and t in self.validNonePointModes:
            self.NonePointMode = t
            return True
        return False
    def set_noneText(self, t):
        if not t or isinstance(t, str):
            self.NoneText = t
            return True
        return False
    def set_nullPointMode(self, t):
        if isinstance(t, str) and t in self.validNonePointModes:
            self.nullPointMode = t
            return True
        return False
    def set_nullText(self, t):
        if not t or isinstance(t, str):
            self.nullText = t
            return True
        return False
    def set_cacheTimeout(self, t):
        if not t or isinstance(t, str):
            self.cacheTimeout = t
            return True
        return False
    def set_invertColors(self, b):
        if isinstance(b, bool):
            self.invertColors = b
            return True
        return False
    def set_colorBackground(self, b):
        if isinstance(b, bool):
            self.colorBackground = b
            return True
        return False
    def set_colorValue(self, b):
        if isinstance(b, bool):
            self.colorValue = b
            return True
        return False
    def set_editable(self, b):
        if isinstance(b, bool):
            self.editable = b
            return True
        return False
    def set_error(self, b):
        if isinstance(b, bool):
            self.error = b
            return True
        return False
    def set_isNew(self, b):
        if isinstance(b, bool):
            self.isNew = b
            return True
        return False
    def set_gauge(self, g):
        if isinstance(g, Gauge):
            self.gauge = g
            return True
        return False
    def set_sparkline(self, g):
        if isinstance(g, Sparkline):
            self.sparkline = g
            return True
        return False
    def set_valueName(self, v):
        if v in self.validValueNames:
            self.valueName = v
            return True
        else:
            print "invalid value %s for valueName" % (v,)
        return False
    def set_prefixFontSize(self, v):
        if v in self.validFontSizes:
            self.prefixFontSize = v
            return True
        else:
            print "invalid value %s for prefixFontSize" % (v,)
        return False
    def set_postfixFontSize(self, v):
        if v in self.validFontSizes:
            self.postfixFontSize = v
            return True
        else:
            print "invalid value %s for postfixFontSize" % (v,)
        return False
    def set_valueFontSize(self, v):
        if v in self.validFontSizes:
            self.valueFontSize = v
            return True
        else:
            print "invalid value %s for valueFontSize" % (v,)
        return False
    def set_mappingType(self, v):
        if v in range(0,3):
            self.mappingType = v
            return True
        return False
    def add_mappingType(self, name, value):
        d = { "name" : name, "value" : value}
        self.mappingTypes.append(d)
    def add_valueMap(self, value, text, operator="="):
        if grafana_version.startswith("4"):
            self.mappingTypes.append({"name" : text, "value" : value})
        else:
            self.valueMaps.append({ "value" : value, "op" : operator, "text": text })
    def add_rangeMap(self, start, end, text ):
        if grafana_version.startswith("4"):
            self.rangeMaps.append({ "from": start, "to": end, "text": text })
        else:
            self.valueMaps.append({ "from": start, "to": end, "text": text })
    def add_color(self, c):
        if check_color(c):
            self.colors.append(c)
            return True
        return False
    def invert_colors(self, c):
        return self.colors[::-1]
    def get(self):
        vmaps = []
        if len(self.valueMaps) == 0 and not grafana_version.startswith("4"):
            vmaps.append( { "op" : "=", "text" : "N/A", "value" : "None" })
        cols = ["rgba(245, 54, 54, 0.9)", "rgba(237, 129, 40, 0.89)", "rgba(50, 172, 45, 0.97)"]
        if len(self.colors) > 0:
            cols = self.colors
        if self.invertColors:
            cols = self.invert_colors(cols)
        d = { "cacheTimeout": self.cacheTimeout, "colorBackground": self.colorBackground,
                 "colorValue": self.colorValue, "colors": cols,
                 "editable": self.editable, "datasource": self.datasource,
                 "error": self.error, "format": self.format, "gauge": self.gauge.get(),
                 "id": self.id, "interval": self.interval,
                 "links": self.links, "maxDataPoints": self.maxDataPoints,
                 "NonePointMode": self.NonePointMode, "NoneText": self.NoneText,
                 "postfix": self.postfix, "postfixFontSize": self.postfixFontSize,
                 "prefix": self.prefix, "prefixFontSize": self.prefixFontSize,
                 "span": self.span, "sparkline": self.sparkline.get(),
                 "targets": [ t.get() for t in self.targets], "thresholds": self.thresholds,
                 "title": self.title, "type": self.type,
                 "valueFontSize": self.valueFontSize, "valueName": self.valueName,
                 "valueMaps": vmaps}
        if not grafana_version.startswith("4"):
            d.update({"isNew": self.isNew})
        else:
            d.update({"nullPointMode" : self.nullPointMode, "nullText" : self.nullText})
            if self.mappingType > 0:
                d.update({"mappingType" : self.mappingType,
                         "mappingTypes" : self.mappingTypes})
            if len(self.rangeMaps) > 0:
                d.update({"rangeMaps" : self.rangeMaps})
        return d
    def read_json(self, j):
        if not isinstance(j, dict):
            try:
                j = json.loads(j)
            except Exception as e:
                print("Cannot parse JSON of SingleStat: %s" % e)
                return False
        if j.has_key("type"):
            if j["type"] != "singlestat":
                return False
            self.type = j["type"]
        if j.has_key("cacheTimeout"):
            self.set_cacheTimeout(j["cacheTimeout"])
        if j.has_key("colorBackground"):
            self.set_colorBackground(j["colorBackground"])
        if j.has_key("colorValue"):
            self.set_colorValue(j["colorValue"])
        if j.has_key("colors"):
            for c in j["colors"]:
                self.add_color(c)
        if j.has_key("targets"):
            for t in j["targets"]:
                target = Target("", tags=[])
                target.read_json(t)
                self.add_target(target)
        if j.has_key("datasource"):
            self.set_datasource(j["datasource"])
        if j.has_key("editable"):
            self.set_editable(j["editable"])
        if j.has_key("error"):
            self.set_error(j["error"])
        if j.has_key("format"):
            self.set_format(j["format"])
        if j.has_key("gauge"):
            g = Gauge().read_json(j["gauge"])
            self.set_gauge(g)
        if j.has_key("sparkline"):
            s = Sparkline().read_json(j["sparkline"])
            self.set_sparkline(s)
        if j.has_key("id"):
            self.set_id(j["id"])
        if j.has_key("interval"):
            self.set_interval(j["interval"])
        if j.has_key("isNew"):
            self.set_isNew(j["isNew"])
        if j.has_key("links"):
            for l in j["links"]:
                self.add_link(l)
        if j.has_key("maxDataPoints"):
            self.set_maxDataPoints(j["maxDataPoints"])
        if j.has_key("NonePointMode"):
            self.set_nonePointMode(j["NonePointMode"])
        if j.has_key("NoneText"):
            self.set_noneText(j["NoneText"])
        if j.has_key("nullPointMode"):
            self.set_nullPointMode(j["nullPointMode"])
        if j.has_key("nullText"):
            self.set_nullText(j["nullText"])
        if j.has_key("postfix"):
            self.set_postfix(j["postfix"])
        if j.has_key("mappingType"):
            self.set_mappingType(j["mappingType"])
        if j.has_key("postfixFontSize"):
            self.set_postfixFontSize(j["postfixFontSize"])
        if j.has_key("prefix"):
            self.set_prefix(j["prefix"])
        if j.has_key("prefixFontSize"):
            self.set_prefixFontSize(j["prefixFontSize"])
        if j.has_key("span"):
            self.set_span(j["span"])
        if j.has_key("thresholds"):
            self.set_thresholds(j["thresholds"])
        if j.has_key("title"):
            self.set_title(j["title"])
        if j.has_key("valueFontSize"):
            self.set_valueFontSize(j["valueFontSize"])
        if j.has_key("valueName"):
            self.set_valueName(j["valueName"])
        if j.has_key("valueMaps"):
            if not grafana_version.startswith("4"):
                for v in j["valueMaps"]:
                    if v.has_key("value"):
                        if v.has_key("operator"):
                            self.add_valueMap(v["value"], v["text"], operator=v["operator"])
                        else:
                            self.add_valueMap(v["value"], v["text"])
                    elif v.has_key("from"):
                        self.add_rangeMap(v["start"], v["end"], v["text"] )
            else:
                self.valueMaps = []
        if j.has_key("rangeMaps") and grafana_version.startswith("4"):
            for r in j["rangeMaps"]:
                if r.has_key("from") and r.has_key("to") and r.has_key("text"):
                    self.add_rangeMap(r["from"], r["to"], r["text"])
        if j.has_key("mappingTypes") and grafana_version.startswith("4"):
            for m in j["mappingTypes"]:
                if m.has_key("name") and m.has_key("value"):
                    self.add_mappingType(m["name"], m["value"])
        if j.has_key("mappingType") and grafana_version.startswith("4"):
            self.set_mappingType(j["mappingType"])
        return True

# TODO Check for dashboard validity:
#   - Repeat string for Row and Panels must be valid template name
#   - Template: add 'useTags' and others only if type == 'query'
#   - Warn if repeat template has multi == False

class Row(object):
    def __init__(self, title="", panels=[], editable=True, collapse=False, height="250px", showTitle=False, repeat=None, repeatIteration=None, minSpan=None, repeatRowId=None, titleSize="h6"):
        self.set_title(title)
        self.panels = []
        for p in panels:
            self.add_panel(p)
        self.set_editable(editable)
        self.set_collapse(collapse)
        self.set_height(height)
        self.set_showTitle(showTitle)
        self.set_repeat(repeat)
        self.set_repeatIteration(repeatIteration)
        self.set_minSpan(minSpan)
        self.set_repeatRowId(repeatRowId)
        self.set_titleSize(titleSize)
    def set_title(self, t):
        if not isinstance(t, str):
            try:
                t = str(t)
            except ValueError:
                print "Title must be stringifyable"
                return False
        self.title = t
        return True
    def set_height(self, height):
        if not isinstance(height, str):
            try:
                height = str(height)
            except ValueError:
                print "Height must be stringifyable"
                return False
        if not (re.match("(\d+)px", height) or re.match("(\d+)[cm]*", height)):
            print "Height not valid"
            return False
        self.height = height
        return True
    def set_repeat(self, repeat):
        if repeat == None or isinstance(repeat, str):
            self.repeat = repeat
            return True
        return False
    def set_repeatIteration(self, repeatIteration):
        if repeatIteration == None or isinstance(repeatIteration, str):
            self.repeatIteration = repeatIteration
            return True
        return False
    def set_repeatRowId(self, repeatRowId):
        if repeatRowId == None or isinstance(repeatRowId, int):
            self.repeatRowId = repeatRowId
            return True
        return False
    def set_titleSize(self, titleSize):
        if isinstance(titleSize, str):
            self.titleSize = titleSize
            return True
        return False
    def set_minSpan(self, minSpan):
        if minSpan == None or isinstance(minSpan, int):
            self.minSpan = minSpan
            return True
        return False
    def set_editable(self, editable):
        if isinstance(editable, bool):
            self.editable = editable
            return True
        return False
    def set_collapse(self, collapse):
        if isinstance(collapse, bool):
            self.collapse = collapse
            return True
        return False
    def set_showTitle(self, showTitle):
        if isinstance(showTitle, bool):
            self.showTitle = showTitle
            return True
        return False
    def add_panel(self, p):
        if isinstance(p, Panel):
            x = copy.deepcopy(p)
            self.panel.append(x)
            return True
        return False
    def get(self):
        g = {'title': self.title, 'panels': [ p.get() for p in self.panels ],
                'collapse': self.collapse,
                'height': self.height, 'repeat' : self.repeat,
                'showTitle': self.showTitle, 'repeatIteration' : self.repeatIteration,
                'repeatRowId' : self.repeatRowId, 'titleSize' : self.titleSize}
        if self.minSpan:
            g.update({'minSpan' : self.minSpan})
        if not grafana_version.startswith("4"):
            g.update({'editable': self.editable})
        return g
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        return str(self.get())
    def add_panel(self, p):
        if isinstance(p, Panel):
            x = copy.deepcopy(p)
            self.panels.append(x)
    def set_datasource(self, d):
        for p in self.panels:
            p.set_datasource(d)
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j.has_key("title"):
            self.set_title(j["title"])
        if j.has_key("editable"):
            self.set_editable(j["editable"])
        if j.has_key("collapse"):
            self.set_collapse(j["collapse"])
        if j.has_key("height"):
            self.set_height(j["height"])
        if j.has_key("panels"):
            for p in j["panels"]:
                o = None
                if p.has_key("type"):
                    if p["type"] == "singlestat":
                        o = SingleStat()
                        o.read_json(p)
                    if p["type"] == "graph":
                        o = GraphPanel()
                        o.read_json(p)
                    if p["type"] == "text":
                        o = TextPanel()
                        o.read_json(p)
                if o:
                    self.add_panel(o)


class Template(object):
    def __init__(self, name, value, multi=True, allFormat="regex wildcard",
                       refresh=None, options=[], current={}, datasource="", tags=[],
                       type="query", multiFormat="regex values", includeAll=False,
                       label=None, hideLabel=False, auto_count=None, auto=False,
                       useTags=False, tagsQuery="", tagValuesQuery="", sort=0, hide=0,
                       regex="", allValue=None):
        self.validAllFormats = ["regex wildcard", "glob"]
        self.validMultiFormats = ["regex values", "glob"]
        self.validTypes = ["query", "interval", "custom"]
        self.validAutoCounts = [3, 5, 10, 30, 50, 100, 200]
        self.name = ""
        self.value = ""
        self.multi = True
        self.allFormat = "regex wildcard"
        self.refresh = None
        self.current = {}
        self.datasource = ""
        self.type="query"
        self.multiFormat = "regex values"
        self.includeAll = False
        self.label = None
        self.hideLabel = False
        self.auto_count = None
        self.auto = False
        self.useTags = False
        self.tagsQuery = ""
        self.tagValuesQuery = ""
        self.sort = 0
        self.hide = 0
        self.regex = ""
        self.query = ""
        self.allValue = None
        self._set_name_and_value(name, value)
        self.set_multi(multi)
        self.set_allFormat(allFormat)
        self.set_refresh(refresh)
        self.options = []
        for o in options:
            self.add_option(o)
        self.current = current
        self.set_datasource(datasource)
        self.tags = []
        for t in tags:
            self.add_tag(t)
        self.set_type(type)
        self.set_multiFormat(multiFormat)
        self.set_includeAll(includeAll)
        self.set_label(label)
        self.set_hideLabel(hideLabel)
        self.set_auto(auto)
        self.set_autoCount(auto_count)
        self.set_useTags(useTags)
        self.set_tagsQuery(tagsQuery)
        self.set_tagValuesQuery(tagValuesQuery)
        self.set_sort(sort)
        self.set_hide(hide)
        self.set_regex(regex)
        self.set_allValue(allValue)
    def _set_name_and_value(self, name, value):
        if not isinstance(name, str):
            try:
                name = str(name)
            except:
                print "Name not stringifyable"
                return False
        if not isinstance(value, str):
            try:
                value = str(value)
            except:
                print "Value not stringifyable"
                return False
        self.name = name
        self.value = value
        return True
    def set_useTags(self, useTags):
        if isinstance(useTags, bool):
            self.useTags = useTags
            return True
        return False
    def set_tagsQuery(self, tagsQuery):
        if isinstance(tagsQuery, str):
            self.tagsQuery = tagsQuery
            return True
        return False
    def set_regex(self, regex):
        if isinstance(regex, str):
            self.regex = regex
            return True
        return False
    def set_query(self, query):
        if isinstance(query, str) or isinstance(query, unicode):
            self.query = query
            return True
        return False
    def set_tagValuesQuery(self, tagValuesQuery):
        if isinstance(tagValuesQuery, str):
            self.tagValuesQuery = tagValuesQuery
            return True
        return False
    def set_label(self, label):
        if label == None or isinstance(label, str):
            self.label = label
            return True
        return False
    def set_allValue(self, allValue):
        if allValue == None or isinstance(allValue, str):
            self.allValue = allValue
            return True
        return False
    def set_datasource(self, datasource):
        if isinstance(datasource, str):
            self.datasource = datasource
            return True
        return False
    def set_multi(self, multi):
        if isinstance(multi, bool):
            self.multi = multi
            return True
        return False
    def set_auto(self, auto):
        if isinstance(auto, bool):
            self.auto = auto
            return True
        return False
    def set_autoCount(self, autoCount):
        if autoCount == None or (isinstance(autoCount, int) and autoCount in self.validAutoCounts):
            self.auto_count = autoCount
            return True
        return False
    def set_hideLabel(self, hideLabel):
        if isinstance(hideLabel, bool):
            self.hideLabel = hideLabel
            return True
        return False
    def set_refresh(self, refresh):
        if grafana_version.startswith("2") or grafana_version.startswith("3"):
            if not refresh:
                refresh = False
            if isinstance(refresh, bool):
                self.refresh = refresh
                return True
            return False
        elif grafana_version.startswith("4"):
            if not refresh:
                refresh = 0
            if isinstance(refresh, int) and refresh in range(0,3):
                self.refresh = refresh
                return True
            return False
    def set_includeAll(self, includeAll):
        if isinstance(includeAll, bool):
            self.includeAll = includeAll
            return True
        return False
    def set_sort(self, sort):
        if isinstance(sort, int) and sort in range(0,5):
            self.sort = sort
            return True
        return False
    def set_hide(self, hide):
        if isinstance(hide, int) and hide in range(0,3):
            self.hide = hide
            return True
        return False
    def set_type(self, typ):
        if typ in self.validTypes:
            self.type = typ
            return True
        return False
    def set_allFormat(self, allFormat):
        if allFormat in self.validAllFormats:
            self.allFormat = allFormat
            return True
        return False
    def set_multiFormat(self, multiFormat):
        if multiFormat in self.validMultiFormats:
            self.multiFormat = multiFormat
            return True
        return False
    def add_option(self, option):
        if isinstance(option, list):
            self.options = copy.deepcopy(option)
            return True
        elif isinstance(option, str):
            self.options.append(option)
            return True
        return False
    def add_tag(self, tag):
        if isinstance(tag, list):
            self.tags = copy.deepcopy(tag)
            return True
        elif isinstance(tag, tuple):
            self.tags.append(tag)
            return True
        return False
    def get(self):
        q = ""
        if len(self.query) == 0:
            q = self.value
            if self.type == "query" and not q.upper().startswith("SHOW TAG VALUES WITH KEY"):
                q = "SHOW TAG VALUES WITH KEY = %s" % (self.value.strip("$"),)
                if len(self.tags) > 0:
                    l = []
                    for i, t in enumerate(self.tags):
                        k,v = t
                        v = v.strip("/")
                        if v[0] == "$" and v[-1] != "$":
                            v += "$"
                        l.append("%s =~ /%s/" % (k, v))
                    q += " WHERE "+" AND ".join(l)
            elif self.type == "interval" or self.type == "custom":
                q = str(self.value)
        else:
            q = self.query
        #c = self.current
        #if len(c) == 0 and len(self.value.split(",")) > 0:
        #    s = self.value.split(",")[0]
        #    c = {"text" : str(s), "value" : str(s)}
        #    if grafana_version.startswith("4"):
        #        c.update({"tags" : []})
        d = {"multi" : self.multi, "name" : self.name, "allFormat" : self.allFormat,
                "refresh" : self.refresh, "options" : self.options,
                "current" : self.current, "datasource" : self.datasource,
                "query": q, "type" : self.type,
                "multiFormat" : self.multiFormat, "includeAll" : self.includeAll,
                "label" : self.label}
        if self.type == "query":
            d.update({"useTags" : self.useTags,
                      "tagsQuery" : self.tagsQuery,
                      "tagValuesQuery" : self.tagValuesQuery})
        if grafana_version.startswith("4"):
            d.update({"sort": self.sort, "hide": self.hide,
                      "useTags" : self.useTags,
                      "tagsQuery" : self.tagsQuery,
                      "tagValuesQuery" : self.tagValuesQuery,
                      "regex" : self.regex,
                      "tags" : [],
                      "allValue" : self.allValue})
        else:
            d.update({"hideLabel" : self.hideLabel,
                      "auto_count" : self.auto_count,
                      "auto" : self.auto,
                      "refresh_on_load" : self.refresh})
        return d
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        return str(self.get())
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j.has_key('name') and j.has_key('value'):
            self._set_name_and_value(j['name'], j['value'])
        if j.has_key('name') and j.has_key('query'):
            self._set_name_and_value(j['name'], j['query'])
        if j.has_key('allFormat'):
            self.set_allFormat(j['allFormat'])
        if j.has_key('type'):
            self.set_type(j['type'])
        if j.has_key('datasource'):
            self.set_datasource(j['datasource'])
        if j.has_key('refresh'):
            self.set_refresh(j['refresh'])
        if j.has_key('multiFormat'):
            self.set_multiFormat(j['multiFormat'])
        if j.has_key('includeAll'):
            self.set_includeAll(j['includeAll'])
        if j.has_key('multi'):
            self.set_multi(j['multi'])
        if j.has_key('label'):
            self.set_label(j['label'])
        if j.has_key('hideLabel'):
            self.set_hideLabel(j['hideLabel'])
        if j.has_key('auto'):
            self.set_auto(j['auto'])
        if j.has_key('auto_count'):
            self.set_autoCount(j['auto_count'])
        if j.has_key('useTags'):
            self.set_useTags(j['useTags'])
        if j.has_key('tagsQuery'):
            self.set_tagsQuery(j['tagsQuery'])
        if j.has_key('tagValuesQuery'):
            self.set_tagValuesQuery(j['tagValuesQuery'])
        if j.has_key('query'):
            self.set_query(j['query'])


class Timepicker(object):
    def __init__(self, time_options=['5m', '15m', '1h', '6h', '12h', '24h', '2d', '7d', '30d'],
                       refresh_intervals=['5s', '10s', '30s', '1m', '5m', '15m', '30m', '1h', '2h', '1d'], now=True):
        self.time_options = time_options
        self.refresh_intervals = refresh_intervals
        self.now=True
    def set_time_options(self, t):
        if isinstance(t, list):
            self.time_options = copy.deepcopy(t)
            return True
        elif isinstance(t, str):
            self.time_options.append(t)
            return True
        return False
    def set_refresh_intervals(self, t):
        if isinstance(t, list):
            self.refresh_intervals = copy.deepcopy(t)
            return True
        elif isinstance(t, str):
            self.refresh_intervals.append(t)
            return True
        return False
    def set_now(self, n):
        if isinstance(n, bool):
            self.now = n
            return True
        return False
    def get(self):
        g = {'time_options': self.time_options,
             'refresh_intervals': self.refresh_intervals}
        if grafana_version.startswith("4"):
            g.update({'now': self.now})
        return g
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        return str(self.get())
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j.has_key('time_options') and isinstance(j['time_options'], list):
            self.set_time_options(j['time_options'])
        if j.has_key('refresh_intervals') and isinstance(j['refresh_intervals'], list):
            self.set_refresh_intervals(j['refresh_intervals'])

class Annotation(object):
    def __init__(self, name, query, datasource="", iconColor="rgba(255, 96, 96, 1)",
                       limit=100, textColumn="", titleColumn="", typ="alert",
                       enable=True, tagsColumn=""):
        self.validTypes = ["alert"]
        self.name = ""
        self.query = ""
        self.datasource = ""
        self.iconColor="rgba(255, 96, 96, 1)"
        self.limit = 100
        self.textColumn = ""
        self.titleColumn = ""
        self.type = "alert"
        self.enable = True
        self.tagsColumn = ""
        self.set_name(name)
        self.set_query(query)
        self.set_datasource(datasource)
        self.set_iconColor(iconColor)
        self.set_limit(limit)
        self.set_textColumn(textColumn)
        self.set_titleColumn(titleColumn)
        self.set_tagsColumn(tagsColumn)
        self.set_type(typ)
        self.set_enable(enable)
    def set_name(self, name):
        if isinstance(name, str) or isinstance(name, unicode):
            self.name = str(name)
            return True
        return False
    def set_query(self, query):
        if isinstance(query, str) or isinstance(query, unicode):
            self.query = str(query)
            return True
        return False
    def set_datasource(self, datasource):
        if isinstance(datasource, str) or isinstance(datasource, unicode):
            self.datasource = str(datasource)
            return True
        return False
    def set_iconColor(self, c):
        if isinstance(c, str) and check_color(c):
            self.iconColor = c
            return True
        return False
    def set_limit(self, c):
        if isinstance(c, int):
            self.limit = c
            return True
        return False
    def set_textColumn(self, textColumn):
        if isinstance(textColumn, str) or isinstance(textColumn, unicode):
            self.textColumn = str(textColumn)
            return True
        return False
    def set_titleColumn(self, titleColumn):
        if isinstance(titleColumn, str) or isinstance(titleColumn, unicode):
            self.titleColumn = str(titleColumn)
            return True
        return False
    def set_tagsColumn(self, tagsColumn):
        if isinstance(tagsColumn, str) or isinstance(tagsColumn, unicode):
            self.tagsColumn = str(tagsColumn)
            return True
        return False
    def set_type(self, typ):
        if (isinstance(typ, str) or isinstance(typ, unicode)) and typ in self.validTypes:
            self.typ = str(typ)
            return True
        return False
    def set_enable(self, b):
        if isinstance(b, bool):
            self.enable = b
            return True
        return False
    def get(self):
        return {"datasource": self.datasource,
                "enable": self.enable,
                "iconColor": self.iconColor,
                "limit": self.limit,
                "name": self.name,
                "query": self.query,
                "tagsColumn": self.tagsColumn,
                "textColumn": self.textColumn,
                "titleColumn": self.titleColumn,
                "type": self.typ}
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        return str(self.get())
    def read_json(self, j):
        if not isinstance(j, dict):
            j = json.loads(j)
        if j.has_key("datasource"):
            self.set_datasource(j["datasource"])
        if j.has_key("enable"):
            self.set_enable(j["enable"])
        if j.has_key("iconColor"):
            self.set_iconColor(j["iconColor"])
        if j.has_key("limit"):
            self.set_limit(j["limit"])
        if j.has_key("name"):
            self.set_name(j["name"])
        if j.has_key("query"):
            self.set_query(j["query"])
        if j.has_key("tagsColumn"):
            self.set_tagsColumn(j["tagsColumn"])
        if j.has_key("textColumn"):
            self.set_textColumn(j["textColumn"])
        if j.has_key("titleColumn"):
            self.set_titleColumn(j["titleColumn"])
        if j.has_key("type"):
            self.set_type(j["type"])

dashboard_id = 0

class Dashboard(object):
    def __init__(self, title, style='dark', rows=[], links=[], tags=[], hideControls=False,
                       editable=True, originalTitle="", timepicker=Timepicker(),
                       refresh=False, sharedCrosshair=False, timezone='browser',
                       schemaVersion=0, overwrite=False, templates=[], annotations=[],
                       startTime="now-6h", endTime="now", gnetId=None, graphTooltip=0,
                       description=""):
        self.id = 0
        self.templates = []
        self.rows = []
        self.links = []
        self.tags = []
        self.annotations = []
        self.style = style
        self.tags = tags
        self.hideControls = hideControls
        self.title = title
        self.editable = editable
        self.originalTitle = originalTitle
        self.timepicker = timepicker
        self.refresh = refresh
        self.sharedCrosshair = sharedCrosshair
        self.timezone = timezone
        self.schemaVersion = schemaVersion
        self.annotations = annotations
        self.overwrite = overwrite
        self.startTime = startTime
        self.endTime = endTime
        self.gnetId = gnetId
        self.description = description
        self.graphTooltip = graphTooltip
        self.slug = self.title.lower().replace(" ", "-").replace("_","-")
        self.validStyles = ["light", "dark"]
        if grafana_version.startswith("2"):
            self.schemaVersion = 8
        elif grafana_version.startswith("3"):
            self.schemaVersion = 12
        elif grafana_version.startswith("4"):
            self.schemaVersion = 14
    def get_slug(self):
        return self.slug
    def add_template(self, t):
        if isinstance(t, Template):
            x = copy.deepcopy(t)
            self.templates.append(x)
            return True
        return False
    def set_id(self, i):
        if isinstance(i, int):
            self.id = i
            return True
        return False
    def add_row(self, r):
        if isinstance(r, Row):
            x = copy.deepcopy(r)
            self.rows.append(x)
            return True
        return False
    def set_graphTooltip(self, t):
        if isinstance(t, int) and t in range(0,3):
            self.graphTooltip = t
            return True
        return False
    def add_tag(self, t):
        if not isinstance(t, str):
            try:
                t = str(t)
            except ValueError:
                print "Tag must be stringifyable"
                return False
        self.tag.append(t)
        return True
    def set_timepicker(self, t):
        if isinstance(t, Timepicker):
            x = copy.deepcopy(t)
            self.timepicker = x
            return True
        elif isinstance(t, dict):

            x = Timepicker()
    def set_overwrite(self, b):
        if isinstance(b, bool):
            self.overwrite = b
            return True
        return False
    def set_editable(self, b):
        if isinstance(b, bool):
            self.editable = b
            return True
        return False
    def set_hideControls(self, b):
        if isinstance(b, bool):
            self.hideControls = b
            return True
        return False
    def set_sharedCrosshair(self, b):
        if isinstance(b, bool):
            self.sharedCrosshair = b
            return True
        return False
    def set_title(self, t):
        if not isinstance(t, str):
            try:
                t = str(t)
            except ValueError:
                print "Title must be stringifyable"
                return False
        self.title = t
        return True
    def set_originalTitle(self, t):
        if not isinstance(t, str):
            try:
                t = str(t)
            except ValueError:
                print "Title must be stringifyable"
                return False
        self.originalTitle = t
        return True
    def set_description(self, t):
        if not isinstance(t, str):
            try:
                t = str(t)
            except ValueError:
                print "Description must be stringifyable"
                return False
        self.description = t
        return True
    def set_refresh(self, r):
        if (isinstance(r, str) and r[-1] in time_limits.keys()) or r == False:
            self.refresh = r
            return True
        return False
    def set_version(self, v):
        if not isinstance(v, int):
            try:
                v = int(v)
            except ValueError:
                print "Input parameter %s must be castable to integer" % (v,)
                return False
        self.version = v
        return True
    def set_schemaVersion(self, v):
        if not isinstance(v, int):
            try:
                v = int(v)
            except ValueError:
                print "Input parameter %s must be castable to integer" % (v,)
                return False
        self.schemaVersion = v
        return True
    def set_timezone(self, t):
        if not isinstance(t, str):
            try:
                t = str(t)
            except ValueError:
                print "Timezone must be stringifyable"
                return False
        self.timezone = t
        return True
    def set_style(self, s):
        if s in self.validStyles:
            self.style = s
    def set_gnetId(self, gnetId):
        if gnetId == None or isinstance(gnetId, int):
            self.gnetId = gnetId
            return True
        return False
    def set_startTime(self, t):
        # check time
        if isinstance(t, str):
            self.startTime = t
        if isinstance(t, int) or isinstance(t, float) or isinstance(t, datetime.datetime):
            self.startTime = str(t)
    def set_endTime(self, t):
        # check time
        if isinstance(t, str):
            self.endTime = t
        if isinstance(t, int) or isinstance(t, float) or isinstance(t, datetime.datetime):
            self.endTime = str(t)
    def add_annotation(self, a):
        if isinstance(a, Annotation):
            self.annotations.append(a)
    def get(self):
        origTitle = self.originalTitle
        #if not origTitle:
        #    origTitle = self.title
        i = 1
        for r in self.rows:
            for p in r.panels:
                p.id = i
                i += 1
        d = {'dashboard': {'version': 0, 'style': self.style, 'rows': [ r.get() for r in self.rows ],
                'templating': {'list': [ t.get() for t in self.templates] }, 'links': self.links,
                'tags': self.tags, 'hideControls': self.hideControls,
                'title': self.title, 'editable': self.editable, 'id': self.id,
                'timepicker': self.timepicker.get(),
                'time': {'to': self.endTime, 'from': self.startTime}, 'timezone': self.timezone,
                'schemaVersion': self.schemaVersion,
                'annotations': {'list': [ a.get() for a in self.annotations ]}},
                'overwrite': self.overwrite, 'description' : self.description}
        if grafana_version.startswith("2") or grafana_version.startswith("3"):
            d['dashboard'].update({'sharedCrosshair': self.sharedCrosshair,
                                   'refresh': self.refresh})
            if len(self.originalTitle) > 0:
                d['dashboard'].update({'originalTitle': self.originalTitle})
        if grafana_version.startswith("3") or grafana_version.startswith("4"):
            d['dashboard'].update({"gnetId" : self.gnetId})
        if grafana_version.startswith("4"):
            d['dashboard'].update({"graphTooltip" : self.graphTooltip})
            if self.refresh != False:
                d["dashboard"].update({'refresh': self.refresh})
        return d
    def get_json(self):
        return json.dumps(self.get())
    def __str__(self):
        return str(self.get())
    def __repr__(self):
        return str(self.get())
    def set_datasource(self, d):
        for r in self.rows:
            r.set_datasource(d)
        for t in self.templates:
            t.set_datasource(d)
        for a in self.annotations:
            a.set_datasource(d)


def read_json(dstr):
    dash = None
    if isinstance(dstr, str):
        try:
            dash = json.loads(dstr)
        except ValueError as e:
            print e
            return None
    else:
        dash = dstr
    if isinstance(dash, dict):
        if dash.has_key("dashboard"):
            out = read_json(dash["dashboard"])
            if isinstance(out, Dashboard) and "overwrite" in dash:
                out.set_overwrite(dash["overwrite"])
            return out
        elif dash.has_key("title"):
            out = Dashboard(dash["title"])
            if dash.has_key("version"):
                out.set_version(dash["version"])
            if dash.has_key("links"):
                out.set_style(dash["links"])
            if dash.has_key("schemaVersion"):
                out.set_schemaVersion(dash["schemaVersion"])
            if dash.has_key("tags"):
                for t in dash["tags"]:
                    out.add_tag(t)
            if dash.has_key("hideControls"):
                out.set_hideControls(dash["hideControls"])
            if dash.has_key("description"):
                out.set_description(dash["description"])
            if dash.has_key("editable"):
                out.set_editable(dash["editable"])
            if dash.has_key("originalTitle"):
                out.set_originalTitle(dash["originalTitle"])
            if dash.has_key("refresh"):
                out.set_refresh(dash["refresh"])
            if dash.has_key("sharedCrosshair"):
                out.set_sharedCrosshair(dash["sharedCrosshair"])
            if dash.has_key("timezone"):
                out.set_timezone(dash["timezone"])
            if dash.has_key("time"):
                if dash["time"].has_key("from"):
                    out.set_startTime(dash["time"]["from"])
                if dash["time"].has_key("to"):
                    out.set_endTime(dash["time"]["to"])
            if dash.has_key("timepicker"):
                t = Timepicker(refresh_intervals=[], time_options=[])
                if dash["timepicker"].has_key("refresh_intervals"):
                    t.set_refresh_intervals(dash["timepicker"]["refresh_intervals"])
                if dash["timepicker"].has_key("time_options"):
                    t.set_time_options(dash["timepicker"]["time_options"])
                out.set_timepicker(t)
            if dash.has_key("rows"):
                for row in dash["rows"]:
                    r = Row()
                    r.read_json(row)
                    out.add_row(r)
            if dash.has_key("annotations") and dash["annotations"].has_key("list"):
                for a in dash["annotations"]["list"]:
                    anno = Annotation("", "")
                    anno.read_json(a)
                    out.add_annotation(anno)
            if dash.has_key("templating") and dash["templating"].has_key("list"):
                for t in dash["templating"]["list"]:
                    temp = Template("", "")
                    temp.read_json(t)
                    out.add_template(temp)
            return out
        else:
            print "Not a Grafana dashboard"
            return None
    else:
        return None

def guess_panel(typ):
    if typ == "graph":
        return GraphPanel()
    elif typ == "singlestat":
        return SingleStat()
    elif typ == "text":
        return TextPanel()
    elif typ == "grafana-piechart-panel":
        return PiePanel("")
    elif typ == "table":
        return TablePanel()
    return None


if __name__ == "__main__":
    t = Target("cpi")
    t.set_alias("CPI")
    t.add_tag("host","$hostname", operator="=~")
    t.add_groupBy("tag", "host")
    t.set_refId(1)
    g = Graph()
    g.add_target(t)
    b = SingleStat()
    b.add_target(t)
    c = SingleStat()
    r = Row()
    print r.get_json()
    r.add_panel(b)
    r.add_panel(c)
    print r.get_json()
    te = Template("hostname", "host", tags=[("jobid", "1234.tbadm")])
    d = Dashboard("Test")
    d.add_row(r)
    d.add_template(te)
    d.set_datasource("fepa")
    d.set_refresh("10s")
    print d

    sO = SeriesOverride("cpi")
    sO.set_bars(True)
    sO.set_points(False)
    print sO

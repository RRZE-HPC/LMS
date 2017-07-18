#!/usr/bin/env python

import os, sys, os.path, re, hashlib, signal, copy
from optparse import OptionParser

from jobmonitor import JobMonitor
from influxdbrouter.influxdbrouter import Measurement

from ConfigParser import SafeConfigParser
from pygrafana.api import Connection
import pygrafana.dashboard as pydash

def get_cast(v):
    if isinstance(v, bool) or str(v).lower() in ("true", "false"):
        return bool
    elif isinstance(v, int):
        return int
    elif isinstance(v, str):
        return str
    return id

def name_to_slug(name):
    return name.replace(".","-").replace(" ","-").lower()


def create_pix(jobid, panelId, path, starttime=None, endtime=None):
    if not starttime:
        starttime = int(time.time()*1E3)
    if not endtime:
        endtime = int(time.time()*1E3)
    add = {self.adminconf["pix_jobtag"] : jobid}
    if not os.path.exists(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    pic = self.gcon.get_pic(name_to_slug(self.adminconf["pix_dashboard"]), panelId, starttime, endtime, add=add, theme=self.adminconf["pix_theme"])
    if pic:
        f = open(path, "w")
        f.write(pic)
        f.close()
    else:
        print("Got no picture from grafana")

def resolve_str(s, m):
    tags = m.get_all_tags()
    for t in tags:
        s = s.replace("[tags.%s]" % t, str(tags[t]).strip("\""))
    fields = m.get_all_fields()
    for f in fields:
        if fields[f]:
            s = s.replace("[fields.%s]" % f, str(fields[f]).strip("\""))
    s = s.replace("[time]", str(m.get_time()))
    s = s.replace("[metric]", str(m.get_metric()))
    return s

def get_influx_values(data):
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

def create_url(indict, add=""):
    url = "http://%s:%s%s" % (indict["hostname"], str(indict["port"]), add)
    base64string = base64.encodestring('%s:%s' % (indict["username"], indict["password"])).replace('\n', '')
    heads = {"Authorization" : "Basic %s" % base64string,
             "Content-Type" : "application/octet-stream"}
    return url, heads

def measurement_to_text(m):
    s = ""
    s += "Job Name: %s<br>" % m.get_attr("fields.jobname")
    s += "JobID: %s<br>" % m.get_attr("tags.jobid")
    s += "User: %s<br>" % m.get_attr("tags.username")
    s += "Queue: %s<br>" % m.get_attr("fields.queue")
    s += "Walltime: %s<br>" % str(seconds_to_timedelta(m.get_attr("fields.walltime")))
    s += "Starttime: %s" % ns_to_datetime(m.get_time())
    return s


def parse_grafana_time(s):
    example = "2017-07-13T15:41:44+02:00"
    m = re.match("([\d][\d][\d][\d])-([\d][\d])-([\d][\d])T([\d][\d]):([\d][\d]):([\d][\d])([+-]*[\d][\d]:[\d][\d])", s)
    if m:
        d = datetime.datetime(int(m.group(1)),int(m.group(2)),int(m.group(3)),int(m.group(4)),int(m.group(5)),0,)
        return d
    return None


class UserJobMonitor(JobMonitor):
    def __init__(self, configfile):
        self.grafanaconf = { "hostname": "localhost",
                             "port": 3000,
                             "username": "admin",
                             "password" : "admin"}
        self.userconf = {"do_userview" : False,
                         "create_users" : False,
                         "create_user_orgs" : False,
                         "create_user_role" : "Viewer",
                         "dashboard_name" : "TestDash",
                         "delete_interval" : "30m",
                         "delete_only_unstarred" : True,
                         "create_user_ds" : True,
                         "templates" : os.path.join(os.getcwd(),"templates"),
                         "usermetrics" : False,
                         "userevents" : False,
                         "grafana_user" : "testuser",
                         "grafana_def_pass" : "testpass",
                         "grafana_org" : "testorg",
                         "grafana_datasource" : "testsource",
                         "check_metrics": True,
                         "exclude" : ""}
        self.dbconf = {"hostname" : "localhost",
                       "port" : 8086,
                       "username" : "testuser",
                       "password" : "testpass",
                       "dbname" : "testdb"}
        self.gcon = None
        self.dbs = {}
        JobMonitor.__init__(self, configfile=configfile)
    def read_grafana_config(self, configfile=None):
        if self.config and self.config.has_section("Grafana"):
            for k in self.grafanaconf:
                if self.config.has_option("Grafana", k):
                    c = get_cast(self.grafanaconf[k])
                    self.grafanaconf[k] = c(self.config.get("Grafana", k))
    def read_admin_config(self, configfile=None):
        if self.config and self.config.has_section("UserView"):
            for k in self.userconf:
                if self.config.has_option("UserView", k):
                    c = get_cast(self.userconf[k])
                    self.userconf[k] = c(self.config.get("UserView", k))

    def read_db_config(self, configfile=None):
        if self.config:
            self.userconf["user_dbs"] = {}
            sections = self.config.sections()
            for sec in sections:
                if sec.startswith("Database-"):
                    d = copy.deepcopy(self.dbconf)
                    for k in d:
                        if self.config.has_option("Database", k):
                            c = get_cast(d[k])
                            d[k] = c(self.config.get("Database", k))
                    self.userconf["user_dbs"][sec] = d
    def read_config(self, configfile=None):
        self.read_def_config(configfile=configfile)
        self.read_grafana_config(configfile=configfile)
        self.read_admin_config(configfile=configfile)
        self.read_db_config(configfile=configfile)
    def open_grafana_con(self):
        if not self.gcon:
            self.gcon = Connection( self.grafanaconf["hostname"],
                                    int(self.grafanaconf["port"]),
                                    username=self.grafanaconf["username"],
                                    password=self.grafanaconf["password"])
            if self.gcon.is_connected:
                ver = self.gcon.get_grafana_version()
                print(ver)
                pydash.set_grafana_version(ver)
            else:
                self.gcon = None
            uid = self.gcon.get_uid(grafanaconf["username"])
            if uid < 0:
                print("User for this script %s does not exist" % self.grafanaconf["username"])
                print("Exiting")
                sys.exit(1)
            self.grafanaconf["uid"] = uid
            oid = self.gcon.get_orgid_by_name(self.adminconf["organization"])
            if oid < 0:
                oid = self.gcon.add_org(self.adminconf["organization"])
                admins = [ u for u in self.gcon.get_users() if u["isAdmin"] ]
                for u in admins:
                    self.gcon.add_uid_to_orgid(u["id"], oid, login=u["login"])
            self.adminconf["oid"] = oid
    def start(self, m):
        if not self.gcon:
            self.open_grafana_con()
        user = m.get_attr("tags.username")
        jobid = m.get_attr("tags.jobid")
        tfolder = resolve_str(self.userconf["templates"], m)
        guser = resolve_str(self.userconf["grafana_user"], m)
        gpass = resolve_str(self.userconf["grafana_def_pass"], m)
        gorg = resolve_str(self.userconf["grafana_org"], m)
        gds = resolve_str(self.userconf["grafana_datasource"], m)
        dashname = resolve_str(self.userconf["dashboard_name"], m)
        print("Create dashboard %s for user %s" % (dashname, guser))
        
        udbhost = None
        
        for host,dblist in get_user_dbs().items():
            udb = resolve_str(self.userconf["user_dbs"][host]["dbname"], m)
            for db in dblist:
                if db == udb:
                    udbhost = host
        if not udbhost:
            print("Cannot find corresponding database")
            return
        
        uid = self.gcon.get_uid(guser)
        if uid < 0:
            if self.userconf["create_users"]:

                ret = self.gcon.admin_add_user(login=guser, password=gpass, name=guser)
                if not ret:
                    print("Failed to create user")
                else:
                    uid = self.gcon.get_uid(guser)
            else:
                print("User %s does not exist. Cannot create dashboard for non-existing user." % guser)
                return

        oid = self.gcon.get_orgid_by_name(gorg)
        print(oid)
        if oid < 0:
            if self.userconf["create_user_orgs"]:
                oid = self.gcon.add_org(gorg)
                if oid < 0:
                    print("Failed to create organization for user %s with name %s" % (guser, gorg))
            else:
                print("Organization %s does not exist. Cannot create dashboard without organization" % gorg)
        
        gusers = self.gcon.get_users_in_oid(oid)
        logins = [ d["login"] for d in gusers ]
        if guser not in logins:
            ret = self.gcon.add_uid_to_orgid(uid, oid, login=guser, role=self.userconf["create_user_role"])
            print(ret)
            if len(ret) == 0:
                print("Faild to add user %s to organization %s" % (guser, gorg))
        if grafanaconf["username"] not in logins:
            ret = self.gcon.add_uid_to_orgid(grafanaconf["uid"], oid, login=grafanaconf["username"], role="Admin")
            print(ret)
            if len(ret) == 0:
                print("Faild to add script user %s to organization %s" % (grafanaconf["username"], gorg))        
        
        ds = self.gcon.get_ds_by_name(gds, org=oid)
        if len(ds) == 0:
            print("Datasource %s does not exist" % gds)
            if self.userconf["create_user_ds"]:
                self.userconf["user_dbs"][host]
                udb = resolve_str(self.userconf["user_dbs"][host]["dbname"], m)
                url, heads = create_url(self.userconf["user_dbs"][host])
                gdsid = self.gcon.add_ds(gds, typ="influxdb", url=url, database=udb, orgId=oid)
        else:
            if "id" in ds:
                gdsid = ds["id"]
            else:
                print(ds)    
        
            
        
        
        if not os.path.exists(tfolder):
            print("Cannot find template folder %s" % tfolder)
        else:
            d = pydash.Dashboard(title=dashname)
            templates = []
            annotations = []
            
            if os.path.exists(os.path.join(tfolder, "global.json")):
                fp = open(os.path.join(tfolder, "global.json"))
                global_spec = json.loads(resolve_str(fp.read().strip(), m))
                fp.close()
                if global_spec.has_key("templating") and global_spec["templating"].has_key("list"):
                    for tdict in global_spec["templating"]["list"]:
                        t = pydash.Template("", "")
                        t.read_json(tdict)
                        templates.append(t)
                if global_spec.has_key("annotations") and global_spec["annotations"].has_key("list"):
                    for adict in global_spec["annotations"]["list"]:
                        a = pydash.Annotation("", "")
                        a.read_json(adict)
                        annotations.append(a)
            else:
                print("Cannot find global configurations in template folder %s" % tfolder)

            
            if self.userconf["userevents"] and os.path.exists(os.path.join(tfolder, "userevents.json")):
                fp = open(os.path.join(tfolder, "userevents.json"))
                event_spec = json.loads(resolve_str(fp.read().strip(), m))
                fp.close()
                if event_spec.has_key("annotations") and event_spec["annotations"].has_key("list") and len(event_spec["annotations"]["list"]) > 0:
                    for inp in event_spec["annotations"]["list"]:
                        a = pydash.Annotation("", "")
                        a.read_json(inp)
                        annotations.append(a)
            files = sorted(glob.glob(tfolder+"/*.json"))
            for f in files:
                if re.match(".+/(\d+).json$", f):
                    fp = open(f)
                    inp = json.loads(resolve_str(fp.read().strip(), m))
                    fp.close()
                    if inp.has_key("exec"):

                        e = re.split("\s+", inp["exec"])
                        e[0] = os.path.abspath(e[0])
                        if os.path.exists(e[0]):
                            for i, elem in enumerate(e):
                                e[i] = elem.replace("$DB", database).replace("$NAME",name).replace("$SRC", datasource)
                            p = subprocess.Popen(" ".join(e), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,close_fds=True)
                            out, err = p.communicate()
                            if p.returncode != 0:
                                print(err)
                                continue
                            try:
                                j = json.loads(out)
                            except:
                                continue
                            inp = j
                    if inp.has_key("type"):
                        c = pydash.guess_panel(inp["type"])
                        if c:
                            c.read_json(inp)
                            r = pydash.Row()
                            r.add_panel(c)
                            d.add_row(r)
                    if inp.has_key("dashboard"):
                        d = pydash.read_json(inp)
                        if d:
                            d.set_title(name)
                    if inp.has_key("height"):
                        r = pydash.Row()
                        r.read_json(inp)
                        d.add_row(r)
            for t in templates:
                t.set_refresh(1)
                d.add_template(t)
            for a in annotations:
                d.add_annotation(a)
            d.set_startTime(ns_to_datetime(m.get_time()))
            d.set_refresh("5m")
            d.set_endTime("now")
            d.set_id(0)
            d.set_overwrite("True")
            d.set_datasource(gds)
            f = open("userdash.json", "w")
            f.write(json.dumps(d.get(), sort_keys=True, indent=4, separators=(',', ': ')))
            f.close()
            print(jobid, name_to_slug(jobid))
            self.gcon.del_dashboard(name_to_slug(jobid))
            ret = self.gcon.add_dashboard(d, org=oid)
            print(ret)
        
        if user not in self.userjobstore:
            self.userjobstore[user] = {}
        if jobid not in self.userjobstore[user]:
            self.userjobstore[user][jobid] = m
    def update(self, m):
        print("Check all dashboards for outdated ones")
        starred = not self.userconf["delete_only_unstarred"]
        if self.userconf["delete_only_unstarred"]:
            print("but only unstarred ones")

        orgs = self.gcon.get_orgs()
        alld = []
        for o in orgs:
            self.gcon.change_active_org(o["id"])
            tmp = self.gcon.search_dashboard(query="", starred=starred)
            alld += tmp
        print(alld)
        thres_date = datetime.datetime.now()-datetime.timedelta(seconds=interval_to_seconds(self.userconf["delete_interval"]))
        for d in alld:
            if self.userconf["delete_only_unstarred"]:
                dash = self.gcon.get_dashboard(name_to_slug(d["title"]))
                lastchange = dash["meta"]["updated"]
                if parse_grafana_time(lastchange) < thres_date:
                    self.gcon.del_dashboard(name_to_slug(d["title"]))
    def stop(self, m):
        user = m.get_attr("tags.username")
        jobid = m.get_attr("tags.jobid")
        if user not in self.userjobstore:
            return
        if jobid in self.userjobstore[user]:
            oldm = self.userjobstore[user][jobid]
        else:
            print("No start measurement avaliable")
        dashname = resolve_str(self.userconf["dashboard_name"], m)
        gorg = resolve_str(self.userconf["grafana_org"], m)
        gds = resolve_str(self.userconf["grafana_datasource"], m)
        print("Update dashboard %s for user %s to new endtime %s" % (dashname, user, str(ns_to_datetime(m.get_time()))))
        oid = self.gcon.get_orgid_by_name(gorg)
        try:
            d = self.gcon.get_dashboard(name_to_slug(dashname), oid=oid)
            d = pydash.read_json(d)
        except:
            print("Cannot find dashboard for %s")
        d.set_startTime(ns_to_datetime(oldm.get_time()))
        d.set_endTime(ns_to_datetime(m.get_time()))
        d.set_datasource(gds)
        d.set_refresh(None)
        d.set_overwrite(True)
        
        ret = self.gcon.add_dashboard(d, org=oid)
        
        del self.userjobstore[user][jobid]
        if len(self.userjobstore[user]) == 0:
            del self.userjobstore[user]


def main():
    parser = OptionParser()
    parser.add_option("-c", "--config", dest="configfile", help="Configuration file", default=sys.argv[0]+".conf", metavar="FILE")
    (options, args) = parser.parse_args()
    mymon = UserJobMonitor(configfile=options.configfile)
    mymon.recv_loop()

if __name__ == "__main__":
    main()

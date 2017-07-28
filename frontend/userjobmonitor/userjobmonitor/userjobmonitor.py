#!/usr/bin/env python

import os, sys, os.path, re, hashlib, signal, copy
from optparse import OptionParser
import logging, datetime, threading, time, json
import base64, urllib2, glob
from string import capwords

from influxdbrouter import JobMonitor, Measurement
from influxdbrouter.jobmonitor import parse_interval

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

def ns_to_datetime(v):
    if isinstance(v, str):
        v = int(v)
    v_fl = float(v)/1E9
    v_int = v/1E9
    ms = int((v_fl - float(v_int))*1E6)
    d = datetime.datetime.fromtimestamp(v_int)
    d = d.replace(microsecond=ms)
    return d



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
    fields = m.get_all_fields()
    for t in fields:
        s += "%s: %s<br>" % (capwords(t), str(fields[t]).strip("\""))
    tags = m.get_all_fields()
    for t in tags:
        s += "%s: %s<br>" % (capwords(t), str(tags[t]).strip("\""))
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
                         "def_templates" : os.path.join(os.getcwd(),"templates"),
                         "usermetrics" : False,
                         "userevents" : False,
                         "grafana_user" : "testuser",
                         "grafana_def_pass" : "testpass",
                         "grafana_org" : "testorg",
                         "grafana_datasource" : "testsource",
                         "check_metrics": True,
                         "exclude" : "",
                         "search_query": "",
                         "exclude_orgs" : ""}
        self.dbconf = {"hostname" : "localhost",
                       "port" : 8086,
                       "username" : "testuser",
                       "password" : "testpass",
                       "dbname" : "testdb",
                       "exclude" : ""}
        self.gcon = None
        self.dbs = {}
        self.userjobstore = {}
        self.user_databases = {}
        self.orgdashs = {}
        self.databases_last_update = None
        JobMonitor.__init__(self, configfile=configfile)
    def read_grafana_config(self, configfile=None):
        if self.config and self.config.has_section("Grafana"):
            for k in self.grafanaconf:
                if self.config.has_option("Grafana", k):
                    c = get_cast(self.grafanaconf[k])
                    self.grafanaconf[k] = c(self.config.get("Grafana", k))
    def read_user_config(self, configfile=None):
        if self.config and self.config.has_section("UserView"):
            for k in self.userconf:
                if self.config.has_option("UserView", k):
                    c = get_cast(self.userconf[k])
                    self.userconf[k] = c(self.config.get("UserView", k))
            self.userconf["exclude"] = re.split("\s*,\s*", self.userconf["exclude"])
            self.userconf["exclude_orgs"] = re.split("\s*,\s*", self.userconf["exclude_orgs"])
    def read_db_config(self, configfile=None):
        if self.config:
            self.userconf["user_dbs"] = {}
            sections = self.config.sections()
            for sec in sections:
                if sec.startswith("Database-"):
                    d = copy.deepcopy(self.dbconf)
                    for k in d:
                        if self.config.has_option(sec, k):
                            c = get_cast(d[k])
                            d[k] = c(self.config.get(sec, k))
                    d["exclude"] = re.split("\s*,\s*", d["exclude"])
                    self.userconf["user_dbs"][sec.replace("Database-","")] = d
    def read_config(self, configfile=None):
        self.read_def_config(configfile=configfile)
        self.read_grafana_config(configfile=configfile)
        self.read_user_config(configfile=configfile)
        self.read_db_config(configfile=configfile)
    def open_grafana_con(self):
        if not self.gcon:
            logging.info("Opening connection to Grafana %s:%s User %s" % (self.grafanaconf["hostname"],
                                                                         self.grafanaconf["port"],
                                                                         self.grafanaconf["username"]))
            self.gcon = Connection( self.grafanaconf["hostname"],
                                    int(self.grafanaconf["port"]),
                                    username=self.grafanaconf["username"],
                                    password=self.grafanaconf["password"])
            if self.gcon.is_connected:
                ver = self.gcon.get_grafana_version()
                logging.debug("Setting Grafana version for Dashboard module to %s" % ver)
                pydash.set_grafana_version(ver)
            else:
                self.gcon = None
                logging.error("Cannot open connection to Grafana. Exiting....")
                sys.exit(1)
            logging.debug("Getting Grafana user identifier for the script user %s" % self.grafanaconf["username"])
            uid = self.gcon.get_uid(self.grafanaconf["username"])
            if uid < 0:
                logging.error("User for this script %s does not exist. Exiting!" % self.grafanaconf["username"])
                sys.exit(1)
            self.grafanaconf["uid"] = uid
            logging.debug("Getting Grafana user has identifier %d" % uid)
            self.update_orgdashs()
    
    def get_user_dbs(self):
        need_update = False
        if len(self.user_databases) == 0 and len(self.userconf["user_dbs"]) > 0:
            need_update = True
        delta = datetime.timedelta(seconds=parse_interval(self.interval))
        if self.databases_last_update and self.databases_last_update + delta > datetime.datetime.now():
            need_update = True

        if need_update:
            for dbhost in self.userconf["user_dbs"]:
                db = self.userconf["user_dbs"][dbhost]
                url, heads = create_url(db, "/query?q=show+databases")
                heads = {"Content-Type" : "application/octet-stream"}
                req = urllib2.Request(url, headers=heads)
                resp = None
                data = []
                try:
                    resp = urllib2.urlopen(req)
                except urllib2.URLError as e:
                    logging.error("Cannot retrieve list of databases from %s" % dbhost)
                    continue
                if resp:
                    data = get_influx_values(resp.read())
                    resp.close()
                if dbhost not in self.user_databases:
                    self.user_databases[dbhost] = []
                for x in data:
                    if x["name"] not in self.user_databases[dbhost] and x["name"] not in db["exclude"]:
                        self.user_databases[dbhost].append(x["name"])
            self.databases_last_update = datetime.datetime.now()
        else:
            logging.debug("Return old user databases, timedelta since last check too small")
        return self.user_databases

    def start(self, m):
        if not self.gcon:
            self.open_grafana_con()
        user = m.get_attr("tags.username")
        jobid = m.get_attr("tags.jobid")
        tfolder = resolve_str(self.userconf["templates"], m)
        if not os.path.exists(tfolder):
            logging.warn("Template folder %s does not exist, trying default template path" % self.userconf["templates"])
            tfolder = resolve_str(self.userconf["def_templates"], m)
        guser = resolve_str(self.userconf["grafana_user"], m)
        gpass = resolve_str(self.userconf["grafana_def_pass"], m)
        gorg = resolve_str(self.userconf["grafana_org"], m)
        gds = resolve_str(self.userconf["grafana_datasource"], m)
        dashname = resolve_str(self.userconf["dashboard_name"], m)
        logging.info("Create dashboard %s for user %s" % (dashname, guser))
        
        udbhost = None
        
        for host,dblist in self.get_user_dbs().items():
            udb = resolve_str(self.userconf["user_dbs"][host]["dbname"], m)
            for db in dblist:
                if db == udb:
                    udbhost = host
                    break
        if not udbhost:
            logging.error("Cannot find corresponding database")
            return
        
        uid = self.gcon.get_uid(guser)
        logging.debug("UserID for user %s: %d" % (guser, uid))
        if uid < 0:
            if self.userconf["create_users"]:
                logging.debug("Adding user %s" % guser)
                ret = self.gcon.admin_add_user(login=guser, password=gpass, name=guser)
                if not ret:
                    logging.error("Failed to create user")
                    return
                else:
                    uid = self.gcon.get_uid(guser)
            else:
                logging.error("User %s does not exist. Cannot create dashboard for non-existing user." % guser)
                return

        oid = self.gcon.get_orgid_by_name(gorg)
        logging.debug("OrgID for org %s: %d" % (gorg, oid))
        if oid < 0:
            if self.userconf["create_user_orgs"]:
                logging.debug("Adding organization %s" % gorg)
                oid = self.gcon.add_org(gorg)
                if oid < 0:
                    logging.error("Failed to create organization for user %s with name %s" % (guser, gorg))
                    return
            else:
                logging.error("Organization %s does not exist. Cannot create dashboard without organization" % gorg)
                return
        
        gusers = self.gcon.get_users_in_oid(oid)
        logins = [ d["login"] for d in gusers ]
        if guser not in logins:
            logging.debug("Adding user %s to organization %s" % (guser, gorg))
            ret = self.gcon.add_uid_to_orgid(uid, oid, login=guser, role=self.userconf["create_user_role"])
            if len(ret) == 0:
                logging.error("Failed to add user %s to organization %s" % (guser, gorg))
        if self.grafanaconf["username"] not in logins:
            ret = self.gcon.add_uid_to_orgid(self.grafanaconf["uid"], oid, login=self.grafanaconf["username"], role="Admin")
            if len(ret) == 0:
                logging.error("Failed to add script user %s to organization %s" % (self.grafanaconf["username"], gorg))
        
        ds = self.gcon.get_ds_by_name(gds, org=oid)
        if len(ds) == 0:
            logging.debug("Datasource %s does not exist" % gds)
            if self.userconf["create_user_ds"]:
                self.userconf["user_dbs"][host]
                udb = resolve_str(self.userconf["user_dbs"][host]["dbname"], m)
                url, heads = create_url(self.userconf["user_dbs"][host])
                gdsid = self.gcon.add_ds(gds, typ="influxdb", url=url, database=udb, orgId=oid)
        else:
            if "id" in ds:
                gdsid = ds["id"]


        if not os.path.exists(tfolder):
            logging.error("Cannot find template folder %s" % tfolder)
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
                logging.warn("Cannot find global configurations in template folder %s" % tfolder)

            
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
            self.gcon.del_dashboard(name_to_slug(jobid))
            ret = self.gcon.add_dashboard(d, org=oid)
            if len(ret) != 0:
                logging.debug("Created dashboard %s for user %s in org %s" % (name_to_slug(jobid),guser, gorg))
            else:
                logging.error("Failed to create dashboard %s for user %s in org %s" % (name_to_slug(jobid),guser, gorg))

        if oid not in self.orgdashs:
            self.orgdashs[oid] = [name_to_slug(jobid)]
        else:
            self.orgdashs[oid].append(name_to_slug(jobid))
        if user not in self.userjobstore:
            self.userjobstore[user] = {}
        if jobid not in self.userjobstore[user]:
            self.userjobstore[user][jobid] = m
    def update(self):
        
        if self.userconf["delete_only_unstarred"]:
            logging.info("Check all dashboards for outdated ones but only unstarred ones")
        else:
            logging.info("Check all dashboards for outdated ones")

        delta = datetime.timedelta(seconds=parse_interval(self.userconf["delete_interval"]))
        thres_date = datetime.datetime.now() - delta
        deloids = []
        for oid in self.orgdashs:
            self.gcon.change_active_org(oid)
            delslugs = []
            for slug in self.orgdashs[oid]:
                dash = self.gcon.get_dashboard(slug)
                print(dash)
                if self.userconf["delete_only_unstarred"]:
                    if "meta" in dash and "isStarred" in dash["meta"] and dash["meta"]["isStarred"]:
                        continue
                if "meta" in dash and "updated" in dash["meta"]:
                    lastchange = dash["meta"]["updated"]
                    if parse_grafana_time(lastchange) < thres_date:
                        logging.info("Delete dashboard %s in organization %d" % (slug, oid))
                        self.gcon.del_dashboard(slug)
                        delslugs.append(slug)
                else:
                    logging.info("Cannot check timestamp for slug %s, no such field" % slug)
            for d in delslugs:
                self.orgdashs[oid].remove(d)
            if len(self.orgdashs[oid]) == 0:
                deloids.append(oid)
        for oid in deloids:
            del self.orgdashs[oid]
    def update_orgdashs(self):
        orgs = self.gcon.get_orgs()
        for o in orgs:
            oid = o["id"]
            if o["name"] in self.userconf["exclude_orgs"]:
                continue
            dashboards = self.gcon.search_dashboard(self.userconf["search_query"], oid=oid)
            if len(dashboards) > 0 and oid not in self.orgdashs:
                self.orgdashs[oid] = []
            for d in dashboards:
                self.orgdashs[oid].append(name_to_slug(d["title"]))
    def stop(self, m):
        user = m.get_attr("tags.username")
        jobid = m.get_attr("tags.jobid")
        if user not in self.userjobstore:
            return
        if jobid in self.userjobstore[user]:
            oldm = self.userjobstore[user][jobid]
        else:
            logging.warn("No start signal measurement for received stop signal available")
        dashname = resolve_str(self.userconf["dashboard_name"], m)
        gorg = resolve_str(self.userconf["grafana_org"], m)
        gds = resolve_str(self.userconf["grafana_datasource"], m)
        
        oid = self.gcon.get_orgid_by_name(gorg)
        try:
            d = self.gcon.get_dashboard(name_to_slug(dashname), oid=oid)
            d = pydash.read_json(d)
        except:
            logging.warn("Cannot find dashboard for %s" % dashname)
        if d:
            logging.info("Update dashboard %s for user %s to new endtime %s" % (dashname, user, str(ns_to_datetime(m.get_time()))))
            d.set_startTime(ns_to_datetime(oldm.get_time()))
            d.set_endTime(ns_to_datetime(m.get_time()))
            d.set_datasource(gds)
            d.set_refresh(None)
            d.set_overwrite(True)
            ret = self.gcon.add_dashboard(d, org=oid)

        if oid in self.orgdashs:
            slug = name_to_slug(dashname)
            if slug in self.orgdashs[oid]:
                self.orgdashs[oid].remove(slug)
            if len(self.orgdashs[oid]) == 0:
                del self.orgdashs[oid]
        if user in self.userjobstore:
            if jobid in self.userjobstore[user]:
                del self.userjobstore[user][jobid]
            else:
                logging.warn("Stop signal for user %s and job %s which is not registered" % (user, jobid))
        else:
            logging.warn("Stop signal for user %s who has no job registered" % user)
        if user in self.userjobstore and len(self.userjobstore[user]) == 0:
            del self.userjobstore[user]



def main():
    parser = OptionParser()
    parser.add_option("-c", "--config", dest="configfile", help="Configuration file", default=sys.argv[0]+".conf", metavar="FILE")
    (options, args) = parser.parse_args()
    if not os.path.exists(options.configfile):
        print("Cannot read configuration file %s" % options.configfile)
        sys.exit(1)
    mymon = UserJobMonitor(configfile=options.configfile)
    try:
        mymon.recv_loop()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()

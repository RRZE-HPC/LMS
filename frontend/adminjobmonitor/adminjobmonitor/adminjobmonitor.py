#!/usr/bin/env python

import os, sys, os.path, re, hashlib, signal
from optparse import OptionParser

from jobmonitor import JobMonitor, Measurement


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
    pic = gcon.get_pic(name_to_slug(self.adminconf["pix_dashboard"]), panelId, starttime, endtime, add=add, theme=self.adminconf["pix_theme"])
    if pic:
        f = open(path, "w")
        f.write(pic)
        f.close()
    else:
        print("Got no picture from grafana")


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

def create_adm_job_panel(m):
    
    # Get jobid of current measurement. Measurement must be a signal/event measurement
    jobid = m.get_attr("tags.jobid")
    global jobdashboard
    if not jobdashboard:
        jobdashboard = gcon.get_dashboard(name_to_slug(self.adminconf["pix_dashboard"]), oid=self.adminconf["oid"])
    global jobdashpanels
    if not jobdashpanels:
        for ppart in self.adminconf["panels"]:
            for r in jobdashboard["dashboard"]["rows"]:
                for p in r["panels"]:
                    if re.search(ppart, p["title"]):
                        jobdashpanels[p["id"]] = p["title"]
    hstr = ""
    for elem in self.adminconf["pix_hash"]:
        hstr += m.get_attr(elem)
    h = hashlib.sha224(hstr)
    jobhash = hashlib.sha224(jobid).hexdigest()
    pixfolder = os.path.join(self.adminconf["pix_path"], str(h.hexdigest()))
    pixurl = self.adminconf["pix_url"]+"/"+str(h.hexdigest())
    pixurl = pixurl.replace("//","/").replace("http:/","http://")
    linkurl = "http://%s:%s/dashboard/db/%s?var-%s=%s" % (grafanaconf["hostname"], str(grafanaconf["port"]), name_to_slug(self.adminconf["pix_dashboard"]), self.adminconf["pix_jobtag"], jobid)
    
    func = "<div id=\"%s\" class=\"ng-scope\">\n" % jobhash
    func += "<script type=\"text/javascript\">\n"
    func += "$(document).ready(function() {\n"
    

    tab = "<table border=\"0\" id=\"tab-%s\">\n" % jobhash
    tab += "<tr>\n"
    tab +=" <td>%s</td>\n" % measurement_to_text(m)
    
    funcs = []
    tablines = []
    for pid in sorted(jobdashpanels.keys()):
        t = "<td><a href=\""+linkurl+"\" target=\"_blank\">"
        pixpath = os.path.join(pixfolder, "%d.png" % pid)
        create_pix(jobid, pid, pixpath, starttime=m.get_time())
        picurl = pixurl+"/%d.png" % pid
        t += "<img id=\"%s-%d\" src=\"%s\" alt=\"%s for Job %s\">\n" % (jobhash, pid, picurl, jobdashpanels[pid], jobid)
        t += "</img></a></td>\n"
        tablines.append(t)
        f = "$('table#tab-%s img#%s-%d').attr('src', '%s?' + new Date().getTime());" % (jobhash, jobhash, pid, picurl)
        
        funcs.append(f)
    
    func += "\n".join(funcs) + "\n"
    func += "angular.element('#%s').injector().get('$rootScope').$on('refresh', function() {" % jobhash
    func += "\n".join(funcs) + "\n"
    func += "});\n});\n</script>\n</div>"
    
    tab += "\n".join(tablines) + "\n"
    
    tab += "</tr>\n"
    tab += "</table>\n"
    panel = pydash.TextPanel(title=jobid)
    panel.set_mode("html")
    panel.set_content(func+"\n\n"+tab)

    return panel

def add_admin_job(newjob):
    jobid = newjob.get_attr("tags.jobid")
    print("Add %s to admin_view" % jobid)
    try:
        d = gcon.get_dashboard(name_to_slug(adminconf["dashboard"]), oid=adminconf["oid"])
        d = pydash.read_json(d)
    except:
        d = pydash.Dashboard(title=adminconf["dashboard"])
        pass
    print(d)

    panel = create_adm_job_panel(newjob)
    
    i = 1
    for r in d.rows:
        print("\""+str(r)+"\"")
        for p in r.panels:
            i = p["id"]+1
            break
    panel.set_id(i)
    row = pydash.Row(title=jobid)
    row.add_panel(panel)
    d.rows = [row] + d.rows
    d.set_overwrite(True)
    f = open("admindash.json", "w")
    f.write(json.dumps(d.get(), sort_keys=True, indent=4, separators=(',', ': ')))
    f.close()
    try:
        ret = gcon.add_dashboard(d)
    except:
        print("Cannot upload updated dashboard")
    jobstore[jobid] = newjob
        


def del_admin_job(deljob):
    jobid = deljob.get_attr("tags.jobid")
    if not jobid:
        print("Cannot delete job without JobID")
        return
    print("Remove %s from admin_view" % jobid)

    try:
        d = gcon.get_dashboard(name_to_slug(adminconf["dashboard"]), oid=adminconf["oid"])
        d = pydash.read_json(d)
    except:
        print("Cannot download admin dashboard %s" % adminconf["dashboard"])
        return
    idx = -1
    for i,r in enumerate(d.rows):
        if r.title == jobid:
            idx = i
            break
    if idx >= 0:
        del d.rows[idx]
        idx = 1
        for r in d.rows:
            for p in r.panels:
                p.set_id(idx)
                idx += 1
    else:
        print("Cannot find job %s in dashboard" % jobid)
        return
    try:
        d.gcon.add_dashboard(d)
    except:
        print("Cannot upload updated dashboard")
    hstr = ""
    for elem in adminconf["pix_hash"]:
        hstr += deljob.get_attr(elem)
    h = hashlib.sha224(hstr)
    pixfolder = os.path.join(adminconf["pix_path"], str(h.hexdigest()))
    if os.path.exists(pixfolder):
        os.remove(pixfolder)
    del jobstore[jobid]
    


def update_admin_pix():
    print("Update Pics")
    global jobdashboard
    if not jobdashboard:
        jobdashboard = gcon.get_dashboard(name_to_slug(adminconf["pix_dashboard"]), oid=adminconf["oid"])
    global jobdashpanels
    if not jobdashpanels:
        for ppart in adminconf["panels"]:
            for r in jobdashboard["dashboard"]["rows"]:
                for p in r["panels"]:
                    if re.search(ppart, p["title"]):
                        jobdashpanels[p["id"]] = p["title"]
    curtime = int(time.time())*1E3
    for jobid in jobstore:
        m = jobstore[jobid]
        hstr = ""
        for elem in adminconf["pix_hash"]:
            hstr += m.get_attr(elem)
        h = hashlib.sha224(hstr)
        jobhash = hashlib.sha224(jobid).hexdigest()
        pixfolder = os.path.join(adminconf["pix_path"], str(h.hexdigest()))
        for pid in sorted(jobdashpanels.keys()):
            pixpath = os.path.join(pixfolder, "%d.png" % pid)
            create_pix(jobid, pid, pixpath, starttime="%d" % m.get_time(), endtime="%d" % curtime)


class AdminJobMonitor(JobMonitor):
    def __init__(self, configfile):
        self.grafanaconf = { "hostname": "localhost",
                             "port": 3000,
                             "username": "admin",
                             "password" : "admin"}
        self.adminconf = {   "organization" : "AdminOrg",
                             "pix_interval" : "5m",
                             "dashboard" : "AdminView",
                             "panels" : "",
                             "pix_interval" : "5m",
                             "pix_dashboard" : "TestDash",
                             "pix_jobtag": "JobID",
                             "pix_hash" : "",
                             "pix_path" : "./pix",
                             "pix_theme": "light",
                             "pix_url" : "http://localhost:8092"}
        self.dbconf = {"hostname" : "localhost",
                       "port" : 8086,
                       "username" : "testuser",
                       "password" : "testpass",
                       "dbname" : "testdb"}
        self.gcon = None
        JobMonitor.__init__(self, configfile=configfile)
    def read_grafana_config(self, configfile=None):
        if self.config and self.config.has_section("Grafana"):
            for k in self.grafanaconf:
                if self.config.has_option("Grafana", k):
                    c = get_cast(self.grafanaconf[k])
                    self.grafanaconf[k] = c(self.config.get("Grafana", k))
    def read_admin_config(self, configfile=None):
        if self.config and self.config.has_section("AdminView"):
            for k in self.adminconf:
                if self.config.has_option("AdminView", k):
                    c = get_cast(self.adminconf[k])
                    self.adminconf[k] = c(self.config.get("AdminView", k))
        self.adminconf["panels"] = re.split("\s*,\s*", self.adminconf["panels"])
        self.adminconf["pix_hash"] = re.split("\s*,\s*", self.adminconf["pix_hash"])
    def read_db_config(self, configfile=None):
        if self.config and self.config.has_section("Database"):
            for k in self.dbconf:
                if self.config.has_option("Database", k):
                    c = get_cast(self.dbconf[k])
                    self.dbconf[k] = c(self.config.get("Database", k))
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
        add_admin_job(m)
    def stop(self, m):
        del_admin_job(m)
    def update(self, m):
        update_admin_pix()


def main():
    parser = OptionParser()
    parser.add_option("-c", "--config", dest="configfile", help="Configuration file", default=sys.argv[0]+".conf", metavar="FILE")
    (options, args) = parser.parse_args()
    mymon = AdminJobMonitor(configfile=options.configfile)
    mymon.recv_loop()

if __name__ == "__main__":
    main()

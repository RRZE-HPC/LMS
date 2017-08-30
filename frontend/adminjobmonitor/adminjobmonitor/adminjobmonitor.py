#!/usr/bin/env python

import os, sys, os.path, re, hashlib, signal, urllib2
from optparse import OptionParser
from string import Template, capwords
from influxdbrouter import JobMonitor, Measurement
import logging, datetime, threading, time, json


from ConfigParser import SafeConfigParser
from pygrafana.api import Connection
import pygrafana.dashboard as pydash

from SocketServer import ThreadingMixIn
from SocketServer import TCPServer
from SimpleHTTPServer import SimpleHTTPRequestHandler

def get_cast(v):
    if isinstance(v, bool) or str(v).lower() in ("true", "false"):
        return bool
    elif isinstance(v, int):
        return int
    elif isinstance(v, str):
        return str
    return id

def name_to_slug(name):
    return name.replace(".","-").replace(" ","-").replace("(","").replace(")","").lower()


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

class AdminJobHTTPServer(ThreadingMixIn, TCPServer, object):
    def __init__(self, path, server_address, RequestHandlerClass):
        self.timeout = 1
        self.path = path
        request_queue_size = 100

        super(AdminJobHTTPServer, self).__init__(server_address, RequestHandlerClass)

class AdminJobHandler(SimpleHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        self.timeout = 1
        SimpleHTTPRequestHandler.__init__(self, request, client_address, server)
    def log_message(self,fmt, *args):
        pass

class AdminJobServer(threading.Thread):
    def __init__(self, path, server_address):
        self.path = os.path.abspath(path)
        self.server_address = server_address
        self.server = None
        self.terminate = False
        os.chdir(self.path)
        threading.Thread.__init__(self)
    def term(self):
        self.terminate = True
        req = urllib2.Request("http://%s:%d" % self.server_address)
        resp = urllib2.urlopen(req)
        resp.close()
    def run(self):
        if not self.server:
            self.server = AdminJobHTTPServer(self.path, self.server_address, AdminJobHandler)
        while not self.terminate:
            self.server.handle_request()


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
                             "dumpfile" : "",
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
        self.update_t = None
        self.gcon = None
        self.jobstore = {}
        self.panels_for_pix = []
        self.pixserver = None
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
        if len(self.adminconf["dumpfile"]) > 0:
            if os.path.exists(os.path.dirname(os.path.abspath(self.adminconf["dumpfile"]))):
                self.adminconf["dumpfile"] = os.path.abspath(self.adminconf["dumpfile"])
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
        if not self.pixserver:
            self.open_http_server()
        if not self.gcon:
            self.open_grafana_con()
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
                print("User for this script %s does not exist" % self.grafanaconf["username"])
                print("Exiting")
                sys.exit(1)
            self.grafanaconf["uid"] = uid
            logging.debug("Getting Grafana user has identifier %d" % uid)
            logging.debug("Getting Grafana organization identifier for the admin organization %s" % self.adminconf["organization"])
            oid = self.gcon.get_orgid_by_name(self.adminconf["organization"])
            if oid < 0:
                logging.debug("Adding Grafana organization %s" % self.adminconf["organization"])
                oid = self.gcon.add_org(self.adminconf["organization"])
                admins = [ u for u in self.gcon.get_users() if u["isAdmin"] ]
                logging.debug("Adding all admins to new Grafana organization %s" % self.adminconf["organization"])
                for u in admins:
                    logging.debug("Adding all admin %s Grafana organization %s" % (u["login"],self.adminconf["organization"]))
                    self.gcon.add_uid_to_orgid(u["id"], oid, login=u["login"])
            logging.debug("Grafana organization identifier for the admin organization %d" % oid)
            self.adminconf["oid"] = oid
            logging.debug("Getting picture dashboard '%s' Slug %s" % (self.adminconf["pix_dashboard"], name_to_slug(self.adminconf["pix_dashboard"])))
            jobdashboard = self.gcon.get_dashboard(name_to_slug(self.adminconf["pix_dashboard"]), oid=self.adminconf["oid"])

            if len(jobdashboard) > 0:
                logging.debug("Getting panel identifiers from picture dashboard")
                for ppart in self.adminconf["panels"]:
                    for r in jobdashboard["dashboard"]["rows"]:
                        for p in r["panels"]:
                            if re.search(ppart, p["title"]):
                                logging.debug("Adding panel identifier %d: %s" % (p["id"], p["title"]))
                                self.panels_for_pix.append((p["id"], p["title"]))
            logging.info("Opened connection to Grafana")
    def open_http_server(self):
        m = re.match("http://(.+):(\d+)[/]*", self.adminconf["pix_url"])
        if m and not self.pixserver:
            host, port = m.groups()
            logging.info("Publishing pix folder %s at %s" % (self.adminconf["pix_path"],self.adminconf["pix_url"]))
            self.pixserver = AdminJobServer(self.adminconf["pix_path"], (host, int(port)))
            self.pixserver.start()
    def add_admin_job(self, newjob):
        jobid = newjob.get_attr("tags.jobid")
        logging.info("Adding new job %s" % jobid)
        logging.debug("Get admin dashboard '%s' Slug %s" % (self.adminconf["dashboard"], name_to_slug(self.adminconf["dashboard"])))
        try:
            slug = name_to_slug(self.adminconf["dashboard"])
            d = self.gcon.get_dashboard(slug, oid=int(self.adminconf["oid"]))
        except Exception as e:
            logging.debug("Failed to get admin dashboard, creating a new one")
            logging.debug(e)
            d = pydash.Dashboard(title=self.adminconf["dashboard"])
            d.set_refresh ("1m")
            pass
        if not isinstance(d, pydash.Dashboard):
            d = pydash.read_json(d)
        t = newjob.get_time()
        if not t:
            newjob.set_time(int(time.time()*1E9))
        panel = self.create_adm_job_panel(newjob)


        logging.debug("Create row with title %s" % jobid)
        row = pydash.Row(title=jobid)
        row.add_panel(panel)

        newrows = [row]
        for r in d.rows:
            newrows.append(r)
        d.rows = []
        for r in newrows:
            d.add_row(r)

        d.set_overwrite(True)
        d.set_refresh ("1m")
        if len(self.adminconf["dumpfile"]) > 0:
            logging.debug("Dumping dashboard to file %s" % self.adminconf["dumpfile"])
            f = open("admindash.json", "w")
            f.write(json.dumps(d.get(), sort_keys=True, indent=4, separators=(',', ': ')))
            f.close()
        logging.info("Adding dashboard to Grafana")
        try:
            ret = self.gcon.add_dashboard(d, org=int(self.adminconf["oid"]))
            logging.debug("Added successfully")
        except:
            logging.error("Cannot upload updated dashboard")
        self.jobstore[jobid] = newjob
    def measurement_to_text(self,m):
        s = ""
        tags = m.get_all_tags()
        for t in tags:
            s += "<b>%s</b>: %s<br>" % (capwords(t), str(tags[t]).strip("\""))
        fields = m.get_all_fields()
        for t in fields:
            s += "<b>%s</b>: %s<br>" % (capwords(t), str(fields[t]).strip("\""))
        return s
    def create_pix(self, jobid, panelId, path, starttime=None, endtime=None):
        if not starttime:
            starttime = int(time.time()*1E3)
        if not endtime:
            endtime = int(time.time()*1E3)
        add = {self.adminconf["pix_jobtag"] : jobid}
        if not os.path.exists(os.path.dirname(os.path.abspath(path))):
            logging.debug("Creating picture directory %s" % os.path.dirname(os.path.abspath(path)))
            os.makedirs(os.path.dirname(path))
        pic = self.gcon.get_pic(name_to_slug(self.adminconf["pix_dashboard"]), panelId, starttime, endtime, add=add, theme=self.adminconf["pix_theme"], height=900)
        if pic:
            f = open(path, "w")
            f.write(pic)
            f.close()
        else:
            print("Got no picture from grafana")
            logging.error("Got no picture from grafana from dashboard %s panel %d" % (name_to_slug(self.adminconf["pix_dashboard"]), panelId))
    def create_adm_job_panel(self,m):
        
        # Get jobid of current measurement. Measurement must be a signal/event measurement
        jobid = m.get_attr("tags.jobid")
        sub = {"jobid" : jobid}
        hstr = ""
        for elem in self.adminconf["pix_hash"]:
            hstr += m.get_attr(elem)
        h = hashlib.sha224(hstr)
        jobhash = str(h.hexdigest())
        logging.debug("Hash for job %s" % jobhash)
        sub.update({"hash" : jobhash})
        pixfolder = os.path.join(self.adminconf["pix_path"], jobhash)
        logging.debug("Creating pics in %s" % pixfolder)
        defpixurl = self.adminconf["pix_url"]+"/"+self.adminconf["pix_path"]+"/"+str(h.hexdigest())
        defpixurl = defpixurl.replace("//","/").replace("http:/","http://")
        logging.debug("Offering pics at %s" % defpixurl)
        starttime = int(m.get_time()/1E6)
        endtime = int(time.time()*1E3)
        linkurl = "http://%s:%s/dashboard/db/%s?var-%s=%s&from=%s&to=now" % (self.grafanaconf["hostname"], str(self.grafanaconf["port"]), name_to_slug(self.adminconf["pix_dashboard"]), self.adminconf["pix_jobtag"], jobid, starttime)
        logging.debug("Link url to job dashboard: %s" % linkurl)
        sub.update({"linkurl" : linkurl})

        # Defining templates for javascript
        t_funcs = Template("""
        <div id=\"$hash\" class=\"ng-scope\">
        <script type=\"text/javascript\">
        $(document).ready(function() {
            angular.element('#tab-$hash').injector().get('$rootScope').$on('refresh', function() {
                $funcs
            });
        });
        </script>
        </div>
        """)
        t_func = Template("""
        $('table#tab-$hash img#$hash-$panel').attr('src', '$picurl?' + new Date().getTime());
        """)
        # Defining templates for html table
        t_table = Template("""
        <table border=\"0\" id=\"tab-$hash\">
        <tr>
        <td>$header</td>
        $elements
        </tr>
        </table>
        """)
        t_tentry = Template("""
        <td>
        <a href=\"$linkurl\" target=\"_blank\">
        <img id=\"$hash-$panel\" src=\"$picurl\" alt=\"$ptitle for Job $jobid\"></img>
        </a>
        </td>
        """)

        funcs = []
        tablines = []
        for pid,ptitle in self.panels_for_pix:
            pixpath = os.path.join(pixfolder, "%d.png" % pid)
            logging.debug("Creating pic at %s" % pixpath)
            self.create_pix(jobid, pid, pixpath, starttime=starttime, endtime=endtime)
            sub.update({"panel": pid, "picurl" : defpixurl+"/%d.png" % pid, "ptitle" : ptitle})

            tablines.append(t_tentry.safe_substitute(sub))
            funcs.append(t_func.safe_substitute(sub))

        sub = {"hash" : jobhash, "header": self.measurement_to_text(m),
               "funcs" : "\n".join(funcs), "elements" : "\n".join(tablines)}
        panel = pydash.TextPanel(title=jobid)
        panel.set_mode("html")
        content = t_funcs.safe_substitute(sub)+"\n\n"+t_table.safe_substitute(sub)
        panel.set_content(content)
        return panel

    def del_admin_job(self,deljob):
        jobid = deljob.get_attr("tags.jobid")
        if not jobid:
            logging.error("Given measurent has no jobid")
            return
        logging.info("Remove %s from %s" % (jobid, self.adminconf["dashboard"]))

        try:
            slug = name_to_slug(self.adminconf["dashboard"])
            d = self.gcon.get_dashboard(slug, oid=self.adminconf["oid"])

        except Exception as e:
            logging.error("Cannot download admin dashboard %s" % self.adminconf["dashboard"])
            logging.error(e)
            return
        d = pydash.read_json(d)
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
            logging.error("Cannot find job %s in dashboard" % jobid)
            return
        d.set_overwrite(True)
        d.set_refresh("1m")
        try:
            self.gcon.add_dashboard(d)
        except:
            logging.error("Cannot upload updated dashboard")

        hstr = ""
        for elem in self.adminconf["pix_hash"]:
            hstr += deljob.get_attr(elem)
        h = hashlib.sha224(hstr)
        pixfolder = os.path.join(self.adminconf["pix_path"], str(h.hexdigest()))
        if os.path.exists(pixfolder):
            logging.debug("Delete pic folder %s" % pixfolder)
            os.system("rm -rf %s" % pixfolder)
        if jobid in self.jobstore:
            del self.jobstore[jobid]
    def update_admin_pix(self):
        """
        Update all pictures for all active jobs
        """
        if self.update_t and self.update_t.is_alive():
            self.update_t.join()
        self.update_t = threading.Thread(target=update_all_pix_thread, args=(self.gcon, self.jobstore, self.adminconf, self.panels_for_pix))
        self.update_t.start()
    def start(self, m):
        self.add_admin_job(m)
    def stop(self, m):
        self.del_admin_job(m)
    def update(self):
        self.update_admin_pix()

def update_all_pix_thread(gcon, jobstore, config, panels):
    """
    This function is called by a thread to create all pictures for all currently
    running jobs. It is better to use a thread for this work because rendering
    the pictures takes some time and will block the receive loop.
    """
    endtime = int(time.time()*1E3)
    jobids = jobstore.keys()
    for jobid in jobids:
        if jobid in jobstore:
            logging.debug("Thread: Updating pics for job %s" % jobid)
            m = jobstore[jobid]
            hstr = ""
            for elem in config["pix_hash"]:
                hstr += m.get_attr(elem)
            h = hashlib.sha224(hstr)
            jobhash = hashlib.sha224(jobid).hexdigest()
            pixfolder = os.path.join(config["pix_path"], str(h.hexdigest()))
            starttime = int(m.get_time()/1E6)
            for pid, ptitle in panels:
                pixpath = os.path.join(pixfolder, "%d.png" % pid)
                
                add = {config["pix_jobtag"] : jobid}
                if not os.path.exists(os.path.dirname(os.path.abspath(config["pix_path"]))):
                    logging.debug("Creating picture directory %s" % os.path.dirname(os.path.abspath(config["pix_path"])))
                    os.makedirs(os.path.dirname(config["pix_path"]))
                pic = gcon.get_pic(name_to_slug(config["pix_dashboard"]), pid, starttime, endtime, add=add, theme=config["pix_theme"],height=900)
                if pic:
                    try:
                        f = open(pixpath, "w")
                        f.write(pic)
                        f.close()
                    except:
                        pass
                else:
                    logging.error("Got no picture from grafana from dashboard %s panel %d" % (name_to_slug(config["pix_dashboard"]), panelId))

def main():
    parser = OptionParser()
    parser.add_option("-c", "--config", dest="configfile", help="Configuration file", default=sys.argv[0]+".conf", metavar="FILE")
    parser.add_option("-l", "--log", dest="logfile", help="Log file", default="AdminJobMonitor.log", metavar="FILE")
    (options, args) = parser.parse_args()
    if not os.path.exists(options.configfile):
        print("Cannot read configuration file %s" % options.configfile)
        sys.exit(1)
    FORMAT = '%(asctime)s %(message)s'
    logging.basicConfig(filename=options.logfile, level=logging.DEBUG, format=FORMAT)
    mymon = AdminJobMonitor(configfile=options.configfile)
    mymon.read_config()
    try:
        mymon.recv_loop()
    except KeyboardInterrupt:
        if mymon.update_t:
            mymon.update_t.join(0.5)
        if mymon.pixserver:
            mymon.pixserver.term()

        sys.exit(1)

if __name__ == "__main__":
    main()

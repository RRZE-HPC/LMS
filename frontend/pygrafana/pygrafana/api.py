#!/usr/bin/python

import subprocess
import json
import re
import base64
has_requests = False
try:
    import requests
    import urllib
    has_requests = True
except ImportError:
    pass
import urllib2
import urllib

import dashboard


global_valid_themes = ["light", "dark"]
global_valid_roles = ["Admin", "Viewer", "Editor"]


def is_json(myjson):
  try:
    json_object = json.loads(myjson)
  except ValueError, e:
    return False
  return True

if not has_requests:
    class RequestWithMethod(urllib2.Request):
        """Just a simple urllib2.Request overload class to accept HTTP method at init"""
        def __init__(self, method='GET', *args, **kwargs):
            # This assignment works directly in older Python versions
            self._method = method
            urllib2.Request.__init__(self, *args, **kwargs)
            if self.has_data() and self._method == 'GET':
                self._method = 'PUT'
        def get_method(self):
            return self._method

class Connection(object):
    def __init__(self, hostname, port, username="", password="", apitoken=None, ssl=False, timeout=5):
        self.hostname = hostname
        self.port = port
        self.ssl = ssl
        self.apitoken = apitoken
        self.username = username
        self.password = password
        self.timeout = timeout
        self.grafana_version = None

        assert(self.apitoken or (self.username and self.password)), "Either API token or username/password required"
        if self.ssl:
            self.url = "https://"
        else:
            self.url = "http://"
        self.empty_json = json.loads("{}")
        self.url += "%s:%d/api/" % (self.hostname, self.port,)
        self.headers = {"Content-Type" : "application/json", "Accept" : "application/json"}
        if self.apitoken:
            self.headers.update({"Authorization" : "Bearer %s" % (apitoken,)})
        elif len(self.username) > 0 and len(self.password) > 0:
            base64string = base64.encodestring('%s:%s' % (self.username, self.password)).replace('\n', '')
            self.headers.update({"Authorization" : "Basic %s" % base64string})

        self.connected = self.test_connection()
        if self.is_connected():
            d = self.get_settings()
            self.grafana_version = d["buildInfo"]["version"]
    def __str__(self):
        s = "Grafana API connection:\n"
        s += "\tHostname: %s\n\tPort:%d\n"  % (self.hostname, self.port,)
        if self.username != "" and self.apitoken:
            s += "\tAPI token: %s\n" % self.apitoken
        else:
            s += "\tUsername: %s\n\tPassword:%s\n"  % (self.username, self.password,)
        if self.ssl:
            s += "\tSSL: Yes\n"
        else:
            s += "\tSSL: No\n"
        s += "\tTimeout: %d\n" % self.timeout
        if self.connected:
            s += "\tConnected: Yes"
        else:
            s += "\tConnected: No"
        return s
    def _get_urllib2(self, url):
        out = self.empty_json
        try:
            req = urllib2.Request(url, headers=self.headers)
            resp = urllib2.urlopen(req, timeout=self.timeout)
            if resp.getcode() == 200:
                try:
                    out = json.loads(resp.read())
                except ValueError, e:
                    #print "Response from %s is no JSON document" (resp.geturl(),)
                    #print "Headers: %s" % (str(self.headers),)
                    return resp.getcode(), "Response from %s is no JSON document" % (url,), out
            else:
                #print "Request to URL %s returns error code %d" % (resp.geturl(), resp.getcode(), )
                #print "Headers: %s" % (str(self.headers),)
                return resp.getcode(), "Request to URL %s returns error code %d" % (resp.geturl(), resp.getcode(),), out
        except urllib2.URLError as e:
            #print "URLError for URL %s: %s" % (url,e.reason,)
            #print "Headers: %s" % (str(self.headers),)
            return 400, "GET URLError for url %s : %s" % (url,e.reason,), out
        except Exception as e:
            #print "Exception for URL %s: %s" % (url,e,)
            #print "Headers: %s" % (str(self.headers),)
            return 400, "GET Exception for url %s : %s" % (url,e,), out
        return 200, "OK", out
    def _post_curl(self, url, data):
        cmd = "curl -s -XPOST -m %d '%s' --data-binary '%s'" % (self.timeout, url, data,)
        for h in self.headers:
            cmd += " -H '%s: %s'" % (h, self.headers[h])
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out, err = p.communicate()
        if p.returncode == 0:
            return 200, "OK", out
        else:
            return 400, "POST error", out
    def _post_urllib2(self, url, data=""):
        out = self.empty_json
        if isinstance(data, dict):
            data = json.dumps(data)
        else:
            try:
                data = json.loads(str(data))
            except ValueError:
                print "Input not a valid JSON document"
                return 400, "Input not a valid JSON document", out
        try:
            #print("Create request %s" % url)
            req = urllib2.Request(url, str(data), headers=self.headers)
            #print(req)
            #print("URLopen")
            resp = urllib2.urlopen(req, timeout=self.timeout)
            #print("Return %d" % resp.getcode())
            if resp.getcode() == 200:
                try:
                    f = resp.read()
                    if len(f) > 0:
                        out = json.loads(f)
                    else:
                        print "Empty response from %s" % (url,)
                        return resp.getcode(), "Empty response from %s" % (url,), out
                except ValueError, e:
                    print "Response from %s is no JSON document" (resp.geturl(),)
                    print "Headers: %s" % (str(self.headers),)
                    return resp.getcode(), "Response from %s is no JSON document" % (url,), out
            else:
                print "Request to URL %s returns error code %d" % (resp.geturl(), resp.getcode(), )
                print "Headers: %s" % (str(self.headers),)
                return resp.getcode(), "Request to URL %s returns error code %d" % (resp.geturl(), resp.getcode(),), out
        except urllib2.URLError as e:
            print "POST URLError for url %s : %s" % (url,e.reason,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "POST URLError for url %s : %s" % (url,e.reason,), out
        except Exception as e:
            print "POST Exception for url %s : %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "POST Exception for url %s : %s" % (url,e,), out
        return 200, "OK", out
    def __request_urllib2(self, url, method, data=None):
        out = self.empty_json
        if isinstance(data, str) and is_json(data):
            data = json.loads(data)
            data = json.dumps(data)
        elif isinstance(data, dict):
            data = json.dumps(data)
        elif not data:
            method = 'GET'
        try:
            #opener = urllib2.build_opener(urllib2.HTTPHandler)
            if data and method != 'GET':
                req = RequestWithMethod(method=method, url=url, data=str(data), headers=self.headers)
            else:
                req = urllib2.Request(url, headers=self.headers)
            resp = urllib2.urlopen(req, timeout=self.timeout)
            #resp = opener.open(req)
            if resp.getcode() == 200:
                try:
                    f = resp.read()
                    if len(f) > 0:
                        out = json.loads(f)
                    else:
                        print "Empty response from %s" % (url,)
                        return resp.getcode(), "Empty response from %s" % (url,), out
                except ValueError, e:
                    print "Response from %s is no JSON document" (resp.geturl(),)
                    print "Headers: %s" % (str(self.headers),)
                    print "Data : %s" % (str(data),)
                    return resp.getcode(), "Response from %s is no JSON document" % (url,), out
            else:
                print "Request to URL %s returns error code %d" % (resp.geturl(), resp.getcode(), )
                print "Headers: %s" % (str(self.headers),)
                print "Data : %s" % (str(data),)
                return resp.getcode(), "Request to URL %s returns error code %d" % (resp.geturl(), resp.getcode(),), out
        except urllib2.URLError as e:
            print "%s URLError for url %s: %s" % (method, url,e.reason,)
            print "Headers: %s" % (str(self.headers),)
            print "Data : %s" % (str(data),)
            return 404, "URLError for url %s: %s" % (url,e.reason,), out
        except Exception as e:
            #print "Exception for url %s: %s" % (url,e.reason,)
            #print "Headers: %s" % (str(self.headers),)
            return 400, "Exception for url %s: %s" % (url,e,), out
        return 200, "OK", out
    def _get_requests(self, url):
        out = self.empty_json
        try:
            r = requests.get(url, headers=self.headers,
                             auth=(self.username, self.password),
                             timeout=self.timeout, stream=True)
            s = ""
            for chunk in r.iter_content(1024):
                if chunk:
                    s += chunk
            out = json.loads(s)
        except requests.Timeout as e:
            print "Timeout for URL %s: %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "Timeout for url %s: %s" % (url,e,), out
        except requests.ConnectionError as e:
            print "ConnectionError for URL %s: %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "ConnectionError for url %s: %s" % (url,e,), out
        except requests.HTTPError as e:
            print "HTTPError for URL %s: %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "HTTPError for url %s: %s" % (url,e,), out
        except requests.RequestException as e:
            print "RequestException for URL %s: %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "RequestException for url %s: %s" % (url,e,), out
        
        return r.status_code, "OK", out
    def _post_requests(self, url, data=""):
        out = self.empty_json
        if isinstance(data, dict):
            data = json.dumps(data)
        elif data:
            try:
                data = json.loads(data)
            except ValueError:
                print "Input not a valid JSON document"
                return 400, "Input not a valid JSON document", out
        try:
            r = requests.post(url, data=data, headers=self.headers,
                             auth=(self.username, self.password),
                             timeout=self.timeout)
        except requests.Timeout as e:
            print "Timeout for URL %s: %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "Timeout for url %s: %s" % (url,e,), out
        except requests.ConnectionError as e:
            print "ConnectionError for URL %s: %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "ConnectionError for url %s: %s" % (url,e,), out
        except requests.HTTPError as e:
            print "HTTPError for URL %s: %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "HTTPError for url %s: %s" % (url,e,), out
        except requests.RequestException as e:
            print "RequestException for URL %s: %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "RequestException for url %s: %s" % (url,e,), out
        return r.status_code, "OK", r.json()
    def __request_requests(self, url, method, data=None):
        out = self.empty_json
        if isinstance(data, dict):
            data = json.dumps(data)
        elif data:
            try:
                data = json.loads(data)
            except ValueError:
                print "Input not a valid JSON document"
                return 400, "Input not a valid JSON document", out
        try:
            if method == 'GET':
                return _get_requests(url, headers=self.headers,
                                     auth=(self.username, self.password),
                                     timeout=self.timeout)
            elif method == 'PUSH':
                return _post_requests(url, data=data, headers=self.headers,
                                      auth=(self.username, self.password),
                                      timeout=self.timeout)
            elif method == 'DELETE':
                r = requests.delete(url, headers=self.headers,
                                    auth=(self.username, self.password),
                                    timeout=self.timeout)
            elif method == 'PUT':
                r = requests.put(url, data=data, headers=self.headers,
                                 auth=(self.username, self.password),
                                 timeout=self.timeout)
            elif method == 'PATCH':
                r = requests.patch(url, data=data, headers=self.headers,
                                   auth=(self.username, self.password),
                                   timeout=self.timeout)
        except requests.Timeout as e:
            print "Timeout for URL %s: %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "Timeout for url %s: %s" % (url,e,), out
        except requests.ProxyError as e:
            print "ProxyError for URL %s: %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "ProxyError for url %s: %s" % (url,e,), out
        except requests.SSLError as e:
            print "SSLError for URL %s: %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "SSLError for url %s: %s" % (url,e,), out
        except requests.ConnectionError as e:
            print "ConnectionError for URL %s: %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "ConnectionError for url %s: %s" % (url,e,), out
        except requests.HTTPError as e:
            print "HTTPError for URL %s: %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "HTTPError for url %s: %s" % (url,e,), out
        except requests.RequestException as e:
            print "RequestException for URL %s: %s" % (url,e,)
            print "Headers: %s" % (str(self.headers),)
            return 400, "RequestException for url %s: %s" % (url,e,), out
        return r.status_code, "OK", r.json()
    def _get(self, url):
        if has_requests:
            return self._get_requests(url)
        else:
            return self._get_urllib2(url)
    def _post(self, url, data=""):
        if has_requests:
            return self._post_requests(url, data)
        else:
            return self._post_urllib2(url, data)
    def _put(self, url, data=""):
        if has_requests:
            return self.__request_requests(url, 'PUT', data)
        else:
            return self.__request_urllib2(url, 'PUT', data)
    def _del(self, url, data=""):
        if has_requests:
            return self.__request_requests(url, 'DELETE', data)
        else:
            return self.__request_urllib2(url, 'DELETE', data)
    def _patch(self, url, data=""):
        if has_requests:
            return self.__request_requests(url, 'PATCH', data)
        else:
            return self.__request_urllib2(url, 'PATCH', data)
    def test_connection(self):
        err, estr, data = self._get(self.url+"org")
        #print(err, estr, data)
        if err == 200 and len(data.keys()) > 0:
            return True
        return False
    def is_connected(self):
        return self.connected
    def get_grafana_version(self):
        return self.grafana_version
    def get_ds(self, org=None):
        if not self.connected:
            return self.empty_json
        if org:
            self.change_active_org(org)
        err, estr, data = self._get(self.url+"datasources")
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def get_ds_by_name(self, dsname, org=None):
        if not self.connected:
            return self.empty_json
        out = self.empty_json
        err, estr, data = self._get(self.url+"datasources/name/%s" % (str(dsname),))
        if err == 200:
            out = data
        else:
            print estr
        dss = self.get_ds(org=org)
        for ds in dss:
            if ds.has_key("name") and ds["name"] == dsname:
                out = ds
        return out
    def get_ds_by_id(self, dsid, org=None):
        if not self.connected:
            return self.empty_json
        if org:
            self.change_active_org(org)
        err, estr, data = self._get(self.url+"datasources/%s" % (str(dsid),))
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def add_ds(self, name, typ, url, database, orgId=None, access="proxy", user="", password="", basicAuth=False, basicAuthUser="", basicAuthPassword="", isDefault=False, jsonData=None):
        if not self.connected:
            return self.empty_json
        d = {"name" : name,
             "type" : typ,
             "url" : url,
             "access" : access,
             "database" : database,
             "user" : user,
             "password" : password,
             "isDefault" : isDefault,
             "jsonData" : jsonData}
        if orgId:
            d.update({"orgId" : orgId})
        if basicAuth:
            d.update({"basicAuth" : basicAuth,
                      "basicAuthUser" : basicAuthUser,
                      "basicAuthPassword" : basicAuthPassword})
        err, estr, data = self._post(self.url+"datasources", d)
        if err == 200:
            if data.has_key("id"):
                return data["id"]
            else:
                return self.get_ds_by_name(name)
        print estr
        return -1
    def upd_ds(self, dsid, name=None, typ=None, access=None, url=None, username=None, password=None, database=None, basicAuth=None, basicAuthUser=None, basicAuthPassword=None, isDefault=None, oid=None):
        d = {"id" : dsid}
        if name and isinstance(name, str):
            d.update({"name" : name})
        if typ and isinstance(typ, str):
            all_types = self.get_ds_types()
            avail = False
            if len(all_types) > 0:
                for k in all_types.keys():
                    if k.has_key("type") and k["type"] == typ:
                        avail = True
                        break
            elif grafana_version.startswith("3"):
                avail= True
            if avail:
                d.update({"type" : typ})
            else:
                print "Unknown datasource type %s" % (typ,)
        if access and isinstance(access, str):
            d.update({"access" : access})
        if url and isinstance(url, str):
            d.update({"url" : url})
        if username and isinstance(username, str):
            d.update({"username" : username})
        if password and isinstance(password, str):
            d.update({"password" : password})
        if database and isinstance(database, str):
            d.update({"database" : database})
        if oid and isinstance(oid, int):
            d.update({"orgId" : oid})
        if basicAuth and isinstance(basicAuth, bool):
            d.update({"basicAuth" : basicAuth})
        if isDefault and isinstance(isDefault, bool):
            d.update({"isDefault" : isDefault})
        if basicAuthUser and isinstance(basicAuthUser, str):
            d.update({"basicAuthUser" : basicAuthUser})
        if basicAuthPassword and isinstance(basicAuthPassword, str):
            d.update({"basicAuthPassword" : basicAuthPassword})
        err, estr, data = self._put(self.url+"datasources/%s" % (str(dsid),))
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def del_ds(self, dsid):
        if not self.connected:
            return self.empty_json
        err, estr, data = self._del(self.url+"datasources/%s" % (str(dsid),))
        if err == 200:
            return True
        print estr
        return False
    def get_ds_types(self):
        if not self.connected:
            return self.empty_json
        err, estr, data = self._get(self.url+"datasources/plugins")
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def get_orgs(self):
        if not self.connected:
            return self.empty_json
        err, estr, data = self._get(self.url+"orgs")
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def get_current_org(self):
        if not self.connected:
            return self.empty_json
        err, estr, data = self._get(self.url+"org")
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def upd_current_org(self, name):
        if not self.connected:
            return self.empty_json
        d = {"name" : name}
        err, estr, data = self._put(self.url+"org", d)
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def get_users_of_current_org(self):
        if not self.connected:
            return self.empty_json
        err, estr, data = self._get(self.url+"org/users")
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def change_active_org(self, oid):
        if not self.connected:
            return False
        err, estr, data = self._post(self.url+"user/using/%s" % (str(oid),), {})
        if err == 200:
            return True
        elif data.has_key("message"):
            print "ERROR",data["message"]
        return False
    def add_dashboard(self, d, org=None):
        if not self.connected:
            return self.empty_json
        if org:
            self.change_active_org(org)
        out = json.loads("{}")
        if isinstance(d, str):
            try:
                out = json.loads(str(d))
            except ValueError as e:
                return 400, "Input not a valid JSON document"
        elif isinstance(d, dict):
            try:
                s = json.dumps(d)
                d = json.loads(s)
            except:
                return 400, "Input not a valid JSON document"
        else:
            try:
                out = d.get_json()
            except:
                return 400, "Input not a valid pygrafana Dashboard object"
        err, estr, data = self._post(self.url+"dashboards/db", json.dumps(out))
        if err == 200:
            return data
        elif isinstance(data, list) and data[0].has_key("message"):
            print self.url+"dashboards/db"
            print "ERROR",data[0]["message"]
        elif isinstance(data, dict) and data.has_key("message"):
            print self.url+"dashboards/db"
            print "ERROR",data["message"]
        return self.empty_json
    def get_dashboard(self, slug, oid=None):
        if not self.connected:
            return self.empty_json
        if oid:
            self.change_active_org(oid)
        err, estr, data = self._get(self.url+"dashboards/db/%s" % (slug,))
        if err == 200:
            return data
        elif data.has_key("message"):
            print "ERROR",data["message"]
        return self.empty_json
    def del_dashboard(self, slug, oid=None):
        if not self.connected:
            return self.empty_json
        if oid:
            self.change_active_org(oid)
        err, estr, data = self._del(self.url+"dashboards/db/%s" % (slug,))
        if err == 200:
            return data
        elif data.has_key("message"):
            print "ERROR",data["message"]
        return self.empty_json
    def get_home_dashboard(self, oid=None):
        if not self.connected:
            return self.empty_json
        if oid:
            self.change_active_org(oid)
        err, estr, data = self._get(self.url+"dashboards/home")
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def get_dashboard_tags(self, oid=None):
        if not self.connected:
            return self.empty_json
        if oid:
            self.change_active_org(oid)
        err, estr, data = self._get(self.url+"dashboards/tags")
        if err == 200:
            return data
        elif data.has_key("message"):
            print "ERROR",data["message"]
        return self.empty_json
    def search_dashboard(self, query=None, tags=[], starred=None, tagcloud=None, oid=None):
        if not self.connected:
            return self.empty_json
        if oid:
            self.change_active_org(oid)
        d = {}
        if query:
            d["query"] = query
        if len(tags) > 0:
            for (k,v) in tags:
                d[k] = v
        if starred and isinstance(starred, bool):
            d["starred"] = starred
        if tagcloud and isinstance(tagcloud, bool):
            d["tagcloud"] = tagcloud
        if len(d.keys()) == 0:
            print "No inputs for search"
            return self.empty_json
        url = self.url+"search/?"+urllib.urlencode(d)
        print url
        err, estr, data = self._get(url)
        if err == 200:
            return data
        elif data.has_key("message"):
            print "ERROR",data["message"]
        return self.empty_json
    def deepsearch_dashboard(self, query=None, tags=[], starred=None, tagcloud=None):
        if not self.connected:
            return self.empty_json
        orgs = self.get_orgs()
        res = []
        for o in orgs:
            if o.has_key("id"):
                print "search for oid %d" % (o["id"],)
                d = self.search_dashboard(query, tags, starred, tagcloud, oid=o["id"])
                for e in d:
                    res.append(e)
        return res
    def star_dashboard_by_id(self, did, oid=None):
        if not self.connected:
            return self.empty_json
        if oid:
            self.change_active_org(oid)
        err, estr, data = self._post(self.url+"user/stars/dashboard/%s" % (str(did),),)
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def unstar_dashboard_by_id(self, did, oid=None):
        if not self.connected:
            return self.empty_json
        if oid:
            self.change_active_org(oid)
        err, estr, data = self._del(self.url+"user/stars/dashboard/%s" % (str(did),))
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def star_dashboard_by_name(self, query, oid=None):
        if not self.connected:
            return self.empty_json
        res = self.search_dashboard(query, oid=oid)
        if len(res) == 1:
            return self.star_dashboard_by_id(res[0]["id"], oid=oid)
        else:
            return self.empty_json
    def unstar_dashboard_by_name(self, query, oid=None):
        if not self.connected:
            return self.empty_json
        res = self.search_dashboard(query, oid=oid)
        if len(res) == 1:
            return self.unstar_dashboard_by_id(res[0]["id"], oid=oid)
        else:
            return self.empty_json
    def get_current_user(self):
        if not self.connected:
            return self.empty_json
        err, estr, data = self._get(self.url+"user")
        if (err == 200):
            if not data.has_key("id"):
                users = self.get_users()
                for u in users:
                    if u["login"] == data["login"]:
                        data.update({u"id" : u["id"]})
                        break
            return data
        elif data.has_key("message"):
            print "ERROR",data["message"]
        return self.empty_json
    def get_users(self):
        if not self.connected:
            return self.empty_json
        err, estr, data = self._get(self.url+"users")
        if (err == 200):
            return data
        elif data.has_key("message"):
            print "ERROR",data["message"]
        return self.empty_json

    def upd_user(self, uid, login=None, email=None, name=None, theme=None):
        if not self.connected:
            return self.empty_json
        if not (login or email):
            print "ERROR: login or email required"
            return self.empty_json
        d = {}
        if login and isinstance(login, str):
            d.update({"login" : login})
        if email and isinstance(email, str):
            d.update({"email" : email})
        if name and isinstance(name, str):
            d.update({"name" : name})
        if theme and isinstance(theme, str):
            d.update({"theme" : theme})
        if len(d.keys()) == 0:
            return self.empty_json
        err, estr, data = self._put(self.url+"users/%s" % (str(uid),), d)
        if err == 200:
            return data
        elif data.has_key("message"):
            print "ERROR",data["message"]
        return self.empty_json
    def admin_add_user(self, login=None, email=None, password=None, name=None, theme="dark"):
        if not self.connected:
            return False
        if not (login or email):
            print("Login or email required")
            return False
        if not password:
            print("Password required")
            return False
        d = {}
        if login and isinstance(login, str):
            d.update({"login" : login})
        if email and isinstance(email, str):
            d.update({"email" : email})
        if password and isinstance(password, str):
            d.update({"password" : password})
        if name and isinstance(name, str):
            d.update({"name" : name})
        if theme and isinstance(theme, str) and theme in global_valid_themes:
            d.update({"theme" : theme})
        if len(d.keys()) == 0:
            return self.empty_json
        err, estr, data = self._post(self.url+"admin/users", d)
        if err == 200:
            return True
        elif data.has_key("message"):
            print "ERROR",data["message"]
        return False
    def admin_upd_pass_for_uid(self, uid, password):
        d = {}
        if login and isinstance(login, str):
            d.update({"password" : password})
        err, estr, data = self._post(self.url+"admin/users/%s/password" % (str(uid),), d)
        if (err == 200):
            return data
        elif data.has_key("message"):
            print "ERROR",data["message"]
        return self.empty_json
    def admin_del_uid(self, uid):
        err, estr, data = self._del(self.url+"admin/users/%s" % (str(uid),))
        if (err == 200):
            return data
        elif data.has_key("message"):
            print "ERROR",data["message"]
        return self.empty_json
    def get_current_uid(self):
        data = self.get_users()
        if len(data) == 0:
            return self.empty_json
        udata = self.get_current_user()
        if len(udata.keys()) == 0:
            return self.empty_json
        if isinstance(data, list):
            for d in data:
                if d.has_key("id") and d.has_key("login") and d["login"] == udata["login"]:
                    return d["id"]
        return -1
    def get_uid(self, user):
        data = self.get_users()
        if isinstance(data, list) and len(data) > 0:
            for d in data:
                if d["login"] == user:
                    return d["id"]
        return -1
    def upd_current_user_pass(self, uid, old_pw, new_pw):
        d = {"oldPassword": old_pw,
             "newPassword": new_pw,
             "confirmNew": new_pw}
        err, estr, data = self._put(self.url+"user/password", d)
        if err == 200:
            return data
        elif data.has_key("message"):
            print "ERROR",data["message"]
        return self.empty_json
    def get_user_by_uid(self, uid):
        err, estr, data = self._get(self.url+"users/%s" % (str(uid),))
        if err == 200:
            return data
        elif data.has_key("message"):
            print "ERROR",data["message"]
        return self.empty_json
    def get_orgs_by_uid(self, uid):
        err, estr, data = self._get(self.url+"users/%s/orgs" % (str(uid),))
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def get_orgs_by_current_uid(self):
        err, estr, data = self._get(self.url+"user/orgs")
        if err == 200:
            return data
        elif data.has_key("message"):
            print "ERROR",data["message"]
        return self.empty_json
    def get_orgs_by_user(self, user):
        uid = self.get_uid(user)
        if uid > 0:
            err, estr, data = self._get(self.url+"users/%s/orgs" % (str(uid),))
            if err == 200:
                return data
            else:
                print estr
        return self.empty_json
    def get_orgid_by_name(self, orgname):
        orgs = self.get_orgs()
        for o in orgs:
            if o["name"] == orgname:
                return o["id"]
        return -1
    def add_org(self, org):
        d = {
            "name" : str(org)
        }
        err, estr, data = self._post(self.url+"orgs", d)
        if err == 200:
            if data.has_key("id"):
                return data["id"]
            else:
                return self.get_orgid_by_name(org)
        else:
            print estr
        return -1
    def del_org_by_id(self, oid):
        """
        Not working
        """
        err, estr, data = self._del(self.url+"orgs/%s" % str(oid))
        if err == 200:
            return True
        print err, estr, data
        return False
    def del_org_by_name(self, orgname):
        """
        Not working
        """
        oid = self.get_orgid_by_name(orgname)
        print "OID", oid
        if oid > 0:
            return self.del_org_by_id(oid)
        return False
    def upd_user_by_uid(self, uid, login=None, name=None, email=None, theme=None):
        if not (email or name or theme):
            return self.empty_json
        d = {}
        if login:
            d.update({"login" : login})
        if name:
            d.update({"name" : name})
        if email:
            d.update({"email" : email})
        if theme:
            d.update({"theme" : theme})
        if len(d.keys()) == 0:
            return self.empty_json
        err, estr, data = self._put(self.url+"users/%s" % (str(uid),), d)
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def del_uid_from_orgid(self, uid, oid):
        err, estr, data = self._del(self.url+"orgs/%s/users/%s", (str(oid), str(uid),))
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def del_uid_from_current_orgid(self, uid):
        err, estr, data = self._del(self.url+"org/users/%s", (str(uid),))
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def del_user_from_orgid(self, user, oid):
        uid = self.get_uid()
        if uid > 0:
            return del_uid_from_orgid(uid, oid)
        else:
            print "User %s unknown" % (user,)
        return self.empty_json
    def del_user_from_current_orgid(self, user):
        uid = self.get_uid()
        if uid > 0:
            return del_uid_from_current_orgid(uid)
        else:
            print "User %s unknown" % (user,)
        return self.empty_json
    def upd_uid_in_orgid(self, uid, oid, role):
        assert(role in global_valid_roles), "Invalid role"
        d = {"role" : role}
        err, estr, data = self._patch(self.url+"orgs/%s/users/%s" % (str(oid), str(uid),), d)
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def add_uid_to_orgid(self, uid, oid, login=None, email=None, role=None):
        assert(login or email), "Either login or email are required"
        assert(role == None or role in global_valid_roles), "Invalid role"
        d = {}
        if role:
            d.update({"role" : role})
        if login:
            d.update({"loginOrEmail" : login})
        elif email:
            d.update({"loginOrEmail" : email})
        err, estr, data = self._post(self.url+"orgs/%s/users" % (str(oid),), d)
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def add_uid_to_current_org(self, login=None, email=None, role=None):
        assert(login or email), "Either login or email are required"
        d = {}
        if role:
            d.update({"role" : role})
        if login:
            d.update({"loginOrEmail" : login})
        elif email:
            d.update({"loginOrEmail" : email})
        err, estr, data = self._post(self.url+"org/users", d)
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def upd_uid_in_current_org(self, uid, login=None, email=None, role=None):
        assert(login or email), "Either login or email are required"
        d = {}
        if role:
            d.update({"role" : role})
        if login:
            d.update({"loginOrEmail" : login})
        elif email:
            d.update({"loginOrEmail" : email})
        err, estr, data = self._patch(self.url+"org/users/%s" % (str(uid),), d)
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def del_uid_from_current_org(self, uid):
        err, estr, data = self._del(self.url+"org/users/%s" % (str(uid),), d)
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def get_users_in_oid(self, oid):
        err, estr, data = self._get(self.url+"orgs/%s/users" % (str(oid),))
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def upd_organization(self, oid, name):
        d = {"name" : name}
        err, estr, data = self._put(self.url+"orgs/%s" % (str(oid),), d)
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def admin_get_settings(self):
        err, estr, data = self._get(self.url+"admin/settings")
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def get_settings(self):
        err, estr, data = self._get(self.url+"frontend/settings")
        if err == 200:
            return data
        else:
            print estr
        return self.empty_json
    def get_pic(self, slug, panelId, stime, etime, width=1000, height=400, add={}, theme=None):
        url = self.url.replace("api", "render/dashboard-solo/db")
        url += slug
        if len(add) > 0:
            akeys = add.keys()
            url += "?var-%s=%s" % (akeys[0], add[akeys[0]],)
            for a in akeys[1:]:
                url += "&var-%s=%s" % (a, add[a],)
            url += "&from=%s&to=%s&panelId=%d&width=%d&height=%d" % (str(stime), str(etime), panelId, width, height)
        else:
            url += "?from=%s&to=%s&panelId=%d&width=%d&height=%d" % (str(stime), str(etime), panelId, width, height)
        if theme and theme in ("light", "dark"):
            url += "&theme=%s" % theme
        heads = self.headers
        heads.update({"Accept" : "image/png"})
        if not has_requests:
            try:
                req = urllib2.Request(url, headers=heads)
                resp = urllib2.urlopen(req)
            except Exception as e:
                print(e)
                return None
            if resp:
                return resp.read()
        else:
            r = requests.get(url, headers=heads,
                             auth=(self.username, self.password),
                             timeout=self.timeout*2, stream=True)
            s = ""
            for chunk in r.iter_content(1024):
                if chunk:
                    s += chunk
            return s
        return None


if __name__ == "__main__":
    import doctest
    doctest.testmod()
    c = Connection("fepa.rrze.uni-erlangen.de", 3000, username="admin", password="admin")
#    print c.test_connection()
#    print c.get_orgs()
#    print c.get_ds()
#    c.change_active_org(1)
#    print c.get_dashboard("222701_tbadm1_rrze_uni-erlangen_de")
#    print c.get_ds(org=1)
#    print c.get_current_user()
#    print c.get_users()
#    print c.get_current_uid()
#    print c.get_orgs_by_uid(1)
#    print c.get_uid("unrz139")
#    print c.get_orgs_by_user("unrz139")
#    print c.get_user_by_uid(52)
#    print c.get_users_in_oid(1)
#    print c.search_dashboard("tbadm",oid=71)
#    print c.get_ds_types()
#    print c.get_current_org()

    if c.test_connection():
        print c.get_ds()
        valid_ds = c.get_ds()
        print c.get_ds_by_id(valid_ds[0]["id"])
    #    print c.add_ds()
    #    print c.upd_ds()
    #    print c.del_ds()
        print c.get_ds_types()
        print c.get_orgs()
        print c.get_current_org()
    #    print c.upd_current_org()
        print c.get_users_of_current_org()
        print c.change_active_org(1)
    #    print c.add_dashboard()
        print c.get_dashboard("222701_tbadm1_rrze_uni-erlangen_de", oid=71)
    #    print c.del_dashboard()
        print c.get_home_dashboard()
        print c.get_dashboard_tags()
        print c.search_dashboard("tbadm",oid=71)
        print c.deepsearch_dashboard("tbadm")
        print c.star_dashboard("222701_tbadm1_rrze_uni-erlangen_de", oid=71)
        print c.unstar_dashboard("222701_tbadm1_rrze_uni-erlangen_de", oid=71)
        print c.get_current_user()
        print c.get_users()
        print c.get_uid("unrz139")
        uid = c.get_uid("unrz139")
        print c.get_user_by_uid(uid)
    #    print c.upd_user()
        print c.get_current_uid()

    #    print c.upd_current_user_pass()
        print c.get_orgs_by_uid(uid)
        print c.get_orgs_by_current_uid()
        print c.get_orgs_by_user("unrz139")
        print c.upd_user_by_uid(52, login="unrz139", name="unrz139", email="test@test.org")
    #    print c.del_uid_from_orgid()
    #    print c.del_uid_from_current_orgid()
    #    print c.del_user_from_orgid()
    #    print c.del_user_from_current_orgid()
    #    print c.upd_uid_in_orgid()
    #    print c.add_uid_to_orgid()
    #    print c.add_uid_to_current_org()
    #    print c.upd_uid_in_current_org()
    #    print c.del_uid_from_current_org()
        print c.get_users_in_oid(1)
    #    print c.upd_organization()

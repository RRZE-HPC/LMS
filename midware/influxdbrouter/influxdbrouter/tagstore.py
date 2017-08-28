#!/usr/bin/env python

import re, logging, copy
from threading import Lock


class Tagger(object):
    def __init__(self, hosts_attr="fields.hosts", hosts_sep=":", tag_file="tags_jobs.safe"):
        self.tags_by_host = {}
        self.hosts_sep = str(hosts_sep)
        self.hosts_attr = str(hosts_attr)
        self.tag_file = tag_file
        self.lock = Lock()

    def add(self, measurement):
        hosts = measurement.get_attr(self.hosts_attr)
        if not hosts:
            logging.error("Measurement does not have the attribute with host list %s" % self.hosts_attr)
            return False
        hostlist = re.split(self.hosts_sep, hosts.strip("'").strip("\""))
        tags = measurement.get_all_tags()
        if self.hosts_attr in tags:
            del tags[self.hosts_attr]
        
        self.lock.acquire()
        for h in hostlist:
            if h in self.tags_by_host:
                logging.info("Host %s already registered for key %s. Overwrite exiting mapping" % (h, self.tags_by_host[h],))
	    logging.info("Add Host %s with tags %s" % (h, str(tags),))
            self.tags_by_host[h] = tags
        self.lock.release()
        return True
        

    def delete(self, measurement):
        hosts = measurement.get_attr(self.hosts_attr)
        if not hosts:
            logging.error("Measurement does not have the attribute with host list %s" % self.hosts_attr)
            return False
        hostlist = re.split(self.hosts_sep, hosts.strip("'").strip("\""))

        self.lock.acquire()
        for h in hostlist:
            if h in self.tags_by_host:
		logging.info("Delete Host %s with tags %s" % (h, str(self.tags_by_host[h]),))
                del self.tags_by_host[h]
        self.lock.release()
        return True
    def get_tags_by_host(self, host):
        if host not in self.tags_by_host:
            return {}
        return copy.deepcopy(self.tags_by_host[host])
    def get_all_tags(self):
        return self.tags_by_host
    def get_all_active_hosts(self):
        return sorted(self.tags_by_host.keys())
    def host_active(self, host):
        return host in self.tags_by_host
    def store(self):
        f = open(self.tag_file, "w")
        f.write(json.dumps(self.tags_by_host, sort_keys=True, indent=4, separators=(',', ': ')))
        f.close()
    def restore(self):
        f = open(self.tag_file, "r")
        self.lock.acquire()
        self.tags_by_host = json.loads(f.read())
        self.lock.release()
        f.close()
            
                
        
        
            
        
        
    

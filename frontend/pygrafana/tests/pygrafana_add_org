#!/usr/bin/env python

import sys
import pygrafana.api as gapi

orgname = "testorg2"

con = gapi.Connection("localhost", 3000, "admin", "admin")
if not con.is_connected:
    print "Cannot establish connection"
    sys.exit(1)
print con
oid = con.get_orgid_by_name(orgname)
if oid < 0:
    oid = con.add_org(orgname)
    print "Organization created with ID %d" % oid
else:
    print "Organization exists with ID %d" % oid

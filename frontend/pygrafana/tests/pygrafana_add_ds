#!/usr/bin/env python

import sys
import pygrafana.api as gapi

orgname = "testorg"
dsname = "testds2"
dstype = "influxdb"
dsurl = "http://localhost:8086"
dsdb = "testdb"


con = gapi.Connection("localhost", 3000, "admin", "admin")
if not con.is_connected:
    print "Cannot establish connection"
    sys.exit(1)
print con

oid = con.get_orgid_by_name(orgname)
if oid < 0:
    print "Organization does not exists, searching in current org"
    oid = None
else:
    print "Searching in Organization %s (ID %d)" % (orgname, oid, )

print con.get_ds_types().keys()

if len(con.get_ds_by_name(dsname, org=oid)) == 0:
    dsid = con.add_ds(dsname, typ=dstype, url=dsurl, database=dsdb, isDefault=True, orgId=oid)
    print "Datasource with ID %d created" % dsid
else:
    dsid = con.get_ds_by_name(dsname, org=oid)["id"]
    print "Datasource exists with ID %d" % dsid

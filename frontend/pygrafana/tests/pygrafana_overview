#!/usr/bin/env python

import sys

import pygrafana.api as gapi
import pygrafana.dashboard as gdash


hostname = "localhost"
port = 3000
username = "admin"
password = "admin"

def print_head(head):
    print "*"*80
    print head
    print "*"*80

c = gapi.Connection(hostname, port, username, password)

if not c.is_connected():
    print "Not connected"
    sys.exit()

uid = 1
usern = "admin"
oid = 1

print_head("Current User:")
d = c.get_current_user()
for k in d.keys():
    strk = k.capitalize()
    print "\t",strk,":", d[k]
usern = d["login"]
d = c.get_current_uid()
uid = d
print "\t","UID by get_current_uid:", str(d)
print "\t","UID by get_uid(\"%s\"):" % usern, c.get_uid(usern)


print_head("User by get_user_by_uid(%d)" % uid)
d = c.get_user_by_uid(uid)
for k in d.keys():
    strk = k.capitalize()
    print "\t",strk,":", d[k]

print_head("Current Organization:")
d = c.get_current_org()
for k in d.keys():
    strk = k.capitalize()
    print "\t",strk,":", d[k]
if d.has_key("id"):
    oid = d["id"]
print "\tUsers:"
d = c.get_users_of_current_org()
for u in d:
    for k in u.keys():
        strk = k.capitalize()
        print "\t\t",strk,":", u[k]
    print

print_head("All Organizations of User %s" % usern)
d = c.get_orgs_by_user(usern)
for u in d:
    for k in u.keys():
        strk = k.capitalize()
        print "\t",strk,":", u[k]
    print

print_head("All Organizations of UID %d" % uid)
d = c.get_orgs_by_uid(uid)
for u in d:
    for k in u.keys():
        strk = k.capitalize()
        print "\t",strk,":", u[k]
    print

print_head("All Users:")
d = c.get_users()
for u in d:
    for k in u.keys():
        strk = k.capitalize()
        print "\t",strk,":", u[k]
    print

print_head("All Organizations:")
d = c.get_orgs()
for u in d:
    for k in u.keys():
        strk = k.capitalize()
        print "\t",strk,":", u[k]
    if u.has_key("id"):
        print "\tUsers:"
        for user in c.get_users_in_oid(u["id"]):
            for i in user.keys():
                stri = i.capitalize()
                print "\t\t",stri,":", user[i]
    print

print_head("Datasource types:")
d = c.get_ds_types()
for u in d.keys():
    print "\t",u
    for ds in d[u].keys():
        if isinstance(d[u][ds], dict):
            for i in d[u][ds].keys():
                stri = i.capitalize()
                print "\t\t\t",stri,":", d[u][ds][i]
        else:
            strds = ds.capitalize()
            print "\t\t",strds,":", str(d[u][ds])
    print

dsname = ""
dsid = 1
print_head("Datasource of OID %d:" % oid)
d = c.get_ds(org=oid)
for u in d:
    for k in u.keys():
        strk = k.capitalize()
        print "\t",strk,":", u[k]
    print
    if u.has_key("name"):
        dsname = u["name"]
    if u.has_key("id"):
        dsid = u["id"]

print_head("Datasource with ID %d in OID %d:" % (dsid, oid,))
u = c.get_ds_by_id(dsid, org=oid)
for k in u.keys():
    strk = k.capitalize()
    print "\t",strk,":", u[k]
print

print_head("Datasource with name %s in OID %d:" % (dsname, oid,))
u = c.get_ds_by_name(dsname, org=oid)
for k in u.keys():
    strk = k.capitalize()
    print "\t",strk,":", u[k]
print

print_head("Settings")
d = c.get_settings()
for u in d.keys():
    print "\t",u.capitalize()
    if isinstance(d[u], dict):
        for k in d[u].keys():
            if isinstance(d[u][k], dict):
                for l in d[u][k].keys():
                    strl = l.capitalize()
                    print "\t\t",strl,":", d[u][k][l]
            else:
                strk = k.capitalize()
                print "\t\t",strk,":", d[u][k]
    else:
        stru = u.capitalize()
        print "\t\t",stru,":", str(u)

print_head("Admin Settings")
d = c.admin_get_settings()
for u in d.keys():
    print "\t",u.capitalize()
    if isinstance(d[u], dict):
        for k in d[u].keys():
            strk = k.capitalize()
            print "\t\t",strk,":", d[u][k]
    else:
        stru = u.capitalize()
        print "\t\t",stru,":", str(u)

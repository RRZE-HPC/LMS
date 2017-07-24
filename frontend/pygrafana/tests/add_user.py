#!/usr/bin/env python

import sys
import pygrafana.api as gapi


username = "testuser"
password = "testpass"

con = gapi.Connection("localhost", 3000, "admin", "admin")
if not con.is_connected:
    print "Cannot establish connection"
    sys.exit(1)
print con
uid = con.get_uid(username)
if uid < 0:
    if con.admin_add_user(login=username, password=password):
        uid = con.get_uid(username)
        print "User %s created with ID %d" % (username, uid,)
    else:
        print "Cannot create user"
print "User already exists with ID %d" % uid

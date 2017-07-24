#!/usr/bin/env python


from pygrafana.dashboard import Target, GraphPanel, Row, Dashboard, set_grafana_version, TextPanel
from pygrafana.api import Connection

# Establish connection to Grafana
con = Connection("localhost", 3000, "testuser", "testpw")

# Read Grafana version from Connection and set it for dashboard creation
ver = con.get_grafana_version()
set_grafana_version(ver)


# Create a database query target
t = Target("testmetric", alias="Testmetric [[tag_host]]")
# Add a Tag to the query target
t.add_groupBy("tag", "testtag")
# Create a graph panel displaying the single Target
g = GraphPanel(title="Testmetric", targets=[t])
# Create a row for the graph panel
r = Row("Testmetric Row")
# Add the graph panel to the row
r.add_panel(g)
text = TextPanel(title="Testtext", mode="html", content="<center>foobar</center>")
r2 = Row("Testtext Row")
r2.add_panel(text)
# Create a dashboard
d = Dashboard("Test Dashboard")
# Add row
d.add_row(r)
d.add_row(r2)
# sets datasource of all targets and templates in dashboard
d.set_datasource("myDS")

# Get JSON of dashboard
res = d.get_json()
# Get dict of dashboard
res = d.get()

# Add dashboards tags JSON documents or Dashboard objects
print con.add_dashboard(d)

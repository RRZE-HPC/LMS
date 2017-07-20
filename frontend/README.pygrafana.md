# README for pygrafana

# What is it?
PyGrafana is a python interface to Grafana. It is built of two seperate parts:
a Grafana dashboard interface and an interface to Grafana's HTTP API.

# Where can I get it?
Currently there is only a repository for PyGrafana:
https://github.com/TomTheBear/pygrafana
The installation is the default python setuptools way:
$ python setup.py build
$ sudo python setup.py install

# Dashboard module
The dashboard module encapsulates many Grafana options in Python classes and
they can be put together to set up a complete dashboard.

A small example (creates one graph panel spanning a complete row):
```
from pygrafana.dashboard import Target, GraphPanel, Row, Dashboard

target = Target("testmetric", alias="Testmetric [[tag_host]]")
graph = GraphPanel(targets=[target])
row = Row("Testmetric Row")
row.add_panel(graph)
dashboard = Dashboard("Test Dashboard")
dashboard.add_row(row)
```

# The API module
The API module encapsulates (I hope) all calls to the Grafana API. You can
add, delete, modify dashboards but also do the user/organization management
over it

A small example (adding the dashboard created above):
```
from pygrafana.api import Connection

con = Connection("localhost", 3000, "testuser", "testpass")
if con.is_connected:
    con.add_dashboard(dashboard)
```

# More information
See GitHub page of PyGrafana https://github.com/TomTheBear/pygrafana

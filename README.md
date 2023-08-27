

# LIKWID Monitoring Stack

**NOTE**: This repository is deprecated. If you are searching for a cluster-wide job-specific monitoring solution, check [ClusterCockpit](https://github.com/ClusterCockpit).

## What is it?
The LIKWID Monitoring Stack (LMS) is a set of tools and scripts to employ
job specific monitoring on a small to midsized HPC cluster. It contains
components running on the compute nodes, a tool to route the measurements as
middleware and agents for Grafana that automatically create dashboards.

It is thought to allow easy integration without changes to other software or
the creation of interfaces to them. There are so many solutions to gather data
at the job nodes that the interface to the upper stack should be as simple and
globally available as possible, thus the decision was made for HTTP.

The middleware tags the measurements with additional information like jobid or
username and forwards the data into a central database. The current version
provides only InfluxDB as database (mainly because it supports numbers AND
strings as metric values). If configured, the middleware can also duplicate the
measurements and send them in other databases (e.g. one per user) so that users
can view their own data without being able to see others' data.

The stack top is the web frontend which presents the job data for admins/users/
... The decision was made for Grafana as is supports many visualization options,
is scriptable and has a good HTTP API for management. It would be tedious to
create dashboards for each job manually, thus agents provide automatic
generation or manipulations of dashboards.

## Is it complete?
It is never complete! Things are changing, some people require features that are
currently not provided by the LMS: New metrics? New node agent? New grafana
agent?

## More documentation?
Each folder contains a README file about the content in the folder.

## License
All stuff in this repository is GPLv3. This might not fit for third-party
components like diamond, InfluxDB or Grafana.

## Help
If you have problems, please open an issue
For other things, please write me an email: Thomas.Roehl@fau.de

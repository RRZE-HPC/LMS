#!/bin/bash

# Example write for InfluxDB line protocol with timestamp set at receiption
curl -XPOST 'http://testhost.testdomain.de/write?db=testdatabase' --data-binary \
            "testmetric,hostname=testhost,username=testuser value=1.0"


# Example write for InfluxDB line protocol with custom timestamp in nanoseconds
curl -XPOST 'http://testhost.testdomain.de/write?db=testdatabase' --data-binary \
            "testmetric,hostname=testhost,username=testuser value=1.0 1500507673000000000"

# Example to register a new job. All key-value-pairs after the metric name
# will be added to each further measurement e.g. username or task identifier.
# Fields (like value) can be used to add further information like a task name
# or similar. Strings in fields must be surrounded by ' or " and properly escaped.
# At least these fields are required:
# - 'hosts' with a ':' separated list of hostnames
# - 'stat=start'
# Both field requirements can be changed in the InfluxDB router configuration

curl -XPOST 'http://testhost.testdomain.de/write?db=testdatabase' --data-binary \
            "baseevents,username=testuser,taskid=task0123 stat=start,hosts=host1:host2 1500507673000000000"

# Example to unregister a job with same mandatory fields as above

curl -XPOST 'http://testhost.testdomain.de/write?db=testdatabase' --data-binary \
            "baseevents stat=finish,hosts=host1:host2 1500507773000000000"

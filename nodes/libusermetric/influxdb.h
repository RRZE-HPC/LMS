#ifndef INFLUXDB_H
#define INFLUXDB_H


int influxdb_init(char* host, char* port, char* dest, int nbuff) __attribute__ ((visibility ("hidden") ));
//int influxdb_submit_value(char *key, int nfields, char** fields, float* values, unsigned long timestamp, int ntags, char** tagkeys, char** tagvalues) __attribute__ ((visibility ("hidden") ));
//int influxdb_submit_event(char *key, int nfields, char** fields, char** values, unsigned long timestamp, int ntags, char** tagkeys, char** tagvalues) __attribute__ ((visibility ("hidden") ));
void influxdb_close(void) __attribute__ ((visibility ("hidden") ));
int influxdb_submit_string(char* str) __attribute__ ((visibility ("hidden") ));

#endif

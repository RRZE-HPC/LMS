#ifndef USERMETRIC_H
#define USERMETRIC_H

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    INFLUXDB_OUT,
    FILE_OUT,
} UserMetricOutputType;


#define QUEUESIZE 10000

extern int init_usermetric(UserMetricOutputType type, char* host, char* port, char* dest, int add_defaults) __attribute__ ((visibility ("default") ));
extern int add_default_tag(char* key, char* val) __attribute__ ((visibility ("default") ));
extern int supply_uservalue(char *key, char* field, float value, int ntags, char** tagkeys, char** tagvalues) __attribute__ ((visibility ("default") ));
extern int supply_uservalues(char *key, int nfields, char** fields, float* values, int ntags, char** tagkeys, char** tagvalues) __attribute__ ((visibility ("default") ));
extern int supply_userevent(char *key, char* field, char* string, int ntags, char** tagkeys, char** tagvalues) __attribute__ ((visibility ("default") ));
extern int supply_userevents(char *key, int nfields, char** fields, char** strings, int ntags, char** tagkeys, char** tagvalues) __attribute__ ((visibility ("default") ));
extern void close_usermetric(void) __attribute__ ((visibility ("default") ));
extern void debug_usermetric(int val) __attribute__ ((visibility ("default") ));

#ifdef __cplusplus
} // extern "C"
#endif

#endif

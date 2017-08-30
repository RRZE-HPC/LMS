#ifndef FILE_OUTPUT_H
#define FILE_OUTPUT_H


int fileoutput_init(char* host, char* port, char* dest, int nbuff) __attribute__ ((visibility ("hidden") ));
//int fileoutput_submit_value(char *key, int nfields, char** fields, float* values, unsigned long timestamp, int ntags, char** tagkeys, char** tagvalues) __attribute__ ((visibility ("hidden") ));
//int fileoutput_submit_event(char *key, int nfields, char** fields, char** values, unsigned long timestamp, int ntags, char** tagkeys, char** tagvalues) __attribute__ ((visibility ("hidden") ));
void fileoutput_close(void) __attribute__ ((visibility ("hidden") ));

int fileoutput_submit_string(char* str) __attribute__ ((visibility ("hidden") ));

#endif

#ifndef CURL_CLIENT_H
#define CURL_CLIENT_H


int curl_client_init(char* host, int portno) __attribute__ ((visibility ("hidden") ));
size_t curl_client_get(char* path, char* query, size_t nheads, char** headers, char** data) __attribute__ ((visibility ("hidden") ));
int curl_client_post(char* path, char* query, char* data, size_t nheads, char** headers, char** resp) __attribute__ ((visibility ("hidden") ));
void curl_client_close(void) __attribute__ ((visibility ("hidden") ));



#endif

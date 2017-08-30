#ifndef HTTP_CLIENT_H
#define HTTP_CLIENT_H


int http_client_init(char* host, int portno) __attribute__ ((visibility ("hidden") ));
size_t http_client_get(char* path, char* query, size_t nheads, char** headers, char** data) __attribute__ ((visibility ("hidden") ));
int http_client_post(char* path, char* query, char* data, size_t nheads, char** headers, char** resp) __attribute__ ((visibility ("hidden") ));
void http_client_close(void) __attribute__ ((visibility ("hidden") ));



#endif

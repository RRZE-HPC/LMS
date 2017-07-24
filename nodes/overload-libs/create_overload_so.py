#!/usr/bin/env python3

import sys
import os
import re
from optparse import OptionParser

base = """#define _GNU_SOURCE

#include <stdio.h>
#include <dlfcn.h>

static void* (*real_malloc)(size_t)=NULL;

static void malloc_init(void)
{
    real_malloc = dlsym(RTLD_NEXT, "malloc");
    if (NULL == real_malloc) {
        fprintf(stderr, "Error in `dlsym`: %s\n", dlerror());
    }
}

void *malloc(size_t size)
{
    if(real_malloc==NULL) {
        malloc_init();
    }

    void *p = NULL;
    fprintf(stderr, "malloc(%d) = ", size);
    p = real_malloc(size);
    fprintf(stderr, "%p\n", p);
    return p;
}"""

base_func = """
static <REAL_HEAD>=NULL;
"""

base_init = """
static void <FUNC_NAME>_init(void)
{
    <REAL_NAME> = dlsym(RTLD_NEXT, "<FUNC_NAME>");
    if (NULL == <REAL_NAME>) {
        fprintf(stderr, "Error in `dlsym`: %s\\n", dlerror());
    }
}
"""

base_init_with_usermetrics = """
static void <FUNC_NAME>_init(void)
{
    <REAL_NAME> = dlsym(RTLD_NEXT, "<FUNC_NAME>");
    if (NULL == <REAL_NAME>) {
        fprintf(stderr, "Error in `dlsym`: %s\\n", dlerror());
    }
    if (!usermetric_initialized)
    {
        init_sending();
    }
}
"""



base_overl = """
<FUNC_HEAD>
{
    <INIT_COMMANDS>
    if(<REAL_NAME>==NULL) {
        <FUNC_NAME>_init();
    }

    <DEFINE_VAR>
    <MISC>
    <PRE_COMMANDS>
    <REAL_HEAD>;
    <POST_COMMANDS>
    return <RETURN_VAR>;
}
"""

base_init_usermetrics = """
static int usermetric_initialized = 0;
static int init_sending()
{
    return init_usermetric(INFLUXDB_OUT, "<HOSTNAME>", "<PORT>", "<DATABASE>", 1);
    usermetric_initialized = 1;
}
"""

test_init_usermetrics = """
    if (!usermetric_initialized)
    {
        init_sending();
    }
"""

base_close_usermetrics = """
__attribute__((destructor))
static void close_sending()
{
    if (usermetric_initialized)
        close_usermetric();
}
"""

base_num2str = """
char str[100]; snprintf(str, 99, \"<FORMAT>\", <PARAMS>");
"""

valid_data_types = {"int" : {"init": "0", "format": "%d"},
                    "unsigned" : {"init": "0", "format": "%u"},
                    "unsigned int" : {"init": "0", "format": "%u"},
                    "long" : {"init": "0", "format": "%ld"},
                    "unsigned long" : {"init": "0", "format": "%lu"},
                    "size_t" : {"init": "0", "format": "%lu"},
                    "off_t" : {"init": "0", "format": "%lu"},
                    "long long" : {"init": "0", "format": "%llu"},
                    "void" : {"init": None, "format": None},
                    "char" : {"init": "'0'", "format": "%c"} }


def get_func_info(fh):
    info = None
    m = re.search("(?P<func_ret>.*\s[\*]*)\s*(?P<func_name>[\w][\d\w]+)\s*\((?P<func_param>.*)\)", fh)
    if m:
        info = {}
        info["func_name"] = m.group("func_name")
        info["func_head"] = fh
        info["func_param"] = m.group("func_param")
        info["real_name"] = "real_%s" % m.group("func_name")
        info["real_head"] = fh.replace(info["func_name"], "(*%s)" % info["real_name"])
        func_param_names = []
        func_param_types = []
        for item in re.split(",", m.group("func_param")):
            if "(" in item:
                n = re.search("\(\*\s*([\w]+)\)", item)
                if n:
                    func_param_names.append(n.group(1))
                    func_param_types.append(None)
            else:
                ilist = re.split("\s+", item)
                if len(ilist) > 1:
                    func_param_names.append(ilist[-1].strip("*"))
                    func_param_types.append(" ".join(ilist[:-1]).strip(" "))

        info["func_param_names"] = func_param_names
        info["func_param_types"] = func_param_types
        retlist = re.split("\s+", m.group("func_ret"))
        newlist = []
        for item in retlist:
            if not item.startswith("_"):
                newlist.append(item)
        func_ret = " ".join(newlist).strip()
        info["func_ret"] = func_ret
        if func_ret in valid_data_types:
            info["func_init"] = valid_data_types[func_ret]["init"]
            info["func_print"] = valid_data_types[func_ret]["format"]
        else:
            info["func_init"] = None
            info["func_print"] = None
    return info

def is_ptr(s):
    if "*" in s: return True
    return False

def get_header(additional_headers=[]):
    s = """#define _GNU_SOURCE\n#include <stdio.h>\n#include <dlfcn.h>\n"""
    for h in additional_headers:
        if "include" in h:
            s += "%s\n" % h
        else:
            s += "#include <%s>\n" % h

    return s

def get_safe_ptr(info):
    return base_func.replace("<REAL_HEAD>", info["real_head"])

def get_init_func(info, usermetrics=False):
    if not usermetrics:
        return base_init.replace("<FUNC_NAME>", info["func_name"]).replace("<REAL_NAME>", info["real_name"])
    else:
        return base_init_with_usermetrics.replace("<FUNC_NAME>", info["func_name"]).replace("<REAL_NAME>", info["real_name"])

def get_overl_func(info):
    #print(info)
    s = base_overl.replace("<FUNC_HEAD>", info["func_head"])
    s = s.replace("<REAL_NAME>", info["real_name"])
    s = s.replace("<FUNC_NAME>", info["func_name"])
    if is_ptr(info["func_ret"]):
        s = s.replace("<DEFINE_VAR>", "%s p = NULL;" % (info["func_ret"],))
    else:
        if info["func_init"]:
            s = s.replace("<DEFINE_VAR>", "%s p = %s;\n" % (info["func_ret"], info["func_init"],))
        else:
            s = s.replace("<DEFINE_VAR>", "")
    if is_ptr(info["func_ret"]) or info["func_init"]:
        if is_ptr(info["func_ret"]) and not info["func_print"]:
            info["func_print"] = "%p"
        for i,p in enumerate(info["func_param_names"]):
            if p == "...":
                misc = "    va_list vl;\n    va_start(vl, %s);\n" % info["func_param_names"][i-1]
                s = s.replace("<MISC>", misc)
                info["func_param_names"][i] = "vl"
                break
        call_func = "p = %s(%s)" % (info["real_name"], ", ".join(info["func_param_names"]),)
        return_var = "p"
    else:
        call_func = "%s(%s)"  % (info["real_name"], ", ".join(info["func_param_names"]),)
        return_var = ""
    s = s.replace("<REAL_HEAD>", call_func)
    s = s.replace("<RETURN_VAR>", return_var)
    if "<MISC>" in s:
        s = s.replace("<MISC>", "")
    return s

def prepare_funcs(info, place="pre"):
    init = []
    funcs = []
    for fdict in info[place]:
        fields = len(fdict["param"])
        if fields > 0:
            init.append("char* keys[%d] = {\"title\", %s};" % (fields+1, ",".join(["\"%s\"" % k for k in fdict["name"]])))

            valnames = ["\""+info["func_name"]+"\""]
            for n, p in zip(fdict["name"], fdict["param"]):
                init.append("char param_%s[100];" % p)
                valnames.append("param_%s" % p)
                typ = info["func_param_types"][info["func_param_names"].index(p)]
                fmt = valid_data_types[typ]["format"]
                funcs.append("snprintf(param_%s, 99, \"%s\", %s);" % (p, fmt, p))
            funcs.append("char* vals[%d] = {%s};" % (fields+1, ", ".join(valnames)))
            keys = "keys"
            vals = "vals"
        else:
            init.append("char* keys[1] = {\"title\"};")
            init.append("char* vals[1] = {\"%s\"};" % info["func_name"])
            keys = "keys"
            vals = "vals"
        if fdict["op"] == "sendevent":
            f = "supply_userevents(\"appevents\", %d, %s, %s, 0, NULL, NULL);" % (fields+1, keys, vals)
        funcs.append(f)

    return init, funcs



def read_infile(filename, do_usermetric):
    def analyse_ops(line):
        ops = []

        ilist = re.split("\s*,\s*", line)
        for elem in ilist:
            if do_usermetric and elem.strip().startswith("sendvalue"):
                op = {}
                op["op"] = "sendvalue"
                op["name"] = []
                op["param"] = []
                for e in re.split("\s+", elem.strip()):
                    if e == "sendvalue": continue
                    name, param = e.split(":")
                    op["name"].append(name)
                    op["param"].append(param)
                ops.append(op)
            if do_usermetric and elem.strip().startswith("sendevent"):
                op = {}
                op["op"] = "sendevent"
                op["name"] = []
                op["param"] = []

                for e in re.split("\s+", elem.strip()):
                    if e == "sendevent": continue
                    name, param = e.split(":")
                    op["name"].append(name)
                    op["param"].append(param)
                ops.append(op)
            elif elem.strip().startswith("print"):
                op = {}
                op["op"] = "print"
                op["name"] = []
                op["param"] = []
                for e in re.split("\s+", elem.strip()):
                    if e == "print": continue
                    name, param = e.split(":")
                    op["name"].append(name)
                    op["param"].append(param)
                ops.append(op)
        return ops
    f = open(filename)
    out = f.read().strip().split("\n")
    f.close()
    data = {}
    data["headers"] = []
    data["funcs"] = []
    newout = []
    newheads = []
    newconf = {"head" : None, "pre" : {}, "post" : {}}
    for i,item in enumerate(out):
        if item.startswith("#"):
            data["headers"].append(item.strip("#").strip(" "))
        else:
            if item.startswith(" "):
                newitem = item.strip()
                if newitem.startswith("pre:"):
                    newconf["pre"] = analyse_ops(newitem.replace("pre:", ""))
                elif newitem.startswith("post:"):
                    newconf["post"] = analyse_ops(newitem.replace("post:", ""))
            else:
                if newconf["head"]:
                    data["funcs"].append(newconf)
                    newconf = {"head" : None, "pre" : {}, "post" : {}}
                newconf["head"] = item
    if newconf["head"]:
        data["funcs"].append(newconf)
    return data

def print_indata(indata):
    if len(indata["headers"]) > 0:
        print("Adding headers:")
        for h in indata["headers"]:
            print("- %s" % h)
        print("")
    for f in indata["funcs"]:
        print("\n\nFunction head: %s" % f["head"])

        if len(f["pre"]) > 0:
            print("Execute before function call:")
            for func in f["pre"]:
                print("- %s:" % func["op"])
                for n,p in zip(func["name"], func["param"]):
                    print("    %s - %s" % (n,p,))
                print("")

        if len(f["post"]) > 0:
            print("Execute after function call:")
            for func in f["post"]:
                print("- %s:" % func["op"])
                for n,p in zip(func["name"], func["param"]):
                    print("    %s - %s" % (n,p,))
                print("")

#func_list = ["void* malloc(size_t size)", "void free(void *ptr)",  "void *calloc(size_t nmemb, size_t size)", "void *realloc(void *ptr, size_t size)"]
def main():
    parser = OptionParser()
    parser.add_option("-i", "--input", dest="infile", help="Input dat file", default=None, metavar="FILE")
    parser.add_option("-o", "--output", dest="outfile", help="Output c file with code of overloaded functions (default print to stdout)", default=None, metavar="FILE")
    parser.add_option("-u", action="store_true", dest="usermetric",help="Embed libusermetric into shared library")
    (options, args) = parser.parse_args()


    infile = options.infile
    outfile = options.outfile
    print(options.usermetric)
    if not options.usermetric:
        options.usermetric = False
    if not infile:
        print("Filename of input dat file required")
        parser.print_help()
        sys.exit(1)


    hostname = "testhost"
    port = "8090"
    database = "testdatabase"
    do_usermetric = options.usermetric

    indata = read_infile(infile, do_usermetric)

    out = []
    heads = indata["headers"]
    if do_usermetric:
        heads.append("usermetric.h")
    out.append(get_header(additional_headers=heads))
    if do_usermetric:
        out.append(base_init_usermetrics.replace("<HOSTNAME>", hostname).replace("<PORT>", port).replace("<DATABASE>", database))
        out.append(base_close_usermetrics)

    fhinfos = {}
    for f in indata["funcs"]:
       fhinfos[f["head"]] = get_func_info(f["head"])
       fhinfos[f["head"]].update(f)

    for f in indata["funcs"]:
       out.append(get_safe_ptr(fhinfos[f["head"]]))
       out.append(get_init_func(fhinfos[f["head"]]))
       func = get_overl_func(fhinfos[f["head"]])
       pre_init, pre_funcs = prepare_funcs(fhinfos[f["head"]], place="pre")
       post_init, post_funcs = prepare_funcs(fhinfos[f["head"]], place="post")
       func = func.replace("<INIT_COMMANDS>", "\n".join(pre_init + post_init))
       func = func.replace("<PRE_COMMANDS>", "\n".join(pre_funcs))
       func = func.replace("<POST_COMMANDS>", "\n".join(post_funcs))
       out.append(func)

    if not outfile:
        print("\n".join(out))
    else:
        fp = open(outfile, "w")
        fp.write("\n".join(out))
        fp.close()

if __name__ == "__main__":
    main()

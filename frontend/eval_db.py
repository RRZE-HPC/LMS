#!/usr/bin/env python3


from influxdb import InfluxDBClient as DBClient
import pandas as pd
import numpy as np
import re
import matplotlib.pyplot as plt
from optparse import OptionParser

from pygrafana.dashboard import TextPanel

def mask(df, key, value):
    return df[df[key] == value]
pd.DataFrame.mask = mask



client = None



def influx_to_df(client, metric, fields=["*"], where=""):
    q = "select %s from %s" % (",".join(fields), metric)
    if len(where) > 0:
        q += " where %s" % where
    points = client.query(q).get_points()
    idx = []
    if fields != ["*"]:
        cols = fields
    else:
        cols = points[0].keys()
    vals = {}
    for p in points:
        idx.append(p["time"])
        for c in cols:
            if c not in vals:
                vals[c] = [p[c]]
            else:
                vals[c].append(p[c])

    df = pd.DataFrame(vals, index=pd.to_datetime(idx, unit='ns').tz_localize('UTC'))
    return df


def read_csv(filename, fields=None, timeoffset=120*60E9):
    def cast(v):
        if isinstance(v, str) and len(v) > 0:
            if "." in v:
                try:
                    v = np.float64(v)
                except:
                    pass
            else:
                try:
                    v = np.int64(v)
                except:
                    pass
        return v
    out = None
    with open(filename) as fp:
        name = None
        fdict = {}
        fnames = ["time"]
        indicies = [0]
        lines = fp.read().split("\n")
        while not lines[0].strip():
            del lines[0]
        m = re.match("#\s*(.*)", lines[0])
        if m:
            name = m.group(1)
            del lines[0]
        m = re.match("#\s*(.*)", lines[0])
        if m:
            fieldnames = m.group(1).split(",")
            if not fields:
                fields = fieldnames
                indicies = list(range(len(fieldnames)))
            for c in fields:
                if isinstance(c, int) and c >= 0 and c < len(fieldnames):
                    fdict.update({fieldnames[c] : []})
                    indicies.append(c)
                    fnames.append(fieldnames[c])
                if isinstance(c, str):
                    for i,f in enumerate(fieldnames):
                        if c == f:
                            fdict.update({c : []})
                            indicies.append(i)
                            fnames.append(c)
                            break
            del lines[0]
        content = [line.split(",") for line in lines if line.strip()]
        max_fields = max([len(l) for l in content])
        time = []
        for line in content:
            if len(line) != max_fields:
                continue
            for idx,fname in zip(indicies, fnames):
                if fname.lower() == "time":
                    time.append(np.int64(line[idx])+timeoffset)
                else:
                    fdict[fname].append(cast(line[idx]))
    return pd.DataFrame(fdict, index=pd.to_datetime(time, unit='ns').tz_localize('UTC'))


def get_uniques(df, key):
    hosts = df[key].unique()
    return hosts

def split_by_key(df, key, col="value", fill=["ffill", 0 ], drop_duplicates=True):
    hostvals = []
    hosts = get_uniques(df, key)
    hdf = pd.DataFrame([], index=df.index)
    for h in hosts:
        c = df.mask("hostname", h)[col]
        hdf[h] = c
    for f in fill:
        if type(f) == int:
            hdf.fillna(f, inplace=True)
        elif f in ("ffill", "bfill"):
            hdf.fillna(method=f, inplace=True)
    if drop_duplicates:
        hdf.drop_duplicates(inplace=True)
    return hdf

def get_series(df):
    idx_series = []
    for i in hdf.index[:10]:
        l = []
        for h in hosts:
            l.append(hdf[h][i])
    idx_series.append(pd.Series(l, index=hosts, name=i))
    return idx_series


def check_thresholds(hdf, keys, thresholds=[], threshold_names=[]):
    res = {}
    #thresholds = [100, 40000]
    #threshold_names = ["low", "ok", "good"]
    for h in keys:
        res[h] = "none"
        if h not in hdf:
            continue
        m = hdf[h].max()
        if m < thresholds[0]:
            res[h] = threshold_names[0] + " (%.1f)" % m
        elif m > thresholds[-1]:
            res[h] = threshold_names[-1] + " (%.1f)" % m
            #res[h] = threshold_names[-1]
        else:
            for i in range(len(thresholds)-1):
                if m >= thresholds[i] and m < thresholds[i+1]:
                    res[h] = threshold_names[i+1]  + " (%.1f)" % m
    return res

def check_load_imbalanace(hdf):
    trans = hdf.transpose()
    out = []
    idx = []
    for t in trans:
        idx.append(t)
        m = trans[t].max()
        if m > 0:
            out.append((m-trans[t].min())/m)
        else:
            out.append(np.NaN)
    return pd.Series(out, index=idx, name="load_imbalance")


def plot_roofline():
    max_flops = machine['clock']*sum(machine['FLOPs per cycle']['DP'].values())
    max_flops.unit = "FLOP/s"

    pprint(result)
    pprint(max_flops)

    # Plot configuration
    height = 0.8

    fig = plt.figure(frameon=False)
    ax = fig.add_subplot(1, 1, 1)

    yticks_labels = []
    yticks = []
    xticks_labels = []
    xticks = [2.**i for i in range(-4, 4)]

    ax.set_xlabel('arithmetic intensity [FLOP/byte]')
    ax.set_ylabel('performance [FLOP/s]')

    # Upper bound
    x = list(frange(min(xticks), max(xticks), 0.01))
    bw = float(result['mem bottlenecks'][result['bottleneck level']]['bandwidth'])
    ax.plot(x, [min(bw*x, float(max_flops)) for x in x])

    # Code location
    perf = min(
        float(max_flops),
        float(result['mem bottlenecks'][result['bottleneck level']]['performance']))
    arith_intensity = result['mem bottlenecks'][result['bottleneck level']]['arithmetic intensity']
    ax.plot(arith_intensity, perf, 'r+', markersize=12, markeredgewidth=4)

    # ax.tick_params(axis='y', which='both', left='off', right='off')
    # ax.tick_params(axis='x', which='both', top='off')
    ax.set_xscale('log', basex=2)
    ax.set_yscale('log')
    ax.set_xlim(min(xticks), max(xticks))
    # ax.set_yticks([perf, float(max_flops)])
    ax.set_xticks(xticks+[arith_intensity])
    ax.grid(axis='x', alpha=0.7, linestyle='--')
    # fig.savefig('out.pdf')
    plt.show()


def print_console(out):
    s = "Check\t"
    for h in hosts:
        s += "\t%s" % h
    print(s)
    for m in out:
        s = "%s" %m
        for h in hosts:
            s += "\t%s" % out[m][h]
        print(s)
#
#  <tr>
#    <th>Firstname</th>
#    <th>Lastname</th>
#    <th>Age</th>
#  </tr>
#  <tr>
#    <td>Jill</td>
#    <td>Smith</td>
#    <td>50</td>
#  </tr>
#  <tr>
#    <td>Eve</td>
#    <td>Jackson</td>
#    <td>94</td>
#  </tr>
#</table>
def print_html(out, width="100%"):
    colors= {"low" : "#FF0000", "ok" : "#FFFF00", "good" : "#00FF00", "none": "#808080"}
    s = "<table style=\"width:%s\", border=1>\n" % width
    s += "<tr>\n"
    s += "\t<th><center>Check</center></th>\n"
    cols = sorted(out[list(out.keys())[0]].keys())
    for c in cols:
        s+="\t<th><center>%s</center></th>\n" % c
    s += "</tr><tr>\n"
    for l in out:
        s += "\t<td>%s</td>\n" % l
        for c in cols:
            col = colors[out[l][c].split(" ")[0]]
            s += "\t<td bgcolor=%s>%s</td>\n" % (col, out[l][c])
        s += "</tr><tr>\n"
    s += "</tr>\n</table>"
    #print(s)
    return s

#






#print(lb.mean())
#print(hdf.head(10))

#print_console(out)


def main():
    parser = OptionParser()
    parser.add_option("-b", "--host", dest="dbhost", help="Hostname of database host", default="localhost")
    parser.add_option("-p", "--port", dest="dbport", help="Post number of database", default=8086)
    parser.add_option("-d", "--db", dest="dbname", help="Name of database", default="")
    parser.add_option("-u", "--user", dest="dbuser", help="User for database", default="admin")
    parser.add_option("-x", "--pass", dest="dbpass", help="Password for database", default="admin")
    parser.add_option("-j", "--job", dest="jobid", help="Job that should be analyzed", default="")
    (options, args) = parser.parse_args()

    client = DBClient(options.dbhost, options.dbport, options.dbuser, options.dbpass, options.dbname)
    where = ""
    if len(options.jobid) > 0:
        where = "jobid =~ /%s/" % options.jobid
    df = influx_to_df(client, "dpmflops", fields=["value", "hostname"], where=where)
    hosts = get_uniques(df, "hostname")
    hdf = split_by_key(df, "hostname")
    out = { "DP FLOP rate" : check_thresholds(hdf, hosts, [100, 40000], ["low", "ok", "good"]) }

    df = influx_to_df(client, "spmflops", fields=["value", "hostname"], where=where)
    hosts = get_uniques(df, "hostname")
    hdf = split_by_key(df, "hostname")
    out.update({ "SP FLOP rate" : check_thresholds(hdf, hosts, [100, 40000], ["low", "ok", "good"]) })

    df = influx_to_df(client, "mem_mbpers", fields=["value", "hostname"], where=where)
    hosts = get_uniques(df, "hostname")
    hdf = split_by_key(df, "hostname")
    out.update({ "Memory bandwidth rate" : check_thresholds(hdf, hosts, [2000, 20000], ["low", "ok", "good"]) })
    
    #df1 = influx_to_df(client, "ibPortRcvData_rate", fields=["value", "hostname"])
    #df2 = influx_to_df(client, "ibPortXmitData_rate", fields=["value", "hostname"])
    #df = pd.DataFrame({"value" : df1.value+df2.value, "hostname" : df1.hostname}, index=df1.index)
    #hdf = split_by_key(df, "hostname")
    #out.update({ "IB Rate" : check_thresholds(hdf, hosts, [10, 20000, 1E6], ["none", "low", "ok", "good"]) })

    #df1 = influx_to_df(client, "lustre_read_bytes", fields=["value", "hostname"])
    #df2 = influx_to_df(client, "lustre_write_bytes", fields=["value", "hostname"])
    #s = df1.value+df2.value
    #h = df1.hostname+df2.hostname
    #ndf = pd.DataFrame({"value" : s, "hostname" : h}, index=s.index)

    ##df = pd.DataFrame({"value" : df1.value+df2.value, "hostname" : df1.hostname+df2.hostname}, index=df1.index+df2.index)
    #hdf = split_by_key(ndf, "hostname")
    #out.update({ "Lustre Rate" : check_thresholds(hdf, hosts, [10, 20000, 1E6], ["none", "low", "ok", "good"]) })


    #lb = check_load_imbalanace(hdf)
    #hdf["load_imbalance"] = lb
    
    c = print_html(out)
    p = TextPanel("Job evaluation")
    p.set_mode("html")
    p.set_content(c)
    print(p)


if __name__ == "__main__":
    main()


#df1 = influx_to_df(client, "select value, hostname from likwid_mem_mbpers")
#df2 = influx_to_df(client, "select value, hostname from likwid_dpmflops")
#df3 = influx_to_df(client, "select value, hostname from likwid_spmflops")
##out.update({ "bla" : check_thresholds(hdf, hosts, [250, 20000], ["low", "ok", "good"]) })
#hdf = pd.DataFrame({"likwid_mem_mbpers" : df1.value, "likwid_tot_mflops" : df2.value+df3.value, "hostname" : df1.hostname, "op_intensity" : (df2.value+df3.value)/df1.value}, index=df1.index+df2.index+df3.index)




#test1 = split_by_key(hdf[["hostname", "op_intensity"]], "hostname", col="op_intensity")
#print(test1.head(10))
#test2 = split_by_key(hdf[["hostname", "likwid_tot_mflops"]], "hostname", col="likwid_tot_mflops")
#print(test2.head(10))
#hosts = get_uniques(hdf, "hostname")
#h= hosts[0]
#s = pd.Series(test2[h], index=test1[h])
#print(s)
#hdf["load_imbalance"] = pd.Series(lb, index=hdf.index)
#print(hdf.head(20))



#hosts = list(set(df["hostname"]))
#hostvals = {}
#for h in hosts:
#    hostvals[h] = []
#for i,h,v in zip(df.index, df["hostname"], df["value"]):
#    for t in hosts:
#        if t == h:
#            hostvals[t].append(v)
#        else:
#            hostvals[t].append(np.NaN)
#df2 = pd.DataFrame(hostvals, index=df.index).fillna(method="ffill")
#print(df2[20:30])

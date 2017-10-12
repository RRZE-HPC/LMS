#!/usr/bin/perl -w

# MASTER VERSION IS IN git@git:admintools/scripts/; THIS IS # REVISION ......

# This script collects as many metrics for ganglia as possible.
# It is usually run in endless loop mode for continuous data collection.

use Sys::Hostname;

# Gets symlinked into that path by the HP installer, should thus never need to be changed
$HPASMCLI = '/sbin/hpasmcli';

# ipmitool
$IPMITOOL = '/usr/bin/ipmitool';

# gmetric
$GMETRIC = '/usr/bin/gmetric';

# lmsensors
$LMSENSORS = '/usr/bin/sensors';

# Nodehealthcheck
$NODEHEALTHCHECK = '/var/cfengine/scripts/nodehealthcheck.pl';

# Sensors for ipmitool2
$IPMISENSORS = '';

# File for network traffic
$NETSTATFILE = '/proc/net/dev';

# File for memory information
$MEMSTATFILE = '/proc/meminfo';

# File for load information
$LOADSTATFILE = '/proc/loadavg';

# File for cpu information
$CPUSTATFILE = '/proc/stat';

# Curl to write directly into InfluxDB
$CURL = '/usr/bin/curl';
$CURLHOST = 'testhost.testdomain.de:8090';
$CURLDB = 'testcluster';


# Command line for hpcmon
$HPCMON = '/var/cfengine/inputs/datafiles/hpcmon/hpcm_p -m -fd -fs -f -l -bc -b /bin/sleep 5';
#$HPCMON = '/apps/rrze/sbin/hpcm_p -m -fd -fs -f -l -bc -b /bin/sleep 5';

$CLUSTER="none";
$firstloop = 1;

# Command line for LIKWID
if ( hostname() =~ /^tb/ ) {
   $LIKWID = 'su hpcop -c "/apps/likwid/system/bin/likwid-perfctr -f -c 0-15 -g VIEW -O -S 10"';
   $CLUSTER = "tinyblue";
} elsif ( hostname() =~ /^tg/ ) {
   $LIKWID = 'su hpcop -c "/apps/likwid/system/bin/likwid-perfctr -f -c 0-11 -g VIEW -O -S 10s"';
   $CLUSTER = "tinygpu";
} elsif ( hostname() =~ /^l[01]/ ) {
   $LIKWID = 'su hpcop -c "/apps/likwid/system/bin/likwid-perfctr -f -c 0-23 -g VIEW -O -S 10"';
   $CLUSTER = "lima";
} elsif ( hostname() =~ /^e[01]/ ) {
   $LIKWID = 'su hpcop -c "/apps/likwid/system/bin/likwid-perfctr -f -c 0-39 -g VIEW -O -S 10"';
   $CLUSTER = "emmy";
} else {
   $LIKWID = '/apps/likwid/system/bin/likwid-perfctr -f -c 0-23 -g VIEW -M 2 -P -O -s 10';
}

# Path for Lustre/LXFS statistics
$LUSTRESTATS =  '/proc/fs/lustre/llite/lnec-XXXXXX/stats';

# Path for IB statistics
$IBLID = '/sys/class/infiniband/mlx4_0/ports/1/lid';

# Defaults for running data collections
$trytorun{'vmstats'} = 1;
$trytorun{'diskstats'} = 1;
$trytorun{'ipmitool'} = 1;
$trytorun{'ipmitool2'} = 1;
$trytorun{'hpasmcli'} = 1;
$trytorun{'lmsensors'} = 1;
$trytorun{'pperfctrs'} = 1;
$trytorun{'nfsdstats'} = 0;
$trytorun{'lustrestats'} = 0;
$trytorun{'ibstats'} = 0;
$trytorun{'nodehealthcheck'} = 0;
$trytorun{'hpcmon'} = 0;
$trytorun{'likwid'} = 0;
$trytorun{'netstats'} = 0;
$trytorun{'memstats'} = 0;
$trytorun{'cpustats'} = 0;
$trytorun{'loadstats'} = 0;

# Default sampletime
$sampletime = 60;

%valuehash = ();
%unithash = ();
#
#############################################################################
# End of settings section
#############################################################################
#

# Par: none
# Returns: Associative Array countername -> value
sub getperfcounters {
  my %perfarray = ();
  if (-r '/proc/perfcounters') {
    my $PCF = undef; my $ll;
    if (open($PCF, '</proc/perfcounters')) {
      while ($ll = <$PCF>) {
        #print($ll);
        # Untested
        if ($ll =~ m/^non-sleep clockticks.*: (\d+)/) { $perfarray{'nsTicks'} = $1 / 10.0; }
        if ($ll =~ m/^instructions retired.*: (\d+)/) { $perfarray{'instRet'} = $1 / 10.0; }
        if ($ll =~ m/^x87 compute instructions retired.*: (\d+)/) { $perfarray{'x87Ret'} = $1 / 10.0; }
        if ($ll =~ m/^x87 fp ops retired.*: (\d+)/) { $perfarray{'x87Ret'} = $1 / 10.0; }
        if ($ll =~ m/^sse instructions retired.*: (\d+)/) { $perfarray{'sseRet'} = $1 / 10.0; }
      }
      close($PCF);
    }
  }
  return %perfarray;
}

# Par: none
# Returns: associative array  diskname -> { sectors_read, sectors_written, pending_requests }
sub getdiskstats {
  my %diskstats = ();
  if (-r '/proc/diskstats') {
    my $DSKST = undef; my $ll; my @ls; my @curstats;
    if (open($DSKST, '</proc/diskstats')) {
      while ($ll = <$DSKST>) {
        @ls = split(' ', $ll);
        if (@ls == 14) { # Physical disk
          @curstats = ($ls[5], $ls[9], $ls[11]);
        } elsif (@ls == 7) {
          @curstats = ($ls[4], $ls[6], -1);
        } else {
          @curstats = (0, 0, -1);
        }
        if (($curstats[0] > 10) || ($curstats[1] > 10)) {
          $ls[2] =~ s|/|_|g;
          $diskstats{$ls[2]} = [ @curstats ];
        }
      }
      close($DSKST);
    }
  }
  return %diskstats;
}

# Par: none
# Returns: associative array  name -> value (just like in /proc/vmstat)
sub getvmstats {
  my %vmstats = ();
  if (-r '/proc/vmstat') {
    my $VMST = undef; my $ll;
    if (open($VMST, '</proc/vmstat')) {
      while ($ll = <$VMST>) {
        if ($ll =~ m/^([a-z0-9]+)\s+(\d+)$/) {
          $vmstats{$1} = $2;
        }
      }
      close($VMST);
    }
  }
  return %vmstats;
}

# Par: none
# Returns: associative array  name -> value (just like in /proc/stat)
sub getgenstats {
  my %vmstats = ();
  if (-r '/proc/stat') {
    my $VMST = undef; my $ll;
    if (open($VMST, '</proc/stat')) {
      while ($ll = <$VMST>) {
        if ($ll =~ m/^([a-z0-9]+)\s+(\d+)/) {
          $vmstats{$1} = $2;
        }
      }
      close($VMST);
    }
  }
  return %vmstats;
}

# Par: none
# Returns: nr. of open filedescriptors (or undef)
sub getnumopenfds {
  my $ret = undef;
  if (-r '/proc/sys/fs/file-nr') {
    my $VMST = undef; my $ll;
    if (open($VMST, '</proc/sys/fs/file-nr')) {
      $ll = <$VMST>;
      if ($ll =~ m/^(\d+)/) {
        $ret = $1;
      }
      close($VMST);
    }
  }
  return $ret;
}

# Par: none
# Returns: associative array  tempsensorname -> value
sub gethpasmcli {
  my %res = ();
  if (-x $HPASMCLI) {
    my $HPCLI = undef; my $ll;
    if (open($HPCLI, "$HPASMCLI -s 'show temp'|")) {
      while ($ll = <$HPCLI>) {
        # #1        PROCESSOR_ZONE       37C/98F    62C/143F
        if ($ll =~ m/^\s*#\d+\s+([^ \t]+)\s+([0-9.]+)C/) {
          my $tempname = lc($1);
          my $tempval = $2;
          $tempname =~ s/[^a-z0-9]//g;
          $res{$tempname} = $tempval;
        }
      }
      close($HPCLI);
    }
  }
  return %res;
}

# Par: none
# Returns: associative array  sensorname -> ( value, unit )
sub getipmisensor {
  my %res = ();
  if (-x $IPMITOOL) {
    my $HPCLI = undef; my $ll; my @ls;
    if (open($HPCLI, "$IPMITOOL sensor|")) {
      while ($ll = <$HPCLI>) {
        @ls = split(/\s*\|\s*/, $ll);
        $ls[0] = lc($ls[0]);
        $ls[0] =~ s/[^a-z0-9]//g;
        $ls[2] = lc($ls[2]);
        $ls[2] =~ s/[^a-z0-9]//g;
        if (($ls[0] =~ m/^Fan (\d+)$/) && ($ls[2] eq 'unspecified')) {
          if ($ls[1] =~ m/^\d+\.\d+$/) {
            my $realnumb = $ls[1] * 1000.0;
            if (int($realnumb) > 1000) {
              # This is a RPM value, Silently correct this
              $ls[1] = int($realnumb);
              $ls[2] = 'rpm';
            }
          }
        }
        if (($ls[2] eq 'degreesc')
         || ($ls[2] eq 'volts')
         || ($ls[2] eq 'rpm')
         || ($ls[2] eq 'watts')) {
          if ($ls[1] =~ m/^[0-9.]+$/) {
            $res{$ls[0]} = [ $ls[1], $ls[2] ];
          }
        }
      }
      close($HPCLI);
    }
  }
  return %res;
}

# Par: none
# Returns: associative array  sensorname -> ( value, unit )
sub getlmsensors {
  my %res = ();
  if (-x $LMSENSORS) {
    my $HPCLI = undef; my $ll = ''; my $sll;
    if (open($HPCLI, "$LMSENSORS |")) {
      while ($sll = <$HPCLI>) {
        $sll =~ s/[\r\n]/ /g;
        if ($sll =~ m/^\s+/) {
          $ll .= $sll;
        } else {
          $ll = $sll;
        }
        if ($ll =~ m/^([a-zA-Z0-9_\- .]+):\s+([0-9\-+.]+)[ \xB0]+([A-Za-z]+)/) {
          my $vname = lc($1); my $vval = $2; my $vunit = lc($3);
          $vname =~ s|[^a-z0-9_\-]|_|g;
          $vval =~ s/\+//g;
          $vunit =~ s|[^a-z0-9_\-]|_|g;
          $res{$vname} = [ $vval, $vunit ];
          $ll = '';
        }
      }
      close($HPCLI);
    }
  }
  return %res;
}

# Par: none
# Returns: associative array. Keys: getattr, setattr, read, write, readdir, readdirplus
sub getnfsdstats {
  my %res = ();
  if (-r '/proc/net/rpc/nfsd') {
    my $NFSDST = undef; my $ll; my @ls; my @curstats;
    if (open($NFSDST, '</proc/net/rpc/nfsd')) {
      while ($ll = <$NFSDST>) {
        @ls = split(' ', $ll);
        if ((@ls == 24) && ($ls[0] =~ m/^proc3/))  { # NFS V3
          $res{'getattr'} = $ls[3];
          $res{'setattr'} = $ls[4];
          $res{'read'} = $ls[8];
          $res{'write'} = $ls[9];
          $res{'readdir'} = $ls[18];
          $res{'readdirplus'} = $ls[19];
        }
      }
      close($NFSDST);
    }
  }
  return %res;
}

# Par: none
# Returns: associative array. Keys: read_bytes, write_bytes, open, close, setattr, getattr, statfs, inode_permission
sub getlustrestats {
  my %res = ();
  if (-r "$LUSTRESTATS") {
    my $LUSTREST = undef; my $ll; my @ls; my @curstats;
    if (open($LUSTREST, '<'.$LUSTRESTATS)) {
      while ($ll = <$LUSTREST>) {
        @ls = split(/\s+/, $ll);
        if ($ls[0] =~ m/read_bytes/) {
          $res{'read_requests'} = $ls[1];
          $res{'read_bytes'} = $ls[6];
	} elsif ($ls[0] =~ m/write_bytes/) {
          $res{'write_requests'} = $ls[1];
          $res{'write_bytes'} = $ls[6];
	} elsif ($ls[0] =~ m/open/) {
          $res{'open'} = $ls[1];
	} elsif ($ls[0] =~ m/close/) {
          $res{'close'} = $ls[1];
	} elsif ($ls[0] =~ m/setattr/) {
          $res{'setattr'} = $ls[1];
	} elsif ($ls[0] =~ m/getattr/) {
          $res{'getattr'} = $ls[1];
	} elsif ($ls[0] =~ m/statfs/) {
          $res{'statfs'} = $ls[1];
	} elsif ($ls[0] =~ m/inode_permission/) {
          $res{'inode_permission'} = $ls[1];
        }
      }
      close($LUSTREST);
    }
  }
  return %res;
}

# Par: none
# Returns: associative array. Keys: recv, xmit
sub getibstats {
  my %res = ();
  if (-r "$IBLID") {
    #if (open($IB, "/usr/sbin/perfquery -r `cat $IBLID` 1 0x3000 |")) {
    if (open($IB, "/usr/sbin/perfquery -r `cat $IBLID` 1 0xf000 |")) {
      while ($ll = <$IB>) {
        @ls = ( $ll =~ m/(.+:)\.+([0-9]*)/ );
        # from the perfquery manpage:
        # Note: In PortCounters, PortCountersExtended, PortXmitDataSL, and PortRcvDataSL, components that represent Data (e.g. PortXmitData
        # and PortRcvData)  indicate octets divided by 4 rather than just octets.
        if ( defined($ls[0]) && $ls[0] =~ m/PortRcvData:|RcvData:/) {
          $res{'recv'}  = $ls[1] * 4;
        } elsif ( defined($ls[0]) && $ls[0] =~ m/PortXmitData:|XmtData:/) {
          $res{'xmit'}  = $ls[1] * 4;
        }
      }
      close($IB);
    }
  }
  return %res;
}

# Par: none
# Returns: associative array with keys HCWarnings and HCErrors.
sub getnodehealthcheck {
  my %res = ();
  if (-x $NODEHEALTHCHECK) {
    my $HPCLI = undef; my $ll; my @ls;
    if (open($HPCLI, "$NODEHEALTHCHECK |")) {
      while ($ll = <$HPCLI>) {
        if ($ll =~ m/WARNING:/) {
          if (defined($res{'HCWarnings'})) { $res{'HCWarnings'}++; } else { $res{'HCWarnings'} = 1; }
        }
        if ($ll =~ m/ERROR:/) {
          if (defined($res{'HCErrors'})) { $res{'HCErrors'}++; } else { $res{'HCErrors'} = 1; }
        }
        if ($ll =~ m/^All Ok\.$/) {
          if (!defined($res{'HCErrors'})) { $res{'HCErrors'} = 0; }
          if (!defined($res{'HCWarnings'})) { $res{'HCWarnings'} = 0; }
        }
        if ($ll =~ m/Warncode (\d+), Errcode (\d+)\./) {
          $res{'HCErrors'} = $2;
          $res{'HCWarnings'} = $1;
        }
      }
      close($HPCLI);
    }
  }
  return %res;
}

# Par: none
# Returns: associative array  sensorname -> ( value, unit )
sub getipmisensor2 {
  my %res = ();
  if ((length($IPMISENSORS) > 0) && (-x $IPMITOOL)) {
    my $HPCLI = undef; my $ll; my $cs = '';
    my $cmdline = "$IPMITOOL sensor get";
    foreach $ll (split(/,/, $IPMISENSORS)) {
      $cmdline .= " '$ll'";
    }
    if (open($HPCLI, "$cmdline |")) {
      while ($ll = <$HPCLI>) {
        if ($ll =~ m/Sensor ID\s+: +(.*)\s+\(0x.*\)/i) {
          $cs = lc($1);
          $cs =~ s/[^a-z0-9]//g;
        }
        if ($ll =~ m/Sensor Reading\s+: +(.*)/i) {
          my $sr = $1;
          if ($sr =~ m/([0-9.]+)\s+\(.*\)\s+(.*)/) {
            my $v = $1;
            my $u = lc($2);
            $u =~ s/[^a-z0-9]//g;
            if (($u eq 'degreesc')
             || ($u eq 'volts')
             || ($u eq 'rpm')
             || ($u eq 'watts')) {
              if ($v =~ m/^[0-9.]+$/) {
                if (length($cs) > 0) {
                  $res{$cs} = [ $v, $u ];
                }
              }
            }
          }
        }
      }
      close($HPCLI);
    }
  }
  return %res;
}

# Par: none
# Returns: associative array. Keys: CyclesPerInst X87MOPS SSEMOPS DPMFLOPS SPMFLOPS L2MissRate FSBClTraf BytesPerFlop
sub gethpcmon {
  my %res = ();
  my $ll; my $HPCMEX = undef;
  if (open($HPCMEX, "$HPCMON |")) {
    while ($ll = <$HPCMEX>) {
      if ($ll =~ m/Cycles per instruction \(CPI\):\s+([0-9.]+)/) {
        $res{'hpcm_CyclesPerInst'} = $1;
      }
      if ($ll =~ m/X87 MOPS:\s+([0-9.]+)/) {
        $res{'hpcm_X87_MOPS'} = $1;
      }
      if ($ll =~ m/SSE MOPS:\s+([0-9.]+)/) {
        $res{'hpcm_SSE_MOPS'} = $1;
      }
      if ($ll =~ m/Double precision MFLOPS:\s+([0-9.]+)/) {
        $res{'hpcm_DP_MFLOPS'} = $1;
      }
      if ($ll =~ m/Single precision MFLOPS:\s+([0-9.]+)/) {
        $res{'hpcm_SP_MFLOPS'} = $1;
      }
      if ($ll =~ m/L2 miss rate:\s+([0-9.]+)/) {
        $res{'hpcm_L2_MissRate'} = $1;
      }
      if ($ll =~ m/FSB cacheline traffic:\s+([0-9.]+)/) {
        $res{'hpcm_FSB_ClTraf'} = $1;
      }
      if ($ll =~ m|Bytes/FLOP:\s+([0-9.]+)|) {
        $res{'hpcm_BytesPerFlop'} = $1;
      }
    }
    close($HPCMEX);
  }
  return %res;
}

# Par: none
# Returns: associative array. Keys:
sub getnetstats {
    my %netstats = ();
    if ( -r $NETSTATFILE) {
        if (open($NETST, '<'.$NETSTATFILE)) {
            while ($ll = <$NETST>) {
                @ls = split(' ', $ll);
                if ($ls[0] =~ /(.*):/) {
                    $netstats{$1."_bytes_in"} = $ls[1];
                    $netstats{$1."_bytes_out"} = $ls[9];
                    $netstats{$1."_pkts_in"} = $ls[2];
                    $netstats{$1."_pkts_out"} = $ls[10];
                }
            }
        }
    }
    return %netstats;
}

# Par: none
# Returns: associative array. Keys:
sub getmemstats {
    my %memstats = ();
    if ( -r $MEMSTATFILE) {
        if (open($MEMST, '<'.$MEMSTATFILE)) {
            while ($ll = <$MEMST>) {
                @ls = split(' ', $ll);
                $ls[0] =~ s/://;
                $memstats{$ls[0]} = $ls[1];
            }
        }
    }
    return %memstats;
}

# Par: none
# Returns: associative array. Keys:
sub getloadstats {
    my %loadstats = ();
    if ( -r $LOADSTATFILE) {
        if (open($LOADST, '<'.$LOADSTATFILE)) {
            $ll = <$LOADST>;
            @ls = split(' ', $ll);
            $loadstats{"load_one"} = $ls[0];
            $loadstats{"load_five"} = $ls[1];
            $loadstats{"load_fifteen"} = $ls[2];
        }
    }
    return %loadstats;
}

# Par: none
# Returns: associative array. Keys:
sub getcpustats {
    my %cpustats = ();
    if ( -r $CPUSTATFILE)
    {
        if (open($CPUST, '<'.$CPUSTATFILE)) {
            while ($ll = <$CPUST>) {
                @ls = split(' ', $ll);
                @keys = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal", "guest", "guest_nice");
                if ($ll =~ /cpu(\d+)/)
                {
                    my $cpu = $1;
                    for ($j=0; $j<@keys; $j += 1) {
                        $cpustats{"C".$cpu."_cpu_".$keys[$j]} = $ls[$j + 1];
                    }
                    next;
                }
                #if ($ls[0] eq "processes") {
                #    $cpustats{"processes"} = $ls[1];
                #}
            }
        }
    }
    return %cpustats;
}


# Par: none
# Returns: associative array. Keys: 
sub getlikwid {
  my %res = ();
  my $ll; my $LIKWIDEX = undef;
  if (open($LIKWIDEX, "$LIKWID |")) {
    while ($ll = <$LIKWIDEX>) {
      $ll =~ s/[\r\n]//g;
      if ($ll =~ m/^Clock \[MHz\],(.+)/) {
        my @spl = split(/,/, $1);
        my $cfs = 0; my $cfc = 0; my $m;
        foreach $m (@spl) {
          if ($m ne 'nan') {
            if ($m > 0.0) {
              $cfc++; $cfs += 0.0 + $m;
            }
          }
        }
        if ($cfc > 0) {
          $res{'likwid_cpusnothalted'} = $cfc;
          $res{'likwid_avgcpuspeed'} = ($cfs * 1.0 / $cfc);
        }
      }
      #start-temporary-cpi-workaround
#      if ($ll =~ m/^CPI,(.+)/) {
#        my @spl = split(/,/, $1);
#        my $cfs = 0; my $cfc = 0; my $m;
#        foreach $m (@spl) {
#          if ($m ne 'nan') {
#            if ($m > 0.0) {
#              $cfc++; $cfs += 0.0 + $m;
#            }
#          }
#        }
#        if ($cfc > 0) {
#          $res{'likwid_avgcpi'} = ($cfs * 1.0 / $cfc);
#        }
#      }
      if ($ll =~ m|INSTR_RETIRED_ANY STAT,([0-9.]+),[^,]*,[^,]*,[0-9.]+|) {
        $res{'raw_likwid_instructions_retired'} = $1;
      }
      if ($ll =~ m|CPU_CLK_UNHALTED_CORE STAT,([0-9.]+),[^,]*,[^,]*,[0-9.]+|) {
        $res{'raw_likwid_clk_unhalted'} = $1;
      }
      #end-temporary-cpi-workaround
      if ($ll =~ m|Packed MUOPS/s STAT,([0-9.]+),[^,]*,[^,]*,[0-9.]+|) {
        $res{'likwid_muops_packed'} = $1;
      }
      if ($ll =~ m|Scalar MUOPS/s STAT,([0-9.]+),[^,]*,[^,]*,[0-9.]+|) {
        $res{'likwid_muops_scalar'} = $1;
      }
      if ($ll =~ m|SP MUOPS/s STAT,([0-9.]+),[^,]*,[^,]*,[0-9.]+|) {
        $res{'likwid_muops_float'} = $1;
      }
      if ($ll =~ m|DP MUOPS/s STAT,([0-9.]+),[^,]*,[^,]*,[0-9.]+|) {
        $res{'likwid_muops_double'} = $1;
      }
      if ($ll =~ m|Memory bandwidth \[MBytes/s\] STAT,([0-9.]+),[^,]*,[^,]*,[0-9.]+|) {
        $res{'likwid_mem_mbpers'} = $1;
      }
      if ($ll =~ m|Remote Read BW \[MBytes/s\] STAT,([0-9.]+),[^,]*,[^,]*,[0-9.]+|) {
        $res{'likwid_remread_mbpers'} = $1;
      }
      if ($ll =~ m|DP MFlops/s \(DP assumed\) STAT,([0-9.]+),[^,]*,[^,]*,[0-9.]+|) {
        $res{'likwid_dpmflops'} = $1;
      }
      @ids = ("INSTR_RETIRED_ANY", "CPU_CLK_UNHALTED_CORE");
      @names = ("instructions_retired", "clk_unhalted");
      @units = ("", "MHz");
      my $index = 0;
      my $iindex = 0;
      foreach my $id (@ids) {
        if ($ll =~ m|$id[^,]*,(.*)| and not $ll =~ m|STAT|) {
            my @spl = split(/,/, $1);
            my $unit = $units[$index];
            my $name = $names[$index];
            $iindex = 0;
            foreach my $m (@spl) {
                if ($m =~ /^\d+/)
                {
                    $valuehash{"C".$iindex."_".$name} = $m;
                    if ($unit ne "") {
                        $unithash{"C".$iindex."_".$name} = $unit;
                    }
                    $iindex++;
                }
            }
        }
        $index++;
      }
      $index = 0;
      $iindex = 0;
      @ids = ("Packed MUOPS/s", "Scalar MUOPS/s", "SP MUOPS/s", "DP MUOPS/s", "DP MFLOP/s", "SP MFLOP/s");
      @names = ("muops_packed", "muops_scalar", "muops_float", "muops_double", "dpmflops", "spmflops");
      @units = ("MUOPS/s", "MUOPS/s", "MUOPS/s", "MUOPS/s", "MFLOP/s", "MFLOP/s");
      $index = 0;
      $iindex = 0;
      foreach my $id (@ids) {
        if ($ll =~ m|$id[^,]*,(.*)| and not $ll =~ m|STAT|) {
            my @spl = split(/,/, $1);
            my $unit = $units[$index];
            my $name = $names[$index];
            $iindex = 0;
            foreach my $m (@spl) {
                $valuehash{"C".$iindex."_".$name} = $m;
                if ($unit ne "") {
                    $unithash{"C".$iindex."_".$name} = $unit;
                }
                $iindex++;
            }
        }
        $index++;
      }
      $index = 0;
      $iindex = 0;
      @ids = ("Memory bandwidth", "Remote Read BW");
      @names = ("mem_mbpers", "remread_mbpers");
      @units = ("MBytes/s", "MBytes/s");
      foreach my $id (@ids) {
        if ($ll =~ m|$id[^,]*,(.*)| and not $ll =~ m|STAT|) {
            if ($ll =~ m|STAT|)
            {
              continue;
            }
            my @spl = split(/,/, $1);
            my $unit = $units[$index];
            my $name = $names[$index];
            $iindex = 0;
            foreach my $m (@spl) {
                if ($m+0.0 > 0)
                {
                  $valuehash{"S".$iindex."_".$name} = $m;
                  if ($unit ne "") {
                      $unithash{"S".$iindex."_".$name} = $unit;
                  }
                  $iindex++;
                }
            }
        }
        $index++;
      }
    }
    close($LIKWIDEX);
    my $cpi_sum = 0;
    my $cpi_count = 0;
    foreach my $k (keys(%valuehash)) {
        if ($k =~ m/C(\d+)_instructions_retired/)
        {
            if ($valuehash{"C".$1."_instructions_retired"} != 0.0) {
                $valuehash{"C".$1."_cpi"} = $valuehash{"C".$1."_clk_unhalted"} / $valuehash{"C".$1."_instructions_retired"};
                $cpi_sum += $valuehash{"C".$1."_cpi"};
                $cpi_count += 1;
            }
            else
            {
                $valuehash{"C".$1."_cpi"} = 0;
            }
        }
    }
    if ($cpi_count > 0) {
        $res{'likwid_avgcpi'} = $cpi_sum / $cpi_count;
    }
    #start-temporary-cpi-workaround
    #if ( defined($res{'raw_likwid_instructions_retired'}) && defined ($res{'raw_likwid_clk_unhalted'}) && $res{'raw_likwid_instructions_retired'} > 0.0 ) {
    #      $res{'likwid_avgcpi'} = $res{'raw_likwid_clk_unhalted'} / $res{'raw_likwid_instructions_retired'};
    #}
    
    delete $res{'raw_likwid_instructions_retired'};
    delete $res{'raw_likwid_clk_unhalted'};
    #end-temporary-cpi-workaround
  }
  else
  {
    printf("Cannot execute $LIKWID\n");
  }
  return %res;
}

# Par. 0: metric name
# Par. 1: type (double, int, etc.)
# Par. 2: value
# Par. 3: Unit (optional, default '')
sub callgmetric($$$;$) {
  my $cmd = "$GMETRIC --dmax=".int(5*$sampletime)." --name=$_[0] --type=$_[1]";
  my $vv;
  if (($_[1] eq 'double') || ($_[1] eq 'float')) {
    $vv = sprintf("%.6lf", $_[2]);
  } else {
    $vv = $_[2];
  }
  $cmd .= " --value=$vv";
  $unithash{$_[0]} = "";
  if (defined($_[3])) {
    $cmd .= " --unit=$_[3]";
    $unithash{$_[0]} = $_[3];
  }
  $valuehash{$_[0]} = $vv;
}


sub callcurl {
    my $host = hostname();
#    my $job = "NONE";
#    my $user = "NONE";
    my $timestamp = time();
    $timestamp = (int ($timestamp / $sampletime)) * $sampletime;
    $timestamp *= 1000000000;
    my $maxtime = $sampletime - 2;
#    if (open(my $fh, '<', $JOBFILE)) {
#        while (my $row = <$fh>) {
#            if ($row =~ m/(\d+)\s+([\d\w]+)/)
#            {
#                $job = $1;
#                $user = $2;
#            }
#        }
#    }
#    my $topprocess = `ps -eo cmd --sort=pcpu | tail -n 1`;

    my $ccmd = "$CURL -f -m $maxtime -XPOST 'http://$CURLHOST/write?db=$CURLDB' --data-binary '";
    foreach $k (keys(%valuehash)) {
        my $metric = $k;
        my $cpu = "-1";
        my $socket = "-1";
        if ($metric =~ m/C(\d+)_(.+)/) {
            $metric = $2;
            $cpu = $1;
        }
        if ($metric =~ m/S(\d+)_(.+)/) {
            $metric = $2;
            $socket = $1;
        }
        $ccmd .= "$metric,hostname=$host";
        if ($cpu ne "-1") {
            $ccmd .= ",cpuid=$cpu";
        }
        if ($socket ne "-1") {
            $ccmd .= ",socketid=$socket";
        }
        $ccmd .= " value=$valuehash{$k}";
        if (defined($unithash{$k}) and ($unithash{$k} ne "")) {
            $ccmd .= ",unit=\"$unithash{$k}\"";
        }
        $ccmd .= " $timestamp\n"
    }
    $ccmd .= "'";
    if ($detectionrun) {
        print("$ccmd\n");
    } else {
        system($ccmd);
        %{$valuehash} = ();
        %{$unithash} = ();
    }
}

#
# --- main() ----------------------------------------------------------------
#
$detectionrun = 0;
for ($i = 0; $i < @ARGV; $i++) {
  if      ($ARGV[$i] eq '-h') {
    $showhelp = 1;
  } elsif ($ARGV[$i] eq '-help') {
    $showhelp = 1;
  } elsif ($ARGV[$i] eq '--help') {
    $showhelp = 1;
  } elsif ($ARGV[$i] eq '-loop') {
    $loop = 1;
  } elsif ($ARGV[$i] eq '-sampletime') {
    $i++;
    if ($i >= @ARGV) {
      print("Option -sampletime requires a parameter\n");
      $showhelp = 1;
    } else {
      $sampletime = $ARGV[$i];
    }
  } elsif ($ARGV[$i] eq '-lustre') {
    $i++;
    if ($i >= @ARGV) {
      print("Option -lustre requires a parameter\n");
      $showhelp = 1;
    } else {
      $LUSTRESTATS = $ARGV[$i];
    }
  } elsif ($ARGV[$i] eq '-gmetric') {
    $i++;
    if ($i >= @ARGV) {
      print("Option -gmetric requires a parameter\n");
      $showhelp = 1;
    } else {
      $GMETRIC = $ARGV[$i];
    }
  } elsif ($ARGV[$i] eq '-hpasmcli') {
    $i++;
    if ($i >= @ARGV) {
      print("Option -hpasmcli requires a parameter\n");
      $showhelp = 1;
    } else {
      $HPASMCLI = $ARGV[$i];
    }
  } elsif ($ARGV[$i] eq '-ipmitool') {
    $i++;
    if ($i >= @ARGV) {
      print("Option -ipmitool requires a parameter\n");
      $showhelp = 1;
    } else {
      $IPMITOOL = $ARGV[$i];
    }
  } elsif ($ARGV[$i] eq '-lmsensors') {
    $i++;
    if ($i >= @ARGV) {
      print("Option -lmsensors requires a parameter\n");
      $showhelp = 1;
    } else {
      $LMSENSORS = $ARGV[$i];
    }
  } elsif ($ARGV[$i] eq '-nodehealthcheck') {
    $i++;
    if ($i >= @ARGV) {
      print("Option -nodehealthcheck requires a parameter\n");
      $showhelp = 1;
    } else {
      $NODEHEALTHCHECK = $ARGV[$i];
    }
  } elsif ($ARGV[$i] eq '-ipmisensors') {
    $i++;
    if ($i >= @ARGV) {
      print("Option -ipmisensors requires a parameter\n");
      $showhelp = 1;
    } else {
      $IPMISENSORS = $ARGV[$i];
    }
  } elsif ($ARGV[$i] eq '-iblid') {
    $i++;
    if ($i >= @ARGV) {
      print("Option -iblid requires a parameter\n");
      $showhelp = 1;
    } else {
      $IBLID = $ARGV[$i];
    }
  } elsif ($ARGV[$i] eq '-influxhost') {
    $i++;
    if ($i >= @ARGV) {
      print("Option -influxhost requires a parameter\n");
      $showhelp = 1;
    } else {
      $CURLHOST = $ARGV[$i];
    }
  } elsif ($ARGV[$i] eq '-influxdb') {
    $i++;
    if ($i >= @ARGV) {
      print("Option -influxdb requires a parameter\n");
      $showhelp = 1;
    } else {
      $CURLDB = $ARGV[$i];
    }
  } elsif ($ARGV[$i] eq '-jobfile') {
    $i++;
    if ($i >= @ARGV) {
      print("Option -jobfile requires a parameter\n");
      $showhelp = 1;
    } else {
      $JOBFILE = $ARGV[$i];
    }
  } elsif ($ARGV[$i] eq '-detect') {
    $detectionrun = 1;
    foreach $k (keys(%trytorun)) { $trytorun{$k} = 1; }
  } elsif ($ARGV[$i] =~ m/^-disable-(.*)/) {
    $trytorun{$1} = 0;
  } elsif ($ARGV[$i] =~ m/^-enable-(.*)/) {
    $trytorun{$1} = 1;
  } else {
    print("Unknown option: $ARGV[$i]\n");
    $showhelp = 1;
  }
}
if ($showhelp) {
  print("Syntax: $0 [-sampletime n] [-loop] [-disable-NAME] [-enable-NAME] ...\n");
  print(" -sampletime n          sample data for n seconds (default 60)\n");
  print(" -loop                  go into an endless loop\n");
  print(" -detect                do a dry run, and print the metrics collected\n");
  print(" -disable-NAME          disable a data collection attempt\n");
  print(" -enable-NAME           enable a data collection attempt\n");
  print("                        NAME is one of: hpasmcli, hpcmon, ibstats, ipmitool, ipmitool2,\n");
  print("                                        likwid, lmsensors, lustrestats, nfsdstats,\n");
  print("                                        nodehealthcheck, netstats\n");
  print(" -lustre STATFILE       Location of the Lustre stats file (default: $LUSTRESTATS)\n");
  print(" -gmetric PATH          Location of the gmetric binary (default: $GMETRIC)\n");
  print(" -hpasmcli PATH         Location of the hpasmcli binary (default: $HPASMCLI)\n");
  print(" -ipmitool PATH         Location of the ipmitool binary (default: $IPMITOOL)\n");
  print(" -lmsensors PATH        Location of the lmsensors binary (default: $LMSENSORS)\n");
  print(" -nodehealthcheck PATH  Location of the nodehealthcheck script (default: $NODEHEALTHCHECK)\n");
  print(" -ipmisensors SN,SN     List of IPMI Sensor names for ipmitool2 mode\n");
  print(" -iblid PATH            Location of the file with the IB LID (default: $IBLID)\n");
  print(" -influxhost HOSTNAME   Hostname of host running InfluxDB (default: $CURLHOST)\n");
  print(" -influxdb DBNAME       Name of the database for InfluxDB (default: $CURLDB)\n");
  print(" -jobfile PATH          Filename which contains job and user information (default: $JOBFILE)\n");
  exit(1);
}

while (1) {
  %olddiskstats = %curdiskstats;
  %oldvmstats = %curvmstats;
  %oldgenstats = %curgenstats;
  %oldnfsdstats = %curnfsdstats;
  %oldlustrestats = %curlustrestats;
  %oldnetstats = %curnetstats;
  %oldcpustats = %curcpustats;
  if (!$firstloop) {
    my $sincelastsamp = time() - $lastsample;
    my $slptime = ($sincelastsamp >= $sampletime) ? 1 : ($sampletime - $sincelastsamp);
    print("Need to sleep for $slptime more seconds...\n");
    sleep($slptime);
  }
  $lastsample = time();
  if ($trytorun{'diskstats'}) {
    %curdiskstats = getdiskstats();
  } else {
    %curdiskstats = ();
  }
  if ($trytorun{'netstats'}) {
    %curnetstats = getnetstats();
  } else {
    %curnetstats = ();
  }
  if ($trytorun{'memstats'}) {
    %curmemstats = getmemstats();
  } else {
    %curmemstats = ();
  }
  if ($trytorun{'vmstats'}) {
    %curvmstats = getvmstats();
  } else {
    %curvmstats = ();
  }
  %curgenstats = getgenstats();
  if ($trytorun{'nfsdstats'}) {
    %curnfsdstats = getnfsdstats();
  } else {
    %curnfsdstats = ();
  }
  if ($trytorun{'lustrestats'}) {
    %curlustrestats = getlustrestats();
  } else {
    %curlustrestats = ();
  }
  if ($trytorun{'loadstats'}) {
    %curloadstats = getloadstats();
  } else {
    %curloadstats = ();
  }
  if ($trytorun{'cpustats'}) {
    %curcpustats = getcpustats();
  } else {
    %curcpustats = ();
  }
  if ($trytorun{'ibstats'}) {
    %curibstats = getibstats();
  } else {
    %curibstats = ();
  }
  if ($firstloop) {
    $firstloop = 0;
  } else {
    # These don't need to compare to previous value
    $curnopenfds = getnumopenfds();
    if ($trytorun{'pperfctrs'}) {
      %curperfcounters = getperfcounters();
    } else {
      %curperfcounters = ();
    }
    if ($trytorun{'hpasmcli'}) {
      %curhpasmcli = gethpasmcli();
    } else {
      %curhpasmcli = ();
    }
    if ($trytorun{'ipmitool'}) {
      %curipmisensor = getipmisensor();
    } else {
      %curipmisensor = ();
    }
    if ($trytorun{'ipmitool2'}) {
      %curipmisensor2 = getipmisensor2();
    } else {
      %curipmisensor2 = ();
    }
    if ($trytorun{'lmsensors'}) {
      %curlmsensors = getlmsensors();
    } else {
      %curlmsensors = ();
    }
    if ($trytorun{'nodehealthcheck'}) {
      %curnodehealthcheck = getnodehealthcheck();
    } else {
      %curnodehealthcheck = ();
    }
    if ($trytorun{'hpcmon'}) {
      %curhpcmon = gethpcmon();
    } else {
      %curhpcmon = ();
    }
    if ($trytorun{'likwid'}) {
      %curlikwid = getlikwid();
    } else {
      %curlikwid = ();
    }
    # Calculate difference
    foreach $k (keys(%curdiskstats)) {
      if (defined($olddiskstats{$k})) {
        if (not ( $k =~ /loop\d+/ or $k =~ /sd[a-z]\d+/))
        {
          my $dif1 = $curdiskstats{$k}->[0] - $olddiskstats{$k}->[0];
          if ($dif1 >= 0) {
            callgmetric('disk_'.$k.'_read', 'double', $dif1 / ($sampletime.'.0'), 'sectors/s');
          }
          my $dif2 = $curdiskstats{$k}->[1] - $olddiskstats{$k}->[1];
          if ($dif2 >= 0) {
            callgmetric('disk_'.$k.'_write', 'double', $dif2 / ($sampletime.'.0'), 'sectors/s');
          }
          if ($curdiskstats{$k}->[2] >= 0) {
            callgmetric('disk_'.$k.'_queue', 'uint32', $curdiskstats{$k}->[2], 'requests');
          }
        }
      }
    }
    my @vnames; my @vgname; my @vunit;
    @vnames = ('pswpin', 'pswpout');
    @vgname = ('swap_in', 'swap_out');
    @vunit = ('pages/sec', 'pages/sec');
    for ($j = 0; $j < @vnames; $j++) {
      $k = $vnames[$j];
      unless (defined($oldvmstats{$k})) { next; }
      unless (defined($curvmstats{$k})) { next; }
      my $dif = $curvmstats{$k} - $oldvmstats{$k};
      if ($dif >= 0) {
        callgmetric('vmstats_'.$vgname[$j], 'double', $dif / ($sampletime.'.0'), $vunit[$j]);
      }
    }
    @vnames = ('intr', 'processes');
    @vgname = ('interrupts', 'newthreads');
    @vunit = ('ints/sec', 'threads/sec');
    for ($j = 0; $j < @vnames; $j++) {
      $k = $vnames[$j];
      unless (defined($oldgenstats{$k})) { next; }
      unless (defined($curgenstats{$k})) { next; }
      my $dif = $curgenstats{$k} - $oldgenstats{$k};
      if ($dif >= 0) {
        callgmetric('genstats_'.$vgname[$j], 'double', $dif / ($sampletime.'.0'), $vunit[$j]);
      }
    }
    foreach $k (keys(%curnfsdstats)) {
      if (defined($oldnfsdstats{$k})) {
        my $dif1 = $curnfsdstats{$k} - $oldnfsdstats{$k};
        if ($dif1 >= 0) {
          callgmetric('nfsd_'.$k, 'double', $dif1 / ($sampletime.'.0'), 'requests/s');
        }
      }
    }
    foreach $k (keys(%curcpustats)) {
      if (defined($oldcpustats{$k})) {
        my $dif1 = $curcpustats{$k} - $oldcpustats{$k};
        if ($dif1 >= 0) {
          callgmetric($k, 'double', $dif1);
        }
      }
    }
    foreach $k (keys(%curnetstats)) {
      if (defined($oldnetstats{$k})) {
        my $dif1 = $curnetstats{$k} - $oldnetstats{$k};
        if ($dif1 >= 0) {
          callgmetric('net_'.$k, 'double', $dif1 / ($sampletime.'.0'), 'bytes/s');
        }
      }
    }
    foreach $k (keys(%curlustrestats)) {
      if (defined($oldlustrestats{$k})) {
        my $dif1 = $curlustrestats{$k} - $oldlustrestats{$k};
        if ($dif1 >= 0) {
            if ( $k =~ m/read_bytes|write_bytes/ ) {
                callgmetric('lustre_'.$k, 'double', $dif1 / ($sampletime.'.0'), 'bytes/s');
            } else {
                callgmetric('lustre_'.$k, 'double', $dif1 / ($sampletime.'.0'), 'requests/s');
            }
        }
      }
    }
    foreach $k (keys(%curibstats)) {
      if (defined($curibstats{$k})) {
        callgmetric('ib_'.$k, 'double', $curibstats{$k} / ($sampletime.'.0'), 'bytes/s');
      }
    }
    if ($curnopenfds > 0) {
      callgmetric('openfds', 'uint32', $curnopenfds);
    }
    foreach $k (keys(%curhpasmcli)) {
      callgmetric('temp_'.$k, 'float', $curhpasmcli{$k}, "degC");
    }
    foreach $k (keys(%curipmisensor)) {
      if      ($curipmisensor{$k}->[1] eq 'volts') {
        callgmetric('voltage_'.$k, 'float', $curipmisensor{$k}->[0], "volts");
      } elsif ($curipmisensor{$k}->[1] eq 'rpm') {
        callgmetric('fan_'.$k, 'float', $curipmisensor{$k}->[0], "RPM");
      } elsif ($curipmisensor{$k}->[1] eq 'degreesc') {
        callgmetric('temp_'.$k, 'float', $curipmisensor{$k}->[0], "degC");
      } elsif ($curipmisensor{$k}->[1] eq 'watts') {
        callgmetric('power_'.$k, 'float', $curipmisensor{$k}->[0], "watts");
      }
    }
    foreach $k (keys(%curipmisensor2)) {
      if      ($curipmisensor2{$k}->[1] eq 'volts') {
        callgmetric('voltage_'.$k, 'float', $curipmisensor2{$k}->[0], "volts");
      } elsif ($curipmisensor2{$k}->[1] eq 'rpm') {
        callgmetric('fan_'.$k, 'float', $curipmisensor2{$k}->[0], "RPM");
      } elsif ($curipmisensor2{$k}->[1] eq 'degreesc') {
        callgmetric('temp_'.$k, 'float', $curipmisensor2{$k}->[0], "degC");
      } elsif ($curipmisensor2{$k}->[1] eq 'watts') {
        callgmetric('power_'.$k, 'float', $curipmisensor2{$k}->[0], "watts");
      }
    }
    foreach $k (keys(%curlmsensors)) {
      if      ($curlmsensors{$k}->[1] eq 'v') {
        callgmetric('voltage_'.$k, 'float', $curlmsensors{$k}->[0], "volts");
      } elsif ($curlmsensors{$k}->[1] eq 'rpm') {
        callgmetric('fan_'.$k, 'float', $curlmsensors{$k}->[0], "RPM");
      } elsif ($curlmsensors{$k}->[1] eq 'c') {
        callgmetric('temp_'.$k, 'float', $curlmsensors{$k}->[0], "degC");
      }
    }
    foreach $k (keys(%curperfcounters)) {
      callgmetric($k, 'double', $curperfcounters{$k});
    }
    foreach $k (keys(%curnodehealthcheck)) {
      callgmetric($k, 'uint32', $curnodehealthcheck{$k});
    }
    foreach $k (keys(%curhpcmon)) {
      callgmetric($k, 'double', $curhpcmon{$k});
    }
    foreach $k (keys(%curloadstats)) {
      callgmetric($k, 'double', $curloadstats{$k});
    }
    foreach $k (keys(%curlikwid)) {
      callgmetric($k, 'double', $curlikwid{$k});
    }
    @vnames = ('MemTotal', 'MemFree', 'MemAvailable');
    @vgname = ('mem_total', 'mem_free', 'mem_available');
    @vunit = ('kByte', 'kByte', 'kByte');
    for ($j = 0; $j < @vnames; $j++) {
      $k = $vnames[$j];
      unless (defined($curmemstats{$k})) { next; }
      callgmetric($k, 'uint32', $curmemstats{$k});
    }
    callcurl();
    if ($detectionrun) {
      print("The following list shows the recommended parameters, based on which\n");
      print("commands successfully collected data:\n");
      printf(" -%s-vmstats", ((int(keys(%curvmstats)) > 0) ? "enable" : "disable"));
      printf(" -%s-diskstats", ((int(keys(%curdiskstats)) > 0) ? "enable" : "disable"));
      printf(" -%s-hpasmcli", ((int(keys(%curhpasmcli)) > 0) ? "enable" : "disable"));
      printf(" -%s-hpcmon", ((int(keys(%curhpcmon)) > 0) ? "enable" : "disable"));
      printf(" -%s-likwid", ((int(keys(%curlikwid)) > 0) ? "enable" : "disable"));
      printf(" -%s-ipmitool", ((int(keys(%curipmisensor)) > 0) ? "enable" : "disable"));
      printf(" -%s-ipmitool2", ((int(keys(%curipmisensor2)) > 0) ? "enable" : "disable"));
      printf(" -%s-lmsensors", ((int(keys(%curlmsensors)) > 0) ? "enable" : "disable"));
      printf(" -%s-pperfctrs", ((int(keys(%curperfcounters)) > 0) ? "enable" : "disable"));
      printf(" -%s-nfsdstats", ((int(keys(%curnfsdstats)) > 0) ? "enable" : "disable"));
      printf(" -%s-lustrestats", ((int(keys(%curlustrestats)) > 0) ? "enable" : "disable"));
      printf(" -%s-nodehealthcheck", ((int(keys(%curnodehealthcheck)) > 0) ? "enable" : "disable"));
      printf(" -%s-netstats", ((int(keys(%curnetstats)) > 0) ? "enable" : "disable"));
      printf(" -%s-memstats", ((int(keys(%curmemstats)) > 0) ? "enable" : "disable"));
      printf(" -%s-cpustats", ((int(keys(%curcpustats)) > 0) ? "enable" : "disable"));
      printf(" -%s-loadstats", ((int(keys(%curloadstats)) > 0) ? "enable" : "disable"));
      print("\n");
      exit(0);
    }
    if (!$loop) {
      exit(0);
    }
  }
}

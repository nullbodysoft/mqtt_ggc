#!/usr/bin/python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

# TODO:
#  periordic update  calibrate information, update calibrate on start ?
#  send probe enable data

SW_VER = 20160229
# 2016-02-03: allow switch_main_h to be float between 0.2 - 23, allow air_control to switch air down to 12 minute
# 2016-02-04: allow ct_phase set to 0 for current-only probe
# 2016-02-15: Unload USB serial module when no input data
# 2016-02-15: DHT22 Reset
# 2016-02-17: Check value from DS18B20 before publish
# 2016-02-18: Check value from UPS before publish

from time import gmtime,strftime
import time
import serial
import struct
import shutil
import os
import subprocess
import syslog
import sys, traceback
from subprocess import Popen
from sys import platform as _platform
import paho.mqtt.client as mqtt
sys.path.insert(0, '/usr/lib/python2.7/bridge/')
from bridgeclient import BridgeClient as bridgeclient

# bridge config vaiable
#
# NUM_OW_ENABLE : (ow) : nuber of onewire enable port    default: 5
# DHT_ENABLE : (dh) : enable/disable dht22               default: 1
# TEMP_LOOP_TIME : (li) : seconds run for each loop      default: 15
#
NUM_OW_ENABLE = 5
DHT_ENABLE = 1
TEMP_LOOP_TIME = 15

mqtt_client_name='' # '' = get from '/root/mqtt/MAC'  default: 'Yun-notcon
base_topic = ''     # '' = get from '/root/mqtt/MQTT_BASE_TOPIC'  default: 'no
device_type = ''    # '' = get from '/root/mqtt/DEVICE_TYPE'  default: 'EnvMon
mqtt_host=''        # '' = get from '/root/mqtt/MQTT_HOST'  default: '100.64.2.1

#mqtt_client_name='Yun-lab-test'
#base_topic = 'devel/lab-test'
#device_type = 'EnvMonCtrl1'
#mqtt_host='100.64.2.1'

mqtt_port=1883
mqtt_timeout=15
mqtt_user=''
mqtt_pass=''
mqtt_LWT_retained=True


SITE_ID = 99
DEVICE_ID = 'mega1'

DEBUG_SERIAL = 0        # log to syslog
DEBUG_SERIAL2 = 0       # log to stdout
SYSLOG_REPORT = 0       # log V, I, P to syslog

CYGWIN_SERIAL = '/dev/ttyS5'
DEBUG_LOG_SIZE = 10240

DS_OFFSET=10

NUM_AIR=10

aircmd2status = {'011':'1','110':'2','100':'2','000':'3','010':'4'}
airstatusname = {'1':'AIR_ON','2':'AIR_OFF','3':'AIR_BYPASS','4':'AIR_FAN_ONLY'}
# AIR_ON:       1 011
# AIR_OFF:      2 110, 100
# AIR_BYPASS:   3 000
# AIR_FAN_ONLY: 4 010

CONF_DIR='/root/mqtt/calibrate/'
TEMP_DIR='/tmp/'
FILE_CT=CONF_DIR + 'ct.txt'
FILE_CT_PHASE=CONF_DIR + 'ct_phase.txt'
FILE_V_CAL=CONF_DIR + 'v_cal.txt'
FILE_V_PHASECAL=CONF_DIR + 'v_phasecal.txt'
FILE_V_PHASECOEF=CONF_DIR + 'v_phasecoef.txt'
FILE_PROBE_EN=CONF_DIR + 'probe_enable.txt'
FILE_IRMS_NSAM=CONF_DIR + 'irms_nsam.txt'
FILE_CALCVI_CRTO=CONF_DIR + 'calcvi_crto.txt'
FILE_READ_TO=CONF_DIR + 'read_timeout.txt'
FILE_AIR_PHASE=CONF_DIR + 'air_phase.txt'
FILE_AIR_VLOW=CONF_DIR + 'air_vlow.txt'
TIME_CT=0
TIME_CT_PHASE=0
TIME_V_CAL=0
TIME_V_PHASECAL=0
TIME_V_PHASECOEF=0
TIME_PROBE_EN=0
TIME_IRMS_NSAM=0
TIME_CALCVI_CRTO=0
TIME_READ_TO=0
TIME_AIR_PHASE=0
TIME_AIR_VLOW=0

FILE_UPDATE=TEMP_DIR + 'have_update'
TIME_UPDATE=0

TEMP_FILE_TMP = TEMP_DIR + '.temp'
TEMP_DATA_FILE = TEMP_DIR + 'temp_data.txt'
AIR_FILE_TMP = TEMP_DIR + '.air'
AIR_DATA_FILE = TEMP_DIR + 'air_data.txt'
RUN_FILE = TEMP_DIR + 'serial.run'

need_calibrate=0
can_calibrate=1

def get_config_from_file(filename,defaultvalue,prefix):
    try:
        f = open(filename,'r')
        data = f.readline().strip(' \t\n\r')
        f.close()
    except:
        data = defaultvalue
    data = str(prefix) + str(data)
    debug_txt = "get_config_from_file %s %s" % (filename, data)
    syslog.syslog(debug_txt)
    print(debug_txt)
    return data

def cal_checksum(data):
    data.strip()
    calc_csum = 0
    for s in data:
        calc_csum ^= ord(s)
    return "%02X" % calc_csum

def get_ct_ical():
    global TIME_CT
    try:
        fn = FILE_CT
        f1 = open(FILE_CT,'r')
        lines = f1.readline().strip(' \t\n\r')
        f1.close()
        ct=lines.split(',')
        if len(ct) <1 or len(ct)> 13:
            print "ct.txt error: require 1-13 values :"+lines
            return ""
        for i in range(0,len(ct)):
            if ct[i].replace('.','',1).isdigit() != True:
                print "ct_ical Error: accept only numeric value :"+lines
                return ""
        lines = "ct_ical,"+lines
        TIME_CT=os.path.getmtime(FILE_CT)
        #print "TIME_CT: %f" % TIME_CT
        return "$%s*%s" % (lines,cal_checksum(lines))
    except IOError as e:
        print("I/O error({0}): {2} {1}".format(e.errno, e.strerror, fn))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
    except:
        print "get_ct_ical() error"
        return ""

def get_ct_phase():
    global TIME_CT_PHASE
    try:
        fn = FILE_CT_PHASE
        f1 = open(FILE_CT_PHASE,'r')
        lines = f1.readline().strip(' \t\n\r')
        f1.close()
        ct=lines.split(',')
        if len(ct) < 1 or len(ct) > 13:
            print "ct_phase.txt error: require 1-13 values :"+lines
            return ""
        for i in range(0,len(ct)):
            if ct[i].replace('.','',1).isdigit() != True:
                print "ct_phase.txt error: accept only 0,1,2,3 :"+lines
                return ""
            if ct[i]!="0" and ct[i]!="1" and ct[i]!="2" and ct[i]!="3":
                print "ct_phase.txt error: accept only 0,1,2,3 :"+lines
                return ""
        lines = "ct_phase,"+lines
        TIME_CT_PHASE=os.path.getmtime(FILE_CT_PHASE)
        #print "TIME_CT_PHASE: %f" % TIME_CT_PHASE
        return "$%s*%s" % (lines,cal_checksum(lines))
    except IOError as e:
        print("I/O error({0}): {2} {1}".format(e.errno, e.strerror, fn))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
    except:
        print "get_ct_phase() error"
        return ""

def get_v_cal():
    global TIME_V_CAL
    try:
        fn = FILE_V_CAL
        f1 = open(FILE_V_CAL,'r')
        lines = f1.readline().strip(' \t\n\r')
        f1.close()
        ct=lines.split(',')
        if len(ct) != 3:
            print "v_cal.txt error: require 3 values :"+lines
            return ""
        for i in range(0,3):
            if ct[i].replace('.','',1).isdigit() != True:
                print "v_cal Error: accept only numeric value :"+lines
                return ""
        lines = "v_cal,"+lines
        TIME_V_CAL=os.path.getmtime(FILE_V_CAL)
        #print "TIME_V_CAL: %f" % TIME_V_CAL
        return "$%s*%s" % (lines,cal_checksum(lines))
    except IOError as e:
        print("I/O error({0}): {2} {1}".format(e.errno, e.strerror, fn))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
    except:
        print "get_v_cal() error"
        return ""

def get_v_phasecal():
    global TIME_V_PHASECAL
    try:
        fn = FILE_V_PHASECAL
        f1 = open(FILE_V_PHASECAL,'r')
        lines = f1.readline().strip(' \t\n\r')
        f1.close()
        ct=lines.split(',')
        if len(ct) < 1 or len(ct) >13:
            print "v_phasecal.txt error: require 1-13 values :"+lines
            return ""
        for i in range(0,len(ct)):
            if ct[i].replace('.','',1).isdigit() != True:
                print "v_phasecal Error: accept only numeric value :"+lines
                return ""
            if float(ct[i]) < 1 or float(ct[i]) >1.8:
                print "v_phasecal Error: accept only 1.0 to 1.8 :"+lines
        lines = "v_phasecal,"+lines
        TIME_V_PHASECAL=os.path.getmtime(FILE_V_PHASECAL)
        return "$%s*%s" % (lines,cal_checksum(lines))
    except IOError as e:
        print("I/O error({0}): {2} {1}".format(e.errno, e.strerror, fn))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
    except:
        print "get_v_phasecal() error"
        return ""

def get_v_phasecoef():
    global TIME_V_PHASECOEF
    try:
        fn = FILE_V_PHASECOEF
        f1 = open(FILE_V_PHASECOEF,'r')
        lines = f1.readline().strip(' \t\n\r')
        f1.close()
        ct=lines.split(',')
        if len(ct) <1 or len(ct) >13:
            print "v_phasecoef.txt error: require 1-13 values :"+lines
            return ""
        for i in range(0,len(ct)):
            if ct[i].replace('.','',1).isdigit() != True:
                print "v_phasecoef Error: accept only numeric value :"+lines
                return ""
        lines = "v_phasecoef,"+lines
        TIME_V_PHASECOEF=os.path.getmtime(FILE_V_PHASECOEF)
        return "$%s*%s" % (lines,cal_checksum(lines))
    except IOError as e:
        print("I/O error({0}): {2} {1}".format(e.errno, e.strerror, fn))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
    except:
        print "get_v_phasecoef() error"
        return ""

def get_probe_en():
    global TIME_PROBE_EN
    try:
        fn = FILE_PROBE_EN
        f1 = open(FILE_PROBE_EN,'r')
        lines = f1.readline().strip(' \t\n\r')
        f1.close()
        probe_en=lines.split(',')
        if probe_en[0].isdigit() != True:
            print "probe_en Error: require numeric number of I probe:"+lines
            return ""
        if int(probe_en[0]) < 0 or int(probe_en[0]) > 13:
            print "probe_en Error: invalid number of I probe:"+lines
            return ""
        if len(probe_en[1]) != int(probe_en[0]):
            print "probe_en Error: I probe data error:"+lines
            return ""
        if len(probe_en[2]) != 3:
            print "probe_en Error: V probe data error:"+lines
            return ""
        if len(probe_en[3]) != 2:
            print "probe_en Error: T,H probe data error:"+lines
            return ""
        lines = "probe_con,"+lines
        TIME_PROBE_EN=os.path.getmtime(FILE_PROBE_EN)
        return "$%s*%s" % (lines,cal_checksum(lines))
    except IOError as e:
        print("I/O error({0}): {2} {1}".format(e.errno, e.strerror, fn))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
    except:
        print "get_probe_en() error"
        return ""
        
def get_irms_nsam():
    global TIME_IRMS_NSAM
    try:
        fn = FILE_IRMS_NSAM
        f1 = open(FILE_IRMS_NSAM,'r')
        lines = f1.readline().strip(' \t\n\r')
        f1.close()
        if lines.isdigit() != True:
            print "irms_nsam Error: accept only numeric value:"+lines
            return ""
        if int(lines) < 50 or int(lines) > 4000:
            print "irms_nsam Error: accept only numeric value between 50 - 4000:"+lines
            return ""
        lines = "irms_nsam,"+lines
        TIME_IRMS_NSAM=os.path.getmtime(FILE_IRMS_NSAM)
        return "$%s*%s" % (lines,cal_checksum(lines))
    except IOError as e:
        print("I/O error({0}): {2} {1}".format(e.errno, e.strerror, fn))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
    except:
        print "get_irms_nsam() error"
        return ""

def get_calcvi_crto():
    global TIME_CALCVI_CRTO
    try:
        fn = FILE_CALCVI_CRTO
        f1 = open(FILE_CALCVI_CRTO,'r')
        lines = f1.readline().strip(' \t\n\r')
        f1.close()
        crto=lines.split(',')
        if len(crto) != 2:
            print "calcvito_crto.txt error: require 2 values :"+lines
            return ""
        for i in range(0,2):
            if crto[i].replace('.','',1).isdigit() != True:
                print "calcvito_crto.txt Error: accept only numeric value :"+lines
                return ""
        lines = "calvi_crto,"+lines
        TIME_CALCVI_CRTO=os.path.getmtime(FILE_CALCVI_CRTO)
        return "$%s*%s" % (lines,cal_checksum(lines))
    except IOError as e:
        print("I/O error({0}): {2} {1}".format(e.errno, e.strerror, fn))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
    except:
        print "get_calcvi_crto() error"
        return ""

def get_read_to():
    global TIME_READ_TO
    try:
        fn = FILE_READ_TO
        f1 = open(FILE_READ_TO,'r')
        lines = f1.readline().strip(' \t\n\r')
        f1.close()
        if lines.isdigit() != True:
            print "read_timeout Error: accept only numeric value:"+lines
            return ""
        if int(lines) < 1000 or int(lines) > 60000:
            print "read_timeout Error: accept only numeric value between 1000 - 60000:"+lines
            return ""
        lines = "read_timeout,"+lines
        TIME_READ_TO=os.path.getmtime(FILE_READ_TO)
        return "$%s*%s" % (lines,cal_checksum(lines))
    except IOError as e:
        print("I/O error({0}): {2} {1}".format(e.errno, e.strerror, fn))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
    except:
        print "get_read_to() error"
        return ""    

def get_air_phase():
    global TIME_AIR_PHASE
    try:
        fn = FILE_AIR_PHASE
        f1 = open(FILE_AIR_PHASE,'r')
        lines = f1.readline().strip(' \t\n\r')
        f1.close()
        airp=lines.split(',')
        if len(airp) < 1 or len(airp) > 10:
            print "air_phase.txt error: require 1-10 values :"+lines
            return ""
        for i in range(0,len(airp)):
            if airp[i].replace('.','',1).isdigit() != True:
                print "air_phase.txt error: 1 accept only 0,1,2,3 :"+lines
                return ""
            if airp[i]!="0" and airp[i]!="1" and airp[i]!="2" and airp[i]!="3":
                print "air_phase.txt error: 2 accept only 0,1,2,3 :"+lines
                return ""
        lines = "air_phase,"+lines
        TIME_AIR_PHASE=os.path.getmtime(FILE_AIR_PHASE)
        #print "TIME_AIR_PHASE: %f" % TIME_AIR_PHASE
        return "$%s*%s" % (lines,cal_checksum(lines))
    except IOError as e:
        print("I/O error({0}): {2} {1}".format(e.errno, e.strerror, fn))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
    except:
        print "get_air_phase() error"
        return ""

def get_air_vlow_threshold():
    global TIME_AIR_VLOW
    try:
        fn = FILE_AIR_VLOW
        f1 = open(FILE_AIR_VLOW,'r')
        lines = f1.readline().strip(' \t\n\r')
        f1.close()
        airv=lines.split(',')
        if len(airv) !=4:
            print "air_vlow.txt error: require 4 values :"+lines
            return ""
        for i in range(0,4):
            if airv[i].isdigit() != True:
                print "air_phase.txt error: accept only integer value :"+lines
                return ""
        lines = "air_vlow_threshold,"+lines
        TIME_AIR_VLOW=os.path.getmtime(FILE_AIR_VLOW)
        #print "TIME_AIR_VLOW: %f" % TIME_AIR_VLOW
        return "$%s*%s" % (lines,cal_checksum(lines))
    except IOError as e:
        print("I/O error({0}): {2} {1}".format(e.errno, e.strerror, fn))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
    except:
        print "get_air_vlow_threshold() error"
        return ""

def send_air_cmd(buff):
    i=len(buff)
    i=i/3
    lines = "air_cmd,%d,%s" % (i,buff)
    cmd = "$%s*%s" % (lines,cal_checksum(lines))
    ser.write(cmd +'\n')
    d_log.write(time.strftime("%Y-%m-%d %H:%M:%S") +' < ' +cmd +'\n')
    d_log.flush()
    if DEBUG_SERIAL:
        syslog.syslog('write: ' +cmd +'\n')
    if DEBUG_SERIAL2:
        print('write: ' +cmd);
    time.sleep(10/1000)

def getairconfig(cfg):
    cfgfile=""
    if cfg=="airmode":
        cfgfile=TEMP_DIR + "auto_from_server.txt"
    elif cfg=="airgroup":
        cfgfile=TEMP_DIR + "air_group.txt"
    elif cfg=="airdata":
        cfgfile=TEMP_DIR + "data_from_server.txt"
    if cfgfile!="":
        try:
            txt=open(cfgfile)
            data=txt.read()
            data=data.strip(' \t\n\r')
            txt.close()
        except:
            data=""
        if cfg=="airgroup":
            data=data.replace('\n','|')
    elif cfg=="airschedule":
        data=""
        for i in range(0,7):
            try:
                txt=open(TEMP_DIR +"air_schedule_" +str(i) +".txt")
                stxt=txt.read().strip(' \t\n\r')
                txt.close()
            except:
                stxt=""
            data = data +str(i) +":"
            s=stxt.split('\n')
            for i in range(0,len(s)):
                data=data+s[i].strip(' \t\n\r')
                if i < (len(s)-1):
                    data = data +","
            data=data+"|"
    return cfg+"|"+data.strip(' \t\n\r|')

def setairconfig(kv):
    k=kv[0]
    filename=""
    data=""
    if k=="setairmode":
        try:
            v=int(kv[1])
            if v>=0 and v<=2:
                data=str(v)
            else:
                return "failed: invalid value"
        except:
            return "failed: exception error"
        filename=TEMP_DIR +"auto_from_server.txt";
    elif k=="setairdata":
        try:
            v=kv[1]
            data = v
        except:
            return "failed: exception error"
        # check data
        if len(v)>0 and len(v) <= NUM_AIR:
            for i in range(0,len(v)):
                if v[i]!="0" and v[i]!="1" and v[i]!="2" and v[i]!="3" and v[i]!="4":
                    return "failed: invalid air state"
        else:
            return "failed: invalid air count"
        filename=TEMP_DIR +"data_from_server.txt";
    elif k=="setairschedule":
        report=""
        for i in range(0,len(kv)):
            if i==0:
                continue
            s_id=-1
            s_data=""
            v=kv[i]
            s_buff=v.split(":")
            if len(s_buff)==2:
                try:
                    s_id=int(s_buff[0])
                    s_data=s_buff[1]
                except:
                    s_id=-1
            #print "sch" +str(s_id) +": " +s_data
            s_data_l=s_data.split(",")
            dataOk=1
            data=""
            for d in range(0,len(s_data_l)):
                s_data_buff=s_data_l[d].strip(' \t\n\r')
                if len(s_data_buff)!=24:
                    dataOk=0
                else:
                    for d2 in range(0,24):
                        if s_data_buff[d2]!="0" and s_data_buff[d2]!="1" and s_data_buff[d2]!="2" and s_data_buff[d2]!="3" and s_data_buff[d2]!="4":
                            dataOk=0
                if dataOk:
                    data=data + s_data_buff + "\n"
                    #print "    " + s_data_buff
            if dataOk and savefile(TEMP_DIR +"air_schedule_" +str(s_id) +".txt",data):
                report=report+"success:" +str(s_id) +" "
            else:
                report=report+"failed:" +str(s_id) +" "
        return report;
    elif k=="setairgroup":
        report=""
        g_ok=1
        g_data=""
        for g_id in range(0,len(kv)):
            if g_id==0:
                continue
            v=kv[g_id].strip(' \t\n\r')
            s_buff=v.split(";")
            g_data_item_chk=0
            air_list_count=0
            num_main=0
            temp_cond1=0.0
            temp_cond2=0.0
            for d in range(0,len(s_buff)):
                g_data_item=s_buff[d].strip(' \t\n\r')
                g_data_item_kv=g_data_item.split("=")
                if len(g_data_item_kv)!=2:
                    g_data_item_chk=g_data_item_chk+64
                    debug_txt = "setairgroup: error "+g_data_item
                    syslog.syslog(debug_txt)
                    if DEBUG_SERIAL2: print(debug_txt)
                    break
                # check group data item
                if g_data_item_kv[0]=="air_list":
                    item_v=g_data_item_kv[1].split(",")
                    for air_id in range(0,len(item_v)):
                        air_str=item_v[air_id].strip(' \t\n\r')
                        try:
                            air=int(air_str)
                        except:
                            air=-1
                        if air < 1 or air > NUM_AIR:
                            g_ok=0
                            report=report+"failed:"+str(g_id)+" "
                            debug_txt = "setairgroup: error "+g_data_item
                            syslog.syslog(debug_txt)
                            if DEBUG_SERIAL2: print(debug_txt)
                            break
                        air_list_count=air_list_count+1
                    g_data_item_chk=g_data_item_chk+1
                elif g_data_item_kv[0]=="num_main":
                    try:
                        num_main=int(g_data_item_kv[1])
                    except:
                        num_main=-1
                    if num_main < 0 or num_main > NUM_AIR:
                        g_ok=0
                        report=report+"failed:"+str(g_id)+" "
                        debug_txt = "setairgroup: error "+g_data_item
                        syslog.syslog(debug_txt)
                        if DEBUG_SERIAL2: print(debug_txt)
                        break
                    g_data_item_chk=g_data_item_chk+2
                elif g_data_item_kv[0]=="switch_main_h":
                    try:
                        i=float(g_data_item_kv[1])
                    except:
                        i=-1
                    if i < 0.2 or i > 24:
                        g_ok=0
                        report=report+"failed:"+str(g_id)+ " "
                        debug_txt = "setairgroup: error "+g_data_item
                        syslog.syslog(debug_txt)
                        if DEBUG_SERIAL2: print(debug_txt)
                        break
                    g_data_item_chk=g_data_item_chk+4
                elif g_data_item_kv[0]=="temp_cond1":
                    try:
                        temp_cond1=float(g_data_item_kv[1])
                    except:
                        g_ok=0
                        report=report+"failed:"+str(g_id)+ " "
                        debug_txt = "setairgroup: error "+g_data_item
                        syslog.syslog(debug_txt)
                        if DEBUG_SERIAL2: print(debug_txt)
                        break
                    g_data_item_chk=g_data_item_chk+8
                elif g_data_item_kv[0]=="temp_cond2":
                    try:
                        temp_cond2=float(g_data_item_kv[1])
                    except:
                        g_ok=0
                        report=report+"failed:"+str(g_id)+ " "
                        debug_txt = "setairgroup: error "+g_data_item
                        syslog.syslog(debug_txt)
                        if DEBUG_SERIAL2: print(debug_txt)
                        break
                    g_data_item_chk=g_data_item_chk+16
                elif g_data_item_kv[0]=="temp_sensors":
                    sensor_list = g_data_item_kv[1].split(",")
                    sensor_ok=1
                    for i in range(0,len(sensor_list)):
                        if len(sensor_list[i].strip(' \t\n\r'))!=16:
                            sensor_ok=0
                            break
                    if sensor_ok==0:
                        g_ok=0
                        report=report+"failed:"+str(g_id)+ " "
                        debug_txt = "setairgroup: error "+g_data_item
                        syslog.syslog(debug_txt)
                        if DEBUG_SERIAL2: print(debug_txt)
                        break
                    g_data_item_chk=g_data_item_chk+32
                elif g_data_item_kv[0]=="min_backup_time_m":
                    try:
                        i=int(g_data_item_kv[1])
                    except:
                        i=-1
                    if i<1 or i > 60:
                        g_ok=0
                        report=report+"failed:"+str(g_id)+ " "
                        debug_txt = "setairgroup: error "+g_data_item+ " (1-60)"
                        syslog.syslog(debug_txt)
                        if DEBUG_SERIAL2: print(debug_txt)
                        break
                else:
                    debug_txt = "setairgroup: unknown items " +g_data_item
                    syslog.syslog(debug_txt)
                    if DEBUG_SERIAL2: print(debug_txt)
                #print g_data_item_kv[0] + " " + g_data_item_kv[1]
            if g_data_item_chk!=63:
                report=report+"failed:"+str(g_id)+" "
                debug_txt = "setairgroup: error not enough data item"
                syslog.syslog(debug_txt)
                if DEBUG_SERIAL2: print(debug_txt)
                g_ok=0
            elif temp_cond1 >= temp_cond2:
                report=report+"failed:"+str(g_id)+" "
                print "setairgroup: error temp_cond"
                syslog.syslog(debug_txt)
                if DEBUG_SERIAL2: print(debug_txt)
                g_ok=0
            elif num_main > air_list_count:
                report=report+"failed:"+str(g_id)+" "
                debug_txt = "setairgroup: error num_main"
                syslog.syslog(debug_txt)
                if DEBUG_SERIAL2: print(debug_txt)
                g_ok=0
            else:
                g_data=g_data +v +"\n"
        if g_ok==1:
            data = g_data
            filename=TEMP_DIR +"air_group.txt";
            report="success"

    if filename != "":
        if savefile(filename,data):
            return "success"
        else:
            return "failed: cannot save config file"
    return "failed: unknown config"

def savefile(f,v):
    try:
        #print "open " +f +".new"
        fd = open(f +".new","w")
        #print "write"
        fd.write(str(v))
        #print "close"
        fd.close()
        if os.path.isfile(f +".old"):
            #print "remove .old"
            os.remove(f +".old")
        if os.path.isfile(f):
            #print "rename to .old"
            os.rename(f, f +".old")
        #print "rename .new to " +f
        os.rename(f +".new", f)
    except:
        return False
    return True

def on_connect(client, userdata, flags, rc):
    global conn_error
    debug_txt =  "Connection returned result: "+str(rc)
    syslog.syslog(debug_txt)
    if DEBUG_SERIAL2: print(debug_txt)
    if rc ==0:
        mqttc.publish(base_topic+"/status", "up" , 0, mqtt_LWT_retained)
        mqttc.publish(base_topic+"/info/device", device_type , 0, mqtt_LWT_retained)
        mqttc.publish(base_topic+"/info/sw_version", SW_VER , 0, mqtt_LWT_retained)
        mqttc.subscribe(base_topic+"/cmd",0);
        conn_error=0

def on_message(client, userdata, msg):
    global cmds
    debug_txt = msg.topic+" "+str(msg.payload)
    syslog.syslog(debug_txt)
    if DEBUG_SERIAL2: print(debug_txt)
    cmdtxt=msg.payload.strip(' \t\n\r')
    kv=cmdtxt.split("|")
    k=kv[0]
    try:
        v=kv[1]
    except:
        v=""
    if(k=="ping"):
        mqttc.publish(base_topic+"/msg", "pong", 0, 0)
    elif(k=="getairmode"):
        mqttc.publish(base_topic+"/msg", getairconfig("airmode"), 0, 0)
    elif(k=="getairschedule"):
        mqttc.publish(base_topic+"/msg", getairconfig("airschedule"), 0, 0)
    elif(k=="getairgroup"):
        mqttc.publish(base_topic+"/msg", getairconfig("airgroup"), 0, 0)
    elif(k=="getairdata"):
        mqttc.publish(base_topic+"/msg", getairconfig("airdata"), 0, 0)
    elif(k=="setairmode" or k=="setairschedule" or k=="setairgroup" or k=="setairdata"):
        ret=setairconfig(kv)
        mqttc.publish(base_topic+"/msg", k +"|" +ret, 0,0)
    elif(k=="setairmaintenance"):
        #print "%s %s" % (k,v)
        if(v=="0" or v=="1"):
            line="air_maintenance," + v
            cmds.append("$%s*%s" % (line,cal_checksum(line)));

def on_disconnect(client, userdata, rc):
    global conn_error
    if rc != 0:
        debug_txt = "Unexpected disconnection:"+str(rc)
        syslog.syslog(debug_txt)
        if DEBUG_SERIAL2: print(debug_txt)
        conn_error=1

    
# SETUP

syslog.openlog(ident="mqtt_pub.py", logoption=syslog.LOG_PID, facility=syslog.LOG_LOCAL1)
d_log = open(TEMP_DIR +'debug.log','a+')

serialdev=''
if _platform == 'cygwin':
    serialdev = CYGWIN_SERIAL
    DEBUG_LOG_SIZE = DEBUG_LOG_SIZE*10
else:
    d_log.write(time.strftime("%Y-%m-%d %H:%M:%S") +' Finding Arduino MEGA ... \n')
    print 'Finding Arduino MEGA ...'
    d_log.flush()
    retry = 5
    while (serialdev == '' and retry >0 ):
        sys.stdout.write('.'); sys.stdout.flush()
        for i in range(0,3):
            try:
                fn = '/sys/class/tty/ttyACM%d/device/modalias' % (i)
                f = open(fn,'r')
                lines = f.readline().strip()
                f.close()
                if (lines[0:14] == 'usb:v2341p0042' or lines[0:14] == 'usb:v2341p0242'):
                    serialdev = '/dev/ttyACM%d' % (i)
                    break
            except:
                pass
        if serialdev != '':
            break
        retry = retry -1
        time.sleep(10)

if serialdev == '':
    print(' Arduino MEGA not found, exit.')
    sys.exit()
else:
    d_log.write(time.strftime("%Y-%m-%d %H:%M:%S") +' Found Arduino MEGA on %s\n' % (serialdev))
    d_log.flush()
    syslog.syslog('Found Arduino MEGA on %s\n' % (serialdev))
    print(' Found Arduino MEGA on %s\n' % (serialdev))

if _platform == 'cygwin':
    ser = serial.Serial(serialdev, baudrate=9600, timeout=20)
else:
    ser = serial.Serial(serialdev, baudrate=9600, timeout=20, writeTimeout=10)
ser.open


c1='0'; c2='0'; c3='0'; c4='0'; c5='0'; c6='0'; c7='0'; c8='0'; c9='0'; c10='0'; c11='0'; c12='0'; c13='0'
v1='0'; v2='0'; v3='0'
pf1='0'; pf2='0'; pf3='0'; pf4='0'; pf5='0'; pf6='0'; pf7='0'; pf8='0'; pf9='0'; pf10='0'; pf11='0'; pf12='0'; pf13='0'
pw1='0'; pw2='0'; pw3='0'; pw4='0'; pw5='0'; pw6='0'; pw7='0'; pw8='0'; pw9='0'; pw10='0'; pw11='0'; pw12='0'; pw13='0'

uptime = 0

ser.flushInput()
x = 0
nodata=0
cmds=[]

rV=['','','']
rI=['','','','','','','','','','','','','']
rPf=['','','','','','','','','','','','','']
rPw=['','','','','','','','','','','','','']

# load config
if mqtt_client_name == '':
    mqtt_client_name = get_config_from_file('/root/mqtt/MAC','notconfig','Yun-')
if base_topic == '':
    base_topic = get_config_from_file('/root/mqtt/MQTT_BASE_TOPIC','notconfig','')
if device_type == '':
    device_type = get_config_from_file('/root/mqtt/DEVICE_TYPE','EnvMonCtrl1','')
if mqtt_host == '':
    mqtt_host = get_config_from_file('/root/mqtt/MQTT_HOST','100.64.2.1','')
AVR_TEMP_OFFSET= int(get_config_from_file('/root/mqtt/TEMP_OFFSET',-6,''))
        
bridge = bridgeclient()
bridge.put("ow",str(NUM_OW_ENABLE))
bridge.put("dh",str(DHT_ENABLE))
bridge.put("li",str(TEMP_LOOP_TIME))
bridge.put("pe","------") # disable Emon

dht_reset_delay = 0

for calibrate_string in (get_ct_ical(),get_ct_phase(),get_v_cal(),get_v_phasecal(),get_v_phasecoef(),get_probe_en(),get_irms_nsam(),get_calcvi_crto(),get_read_to(),get_air_phase(),get_air_vlow_threshold()):
    try:
        if len(calibrate_string)>0:
            d_log.write(time.strftime("%Y-%m-%d %H:%M:%S") +" CALIBRATE:" +calibrate_string +"\n")
        if DEBUG_SERIAL:
            syslog.syslog('CALIBRATE: '+ calibrate_string)
        if DEBUG_SERIAL2:
            print('CALIBRATE: '+ calibrate_string)
        
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)

u = open(FILE_UPDATE,'a+')
u.close()

i=5000
while i >0:
    while ser.inWaiting() == 0 and i > 0:
        time.sleep(0.1)
        i = i - 100
    if ser.inWaiting() > 0:
        current = ser.readline().strip('\r\n').strip()
        if current == "*End":
            break

if mqtt_client_name == '':
        try:
                f = open("/root/mqtt/MAC",'r')
                MAC = f.readline().strip(' \t\n\r')
                f.close()
        except:
                MAC = "notconfig"
        mqtt_client_name = 'Yun-' + MAC

debug_txt = "mqtt client %s start" % mqtt_client_name
d_log.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + debug_txt + "\n")
d_log.flush()
if DEBUG_SERIAL:
    syslog.syslog(debug_txt)
if DEBUG_SERIAL2:
    print(debug_txt)

mqttc = mqtt.Client(mqtt_client_name)
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.on_disconnect = on_disconnect
if mqtt_user != "":
    mqttc.username_pw_set(mqtt_user,mqtt_pass)
mqttc.will_set(base_topic+"/status","down",0,mqtt_LWT_retained)
mqttc.connect(mqtt_host,mqtt_port,mqtt_timeout)
mqtt_ts=time.time()
conn_error = 0

# open tempureature data file
try:
    f_temp = open(TEMP_FILE_TMP,'w')
except:
    pass
        
# LOOP
mqtt_reconnect_count=0
while 1:
    if conn_error >0 :
        if mqtt_reconnect_count % 10 == 0:
            debug_txt = "MQTT Reconnect..."
            d_log.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + debug_txt + "\n")
            if DEBUG_SERIAL: syslog.syslog(debug_txt)
            if DEBUG_SERIAL2: print(debug_txt)
            mqttc.reconnect()
        mqtt_reconnect_count = mqtt_reconnect_count + 1
    else:
        mqtt_reconnect_count=0
        
    #print "X: " +str(x) +"\n";
    if nodata > 2:
        d_log.write("loop with no data receive: "+str(nodata)+"\n")
        d_log.flush()
        if nodata > 10:
            syslog.syslog("no data receive too long, exit")
            d_log.write("no data receive too long, exit\n")
            d_log.flush()
            # posible usb error. close serial and unload usb kernel module
            ser.close()
            os.system("/sbin/rmmod cdc_acm")
            break
    if(x == 1):
        mqttc.publish(base_topic+"/info/device", device_type , 0, mqtt_LWT_retained)
        if can_calibrate:
            try:
                # check if file change?
                if TIME_CT_PHASE <> os.path.getmtime(FILE_CT_PHASE):
                    cmds.append(get_ct_phase())
#                    need_calibrate += 1
                if TIME_CT <> os.path.getmtime(FILE_CT):
                    cmds.append(get_ct_ical())
#                    need_calibrate += 1
                if TIME_V_CAL <> os.path.getmtime(FILE_V_CAL):
                    cmds.append(get_v_cal())
#                    need_calibrate += 1
                if TIME_V_PHASECAL <> os.path.getmtime(FILE_V_PHASECAL):
                    cmds.append(get_v_phasecal())
#                    need_calibrate += 1
                if TIME_V_PHASECOEF <> os.path.getmtime(FILE_V_PHASECOEF):
                    cmds.append(get_v_phasecoef())
#                    need_calibrate += 1
                if TIME_PROBE_EN <> os.path.getmtime(FILE_PROBE_EN):
                    cmds.append(get_probe_en())
                if TIME_IRMS_NSAM <> os.path.getmtime(FILE_IRMS_NSAM):
                    cmds.append(get_irms_nsam())
                if TIME_CALCVI_CRTO <> os.path.getmtime(FILE_CALCVI_CRTO):
                    cmds.append(get_calcvi_crto())
                if TIME_READ_TO <> os.path.getmtime(FILE_READ_TO):
                    cmds.append(get_read_to())
                if TIME_AIR_PHASE <> os.path.getmtime(FILE_AIR_PHASE):
                    cmds.append(get_air_phase())
                if TIME_AIR_VLOW <> os.path.getmtime(FILE_AIR_VLOW):
                    cmds.append(get_air_vlow_threshold())
            except:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
            
        if need_calibrate:
            need_calibrate=0
            cmds=[]
            try:
                for calibrate_string in (get_ct_phase(),get_ct_ical(),get_v_cal(),get_v_phasecal(),get_v_phasecoef(),get_probe_en(),get_irms_nsam(),get_calcvi_crto(),get_read_to(),get_air_phase(),get_air_vlow_threshold()):
                    if len(calibrate_string)>0:
                        ser.write(calibrate_string +'\n')
                        syslog.syslog('write: ' +calibrate_string +'\n')
                        if DEBUG_SERIAL2:
                            print('write: ' +calibrate_string);
                        d_log.write(time.strftime("%Y-%m-%d %H:%M:%S") +' < ' +calibrate_string +'\n')
                        # Wait for response
                        i=500
                        while ser.inWaiting() == 0 and i > 0:
                            time.sleep(0.1)
                            i = i - 100
                        while ser.inWaiting() > 0:
                            current = ser.readline().strip('\r\n').strip()
                            if current[0:2] == 'C:':
                                report_txt=("REPORT:%d:%s:cfg: %s" % (SITE_ID,DEVICE_ID,current))
                                syslog.syslog(report_txt);
                                d_log.write(time.strftime("%Y-%m-%d %H:%M:%S")+' > '+current+'\n')

                            if DEBUG_SERIAL:
                                syslog.syslog('read: '+current);
                            if DEBUG_SERIAL2:
                                print('read: '+current);
                            time.sleep(10/1000)
            except:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
            
        if len(cmds) > 0:
            print "found cmds..."
            for calibrate_string in cmds:
                if len(calibrate_string)>0:
                    ser.write(calibrate_string +'\n')
                    syslog.syslog('write: ' +calibrate_string +'\n')
                    if DEBUG_SERIAL2:
                        print('write: ' +calibrate_string);
                    d_log.write(time.strftime("%Y-%m-%d %H:%M:%S") +' < ' +calibrate_string +'\n')
                    time.sleep(10/1000)
            cmds=[]

        try:
            fn = TEMP_DIR +'data_air_to_board.txt'
            f2 = open(fn,'r')
            buff = f2.readline().strip()
            f2.close()

            if(uptime < 300):
                fn = 'd_log'
                d_log.write(time.strftime("%Y-%m-%d %H:%M:%S")+' # wait for system initialize, command not sent.\n')
                d_log.flush()
                fn = 'syslog'
                syslog.syslog('wait for system initialize, command not sent.')
                fn = '/proc/uptime'
                f = open(fn,'r')
                lines = f.readline().strip()
                f.close()
                uptime = lines.split(" ")
                uptime = uptime[0]
            else:
                if can_calibrate:
                    fn = 'serial'
                    send_air_cmd(buff)
        except IOError as e:
            d_log.write("I/O error({0}): {2} {1}".format(e.errno, e.strerror, fn)+'\n')
            d_log.flush()
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)

        x = 0

    if(time.time() - mqtt_ts > 1):
        mqttc.loop(0.1,100)
        mqtt_ts = time.time()

    current = ser.readline().strip('\r\n').strip()
    if current[0:2] == 'C:':
        report_txt=("REPORT:%d:%s:cfg: %s" % (SITE_ID,DEVICE_ID,current))
        syslog.syslog(report_txt);
    if DEBUG_SERIAL:
        syslog.syslog('read: '+current);
    if DEBUG_SERIAL2:
        print('read: '+current);
    if len(current)==0:
        nodata = nodata +1
        continue
    else:
        nodata = 0

    # Process serial info
    # *?k[0]:k[1]... v
    if len(current)>2 and current[0]=='*':
        k=[]; v=""
        ki=0
        tmp=current.split(' ')
        if len(tmp)==2:
            k=tmp[0].split(':'); v=tmp[1]
            if DEBUG_SERIAL2: print("k:%s v:%s" % (k[0],v))
            ki=len(k)

        if ki==1:
            if k[0] == "*vcc":
                try:
                    i=float(v)
                except:
                    i=0.00
                v= "%0.2f" % (i/1000)
                mqttc.publish("%s/info/vcc" %(base_topic),v)    
            elif k[0] == "*ver":
                mqttc.publish("%s/info/version" %(base_topic),str(v))
            elif k[0] == "*ms":
                try:
                    i=int(v)/1000
                except:
                    i=0
                # uptime in seconds
                mqttc.publish("%s/info/uptime" %(base_topic),str(i))
            elif k[0] == "*DH":
                try:
                    i=float(v)
                except:
                    i=0
                v="%0.2f" % i
                mqttc.publish("%s/dht22/humidity" %(base_topic),v)   
            elif k[0] == "*DT":
                try:
                    i=float(v)
                except:
                    i=0
                v="%0.2f" % i
                mqttc.publish("%s/dht22/temp" %(base_topic),v)  
            elif k[0] == "*Air_Bit":
                i=0
                # write air data file
                f_air = open(AIR_FILE_TMP,'w')
                f_air.write("Air_Bit %s\n" % v)
                f_air.close()
                shutil.copy(AIR_FILE_TMP,AIR_DATA_FILE)
                
                while (i+1)*3 <= len(v):
                    aircmd=v[i*3:i*3+3]
                    if len(aircmd) == 3:
                        try:
                            air_state = aircmd2status[aircmd]
                        except:
                            air_state = 0
                            pass
                        mqttc.publish("%s/air/%d" %(base_topic,i+1),air_state)
                    i = i+1
            elif k[0] == "*AIR_MAINT":
                mqttc.publish("%s/info/air_maintenance" % (base_topic),v)
            else:
                print "ki=1 %s" % current
                
        elif ki==2:
            if k[0] == "*V":
                i=int(k[1])-1
                if i>=0 and i<3:
                    rV[i]=v;
                    mqttc.publish("%s/voltage/%d" %(base_topic,i+1),v)
            elif k[0] == "*I":
                i=int(k[1])-1
                if i>=0 and i<13:
                    rI[i]=v;
                    mqttc.publish("%s/current/%d" %(base_topic,i+1),v)
            elif k[0] == "*Pf":
                i=int(k[1])-1
                if i>=0 and i<13:
                    rPf[i]=v;
                    mqttc.publish("%s/powerfactor/%d" %(base_topic,i+1),v)
            elif k[0] == "*P":
                i=int(k[1])-1
                if i>=0 and i<13:
                    rPw[i]=v;
                    mqttc.publish("%s/power/%d" %(base_topic,i+1),v)
            elif k[0] == "*W":
                if k[1]=="AIR_LOW_VOLTAGE":
                    lowv_temp=v.split(',')
                    try:
                        airid=int(lowv_temp[0]) +1
                        voltage=lowv_temp[1]
                        mqttc.publish("%s/warning/air/%d/lowvoltage" %(base_topic,airid),voltage)
                        report_txt = "air_low_voltage: %s" % v
                        d_log.write(time.strftime("%Y-%m-%d %H:%M:%S")+'  '+report_txt+'\n')
                        d_log.flush()
                        syslog.syslog(report_txt)
                    except:
                        pass
                elif k[1]=="AIR_EMER_STOP":
                        mqttc.publish("%s/warning/air_emer_stop" %(base_topic),v)
                        report_txt = "air_emer_stop: %s" % v
                        d_log.write(time.strftime("%Y-%m-%d %H:%M:%S")+'  '+report_txt+'\n')
                        d_log.flush()
                        syslog.syslog(report_txt)

        elif ki==3:
            if k[0] == "*T":
                try:
                    i=int(k[1])
                    ds_id=k[2]
                    v="%0.2f" % (float(v))
                except:
                    i=-1
                if i>=0 and ds_id[0:2]=="28" and v > -55 and v < 125:
                    mqttc.publish("%s/temp/%d/%s" %(base_topic,i+DS_OFFSET,ds_id),v)
                    if not f_temp:
                        f_temp = open(TEMP_FILE_TMP,'w')
                    f_temp.write("%s %s\n" % (ds_id,v));
                
        elif ki==0:
            if current == "*End":
                x = 1
                # get temp from bridge
                t=os.path.getmtime(FILE_UPDATE)
                A = None
                if t != TIME_UPDATE:
                    A = bridge.getall()
                    TIME_UPDATE = t
                if not A is None:
                    # open tempurature data file
                    if not f_temp:
                        f_temp = open(TEMP_FILE_TMP,'w')
                    # get temperature from 32u4
                    for ds in range (2,7):
                        key = "num_ds%d" % ds
                        try:
                            num_ds=int(A[key])
                        except:
                            num_ds=0
                        i=1
                        while i <= num_ds:
                            key = "ds%d_%d" % (ds,i)
                            try:
                                buff=A[key]
                                sensor=buff.split(' ')
                            except:
                                sensor = []
                            i=i+1
                            if len(sensor) <2:
                                continue
                            try:
                                t="%0.2f" % (float(sensor[1]))
                                topic = "%s/temp/%d/%s" % (base_topic,ds,sensor[0])
                                mqttc.publish(topic, t , 0)
                                debug_txt = "bridge: %s %s %s" % (key,sensor[0],t)
                                d_log.write(time.strftime("%Y-%m-%d %H:%M:%S")+'  '+debug_txt+'\n')
                                d_log.flush()
                                if DEBUG_SERIAL2:
                                    print debug_txt
                                f_temp.write("%s %s\n" % (sensor[0],t));
                            except:
                                pass
                        if num_ds>0:
                            mqttc.loop(1,50)

                    # get ups
                    os.system("php upswalk.php > /tmp/ups_results.txt")
                    ups_ = open("/tmp/ups_results.txt")
                    for ups in ups_:
                        v_ups = ups.strip(' \t\n\r').split(" ")    
                        if len(v_ups)==2:
                            mqttc.publish(v_ups[0], v_ups[1] , 0)
                            mqttc.loop(1,50)

                    # get dht22
                    if DHT_ENABLE:
                        try:
                            dh = int(A['dh'])
                            dht = float(A['dht'])
                            dhh = float(A['dhh'])
                            if dh == 1:
                                if dht == 0 and dhh == 0 :
                                    if dht_reset_delay > 0:
                                        dht_reset_delay = dht_reset_delay -1
                                    else:
                                        bridge.put("dh","0")
                                        dht_reset_delay = 1
                                        debug_txt = "reset dht22..."
                                        syslog.syslog(debug_txt)
                                else:
                                    topic = "%s/dht22/temp" % (base_topic)
                                    mqttc.publish(topic, ("%0.2f" % dht), 0)
                                    topic = "%s/dht22/humidity" % (base_topic)
                                    mqttc.publish(topic, ("%0.2f" % dhh), 0)
                                    mattc.loop(1,4)
                            else:
                                if dht_reset_delay > 0:
                                    dht_reset_delay = dht_reset_delay -1
                                else:
                                    debug_txt = "enable dht22..."
                                    syslog.syslog(debug_txt)
                                    bridge.put("dh","1")
                                    dht_reset_delay = 1
                        except:
                            pass
                    
                    # get 32u4 version
                    try:
                        ver=A["ver"]
                        topic = "%s/info/version_32u4" % base_topic
                        mqttc.publish(topic, ver, 0)
                        mqttc.loop(1,5)
                    except:
                        pass
                    
                    # get 32u4 temp
                    try:
                        t = float(A['temp'])
                        t = t - 273 + AVR_TEMP_OFFSET
                        topic = "%s/info/mcutemp" % (base_topic)
                        m="%0.2f" % t
                        mqttc.publish(topic, m , 0)
                    except:
                        pass
                        
                # create run file
                f = open(RUN_FILE,'w')
                f.close
                
                # report to syslog
                report_txt=("REPORT:%d:%s:v: %s %s %s" % (SITE_ID,DEVICE_ID,v1,v2,v3))
                if SYSLOG_REPORT:
                    syslog.syslog(report_txt)
                d_log.write(time.strftime("%Y-%m-%d %H:%M:%S") +' ' +report_txt +'\n')
                report_txt=("REPORT:%d:%s:i: %s %s %s %s %s %s %s %s %s %s %s %s %s" % (SITE_ID,DEVICE_ID,rI[0],rI[1],rI[2],rI[3],rI[4],rI[5],rI[6],rI[7],rI[8],rI[9],rI[10],rI[11],rI[12]))
                if SYSLOG_REPORT:
                    syslog.syslog(report_txt)
                d_log.write(time.strftime("%Y-%m-%d %H:%M:%S") +' ' +report_txt +'\n')
                report_txt=("REPORT:%d:%s:pw: %s %s %s %s %s %s %s %s %s %s %s %s %s" % (SITE_ID,DEVICE_ID,rPw[0],rPw[1],rPw[2],rPw[3],rPw[4],rPw[5],rPw[6],rPw[7],rPw[8],rPw[9],rPw[10],rPw[11],rPw[12]))
                if SYSLOG_REPORT:
                    syslog.syslog(report_txt)
                d_log.write(time.strftime("%Y-%m-%d %H:%M:%S") +' ' +report_txt +'\n')
                report_txt=("REPORT:%d:%s:pf: %s %s %s %s %s %s %s %s %s %s %s %s %s" % (SITE_ID,DEVICE_ID,rPf[0],rPf[1],rPf[2],rPf[3],rPf[4],rPf[5],rPf[6],rPf[7],rPf[8],rPf[9],rPf[10],rPf[11],rPf[12]))
                if SYSLOG_REPORT:
                    syslog.syslog(report_txt)
                d_log.write(time.strftime("%Y-%m-%d %H:%M:%S") +' ' +report_txt +'\n')
                
                # close tempurate data file
                if f_temp:
                    f_temp.close()
                f_temp = None
                shutil.copy(TEMP_FILE_TMP,TEMP_DATA_FILE)
            
                # rotate debug log
                try:
                    #print('close debug log');
                    d_log.close()
                    if(os.path.getsize(TEMP_DIR +'debug.log')>10240):
                        shutil.copy(TEMP_DIR +'debug.log',TEMP_DIR +'debug.log.1')
                        open(TEMP_DIR +'debug.log', 'w').close()
                    #print('open debug log');
                    d_log = open(TEMP_DIR +'debug.log','a+')
                except:
                    print('debug log error')
                    pass
            
            else:
                print "ki=0 %s" % current
        else:
            print "unknow ki: %d %s" % (ki,current)
            
    else:
        d_log.write(time.strftime("%Y-%m-%d %H:%M:%S")+' > '+current+'\n')
        d_log.flush()

        if current == "$calibrate":
            need_calibrate=1
            can_calibrate=1


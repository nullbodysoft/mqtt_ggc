#!/usr/bin/python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4

VER="20160229"

import sys
import time
import os
import syslog

sys.path.insert(0, '/usr/lib/python2.7/bridge/')
from bridgeclient import BridgeClient as bridgeclient
import paho.mqtt.client as mqtt

mqtt_client_name='' # '' = get from '/root/mqtt/MAC'  default: 'Yun-notconfig'
base_topic = ''     # '' = get from '/root/mqtt/MQTT_BASE_TOPIC'  default: 'notconfig'
device_type = ''    # '' = get from '/root/mqtt/DEVICE_TYPE'  default: 'EnvMon1'
mqtt_host=''        # '' = get from '/root/mqtt/MQTT_HOST'  default: '100.64.2.1'

mqtt_port=1883
mqtt_timeout=15
#mqtt_keep_status=False
mqtt_keep_status=True

LOOP_INTERVAL=15     # mcu loop interval

#AVR_TEMP_OFFSET= -6 # get from '/root/mqtt/TEMP_OFFSET'  default: -6

DEBUG=0
DEBUG_BRIDGE=0

FILE_UPDATE='/tmp/have_update'
TIME_UPDATE=0

CONF_PATH='/root/mqtt/conf/'
FILE_NAME={ 'ct.txt', 'ct_phase.txt', 'dht_enable.txt', 'ow_enable.txt', 'probe_enable2.txt', 'v_cal.txt', 'v_phasecal.txt', 'v_phasecoef.txt' }
FILE_TIME=[ 0, 0, 0, 0, 0, 0, 0, 0 ]


ICAL_UPDATE=0
VCAL_UPDATE=0
VPHASECAL_UPDATE=0
VPHASECOEF_UPDATE=0

DHT_ENABLE=0
conn_error=0
dht_reset_delay=0

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

def on_connect(client, userdata, flags, rc):
    global conn_error
    debug_txt =  "Connection returned result: "+str(rc)
    syslog.syslog(debug_txt)
    if DEBUG: print(debug_txt)
    if rc ==0:
        mqttc.publish(base_topic+"/status", "up" , 0, mqtt_keep_status)
        conn_error=0
    
def on_message(client, userdata, msg):
    debug_txt = msg.topic+" "+str(msg.payload)
    syslog.syslog(debug_txt)
    if DEBUG: print(debug_txt)

def on_disconnect(client, userdata, rc):
    global conn_error
    if rc != 0:
        debug_txt = "Unexpected disconnection:"+str(rc)
        syslog.syslog(debug_txt)
        if DEBUG: print(debug_txt)
        conn_error=1
        
def bridge_put_multi_float(key_prefix, values, num_items):
    if len(values) != num_items:
        return
    bridge.begin()
    for i in range (0,num_items):
        try:
            k=key_prefix + ('%d' % (i+1))
            v=str(float(values[i]))
        except Exception as e:
            print str(e)
            continue
        if DEBUG_BRIDGE: print('bridge.put(%s,%s)' % (k,v))
        bridge.put(k,v)
    bridge.close()

def bridge_put_str(key, values, num_items, l):
    if (len(values)) != num_items:
        return
    k = str(key)
    v = str(values[0])
    if (len(v)!=l):
        return
    if DEBUG_BRIDGE: print('bridge.put(%s,%s)' % (k,v))
    bridge.put(k,v)
    return v

def bridge_put_int(key, values, num_items):
    if (len(values)) != num_items:
        return
    try:
        v = int(values[0])
    except:
        return
    k = str(key)
    v = str(v)
    if DEBUG_BRIDGE: print('bridge.put(%s,%s)' % (k,v))
    bridge.put(k,v)
    return int(v)
    
def set_conf(check_time):
    global FILE_TIME
    global ICAL_UPDATE, VCAL_UPDATE, VPHASECAL_UPDATE, VPHASECOEF_UPDATE
    global DHT_ENABLE

    bridge.put("li",str(LOOP_INTERVAL))
    
    file_id=-1
    for filename in FILE_NAME:
        fn = CONF_PATH + filename
        file_id=file_id+1
        #print str(file_id) + ":" + fn
        line = ''
        ft =0
        try:
            ft = os.path.getmtime(fn)
            if check_time and ft == FILE_TIME[file_id]:
                #print(' not change')
                continue
            FILE_TIME[file_id] = ft
            f = open(fn,'r')
            line = f.readline().strip(' \t\n\r')
            f.close()
        except Exception as e:
            print str(e)
            continue
        if DEBUG: print str(file_id) + ":" + filename + ">" + str(ft) + ":" + line
        items = line.split(' ')
        if filename == 'ct.txt':
            bridge_put_multi_float('ical_', items, 6)
            ICAL_UPDATE = 1
        elif filename == 'v_cal.txt':
            bridge_put_multi_float('vcal_', items, 3)
            VCAL_UPDATE = 1
        elif filename == 'v_phasecal.txt':
            bridge_put_multi_float('pca_', items, 6)
            VPHASECAL_UPDATE = 1
        elif filename == 'v_phasecoef.txt':
            bridge_put_multi_float('pco_', items, 6)
            VPHASECOEF_UPDATE = 1
        elif filename == 'probe_enable2.txt':
            bridge_put_str('pe',items,1,6)
        elif filename == 'ct_phase.txt':
            bridge_put_str('pm',items,1,6)
        elif filename == 'dht_enable.txt':
            DHT_ENABLE=bridge_put_int('dh',items,1)
        elif filename == 'ow_enable.txt':
            bridge_put_int('ow',items,1)

def mqtt_multi_float(probe_type, bridge_prefix, start_index, end_index):
    bridge.begin
    for i in range (start_index, end_index+1):
        key = bridge_prefix + "%d" % i
        #ctxt = bridge.get(key)
        try:
            ctxt=A[key]
            c=float(ctxt)
        except:
            c=0.00
        m = "%0.2f" % c
        debug_txt = ("%s:%s") % (key,m)
        syslog.syslog(debug_txt)
        if DEBUG: print(debug_txt)
        topic = "%s/%s/%d" % (base_topic,probe_type,i)
        mqttc.publish(topic, m , 0)
    mqttc.loop(2,20)
    bridge.close()

# SETUP

bridge = bridgeclient()

# load config
if mqtt_client_name == '':
  mqtt_client_name = get_config_from_file('/root/mqtt/MAC','notconfig','Yun-')
if base_topic == '':
  base_topic = get_config_from_file('/root/mqtt/MQTT_BASE_TOPIC','notconfig','')
if device_type == '':
  device_type = get_config_from_file('/root/mqtt/DEVICE_TYPE','EnvMon1','')
if mqtt_host == '':
  mqtt_host = get_config_from_file('/root/mqtt/MQTT_HOST','100.64.2.1','')
AVR_TEMP_OFFSET= int(get_config_from_file('/root/mqtt/TEMP_OFFSET',-6,''))

debug_txt = "mqtt client %s start" % mqtt_client_name
syslog.syslog(debug_txt)
if DEBUG: print(debug_txt)

mqttc = mqtt.Client(mqtt_client_name)
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.on_disconnect = on_disconnect
#mqttc.username_pw_set('user','pass')

mqttc.will_set(base_topic+"/status","down",0,mqtt_keep_status)

mqttc.connect(mqtt_host,mqtt_port,mqtt_timeout)

u = open(FILE_UPDATE,'a+')
u.close()
syslog.openlog(ident="mqtt_pub.py", logoption=syslog.LOG_PID, facility=syslog.LOG_LOCAL1)

set_conf(False)

recalibrate = 1

# LOOP
while 1 :
    A = bridge.getall()
    while A is None:
        debug_txt = "Retry getall()..."
        syslog.syslog(debug_txt)
        if DEBUG: print(debug_txt)
        time.sleep(1000)
        A = bridge.getall()
        
    try:
        recalibrate = int(A['rc'])
    except:
        recalibrate = 0
    if recalibrate > 0:
        debug_txt = "Recalibrate..."
        syslog.syslog(debug_txt)
        if DEBUG: print(debug_txt)
        set_conf(False)
        bridge.put("rc","0")

    # wait for new data
    wait = 300
    if DEBUG: print "wait"
    while wait > 0:
        if DEBUG:
            sys.stdout.write('.')
            sys.stdout.flush()
        t=os.path.getmtime(FILE_UPDATE)
        if t != TIME_UPDATE:
            TIME_UPDATE=os.path.getmtime(FILE_UPDATE)
            break
        mqttc.loop(1,10)
        wait = wait -1
        time.sleep(0.5)
    if DEBUG: print('')
        
    if conn_error >0 :
        debug_txt = "Reconnect..."
        syslog.syslog(debug_txt)
        if DEBUG: print(debug_txt)
        mqttc.reconnect()

    set_conf(True)

    if ICAL_UPDATE > 0:
        bridge.put('i_u','1')
        ICAL_UPDATE = 0
    if VCAL_UPDATE > 0:
        bridge.put('v_u','1')
        VCAL_UPDATE = 0
    if VPHASECAL_UPDATE > 0:
        bridge.put('pc_u','1')
        VPHASECAL_UPDATE = 0
    if VPHASECOEF_UPDATE > 0:
        bridge.put('pc_u','1')
        VPHASECOEF_UPDATE = 0


    if DEBUG: print "run temp ...."
    for ds in range (2,7):
        key = "num_ds%d" % ds
        try:
            num_ds=int(A[key])
            if DEBUG: print "ds" +str(ds) + ": " + str(A[key])
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
                if DEBUG: print "publish " + topic + " " + t
                mqttc.publish(topic, t , 0)
            except:
                pass
                
        if num_ds >0:
            #if DEBUG: print "mqtt loop start"
            mqttc.loop(2,50)
            #if DEBUG: print "mqtt loop end"
    
    if DEBUG: print "run current ...."
    mqtt_multi_float('current','i',1,6)
    if DEBUG: print "run voltage ...."
    mqtt_multi_float('voltage','v',1,6)
    if DEBUG: print "run power ...."
    mqtt_multi_float('power','r',1,6)
    if DEBUG: print "run power factor ...."
    mqtt_multi_float('powerfactor','p',1,6)


    topic = "%s/info/device" % (base_topic)
    mqttc.publish(topic,device_type, 0, mqtt_keep_status)
    
    try:
        vcc = float(A['vcc'])
        vcc = vcc/1000
    except:
        vcc = -1
    topic = "%s/info/vcc" % (base_topic)
    m="%0.2f" % vcc
    mqttc.publish(topic, m , 0)
    
    try:
        buff=A['ver']
        topic = "%s/info/version" % (base_topic)
        mqttc.publish(topic, buff, 0)
    except:
        pass
        
    try:
        uptime = int(A['up'])
    except:
        uptime = 0
    topic = "%s/info/uptime" % (base_topic)
    mqttc.publish(topic, str(uptime), 0)
    if DEBUG:
        print("up: %d" % uptime)

    try:
        t = float(A['temp'])
        t = t -273 + AVR_TEMP_OFFSET
    except:
        t = -1
    topic = "%s/info/mcutemp" % (base_topic)
    m="%0.2f" % t
    mqttc.publish(topic, m , 0)
    
    topic = "%s/info/probe" % (base_topic)
    try:
        pe = A['pe']
        mqttc.publish(topic, pe, 0)
    except:
        pass

    if DHT_ENABLE:
        try:
            dh = int(A['dh'])
            dht = float(A['dht'])
            dhh = float(A['dhh'])
            if dh == 1:
                if dht == 0 and dhh == 0:
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
            else:
                if dht_reset_delay > 0:
                    dht_reset_delay = dht_reset_delay -1
                else:
                    bridge.put("dh","1")
                    dht_reset_delay = 1
                    debug_txt = "enable dht22..."
                    syslog.syslog(debug_txt)
        except:
            pass
    
    mqttc.loop(1,20)

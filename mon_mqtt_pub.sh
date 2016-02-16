#!/bin/sh
ps | grep -v grep | grep -q 'python /root/mqtt/mqtt_pub.py' && exit
[ -x /etc/init.d/mqtt-pub ] && /etc/init.d/mqtt-pub start

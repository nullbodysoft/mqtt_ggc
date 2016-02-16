import os
import sys
import time

t1=0.0
t2=0.0
c=0
a=0.0
while 1:
	t1=os.path.getmtime('/tmp/have_update')
	if t2==0:
		t2=t1
	if t1 == t2:
		sys.stdout.write('.')
		sys.stdout.flush()
	else:
		d=t1-t2
		a+=d
		c+=1
		print "\n%0.2f %0.2f" % (d, a/c)
	t2 = t1
	time.sleep(1);

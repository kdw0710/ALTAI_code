import fileinput
import re

steps=[]
dv=-1
try:
    for line in fileinput.input():
        if re.search('EVENT',line):
            dvp=re.search(r'DV=(\d+)',line).group(1)
            if dvp!=dv:
                steps.append([0]*(1<<19))
                n=0
                dv=dvp
            else:
               n+=1
        else:
           x,y=map(int,line.split())
           steps[-1][y*1024+x]+=1
except:
    pass

pixels=[]
for x in range(128*5,128*6):
    for y in range(8):
        pixels.append((x,y))

for step in steps:
    n=[]
    for pixel in pixels:
        n.append(str(step[pixel[1]*1024+pixel[0]]))
    print('\t'.join(n))

fp = r'e:\code\claude-1\a3-learning-system\backend\app\agents\supervisor.py'
lines = open(fp,'r',encoding='utf-8').readlines()
ins = [''    # chat: system (before resource)'', ''    if any(k in text for k in [chr(20171)+chr(32461)+chr(19968)+chr(19979)+chr(20320), chr(20320)+chr(30340)+chr(21151)+chr(33021), chr(20320)+chr(33021)+chr(20570)+chr(20160)+chr(20040), chr(20320)+chr(662f)+chr(35780), ''what can you do'', ''who are who'']):'', ''        return {'''':char(39)+''intent'''':char(39)+'':'''+char(39)+''chat'''+char(39)+''','+char(39)+''params'''+char(39)+':''+char(39)+char(123)+char(125)+char(39)+''}'', '''']'
lines[274:274]=ins
open(fp,'w',encoding='utf-8').writelines(lines)
print('OK')

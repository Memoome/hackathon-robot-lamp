"""Validate stock emotional plans without touching hardware or calibration."""
import pathlib,sys,json,copy
folder=pathlib.Path(__file__).resolve().parents[1]/'apps/LJWB03-Lamp-Demo'
sys.path.insert(0,str(folder))
import expressive_routines as e
import visual_control as v
p=json.loads((folder/'visual-lamp.json').read_text(encoding='utf-8'))
before=copy.deepcopy(p)
locked=(folder/'profiles/final draft.json').read_bytes()
for music in (False,True):
    plans={name:e.build_gesture(p,p['roles'],name,music) for name in ('Slump','Water','Stretch')}
    plans['Sad']=e.build_sad(p,p['roles'],music,1500)
    plans['Happy']=e.build_happy(p,p['roles'],music)
    for name,rows in plans.items():
        candidate=copy.deepcopy(p);candidate['routine']=rows;v.check_project(candidate)
        start=p['poses'][p['roles']['Rest']];base=1500;origin=[26,21,15];light=origin.copy()
        for row in rows:
            adjusted=e.coordinated_row(start,row,600,base)
            duration=e.trajectory_duration(start,adjusted,600)
            assert duration>0 and all(500<=x<=2500 for x in row['pulse'])
            if 'base_pulse' in row:
                assert 500<=row['base_pulse']<=2500
                assert abs(row['base_pulse']-base)<=600*duration+1
                base=row['base_pulse']
            for n in range(21):
                pulse,_=e.sample_motion(start,adjusted,n*duration/20,600)
                assert all(min(a,b)<=x<=max(a,b) for x,a,b in zip(pulse,start,row['pulse']))
                if any(k in row for k in ('light_rgb','warm_level','light_progress')):
                    rgb=e.sample_emotion_light(origin,row,light,n/20)
                    assert len(rgb)==3 and all(type(x)==int and 0<=x<=255 for x in rgb)
            if any(k in row for k in ('light_rgb','warm_level','light_progress')):
                light=e.sample_emotion_light(origin,row,light,1)
            start=row['pulse']
        if name!='Sad':assert rows[-1]['pulse']==p['poses'][p['roles']['Rest']]
        if name=='Sad':assert light[0]==light[1]==0 and light[2]<max(origin)
        assert all(-1<=row['sound']<=9 for row in rows)
assert p==before and (folder/'profiles/final draft.json').read_bytes()==locked
print('PASS: all five actions/both sound styles, command/light bounds, coordinated base speed, no arm overshoot, rest/sad end states and immutable calibration.')

"""Expressive, model-aware lamp gestures. Geometry is an estimate, never feedback."""
import math

def lerp(a,b,t):return [round(x+(y-x)*t) for x,y in zip(a,b)]
def interp(points,pulse):
    for (a,b),(c,d) in zip(points,points[1:]):
        if pulse<=c:return b+(d-b)*(pulse-a)/(c-a)
    return points[-1][1]
def inverse(points,angle):
    pts=sorted((a,p) for p,a in points);angle=max(pts[0][0],min(pts[-1][0],angle))
    for (a,b),(c,d) in zip(pts,pts[1:]):
        if angle<=c:return round(b+(d-b)*(angle-a)/(c-a))
    return round(pts[-1][1])
def geometry(p,pulse):
    angles=[interp(c,v) for c,v in zip(p['calibration'],pulse)]
    xy=[(0.,0.)];a=-90
    for angle,length in zip(angles,p['lengths']):
        a+=angle;x,y=xy[-1];xy.append((x+length*math.cos(math.radians(a)),y+length*math.sin(math.radians(a))))
    return xy,a+(180 if p.get('head_face_sign',1)<0 else 0)
def face(p,pose,angle,home,limit=210):
    _,current=geometry(p,pose)
    delta=(angle-current+180)%360-180
    a=interp(p['calibration'][2],pose[2])+delta
    result=pose.copy();result[2]=max(500,home[2]-limit,min(2500,home[2]+limit,inverse(p['calibration'][2],a)))
    return result
def tilt(p,pose,delta,home):
    return face(p,pose,geometry(p,pose)[1]+delta,home)
def body(p,home,dx,dy,face_angle,reach=150,head_limit=210):
    """Search a small local neighbourhood, avoiding a large inverse-IK branch jump."""
    origin,_=geometry(p,home);goal=(origin[-1][0]+dx,origin[-1][1]+dy);hinge_goal=(origin[2][0]+dx,origin[2][1]+dy);best=None
    side=1 if origin[-1][0]>=0 else -1
    for da in range(-reach,reach+1,15):
        for db in range(-reach,reach+1,15):
            candidate=[max(500,min(2500,home[0]+da)),max(500,min(2500,home[1]+db)),home[2]]
            candidate=face(p,candidate,face_angle,home,head_limit)
            xy,_=geometry(p,candidate)
            if xy[-1][0]*side<25 or xy[-1][1]>-15:continue
            cost=2*((xy[2][0]-hinge_goal[0])**2+(xy[2][1]-hinge_goal[1])**2)+.2*((xy[-1][0]-goal[0])**2+(xy[-1][1]-goal[1])**2)+.001*(da*da+db*db)
            if best is None or cost<best[0]:best=(cost,candidate)
    return best[1] if best is not None else home.copy()
def trajectory_duration(start,row,cap):
    delays=row.get('delays',[0,0,0])
    # Quintic easing has a maximum slope of1.875. Include joint lag in the cap.
    return max(row['seconds'],max(1.875*abs(b-a)/(cap*(1-d)) for a,b,d in zip(start,row['pulse'],delays)))
def sample_motion(start,row,elapsed,cap):
    duration=trajectory_duration(start,row,cap);values=[]
    for a,b,delay in zip(start,row['pulse'],row.get('delays',[0,0,0])):
        u=max(0,min(1,(elapsed/duration-delay)/(1-delay)))
        ease=u*u*u*(10+u*(-15+6*u));values.append(round(a+(b-a)*ease))
    return values,duration

def coordinated_row(start,row,cap,base_start):
    result=dict(row)
    if 'base_pulse' in row:
        result['seconds']=max(trajectory_duration(start,row,cap),abs(row['base_pulse']-base_start)/600)
    return result

def sad_light(origin,progress):
    progress=max(0,min(1,progress));level=max(origin) or 26
    blue=[0,0,level]
    if progress<=.65:return lerp(origin,blue,progress/.65)
    return [0,0,round(level*(1-.8*(progress-.65)/.35))]

def build_sad(p,roles,music=False,base_start=1500):
    rows=build_gesture(p,roles,'Slump',music)[:3]
    for row in rows:row.pop('light_rgb',None)
    extreme=500 if base_start>1500 else 2500
    rows[0].update(name='Sad · take a breath',light_progress=0)
    rows[1].update(name='Sad · turn away and lower the head',seconds=1.8,pause=0,sound=2 if music else 0,
                   base_pulse=round(base_start+(extreme-base_start)*.65),light_progress=.65)
    rows[2].update(name='Sad · curl inward and fade to dim blue',seconds=1.4,pause=.5,base_pulse=extreme,light_progress=1)
    return rows

def emotion_light(origin,row):
    if 'light_rgb' in row:return row['light_rgb'].copy()
    if 'warm_level' in row:
        peak=max(64,min(180,max(origin)))
        return [round(channel*peak*row['warm_level']/255) for channel in (255,196,180)]
    return sad_light(origin,row['light_progress'])

def sample_emotion_light(origin,row,start,t):
    t=max(0,min(1,t));target=emotion_light(origin,row)
    rgb=lerp(start,target,t*t*(3-2*t))
    if 'light_breathe' in row:
        scale=.7+.3*math.cos(2*math.pi*row['light_breathe']*t)
        rgb=[round(v*scale) for v in rgb]
    return rgb

def build_happy(p,roles,music=False):
    home=p['poses'][roles['Rest']].copy();xy,heading=geometry(p,home)
    side=1 if xy[-1][0]>=0 else -1
    base=p.get('base_position',{});front=max(0,min(180,base.get('front',90)))
    def yaw(delta):
        angle=max(0,min(180,front+delta))
        return round(500+(180-angle if base.get('reverse',False) else angle)*2000/180)
    lifted=body(p,home,side*8,-22,heading-side*10,reach=240,head_limit=350)
    rows=[]
    def add(name,pose,seconds,yaw_offset,level,sound=-1):
        row=dict(name=name,pulse=pose.copy(),seconds=seconds,pause=0,sound=sound,easing='quintic',
                 delays=[0,0,0],gesture_speed=600,base_pulse=yaw(yaw_offset),warm_level=level)
        previous=rows[-1]['pulse'] if rows else home
        if not clear_path(p,previous,row,side):row['pulse']=previous.copy()
        rows.append(row)
    add('Happy · did you see what I did?',home,.6,0,.45)
    add('Cheeky grin · head up and a sideways glance',lifted,.65,-12,1,3 if music else 8)
    for n,(offset,level,tilt_angle) in enumerate(((12,.22,7),(-12,1,-6),(12,.22,7),(-8,1,-4))):
        pose=face(p,lifted,geometry(p,lifted)[1]+side*tilt_angle,home,350)
        add('Hehe · playful wiggle '+str(n+1),pose,.48,offset,level)
    add('An innocent little nod',face(p,home,heading+side*6,home,350),.4,5,.35)
    add('Who, me? · warm happy rest',home,.55,0,.65)
    return rows

def build_slow_gesture(p,roles,kind,music=False):
    home=p['poses'][roles['Rest']].copy();xy,heading=geometry(p,home)
    forward=1 if math.cos(math.radians(heading))>=0 else -1
    down=forward*1;up=-forward*1;length=sum(p['lengths'][:2])
    # Saved real checkpoints take priority. Starter guesses are replaced locally
    # by generated poses whose head height and facing are evaluated in the model.
    name=roles[kind];custom=not name.startswith('Starter ')
    target=p['poses'][name].copy() if custom else None
    rows=[]
    def add(label,pulse,seconds,pause=0,sound=-1,delays=(0,0,0)):
        rows.append(dict(name=label,pulse=pulse.copy(),seconds=seconds,pause=pause,sound=sound,easing='quintic',delays=list(delays)))
    happy=3 if music else 1
    add('Find a comfortable rest',home,1.1,.15)
    if kind=='Slump':
        target=target or body(p,home,forward*length*.025,length*.045,heading+down*18)
        glance=tilt(p,home,down*9,home)
        add('Eyelids heavy · head sinks first',glance,.75,delays=(0,0,0))
        add('Body gives in · head follows',target,1.8,1.0,2 if music else 0,delays=(.12,0,.2))
        effort=lerp(target,home,.18)
        add('A small effort to straighten',effort,.85,.2)
        add('Soft sigh · settle back',target,1.05,.55)
        notice=target.copy();notice[2]=lerp(target,home,.7)[2]
        add('Notice you · lift the face',notice,.85,.2)
        add('Recover · body follows the face',home,1.9,.15,delays=(.12,0,0))
        add('Thank-you nod',tilt(p,home,down*4,home),.55)
        add('Back with you',home,.8,.3,happy)
    elif kind=='Water':
        target=target or body(p,home,forward*length*.055,length*.015,heading+down*12)
        glance=home.copy();glance[2]=target[2]
        add('Notice the bottle · glance first',glance,.65,.2)
        add('Lean toward its fixed spot',target,1.35,.2,delays=(.12,0,0))
        point=tilt(p,target,down*5,home)
        add('There · a gentle invitation',point,.55,.2,5 if music else 4)
        add('Offer, do not insist',target,.8,1.4)
        back=target.copy();back[2]=home[2]
        add('Look back at you',back,.8,.15)
        add('Relax to rest',home,1.65,.3,delays=(.1,0,0))
    elif kind=='Stretch':
        target=target or body(p,home,-forward*length*.015,-length*.065,heading+up*13)
        dip=body(p,home,0,length*.012,heading+down*3)
        add('Gather a little breath',dip,.8,.2)
        first=dip.copy();first[2]=target[2]
        add('Breathe in · face rises first',first,.85,delays=(0,0,0))
        add('Unfold slowly · reach upward',target,2.4,1.6,7 if music else 6,delays=(.08,0,.18))
        settle=lerp(target,home,.08)
        add('Enjoy the stretch · soften the head',settle,1.0,.5)
        halfway=lerp(target,home,.55)
        add('Breathe out · let the links relax',halfway,1.6,delays=(0,.1,.2))
        add('Settle without snapping back',home,1.6,.15,delays=(0,.05,.12))
        add('Contented little nod',tilt(p,home,down*3,home),.55)
        add('Comfortable again',home,.85,.25,happy)
    else:raise ValueError('Unknown action')
    return rows


def build_compact_gesture(p,roles,kind,music=False,intensity=1.):
    home=p['poses'][roles['Rest']].copy();_,heading=geometry(p,home)
    forward=1 if math.cos(math.radians(heading))>=0 else -1
    down=forward;size=sum(p['lengths'][:2]);rows=[]
    custom=not roles[kind].startswith('Starter ')
    def expressive_body(dx,dy,angle):return body(p,home,dx,dy,angle,reach=420,head_limit=450)
    def turn(pose,delta):return face(p,pose,geometry(p,pose)[1]+delta,home,450)
    def add(name,pose,seconds,pause=0,sound=-1,delays=(0,.04,.08)):
        rows.append(dict(name=name,pulse=lerp(home,pose,intensity),seconds=seconds,pause=pause,sound=sound,easing='quintic',delays=list(delays),gesture_speed=600))
    add('Left-facing home',home,.12)
    if kind=='Slump':
        target=p['poses'][roles[kind]].copy() if custom else expressive_body(-forward*size*.09,size*.17,heading+down*38)
        add('Oh… · the face loses its energy',turn(home,down*22),.4,sound=2 if music else 0)
        add('Body gives in · curl inward and down',target,.95,.45,delays=(.12,0,.18))
        add('Heavy head · one last sag',turn(target,down*6),.3,.2)
        halfway=lerp(target,home,.3)
        add('A reluctant effort to look up',halfway,.45,.12)
        add('Recover · lift the body with relief',home,.95,delays=(.08,0,.12))
        add('A grateful little nod',turn(home,down*5),.24)
        add('Back with you',home,.3)
    elif kind=='Water':
        target=p['poses'][roles[kind]].copy() if custom else expressive_body(forward*size*.19,size*.015,heading+down*6)
        add('Hey! · quick glance toward the bottle',turn(home,down*10),.3)
        add('Reach out · this is for you',target,.85,sound=5 if music else 4,delays=(.12,0,.06))
        add('There! · first pointing nod',turn(target,down*15),.25)
        add('Look at the bottle',target,.3)
        add('Yes, there · a second smaller nod',turn(target,down*10),.24)
        add('Friendly invitation · wait for you',target,.3,.35)
        add('Relax to rest',home,.85,delays=(.1,0,.05))
    elif kind=='Stretch':
        target=p['poses'][roles[kind]].copy() if custom else expressive_body(forward*size*.03,-size*.25,heading-down*43)
        dip=expressive_body(-forward*size*.015,size*.03,heading+down*5)
        add('Gather a breath · small crouch',dip,.4)
        add('Unfold slowly · reach high and open',target,1.1,.4,7 if music else 6,delays=(.08,0,.15))
        add('Aah · lift the face into the stretch',turn(target,-down*5),.3,.3)
        add('Breathe out · release the whole body',lerp(target,home,.55),.7)
        add('Settle softly after the stretch',home,.65)
        add('That felt good · contented nod',turn(home,down*4),.25)
        add('Comfortable again',home,.3)
    else:raise ValueError('Unknown action')
    return rows

def clear_pose(p,pose,side):
    xy,_=geometry(p,pose)
    return all(y<=-8 for x,y in xy[1:]) and xy[-1][0]*side>=20

def clear_path(p,start,row,side):
    duration=trajectory_duration(start,row,600)
    return all(clear_pose(p,sample_motion(start,row,duration*n/40,600)[0],side) for n in range(41))

def broad_pose(p,home,x,y,heading):
    """Search the full configured pulse sector, retaining a clear home path.

    Targets stay 5% inside the electrical edges. This is a stick-model check,
    not a model of servo housings, cables, torque or physical collisions.
    """
    lo=p['config']['low'];hi=p['config']['high'];candidates=[]
    side=1 if geometry(p,home)[0][-1][0]>=0 else -1
    for a in range(lo[0]+100,hi[0]-99,50):
        for b in range(lo[1]+100,hi[1]-99,50):
            pose=face(p,[a,b,home[2]],heading,home,2000)
            pose[2]=max(lo[2]+100,min(hi[2]-100,pose[2]))
            if not clear_pose(p,pose,side):continue
            xy,angle=geometry(p,pose);error=(angle-heading+180)%360-180
            score=(xy[-1][0]-x)**2+(xy[-1][1]-y)**2+2*error**2
            candidates.append((score,pose))
    for _,pose in sorted(candidates):
        row=dict(pulse=pose,seconds=1,delays=[0,.04,.08])
        if clear_path(p,home,row,side):return pose
    return home.copy()

def build_gesture(p,roles,kind,music=False,intensity=1.):
    home=p['poses'][roles['Rest']].copy();xy,heading=geometry(p,home)
    side=1 if xy[-1][0]>=0 else -1;size=sum(p['lengths']);rows=[]
    custom=not roles[kind].startswith('Starter ')
    def target(x,y,angle):return broad_pose(p,home,side*size*x,-size*y,angle)
    def turn(pose,delta):return face(p,pose,geometry(p,pose)[1]+delta,home,2000)
    base=p.get('base_position',{});front=max(0,min(180,base.get('front',90)))
    def yaw(angle):
        angle=max(0,min(180,angle))
        return round(500+(180-angle if base.get('reverse',False) else angle)*2000/180)
    def add(name,pose,seconds,pause=0,sound=-1,delays=(0,.04,.08)):
        row=dict(name=name,pulse=lerp(home,pose,intensity),seconds=seconds,pause=pause,sound=sound,easing='quintic',delays=list(delays),gesture_speed=600)
        start=rows[-1]['pulse'] if rows else home
        # Joint lags can bow the path. Remove lags first; if necessary insert
        # the known home as a bridge instead of silently passing through floor.
        if not custom and clear_pose(p,home,side) and not clear_path(p,start,row,side):
            row['delays']=[0,0,0]
            if not clear_path(p,start,row,side):
                bridge=dict(name='Open through rest',pulse=home.copy(),seconds=1,pause=0,sound=-1,easing='quintic',delays=[0,0,0],gesture_speed=600)
                if clear_path(p,start,bridge,side) and clear_path(p,home,row,side):rows.append(bridge)
                else:row['pulse']=start.copy()
        rows.append(row)
    add('Your calibrated rest',home,.2)
    if kind=='Slump':
        curled=p['poses'][roles[kind]].copy() if custom else target(.3,.15,side*78)
        droop=target(.6,.35,side*85)
        add('Head hangs heavily · silent descent',droop,.55,delays=(.08,.04,0))
        add('Collapse · fold into a deep sad curl',curled,.85,.18,delays=(.04,0,.06))
        add('Relief · recover directly to good posture',home,1.05,sound=3 if music else 1,delays=(0,0,0))
    elif kind=='Water':
        recoil=target(.3,.7,-side*80)
        reach=p['poses'][roles[kind]].copy() if custom else target(.94,.13,side*18)
        point=target(.83,.16,side*80)
        add('Hey! · pull back and look at you',recoil,.65,.08)
        rows[-1]['base_pulse']=yaw(base.get('water_angle',front+90 if front<=90 else front-90))
        add('Look · a big invitation toward the bottle',reach,.9,.1,5 if music else 4,delays=(.06,.02,0))
        add('There! · an emphatic pointing bow',point,.5,.25)
        add('Relax to rest',home,.75)
        rows[-1]['base_pulse']=yaw(front)
    elif kind=='Stretch':
        coil=target(.32,.2,side*70)
        tall=p['poses'][roles[kind]].copy() if custom else target(.08,.98,-side*90)
        open_face=target(.12,.8,-side*15)
        add('Gather a breath · curl all the way in',coil,.65,.12)
        rows[-1]['base_pulse']=yaw(front-15)
        add('Aaaah · unfold into a full tall stretch',tall,1.1,.3,7 if music else 6,delays=(.03,0,.05))
        rows[-1]['base_pulse']=yaw(front+15)
        for n,delta in enumerate((10,-10,8,-6,0)):
            tremble=tall.copy();tremble[2]=max(500,min(2500,tall[2]+delta))
            tremble[1]=max(500,min(2500,tall[1]+round(delta*.6)))
            add('Stretch tremble '+str(n+1),tremble,.13,delays=(0,0,0))
        add('Enjoy it · open the face wide',open_face,.6,.15)
        rows[-1]['base_pulse']=yaw(front-10)
        add('Soft landing · relaxed and happy',home,.85)
        rows[-1]['base_pulse']=yaw(front)
    else:raise ValueError('Unknown action')
    if kind in ('Water','Stretch'):rows[0]['base_pulse']=yaw(front)
    if kind=='Slump':
        for row in rows:row['light_rgb']=[22,8,2]
        rows[0]['light_rgb']=[60,28,8];rows[-1]['light_rgb']=[145,65,18]
    elif kind=='Stretch':
        for i,row in enumerate(rows):
            t=i/max(1,len(rows)-1);row['light_rgb']=lerp([80,125,75],[5,85,20],t)
        rows[-1]['sound']=9
    elif kind=='Water':
        for row in rows:row['light_rgb']=[25,80,130]
        index=next(i for i,row in enumerate(rows) if 'pointing bow' in row['name'])
        point=rows[index];point['light_rgb']=[100,135,150]
        hold=dict(point,name='Water · slow blue-to-white breathing invitation',seconds=3.2,pause=0,
                  sound=-1,light_rgb=[145,150,150],light_breathe=2)
        rows.insert(index+1,hold);rows[-1]['light_rgb']=[90,125,145]
    rows[0]['seconds']=max(rows[0]['seconds'],.7)
    return rows

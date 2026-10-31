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
        add('Oh no… · head hangs heavily',droop,.55,sound=2 if music else 0,delays=(.08,.04,0))
        add('Collapse · fold into a deep sad curl',curled,.85,.18,delays=(.04,0,.06))
        add('Notice you · gather courage',lerp(curled,home,.32),.4,0,delays=(.04,.02,0))
        add('Relief · open back up',home,.8,sound=3 if music else 1,delays=(.05,.02,0))
    elif kind=='Water':
        recoil=target(.3,.7,-side*80)
        reach=p['poses'][roles[kind]].copy() if custom else target(.94,.13,side*18)
        point=target(.83,.16,side*80)
        add('Hey! · pull back and look at you',recoil,.65,.08)
        add('Look · a big invitation toward the bottle',reach,.9,.1,5 if music else 4,delays=(.06,.02,0))
        add('There! · an emphatic pointing bow',point,.5,.25)
        add('Relax to rest',home,.75)
    elif kind=='Stretch':
        coil=target(.32,.2,side*70)
        tall=p['poses'][roles[kind]].copy() if custom else target(.08,.98,-side*90)
        open_face=target(.12,.8,-side*15)
        add('Gather a breath · curl all the way in',coil,.65,.12)
        add('Aaaah · unfold into a full tall stretch',tall,1.1,.3,7 if music else 6,delays=(.03,0,.05))
        add('Enjoy it · open the face wide',open_face,.6,.15)
        add('Soft landing · relaxed and happy',home,.85)
    else:raise ValueError('Unknown action')
    return rows
